# Copyright (c) 2026 xingluosama121, MIT Licensed
"""SQLite session manager: persistent session storage (standard library sqlite3, zero third-party dependencies).

Implements the same SessionManager protocol as MemorySessionManager;
replacement works the same way:

    registry.register_session("memory", SQLiteSessionManager)

Default database file ``~/.norpagent/sessions.db``; the ``path`` parameter can
point elsewhere (pass a temp file in tests).

Thread safety: the sqlite3 connection is opened with check_same_thread=False,
all public methods are serialized by an RLock; every write commits immediately,
so data remains intact even after a process crash.
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
import uuid
from typing import Any, Dict, List, Optional

from norpagent.protocols.model import ChatMessage, ToolCallSpec
from norpagent.protocols.session import Session

_SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL DEFAULT '',
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL DEFAULT 0,
    pinned INTEGER NOT NULL DEFAULT 0,
    system_prompt TEXT NOT NULL DEFAULT '',
    system_prompt_mode TEXT NOT NULL DEFAULT 'append'
);
CREATE TABLE IF NOT EXISTS messages (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL DEFAULT '',
    tool_calls TEXT NOT NULL DEFAULT '',
    tool_call_id TEXT,
    name TEXT,
    reasoning TEXT NOT NULL DEFAULT '',
    has_reasoning INTEGER NOT NULL DEFAULT 0,
    attachments TEXT NOT NULL DEFAULT '',
    stats TEXT NOT NULL DEFAULT '',
    segments TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id, seq);
CREATE TABLE IF NOT EXISTS session_variants (
    session_id TEXT PRIMARY KEY,
    data TEXT NOT NULL DEFAULT ''
);
"""

# legacy database migration: early sessions tables lack updated_at / pinned
_SESSION_MIGRATIONS = (
    # 2026-09-12 round 9: last activity time (list sorting + date buckets)
    ("updated_at", "REAL NOT NULL DEFAULT 0"),
    # 2026-09-12 round 9: pinned to the top of the session list
    ("pinned", "INTEGER NOT NULL DEFAULT 0"),
    # 2026-09-13: per-session system prompt (append / replace the global base)
    ("system_prompt", "TEXT NOT NULL DEFAULT ''"),
    ("system_prompt_mode", "TEXT NOT NULL DEFAULT 'append'"),
)

# legacy database migration: early messages tables lack the reasoning / attachments columns
_MESSAGE_MIGRATIONS = (
    ("reasoning", "TEXT NOT NULL DEFAULT ''"),
    ("has_reasoning", "INTEGER NOT NULL DEFAULT 0"),
    ("attachments", "TEXT NOT NULL DEFAULT ''"),
    # 2026-09-12: per-message generation stats (token speed / total tokens / time)
    ("stats", "TEXT NOT NULL DEFAULT ''"),
    # 2026-09-12 round 9: ordered think/output/tool display segments (JSON list)
    ("segments", "TEXT NOT NULL DEFAULT ''"),
)


def _message_to_row(message: ChatMessage) -> tuple:
    tool_calls_json = ""
    if message.tool_calls:
        tool_calls_json = json.dumps(
            [
                {"id": tc.id, "name": tc.name, "arguments": tc.arguments}
                for tc in message.tool_calls
            ],
            ensure_ascii=False,
        )
    attachments_json = ""
    if message.attachments:
        try:
            attachments_json = json.dumps(message.attachments, ensure_ascii=False)
        except (TypeError, ValueError):
            attachments_json = ""
    stats_json = ""
    if message.stats:
        try:
            stats_json = json.dumps(message.stats, ensure_ascii=False)
        except (TypeError, ValueError):
            stats_json = ""
    segments_json = ""
    if message.segments:
        try:
            segments_json = json.dumps(message.segments, ensure_ascii=False)
        except (TypeError, ValueError):
            segments_json = ""
    return (
        message.role,
        message.content or "",
        tool_calls_json,
        message.tool_call_id,
        message.name,
        message.reasoning or "",
        1 if message.has_reasoning else 0,
        attachments_json,
        stats_json,
        segments_json,
    )


def _row_to_message(row: sqlite3.Row) -> ChatMessage:
    tool_calls: Optional[List[ToolCallSpec]] = None
    raw = row["tool_calls"] or ""
    if raw:
        try:
            tool_calls = [
                ToolCallSpec(
                    id=item.get("id", f"call_{i}"),
                    name=item.get("name", ""),
                    arguments=item.get("arguments") or {},
                )
                for i, item in enumerate(json.loads(raw))
            ]
        except (json.JSONDecodeError, TypeError):
            tool_calls = None
    attachments: Optional[List[dict]] = None
    raw_att = ""
    try:
        raw_att = row["attachments"] or ""
    except (IndexError, KeyError):
        raw_att = ""
    if raw_att:
        try:
            loaded = json.loads(raw_att)
            if isinstance(loaded, list):
                attachments = [x for x in loaded if isinstance(x, dict)]
        except (json.JSONDecodeError, TypeError):
            attachments = None
    stats: Optional[dict] = None
    raw_stats = ""
    try:
        raw_stats = row["stats"] or ""
    except (IndexError, KeyError):
        raw_stats = ""
    if raw_stats:
        try:
            loaded_stats = json.loads(raw_stats)
            if isinstance(loaded_stats, dict):
                stats = loaded_stats
        except (json.JSONDecodeError, TypeError):
            stats = None
    segments: Optional[List[dict]] = None
    raw_segments = ""
    try:
        raw_segments = row["segments"] or ""
    except (IndexError, KeyError):
        raw_segments = ""
    if raw_segments:
        try:
            loaded_segments = json.loads(raw_segments)
            if isinstance(loaded_segments, list):
                segments = [x for x in loaded_segments if isinstance(x, dict)]
        except (json.JSONDecodeError, TypeError):
            segments = None
    return ChatMessage(
        role=row["role"],
        content=row["content"] or "",
        tool_calls=tool_calls,
        tool_call_id=row["tool_call_id"],
        name=row["name"],
        reasoning=row["reasoning"] or "",
        has_reasoning=bool(row["has_reasoning"]),
        attachments=attachments,
        stats=stats,
        segments=segments,
    )


class SQLiteSessionManager:
    """SQLite persistent session storage."""

    def __init__(self, path: Optional[str] = None) -> None:
        self.path = path or os.path.join(
            os.path.expanduser("~"), ".norpagent", "sessions.db"
        )
        parent = os.path.dirname(os.path.abspath(self.path))
        os.makedirs(parent, exist_ok=True)
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        self._mono = 0.0  # monotonic activity clock (see _next_ts)
        with self._lock:
            self._conn.executescript(_SCHEMA)
            self._migrate()
            self._conn.commit()

    def _next_ts(self) -> float:
        """Monotonic activity timestamp: two same-tick activities still order
        strictly (coarse OS clock granularity would otherwise tie them)."""
        now = time.time()
        if now <= self._mono:
            now = self._mono + 0.000001
        self._mono = now
        return now

    def _migrate(self) -> None:
        """Legacy database migration: add missing columns to existing tables."""
        s_cols = {row[1] for row in self._conn.execute("PRAGMA table_info(sessions)")}
        added_session_col = False
        for column, decl in _SESSION_MIGRATIONS:
            if column not in s_cols:
                self._conn.execute(
                    f"ALTER TABLE sessions ADD COLUMN {column} {decl}"
                )
                added_session_col = True
        # backfill: legacy rows have no updated_at -> fall back to created_at so
        # list sorting / date buckets start from a sane value (2026-09-12 round 9)
        self._conn.execute(
            "UPDATE sessions SET updated_at = created_at"
            " WHERE updated_at IS NULL OR updated_at = 0"
        )
        if added_session_col:
            self._conn.commit()
        cols = {row[1] for row in self._conn.execute("PRAGMA table_info(messages)")}
        for column, decl in _MESSAGE_MIGRATIONS:
            if column not in cols:
                self._conn.execute(
                    f"ALTER TABLE messages ADD COLUMN {column} {decl}"
                )

    # ── SessionManager protocol ──────────────────────────

    def create_session(self, title: str = "",
                       session_id: Optional[str] = None) -> Session:
        if session_id:
            existing = self.get_session(session_id)
            if existing is not None:
                return existing
        now = self._next_ts()
        sess = Session(
            id=session_id or uuid.uuid4().hex[:16],
            title=title or f"session-{int(time.time())}",
            created_at=now,
            updated_at=now,
            pinned=False,
        )
        with self._lock:
            try:
                self._conn.execute(
                    "INSERT INTO sessions (id, title, created_at, updated_at, pinned)"
                    " VALUES (?, ?, ?, ?, ?)",
                    (sess.id, sess.title, sess.created_at, sess.updated_at,
                     1 if sess.pinned else 0),
                )
                self._conn.commit()
            except sqlite3.IntegrityError:
                # the same id was created concurrently: fall back to the existing session
                existing = self.get_session(sess.id)
                if existing is not None:
                    return existing
                raise
        return sess

    def get_session(self, session_id: str) -> Optional[Session]:
        with self._lock:
            row = self._conn.execute(
                "SELECT id, title, created_at, updated_at, pinned,"
                " system_prompt, system_prompt_mode FROM sessions"
                " WHERE id = ?",
                (session_id,),
            ).fetchone()
            if row is None:
                return None
            messages = self._load_messages(session_id)
        return Session(
            id=row["id"], title=row["title"], created_at=row["created_at"],
            messages=messages,
            updated_at=(row["updated_at"] or row["created_at"]),
            pinned=bool(row["pinned"]),
            system_prompt=row["system_prompt"] or "",
            system_prompt_mode=(row["system_prompt_mode"] or "append"),
        )

    def append_message(self, session_id: str, message: ChatMessage) -> bool:
        with self._lock:
            exists = self._conn.execute(
                "SELECT 1 FROM sessions WHERE id = ?", (session_id,)
            ).fetchone()
            if exists is None:
                return False
            self._conn.execute(
                "INSERT INTO messages (session_id, role, content, tool_calls,"
                " tool_call_id, name, reasoning, has_reasoning, attachments,"
                " stats, segments)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (session_id, *_message_to_row(message)),
            )
            # last-activity timestamp drives the list sorting / date buckets
            # (monotonic bump: same-tick messages still move the session up)
            self._conn.execute(
                "UPDATE sessions SET updated_at = ? WHERE id = ?",
                (self._next_ts(), session_id),
            )
            self._conn.commit()
            return True

    def history(self, session_id: str) -> List[ChatMessage]:
        with self._lock:
            return self._load_messages(session_id)

    def list_sessions(self) -> List[Session]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT id, title, created_at, updated_at, pinned FROM sessions"
                " ORDER BY pinned DESC, updated_at DESC, created_at DESC"
            ).fetchall()
        return [
            Session(
                id=r["id"], title=r["title"], created_at=r["created_at"],
                updated_at=(r["updated_at"] or r["created_at"]),
                pinned=bool(r["pinned"]),
            )
            for r in rows
        ]

    def set_title(self, session_id: str, title: str) -> bool:
        """Rename a session (persisted; 2026-09-12 round 9)."""
        with self._lock:
            cur = self._conn.execute(
                "UPDATE sessions SET title = ? WHERE id = ?",
                (str(title or ""), session_id),
            )
            self._conn.commit()
            return cur.rowcount > 0

    def set_pinned(self, session_id: str, pinned: bool) -> bool:
        """Pin / unpin a session (persisted; 2026-09-12 round 9)."""
        with self._lock:
            cur = self._conn.execute(
                "UPDATE sessions SET pinned = ? WHERE id = ?",
                (1 if pinned else 0, session_id),
            )
            self._conn.commit()
            return cur.rowcount > 0

    def set_system_prompt(self, session_id: str, prompt: str,
                          mode: str = "append") -> bool:
        """Store the per-session system prompt (persisted; 2026-09-13)."""
        normalized = (
            "replace" if str(mode or "").strip().lower() == "replace"
            else "append"
        )
        with self._lock:
            cur = self._conn.execute(
                "UPDATE sessions SET system_prompt = ?, system_prompt_mode = ?"
                " WHERE id = ?",
                (str(prompt or ""), normalized, session_id),
            )
            self._conn.commit()
            return cur.rowcount > 0

    def delete_session(self, session_id: str) -> bool:
        with self._lock:
            cur = self._conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
            deleted = cur.rowcount > 0
            if deleted:
                self._conn.execute(
                    "DELETE FROM messages WHERE session_id = ?", (session_id,)
                )
            self._conn.commit()
            return deleted

    # ── Extensions: persistence layer management ────────

    def truncate(self, session_id: str, keep: int) -> int:
        """Keep the first ``keep`` messages (by seq) and drop the rest.

        Used by the "regenerate / edit a single turn" feature: the session is
        rewound to just before the edited user message, then the new content is
        submitted as the current turn (instead of piling up as history).
        Returns the number of dropped messages.
        """
        keep = max(0, int(keep))
        with self._lock:
            pivot = self._conn.execute(
                "SELECT seq FROM messages WHERE session_id = ?"
                " ORDER BY seq LIMIT 1 OFFSET ?",
                (session_id, keep),
            ).fetchone()
            if pivot is None:
                return 0
            cur = self._conn.execute(
                "DELETE FROM messages WHERE session_id = ? AND seq >= ?",
                (session_id, pivot["seq"]),
            )
            self._conn.commit()
            return int(cur.rowcount or 0)

    def replace_tail(self, session_id: str, keep: int,
                     messages: List[ChatMessage]) -> bool:
        """Keep the first ``keep`` messages, then append ``messages`` (branch restore).

        Used by version switching: rewind to a turn start and re-apply a saved
        tail snapshot. 2026-09-13.
        """
        keep = max(0, int(keep))
        with self._lock:
            exists = self._conn.execute(
                "SELECT 1 FROM sessions WHERE id = ?", (session_id,)
            ).fetchone()
            if exists is None:
                return False
            pivot = self._conn.execute(
                "SELECT seq FROM messages WHERE session_id = ?"
                " ORDER BY seq LIMIT 1 OFFSET ?",
                (session_id, keep),
            ).fetchone()
            if pivot is not None:
                self._conn.execute(
                    "DELETE FROM messages WHERE session_id = ? AND seq >= ?",
                    (session_id, pivot["seq"]),
                )
            for message in (messages or []):
                self._conn.execute(
                    "INSERT INTO messages (session_id, role, content, tool_calls,"
                    " tool_call_id, name, reasoning, has_reasoning, attachments,"
                    " stats, segments)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (session_id, *_message_to_row(message)),
                )
            self._conn.execute(
                "UPDATE sessions SET updated_at = ? WHERE id = ?",
                (self._next_ts(), session_id),
            )
            self._conn.commit()
            return True

    def get_variants(self, session_id: str) -> Dict[str, Any]:
        """Persisted branch / version store of a session (JSON object).

        Optional capability; callers guard with ``getattr(sm, "get_variants", None)``.
        2026-09-13.
        """
        with self._lock:
            row = self._conn.execute(
                "SELECT data FROM session_variants WHERE session_id = ?",
                (session_id,),
            ).fetchone()
        if row is None or not (row["data"] or ""):
            return {}
        try:
            loaded = json.loads(row["data"])
            return loaded if isinstance(loaded, dict) else {}
        except (json.JSONDecodeError, TypeError):
            return {}

    def set_variants(self, session_id: str, data: Dict[str, Any]) -> bool:
        """Persist the branch / version store of a session. 2026-09-13."""
        payload = json.dumps(data or {}, ensure_ascii=False)
        with self._lock:
            exists = self._conn.execute(
                "SELECT 1 FROM sessions WHERE id = ?", (session_id,)
            ).fetchone()
            if exists is None:
                return False
            self._conn.execute(
                "INSERT INTO session_variants (session_id, data) VALUES (?, ?)"
                " ON CONFLICT(session_id) DO UPDATE SET data = excluded.data",
                (session_id, payload),
            )
            self._conn.commit()
            return True

    def close(self) -> None:
        """Close the database connection (call on process exit / test cleanup)."""
        with self._lock:
            self._conn.close()

    def clear(self) -> None:
        """Clear all sessions (tests and data resets)."""
        with self._lock:
            self._conn.execute("DELETE FROM messages")
            self._conn.execute("DELETE FROM sessions")
            self._conn.commit()

    # ── Internals ────────────────────────────────────────

    def _load_messages(self, session_id: str) -> List[ChatMessage]:
        rows = self._conn.execute(
            "SELECT role, content, tool_calls, tool_call_id, name,"
            " reasoning, has_reasoning, attachments, stats, segments FROM messages"
            " WHERE session_id = ? ORDER BY seq",
            (session_id,),
        ).fetchall()
        return [_row_to_message(r) for r in rows]
