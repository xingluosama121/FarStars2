# Copyright (c) 2026 xingluosama121, MIT Licensed
"""File read/write tools: file_read / file_write / file_list / file_delete.

All operations are subject to workspace path safety constraints (see pathsafe.py):
relative paths + no .. traversal + confined to the workspace root.

Encoding conventions: UTF-8 for writes; reads probe in the order utf-8 -> gbk ->
latin-1 to avoid mojibake from Windows Chinese code pages (consistent with the
existing application's robust_decode).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict

from norpagent.builtin.tools.pathsafe import (
    PathSafetyError,
    resolve_safe_path,
)
from norpagent.protocols.tool import Tool, ToolResult

# full-read cap: larger files must be read in ranges via start_line / end_line
_MAX_FULL_READ_BYTES = 100 * 1024


def _robust_read_text(data: bytes) -> str:
    if not data:
        return ""
    for enc in ("utf-8", "gbk", "cp936", "latin-1"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def _read_bytes(path: Path) -> bytes:
    with open(path, "rb") as fh:
        return fh.read()


class FileReadTool:
    name = "file_read"

    def schema(self) -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": (
                    "Reads the content of a text file inside the workspace. Files larger than 100KB "
                    "must be read in ranges with start_line / end_line (each returned line is numbered)."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "File path relative to the workspace root"},
                        "start_line": {"type": "integer", "description": "Start line number (1-based), optional"},
                        "end_line": {"type": "integer", "description": "End line number (inclusive), optional"},
                    },
                    "required": ["path"],
                    "additionalProperties": False,
                },
            },
        }

    def run(self, args: Dict[str, Any], ctx: Any) -> ToolResult:
        try:
            target = resolve_safe_path(ctx, args.get("path", ""), must_exist=True)
        except PathSafetyError as exc:
            return ToolResult(output=str(exc), success=False, error=str(exc))
        if target.is_dir():
            return ToolResult(
                output=f"target is a directory, not a file: {args.get('path')} (browse with file_list)",
                success=False,
                error="is_directory",
            )
        try:
            data = _read_bytes(target)
            start = args.get("start_line")
            end = args.get("end_line")
            if start is None and end is None:
                if len(data) > _MAX_FULL_READ_BYTES:
                    return ToolResult(
                        output=(
                            f"file too large ({len(data)} bytes); partial read only. "
                            f"Read in ranges with start_line / end_line. "
                            f"First {_MAX_FULL_READ_BYTES} bytes:\n"
                            f"{_format_numbered(_robust_read_text(data[:_MAX_FULL_READ_BYTES]))}"
                        ),
                        success=False,
                        error="file_too_large",
                    )
                return ToolResult(output=_format_numbered(_robust_read_text(data)))
            # line-number range read
            text = _robust_read_text(data)
            lines = text.splitlines()
            start = max(1, int(start or 1))
            end = min(len(lines), int(end or len(lines)))
            if start > len(lines):
                return ToolResult(output=f"start line {start} exceeds total lines {len(lines)}", success=False, error="bad_range")
            if end < start:
                return ToolResult(output=f"invalid line range: start={start} > end={end}", success=False, error="bad_range")
            return ToolResult(output=_format_numbered("\n".join(lines[start - 1 : end]), start))
        except OSError as exc:
            return ToolResult(output=f"read failed: {exc}", success=False, error=str(exc))


class FileWriteTool:
    name = "file_write"

    def schema(self) -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": (
                    "Writes (creates or overwrites) a UTF-8 text file inside the workspace. "
                    "Missing parent directories are created automatically. Before overwriting an "
                    "existing file, confirm its content with file_read first."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "File path relative to the workspace root"},
                        "content": {"type": "string", "description": "The complete text content to write"},
                    },
                    "required": ["path", "content"],
                    "additionalProperties": False,
                },
            },
        }

    def run(self, args: Dict[str, Any], ctx: Any) -> ToolResult:
        try:
            target = resolve_safe_path(ctx, args.get("path", ""))
        except PathSafetyError as exc:
            return ToolResult(output=str(exc), success=False, error=str(exc))
        content = args.get("content", "")
        if not isinstance(content, str):
            content = str(content)
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
            size = len(content.encode("utf-8"))
            return ToolResult(output=f"written {target} ({size} bytes)")
        except OSError as exc:
            return ToolResult(output=f"write failed: {exc}", success=False, error=str(exc))


class FileListTool:
    name = "file_list"

    def schema(self) -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": (
                    "Lists the contents of a directory in the workspace (default: workspace root), "
                    "returning relative paths, types (dir/file) and file sizes."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "Directory path relative to the workspace root; default '.'"},
                        "depth": {"type": "integer", "description": "Recursion depth (default 2, max 6)"},
                    },
                    "additionalProperties": False,
                },
            },
        }

    def run(self, args: Dict[str, Any], ctx: Any) -> ToolResult:
        try:
            target = resolve_safe_path(
                ctx, args.get("path", "") or ".", must_exist=True
            )
        except PathSafetyError as exc:
            return ToolResult(output=str(exc), success=False, error=str(exc))
        if not target.is_dir():
            return ToolResult(
                output=f"path is not a directory: {args.get('path')}", success=False, error="not_a_dir"
            )
        depth = max(1, min(int(args.get("depth") or 2), 6))
        root = workspace_root_for(ctx)
        lines: list[str] = []
        try:
            _walk(target, root, depth, 1, lines)
        except OSError as exc:
            return ToolResult(output=f"walk failed: {exc}", success=False, error=str(exc))
        if not lines:
            return ToolResult(output="(empty directory)")
        return ToolResult(output="\n".join(lines[:2000]) + ("\n...(over 2000 entries, truncated)" if len(lines) > 2000 else ""))


class FileDeleteTool:
    name = "file_delete"

    def schema(self) -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": (
                    "Deletes a file or directory inside the workspace (directories are removed recursively). "
                    "This operation is irreversible; confirm the target before executing."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "File or directory path relative to the workspace root"},
                    },
                    "required": ["path"],
                    "additionalProperties": False,
                },
            },
        }

    def run(self, args: Dict[str, Any], ctx: Any) -> ToolResult:
        try:
            target = resolve_safe_path(ctx, args.get("path", ""), must_exist=True)
        except PathSafetyError as exc:
            return ToolResult(output=str(exc), success=False, error=str(exc))
        # refuse to delete the workspace root itself
        try:
            root = workspace_root_for(ctx)
        except Exception:
            root = None
        if root is not None and target == root:
            return ToolResult(output="deleting the workspace root is forbidden", success=False, error="forbidden")
        try:
            if target.is_dir():
                import shutil

                shutil.rmtree(target)
                return ToolResult(output=f"deleted directory {target}")
            target.unlink()
            return ToolResult(output=f"deleted file {target}")
        except OSError as exc:
            return ToolResult(output=f"delete failed: {exc}", success=False, error=str(exc))


def workspace_root_for(ctx: Any) -> Path:
    from norpagent.builtin.tools.pathsafe import workspace_root

    return workspace_root(ctx)


def _format_numbered(text: str, start_line: int = 1) -> str:
    """Number each line of the text (file_read output format)."""
    if not text:
        return "(empty file)"
    lines = text.splitlines()
    width = len(str(start_line + len(lines)))
    return "\n".join(f"{i + start_line:>{width}}| {ln}" for i, ln in enumerate(lines))


def _walk(dir_path: Path, root: Path, depth: int, level: int, out: list[str]) -> None:
    if level > depth:
        return
    entries = sorted(dir_path.iterdir(), key=lambda p: (p.is_file(), p.name.lower()))
    for entry in entries:
        rel = entry.relative_to(root)
        if entry.is_dir():
            out.append(f"[dir] {rel}/")
            _walk(entry, root, depth, level + 1, out)
        elif entry.is_file():
            size = entry.stat().st_size
            out.append(f"[file] {rel}  ({size} bytes)")
        else:
            out.append(f"[other] {rel}")
