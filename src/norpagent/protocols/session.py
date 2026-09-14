# Copyright (c) 2026 xingluosama121, MIT Licensed
"""Session management protocol: the "memory" abstraction of an Agent.

The session manager persists and retrieves conversation history. The built-in
implementation is in-memory storage; a SQLite implementation will be provided in
P2. Developers may implement any backend: files, databases, cloud sync, etc.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Protocol, runtime_checkable

from norpagent.protocols.model import ChatMessage


@dataclass
class Session:
    """A session. ``messages`` is the full history (including tool messages).

    ``updated_at``: last activity time (message appended / renamed); the front
    session list sorts by this field (newest first) and buckets by date
    ("today / 3 days / 7 days / 30 days / earlier") — 2026-09-12 round 9.
    ``pinned``: user pinned the session to the top of the list.
    """

    id: str
    title: str = ""
    created_at: float = 0.0
    messages: List[ChatMessage] = field(default_factory=list)
    updated_at: float = 0.0
    pinned: bool = False
    # per-session system prompt (2026-09-13): combined with the global system
    # prompt at task time. ``append`` joins it after the global base;
    # ``replace`` uses only this session's prompt. Empty = behave as before.
    system_prompt: str = ""
    system_prompt_mode: str = "append"


@runtime_checkable
class SessionManager(Protocol):
    """Session manager interface. All methods must be thread-safe."""

    def create_session(self, title: str = "") -> Session:
        """Create a new session and return it."""
        ...

    def get_session(self, session_id: str) -> Optional[Session]:
        """Get a session by id; return None if it does not exist."""
        ...

    def append_message(self, session_id: str, message: ChatMessage) -> bool:
        """Append a message to the session; return whether it succeeded."""
        ...

    def history(self, session_id: str) -> List[ChatMessage]:
        """Return the full history of a session (a copy); empty list if the session does not exist."""
        ...

    def list_sessions(self) -> List[Session]:
        """List all sessions (may be sorted by creation time descending)."""
        ...

    def delete_session(self, session_id: str) -> bool:
        """Delete a session; return whether it succeeded."""
        ...

    def set_title(self, session_id: str, title: str) -> bool:
        """Rename a session (persisted); return whether it succeeded.

        Optional capability (2026-09-12 round 9): callers guard with
        ``getattr(sm, "set_title", None)`` so custom managers keep working.
        """
        ...

    def set_pinned(self, session_id: str, pinned: bool) -> bool:
        """Pin / unpin a session (persisted); return whether it succeeded.

        Optional capability (2026-09-12 round 9); same guard rule as ``set_title``.
        """
        ...

    def set_system_prompt(self, session_id: str, prompt: str,
                          mode: str = "append") -> bool:
        """Store the per-session system prompt (persisted); return whether it succeeded.

        ``mode`` is ``append`` (join after the global system prompt) or
        ``replace`` (use only this session's prompt). Optional capability
        (2026-09-13); same guard rule as ``set_title``.
        """
        ...
