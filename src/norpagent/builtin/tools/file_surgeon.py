# Copyright (c) 2026 xingluosama121, MIT Licensed
"""File surgery tool: file_surgeon — precise, surgical edits on specific lines.

Locates target lines by line number and/or content match (literal or regex via
use_regex), then applies one of five operations:

- replace       : replace the first ``count`` matched lines with new_content
- replace_all   : replace every matched line with new_content
- insert_before : insert new_content before each matched line
- insert_after  : insert new_content after each matched line
- delete        : remove each matched line

Streaming design: lines are streamed through a same-directory temp file with
large buffers and swapped back atomically via os.replace — the whole file never
lives in memory (files up to 1GB supported), and untouched lines are copied
byte-for-byte. ``dry_run`` previews the operation with context lines without
modifying the file; ``backup`` saves a .bak copy before editing. All paths are
confined to the workspace root (see pathsafe.py).
"""

from __future__ import annotations

import os
import re
import shutil
import tempfile
import time
from typing import Any, Dict, List, Optional, Set, Tuple

from norpagent.builtin.tools.pathsafe import PathSafetyError, resolve_safe_path
from norpagent.protocols.tool import Tool, ToolResult

_BUFFER_SIZE = 16 * 1024 * 1024       # 16MB streaming read/write buffers
_MAX_FILE_SIZE = 1024 * 1024 * 1024   # 1GB file size cap

_MODES = ("replace", "replace_all", "insert_before", "insert_after", "delete")
_MODES_WITH_CONTENT = ("replace", "replace_all", "insert_before", "insert_after")


def _probe_encoding(path: str) -> str:
    """Probe the text encoding from the file head (utf-8 -> gbk -> cp936 -> latin-1)."""
    with open(path, "rb") as fh:
        head = fh.read(64 * 1024)
    for enc in ("utf-8", "gbk", "cp936", "latin-1"):
        try:
            head.decode(enc)
            return enc
        except UnicodeDecodeError:
            continue
    return "utf-8"


def _format_size(size: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(size) < 1024.0:
            return f"{size:.1f} {unit}"
        size /= 1024.0
    return f"{size:.1f} PB"


def _compile_pattern(old_content: Optional[str], use_regex: bool):
    """Compile the locator pattern. Returns (pattern, error message).

    ``pattern`` is a compiled regex, the literal string, or None (no content
    locator — line_number alone).
    """
    if not old_content:
        return None, ""
    if not use_regex:
        return old_content, ""
    try:
        return re.compile(old_content), ""
    except re.error as exc:
        return None, f"invalid regular expression '{old_content[:80]}': {exc}"


def _locator_hit(pattern, text: str) -> bool:
    if pattern is None:
        return True
    if isinstance(pattern, re.Pattern):
        return pattern.search(text) is not None
    return pattern in text


def _target_hit(line_num: int, text: str, pattern, line_number: Optional[int]) -> bool:
    if line_number is not None and line_num != line_number:
        return False
    return _locator_hit(pattern, text)


def _write_new(fout, content: str, ending: str = "\n") -> None:
    """Write inserted/replacement content, reusing the matched line's own ending."""
    if not content:
        return
    fout.write(content)
    if ending and not content.endswith(("\n", "\r")):
        fout.write(ending)


def _preview(
    path: str,
    pattern,
    old_content: Optional[str],
    line_number: Optional[int],
    new_content: str,
    mode: str,
    count,
    context_lines: int,
    encoding: str,
    size: int,
) -> str:
    """Scan the file and render a dry-run preview of the pending operation."""
    matched: List[Tuple[int, str]] = []
    total_lines = 0
    with open(path, "r", encoding=encoding, errors="replace") as fh:
        for i, line in enumerate(fh, 1):
            total_lines = i
            text = line.rstrip("\n\r")
            if _target_hit(i, text, pattern, line_number):
                matched.append((i, text))
                if len(matched) >= count:
                    break
        # keep counting when the scan stopped early, so the header reports the
        # file's real line count without loading it into memory
        total_lines += sum(1 for _ in fh)

    locator = ""
    if line_number is not None:
        locator = f"line_number={line_number}"
        if old_content:
            locator += f" + pattern='{old_content[:80]}'"
    else:
        locator = f"pattern='{old_content[:80]}'"

    if not matched:
        return (
            f"[dry_run] file_surgeon - {os.path.basename(path)}\n"
            f"no matching lines found.\n"
            f"  file: {path} ({_format_size(size)}, {total_lines} lines)\n"
            f"  locator: {locator}\n"
            f"  hint: verify the line number / search text, or locate the line with search_in_file."
        )

    # one extra streaming pass to gather the context window of every match
    need: Set[int] = set()
    for ln, _ in matched:
        need.update(range(max(1, ln - context_lines), ln + context_lines + 1))
    context: Dict[int, str] = {}
    with open(path, "r", encoding=encoding, errors="replace") as fh:
        for i, line in enumerate(fh, 1):
            if i in need:
                context[i] = line.rstrip("\n\r")

    width = max(len(str(max(need))), len(str(total_lines)), 1)
    marked = {ln for ln, _ in matched}
    action = {
        "replace": f'replace with "{new_content[:200]}"',
        "replace_all": f'replace with "{new_content[:200]}"',
        "insert_before": f'insert "{new_content[:200]}" before the line',
        "insert_after": f'insert "{new_content[:200]}" after the line',
        "delete": "delete the line",
    }[mode]

    lines = [
        f"[dry_run] file_surgeon - {os.path.basename(path)}",
        f"  file: {path} ({_format_size(size)}, {total_lines} lines)",
        f"  mode: {mode} | matched: {len(matched)} | locator: {locator}",
        "",
    ]
    for ln, text in matched:
        lines.append(f"--- target line L{ln} ---")
        lines.append(f"  old:     {text[:200]}")
        lines.append(f"  action:  {action}")
        lines.append("  context:")
        for cl in range(max(1, ln - context_lines), ln + context_lines + 1):
            if cl in context:
                marker = ">>>" if cl == ln else "   "
                lines.append(f"{marker} L{cl:>{width}}: {context[cl][:300]}")
        lines.append("")
    lines.append("Tip: run again with dry_run=false to apply the change.")
    return "\n".join(lines)


def _execute(
    path: str,
    pattern,
    line_number: Optional[int],
    new_content: str,
    mode: str,
    count,
    backup: bool,
    encoding: str,
) -> Tuple[int, int, str, float]:
    """Apply the surgery. Returns (matched lines, total lines, backup path, elapsed seconds)."""
    start = time.time()
    backup_path = ""
    if backup:
        backup_path = path + ".bak"
        shutil.copy2(path, backup_path)

    fd, temp_path = tempfile.mkstemp(dir=os.path.dirname(path) or ".", prefix=".file_surgeon_")
    os.close(fd)
    try:
        matched = 0
        total_lines = 0
        with open(path, "r", encoding=encoding, errors="replace", newline="", buffering=_BUFFER_SIZE) as fin, \
                open(temp_path, "w", encoding=encoding, errors="replace", newline="", buffering=_BUFFER_SIZE) as fout:
            for i, line in enumerate(fin, 1):
                total_lines = i
                text = line.rstrip("\n\r")
                if matched >= count or not _target_hit(i, text, pattern, line_number):
                    fout.write(line)
                    continue
                matched += 1
                ending = line[len(text):]
                if mode == "delete":
                    continue
                if mode in ("replace", "replace_all"):
                    _write_new(fout, new_content, ending=ending)
                elif mode == "insert_before":
                    _write_new(fout, new_content, ending=ending)
                    fout.write(line)
                else:  # insert_after
                    fout.write(line)
                    _write_new(fout, new_content, ending=ending)
        os.replace(temp_path, path)
    except BaseException:
        try:
            os.unlink(temp_path)
        except OSError:
            pass
        raise
    return matched, total_lines, backup_path, time.time() - start


class FileSurgeonTool:
    name = "file_surgeon"

    def schema(self) -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": (
                    "Precisely edits specific lines of a file inside the workspace without rewriting the "
                    "whole file (streaming; files up to 1GB). Locate target lines by line_number and/or "
                    "old_content (literal, or regex with use_regex), then replace / replace_all / "
                    "insert_before / insert_after / delete. dry_run previews the change with context lines "
                    "before applying; backup saves a .bak copy before editing."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "File path relative to the workspace root"},
                        "mode": {
                            "type": "string",
                            "enum": list(_MODES),
                            "description": (
                                "Operation mode (default replace): replace = replace the first count matched "
                                "lines; replace_all = replace every matched line; insert_before / insert_after "
                                "= insert new_content around matched lines; delete = remove matched lines."
                            ),
                        },
                        "line_number": {"type": "integer", "description": "Target line number (1-based); optional, can be combined with old_content"},
                        "old_content": {"type": "string", "description": "Text matching the target line; treated as a regular expression when use_regex=true"},
                        "new_content": {"type": "string", "description": "Replacement text or text to insert (may contain \\n); not used by delete"},
                        "use_regex": {"type": "boolean", "description": "Treat old_content as a regular expression (default false)"},
                        "count": {"type": "integer", "description": "Max matched lines to edit for replace / insert / delete (default 1, -1 = all; ignored by replace_all)"},
                        "dry_run": {"type": "boolean", "description": "Preview the edit with context lines without modifying the file (default false)"},
                        "context_lines": {"type": "integer", "description": "Context lines shown around each match in the preview (default 2, max 10)"},
                        "backup": {"type": "boolean", "description": "Save a .bak copy of the original file before editing (default false)"},
                        "encoding": {"type": "string", "description": "File encoding, e.g. utf-8 or gbk (auto-detected when omitted)"},
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
                output=f"target is a directory, not a file: {args.get('path')}",
                success=False,
                error="is_directory",
            )
        path = str(target)

        mode = str(args.get("mode") or "replace")
        if mode not in _MODES:
            return ToolResult(
                output=f"invalid mode '{mode}'; expected one of {', '.join(_MODES)}",
                success=False,
                error="bad_mode",
            )

        line_number = args.get("line_number")
        if line_number is not None:
            try:
                line_number = int(line_number)
            except (TypeError, ValueError):
                return ToolResult(output="line_number must be an integer >= 1", success=False, error="bad_line_number")
            if line_number < 1:
                return ToolResult(output="line_number must be an integer >= 1", success=False, error="bad_line_number")

        old_content = args.get("old_content")
        if old_content is not None:
            old_content = str(old_content)
        if line_number is None and not old_content:
            return ToolResult(
                output="at least one of line_number / old_content is required to locate the target line",
                success=False,
                error="missing_locator",
            )

        new_content = str(args.get("new_content") or "")
        if mode in _MODES_WITH_CONTENT and not new_content:
            return ToolResult(output=f"mode '{mode}' requires new_content", success=False, error="missing_new_content")

        if mode == "replace_all":
            count = float("inf")
        else:
            raw_count = args.get("count")
            if raw_count is None:
                count = 1
            else:
                try:
                    count = int(raw_count)
                except (TypeError, ValueError):
                    return ToolResult(
                        output="count must be an integer >= 1 (or -1 for all matches)",
                        success=False,
                        error="bad_count",
                    )
                if count == -1:
                    count = float("inf")
                elif count < 1:
                    return ToolResult(
                        output="count must be an integer >= 1 (or -1 for all matches)",
                        success=False,
                        error="bad_count",
                    )

        use_regex = bool(args.get("use_regex"))
        pattern, err = _compile_pattern(old_content, use_regex)
        if err:
            return ToolResult(output=err, success=False, error="bad_pattern")

        try:
            size = target.stat().st_size
        except OSError as exc:
            return ToolResult(output=f"stat failed: {exc}", success=False, error=str(exc))
        if size > _MAX_FILE_SIZE:
            return ToolResult(
                output=f"file too large ({_format_size(size)}); file_surgeon supports up to {_format_size(_MAX_FILE_SIZE)}",
                success=False,
                error="file_too_large",
            )

        encoding = str(args.get("encoding") or "") or _probe_encoding(path)
        try:
            "".encode(encoding)
        except LookupError:
            return ToolResult(output=f"unknown encoding: {encoding}", success=False, error="bad_encoding")

        dry_run = bool(args.get("dry_run"))
        try:
            context_lines = int(args.get("context_lines") or 2)
        except (TypeError, ValueError):
            context_lines = 2
        context_lines = max(0, min(context_lines, 10))

        try:
            if dry_run:
                return ToolResult(output=_preview(
                    path, pattern, old_content, line_number, new_content,
                    mode, count, context_lines, encoding, size,
                ))
            matched, total_lines, backup_path, elapsed = _execute(
                path, pattern, line_number, new_content, mode, count,
                bool(args.get("backup")), encoding,
            )
        except OSError as exc:
            return ToolResult(output=f"operation failed: {exc}", success=False, error=str(exc))

        lines = [
            f"[file_surgeon] done - {os.path.basename(path)}",
            f"  mode: {mode}",
            f"  matched lines: {matched}",
            f"  total lines: {total_lines}",
            f"  file size: {_format_size(size)}",
            f"  elapsed: {elapsed:.2f} s",
        ]
        if backup_path:
            lines.append(f"  backup: {backup_path}")
        if matched == 0:
            lines.append("  note: no lines matched; the file was left unchanged.")
        return ToolResult(output="\n".join(lines))
