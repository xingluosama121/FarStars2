# Copyright (c) 2026 xingluosama121, MIT Licensed
"""Runtime package: one-click startup with np(), lifecycle polling with np.stop(), engine management.

::

    import norpagent as np
    np()                       # starts with default logic (default web frontend, listening on ...)
    running = True
    while running:
        if np.stop() == True:  # lifecycle function: True = the application has ended
            running = False

Single task::

    import norpagent as np
    np(prompt="hello")         # headless runs then stops automatically (output printed to stdout)
    while True:
        if np.stop():
            break
    print(np.current().last_result.final_content)
"""

from __future__ import annotations

import atexit
import threading
from typing import Any, Dict, Optional

from norpagent.arch.layer import ArchLayer
from norpagent.arch.slots import snapshot_slots
from norpagent.runtime.engine import EngineError, EngineState, NorpEngine
from norpagent.runtime.mount import (
    build_registry,
    coerce_frontend,
    mount_defaults,
)

_current: Optional[NorpEngine] = None
_lock = threading.Lock()
_atexit_registered = False


def _register_atexit() -> None:
    global _atexit_registered
    if not _atexit_registered:
        atexit.register(_atexit_shutdown)
        _atexit_registered = True


def launch(**kwargs: Any) -> NorpEngine:
    """Implementation of np(): assembles and starts an Agent application per the architecture layer.

    Keyword arguments fall into two categories:
    - architecture slots: keys with the same names as the slot table in
      norpagent.arch.slots (the 18 built-in slots async_loop / agent_runtime /
      model / tools / session / sandbox / scheduler / context_store /
      project_manager / hooks / security / plugins / frontend / ui / preset /
      logger / storage / error_handler, plus custom slots registered at runtime
      via register_slot()); empty = default logic, address = mount the
      implementation by address;
    - runtime parameters: all other keys pass through to the agent loop as task
      parameters (e.g. max_steps / task_timeout / workspace_root).

    Special keys: ``prompt`` (single-task text; stops automatically after
    finishing), ``config`` (assigns slot values as a dict), ``safemode``
    ("on" = safe mode: loads only a minimal kernel — skips all plugins, forces
    the minimal preset, does not read the WebUI settings file; keeps core
    fallback capabilities for repairs), ``snapshot_dir`` (snapshot storage
    directory, default ~/.norpagent/snapshots/), ``snapshots`` ("off" = disable
    auto snapshots, default "on"), ``snapshot_sessions`` ("on" = snapshot mode B,
    additionally packages session data files, default "off").

    When an engine is already running, the current engine is returned (singleton semantics).
    """
    global _current
    prompt = kwargs.pop("prompt", None)
    config = kwargs.pop("config", None)
    # work-rollback (recovery) special keys
    safemode_raw = kwargs.pop("safemode", None)
    safemode_on = str(safemode_raw).strip().lower() in (
        "on", "1", "true", "yes")
    snapshot_dir = kwargs.pop("snapshot_dir", None)
    snapshots_off = str(kwargs.pop("snapshots", "on")).strip().lower() in (
        "off", "0", "false", "no")
    snapshot_sessions = str(
        kwargs.pop("snapshot_sessions", "off")).strip().lower() in (
        "on", "1", "true", "yes")

    if snapshot_dir:
        try:
            from norpagent.recovery import set_snapshot_dir

            set_snapshot_dir(str(snapshot_dir))
        except Exception:  # noqa: BLE001
            pass
    if snapshots_off:
        try:
            from norpagent.recovery import set_enabled

            set_enabled(False)
        except Exception:  # noqa: BLE001
            pass

    # safe mode: load only the minimal kernel — skip all plugins, force the
    # minimal preset, clear the security-suite parameters (so a bad config
    # cannot drag down startup again).
    if safemode_on:
        for key in ("plugins", "preset", "security"):
            kwargs.pop(key, None)
        kwargs["preset"] = "minimal"

    with _lock:
        if _current is not None and _current.is_running():
            return _current

        # split slot keys from runtime-parameter keys (by the live slot table:
        # includes custom slots registered at runtime; keys registered before the
        # np() call are recognized as slots)
        slots = snapshot_slots()
        slot_values = {k: v for k, v in kwargs.items() if k in slots}
        params = {k: v for k, v in kwargs.items() if k not in slots}

        # crash rescue: consume the rollback target left by the previous
        # norpagent-rescue run — file-level restore (WebUI settings / session
        # files) already ran; here the snapshot's slot config is merged into this
        # startup (parameters explicitly given by the user take priority).
        try:
            from norpagent.recovery import apply_pending_rollback

            pending = apply_pending_rollback()
        except Exception:  # noqa: BLE001
            pending = None
        if pending and isinstance(pending, dict):
            for key, value in (pending.get("layer") or {}).items():
                if key in slots and key not in slot_values:
                    slot_values[key] = value
            for key, value in (pending.get("params") or {}).items():
                if key not in params:
                    params[key] = value
            print(f"[norpagent] applied crash-rescue rollback snapshot: "
                  f"{pending.get('description') or pending.get('id') or ''}")

        layer = ArchLayer(config, **slot_values)
        mount_defaults(layer, prompt=prompt)
        layer.connect()

        registry, preset, extras = build_registry(layer, params=params)

        engine = NorpEngine(
            layer=layer,
            registry=registry,
            preset=preset,
            loop=layer["async_loop"],
            # frontend slot "HTML path direct mount" semantics (v0.9):
            # when the slot value is a .html/.htm file path, assemble it as
            # WebFrontend(html=<that path>), equivalent to address-style mounting.
            frontend=coerce_frontend(
                layer["frontend"], layer.subconfig("frontend")),
            extras=extras,
            task_params=params,
            prompt=prompt,
            safe_mode=safemode_on,
        )
        if snapshot_sessions:
            engine._snapshot_sessions = True
        try:
            engine.start()
        except Exception as exc:  # noqa: BLE001 — startup failure: give self-rescue hints
            import sys

            print(f"[norpagent] startup failed: {exc}", file=sys.stderr)
            print("  → safe mode: np(safemode='on') (loads only the minimal kernel)",
                  file=sys.stderr)
            print("  → crash rescue: norpagent-rescue rollback --last-good",
                  file=sys.stderr)
            raise
        _current = engine
        _register_atexit()
        return engine


def current() -> Optional[NorpEngine]:
    """The current engine (None when not started)."""
    return _current


def stop() -> bool:
    """Lifecycle function: whether the application has ended (True = the main loop should exit).

    Maps to the engine STOPPED state; True when there is no engine (nothing to do).
    """
    engine = _current
    return engine is None or engine.should_stop()


def submit(text: str, session_id: Optional[str] = None,
           task_params: Optional[Dict[str, Any]] = None,
           slot_overrides: Optional[Dict[str, Any]] = None) -> Any:
    """Submit user input to the current engine (requires np() started).

    ``slot_overrides`` (v0.9.2): task-level slot injection — temporarily overrides
    any slot implementation for the duration of this task (see manual 3.9), with
    higher priority than global remount.
    """
    engine = _current
    if engine is None:
        raise EngineError("not started: call np() or norpagent.launch() first")
    return engine.submit(
        text, session_id=session_id,
        task_params=task_params, slot_overrides=slot_overrides,
    )


def remount(**slot_values: Any) -> NorpEngine:
    """Runtime hot mount: replace any slot implementation of the current engine (the engine keeps running).

    Usage::

        np.remount(model="openai_compat")     # swap the model (takes effect on the next run)
        np.remount(tools=["echo"])            # swap the tool set
        np.remount(frontend="norpagent.frontends.headless:HeadlessFrontend")
        np.remount(flow_html="H:/path/flow.html")  # swap the flow page at runtime (HTTP not restarted)
        np.remount(html="H:/path/front.html")      # swap the main page at runtime

    Slot-group semantics (component / assembly / infrastructure / base service)
    are documented in norpagent.runtime.remount; html / flow_html are page
    hot-replace keys (mount parameters of the frontend slot); requires np() started.
    """
    engine = _current
    if engine is None:
        raise EngineError("not started: call np() or norpagent.launch() first")
    return engine.remount(**slot_values)


def shutdown() -> None:
    """Explicitly stop and clean up the current engine (idempotent)."""
    global _current
    engine = _current
    if engine is not None:
        try:
            engine.request_stop()
        finally:
            _current = None


def _atexit_shutdown() -> None:
    shutdown()


def is_running() -> bool:
    engine = _current
    return engine is not None and engine.is_running()


__all__ = [
    "launch",
    "current",
    "stop",
    "submit",
    "remount",
    "shutdown",
    "is_running",
    "NorpEngine",
    "EngineState",
    "EngineError",
]
