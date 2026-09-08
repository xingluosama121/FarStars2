# Copyright (c) 2026 xingluosama121, MIT Licensed
"""Headless frontend: no input reading, program-API driven, but output must be visible.

Used for library embedding, benchmarks and single tasks (prompt mode):
the Agent executes when the engine submit() is called programmatically; this
frontend mounts a lightweight stdout renderer to guarantee "input visible and
output visible" —

- when the preset ui=console already provides a visible renderer, reuse it and
  avoid duplicate output;
- when the preset ui=web or another silent renderer is used, replace it with this
  frontend's visible renderer;
- when a single task (prompt mode) finishes, the engine additionally prints the
  final result.
"""

from __future__ import annotations

import sys
from typing import Any, Optional

from norpagent.frontends.base import Frontend


class _HeadlessRenderer:
    """Visible renderer for headless mode: prints key events to stdout."""

    ui_id = "headless"

    def __init__(self, stream: Any = None) -> None:
        self._stream = stream or sys.stdout
        self._inline = False
        self._streamed = ""  # body accumulated from streaming in this task (dedup)

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
            self._write(f"[headless] task start [{p.get('preset')}] {p.get('task_id')}")
            if p.get("user_input"):
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
        elif etype == "before_tool_call":
            self._write(f"\n[tool] {p.get('tool_name')} {p.get('args')}")
        elif etype == "after_tool_call":
            result = str(p.get("result"))[:200]
            ok = p.get("success", True)
            mark = "OK" if ok else "FAIL"
            self._write(f"[tool:{mark}] {p.get('tool_name')} -> {result}")
        elif etype == "on_tool_error":
            self._write(f"\n[tool:FAIL] {p.get('tool_name')} -> {p.get('error')}")
        elif etype == "on_usage_update":
            self._write(
                f"\n[usage] in={p.get('input')} out={p.get('output')}"
                f" total={p.get('total')}"
            )
        elif etype == "on_task_done":
            self._write(f"\n[headless] task done [{p.get('task_id')}] steps={p.get('steps')}")
        elif etype == "on_task_error":
            self._write(f"\n[headless] task error: {p.get('error')}")
        elif etype == "on_task_stopped":
            self._write(f"\n[headless] task stopped: {p.get('reason', '')}")
        elif etype == "on_task_timeout":
            self._write(f"\n[headless] task timeout: {p.get('timeout')}s")


class HeadlessFrontend:
    """Silent input, visible output: all input is driven by the program API; events render to stdout."""

    frontend_id = "headless"

    def __init__(self, renderer: Any = None, stream: Any = None, **kwargs: Any) -> None:
        self.renderer = renderer
        self._stream = stream
        self._engine: Any = None
        self._started = False

    def attach(self, engine: Any) -> None:
        self._engine = engine
        # existing visible renderer (preset ui=console) → reuse, no duplicate output
        agent = getattr(engine, "agent", None)
        existing = getattr(agent, "ui", None)
        if existing is not None and hasattr(existing, "on_event"):
            if getattr(existing, "ui_id", "") == "console":
                self._started = True
                return
            # silent renderer (e.g. a registered singleton WebUI): unsubscribe, swap in a visible renderer
            listener = getattr(agent, "_ui_listener", None)
            if listener is not None:
                try:
                    engine._bus.unsubscribe(listener)
                except Exception:  # noqa: BLE001
                    pass
                agent._ui_listener = None
            agent.ui = None
        # mount the visible renderer
        if self.renderer is None:
            self.renderer = _HeadlessRenderer(stream=self._stream)
        engine.subscribe_ui(self.renderer)
        self._started = True

    def start(self) -> None:
        self._started = True

    def stop(self) -> None:
        self._started = False

    def is_alive(self) -> bool:
        return self._started


__all__ = ["HeadlessFrontend"]
