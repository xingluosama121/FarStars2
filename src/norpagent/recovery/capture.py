# Copyright (c) 2026 xingluosama121, MIT Licensed
"""Snapshot capture and replay: system state <-> JSON snapshot.

Captured content (snapshot mode A, default):
- architecture layer slot configuration (layer.config, including mode / model /
  tools / session / sandbox / frontend / plugin dirs / security level — all slot values);
- engine runtime parameters (engine.params, port / host / html / flow_html /
  model_name / base_url etc., sensitive keys redacted);
- WebUI settings file (~/.norpagent/webui_config.json content, api_key redacted);
- custom provider data (extension hooks registered via register_snapshot_provider).

Snapshot mode B (``snapshots_session="on"``): additionally copies the session
storage file into the snapshot attachment directory; on rollback the whole file
is restored (this overwrites conversation records written after the rollback point).

Serializability rules:
- built-in types are saved as-is;
- unserializable values such as instances / classes / functions → record a type
  marker ``{"__instance__": "pkg.mod.QualName"}``; skipped during replay with a
  notice (honest degradation, no forged state).
"""

from __future__ import annotations

import json
import os
from typing import Any, Callable, Dict, List, Optional

# sensitive-key redaction (snapshots go to disk; keys must not be written into snapshot files)
_REDACT_KEYS = frozenset((
    "api_key", "api-key", "apikey", "private_key", "private-key",
    "secret", "token", "password", "passwd", "authorization",
))

# engine params that are web-mount / model config keys (handled specially during replay)
_WEB_PARAM_KEYS = frozenset((
    "port", "host", "open_browser", "language", "html", "flow_html",
    "sse_queue_size", "sse_queue_policy",
))

# default session storage file (mode B capture target)
_DEFAULT_SESSION_FILES = (
    os.path.join(os.path.expanduser("~"), ".norpagent", "sessions.db"),
)


def jsonable(value: Any, _depth: int = 0) -> Any:
    """Convert any value into a JSON-serializable shape (sensitive keys redacted).

    Unserializable instances / classes / functions → ``{"__instance__": qualified type name}``.
    """
    if _depth > 8:
        return repr(value)[:200]
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return value
    if isinstance(value, (list, tuple)):
        return [jsonable(v, _depth + 1) for v in value]
    if isinstance(value, dict):
        out: Dict[str, Any] = {}
        for k, v in value.items():
            key = str(k)
            if key.lower() in _REDACT_KEYS:
                out[key] = "<redacted>"
            else:
                out[key] = jsonable(v, _depth + 1)
        return out
    try:
        json.dumps(value)
        return value
    except (TypeError, ValueError):
        return {
            "__instance__": (
                f"{type(value).__module__}.{type(value).__qualname__}"
            )
        }


def is_marker(value: Any) -> bool:
    """Whether the value is an "unserializable" type marker (skipped during replay)."""
    return isinstance(value, dict) and "__instance__" in value


def _read_webui_config() -> Optional[Dict[str, Any]]:
    """Read the WebUI settings file (None when missing or corrupt)."""
    path = os.environ.get(
        "NORPAGENT_WEBUI_CONFIG",
        os.path.join(os.path.expanduser("~"), ".norpagent",
                     "webui_config.json"),
    )
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else None
    except (OSError, ValueError):
        return None


def _session_files(engine: Any) -> List[Dict[str, Any]]:
    """Mode B: collect session storage files (default sessions.db + explicit paths from slot config)."""
    files: List[str] = []
    for path in _DEFAULT_SESSION_FILES:
        if os.path.isfile(path):
            files.append(path)
    if engine is not None:
        layer = getattr(engine, "layer", None)
        if layer is not None:
            session_val = None
            try:
                session_val = layer.config.get("session")
            except Exception:  # noqa: BLE001
                pass
            if isinstance(session_val, str) and not session_val.startswith(";"):
                # a name (sqlite / memory) or a path (contains .db / the file exists)
                cand = session_val.partition(";")[0]
                if (cand.endswith(".db") or os.path.isabs(cand)
                        or os.path.sep in cand) and os.path.isfile(cand):
                    files.append(cand)
    seen = set()
    out = []
    for path in files:
        if path in seen:
            continue
        seen.add(path)
        try:
            out.append({
                "name": os.path.basename(path),
                "path": os.path.abspath(path),
                "size": os.path.getsize(path),
            })
        except OSError:
            continue
    return out


def _norpagent_version() -> str:
    try:
        import norpagent as np  # noqa: F401  lazy import to avoid cycles

        return getattr(np, "__version__", "unknown")
    except Exception:  # noqa: BLE001
        return "unknown"


def capture_system(
    engine: Any,
    description: str = "",
    tag: str = "auto",
    sessions: bool = False,
    providers: Optional[Dict[str, Callable[[Any], Any]]] = None,
) -> Dict[str, Any]:
    """Capture the current system state as a snapshot data dict (not yet written to disk).

    ``providers``: custom capture hooks registered via register_snapshot_provider
    (name -> capture(engine) -> JSON value).
    """
    layer_config: Dict[str, Any] = {}
    params: Dict[str, Any] = {}
    if engine is not None:
        layer = getattr(engine, "layer", None)
        if layer is not None:
            try:
                layer_config = {
                    str(k): jsonable(v)
                    for k, v in layer.config.items()
                }
            except Exception:  # noqa: BLE001
                layer_config = {}
        try:
            params = jsonable(dict(getattr(engine, "params", None) or {}))
        except Exception:  # noqa: BLE001
            params = {}

    provider_data: Dict[str, Any] = {}
    for name, fn in (providers or {}).items():
        try:
            provider_data[name] = jsonable(fn(engine))
        except Exception:  # noqa: BLE001 — a single provider failure must not break the snapshot
            provider_data[name] = {"error": "provider capture failed"}

    return {
        "format": 1,
        "source": "engine",
        "description": description,
        "tag": tag,
        "norpagent_version": _norpagent_version(),
        "layer": layer_config,
        "params": params,
        "webui_config": jsonable(_read_webui_config()),
        "session_files": _session_files(engine) if sessions else [],
        "providers": provider_data,
    }


def capture_cli(
    args: Dict[str, Any],
    description: str = "",
    tag: str = "auto",
    sessions: bool = False,
) -> Dict[str, Any]:
    """Snapshot of the CLI startup shape (source="cli"): command-line args + WebUI settings.

    During rescue rollback, CLI shapes merge back into startup arguments; engine
    shapes (np()) merge into the layer. File-level restoration (webui settings /
    session files) is identical for both shapes.
    """
    return {
        "format": 1,
        "source": "cli",
        "description": description,
        "tag": tag,
        "norpagent_version": _norpagent_version(),
        "cli": jsonable(args or {}),
        "webui_config": jsonable(_read_webui_config()),
        "session_files": [] if not sessions else [
            {"name": os.path.basename(p), "path": os.path.abspath(p),
             "size": os.path.getsize(p)}
            for p in _DEFAULT_SESSION_FILES if os.path.isfile(p)
        ],
        "providers": {},
    }


# ── replay ───────────────────────────────────────────────

def _write_webui_config(cfg: Optional[Dict[str, Any]]) -> None:
    """Write the snapshot's WebUI settings back to disk (takes effect on next start / restart)."""
    if not isinstance(cfg, dict):
        return
    path = os.environ.get(
        "NORPAGENT_WEBUI_CONFIG",
        os.path.join(os.path.expanduser("~"), ".norpagent",
                     "webui_config.json"),
    )
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = f"{path}.{os.getpid()}.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    except OSError:
        pass


def _restore_session_files(snapshot_data: Dict[str, Any],
                           snap_id: str = "") -> int:
    """Mode B: copy the snapshot's session files back to their original paths. Returns the number restored."""
    from norpagent.recovery.store import attachment_dir

    restored = 0
    for item in snapshot_data.get("session_files") or []:
        cand = None
        if snap_id:
            p = os.path.join(attachment_dir(snap_id), item.get("name", ""))
            if os.path.isfile(p):
                cand = p
        if not cand:
            continue
        target = item.get("path")
        if not target:
            continue
        try:
            import shutil

            os.makedirs(os.path.dirname(os.path.abspath(target)),
                        exist_ok=True)
            shutil.copyfile(cand, target)
            restored += 1
        except OSError:
            continue
    return restored


def restore_files(snapshot_data: Dict[str, Any],
                  snap_id: str = "") -> Dict[str, Any]:
    """File-level restore: WebUI settings + session files (shared by engine and CLI shapes).

    Returns {"webui": bool, "sessions": int}. Shared by in-process replay and the
    rescue CLI rollback. ``snap_id`` locates mode-B session attachments.
    """
    cfg = snapshot_data.get("webui_config")
    _write_webui_config(cfg)
    sessions = _restore_session_files(snapshot_data, snap_id)
    return {"webui": isinstance(cfg, dict), "sessions": sessions}


__all__ = [
    "jsonable", "is_marker", "capture_system", "capture_cli",
    "restore_files",
]
