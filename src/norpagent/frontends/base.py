# Copyright (c) 2026 xingluosama121, MIT Licensed
"""Frontend protocol: the user-facing input/output shell.

Frontend and renderer are two layers:

- **frontend (this protocol)**: the user interaction shell — where input is read,
  when to start / stop, how input is handed to the engine;
- **ui (UIAdapter, norpagent.protocols.ui)**: the event rendering layer —
  subscribes to the event bus and renders agent events as text / interface elements.

A frontend usually carries (or references) a ui renderer.
Frontends must be highly swappable: console / headless / web / any custom frontend
all satisfy the same protocol; replace the whole frontend by filling in an address.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class Frontend(Protocol):
    """Frontend shell interface."""

    frontend_id: str

    def attach(self, engine: Any) -> None:
        """Bind the engine (NorpEngine).

        The frontend submits user input via engine.submit(text);
        requests stopping the whole application via engine.request_stop();
        usually also subscribes to the engine's event bus to render output.
        """
        ...

    def start(self) -> None:
        """Start the frontend (usually spawns its own background thread without blocking the caller).

        Exception: the console frontend automatically switches to synchronous mode
        inside the Python interactive interpreter (REPL) — the input loop runs in
        the calling thread and blocks until the user exits (so the background thread
        does not compete with the REPL for stdin and Ctrl+C can be delivered).
        """
        ...

    def stop(self) -> None:
        """Stop the frontend (thread-safe; callable from any thread)."""
        ...

    def is_alive(self) -> bool:
        """Whether the frontend is still running."""
        ...


__all__ = ["Frontend"]
