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

    def ask_user(self, question: str, default: str = "") -> str:
        """Ask the user a question and return the answer (used for human approval, clarification, etc.)."""
        ...

    def notify(self, message: str, level: str = "info") -> None:
        """Non-blocking notification (hints, warnings, etc.)."""
        ...
