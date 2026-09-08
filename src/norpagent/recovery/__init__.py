# Copyright (c) 2026 xingluosama121, MIT Licensed
"""Work rollback (Recovery): snapshots / Undo / Redo / Rollback / crash rescue.

Rollback capability for agent work, in four layers:

1. **One-step Undo / Redo**: Web UI buttons / shortcuts (Ctrl+Z / Ctrl+Shift+Z) /
   API to undo or redo the most recent operation — effective immediately in
   process, reusing the remount hot-mount pipeline (the HTTP port stays the same).

2. **Rollback to any version**: browse the full snapshot history and roll the
   whole system back to any version in one click.

3. **Crash rescue**: the standalone CLI ``norpagent-rescue`` (pure standard
   library; runs no matter how broken the main program is) rolls back snapshots;
   the system suggests the "last known-good snapshot" for one-step recovery. A
   rollback is persisted as rollback_target.json, consumed automatically at the
   next np() / norpagent startup.

4. **Safe mode**: ``np(safemode="on")`` / CLI ``--safe-mode`` loads only the
   minimal kernel (skips all plugins, forces the minimal preset, does not read the
   WebUI settings file), keeping core rollback capabilities for repairs.

Snapshot content (default mode A = system-config level; mode B additionally
includes session data files):
- all architecture-layer slot configurations (mode / model / tools / session /
  sandbox / frontend / plugin dirs / security level...);
- engine runtime parameters (port / host / html / flow_html / model options...,
  sensitive keys redacted);
- WebUI settings file content;
- custom provider data (extension hooks registered via register_snapshot_provider).

Auto-snapshot timing: the startup baseline and after every system-state change
(remount / WebUI settings saved / plugin installed / mode switched). Manual
snapshots: the Web UI "snapshot" button or ``np.snapshot_system("description")``.

"Last known-good snapshot": after the engine starts successfully, a 30-second
health window (or the first task completing) auto-marks good; users can also mark
manually. The rescue CLI suggests it as the one-step restore target.

Usage::

    import norpagent as np
    np()
    np.snapshot_system("before installing plugins")  # manual snapshot
    np.undo()                                  # undo the most recent operation (in-process immediate)
    np.redo()                                  # redo
    np.rollback("20260818T230101_ab12cd")      # roll back to any snapshot
    np.list_snapshots()                        # timeline
    np.mark_good_snapshot("<id>")              # mark "known good"

Custom snapshot content (hook-style extension)::

    from norpagent import recovery
    recovery.register_snapshot_provider("my_state", capture=lambda eng: {...},
                                        restore=lambda eng, v: ...)

Storage: default ``~/.norpagent/snapshots/`` (overridable with the environment
variable ``NORPAGENT_SNAPSHOT_DIR`` or ``np(snapshot_dir=...)``).
"""

from __future__ import annotations

import threading
from typing import Any, Callable, Dict, List, Optional

from norpagent.recovery import capture, store

__version__ = "2.0.1"

# 品牌（v2.0.0 起正式宣传名）：远星 / FarStars——norpagent 调用方式与内核
# 名称不变，FarStars 仅作品牌冠名（import / PyPI 包名保持 norpagent）。
__brand_cn__ = "远星"
__brand_en__ = "FarStars"
__display_name__ = "FarStars（远星）· norpagent"


class RecoveryError(RuntimeError):
    """Rollback operation failed (nothing to undo / snapshot missing / application failed, etc.)."""


# replay-in-progress flag: restoring a snapshot itself triggers remount / config
# application, and those changes must not be auto-snapshotted again (otherwise an
# undo would immediately generate a new snapshot overwriting the redo branch).
_applying = False
_apply_lock = threading.RLock()

# custom snapshot providers: name -> (capture(engine)->json, restore(engine,value))
_providers: Dict[str, tuple] = {}
_providers_lock = threading.Lock()

# auto-snapshot switch (np(snapshots="off") disables)
_enabled = True
_enabled_lock = threading.Lock()

# auto-prune retention cap
_AUTO_PRUNE_KEEP = 200


# ── configuration ────────────────────────────────────────

def set_snapshot_dir(path: str) -> None:
    """Override the snapshot storage directory (in-process)."""
    store.set_snapshot_dir(path)


def get_snapshot_dir() -> str:
    return store.get_snapshot_dir()


def set_enabled(enabled: bool) -> None:
    """Toggle auto snapshots (explicit API calls still work)."""
    global _enabled
    with _enabled_lock:
        _enabled = bool(enabled)


def is_enabled() -> bool:
    with _enabled_lock:
        return _enabled


def register_snapshot_provider(
    name: str,
    capture: Callable[[Any], Any],
    restore: Optional[Callable[[Any, Any], None]] = None,
) -> None:
    """Register a custom snapshot provider (a hook for extending snapshot content / restore logic).

    - ``capture(engine) -> json value``: capture custom state;
    - ``restore(engine, value) -> None``: restore during replay (optional;
      when omitted the segment is only snapshotted, not replayed).
    Takes effect immediately; same-name registrations overwrite.
    """
    with _providers_lock:
        _providers[name] = (capture, restore)


def unregister_snapshot_provider(name: str) -> None:
    with _providers_lock:
        _providers.pop(name, None)


def _provider_callbacks() -> Dict[str, Callable[[Any], Any]]:
    with _providers_lock:
        return {k: v[0] for k, v in _providers.items()}


# ── capture ──────────────────────────────────────────────

def snapshot_system(
    description: str = "",
    tag: str = "manual",
    engine: Optional[Any] = None,
    sessions: Optional[bool] = None,
) -> Dict[str, Any]:
    """Capture the current system state, persist it as a snapshot, and return the manifest info entry.

    Usage::

        np.snapshot_system("before installing plugins")  # manual snapshot
        np.snapshot_system("annotation", engine=eng)     # specify the engine

    ``sessions``: None = follow the engine config (np(snapshot_sessions=...)),
    True/False override explicitly (snapshot mode B / A).
    """
    if engine is None:
        from norpagent.runtime import current

        engine = current()
    if sessions is None:
        sessions = bool(getattr(engine, "_snapshot_sessions", False))
    data = capture.capture_system(
        engine, description=description, tag=tag,
        sessions=sessions, providers=_provider_callbacks(),
    )
    info = store.write_snapshot(
        data, description=description, tag=tag, source="engine",
        sessions=sessions,
    )
    # auto prune: keep only the most recent 200 snapshots by default (prevent unbounded accumulation)
    try:
        if len(store.list_snapshots()) > _AUTO_PRUNE_KEEP:
            store.prune(_AUTO_PRUNE_KEEP)
    except Exception:  # noqa: BLE001
        pass
    return info


def snapshot_cli(
    args: Dict[str, Any],
    description: str = "",
    tag: str = "auto",
    sessions: bool = False,
) -> Dict[str, Any]:
    """Snapshot of the CLI startup shape (used internally by the norpagent command line)."""
    data = capture.capture_cli(args, description=description, tag=tag,
                               sessions=sessions)
    return store.write_snapshot(
        data, description=description, tag=tag, source="cli",
        sessions=sessions,
    )


def notify_system_change(
    engine: Optional[Any] = None,
    description: str = "system change",
) -> None:
    """Auto-snapshot entry after a system-state change (remount / config saved / plugin installed).

    - skipped while a replay is in progress (prevents undo from snapshotting itself);
    - skipped when auto snapshots are disabled;
    - snapshot failures are only logged; never break the main flow.
    """
    global _applying
    if _applying or not is_enabled():
        return
    if engine is None:
        try:
            from norpagent.runtime import current

            engine = current()
        except Exception:  # noqa: BLE001
            engine = None
    if engine is None:
        return
    if not getattr(engine, "is_running", lambda: False)():
        return
    try:
        snapshot_system(description=description, tag="auto",
                        engine=engine)
    except Exception:  # noqa: BLE001
        try:
            logger = getattr(engine, "_logger", None)
            if logger is not None:
                logger.warning("auto snapshot failed: %s", description,
                               exc_info=True)
        except Exception:  # noqa: BLE001
            pass


# ── replay (in-process immediate) ────────────────────────

def _restore_layer(engine: Any, data: Dict[str, Any]) -> List[str]:
    """Reapply the snapshot's slot config and page parameters to the running engine.

    Returns the list of actually applied keys. Goes through the remount hot-mount
    pipeline: component slots take effect on the next run; assembly slots rebuild
    the AgentRuntime; the HTTP port stays the same.
    """
    from norpagent.arch.slots import snapshot_slots

    known = snapshot_slots()
    layer = getattr(engine, "layer", None)
    slots: Dict[str, Any] = {}
    skipped: List[str] = []
    for key, value in (data.get("layer") or {}).items():
        if key not in known:
            skipped.append(key)
            continue
        if capture.is_marker(value):
            skipped.append(key)
            continue
        # skip slots identical to the current config to avoid pointless component
        # rebuilds / frontend restarts (e.g. every undo restarting the HTTP listener).
        try:
            current = layer.config.get(key) if layer is not None else None
            if current is not None and capture.jsonable(current) == value:
                continue
        except Exception:  # noqa: BLE001
            pass
        slots[key] = value

    web_keys = ("html", "flow_html")
    params: Dict[str, Any] = {}
    for key, value in (data.get("params") or {}).items():
        if capture.is_marker(value):
            continue
        if key in web_keys:
            slots[key] = value
        elif key in capture._WEB_PARAM_KEYS or key in (
                "model_name", "base_url"):
            params[key] = value

    # update engine params (used by subsequent frontend attach / next run)
    if params:
        engine_params = getattr(engine, "params", None)
        if engine_params is not None:
            engine_params.update(params)

    applied: List[str] = []
    if slots:
        try:
            engine.remount(**slots)
            applied = list(slots)
        except Exception as exc:  # noqa: BLE001
            raise RecoveryError(
                f"snapshot slot application failed: {exc} ({len(skipped)} unserializable keys skipped)"
            ) from exc
    return applied


def _restore_webui_live(engine: Any, cfg: Optional[Dict[str, Any]]) -> None:
    """Restore WebUI settings into the live UI (disk write + in-memory config + application)."""
    if not isinstance(cfg, dict):
        return
    capture._write_webui_config(cfg)
    frontend = getattr(engine, "frontend", None)
    ui = getattr(frontend, "_ui", None) if frontend is not None else None
    restore = getattr(ui, "restore_config", None)
    if callable(restore):
        try:
            restore(cfg)
        except Exception:  # noqa: BLE001
            pass


def _apply_snapshot(engine: Any, info: Dict[str, Any],
                    data: Dict[str, Any]) -> Dict[str, Any]:
    """Apply a snapshot to the running engine (shared by Undo / Redo / Rollback)."""
    global _applying
    with _apply_lock:
        _applying = True
        try:
            snap_data = data.get("data") if isinstance(data, dict) else None
            if not isinstance(snap_data, dict):
                snap_data = data
            applied = _restore_layer(engine, snap_data)
            _restore_webui_live(engine, snap_data.get("webui_config"))
            # mode B: whole-file session restore
            capture.restore_files(snap_data,
                                  snap_id=(data.get("id") or ""))
            # custom provider restore hooks
            pd = snap_data.get("providers") or {}
            with _providers_lock:
                restorers = {k: v[1] for k, v in _providers.items()
                             if v[1] is not None}
            for name, value in pd.items():
                fn = restorers.get(name)
                if fn is None or (isinstance(value, dict)
                                  and "error" in value):
                    continue
                try:
                    fn(engine, value)
                except Exception:  # noqa: BLE001
                    pass
        finally:
            _applying = False
    return {"ok": True, "applied_slots": applied,
            "snapshot_id": info.get("id")}


def _current_engine() -> Any:
    from norpagent.runtime import current

    engine = current()
    if engine is None:
        raise RecoveryError("engine not started: call np() or norpagent.launch() first")
    return engine


def undo(engine: Optional[Any] = None) -> Dict[str, Any]:
    """Undo the most recent operation: restore to the previous snapshot (in-process immediate)."""
    if engine is None:
        engine = _current_engine()
    target = store.undo_target()
    if target is None:
        raise RecoveryError("nothing to undo (already at the earliest state)")
    info, data = target
    result = _apply_snapshot(engine, info, data)
    store.set_current(info["id"])
    result["undo"] = True
    result["description"] = info.get("description")
    return result


def redo(engine: Optional[Any] = None) -> Dict[str, Any]:
    """Redo the most recent undo: restore to the pre-undo snapshot (in-process immediate)."""
    if engine is None:
        engine = _current_engine()
    target = store.redo_target()
    if target is None:
        raise RecoveryError("nothing to redo (already at the newest state)")
    info, data = target
    result = _apply_snapshot(engine, info, data)
    store.set_current(info["id"])
    result["redo"] = True
    result["description"] = info.get("description")
    return result


def rollback(snap_id: Optional[str] = None,
             engine: Optional[Any] = None) -> Dict[str, Any]:
    """Roll back to any historical snapshot.

    Usage::

        np.rollback("20260818T230101_ab12cd")   # roll back to the given snapshot
        np.rollback()                           # roll back to the last known-good snapshot

    When ``snap_id`` is omitted, rolls back to the "last known-good snapshot".
    """
    if engine is None:
        engine = _current_engine()
    if snap_id is None:
        snap_id = store.last_good_id()
        if snap_id is None:
            raise RecoveryError("no snapshot marked \"known good\"")
    data = store.read_snapshot(snap_id)
    if data is None:
        raise RecoveryError(f"snapshot does not exist: {snap_id}")
    info = next(
        (item for item in store.list_snapshots()
         if item.get("id") == snap_id),
        {"id": snap_id, "description": ""},
    )
    result = _apply_snapshot(engine, info, data)
    store.set_current(snap_id)
    result["rollback"] = True
    result["description"] = info.get("description")
    return result


def list_snapshots() -> List[Dict[str, Any]]:
    """All timeline snapshot entries (including index / good / description, etc.)."""
    items = store.list_snapshots()
    current = store.current_index()
    last_good = store.last_good_id()
    for item in items:
        item["is_current"] = item.get("index") == current
        item["is_last_good"] = item.get("id") == last_good
    return items


def mark_good(snap_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Mark a snapshot as \"known good\" (defaults to the current snapshot)."""
    if snap_id is None:
        snap_id = store.current_id()
    if not snap_id:
        raise RecoveryError("no snapshot to mark")
    return store.mark_good(snap_id)


def last_good_id() -> Optional[str]:
    return store.last_good_id()


def delete_snapshot(snap_id: Optional[str] = None) -> bool:
    """Delete one snapshot from the timeline (files + manifest entry).

    The current snapshot may be deleted too: the pointer then moves to the
    previous entry (standard Undo-style semantics), never leaving the timeline
    pointer dangling.
    """
    if snap_id is None:
        snap_id = store.current_id()
    return store.delete_snapshot(snap_id or "")


def rename_snapshot(snap_id: str, description: str) -> Optional[Dict[str, Any]]:
    """Rename a snapshot's description (display text shown in the rollback panel)."""
    return store.rename_snapshot(snap_id, description)


def prune(keep: int = 50) -> int:
    """Keep only the most recent ``keep`` snapshots."""
    return store.prune(keep)


# ── startup integration ─────────────────────────────────

def apply_pending_rollback() -> Optional[Dict[str, Any]]:
    """Consume the crash-rescue rollback target at startup (np() path).

    - file-level restore (WebUI settings / session files) runs immediately;
    - returns the data dict (including layer / params) for the startup flow to
      merge into the slot config; None when there is no rollback target.
    """
    payload = store.consume_rollback_target()
    if payload is None:
        return None
    data = payload.get("data") or {}
    capture.restore_files(data, snap_id=payload.get("snapshot_id") or "")
    return data


def apply_pending_rollback_cli() -> Optional[Dict[str, Any]]:
    """Consume the rollback target at startup (CLI path): file-level restore + return the data dict."""
    payload = store.consume_rollback_target()
    if payload is None:
        return None
    data = payload.get("data") or {}
    capture.restore_files(data, snap_id=payload.get("snapshot_id") or "")
    return data


__all__ = [
    "RecoveryError",
    "set_snapshot_dir", "get_snapshot_dir",
    "set_enabled", "is_enabled",
    "register_snapshot_provider", "unregister_snapshot_provider",
    "snapshot_system", "snapshot_cli", "notify_system_change",
    "undo", "redo", "rollback",
    "list_snapshots", "mark_good", "last_good_id", "prune",
    "delete_snapshot", "rename_snapshot",
    "apply_pending_rollback", "apply_pending_rollback_cli",
]
