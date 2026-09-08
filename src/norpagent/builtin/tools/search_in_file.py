# Copyright (c) 2026 xingluosama121, MIT Licensed
"""In-file search tool: search_in_file — fast keyword location inside one file.

Streams the file line by line (constant memory, works on files of any size) and
returns every matching line with its exact line number and surrounding context
lines. Supports literal keyword matching (default) and regular expressions
(use_regex), optional case-insensitive matching and line-range limits. Pairs
naturally with file_surgeon: locate the line here, then edit it surgically. All
paths are confined to the workspace root (see pathsafe.py).
"""

from __future__ import annotations

import os
import re
from typing import Any, Dict, List, Optional, Set, Tuple

from norpagent.builtin.tools.pathsafe import PathSafetyError, resolve_safe_path
from norpagent.protocols.tool import Tool, ToolResult

_MAX_MATCHES_HARD = 100
_MAX_CONTEXT = 10


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


def _scan(
    path: str,
    encoding: str,
    query: str,
    regex: Optional[re.Pattern],
    case_sensitive: bool,
    line_start: Optional[int],
    line_end: Optional[int],
    context_lines: int,
    max_matches: int,
) -> Tuple[List[Tuple[int, str]], int, Dict[int, str]]:
    """Two streaming passes: locate matches, then gather their context windows."""
    matched: List[Tuple[int, str]] = []
    total_lines = 0
    with open(path, "r", encoding=encoding, errors="replace") as fh:
        for i, line in enumerate(fh, 1):
            total_lines = i
            if line_start is not None and i < line_start:
                continue
            if line_end is not None and i > line_end:
                break
            text = line.rstrip("\n\r")
            if regex is not None:
                hit = regex.search(text) is not None
            elif case_sensitive:
                hit = query in text
            else:
                hit = query.lower() in text.lower()
            if hit:
                matched.append((i, text))
                if len(matched) >= max_matches:
                    break
        # keep counting when the scan stopped early, so the header reports the
        # file's real line count without loading it into memory
        total_lines += sum(1 for _ in fh)

    need: Set[int] = set()
    for ln, _ in matched:
        need.update(range(max(1, ln - context_lines), ln + context_lines + 1))
    context: Dict[int, str] = {}
    with open(path, "r", encoding=encoding, errors="replace") as fh:
        for i, line in enumerate(fh, 1):
            if i in need:
                context[i] = line.rstrip("\n\r")
    return matched, total_lines, context


class SearchInFileTool:
    name = "search_in_file"

    def schema(self) -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": (
                    "Searches one file inside the workspace for a keyword or regex and returns every match "
                    "with its exact line number and surrounding context lines (streaming; works on files of "
                    "any size). Use it to quickly locate the line to edit before calling file_surgeon."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "File path relative to the workspace root"},
                        "query": {"type": "string", "description": "Keyword to match (or a regular expression when use_regex=true)"},
                        "use_regex": {"type": "boolean", "description": "Treat query as a regular expression (default false)"},
                        "case_sensitive": {"type": "boolean", "description": "Case-sensitive matching (default true)"},
                        "line_start": {"type": "integer", "description": "Only scan from this line (1-based), optional"},
                        "line_end": {"type": "integer", "description": "Only scan up to this line (inclusive), optional"},
                        "context_lines": {"type": "integer", "description": "Context lines shown around each match (default 2, max 10)"},
                        "max_matches": {"type": "integer", "description": "Max matches returned (default 30, max 100)"},
                        "encoding": {"type": "string", "description": "File encoding, e.g. utf-8 or gbk (auto-detected when omitted)"},
                    },
                    "required": ["path", "query"],
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
        path = str(target)

        query = str(args.get("query") or "")
        if not query:
            return ToolResult(output="query parameter is empty", success=False, error="empty_query")

        use_regex = bool(args.get("use_regex"))
        regex = None
        if use_regex:
            try:
                regex = re.compile(query)
            except re.error as exc:
                return ToolResult(output=f"invalid regular expression '{query[:80]}': {exc}", success=False, error="bad_pattern")

        case_sensitive = bool(args.get("case_sensitive", True))

        line_start = args.get("line_start")
        if line_start is not None:
            try:
                line_start = int(line_start)
            except (TypeError, ValueError):
                return ToolResult(output="line_start must be an integer >= 1", success=False, error="bad_range")
            if line_start < 1:
                return ToolResult(output="line_start must be an integer >= 1", success=False, error="bad_range")
        line_end = args.get("line_end")
        if line_end is not None:
            try:
                line_end = int(line_end)
            except (TypeError, ValueError):
                return ToolResult(output="line_end must be an integer >= 1", success=False, error="bad_range")
            if line_end < 1:
                return ToolResult(output="line_end must be an integer >= 1", success=False, error="bad_range")
        if line_start is not None and line_end is not None and line_start > line_end:
            return ToolResult(
                output=f"invalid line range: line_start={line_start} > line_end={line_end}",
                success=False,
                error="bad_range",
            )

        try:
            context_lines = int(args.get("context_lines") or 2)
        except (TypeError, ValueError):
            context_lines = 2
        context_lines = max(0, min(context_lines, _MAX_CONTEXT))
        try:
            max_matches = int(args.get("max_matches") or 30)
        except (TypeError, ValueError):
            max_matches = 30
        max_matches = max(1, min(max_matches, _MAX_MATCHES_HARD))

        encoding = str(args.get("encoding") or "") or _probe_encoding(path)
        try:
            "".encode(encoding)
        except LookupError:
            return ToolResult(output=f"unknown encoding: {encoding}", success=False, error="bad_encoding")

        try:
            size = target.stat().st_size
        except OSError as exc:
            return ToolResult(output=f"stat failed: {exc}", success=False, error=str(exc))

        try:
            matched, total_lines, context = _scan(
                path, encoding, query, regex, case_sensitive,
                line_start, line_end, context_lines, max_matches,
            )
        except OSError as exc:
            return ToolResult(output=f"scan failed: {exc}", success=False, error=str(exc))

        desc = f"query: '{query}'"
        if use_regex:
            desc += " (regex)"
        if not case_sensitive:
            desc += " (case-insensitive)"

        header = [
            f"[search_in_file] {os.path.basename(path)}",
            f"  {desc}",
            f"  file: {_format_size(size)}, {total_lines} lines",
            f"  matches: {len(matched)}"
            + (" (reached the max_matches limit)" if len(matched) >= max_matches else ""),
            "",
        ]
        if not matched:
            header.append("no matches found.")
            header.append("hint: check the keyword spelling, or widen the line range with line_start / line_end.")
            return ToolResult(output="\n".join(header).rstrip())

        width = max(len(str(total_lines)), 1)
        marked = {ln for ln, _ in matched}
        for idx, (ln, _text) in enumerate(matched, 1):
            header.append(f"--- match {idx} at line {ln} ---")
            for cl in range(max(1, ln - context_lines), ln + context_lines + 1):
                if cl in context:
                    marker = ">>>" if cl == ln else "   "
                    header.append(f"{marker} L{cl:>{width}}: {context[cl][:300]}")
            header.append("")
        return ToolResult(output="\n".join(header).rstrip())
