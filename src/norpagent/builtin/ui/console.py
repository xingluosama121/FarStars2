# Copyright (c) 2026 xingluosama121, MIT Licensed
"""Console UI adapter: the default interactive interface.

Subscribes to the event bus and renders by event type. P3 will migrate the
existing FastAPI backend + desktop frontend as a Web UI adapter (same event
protocol; switching UI only requires changing the preset's ui field).
"""

from __future__ import annotations

import sys
from typing import Any


class ConsoleUI:
    """Minimal console renderer: streams body text directly, prints tool-call summaries."""

    ui_id = "console"

    def __init__(self, stream: Any = None, verbose: bool = True) -> None:
        self._stream = stream or sys.stdout
        self.verbose = verbose
        self._inline = False  # last streamed body segment did not end with a newline
        self._streamed = ""   # body accumulated from streaming in this task (dedup)

    def _write(self, text: str, end: str = "\n") -> None:
        if end != "" and self._inline:
            self._stream.write("\n")
            self._inline = False
        self._stream.write(text + end)
        self._stream.flush()
        self._inline = end == ""

    def on_event(self, event: Any) -> None:
        etype = event.type
        p = event.payload
        if etype == "on_task_start":
            self._streamed = ""
            self._write(f"\n== task start [{p.get('preset')}] {p.get('task_id')} ==")
            if self.verbose and p.get("user_input"):
                self._write(f">> {p.get('user_input')}")
        elif etype == "on_content":
            content = p.get("content", "")
            if p.get("stream"):
                self._streamed += content
                self._write(content, end="")
            else:
                # skip if the full text was already streamed (avoid duplication)
                if content.strip() != self._streamed.strip():
                    self._write(content)
                self._streamed = ""
        elif etype == "before_tool_call" and self.verbose:
            self._write(f"\n[tool] {p.get('tool_name')} {p.get('args')}")
        elif etype == "after_tool_call" and self.verbose:
            result = p.get("result")
            ok = p.get("success", True)
            mark = "OK" if ok else "FAIL"
            out = str(result)[:200] + ("..." if len(str(result)) > 200 else "")
            self._write(f"[tool:{mark}] {p.get('tool_name')} -> {out}")
        elif etype == "on_task_done":
            if self.verbose:
                self._write(f"\n== task done [{p.get('task_id')}] steps={p.get('steps')} ==")
        elif etype == "on_task_error":
            self._write(f"\n== task error: {p.get('error')} ==")
        elif etype == "on_task_stopped":
            self._write(f"\n== task stopped: {p.get('reason', '')} ==")
        elif etype == "on_task_timeout":
            self._write(f"\n== task timeout: {p.get('timeout')}s ==")
        elif etype == "on_usage_update" and self.verbose:
            self._write(
                f"[usage] in={p.get('input')} out={p.get('output')} total={p.get('total')}"
            )

    def ask_user(self, question: str, default: str = "") -> str:
        suffix = f" [{default}]" if default else ""
        self._write(f"{question}{suffix}: ", end="")
        try:
            answer = input().strip()
        except EOFError:
            return default
        return answer or default

    def notify(self, message: str, level: str = "info") -> None:
        prefix = {"error": "[error]", "warn": "[warning]"}.get(level, "[info]")
        self._write(f"{prefix} {message}")
