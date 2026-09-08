# Copyright (c) 2026 xingluosama121, MIT Licensed
"""Workspace path safety: the common protection layer for file tools.

Rules (consistent with the framework security constraints):
- paths in tool arguments must be relative; absolute system paths are rejected;
- ``..`` path traversal is rejected (including traversal after symlink resolution);
- every operation is resolved and confined inside the workspace root.

Workspace root resolution order:
    ctx.params["workspace_root"] (preset or task-level parameter) > current process working directory.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any


class PathSafetyError(Exception):
    """Path out of bounds / illegal."""


def workspace_root(ctx: Any) -> Path:
    """Return the workspace root (absolute path)."""
    root = getattr(ctx, "params", None) or {}
    if isinstance(root, dict):
        root = root.get("workspace_root", "") or ""
    else:
        root = ""
    return Path(root).resolve() if root else Path(os.getcwd()).resolve()


def resolve_safe_path(ctx: Any, path: str, must_exist: bool = False) -> Path:
    """Resolve a user-provided relative path into an absolute path inside the workspace.

    ``path`` must be relative (POSIX / Windows separators both accepted);
    "." is allowed. Raises PathSafetyError on failure.
    """
    if path is None or not str(path).strip():
        raise PathSafetyError("path is empty")

    raw = str(path).strip()
    if raw.startswith("\\") or raw.startswith("/") or (
        len(raw) >= 2 and raw[1] == ":"
    ):
        raise PathSafetyError(f"absolute paths are forbidden: {path}")

    root = workspace_root(ctx)
    resolved = (root / raw).resolve()
    try:
        relative = resolved.relative_to(root)
    except ValueError:
        raise PathSafetyError(
            f"path out of bounds (no .. traversal or symlinks escaping the workspace allowed): {path}"
        )
    if relative == Path("..") or ".." in relative.parts:
        raise PathSafetyError(f"path out of bounds (no .. traversal allowed): {path}")
    if must_exist and not resolved.exists():
        raise PathSafetyError(f"path does not exist: {path}")
    return resolved


def format_path_error(exc: Exception) -> str:
    return f"{type(exc).__name__}: {exc}"
