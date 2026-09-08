# Copyright (c) 2026 xingluosama121, MIT Licensed
"""Runtime hot remount: any slot can be replaced at runtime.

After np() starts, while the engine is still RUNNING, replace any slot
implementation at any time:

    import norpagent as np
    np()                                   # start (default web frontend)
    ...
    np.remount(model="openai_compat")      # swap the model: takes effect on the next run()
    np.remount(tools=["echo", "get_time"]) # swap the tool set: takes effect on the next run()
    np.remount(session="sqlite")           # swap session storage: AgentRuntime hot-rebuilds
    np.remount(security="high")            # swap the security level: old protection hooks unsubscribe first
    np.remount(frontend="norpagent.frontends.console:ConsoleFrontend")
    np.remount(async_loop="myapp.loop:create")
    np.remount(model="myapp.model:create") # replace a module file at runtime (module cache invalidated)

Replacement semantics grouped by slot:

1. **component slots** (model / tools / hooks / security / plugins):
   reapplied to the same registry and rewrite the final preset. model / tools
   take effect on the next run() — the agent loop re-resolves models and tool
   schemas on every run. Architecture-level subscriptions (hook extensions /
   security kit / plugins) unsubscribe the old ones before remounting; duplicate
   firing never stacks.

2. **assembly slots** (session / sandbox / scheduler / ui / agent_runtime /
   preset / context_store / project_manager): these components are resolved at
   AgentRuntime construction time; after replacement the runtime is **hot-rebuilt**
   — the old runtime closes (releasing sandboxes / components / unsubscribing the
   renderer), the new runtime assembles per the current architecture layer, and
   the frontend renderer rebinds (the HTTP port stays the same).

3. **infrastructure slots** (frontend / async_loop): stop the old implementation,
   start the new one. When async_loop is replaced, in-flight tasks on the old
   loop are abandoned (see _swap_loop); a frontend replacement failure
   auto-rolls-back to the old frontend.

4. **base-service slots** (logger / storage / error_handler): directly update
   engine references; no structure rebuild needed.

5. **custom slots** (v0.9 hot-pluggable slot table): slots registered via
   register_slot() can also be np.remount-ed — reapplied per the spec's applier
   (must be reentrant-safe); custom assembly slots with
   remount_rebuild_agent=True hot-rebuild the AgentRuntime after replacement,
   consistent with built-in assembly slots.

6. **page hot-replace keys** (html / flow_html, v0.9): they are mount parameters
   of the frontend slot rather than the slot itself — remounting a page does not
   restart the HTTP service and keeps the port unchanged; a browser refresh shows
   the new page; falsy values (None / "") unmount and fall back to the library's
   built-in assets. They are also written into engine.params so later frontend
   hot mounts / attach reuse the new values (the same data path as the np(html=...)
   startup passthrough). When the user registers a same-named custom slot via
   register_slot, the slot table takes priority (handled per slot semantics).

Any slot can be remounted — this is the runtime embodiment of "everything except
the minimal bottom kernel is a slot": assemblies can swap parts while running;
the slot table itself can also plug in new slots while running (register_slot).
"""

from __future__ import annotations

import dataclasses
import inspect
import os
from typing import Any, Dict, FrozenSet

from norpagent.arch.slots import snapshot_slots
from norpagent.kernel.presets import Preset
from norpagent.runtime.engine import EngineError
from norpagent.runtime.mount import apply_slot_overrides, coerce_frontend

# slots requiring a hot AgentRuntime rebuild after replacement:
# these components are resolved at runtime construction time (not re-resolved per run).
_AGENT_REBUILD_SLOTS: FrozenSet[str] = frozenset((
    "session",
    "sandbox",
    "scheduler",
    "ui",
    "agent_runtime",
    "preset",
    "context_store",
    "project_manager",
))

# page hot-replace keys (v0.9): mount parameters of the frontend slot rather than
# the slot itself. remount accepts html / flow_html / farstars_html directly —
# page replacement does not restart the HTTP service; falsy values unmount and
# fall back to the library's built-in assets. Also written into engine.params so
# later frontend hot mounts / attach reuse them (the same data path as the
# np(html=...) startup passthrough). When the user registers a same-named custom
# slot via register_slot, the slot table takes priority (handled per slot
# semantics; see remount_engine).
_WEB_PAGE_KEYS: FrozenSet[str] = frozenset(("html", "flow_html", "farstars_html"))


def remount_engine(engine: Any, **slot_values: Any) -> Any:
    """Execute a hot mount on the running engine (see the slot-group semantics in the module docstring).

    Returns the engine itself; raises EngineError on illegal slot names or when no slot was passed.
    """
    if not slot_values:
        raise EngineError("hot mount needs at least one slot parameter")
    known = snapshot_slots()
    # html / flow_html are mount parameters of the frontend slot rather than the
    # slot itself; handled as "page hot-replace keys"; when the user registers a
    # same-named custom slot via register_slot, the slot table takes priority
    # (handled per slot semantics).
    web_vals = {
        k: slot_values[k] for k in _WEB_PAGE_KEYS
        if k in slot_values and k not in known
    }
    slot_values = {k: v for k, v in slot_values.items() if k not in web_vals}
    if not slot_values and not web_vals:
        raise EngineError("hot mount needs at least one slot parameter")
    unknown = [k for k in slot_values if k not in known]
    if unknown:
        hint = ""
        if set(unknown) & set(_WEB_ATTACH_PARAM_KEYS):
            hint = (
                "; web parameters such as port / host / open_browser / language "
                "should use the address-clause form "
                "np.remount(frontend='norpagent.frontends.web:WebFrontend;port=...') "
                "(this restarts the HTTP listener)"
            )
        raise EngineError(
            f"unknown slots {unknown}. Available slots: {list(known)}{hint}"
        )
    # page hot-replace keys are pre-validated first (same rules as
    # WebUI._resolve_html): bad paths fail fast before slot changes take effect,
    # leaving no half-applied state.
    for key in _WEB_PAGE_KEYS:
        _validate_web_page_value(key, web_vals.get(key))

    layer = engine.layer
    logger = engine._logger

    # 1. update the architecture layer: replace slot values and re-resolve implementations.
    #    string addresses invalidate the module cache first — "edit module file →
    #    remount" is hot reload.
    for slot, value in slot_values.items():
        layer.remount(slot, value)

    # 2. reapply slot overrides on the same registry (old architecture-level subscriptions unsubscribe first).
    final, extras = apply_slot_overrides(engine.registry, layer, engine.params)

    # 3. preset and base-service updates.
    _apply_preset(engine, final)
    engine.extras = dict(extras)
    engine._logger = engine.extras.get("logger")
    engine._error_handler = engine.extras.get("error_handler")
    logger = engine._logger

    # 4. assembly slots: hot-rebuild the agent runtime.
    #    the built-in assembly-slot set plus custom-slot specs'
    #    remount_rebuild_agent flag jointly decide (v0.9 hot-pluggable slot table).
    rebuild = bool(_AGENT_REBUILD_SLOTS & set(slot_values)) or any(
        bool(getattr(known.get(k), "remount_rebuild_agent", False))
        for k in slot_values
    )
    if rebuild and engine._agent is not None:
        engine._swap_agent()

    # 5. page hot-replace keys: first write engine.params (reused by later
    #    frontend hot mounts / attach), then immediately swap pages via
    #    mount_page (HTTP not restarted; port unchanged). Done before the
    #    frontend hot swap: if the frontend slot is replaced in the same call,
    #    the new frontend reads the just-updated params on attach, keeping the
    #    page and parameters consistent.
    _apply_web_keys(engine, web_vals)

    # 6. infrastructure slots: frontend / event loop stop-old-start-new.
    if "frontend" in slot_values:
        _swap_frontend(engine)
    if "async_loop" in slot_values:
        _swap_loop(engine)

    if logger is not None:
        try:
            names = sorted(set(slot_values) | set(web_vals))
            logger.info("norpagent hot mount done: %s", ", ".join(names))
        except Exception:  # noqa: BLE001
            pass
    # work rollback: auto snapshot after a system-state change (the replay lock of
    # recovery suppresses snapshots of the restore itself, so an undo never
    # self-snapshots and overwrites the redo branch immediately).
    try:
        from norpagent.recovery import notify_system_change

        notify_system_change(
            engine,
            description="hot mount: " + ", ".join(
                sorted(set(slot_values) | set(web_vals))),
        )
    except Exception:  # noqa: BLE001 — snapshot failure must not break the hot mount
        pass
    return engine


def _validate_web_page_value(key: str, value: Any) -> None:
    """Pre-validate a page hot-replace key's value (same rules as WebUI._resolve_html).

    - falsy (None / "") → unmount, valid;
    - starts with "<" after strip → HTML content, valid;
    - otherwise it must be an existing file, or ValueError (fail fast, avoiding a
      half-applied slot change where the page key fails midway).
    """
    if not value:
        return
    src = str(value).strip()
    if not src or src.startswith("<"):
        return
    if not os.path.isfile(src):
        raise ValueError(
            f"{key} is neither HTML content (starting with '<') nor an existing file: {src!r}"
        )


def _apply_web_keys(engine: Any, web_vals: Dict[str, Any]) -> None:
    """Apply the page hot-replace keys html / flow_html (v0.9).

    - updates engine.params: later frontend attach / hot mounts reuse the new
      values (params also carries task-parameter passthrough; other keys unaffected);
    - when the current frontend is a web frontend and already attached, swap the
      page immediately via mount_page — the HTTP service is not restarted and the
      port stays the same; a browser refresh shows the new page;
    - falsy values (None / "") count as unmounting, falling back to the library's
      built-in assets;
    - non-web frontends (console / headless etc.) only update parameters; no side effects.
    """
    params = getattr(engine, "params", None)
    if params is None:
        params = {}
    frontend = getattr(engine, "frontend", None)
    page_of = {"html": "front", "flow_html": "flow", "farstars_html": "farstars"}
    for key in ("html", "flow_html", "farstars_html"):
        if key not in web_vals:
            continue
        value = web_vals[key]
        value = str(value) if value else None
        params[key] = value
        if getattr(frontend, "frontend_id", None) == "web":
            mount = getattr(frontend, "mount_page", None)
            if callable(mount):
                mount(page_of[key], value)


def _apply_preset(engine: Any, final: Preset) -> None:
    """Attach the recomputed final preset to the engine and the running agent.

    Maintains the initial assembly's object-identity convention: the preset object
    registered in the registry and the preset object held by the AgentRuntime stay
    the same instance (the frontend's hot rewrites of preset.tools rely on this).
    """
    engine.preset = final
    agent = engine._agent
    if agent is None:
        return
    try:
        agent.preset = final
    except Exception:  # noqa: BLE001 — skip when a custom runtime rejects it
        # when a custom runtime squeezed the preset into a non-writable attribute,
        # sync field-by-field in place as fallback
        try:
            old = agent.preset
            for f in dataclasses.fields(Preset):
                setattr(old, f.name, getattr(final, f.name))
            engine.preset = old
        except Exception:  # noqa: BLE001
            pass


# WebFrontend.attach reads port/host/open_browser/language/html/flow_html from
# engine.params and overrides constructor values. These keys come from np()
# parameter passthrough at first startup; if left unhandled during hot mount,
# they would push the new values passed into this remount back (e.g. starting with
# np(html=...) would make remount(frontend="...;html=other page") never take
# effect). Shield rule: only keys **explicitly given** in this remount are
# shielded from startup parameters; keys not explicitly given (e.g. port) keep the
# startup parameters — so a "swap page" hot mount keeps the browser URL unchanged.
_WEB_ATTACH_PARAM_KEYS: FrozenSet[str] = frozenset((
    "port", "host", "open_browser", "language", "html", "flow_html", "farstars_html",
))


def _explicit_web_keys(engine: Any, new_impl: Any) -> FrozenSet[str]:
    """Web-parameter keys explicitly given in this remount.

    - string address: keys in the clause (";key=value") are explicit;
    - instance: keys whose constructor arguments differ from defaults are explicit
      (html / flow_html judged by the _html / _flow_html attributes; None counts
      as not given). When a custom implementation cannot be introspected, the
      empty set is returned (everything follows startup parameters; behavior safe).
    """
    raw = engine.layer.config.get("frontend")
    if isinstance(raw, str):
        sub = engine.layer._subconfigs.get("frontend", {}) or {}
        keys = frozenset(k for k in sub if k in _WEB_ATTACH_PARAM_KEYS)
        # HTML path direct mount: the path itself is an explicit html parameter
        # (equivalent to "WebFrontend;html=<path>"), so the old html in startup
        # parameters must also be shielded. Note: exclude address clauses (";"
        # — "WebFrontend;flow_html=...x.html" also ends with .html but is not a
        # path direct mount).
        if ";" not in raw and raw.strip().lower().endswith((".html", ".htm")):
            keys = keys | frozenset(("html",))
        return keys
    try:
        sig = inspect.signature(type(new_impl).__init__)
    except Exception:  # noqa: BLE001
        return frozenset()
    keys = set()
    for name, param in sig.parameters.items():
        if name not in _WEB_ATTACH_PARAM_KEYS:
            continue
        if param.default is inspect.Parameter.empty:
            continue
        if name == "html":
            actual, default = getattr(new_impl, "_html", None), None
        elif name == "flow_html":
            actual, default = getattr(new_impl, "_flow_html", None), None
        elif name == "farstars_html":
            actual, default = getattr(new_impl, "_farstars_html", None), None
        else:
            actual, default = getattr(new_impl, name, None), param.default
        if actual != default:
            keys.add(name)
    return frozenset(keys)


def _effective_web_value(impl: Any, key: str, fallback: Any) -> Any:
    """Get the actually effective value of a web parameter key on the frontend implementation (for writing back to params)."""
    attr = {
        "port": "port",
        "host": "host",
        "open_browser": "open_browser",
        "html": "_html",
        "flow_html": "_flow_html",
        "farstars_html": "_farstars_html",
    }.get(key)
    if attr is None or not hasattr(impl, attr):
        return fallback
    return getattr(impl, attr)


def _swap_frontend(engine: Any) -> None:
    """Hot-replace the frontend slot: stop the old frontend → attach the new → start.

    During attach, engine.params temporarily shields the web keys explicitly given
    in this remount so the remount values are authoritative; after a successful
    attach, those keys' **actually effective values** are written back to params
    (e.g. the real port after port shifting, the resolved page parameters after
    attach) — afterwards params always reflect the frontend's current values, and
    later attach / hot mounts are not pushed back by old startup parameters. When
    the new frontend fails to attach / start, the original params are restored and
    the old frontend is rolled back (best effort).

    v0.9: an .html/.htm path string passed through the architecture layer (HTML
    path direct mount) is semantically converted here into WebFrontend(html=<path>),
    equivalent to address-style mounting.
    """
    old = engine.frontend
    new_impl = coerce_frontend(
        engine.layer["frontend"], engine.layer.subconfig("frontend"))
    if new_impl is old:
        return
    if old is not None:
        try:
            old.stop()
        except Exception:  # noqa: BLE001
            pass
    engine.frontend = new_impl
    params = getattr(engine, "params", None) or {}
    shielded = {k: params.pop(k, None) for k in _explicit_web_keys(engine, new_impl)}
    try:
        new_impl.attach(engine)
        new_impl.start()
    except Exception:
        # new frontend failed to start: restore the original startup parameters first, then roll back the old frontend
        if shielded:
            params.update(shielded)
        engine.frontend = old
        if old is not None:
            try:
                old.attach(engine)
                old.start()
            except Exception:  # noqa: BLE001
                pass
        raise
    # success: write the actually effective values of this call's explicit keys
    # back to params (params also carries task-parameter passthrough; other keys unchanged).
    for k, v in shielded.items():
        params[k] = _effective_web_value(new_impl, k, v)


def _swap_loop(engine: Any) -> None:
    """Hot-replace the async_loop slot: stop the old loop → start the new loop.

    Note: in-flight tasks on the old loop are abandoned (nobody consumes their
    results). Replace the event loop when no tasks are running; a replacement
    failure rolls back to the old loop best effort.
    """
    old = engine.loop
    new_impl = engine.layer["async_loop"]
    if new_impl is old:
        return
    if old is not None:
        try:
            old.stop()
            old.join(timeout=2.0)
        except Exception:  # noqa: BLE001
            pass
    engine.loop = new_impl
    try:
        new_impl.start()
    except Exception:
        # new loop failed to start: roll back best effort
        engine.loop = old
        if old is not None:
            try:
                old.start()
            except Exception:  # noqa: BLE001
                pass
        raise


__all__ = ["remount_engine"]
