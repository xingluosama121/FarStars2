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
    """A session. ``messages`` is the full history (including tool messages)."""

    id: str
    title: str = ""
    created_at: float = 0.0
    messages: List[ChatMessage] = field(default_factory=list)


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
