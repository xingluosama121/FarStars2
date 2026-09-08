# Copyright (c) 2026 xingluosama121, MIT Licensed
"""Snapshot storage layer (pure standard library): manifest timeline + one JSON file per snapshot.

The crash-rescue CLI (``norpagent-rescue``, norpagent.rescue module) shares this
storage format with this module, and both depend **only on the standard library** —
even if the main program cannot start at all due to config errors or plugin
problems, the rescue tool can still read / roll back snapshots.

Directory layout (default ``~/.norpagent/snapshots/``; overridable with the
environment variable ``NORPAGENT_SNAPSHOT_DIR`` or ``set_snapshot_dir()``)::

    <snapshot_dir>/
        manifest.json              # timeline metadata + current pointer + last good snapshot
        snap/<snap_id>.json        # one file per snapshot
        attachments/<snap_id>/…    # session file copies (snapshot mode B: includes session data)
        rollback_target.json       # crash-rescue rollback target (deleted after being consumed at next startup)

manifest.json structure::

    {
      "version": 1,
      "current": 2,                 # current pointer (index of the most recently applied/generated snapshot; -1 = none)
      "last_good": "…",             # id of the last known-good snapshot (nullable)
      "snapshots": [
        {"id", "created_at", "description", "tag", "good", "source",
         "sessions", "size"}
      ]
    }

Pointer semantics (Undo / Redo rely on it):
- a new snapshot appends to the tail and ``current`` points at it;
- when a new snapshot is generated in the middle of the timeline (after undo),
  **truncate** all snapshots after it (standard undo semantics: a new operation
  starts a new branch);
- Undo = apply current-1 and move current back; Redo = apply current+1.
"""

from __future__ import annotations

import json
import os
import shutil
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

MANIFEST_VERSION = 1

_default_dir: Optional[str] = None
_lock = threading.RLock()


def _homedir() -> str:
    return os.path.expanduser("~")


def get_snapshot_dir() -> str:
    """Snapshot directory (explicit set_snapshot_dir > environment variable > default).

    Explicit programmatic calls are most specific and win; the environment variable
    ``NORPAGENT_SNAPSHOT_DIR`` comes next; default is ``~/.norpagent/snapshots``.
    """
    global _default_dir
    if _default_dir:
        return _default_dir
    env = os.environ.get("NORPAGENT_SNAPSHOT_DIR", "").strip()
    if env:
        return env
    return os.path.join(_homedir(), ".norpagent", "snapshots")


def set_snapshot_dir(path: str) -> None:
    """Override the snapshot directory (in-process only; not persisted)."""
    global _default_dir
    with _lock:
        _default_dir = path


def _manifest_path() -> str:
    return os.path.join(get_snapshot_dir(), "manifest.json")


def _snap_path(snap_id: str) -> str:
    return os.path.join(get_snapshot_dir(), "snap", f"{snap_id}.json")


def attachment_dir(snap_id: str) -> str:
    """Snapshot attachment directory (session file copies, mode B)."""
    return os.path.join(get_snapshot_dir(), "attachments", snap_id)


def load_manifest() -> Dict[str, Any]:
    """Read the manifest; returns an empty timeline when missing / corrupt (no exceptions — rescue scenarios must be robust)."""
    with _lock:
        try:
            with open(_manifest_path(), "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict) and isinstance(data.get("snapshots"), list):
                data.setdefault("version", MANIFEST_VERSION)
                data.setdefault("current", -1)
                data.setdefault("last_good", None)
                return data
        except (OSError, ValueError):
            pass
        return {"version": MANIFEST_VERSION, "current": -1,
                "last_good": None, "snapshots": []}


def _save_manifest(manifest: Dict[str, Any]) -> None:
    with _lock:
        root = get_snapshot_dir()
        os.makedirs(root, exist_ok=True)
        tmp = f"{_manifest_path()}.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(manifest, f, ensure_ascii=False, indent=2)
        os.replace(tmp, _manifest_path())


def _new_id() -> str:
    return time.strftime("%Y%m%dT%H%M%S") + "_" + os.urandom(3).hex()


def write_snapshot(
    data: Dict[str, Any],
    description: str = "",
    tag: str = "auto",
    source: str = "engine",
    sessions: bool = False,
) -> Dict[str, Any]:
    """Write a new snapshot and append it to the timeline tail (writing after undo truncates the redo branch).

    Returns the snapshot info entry from the manifest (including id / index).
    """
    with _lock:
        snap_id = _new_id()
        created_at = time.time()
        # attachments (session files) are written to disk first, then recorded in the snapshot data
        attachments: List[Dict[str, Any]] = []
        if sessions:
            for item in data.get("session_files") or []:
                src = item.get("path")
                if not src or not os.path.isfile(src):
                    continue
                dst_dir = attachment_dir(snap_id)
                os.makedirs(dst_dir, exist_ok=True)
                name = os.path.basename(src)
                dst = os.path.join(dst_dir, name)
                try:
                    shutil.copyfile(src, dst)
                except OSError:
                    continue
                attachments.append({
                    "name": name,
                    "path": src,
                    "size": os.path.getsize(dst),
                })
        data = dict(data)
        data["session_files"] = attachments

        manifest = load_manifest()
        items: List[Dict[str, Any]] = manifest["snapshots"]
        current = int(manifest.get("current", -1))
        # new branch after undo: truncate snapshots after current
        if 0 <= current < len(items) - 1:
            for stale in items[current + 1:]:
                _delete_snapshot_files(stale.get("id"))
                # a truncated entry invalidates last_good if it points at it
                if manifest.get("last_good") == stale.get("id"):
                    manifest["last_good"] = None
            items = items[:current + 1]

        snap_path = _snap_path(snap_id)
        os.makedirs(os.path.dirname(snap_path), exist_ok=True)
        payload = {
            "id": snap_id,
            "created_at": created_at,
            "description": description,
            "tag": tag,
            "source": source,
            "sessions": bool(sessions),
            "data": data,
        }
        with open(snap_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        info = {
            "id": snap_id,
            "created_at": created_at,
            "description": description,
            "tag": tag,
            "good": False,
            "source": source,
            "sessions": bool(sessions),
            "size": os.path.getsize(snap_path),
        }
        items.append(info)
        manifest["snapshots"] = items
        manifest["current"] = len(items) - 1
        _save_manifest(manifest)
        info["index"] = len(items) - 1
        return info


def read_snapshot(snap_id: str) -> Optional[Dict[str, Any]]:
    """Read a snapshot's full content (None when the id does not exist or the file is corrupt)."""
    with _lock:
        try:
            with open(_snap_path(snap_id), "r", encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError):
            return None


def list_snapshots() -> List[Dict[str, Any]]:
    """All timeline entries (including index)."""
    manifest = load_manifest()
    return [
        {**item, "index": i}
        for i, item in enumerate(manifest.get("snapshots") or [])
    ]


def _index_of(snap_id: str) -> int:
    for item in list_snapshots():
        if item.get("id") == snap_id:
            return int(item["index"])
    return -1


def current_index() -> int:
    return int(load_manifest().get("current", -1))


def current_id() -> Optional[str]:
    items = list_snapshots()
    idx = current_index()
    if 0 <= idx < len(items):
        return items[idx].get("id")
    return None


def set_current(snap_id: str) -> bool:
    """Move the current pointer (call after successfully applying Undo / Redo / Rollback)."""
    idx = _index_of(snap_id)
    if idx < 0:
        return False
    manifest = load_manifest()
    manifest["current"] = idx
    _save_manifest(manifest)
    return True


def undo_target() -> Optional[Tuple[Dict[str, Any], Dict[str, Any]]]:
    """Undo target: the current-1 position (with full data). None when absent."""
    items = list_snapshots()
    idx = current_index()
    if idx < 1:
        return None
    target = items[idx - 1]
    data = read_snapshot(target["id"])
    if data is None:
        return None
    return target, data


def redo_target() -> Optional[Tuple[Dict[str, Any], Dict[str, Any]]]:
    """Redo target: the current+1 position (with full data). None when absent."""
    items = list_snapshots()
    idx = current_index()
    if idx < 0 or idx >= len(items) - 1:
        return None
    target = items[idx + 1]
    data = read_snapshot(target["id"])
    if data is None:
        return None
    return target, data


def mark_good(snap_id: str) -> Optional[Dict[str, Any]]:
    """Mark a snapshot as "known good"; it also becomes last_good."""
    manifest = load_manifest()
    items = manifest.get("snapshots") or []
    hit = None
    for item in items:
        if item.get("id") == snap_id:
            item["good"] = True
            hit = item
    if hit is None:
        return None
    manifest["last_good"] = snap_id
    _save_manifest(manifest)
    return {**hit, "index": _index_of(snap_id)}


def last_good_id() -> Optional[str]:
    return load_manifest().get("last_good")


def delete_snapshot(snap_id: str) -> bool:
    """Delete one snapshot (files + timeline entry); keeps the current pointer consistent.

    - deleting the current snapshot moves the pointer to the previous entry
      (or -1 when the timeline becomes empty);
    - deleting an entry before the pointer shifts the pointer left by one;
    - deleting the last-good snapshot clears ``last_good``.
    """
    if not snap_id:
        return False
    with _lock:
        manifest = load_manifest()
        items = manifest.get("snapshots") or []
        idx = _index_of(snap_id)
        if idx < 0:
            return False
        _delete_snapshot_files(snap_id)
        items.pop(idx)
        manifest["snapshots"] = items
        current = int(manifest.get("current", -1))
        if current == idx:
            manifest["current"] = len(items) - 1 if items else -1
        elif current > idx:
            manifest["current"] = current - 1
        if manifest.get("last_good") == snap_id:
            manifest["last_good"] = None
        _save_manifest(manifest)
        return True


def rename_snapshot(snap_id: str, description: str) -> Optional[Dict[str, Any]]:
    """Rename a snapshot's description (display text). Returns the updated entry or None."""
    if not snap_id:
        return None
    with _lock:
        manifest = load_manifest()
        hit = None
        for item in manifest.get("snapshots") or []:
            if item.get("id") == snap_id:
                item["description"] = str(description or "").strip() or item.get("description") or ""
                hit = item
                break
        if hit is None:
            return None
        _save_manifest(manifest)
        return {**hit, "index": _index_of(snap_id)}


def prune(keep: int = 50) -> int:
    """Keep only the most recent ``keep`` snapshots (old ones are deleted from disk and the timeline)."""
    if keep < 1:
        return 0
    manifest = load_manifest()
    items = manifest.get("snapshots") or []
    if len(items) <= keep:
        return 0
    removed = 0
    stale = items[: len(items) - keep]
    keep_items = items[len(items) - keep:]
    for item in stale:
        _delete_snapshot_files(item.get("id"))
        if manifest.get("last_good") == item.get("id"):
            manifest["last_good"] = None
        removed += 1
    manifest["snapshots"] = keep_items
    # shift the pointer back by the number removed
    manifest["current"] = max(-1, int(manifest.get("current", -1)) - removed)
    _save_manifest(manifest)
    return removed


def _delete_snapshot_files(snap_id: Optional[str]) -> None:
    if not snap_id:
        return
    try:
        os.remove(_snap_path(snap_id))
    except OSError:
        pass
    try:
        shutil.rmtree(attachment_dir(snap_id), ignore_errors=True)
    except OSError:
        pass


# ── crash-rescue rollback target ────────────────────────

def rollback_target_path() -> str:
    return os.path.join(get_snapshot_dir(), "rollback_target.json")


def write_rollback_target(snapshot: Dict[str, Any]) -> str:
    """Persist a snapshot as the "next-startup rollback target" (used by the rescue CLI).

    Returns the target file path. Content includes: snapshot id / time / layer / cli /
    webui_config / session_files / providers. It is consumed and deleted at the next
    np() / norpagent startup.
    """
    data = snapshot.get("data", snapshot)
    payload = {
        "format": 1,
        "snapshot_id": snapshot.get("id") or data.get("id"),
        "created_at": snapshot.get("created_at") or time.time(),
        "description": snapshot.get("description") or data.get("description", ""),
        "data": data,
    }
    path = rollback_target_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)
    return path


def consume_rollback_target() -> Optional[Dict[str, Any]]:
    """Read and delete the rollback target file (called at startup; idempotent).

    Returns the payload dict (including data); None when no target file exists. A
    corrupt file is deleted and None returned (startup is never blocked).
    """
    path = rollback_target_path()
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            payload = json.load(f)
    except (OSError, ValueError):
        payload = None
    try:
        os.remove(path)
    except OSError:
        pass
    if not isinstance(payload, dict) or not isinstance(payload.get("data"), dict):
        return None
    return payload


__all__ = [
    "get_snapshot_dir", "set_snapshot_dir",
    "load_manifest", "write_snapshot", "read_snapshot", "list_snapshots",
    "current_index", "current_id", "set_current",
    "undo_target", "redo_target", "mark_good", "last_good_id", "prune",
    "delete_snapshot", "rename_snapshot",
    "attachment_dir", "write_rollback_target", "consume_rollback_target",
    "rollback_target_path",
]
