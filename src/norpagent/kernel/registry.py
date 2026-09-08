# Copyright (c) 2026 xingluosama121, MIT Licensed
"""Registry: the assembly center of the framework.

Everything is a registered item. Models / tools / sessions / sandboxes /
schedulers / UIs / plugins / presets are all registered and resolved by name.
AgentRuntime only interacts with the registry, so replacing any part never
requires changing core code.

The registry itself is part of the kernel and is unaware of any concrete
implementation.
"""

from __future__ import annotations

import threading
from typing import Any, Callable, Dict, List, Optional, Tuple

from norpagent.kernel.events import EventBus
from norpagent.protocols.plugin import Plugin
from norpagent.protocols.tool import Tool


class ComponentError(Exception):
    """Registry errors: missing / duplicate components, type mismatches, etc."""


class Registry:
    """Component registration center."""

    def __init__(self, bus: Optional[EventBus] = None) -> None:
        self.bus = bus or EventBus()
        self._models: Dict[str, Any] = {}
        self._tools: Dict[str, Tool] = {}
        self._sessions: Dict[str, Callable[[], Any]] = {}
        self._sandboxes: Dict[str, Callable[[], Any]] = {}
        self._schedulers: Dict[str, Callable[[], Any]] = {}
        self._uis: Dict[str, Any] = {}
        self._plugins: Dict[str, Plugin] = {}
        self._presets: Dict[str, Any] = {}
        # generic component namespace: kind -> {name: factory}
        # context stores / project managers / task stores and every other "extra
        # capability" go through here, letting the framework extend new component
        # kinds without touching the kernel.
        self._components: Dict[str, Dict[str, Callable[[], Any]]] = {}
        # security context (installed by norpagent.safe()): AgentRuntime and the
        # plugin loader read the full security policy from it, enabling the
        # "security system as a whole plug" design.
        self.security: Any = None
        # hook system (lazy): the 9-layer hook view over the same bus.
        self._hook_system: Any = None
        self._lock = threading.RLock()

    # ── hooks ─────────────────────────────────────────────

    @property
    def hooks(self) -> Any:
        """The hook system on this registry's bus (HookSystem).

        ``registry.hooks.before_model_call.subscribe(fn)``
        is equivalent to subscribing the same-named event on registry.bus;
        undefined named events automatically become dynamic-layer hooks when fired.
        """
        with self._lock:
            if self._hook_system is None:
                from norpagent.hooks.core import HookSystem

                self._hook_system = HookSystem(self.bus)
            return self._hook_system


    # ── registration ──────────────────────────────────────

    def register_model(self, name: str, provider: Any) -> None:
        with self._lock:
            self._models[name] = provider

    def register_tool(self, name: str, tool: Tool) -> None:
        with self._lock:
            self._tools[name] = tool

    def register_session(self, name: str, factory: Callable[[], Any]) -> None:
        with self._lock:
            self._sessions[name] = factory

    def register_sandbox(self, name: str, factory: Callable[[], Any]) -> None:
        with self._lock:
            self._sandboxes[name] = factory

    def register_scheduler(self, name: str, factory: Callable[[], Any]) -> None:
        with self._lock:
            self._schedulers[name] = factory

    def register_ui(self, name: str, adapter: Any) -> None:
        with self._lock:
            self._uis[name] = adapter

    def register_plugin(self, plugin: Plugin) -> None:
        """Register a plugin: tools enter the tool table; hooks subscribe to the event bus.

        Duplicate tool names are overwritten by the later registration (with a log
        notice); plugin metadata is kept.
        """
        with self._lock:
            name = getattr(plugin, "name", "") or plugin.__class__.__name__
            for tool in plugin.get_tools():
                tname = getattr(tool, "name", "") or tool.__class__.__name__
                if not tname:
                    continue
                if tname in self._tools:
                    print(f"[Registry] tool {tname} already exists; overwritten by plugin {name}")
                self._tools[tname] = tool
            for hook, fn in plugin.get_hooks().items():
                self.bus.subscribe(fn, hook)
            self._plugins[name] = plugin

    def register_preset(self, preset: Any) -> None:
        from norpagent.kernel.presets import Preset

        if not isinstance(preset, Preset):
            raise ComponentError(f"preset must be a Preset instance, got {type(preset)}")
        with self._lock:
            self._presets[preset.name] = preset

    def unregister_plugin(self, name: str) -> None:
        """Unload a plugin: unsubscribe its hook subscriptions and remove the plugin record.

        Tool entries are kept (the tool registry uses name-overwrite semantics; a
        same-named plugin remounted later naturally overwrites; historical entries
        of removed tool names do not affect resolution — they are unreachable when
        not in the preset's tool set). Used when hot-mounting the plugins slot at runtime.
        """
        with self._lock:
            plugin = self._plugins.get(name)
            if plugin is None:
                return
            try:
                for hook, fn in plugin.get_hooks().items():
                    self.bus.unsubscribe(fn, hook)
            except Exception:  # noqa: BLE001 — a single plugin error must not block unloading
                pass
            self._plugins.pop(name, None)

    def register_component(self, kind: str, name: str, factory: Callable[[], Any]) -> None:
        """Register a generic component: kind (e.g. context_store) + name + factory.

        Unlike the dedicated namespaces (session / sandbox etc.), component kinds
        are open: third parties can directly
        register_component("my_kind", "my_impl", factory) and declare
        components={"my_kind": "my_impl"} in a preset.
        """
        with self._lock:
            self._components.setdefault(kind, {})[name] = factory

    # ── resolution ────────────────────────────────────────

    def resolve_model(self, name: str) -> Any:
        with self._lock:
            if name not in self._models:
                raise ComponentError(
                    f"model '{name}' is not registered. Available models: {sorted(self._models)}"
                )
            return self._models[name]

    def resolve_tool(self, name: str) -> Tool:
        with self._lock:
            if name not in self._tools:
                raise ComponentError(
                    f"tool '{name}' is not registered. Available tools: {sorted(self._tools)}"
                )
            return self._tools[name]

    def resolve_preset(self, name: str) -> Any:
        with self._lock:
            if name not in self._presets:
                raise ComponentError(
                    f"preset mode '{name}' is not registered. Available modes: {sorted(self._presets)}"
                )
            return self._presets[name]

    def build_session(self, name: str) -> Any:
        with self._lock:
            if name not in self._sessions:
                raise ComponentError(
                    f"session component '{name}' is not registered. Available: {sorted(self._sessions)}"
                )
            return self._sessions[name]()

    def build_sandbox(self, name: str) -> Any:
        with self._lock:
            if name not in self._sandboxes:
                raise ComponentError(
                    f"sandbox component '{name}' is not registered. Available: {sorted(self._sandboxes)}"
                )
            return self._sandboxes[name]()

    def build_scheduler(self, name: str) -> Any:
        with self._lock:
            if name not in self._schedulers:
                raise ComponentError(
                    f"scheduler component '{name}' is not registered. Available: {sorted(self._schedulers)}"
                )
            return self._schedulers[name]()

    def resolve_ui(self, name: str) -> Any:
        with self._lock:
            if name not in self._uis:
                raise ComponentError(
                    f"UI component '{name}' is not registered. Available: {sorted(self._uis)}"
                )
            return self._uis[name]

    def build_component(self, kind: str, name: str,
                        workspace_root: Optional[str] = None) -> Any:
        """Build a generic component.

        ``workspace_root`` hint: if the factory declares a same-named parameter (or
        **kwargs), the workspace root is auto-injected (project managers and similar
        components locate the project from it).
        """
        with self._lock:
            bucket = self._components.get(kind)
            if not bucket or name not in bucket:
                available = sorted(bucket) if bucket else []
                raise ComponentError(
                    f"component '{kind}={name}' is not registered. "
                    f"Available {kind}: {available}"
                )
            factory = bucket[name]
        if workspace_root is not None:
            try:
                import inspect

                sig = inspect.signature(factory)
                accepts = any(
                    p.kind is p.VAR_KEYWORD
                    for p in sig.parameters.values()
                ) or "workspace_root" in sig.parameters
            except (TypeError, ValueError):
                accepts = False
            if accepts:
                return factory(workspace_root=workspace_root)
        return factory()

    # ── queries ───────────────────────────────────────────

    def list_models(self) -> List[str]:
        with self._lock:
            return sorted(self._models)

    def list_tools(self) -> List[str]:
        with self._lock:
            return sorted(self._tools)

    def list_presets(self) -> List[str]:
        with self._lock:
            return sorted(self._presets)

    def list_sessions(self) -> List[str]:
        with self._lock:
            return sorted(self._sessions)

    def list_sandboxes(self) -> List[str]:
        with self._lock:
            return sorted(self._sandboxes)

    def list_schedulers(self) -> List[str]:
        with self._lock:
            return sorted(self._schedulers)

    def list_uis(self) -> List[str]:
        with self._lock:
            return sorted(self._uis)

    def list_plugins(self) -> List[str]:
        with self._lock:
            return sorted(self._plugins)

    def list_components(self, kind: Optional[str] = None) -> Dict[str, List[str]]:
        """List components: when kind is given, return that kind's name list; otherwise return all kinds."""
        with self._lock:
            if kind is not None:
                return sorted(self._components.get(kind, {}))
            return {k: sorted(v) for k, v in sorted(self._components.items())}

    def tool_schemas(self, names: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """Export the OpenAI function schema list of tools by name (all when omitted)."""
        with self._lock:
            if names is None:
                names = sorted(self._tools)
            schemas: List[Dict[str, Any]] = []
            for n in names:
                tool = self._tools.get(n)
                if tool is None:
                    raise ComponentError(
                        f"tool '{n}' is not registered. Available tools: {sorted(self._tools)}"
                    )
                schemas.append(tool.schema())
            return schemas

    def validate_preset(self, preset: Any) -> Tuple[List[str], List[str]]:
        """Validate that all components referenced by the preset are available.

        Returns (missing component items, missing tools); empty lists mean usable.
        Missing items look like "model=openai_compat" for readable errors.
        """
        from norpagent.kernel.presets import Preset

        if not isinstance(preset, Preset):
            raise ComponentError(f"preset must be a Preset instance, got {type(preset)}")
        missing: List[str] = []
        missing_tools: List[str] = []
        with self._lock:
            if preset.model not in self._models:
                missing.append(f"model={preset.model}")
            if preset.session not in self._sessions:
                missing.append(f"session={preset.session}")
            if preset.sandbox not in self._sandboxes:
                missing.append(f"sandbox={preset.sandbox}")
            if preset.scheduler not in self._schedulers:
                missing.append(f"scheduler={preset.scheduler}")
            if preset.ui not in self._uis:
                missing.append(f"ui={preset.ui}")
            for kind, name in (preset.components or {}).items():
                bucket = self._components.get(kind)
                if not bucket or name not in bucket:
                    missing.append(f"component={kind}:{name}")
            for t in preset.tools:
                if t not in self._tools:
                    missing_tools.append(t)
        return missing, missing_tools
