# Copyright (c) 2026 xingluosama121, MIT Licensed
"""Agent runtime: the only "loop" in the framework kernel.

The loop depends only on the registry and protocol interfaces; it never imports
any concrete model SDK or tool implementation:

    input (L3) -> session & history (L4) -> message assembly (L5) -> [ step (L6) ->
    model call (L7) -> tool call (L8) ]* -> result finalization (L9)

**Every execution structure is exposed as an API and can be intervened by hooks**:

- hooks: ``runtime.hooks`` (9 layers, 29 hooks; see norpagent.hooks); mutating
  hooks can rewrite the data flow; ``HookVeto`` vetoes with one vote;
- methods: ``prepare_input / create_session / append_message /
  build_messages / call_model / execute_tool_call / finalize_result`` are all
  public methods; subclasses can override them directly without touching the loop body.

The security system is injected through ``registry.security`` (installed by
norpagent.safe()); this file no longer directly depends on norpagent.security —
security has been stripped out as a whole plug.
"""

from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Dict, FrozenSet, List, Optional

from norpagent.arch.address import is_address_like, resolve_address
from norpagent.arch.layer import call_factory
from norpagent.hooks.core import HookVeto
from norpagent.kernel.context import RunContext
from norpagent.kernel.events import EventBus
from norpagent.kernel.presets import Preset
from norpagent.kernel.registry import ComponentError, Registry
from norpagent.loops.cancel import cancel_requested, current_cancel_event
from norpagent.protocols.model import ChatMessage, ModelUsage, ToolCallSpec
from norpagent.protocols.tool import ToolResult, tool_error

if TYPE_CHECKING:
    from norpagent.protocols.sandbox import Sandbox
    from norpagent.protocols.scheduler import TaskScheduler
    from norpagent.protocols.session import SessionManager
    from norpagent.protocols.ui import UIAdapter

# interrupt the task after this many consecutive empty outputs, preventing
# model degradation from causing an infinite loop
_EMPTY_OUTPUT_LIMIT = 3

# keys allowed for task-level slot injection (3.9): consistent with np()'s slot
# parameters, but excluding global / presentation-layer slots (frontend / ui /
# plugins / preset — they are process-level or engine-level structures, outside
# the boundary a single task may override).
TASK_SLOT_KEYS: FrozenSet[str] = frozenset((
    "model", "tools", "sandbox", "session", "scheduler",
    "hooks", "security", "agent_runtime",
    "context_store", "project_manager",
    "async_loop", "logger", "storage", "error_handler",
))


class ModelCallTimeout(Exception):
    """Hard timeout when a single model call exceeds call_timeout.

    Hard-interrupt semantics: the main loop immediately gives up waiting and
    returns a timeout result; the background request thread is marked cancelled
    (params["_cancel_event"]), so the adapter's streaming loop exits as early as
    possible, with the SDK's own connection timeout as the final fallback.
    """

    def __init__(self, timeout: float) -> None:
        super().__init__(f"model call exceeded {timeout}s without finishing (hard-interrupted; background request abandoned)")
        self.timeout = timeout


@dataclass
class RunResult:
    """Complete result of one run()."""

    task_id: str = ""
    session_id: str = ""
    preset_name: str = ""
    status: str = "done"  # done | stopped | error | timeout
    steps: int = 0
    tool_call_count: int = 0
    usage: ModelUsage = field(default_factory=ModelUsage)
    final_content: str = ""
    error: str = ""

    @property
    def ok(self) -> bool:
        return self.status == "done"


def _release_task_layer(task_layer: Any) -> None:
    """Release the task-level slot snapshot layer (idempotent; exceptions never leak).

    Task-level overrides are released together with the RunResult: unsubscribe
    task-period hooks / restore security policy / write back persist sessions /
    close temporary components, leaving no residual state.
    """
    if task_layer is not None:
        try:
            task_layer.close()
        except Exception:  # noqa: BLE001 — a release failure must not mask the task result
            pass


class _TaskSlotLayer:
    """Task-level slot snapshot layer (3.9: ``submit(slot_overrides=...)``).

    - construction (at submit time) snapshots: only copies the override values, no resolution;
    - during the ``run()`` lifecycle, component resolution paths check this layer
      first (lazy resolution + caching); keys not overridden fall back to the
      runtime defaults;
    - ``close()`` releases all temporary resources: task-period hook subscriptions,
      the temporary security policy, temporary session / sandbox / scheduler /
      components, and the optional history write-back (persist).

    Isolation semantics:
    - override values are effective only within this task and are **never written
      to the registry** (tool instances / model providers are held directly by this
      layer and released when the task ends — zero pollution);
    - a later ``np.remount`` does not affect in-flight tasks (the snapshot is
      taken at submit time);
    - a task-level session override builds a temporary session store; with
      persist=False (default) it is discarded when the task ends, without
      polluting the global session table; persist=True writes this task's history
      back into the global session table.
    """

    def __init__(self, registry: Any, overrides: Dict[str, Any],
                 task_id: str, workspace_root: Optional[str] = None) -> None:
        self.registry = registry
        self.overrides: Dict[str, Any] = dict(overrides or {})
        self.task_id = task_id
        self._workspace_root = workspace_root
        # lazy resolution caches
        self._model_provider: Any = None
        self._model_done = False
        self._tool_map: Optional[Dict[str, Any]] = None
        self._tool_names: Optional[List[str]] = None
        self._session_manager: Any = None
        self._sandbox: Any = None
        self._scheduler: Any = None
        self._components: Optional[Dict[str, Any]] = None
        # session persist write-back
        self._global_session_manager: Any = None
        self._persist_session = False
        self._task_session_id: Optional[str] = None
        # lifecycle management
        self._security_kit: Any = None
        self._security_prev: Any = None
        self._subscriptions: List[tuple] = []
        self._owned: List[Any] = []

    # ── lifecycle ─────────────────────────────────────────

    def bind_global_session(self, manager: Any) -> None:
        """Bind the global session manager (the persist write-back target; injected by run())."""
        self._global_session_manager = manager

    def set_task_session_id(self, session_id: str) -> None:
        """Record the session id actually used by this task (needed by persist write-back)."""
        self._task_session_id = session_id

    def activate(self) -> None:
        """At task start: subscribe task-level hooks and temporarily install the security policy."""
        hooks = self._parse_hooks(self.overrides.get("hooks"))
        if hooks:
            for hook_name, fn in hooks.items():
                try:
                    self.registry.bus.subscribe(fn, hook_name)
                    self._subscriptions.append((fn, hook_name))
                except Exception:  # noqa: BLE001 — a single hook failure must not block the task
                    pass
        security = self.overrides.get("security")
        if security is not None:
            self._security_prev = getattr(self.registry, "security", None)
            self._security_kit = self._install_security(security)

    def close(self) -> None:
        """At task end: release all temporary resources (released together with the RunResult)."""
        # 1. unsubscribe task-period hook subscriptions
        for fn, hook_name in self._subscriptions:
            try:
                self.registry.bus.unsubscribe(fn, hook_name)
            except Exception:  # noqa: BLE001
                pass
        self._subscriptions.clear()
        # 2. restore the security policy (uninstall the temporary kit → restore the original registry.security)
        if self._security_kit is not None:
            try:
                self._security_kit.uninstall(self.registry)
            except Exception:  # noqa: BLE001
                pass
            self._security_kit = None
        self.registry.security = self._security_prev
        # 3. persist: write the temporary session history back into the global session table (explicit persist=True)
        if self._persist_session and self._task_session_id:
            self._persist_messages()
        # 4. close temporarily built components (reverse order; dependencies close first)
        for obj in reversed(self._owned):
            closer = getattr(obj, "close", None)
            if callable(closer):
                try:
                    closer()
                except Exception:  # noqa: BLE001
                    pass
        self._owned.clear()
        # 5. drop references (the task layer is released with the RunResult; no residual state)
        self._model_provider = None
        self._model_done = False
        self._tool_map = None
        self._tool_names = None
        self._session_manager = None
        self._sandbox = None
        self._scheduler = None
        self._components = None

    # ── component resolution (lazy; this layer first) ────

    @property
    def model_provider(self) -> Any:
        """Resolution result of the task-level model override; None when not overridden."""
        if self._model_done:
            return self._model_provider
        self._model_done = True
        value = self.overrides.get("model")
        if value is None:
            return None
        resolved = self._resolve_component_value(value, "model")
        if isinstance(resolved, str):  # registered-name reference
            self._model_provider = self.registry.resolve_model(resolved)
        else:
            self._model_provider = resolved
        return self._model_provider

    @property
    def tool_names(self) -> Optional[List[str]]:
        """Tool-name list of the task-level tools override; None when not overridden."""
        if self._tool_names is None and self.overrides.get("tools") is not None:
            self._parse_tools()
        return self._tool_names

    def tool_schemas(self) -> Optional[List[Dict[str, Any]]]:
        """Schema list of the task-level tools override; None when not overridden."""
        if self._tool_map is None and self.overrides.get("tools") is not None:
            self._parse_tools()
        if self._tool_map is None:
            return None
        return [t.schema() for t in self._tool_map.values()]

    def resolve_tool(self, name: str) -> Any:
        """Task-level tool resolution (execute_tool_call checks this layer first)."""
        if self._tool_map is None and self.overrides.get("tools") is not None:
            self._parse_tools()
        if self._tool_map is None:
            return None
        return self._tool_map.get(name)

    @property
    def session_manager(self) -> Any:
        """Task-level session override: a standalone temporary session store (persist optional)."""
        if self._session_manager is not None:
            return self._session_manager
        value = self.overrides.get("session")
        if value is None:
            return None
        persist = False
        if isinstance(value, dict):
            persist = bool(value.get("persist", False))
            value = (value.get("name") or value.get("impl")
                     or value.get("value"))
        resolved = self._resolve_component_value(value, "session")
        if isinstance(resolved, str):  # registered-name reference
            self._session_manager = self.registry.build_session(resolved)
        else:
            self._session_manager = resolved
        self._persist_session = persist
        self._owned.append(self._session_manager)
        return self._session_manager

    @property
    def sandbox(self) -> Any:
        """Task-level sandbox override: a standalone temporary sandbox."""
        if self._sandbox is not None or self.overrides.get("sandbox") is None:
            return self._sandbox
        resolved = self._resolve_component_value(
            self.overrides["sandbox"], "sandbox")
        if isinstance(resolved, str):  # registered-name reference
            self._sandbox = self.registry.build_sandbox(resolved)
        else:
            self._sandbox = resolved
        self._owned.append(self._sandbox)
        return self._sandbox

    @property
    def scheduler(self) -> Any:
        """Task-level scheduler override: a standalone temporary scheduler."""
        if self._scheduler is not None or self.overrides.get("scheduler") is None:
            return self._scheduler
        resolved = self._resolve_component_value(
            self.overrides["scheduler"], "scheduler")
        if isinstance(resolved, str):  # registered-name reference
            self._scheduler = self.registry.build_scheduler(resolved)
        else:
            self._scheduler = resolved
        self._owned.append(self._scheduler)
        return self._scheduler

    @property
    def components(self) -> Dict[str, Any]:
        """Task-level generic-component overrides (context_store / project_manager)."""
        if self._components is not None:
            return self._components
        comps: Dict[str, Any] = {}
        for slot, kind in (("context_store", "context_store"),
                           ("project_manager", "project_manager")):
            value = self.overrides.get(slot)
            if value is None:
                continue
            resolved = self._resolve_component_value(value, slot)
            if isinstance(resolved, str):  # registered component-name reference
                instance = self.registry.build_component(
                    kind, resolved, workspace_root=self._workspace_root)
            else:
                instance = resolved
            comps[kind] = instance
            self._owned.append(instance)
        self._components = comps
        return self._components

    # ── internals ─────────────────────────────────────────

    def _factory_ctx(self) -> Dict[str, Any]:
        """Factory-calling context for address-style / factory-style override values (injected by signature)."""
        ctx: Dict[str, Any] = {
            "registry": self.registry,
            "task_id": self.task_id,
        }
        if self._workspace_root is not None:
            ctx["workspace_root"] = self._workspace_root
        storage = self.overrides.get("storage")
        if storage is not None:
            ctx["storage"] = storage
        return ctx

    def _resolve_component_value(self, value: Any, slot: str) -> Any:
        """Resolve a slot value: module address / factory / instance; registered-name strings pass through."""
        if isinstance(value, str):
            if is_address_like(value):
                impl = resolve_address(value, slot=slot)
                if callable(impl):
                    return call_factory(impl, self._factory_ctx())
                return impl
            return value  # registered-name reference; handled by the caller per slot semantics
        if callable(value):
            return call_factory(value, self._factory_ctx())
        return value

    def _parse_tools(self) -> None:
        """Parse the task-level tools override into {name: Tool} (instances held directly; zero registration)."""
        value = self.overrides["tools"]
        names: List[str] = []
        tool_map: Dict[str, Any] = {}
        if isinstance(value, dict):
            for tname, tval in value.items():
                resolved = self._resolve_component_value(tval, "tools")
                if isinstance(resolved, str):  # registered-name reference
                    tool = self.registry.resolve_tool(resolved)
                else:
                    tool = resolved
                tool_map[tname] = tool
                names.append(tname)
        else:
            items = value if isinstance(value, (list, tuple)) else [value]
            for item in items:
                resolved = self._resolve_component_value(item, "tools")
                if isinstance(resolved, str):  # registered-name reference
                    tool = self.registry.resolve_tool(resolved)
                    tool_map[resolved] = tool
                    names.append(resolved)
                else:
                    tname = (getattr(resolved, "name", "")
                             or resolved.__class__.__name__)
                    tool_map[tname] = resolved
                    names.append(tname)
        self._tool_map = tool_map
        self._tool_names = names

    def _parse_hooks(self, value: Any) -> Optional[Dict[str, Any]]:
        """Parse the task-level hooks override: {hook name: callback} or callable(registry)."""
        if value is None:
            return None
        if callable(value) and not isinstance(value, dict):
            try:
                value = value(self.registry)  # callable(registry) returns subscription config
            except Exception:  # noqa: BLE001 — parse failures count as no hooks
                return None
        if isinstance(value, dict):
            return dict(value)
        return None

    def _install_security(self, value: Any) -> Any:
        """Temporarily install the task-level security policy; returns an uninstallable SafetyKit (or None)."""
        from norpagent.safe import SecurityContext

        if isinstance(value, str):
            from norpagent import safe

            return safe(self.registry, level=value)
        if isinstance(value, dict):
            from norpagent import safe

            return safe(
                self.registry,
                level=value.get("level", "standard"),
                config=value.get("config"),
                hooks=value.get("hooks"),
            )
        if callable(value) and not isinstance(value, SecurityContext):
            value(self.registry)  # callable form manages registry.security itself
            return None
        self.registry.security = value
        return None

    def _persist_messages(self) -> None:
        """persist=True: write the temporary session history back into the global session table (best effort)."""
        sm = self._session_manager
        gsm = self._global_session_manager
        sid = self._task_session_id
        if sm is None or gsm is None or not sid:
            return
        try:
            msgs = sm.history(sid)
            if gsm.get_session(sid) is None:
                gsm.create_session(
                    title=f"task-{self.task_id}", session_id=sid)
            for m in msgs:
                gsm.append_message(sid, m)
        except Exception:  # noqa: BLE001 — write-back failures never bubble up
            pass


class AgentRuntime:
    """Generic agent runtime.

    Usage::

        reg = Registry(); install_defaults(reg); register_all_presets(reg)
        agent = AgentRuntime(reg, preset="minimal")
        result = agent.run("hello")

    ``session_manager`` / ``sandbox`` / ``scheduler`` / ``ui`` can all be passed
    from outside to override the preset declarations (for testing and A/B
    comparison; also the benchmark entry). ``components`` likewise:
    {kind: instance}, overriding the preset's declared component assembly.
    """

    def __init__(
        self,
        registry: Registry,
        preset: Preset | str,
        session_manager: Optional["SessionManager"] = None,
        sandbox: Optional["Sandbox"] = None,
        scheduler: Optional["TaskScheduler"] = None,
        ui: Optional["UIAdapter"] = None,
        task_params: Optional[Dict[str, Any]] = None,
        components: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.registry = registry
        self.bus: EventBus = registry.bus
        self.hooks = registry.hooks  # 9-layer hook system (HookSystem)
        self.preset = registry.resolve_preset(preset) if isinstance(preset, str) else preset

        # component availability validation: actionable errors on missing parts
        missing, missing_tools = registry.validate_preset(self.preset)
        if missing or missing_tools:
            parts = missing + [f"tools={t}" for t in missing_tools]
            raise ComponentError(
                f"preset mode '{self.preset.name}' is missing components: {', '.join(parts)}. "
                f"Available models {registry.list_models()} / tools {registry.list_tools()}. "
                "Some modes' components ship with optional dependencies (e.g. norpagent[openai]); see README."
            )

        self.params = self.preset.merged_params(task_params)
        self.session_manager = session_manager or registry.build_session(self.preset.session)
        self.sandbox = sandbox if sandbox is not None else registry.build_sandbox(self.preset.sandbox)
        self.scheduler = scheduler if scheduler is not None else registry.build_scheduler(self.preset.scheduler)
        self.ui = ui if ui is not None else registry.resolve_ui(self.preset.ui)

        # generic component assembly: the preset declares components={kind: name};
        # the runtime builds them by name. Instances are shared across the whole
        # runtime lifecycle (context store / project management etc.). External
        # injection takes priority (testing / dependency injection scenarios).
        if components is not None:
            self.components: Dict[str, Any] = dict(components)
        else:
            workspace_hint = self.params.get("workspace_root") or None
            self.components = {
                kind: registry.build_component(kind, name, workspace_root=workspace_hint)
                for kind, name in (self.preset.components or {}).items()
            }

        # mount the UI as an event subscriber (unsubscribed at shutdown to avoid
        # duplicate output on the shared bus)
        self._ui_listener: Optional[Callable] = None
        if self.ui is not None and hasattr(self.ui, "on_event"):
            self._ui_listener = self.ui.on_event
            self.bus.subscribe(self._ui_listener)

        # background threads left over from call_timeout hard interrupts (daemon); reaped at shutdown
        self._orphan_threads: List[threading.Thread] = []

        self.hooks.on_agent_init.emit(preset=self.preset.name)

    # ══════════════════════════════════════════════════════
    #  main loop
    # ══════════════════════════════════════════════════════

    def run(
        self,
        user_input: str,
        session_id: Optional[str] = None,
        task_id: Optional[str] = None,
        task_params: Optional[Dict[str, Any]] = None,
        slot_overrides: Optional[Dict[str, Any]] = None,
    ) -> RunResult:
        """Execute one user task.

        - input goes through the L3 pipeline (rewritable / vetoable / security-scanned)
        - a session is created or resumed (L4); the user input is written to history
        - at most ``max_steps`` rounds of the L6-L8 loop
        - reaching ``task_timeout`` triggers on_task_timeout and stops
        - all paths return through the L9 result-finalization hook

        ``slot_overrides`` (v0.9.2, task-level slot injection; see manual 3.9):
        snapshotted at submit time; temporarily overrides any slot implementation
        during this task (model / tools / sandbox / session / scheduler / hooks /
        security / context_store / project_manager / logger / storage /
        error_handler); never written to the registry; does not affect other
        in-flight tasks; released together with the RunResult when the task ends.
        """
        task_id = task_id or uuid.uuid4().hex[:12]
        # construction-level task_params are the runtime defaults; task-level task_params override them
        params = dict(self.params)
        if task_params:
            params.update(task_params)
        # ── task-level slot injection (3.9): the submit(slot_overrides=...)
        #    snapshot layer. The snapshot is taken at submit time; later global
        #    remounts do not affect in-flight tasks.
        task_layer = None
        if slot_overrides:
            task_layer = _TaskSlotLayer(
                self.registry, slot_overrides, task_id,
                workspace_root=params.get("workspace_root"),
            )
            task_layer.bind_global_session(self.session_manager)
            task_layer.activate()
            # task-level semantics of storage / logger / error_handler = task
            # parameter injection (readable by component factories / hooks), not
            # replacing the engine's global references (so concurrent tasks never
            # trample engine-level objects).
            for key in ("storage", "logger", "error_handler"):
                if key in slot_overrides:
                    params[key] = slot_overrides[key]
        # Ctrl+C / engine-stop cancel event injected into params:
        # model streaming loops (also effective with call_timeout=0) and tools
        # check params["_cancel_event"] / cancel_requested() and exit early.
        cancel_event = params.get("_cancel_event")
        if not isinstance(cancel_event, threading.Event):
            cancel_event = current_cancel_event()
        if isinstance(cancel_event, threading.Event):
            params["_cancel_event"] = cancel_event
        # drop dead orphan-thread references from timeouts to prevent long-run memory accumulation
        if self._orphan_threads:
            self._orphan_threads = [
                t for t in self._orphan_threads if t.is_alive()
            ]
        result = RunResult(task_id=task_id, preset_name=self.preset.name)
        start_ts = time.time()

        # ── L3 input pipeline: before_input can rewrite / veto ──
        try:
            user_input = self.prepare_input(
                user_input, task_id=task_id, session_id=session_id, params=params
            )
        except HookVeto as veto:
            result.status = "stopped"
            result.error = str(veto)
            self.hooks.on_task_stopped.emit(task_id=task_id, reason=str(veto))
            _release_task_layer(task_layer)
            return self.finalize_result(result, task_id)

        # ── jailbreak / injection protection (the params["jailbreak_guard"]
        #    explicit path; norpagent.safe()'s hook path only takes effect at
        #    before_input when the user explicitly enables it (hooks=True /
        #    install_hooks)) ──
        guard_config = params.get("jailbreak_guard")
        if guard_config:
            from norpagent.security.guard import scan_message

            blocked, reason, _ = scan_message(user_input)
            if blocked:
                result.status = "stopped"
                result.error = reason or "input blocked by security protection"
                self.hooks.on_task_stopped.emit(
                    task_id=task_id,
                    reason="jailbreak_guard", detail=reason,
                )
                _release_task_layer(task_layer)
                return self.finalize_result(result, task_id)

        # ── system prompt hardening (params explicit path) ──
        system_prompt = params.get("system_prompt", "") or ""
        if params.get("harden_prompt"):
            from norpagent.security.guard import harden_system_prompt

            system_prompt = harden_system_prompt(
                system_prompt, self.preset.tools
            )

        # ── L4 session preparation (task-level session override → standalone temporary session store) ──
        if task_layer is not None and task_layer.session_manager is not None:
            session_manager = task_layer.session_manager
        else:
            session_manager = self.session_manager
        try:
            sess = None
            if session_id:
                sess = session_manager.get_session(session_id)
            if sess is None:
                sess = self.create_session(
                    candidate_id=session_id,
                    title=user_input[:40],
                    params=params,
                    task_id=task_id,
                    session_manager=session_manager,
                )
            result.session_id = sess.id
            if task_layer is not None:
                task_layer.set_task_session_id(sess.id)
            self.append_message(
                session_manager, sess.id,
                ChatMessage(role="user", content=user_input),
                task_id,
            )
        except HookVeto as veto:
            result.status = "stopped"
            result.error = str(veto)
            self.hooks.on_task_stopped.emit(task_id=task_id, reason=str(veto))
            _release_task_layer(task_layer)
            return self.finalize_result(result, task_id)

        # task-level overridden sandbox / scheduler / generic components (otherwise the runtime defaults)
        if task_layer is not None and task_layer.sandbox is not None:
            sandbox = task_layer.sandbox
        else:
            sandbox = self.sandbox
        if task_layer is not None and task_layer.scheduler is not None:
            scheduler = task_layer.scheduler
        else:
            scheduler = self.scheduler
        if task_layer is not None and task_layer.components:
            components = dict(self.components)
            components.update(task_layer.components)
        else:
            components = self.components

        ctx = RunContext(
            registry=self.registry,
            session_manager=session_manager,
            session_id=sess.id,
            sandbox=sandbox,
            scheduler=scheduler,
            ui=self.ui,
            params=params,
            task_id=task_id,
            preset_name=self.preset.name,
            components=components,
            task_slot_layer=task_layer,
            slot_overrides=dict(slot_overrides or {}),
        )

        self.hooks.on_task_start.emit(
            task_id=task_id,
            session_id=sess.id,
            preset=self.preset.name,
            user_input=user_input,
        )

        max_steps = int(params.get("max_steps", 32))
        task_timeout = float(params.get("task_timeout", 0) or 0)
        # component resolution path: the task-level slot layer first (3.9), then
        # the runtime defaults. Task-level model / tools overrides are lazily
        # resolved and held by _TaskSlotLayer, never written to the registry —
        # concurrent tasks do not interfere; released when the task ends.
        if task_layer is not None and task_layer.model_provider is not None:
            model_provider = task_layer.model_provider
        else:
            model_provider = self.registry.resolve_model(self.preset.model)
        if task_layer is not None and task_layer.tool_names is not None:
            tool_names = task_layer.tool_names
            tool_schemas = task_layer.tool_schemas()
        else:
            tool_names = list(self.preset.tools)
            tool_schemas = self.registry.tool_schemas(tool_names)

        # user stop check (a callable injected by the Web frontend "stop" button
        # etc.): checked at every turn boundary; True ends the task as stopped.
        stop_check = params.get("_stop_check")

        empty_streak = 0
        try:
            for step in range(1, max_steps + 1):
                # Ctrl+C / engine stop: cancel event set → wrap up immediately at
                # this turn boundary (blocking model calls / sandbox commands are
                # interrupted by their own cancellation checks)
                if cancel_requested():
                    result.status = "stopped"
                    result.error = "task interrupted (Ctrl+C)"
                    self.hooks.on_task_stopped.emit(
                        task_id=task_id, reason=result.error,
                    )
                    break
                if callable(stop_check):
                    try:
                        should_stop = bool(stop_check())
                    except Exception:  # noqa: BLE001 — a broken checker must not terminate the task
                        should_stop = False
                    if should_stop:
                        result.status = "stopped"
                        result.error = "task stopped by the user"
                        self.hooks.on_task_stopped.emit(
                            task_id=task_id, reason=result.error,
                        )
                        break
                # the task-level timeout check sits at turn boundaries. Hard
                # interruption while a single model call is blocked is controlled
                # by the call_timeout parameter (see call_model).
                if task_timeout and (time.time() - start_ts) > task_timeout:
                    result.status = "timeout"
                    result.error = f"task did not finish within {task_timeout}s"
                    self.hooks.on_task_timeout.emit(
                        task_id=task_id, timeout=task_timeout,
                        kind="task_timeout",
                    )
                    break

                # ── L5 message assembly ──
                history = self.build_messages(
                    system_prompt, sess.id, step=step, task_id=task_id,
                    tool_names=list(tool_names),
                    session_manager=session_manager,
                )

                # ── L6 before_step: can rewrite this round's messages / skip the round ──
                self.hooks.before_step.emit(
                    task_id=task_id, step=step,
                    context=ctx, params=params,
                )
                try:
                    modified = self.hooks.before_step.intercept(
                        task_id=task_id, step=step,
                        messages=history, context=ctx, params=params,
                    )
                except HookVeto:
                    continue  # hook vetoed this round: skip the model call
                if isinstance(modified, list):
                    history = modified

                # ── L7 model call ──
                output = self.call_model(
                    model_provider, history, tool_schemas, params,
                    task_id, result, step,
                )

                result.steps = step
                content = (output.content or "").strip()
                tool_calls = output.tool_calls or []

                if content:
                    empty_streak = 0
                    self.hooks.on_content.emit(
                        task_id=task_id, content=content,
                        stream=False, final=(not tool_calls),
                    )

                if tool_calls:
                    self.hooks.after_step.emit(
                        task_id=task_id, step=step,
                        content=content, tool_calls=len(tool_calls),
                    )
                    # record the assistant message (including tool-call intent and
                    # chain-of-thought text; reasoning endpoints like DeepSeek V4
                    # require verbatim reasoning_content echo on tool-call turns)
                    self.append_message(
                        session_manager, sess.id,
                        ChatMessage(
                            role="assistant", content=content,
                            tool_calls=tool_calls,
                            reasoning=getattr(output, "reasoning", "") or "",
                            has_reasoning=bool(getattr(output, "has_reasoning", False)),
                        ),
                        task_id,
                    )
                    for spec in tool_calls:
                        tool_result = self.execute_tool_call(spec, ctx, task_id)
                        result.tool_call_count += 1
                        self.append_message(
                            session_manager, sess.id,
                            ChatMessage(
                                role="tool",
                                content=str(tool_result),
                                tool_call_id=spec.id,
                                name=spec.name,
                            ),
                            task_id,
                        )
                    continue  # continue to the next round; wait for the model to digest tool results

                # no tool calls: treat the model output as the final reply
                empty_streak = empty_streak + 1 if not content else 0
                if not content and empty_streak >= _EMPTY_OUTPUT_LIMIT:
                    result.status = "stopped"
                    result.error = "model produced no output for several consecutive rounds; task interrupted"
                    self.hooks.on_task_stopped.emit(
                        task_id=task_id, reason=result.error,
                    )
                    break
                if not content:
                    continue

                result.final_content = content
                self.append_message(
                    session_manager, sess.id,
                    ChatMessage(
                        role="assistant", content=content,
                        reasoning=getattr(output, "reasoning", "") or "",
                        has_reasoning=bool(getattr(output, "has_reasoning", False)),
                    ),
                    task_id,
                )
                self.hooks.on_task_done.emit(
                    task_id=task_id, session_id=sess.id,
                    content=content, steps=step, context=ctx,
                )
                return self.finalize_result(result, task_id)

            # loop exhausted (step cap reached)
            if result.status not in ("timeout", "stopped"):
                result.status = "stopped"
                result.error = f"reached the step cap max_steps={max_steps}"
                self.hooks.on_task_stopped.emit(
                    task_id=task_id, reason=result.error,
                )
        except HookVeto as veto:
            # hook veto mid-stream (before_model_call / before_session_create etc.)
            result.status = "stopped"
            result.error = str(veto)
            self.hooks.on_task_stopped.emit(task_id=task_id, reason=str(veto))
        except ModelCallTimeout as exc:
            # hard timeout of a model call: the task terminates immediately
            result.status = "timeout"
            result.error = str(exc)
            self.hooks.on_task_timeout.emit(
                task_id=task_id, timeout=exc.timeout,
                kind="call_timeout",
            )
        except Exception as exc:  # noqa: BLE001 — task-level fallback, guaranteeing the event loop closes
            result.status = "error"
            result.error = f"{type(exc).__name__}: {exc}"
            self.hooks.on_task_error.emit(task_id=task_id, error=result.error)
        finally:
            # the task-level slot layer is released together with the RunResult
            # (normal / stopped / timeout / error alike)
            _release_task_layer(task_layer)

        if result.final_content:
            self.hooks.on_task_done.emit(
                task_id=task_id, content=result.final_content,
            )
        return self.finalize_result(result, task_id)

    # ══════════════════════════════════════════════════════
    #  execution-structure APIs (each step independently overridable / hookable)
    # ══════════════════════════════════════════════════════

    # ── L3 input ──────────────────────────────────────────

    def prepare_input(
        self,
        user_input: str,
        *,
        task_id: str,
        session_id: Optional[str],
        params: Dict[str, Any],
    ) -> str:
        """L3 input handling: before_input mutating hook + after_input observation.

        Returns str = the final input; raising HookVeto = the task ends as stopped.
        """
        modified = self.hooks.before_input.intercept(
            task_id=task_id, user_input=user_input,
            session_id=session_id, params=params,
        )
        if isinstance(modified, str):
            user_input = modified
        self.hooks.after_input.emit(
            task_id=task_id, user_input=user_input, session_id=session_id,
        )
        return user_input

    # ── L4 session & history ──────────────────────────────

    def create_session(
        self,
        *,
        candidate_id: Optional[str],
        title: str,
        params: Dict[str, Any],
        task_id: str,
        session_manager: Any = None,
    ) -> Any:
        """L4 session creation: before/after_session_create hooks; the title is rewritable.

        When ``candidate_id`` exists, prefer reusing it (idempotent resume): the
        session id passed in by the browser / host and the id finally used by the
        kernel stay identical, so the event stream (thinking / replies / task end)
        routes correctly per frontend tab instead of drifting into a second session.
        ``session_manager`` defaults to the runtime's; with a task-level session
        override, run() injects the standalone temporary session store (3.9).
        """
        sm = session_manager or self.session_manager
        modified = self.hooks.before_session_create.intercept(
            session_id=candidate_id, title=title, params=params, task_id=task_id,
        )
        if isinstance(modified, str):
            title = modified
        elif isinstance(modified, dict) and isinstance(modified.get("title"), str):
            title = modified["title"]
        if candidate_id:
            existing = sm.get_session(candidate_id)
            if existing is not None:
                sess = existing
            else:
                sess = sm.create_session(
                    title=title, session_id=candidate_id)
        else:
            sess = sm.create_session(title=title)
        self.hooks.after_session_create.emit(
            session_id=sess.id, title=title, task_id=task_id,
        )
        return sess

    def append_message(
        self,
        session_manager: Any,
        session_id: str,
        message: ChatMessage,
        task_id: str,
    ) -> bool:
        """L4 message persistence: before_message_append can replace/drop; after is observable.

        Returns whether the message was actually persisted. A hook returning False
        or raising HookVeto = drop this message.
        """
        try:
            modified = self.hooks.before_message_append.intercept(
                session_id=session_id, message=message, task_id=task_id,
            )
        except HookVeto:
            return False
        if modified is False:
            return False
        if modified is not None and getattr(modified, "role", None):
            message = modified
        session_manager.append_message(session_id, message)
        self.hooks.after_message_append.emit(
            session_id=session_id, message=message, task_id=task_id,
        )
        return True

    # ── L5 message assembly ──────────────────────────────

    def build_messages(
        self,
        system_prompt: str,
        session_id: str,
        *,
        step: int,
        task_id: str,
        tool_names: Optional[List[str]] = None,
        session_manager: Any = None,
    ) -> List[ChatMessage]:
        """L5 message assembly: system prompt + history merge; both-end hooks are rewritable.

        ``session_manager`` defaults to the runtime's; with a task-level session
        override, run() injects the standalone temporary session store (3.9).
        """
        try:
            modified = self.hooks.before_build_messages.intercept(
                system_prompt=system_prompt, session_id=session_id,
                step=step, task_id=task_id,
                tool_names=list(tool_names or []),
            )
        except HookVeto:
            modified = None
        if isinstance(modified, str):
            system_prompt = modified
        elif isinstance(modified, dict) and isinstance(modified.get("system_prompt"), str):
            system_prompt = modified["system_prompt"]

        history = list((session_manager or self.session_manager).history(session_id))
        messages = (
            [ChatMessage(role="system", content=system_prompt)] + history
            if system_prompt else history
        )
        try:
            modified2 = self.hooks.after_build_messages.intercept(
                messages=messages, system_prompt=system_prompt,
                step=step, task_id=task_id,
            )
        except HookVeto:
            modified2 = None
        if isinstance(modified2, list):
            messages = modified2
        return messages

    # ── L7 model call ─────────────────────────────────────

    def call_model(
        self,
        model_provider: Any,
        history: List[ChatMessage],
        tool_schemas: List[Dict[str, Any]],
        params: Dict[str, Any],
        task_id: str,
        result: RunResult,
        step: int,
    ):
        """L7 model call: before/after_model_call hooks + call_timeout hard interrupt."""
        try:
            modified = self.hooks.before_model_call.intercept(
                task_id=task_id, step=step,
                messages=history, tool_schemas=tool_schemas, params=params,
            )
        except HookVeto as veto:
            raise veto  # the main loop catches it and wraps up as stopped
        if isinstance(modified, dict):
            if isinstance(modified.get("messages"), list):
                history = modified["messages"]
            if isinstance(modified.get("params"), dict):
                params = modified["params"]

        output = self._call_model_with_timeout(
            model_provider, history, tool_schemas, params, task_id, result, step
        )

        try:
            modified2 = self.hooks.after_model_call.intercept(
                task_id=task_id, step=step, output=output,
            )
        except HookVeto:
            modified2 = None
        if modified2 is not None and hasattr(modified2, "content"):
            output = modified2
        return output

    def _call_model_with_timeout(
        self,
        model_provider: Any,
        history: List[ChatMessage],
        tool_schemas: List[Dict[str, Any]],
        params: Dict[str, Any],
        task_id: str,
        result: RunResult,
        step: int,
    ):
        """call_timeout blocking hard-interrupt scheduling (see ModelCallTimeout)."""
        call_timeout = float(params.get("call_timeout", 0) or 0)
        if call_timeout <= 0:
            # no timeout requirement: synchronous call (zero thread overhead).
            # the cancel event (Ctrl+C / engine stop) still works: the model
            # streaming loop checks _cancel_event and exits early, never waiting
            # for the SDK's timeout fallback.
            cancel_ev = params.get("_cancel_event")
            return self._call_model_impl(
                model_provider, history, tool_schemas, params, task_id, result,
                cancel_ev if isinstance(cancel_ev, threading.Event) else None,
            )

        cancel_event = threading.Event()
        call_params = dict(params)
        call_params["_cancel_event"] = cancel_event
        box: Dict[str, Any] = {}

        def worker() -> None:
            try:
                box["output"] = self._call_model_impl(
                    model_provider, history, tool_schemas, call_params,
                    task_id, result, cancel_event,
                )
            except Exception as exc:  # noqa: BLE001 — exceptions relay back to the main thread
                box["error"] = exc

        thread = threading.Thread(
            target=worker, daemon=True, name=f"norpagent-model-{task_id[:8]}"
        )
        thread.start()
        thread.join(call_timeout)
        if thread.is_alive():
            cancel_event.set()
            self._orphan_threads.append(thread)
            raise ModelCallTimeout(call_timeout)
        if "error" in box:
            raise box["error"]
        return box["output"]

    def _call_model_impl(
        self,
        model_provider: Any,
        history: List[ChatMessage],
        tool_schemas: List[Dict[str, Any]],
        params: Dict[str, Any],
        task_id: str,
        result: RunResult,
        cancel_event: Optional[threading.Event],
    ):
        """Actual model-call body (streaming preferred; deltas aggregated and broadcast per segment).

        When ``cancel_event`` is non-None and set, production stops (no more
        events emitted), so a post-timeout background thread exits silently as
        soon as possible, preventing orphan output from polluting the UI.
        """

        def _abandoned() -> bool:
            return cancel_event is not None and cancel_event.is_set()

        from norpagent.protocols.model import ModelOutput

        stream = getattr(model_provider, "stream", None)
        if stream is not None:
            content_parts: List[str] = []
            reasoning_parts: List[str] = []
            has_reasoning = False
            tool_map: Dict[str, ToolCallSpec] = {}
            usage = ModelUsage()
            finish = ""
            for chunk in stream(history, tool_schemas or None, params):
                if _abandoned():
                    return ModelOutput()
                if chunk.has_reasoning:
                    has_reasoning = True
                if chunk.reasoning:
                    reasoning_parts.append(chunk.reasoning)
                    self.hooks.on_reasoning.emit(
                        task_id=task_id, content=chunk.reasoning, stream=True,
                    )
                if chunk.delta_content:
                    content_parts.append(chunk.delta_content)
                    self.hooks.on_content.emit(
                        task_id=task_id, content=chunk.delta_content,
                        stream=True, final=False,
                    )
                if chunk.tool_call_delta:
                    tool_map[chunk.tool_call_delta.id] = chunk.tool_call_delta
                if chunk.usage:
                    usage = chunk.usage
                if chunk.finish_reason:
                    finish = chunk.finish_reason
            if _abandoned():
                return ModelOutput()
            self._accumulate_usage(result, usage, task_id)
            return ModelOutput(
                content="".join(content_parts),
                reasoning="".join(reasoning_parts),
                has_reasoning=has_reasoning,
                tool_calls=list(tool_map.values()) if tool_map else None,
                usage=usage,
                finish_reason=finish or ("tool_calls" if tool_map else "stop"),
            )
        output = model_provider.generate(history, tool_schemas or None, params)
        if _abandoned():
            return ModelOutput()
        if getattr(output, "reasoning", ""):
            # non-streaming output: the whole chain of thought is broadcast as one delta
            self.hooks.on_reasoning.emit(
                task_id=task_id, content=output.reasoning, stream=False,
            )
        self._accumulate_usage(result, output.usage, task_id)
        return output

    def _accumulate_usage(self, result: RunResult, usage: Any, task_id: str) -> None:
        if not usage:
            return
        result.usage.input_tokens += usage.input_tokens or 0
        result.usage.output_tokens += usage.output_tokens or 0
        result.usage.total_tokens += usage.total_tokens or (
            usage.input_tokens or 0
        ) + (usage.output_tokens or 0)
        self.hooks.on_usage_update.emit(
            task_id=task_id,
            input=result.usage.input_tokens,
            output=result.usage.output_tokens,
            total=result.usage.total_tokens,
        )

    # ── L8 tool call ──────────────────────────────────────

    def execute_tool_call(
        self, spec: ToolCallSpec, ctx: RunContext, task_id: str
    ) -> ToolResult:
        """L8 tool call: argument rewriting / veto / approval / execution / result rewriting.

        All paths (including blocked, vetoed and approval-denied) uniformly flow
        through the after_tool_call hook — an "execution structure" passes through
        the hook regardless of the outcome.
        """
        self.hooks.before_tool_call.emit(
            task_id=task_id,
            tool_name=spec.name, args=spec.arguments, context=ctx,
        )
        result: Optional[ToolResult] = None

        # mutating hook: modify arguments (dict), block the call (False), veto (HookVeto)
        try:
            modified = self.hooks.before_tool_call.intercept(
                task_id=task_id,
                tool_name=spec.name, args=spec.arguments, context=ctx,
            )
        except HookVeto as veto:
            result = ToolResult(
                output=f"tool call vetoed by a hook: {veto.reason}",
                success=False,
                error=f"blocked_by_hook: {veto.reason}",
            )
        if result is None:
            if modified is False:
                result = ToolResult(
                    output="tool call blocked by a plugin hook (before_tool_call).",
                    success=False,
                    error="blocked_by_hook",
                )
            elif isinstance(modified, dict):
                spec.arguments = modified

        # human approval (explicit params policy first; then registry.security)
        if result is None:
            result = self._check_approval(spec, ctx)

        if result is None:
            try:
                # tool resolution path: the task-level tools override first (3.9),
                # then the registry (runtime defaults / global remount results).
                tool = None
                task_layer = getattr(ctx, "task_slot_layer", None)
                if task_layer is not None:
                    tool = task_layer.resolve_tool(spec.name)
                if tool is None:
                    tool = self.registry.resolve_tool(spec.name)
                result = tool.run(spec.arguments or {}, ctx)
                if not isinstance(result, ToolResult):
                    result = ToolResult(output=str(result))
            except Exception as exc:  # noqa: BLE001
                result = tool_error(spec.name, exc)
                self.hooks.on_tool_error.emit(
                    task_id=task_id, tool_name=spec.name,
                    error=str(exc), args=spec.arguments,
                )

        # mutating hook: external plugins can rewrite the tool result (str / ToolResult effective)
        try:
            modified_result = self.hooks.after_tool_call.intercept(
                task_id=task_id,
                tool_name=spec.name, args=spec.arguments,
                result=result, success=result.success, context=ctx,
            )
        except HookVeto:
            modified_result = None
        if isinstance(modified_result, ToolResult):
            result = modified_result
        elif isinstance(modified_result, str) and modified_result != str(result):
            result = ToolResult(output=modified_result, success=result.success)

        self.hooks.after_tool_call.emit(
            task_id=task_id,
            tool_name=spec.name, args=spec.arguments,
            result=result, success=result.success, context=ctx,
        )
        return result

    def _check_approval(self, spec: ToolCallSpec, ctx: RunContext) -> Any:
        """Human-approval interception (None when not configured = allow).

        Approval-policy sources (highest priority first):
        params["approval_policy"] / params["approval_config"]
        → registry.security (installed by norpagent.safe()).
        Approval happens via the UI's ask_user; a user denial or no UI
        interaction (default returned is not affirmative) blocks the call.
        """
        policy = ctx.params.get("approval_policy")
        if policy is None and isinstance(ctx.params.get("approval_config"), dict):
            from norpagent.security.approval import ApprovalPolicy

            policy = ApprovalPolicy(ctx.params["approval_config"])
        if policy is None:
            security = getattr(self.registry, "security", None)
            approval_config = getattr(security, "approval_config", None) \
                if security is not None else None
            if isinstance(approval_config, dict):
                from norpagent.security.approval import ApprovalPolicy

                policy = ApprovalPolicy(approval_config)
        if policy is None:
            return None
        try:
            requires, level = policy.requires_approval(spec.name, is_plugin=False)
        except Exception:
            return None
        if not requires:
            return None
        answer = ctx.ask_user(
            f"tool {spec.name} call requires human approval (level {level.value}); continue?"
            f"\nargs: {spec.arguments}\n[y/n]",
            default="n",
        ).strip().lower()
        if answer in ("y", "yes", "ok"):
            return None
        return ToolResult(
            output=f"the user denied the approval request for tool {spec.name}; the call was cancelled.",
            success=False,
            error="approval_denied",
        )

    # ── L9 result finalization ────────────────────────────

    def finalize_result(self, result: RunResult, task_id: str) -> RunResult:
        """L9 result finalization: before_result / after_result mutating hooks."""
        try:
            modified = self.hooks.before_result.intercept(
                task_id=task_id, result=result,
            )
            if isinstance(modified, RunResult):
                result = modified
        except HookVeto:
            pass
        try:
            modified2 = self.hooks.after_result.intercept(
                task_id=task_id, result=result,
            )
            if isinstance(modified2, RunResult):
                result = modified2
        except HookVeto:
            pass
        return result

    # ══════════════════════════════════════════════════════
    #  task cooperation / multi-agent orchestration
    # ══════════════════════════════════════════════════════

    def run_task(self, task: Any) -> Any:
        """Execute an AgentTask (the standard implementation of the scheduler drain callback).

        The unified entry of long-run task cooperation and multi-agent
        orchestration:

        - the scheduler (simple / persistent) hands AgentTasks to this method;
        - a subtask can specify a different mode via ``task.preset_name`` (child
          agent), sharing the same registry / session store / scheduler with the
          parent task;
        - every exception becomes a TaskResult; never bubbles to the scheduler.
        """
        from norpagent.protocols.scheduler import TaskResult

        try:
            preset_name = task.preset_name or self.preset.name
            if preset_name != self.preset.name:
                # the subtask specified a different mode: derive a child runtime
                # on the same registry (multi-agent orchestration: child agent =
                # different preset + shared component repository)
                child = AgentRuntime(
                    self.registry,
                    preset_name,
                    session_manager=self.session_manager,
                    scheduler=self.scheduler,
                    ui=self.ui,
                    task_params=self.params,
                )
                try:
                    run_result = child.run(
                        task.user_input,
                        session_id=task.session_id,
                        task_id=task.id,
                        task_params=task.params,
                    )
                finally:
                    child.shutdown()
            else:
                run_result = self.run(
                    task.user_input,
                    session_id=task.session_id,
                    task_id=task.id,
                    task_params=task.params,
                )
            status = "done" if run_result.ok else run_result.status
            return TaskResult(
                task_id=task.id, status=status,
                error=run_result.error, run_result=run_result,
            )
        except Exception as exc:  # noqa: BLE001
            return TaskResult(task_id=task.id, status="failed", error=str(exc))

    def task_runner(self) -> Any:
        """Return a callback suitable for ``scheduler.drain`` (this runtime as the executor)."""
        return self.run_task

    # ── compat aliases (P1/P2 private method names; legacy signature compat) ──

    def _build_messages(self, system_prompt: str, session_id: str,
                        step: int = 0, task_id: str = "") -> List[ChatMessage]:
        return self.build_messages(
            system_prompt, session_id, step=step, task_id=task_id,
            tool_names=list(self.preset.tools),
        )

    def _call_model(self, model_provider: Any, history: List[ChatMessage],
                    tool_schemas: List[Dict[str, Any]], params: Dict[str, Any],
                    task_id: str, result: RunResult, step: int = 0):
        return self.call_model(
            model_provider, history, tool_schemas, params, task_id, result, step,
        )

    def _execute_tool_call(self, spec: ToolCallSpec, ctx: RunContext,
                           task_id: str) -> ToolResult:
        return self.execute_tool_call(spec, ctx, task_id)

    def shutdown(self) -> None:
        """Close the runtime: reap hard-timeout leftover threads, broadcast the shutdown event, release the sandbox and components."""
        try:
            if self.sandbox is not None and hasattr(self.sandbox, "close"):
                self.sandbox.close()
        finally:
            if self._ui_listener is not None:
                try:
                    self.bus.unsubscribe(self._ui_listener)
                except Exception:
                    pass
                self._ui_listener = None
            for component in self.components.values():
                closer = getattr(component, "close", None)
                if callable(closer):
                    try:
                        closer()
                    except Exception:
                        pass
            for thread in self._orphan_threads:
                if thread.is_alive():
                    thread.join(0.5)  # a short self-exit window for background threads (daemon; never blocks exit)
            self._orphan_threads.clear()
            self.hooks.on_agent_shutdown.emit(preset=self.preset.name)
