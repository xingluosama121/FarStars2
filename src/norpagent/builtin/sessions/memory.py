# Copyright (c) 2026 xingluosama121, MIT Licensed
"""In-memory session manager: default session storage (in-process, thread-safe).

Suitable for demos and benchmarks. For production, replace with a persistent
implementation (P2 provides the SQLite version), e.g.:
``registry.register_session("memory", MySessionManager)`` — presets need no changes.
"""

from __future__ import annotations

import threading
import time
import uuid
from typing import Any, Dict, List, Optional

from norpagent.protocols.model import ChatMessage
from norpagent.protocols.session import Session


class MemorySessionManager:
    """In-process in-memory session storage."""

    def __init__(self) -> None:
        self._sessions: Dict[str, Session] = {}
        self._lock = threading.RLock()
        self._mono = 0.0  # monotonic activity clock (see _next_ts)

    def _next_ts(self) -> float:
        """Monotonic activity timestamp: two same-tick activities still order
        strictly (coarse OS clock granularity would otherwise tie them)."""
        now = time.time()
        if now <= self._mono:
            now = self._mono + 0.000001
        self._mono = now
        return now

    def create_session(self, title: str = "",
                       session_id: Optional[str] = None) -> Session:
        with self._lock:
            if session_id:
                existing = self._sessions.get(session_id)
                if existing is not None:
                    return existing
            now = self._next_ts()
            sess = Session(
                id=session_id or uuid.uuid4().hex[:16],
                title=title or f"session-{len(self._sessions) + 1}",
                created_at=now,
                updated_at=now,
                pinned=False,
            )
            self._sessions[sess.id] = sess
            return sess

    def get_session(self, session_id: str) -> Optional[Session]:
        with self._lock:
            return self._sessions.get(session_id)

    def append_message(self, session_id: str, message: ChatMessage) -> bool:
        with self._lock:
            sess = self._sessions.get(session_id)
            if sess is None:
                return False
            sess.messages.append(message)
            sess.updated_at = self._next_ts()
            return True

    def history(self, session_id: str) -> List[ChatMessage]:
        with self._lock:
            sess = self._sessions.get(session_id)
            return list(sess.messages) if sess else []

    def list_sessions(self) -> List[Session]:
        with self._lock:
            return sorted(
                self._sessions.values(),
                key=lambda s: (
                    0 if getattr(s, "pinned", False) else 1,
                    -(getattr(s, "updated_at", 0.0) or s.created_at or 0.0),
                    -(s.created_at or 0.0),
                ),
            )

    def set_title(self, session_id: str, title: str) -> bool:
        """Rename a session (persisted in memory; 2026-09-12 round 9)."""
        with self._lock:
            sess = self._sessions.get(session_id)
            if sess is None:
                return False
            sess.title = str(title or "")
            return True

    def set_pinned(self, session_id: str, pinned: bool) -> bool:
        """Pin / unpin a session (2026-09-12 round 9)."""
        with self._lock:
            sess = self._sessions.get(session_id)
            if sess is None:
                return False
            sess.pinned = bool(pinned)
            return True

    def set_system_prompt(self, session_id: str, prompt: str,
                          mode: str = "append") -> bool:
        """Store the per-session system prompt (2026-09-13)."""
        with self._lock:
            sess = self._sessions.get(session_id)
            if sess is None:
                return False
            sess.system_prompt = str(prompt or "")
            sess.system_prompt_mode = (
                "replace" if str(mode or "").strip().lower() == "replace"
                else "append"
            )
            return True

    def delete_session(self, session_id: str) -> bool:
        with self._lock:
            return self._sessions.pop(session_id, None) is not None

    def truncate(self, session_id: str, keep: int) -> int:
        """Keep the first ``keep`` messages and drop the rest (regenerate / edit a turn)."""
        keep = max(0, int(keep))
        with self._lock:
            sess = self._sessions.get(session_id)
            if sess is None:
                return 0
            dropped = len(sess.messages) - keep
            if dropped <= 0:
                return 0
            sess.messages = sess.messages[:keep]
            return dropped

    def replace_tail(self, session_id: str, keep: int,
                     messages: List[ChatMessage]) -> bool:
        """Keep the first ``keep`` messages, then append ``messages``.

        Used by branch / version restore: rewind to a turn start and re-apply a
        saved tail snapshot. 2026-09-13.
        """
        keep = max(0, int(keep))
        with self._lock:
            sess = self._sessions.get(session_id)
            if sess is None:
                return False
            sess.messages = list(sess.messages[:keep]) + list(messages or [])
            sess.updated_at = self._next_ts()
            return True

    def get_variants(self, session_id: str) -> Dict[str, Any]:
        """Persisted branch / version store of a session (JSON-serializable dict).

        Optional capability; callers guard with ``getattr(sm, "get_variants", None)``.
        2026-09-13.
        """
        with self._lock:
            sess = self._sessions.get(session_id)
            if sess is None:
                return {}
            return dict(getattr(sess, "variants", None) or {})

    def set_variants(self, session_id: str, data: Dict[str, Any]) -> bool:
        """Persist the branch / version store of a session. 2026-09-13."""
        with self._lock:
            sess = self._sessions.get(session_id)
            if sess is None:
                return False
            sess.variants = dict(data or {})
            return True
