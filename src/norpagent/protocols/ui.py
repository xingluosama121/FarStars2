# Copyright (c) 2026 xingluosama121, MIT Licensed
"""UI protocol: the "interface" abstraction of an Agent.

The interface is fully decoupled from the agent loop: the runtime only broadcasts
events through the event bus, and UI adapters subscribe to events and render
themselves (console / web / desktop / tray).

P1 provides the console adapter; P3 will migrate the existing FastAPI backend and
desktop frontend as Web UI adapter plugins.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class UIAdapter(Protocol):
    """User interface adapter interface."""

    ui_id: str

    def on_event(self, event: Any) -> None:
        """Receive and render an AgentEvent."""
        ...

    def ask_user(self, question: str, kind: str = "") -> "str | None":
        """Ask the user a question and return their answer.

        Returns ``None`` when no answer was actually obtained — no interactive UI is
        attached, the user did not reply before the timeout, or input was EOF. There
        is deliberately no "default answer" parameter: silently substituting one
        would put words in the user's mouth, and the caller would then act on a
        decision nobody ever made. A ``None`` return must propagate so the caller
        can fail, re-ask, or explicitly label its own fallback as its own.

        ``kind`` lets the adapter choose the right control instead of guessing from
        the text: ``"approval"`` is a binary approve/reject decision (no free-text
        box), ``"clarify"`` (or empty) is an open question that needs typed input.
        """
        ...

    def notify(self, message: str, level: str = "info") -> None:
        """Non-blocking notification (hints, warnings, etc.)."""
        ...
