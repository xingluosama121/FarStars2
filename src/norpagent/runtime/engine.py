# Copyright (c) 2026 xingluosama121, MIT Licensed
"""NorpEngine: the application engine and lifecycle state machine behind one-click np() startup.

The engine runs the "architecture-layer assembly result":

    layer.connect() → registry + preset + event loop + frontend
                    → agent runtime
                    → background loop thread + frontend input thread

Lifecycle state machine (aligned with the L1 lifecycle hooks):

    STARTING ──start()──▶ RUNNING ──request_stop()──▶ STOPPING ──▶ STOPPED

- start() broadcasts on_agent_init (AgentRuntime construction hook);
- request_stop() / natural completion broadcasts on_agent_shutdown;
- np.stop() polls STOPPED (should_stop() returns True).

The engine is decoupled from the loop system: it interacts only through the
LoopRuntime protocol and never imports any concrete loop implementation.
"""

from __future__ import annotations

import threading
import time
import uuid
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from norpagent.arch.layer import call_factory


class EngineState(str, Enum):
    """Engine lifecycle state."""

    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    STOPPED = "stopped"


class EngineError(RuntimeError):
    """Illegal engine-state operation."""


class EngineTaskHandle:
    """Cancellable engine-level task handle (returned by NorpEngine.submit_async).

    Metadata: task_id / text / session_id / degraded.

    - cancel() requests cancellation of exactly this task (idempotent; the task
      body reads norpagent.loops.cancel.cancel_requested and exits as soon as
      possible);
    - done() / wait(timeout) / result(timeout) follow the loop handle contract;
    - when ``degraded`` is True (the loop runtime has no submit_async extension),
      cancel() only records the request — the running task body cannot be
      interrupted individually; engine.stop() / stop_all_tasks() still cancel all
      in-flight tasks through the loop's interrupt set.
    """

    __slots__ = (
        "task_id", "text", "session_id", "degraded",
        "_underlying", "_box", "_done", "_cancel", "_thread",
    )

    def __init__(
        self,
        task_id: str,
        text: str,
        session_id: Optional[str],
        underlying: Any = None,
        degraded: bool = False,
    ) -> None:
        self.task_id = task_id
        self.text = text
        self.session_id = session_id
        self.degraded = bool(degraded or underlying is None)
        self._underlying = underlying  # loop-level handle (NasyncTaskHandle or None)
        self._box: Dict[str, Any] = {}
        self._done = threading.Event()
        self._cancel = threading.Event()
        self._thread: Optional[threading.Thread] = None

    # internal completion setters (degraded path: a dedicated worker thread fills them)
    def _set_result(self, value: Any) -> None:
        self._box["ok"] = value
        self._done.set()

    def _set_exception(self, exc: BaseException) -> None:
        self._box["exc"] = exc
        self._done.set()

    # ── handle surface ───────────────────────────────────

    def cancel(self) -> bool:
        """Request cancellation of this task; False when it already finished."""
        if self.done():
            return False
        self._cancel.set()
        if self._underlying is not None:
            try:
                self._underlying.cancel()
            except Exception:  # noqa: BLE001 — best-effort
                pass
        return True

    def cancelled(self) -> bool:
        return self._cancel.is_set()

    def done(self) -> bool:
        if self._underlying is not None:
            return self._underlying.done()
        return self._done.is_set()

    def wait(self, timeout: Optional[float] = None) -> bool:
        """Block until the task finishes (True) or the timeout elapses (False)."""
        if self._underlying is not None:
            return self._underlying.wait(timeout)
        if timeout is None:
            self._done.wait()
            return True
        return self._done.wait(timeout)

    def result(self, timeout: Optional[float] = None) -> Any:
        """Wait for completion and return the task's value; re-raises its exception."""
        if self._underlying is not None:
            return self._underlying.result(timeout)
        if not self.wait(timeout):
            raise TimeoutError("task not finished within the timeout")
        if "exc" in self._box:
            raise self._box["exc"]
        return self._box.get("ok")


class NorpEngine:
    """norpagent application engine.

    Users normally do not construct it directly; use ``import norpagent as np; np(...)``.
    """

    def __init__(
        self,
        layer: Any,
        registry: Any,
        preset: Any,
        loop: Any,
        frontend: Any,
        extras: Optional[Dict[str, Any]] = None,
        task_params: Optional[Dict[str, Any]] = None,
        prompt: Optional[str] = None,
        safe_mode: bool = False,
    ) -> None:
        self.layer = layer
        self.registry = registry
        self.preset = preset
        self.loop = loop
        self.frontend = frontend
        self.extras: Dict[str, Any] = dict(extras or {})
        self.params: Dict[str, Any] = dict(task_params or {})
        self.prompt = prompt
        # safe mode: load only the minimal kernel (all plugins skipped; config falls back to defaults)
        self.safe_mode = bool(safe_mode)
        # snapshot mode B (includes session data files); set by np(snapshot_sessions="on")
        self._snapshot_sessions = False
        # after "the first task finishes", mark the snapshot good (mark-good runs only once)
        self._first_task_marked = threading.Event()

        self._state = EngineState.STARTING
        self._state_lock = threading.Lock()
        self._agent: Optional[Any] = None
        self._bus = registry.bus
        self._logger = self.extras.get("logger")
        self._error_handler: Optional[Callable] = self.extras.get("error_handler")
        self._extra_listeners: list = []
        self._stop_requested = threading.Event()
        self._last_result: Optional[Any] = None
        # CNB auto-mount (runtime.cnb; manual 30.8): ordinary engine
        # instances auto-mount as a nervous-tree node when NORP_CNB_* env vars are
        # set. NORP_CNB_MANAGED=1 makes the kernel skip mounting (the upper layer
        # builds its own node — prevents double mounting). Any mounting failure
        # degrades to a plain single instance; request_stop unmounts.
        self._cnb: Optional[Any] = None
        self._cnb_managed = False
        self._cnb_lock = threading.Lock()
        # task-level cancellation (EngineTaskHandle; manual 30.13): task_id -> handle
        self._tasks: Dict[str, Any] = {}
        self._tasks_lock = threading.Lock()

    # ── state ─────────────────────────────────────────────

    @property
    def state(self) -> EngineState:
        with self._state_lock:
            return self._state

    def _set_state(self, state: EngineState) -> None:
        with self._state_lock:
            self._state = state

    def is_running(self) -> bool:
        return self.state in (EngineState.STARTING, EngineState.RUNNING)

    def should_stop(self) -> bool:
        """Semantics of np.stop(): True means the application has ended and the main loop should exit."""
        return self.state is EngineState.STOPPED

    # ── startup ───────────────────────────────────────────

    def start(self) -> "NorpEngine":
        """Assemble the agent runtime and start the loop and frontend (idempotent)."""
        if self.state is not EngineState.STARTING:
            return self
        self._build_agent()
        # bind the frontend to the engine (attach injects the renderer and subscribes events)
        self.frontend.attach(self)
        self.loop.start()
        # enter RUNNING before starting the frontend: the console frontend is in
        # synchronous mode inside the interactive interpreter (REPL); frontend.start()
        # blocks and submits tasks directly in the loop, so the engine must already
        # be RUNNING.
        self._set_state(EngineState.RUNNING)
        # CNB auto-mount: reads NORP_CNB_* env and mounts this instance as a node
        # on a background thread (never delays startup); failures degrade to a
        # plain single instance (see norpagent.runtime.cnb).
        self._setup_cnb()
        self.frontend.start()
        # single-task mode: run the prompt in a background thread; auto-stop after finishing
        if self.prompt is not None:
            threading.Thread(
                target=self._run_prompt_task,
                name="norpagent-prompt-task",
                daemon=True,
            ).start()
        # work rollback: startup baseline snapshot + auto mark "known good" after a
        # 30-second health window (snapshot failures do not affect startup; the
        # rescue capability is extra assurance, not a hard dependency).
        self._recovery_baseline()
        return self

    def _recovery_baseline(self) -> None:
        try:
            from norpagent import recovery

            recovery.snapshot_system(
                description="startup baseline"
                + (" (safe mode)" if self.safe_mode else ""),
                tag="baseline", engine=self,
            )
        except Exception:  # noqa: BLE001
            pass
        # 30-second health window: surviving it marks the "last known-good snapshot"
        try:
            threading.Thread(
                target=self._recovery_health_mark,
                name="norpagent-recovery-health",
                daemon=True,
            ).start()
        except Exception:  # noqa: BLE001
            pass

    def _recovery_health_mark(self) -> None:
        """Survive 30 seconds after a successful startup → mark the current snapshot "known good"."""
        time.sleep(30.0)
        if not self.is_running():
            return
        try:
            from norpagent import recovery

            recovery.mark_good()
        except Exception:  # noqa: BLE001
            pass

    def _recovery_mark_on_task(self, result: Any) -> None:
        """First successful task completed → immediately mark the current snapshot "known good" (once only)."""
        if self._first_task_marked.is_set():
            return
        if not getattr(result, "ok", True):
            return
        if not self._first_task_marked.is_set():
            self._first_task_marked.set()
        try:
            from norpagent import recovery

            recovery.mark_good()
        except Exception:  # noqa: BLE001
            pass

    def _build_agent(self) -> None:
        """Build the agent runtime per the agent_runtime slot.

        Default implementation = kernel.agent.AgentRuntime; filling in an address
        replaces the loop body. The factory context is injected per signature:
        registry / preset / ui / task_params. agent_runtime is a defer_factory
        slot: the architecture layer only resolves the address; the actual factory
        call happens here (with the full context ready).
        """
        runtime_slot = self.layer.get("agent_runtime")
        ui = None
        try:
            ui = self.registry.resolve_ui(self.preset.ui)
        except Exception:  # noqa: BLE001 — the frontend may carry its own renderer
            ui = None
        subconfig_fn = getattr(self.layer, "subconfig", None)
        sub_config = subconfig_fn("agent_runtime") if callable(subconfig_fn) else {}
        self._agent = call_factory(
            runtime_slot,
            {
                "registry": self.registry,
                "preset": self.preset,
                "ui": ui,
                "task_params": self.params,
                "layer": self.layer,
                "config": sub_config,
            },
        )

    # ── input submission ─────────────────────────────────

    def submit(self, text: str, session_id: Optional[str] = None,
               task_params: Optional[Dict[str, Any]] = None,
               slot_overrides: Optional[Dict[str, Any]] = None) -> Any:
        """Submit one user input to the agent (executes in the loop context; blocks returning the result).

        ``task_params`` are task-level parameters (override construction-level
        defaults such as workspace_root / max_steps / _stop_check).

        ``slot_overrides`` (v0.9.2, task-level slot injection; see manual 3.9):
        temporarily overrides any slot implementation for the duration of this
        task — model / tools / sandbox / session / scheduler / hooks / security /
        agent_runtime / context_store / project_manager / async_loop / logger /
        storage / error_handler. Keys match np()'s slot parameters; non-slot keys
        (e.g. max_steps) automatically fall back to task parameters.

        Priority: task-level overrides > global remount > startup np() > preset
        declarations. Task-level overrides are snapshotted at submit() time: later
        np.remount does not affect in-flight tasks; when the task ends, the
        snapshot layer is released with the RunResult, leaving no residue.
        """
        if self.state is not EngineState.RUNNING:
            raise EngineError(f"engine is not running (current {self.state.value})")
        agent = self._agent
        if agent is None:
            raise EngineError("agent not assembled")
        task_params, slot_overrides = self._normalize_task_overrides(
            task_params, slot_overrides)
        run = self._task_run(agent, text, session_id, task_params,
                             slot_overrides)

        # async_loop slot overridden at task level: this task runs on a standalone
        # temporary loop (no contention with the main loop's in-flight tasks for
        # the worker pool); stopped after execution.
        if "async_loop" in slot_overrides:
            loop = self._build_task_loop(slot_overrides["async_loop"])
            try:
                loop.start()
                result = loop.submit(run)
            finally:
                try:
                    loop.stop()
                except Exception:  # noqa: BLE001
                    pass
                try:
                    loop.join(timeout=2.0)
                except Exception:  # noqa: BLE001
                    pass
        else:
            result = self.loop.submit(run)
        # work rollback: first successful task → immediately mark the current snapshot "known good"
        self._recovery_mark_on_task(result)
        return result

    def _task_run(self, agent: Any, text: str, session_id: Optional[str],
                  task_params: Dict[str, Any],
                  slot_overrides: Dict[str, Any]) -> Callable[[], Any]:
        """Build the callable that executes one task in the loop context.

        Shared by submit() and submit_async() so both paths run identical task
        semantics (child runtime / child loop handling included).
        """
        def _run() -> Any:
            # agent_runtime slot overridden at task level: start a standalone
            # Runtime instance for this task and destroy it after execution
            # (without affecting the engine's default Runtime). Other overrides
            # pass through to the child runtime.
            if "agent_runtime" in slot_overrides:
                child = self._build_task_runtime(
                    slot_overrides["agent_runtime"])
                try:
                    return child.run(
                        text, session_id=session_id,
                        task_params=task_params,
                        slot_overrides=slot_overrides,
                    )
                finally:
                    try:
                        child.shutdown()
                    except Exception:  # noqa: BLE001 — destroy failures do not bubble up
                        pass
            return agent.run(
                text, session_id=session_id,
                task_params=task_params, slot_overrides=slot_overrides,
            )

        return _run

    # ── task-level cancellation (manual 30.13) ────────────

    def submit_async(
        self,
        text: str,
        session_id: Optional[str] = None,
        task_params: Optional[Dict[str, Any]] = None,
        slot_overrides: Optional[Dict[str, Any]] = None,
    ) -> EngineTaskHandle:
        """Submit one input without blocking; returns a cancellable EngineTaskHandle.

        Same execution semantics as submit() (loop context / task params / slot
        overrides). ``handle.cancel()`` requests cancellation of exactly this
        task: the task body reads cancel_requested() and exits as soon as possible
        (sandbox force-kill of child processes / model-stream interrupt).

        When the loop runtime implements the optional submit_async extension
        (the default nasyncio loop does) the task is submitted directly and
        cancellation is deep. Otherwise — or when a task-level async_loop
        override is present — the task runs through submit() in a dedicated
        worker thread and cancellation degrades to a request flag.
        """
        if self.state is not EngineState.RUNNING:
            raise EngineError(f"engine is not running (current {self.state.value})")
        agent = self._agent
        if agent is None:
            raise EngineError("agent not assembled")
        task_params, slot_overrides = self._normalize_task_overrides(
            task_params, slot_overrides)
        run = self._task_run(agent, text, session_id, task_params,
                             slot_overrides)
        task_id = uuid.uuid4().hex
        handle: EngineTaskHandle
        if "async_loop" not in slot_overrides and hasattr(self.loop, "submit_async"):
            underlying = self.loop.submit_async(run)
            handle = EngineTaskHandle(task_id, text, session_id,
                                      underlying=underlying)
        else:
            handle = EngineTaskHandle(task_id, text, session_id, degraded=True)

            def _target() -> None:
                try:
                    handle._set_result(self.submit(
                        text, session_id=session_id,
                        task_params=task_params,
                        slot_overrides=slot_overrides))
                except BaseException as exc:  # noqa: BLE001 — relayed via result()
                    handle._set_exception(exc)

            t = threading.Thread(target=_target, daemon=True,
                                 name=f"norpagent-task-{task_id[:8]}")
            handle._thread = t
            t.start()
        # work rollback: mark-good on the first successful async task, too
        self._watch_recovery(handle)
        self._register_task(handle)
        return handle

    def _watch_recovery(self, handle: EngineTaskHandle) -> None:
        """Completion watcher: mirror submit()'s recovery mark-good for async tasks."""

        def _watch() -> None:
            try:
                result = handle.result()
                self._recovery_mark_on_task(result)
            except Exception:  # noqa: BLE001 — recovery is extra assurance
                pass

        threading.Thread(target=_watch, daemon=True,
                         name=f"norpagent-recovery-{handle.task_id[:8]}").start()

    def cancel_task(self, task_id: str) -> bool:
        """Cancel one submitted task by id; False when unknown or already finished."""
        with self._tasks_lock:
            handle = self._tasks.get(task_id)
        if handle is None or handle.done():
            return False
        try:
            return bool(handle.cancel())
        except Exception:  # noqa: BLE001
            return False

    def stop_all_tasks(self) -> int:
        """Cancel every in-flight task while the engine itself stays RUNNING.

        Landing point of the CNB ``cmd.stop`` downlink (stop local session tasks,
        keep the instance alive). Also used by engine.stop paths.
        """
        interrupt = getattr(self.loop, "interrupt", None)
        if callable(interrupt):
            try:
                interrupt()
            except Exception:  # noqa: BLE001 — cancellation failures never block
                pass
        return self._cancel_registered_tasks()

    def active_tasks(self) -> List[Dict[str, Any]]:
        """Snapshot of in-flight tasks (task_id / text / session_id / degraded / cancelled)."""
        self._prune_tasks()
        with self._tasks_lock:
            return [
                {
                    "task_id": handle.task_id,
                    "text": handle.text,
                    "session_id": handle.session_id,
                    "degraded": handle.degraded,
                    "cancelled": handle.cancelled(),
                }
                for handle in self._tasks.values()
                if not handle.done()
            ]

    def forget_task(self, task_id: str) -> bool:
        """Remove a finished task from the registry (bookkeeping only)."""
        with self._tasks_lock:
            return self._tasks.pop(task_id, None) is not None

    # internal registry helpers ───────────────────────────

    def _register_task(self, handle: EngineTaskHandle) -> None:
        with self._tasks_lock:
            self._tasks[handle.task_id] = handle

    def _prune_tasks(self) -> None:
        with self._tasks_lock:
            stale = [k for k, v in self._tasks.items() if v.done()]
            for k in stale:
                self._tasks.pop(k, None)

    def _cancel_registered_tasks(self) -> int:
        with self._tasks_lock:
            handles = [h for h in self._tasks.values() if not h.done()]
        for handle in handles:
            try:
                handle.cancel()
            except Exception:  # noqa: BLE001
                pass
        self._prune_tasks()
        return len(handles)

    # ── CNB auto-mount hooks (manual 30.8) ────────────────

    def _setup_cnb(self) -> None:
        """Auto-mount this instance as a nervous-tree node when NORP_CNB_* env vars are set.

        NORP_CNB_MANAGED=1 asks the kernel to skip mounting (an
        upper layer builds its own node — prevents double mounting). Mounting runs
        on a background thread: startup is never delayed, and any failure degrades
        to a plain single instance (warning printed). request_stop() unmounts.
        """
        try:
            from norpagent.runtime.cnb import setup_cnb

            setup_cnb(self)
        except Exception as exc:  # noqa: BLE001 — auto-mount must never break the instance
            print(f"[cnb] auto-mount error; degrading to a plain instance: {exc}")

    def _teardown_cnb(self) -> None:
        """Unmount the CNB node (idempotent; called from request_stop)."""
        with self._cnb_lock:
            adapter = self._cnb
            self._cnb = None
        if adapter is not None:
            try:
                adapter.shutdown()
            except Exception:  # noqa: BLE001 — teardown failures must not block stop
                pass

    @property
    def cnb(self) -> Optional[Any]:
        """The CNB auto-mount adapter (None = not mounted)."""
        with self._cnb_lock:
            return self._cnb

    @property
    def cnb_status(self) -> str:
        """Mount status: not-mounted / managed-skip / mounting / mounted / failed / stopped."""
        with self._cnb_lock:
            if self._cnb_managed:
                return "managed-skip"
            adapter = self._cnb
        if adapter is None:
            return "not-mounted"
        return str(getattr(adapter, "status", "unknown"))

    @staticmethod
    def _normalize_task_overrides(
        task_params: Optional[Dict[str, Any]],
        slot_overrides: Optional[Dict[str, Any]],
    ) -> tuple:
        """Normalize task parameters and task-level slot overrides.

        Task-level override keys match np()'s slot parameters (TASK_SLOT_KEYS);
        non-slot keys (e.g. max_steps / task_timeout) automatically fall back to
        task parameters passed to the agent loop (the same data path as np()'s
        "slot-key splitting; the rest pass through as parameters").
        """
        from norpagent.kernel.agent import TASK_SLOT_KEYS

        task_params = dict(task_params or {})
        slot_overrides = dict(slot_overrides or {})
        for key in list(slot_overrides):
            if key not in TASK_SLOT_KEYS:
                task_params[key] = slot_overrides.pop(key)
        return task_params, slot_overrides

    def _build_task_runtime(self, slot_value: Any) -> Any:
        """Task-level agent_runtime override: build a standalone Runtime instance
        by address / factory / instance (same factory-calling convention as _build_agent)."""
        from norpagent.arch.address import is_address_like, resolve_address
        from norpagent.arch.layer import call_factory

        ui = None
        try:
            ui = self.registry.resolve_ui(self.preset.ui)
        except Exception:  # noqa: BLE001 — the frontend may carry its own renderer
            ui = None
        subconfig_fn = getattr(self.layer, "subconfig", None)
        sub_config = (
            subconfig_fn("agent_runtime") if callable(subconfig_fn) else {}
        )
        ctx = {
            "registry": self.registry,
            "preset": self.preset,
            "ui": ui,
            "task_params": self.params,
            "layer": self.layer,
            "config": sub_config,
        }
        value = slot_value
        if isinstance(value, str) and is_address_like(value):
            impl = resolve_address(value, slot="agent_runtime")
            if callable(impl):
                return call_factory(impl, ctx)
            return impl
        if callable(value):
            return call_factory(value, ctx)
        return value

    @staticmethod
    def _build_task_loop(slot_value: Any) -> Any:
        """Task-level async_loop override: build a temporary event loop by address /
        factory / instance (LoopRuntime protocol: start / submit / stop / join)."""
        from norpagent.arch.address import is_address_like, resolve_address
        from norpagent.arch.layer import call_factory

        value = slot_value
        if isinstance(value, str) and is_address_like(value):
            impl = resolve_address(value, slot="async_loop")
            if callable(impl):
                return call_factory(impl, {"layer": None, "config": {}})
            return impl
        if callable(value):
            return call_factory(value, {"layer": None, "config": {}})
        return value

    # ── runtime hot mount (any slot replaceable) ─────────

    def remount(self, **slot_values: Any) -> "NorpEngine":
        """Runtime hot mount: replace any slot implementation while the engine stays RUNNING.

        Usage::

            np.remount(model="openai_compat")              # swap the model (takes effect on the next run)
            np.remount(tools=["echo", "get_time"])         # swap the tool set
            np.remount(security="high")                    # swap the security level
            np.remount(frontend="...:ConsoleFrontend")     # swap the frontend
            np.remount(async_loop="myapp.loop:create")     # swap the event loop
            np.remount(model="myapp.model:create")         # replace a module file at runtime
            np.remount(flow_html="/path/new-flow.html")    # swap the flow page at runtime
            np.remount(html="/path/new-front.html")        # swap the main page at runtime

        Replacement semantics grouped by slot (details in norpagent.runtime.remount):

        - component slots (model / tools / hooks / security / plugins): remounted
          onto the registry; take effect on the next run() (the agent loop
          re-resolves models and tool schemas on every run); string addresses
          invalidate the module cache first, so "edit module file → remount" is
          hot reload;
        - assembly slots (session / sandbox / scheduler / ui / context_store /
          project_manager / agent_runtime / preset): the AgentRuntime hot-rebuilds
          (stop old sandbox → build new runtime → frontend rebind);
        - infrastructure slots (frontend / async_loop): stop the old implementation,
          start the new one;
        - base-service slots (logger / storage / error_handler): update the engine;
        - custom slots (registered via register_slot, v0.9): reapplied per the
          spec's applier; specs with remount_rebuild_agent=True also hot-rebuild
          the AgentRuntime.

        Architecture-level subscriptions mounted repeatedly (hooks / security /
        plugins) are unsubscribed first and then remounted; duplicate firing never stacks.
        """
        from norpagent.runtime.remount import remount_engine

        if self.state is not EngineState.RUNNING:
            raise EngineError(
                f"hot mount requires the engine to be running (current {self.state.value})"
            )
        return remount_engine(self, **slot_values)

    # ── work rollback (snapshots / Undo / Redo / Rollback) ──

    def snapshot(self, description: str = "", tag: str = "manual") -> Any:
        """Take a manual snapshot (current system state persisted)."""
        from norpagent import recovery

        return recovery.snapshot_system(description=description, tag=tag,
                                        engine=self)

    def undo(self) -> Any:
        """Undo the most recent operation (in-process immediate)."""
        from norpagent import recovery

        return recovery.undo(self)

    def redo(self) -> Any:
        """Redo the most recent undo."""
        from norpagent import recovery

        return recovery.redo(self)

    def rollback(self, snap_id: Optional[str] = None) -> Any:
        """Roll back to any snapshot (default = the last known-good snapshot)."""
        from norpagent import recovery

        return recovery.rollback(snap_id=snap_id, engine=self)

    def list_snapshots(self) -> Any:
        from norpagent import recovery

        return recovery.list_snapshots()

    def mark_good(self, snap_id: Optional[str] = None) -> Any:
        """Mark a snapshot as "known good"."""
        from norpagent import recovery

        return recovery.mark_good(snap_id)

    def _swap_agent(self) -> None:
        """Hot-rebuild the agent runtime (after assembly-slot replacement).

        Close the old runtime (release sandboxes / components / unsubscribe the
        renderer) → build the new runtime per the current architecture-layer slots
        → notify the frontend to rebind (the renderer points at the new runtime;
        the HTTP service is not restarted).
        """
        old = self._agent
        if old is not None:
            try:
                old.shutdown()
            except Exception:  # noqa: BLE001
                pass
        self._build_agent()
        rebind = getattr(self.frontend, "reattach_agent", None)
        if callable(rebind):
            try:
                rebind(self)
            except Exception:  # noqa: BLE001
                pass

    def subscribe_ui(self, renderer: Any) -> None:
        """Subscribe a renderer to the event bus (auto-dedup; avoids duplicate output)."""
        on_event = getattr(renderer, "on_event", None)
        if on_event is None:
            return
        if self._agent is not None and getattr(self._agent, "ui", None) is renderer:
            return  # the AgentRuntime already subscribed the same instance at construction
        self._bus.subscribe(on_event)
        self._extra_listeners.append(on_event)

    # ── stopping ─────────────────────────────────────────

    def request_stop(self) -> None:
        """Request a stop (idempotent; callable from any thread)."""
        if self._stop_requested.is_set():
            return
        self._stop_requested.set()
        if self.state in (EngineState.STOPPING, EngineState.STOPPED):
            return
        self._set_state(EngineState.STOPPING)
        # 0b. CNB teardown first: deregister + close the node bus (best-effort;
        #     never blocks Ctrl+C for longer than the shutdown join budget)
        self._teardown_cnb()
        # 0c. cancel registered task handles not visible to the loop's interrupt set
        #     (degraded handles); the loop interrupt below covers the rest
        try:
            self._cancel_registered_tasks()
        except Exception:  # noqa: BLE001
            pass
        # 0. cancel all in-flight tasks: sandboxes force-kill child processes
        #    immediately, model streaming loops interrupt — submits stuck in
        #    blocking I/O return as soon as possible (the core of Ctrl+C
        #    usability: signals reach only the main thread, but the cancel event
        #    is visible to everyone)
        interrupt = getattr(self.loop, "interrupt", None)
        if callable(interrupt):
            try:
                interrupt()
            except Exception:  # noqa: BLE001 — cancellation failure must not block cleanup
                pass
        # 1. stop the frontend (input loop exits)
        try:
            self.frontend.stop()
        except Exception:  # noqa: BLE001
            pass
        # 2. close the agent (release sandboxes / components / broadcast on_agent_shutdown)
        agent = self._agent
        if agent is not None:
            def _close() -> None:
                try:
                    agent.shutdown()
                except Exception:  # noqa: BLE001
                    pass

            def _submit_close() -> None:
                try:
                    self.loop.submit(_close)
                except Exception:  # noqa: BLE001 — loop already stopped etc.
                    _close()

            if self.loop.is_running():
                # after the cancel event is set, tasks exit quickly; should a task
                # body stay stuck in an uninterruptible blocking call, close
                # directly in the current thread after 5s (the daemon worker pool
                # does not block process exit; this guards against request_stop
                # itself hanging forever).
                t = threading.Thread(
                    target=_submit_close, daemon=True,
                    name="norpagent-engine-close",
                )
                t.start()
                t.join(timeout=5.0)
                if t.is_alive():
                    _close()
            else:
                _close()
        # 3. unsubscribe renderers subscribed additionally by the engine
        for fn in self._extra_listeners:
            try:
                self._bus.unsubscribe(fn)
            except Exception:  # noqa: BLE001
                pass
        self._extra_listeners.clear()
        # 4. stop the loop thread
        try:
            self.loop.stop()
            self.loop.join(timeout=2.0)
        except Exception:  # noqa: BLE001
            pass
        self._set_state(EngineState.STOPPED)

    def stop(self, timeout: Optional[float] = None) -> None:
        """Request a stop and wait for the engine to fully exit."""
        self.request_stop()
        deadline = (time.time() + timeout) if timeout else None
        while self.state is not EngineState.STOPPED:
            if deadline and time.time() > deadline:
                return
            time.sleep(0.01)

    def wait(self, timeout: Optional[float] = None) -> bool:
        """Wait for the engine to end naturally; returns whether it has stopped."""
        deadline = (time.time() + timeout) if timeout else None
        while not self.should_stop():
            if deadline and time.time() > deadline:
                return False
            time.sleep(0.01)
        return True

    @property
    def agent(self) -> Any:
        """The current agent runtime (assembled)."""
        return self._agent

    @property
    def last_result(self) -> Any:
        """The result of the most recent task (RunResult)."""
        return self._last_result

    # ── single task ──────────────────────────────────────

    def _run_prompt_task(self) -> None:
        try:
            result = self.submit(self.prompt)
            self._last_result = result
            # under the headless frontend, task completion must visibly print the
            # final result (fixes "headless mode only shows input, not output")
            if getattr(self.frontend, "frontend_id", "") == "headless":
                status = getattr(result, "status", "done")
                content = getattr(result, "final_content", "") or ""
                if status == "done" and content:
                    print(f"[headless] task result: {content}")
                else:
                    err = getattr(result, "error", "") or ""
                    print(f"[headless] task {status}: {err}")
            self._handle_error_if_needed(result)
        except EngineError:
            pass  # engine already stopped
        except Exception as exc:  # noqa: BLE001 — last line of defense
            self._handle_exception(exc)
        finally:
            self.request_stop()

    def _handle_error_if_needed(self, result: Any) -> None:
        status = getattr(result, "status", "done")
        if status == "error":
            self._handle_exception(
                RuntimeError(getattr(result, "error", "task failed"))
            )

    def _handle_exception(self, exc: BaseException) -> None:
        # exceptions during interpreter shutdown (main thread ended, daemon engine
        # threads still running) need no reporting: the process is about to die and
        # logs are meaningless. (threading._SHUTTING_DOWN is a stable private flag
        # since CPython 3.9; sys.is_finalizing() is the official interface since
        # 3.13; both as a belt-and-suspenders approach.)
        import sys as _sys

        finalizing = bool(getattr(threading, "_SHUTTING_DOWN", False))
        finalizer = getattr(_sys, "is_finalizing", None)
        if finalizing or (finalizer is not None and finalizer()):
            return
        if self._error_handler is not None:
            try:
                self._error_handler(exc, self)
                return
            except Exception:  # noqa: BLE001 — error-handler errors fall back to logging
                pass
        if self._logger is not None:
            try:
                self._logger.error("norpagent engine error: %s", exc)
            except Exception:  # noqa: BLE001
                pass


__all__ = ["NorpEngine", "EngineState", "EngineError"]
