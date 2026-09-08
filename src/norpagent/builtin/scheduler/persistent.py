# Copyright (c) 2026 xingluosama121, MIT Licensed
"""Persistent task scheduler: the foundation of long-run task cooperation (SQLite, zero third-party dependencies).

Implements the same TaskScheduler protocol as SimpleTaskScheduler (in-process FIFO),
and extends it with:

- **persistence**: tasks are written to disk on submit (default ``~/.norpagent/tasks.db``);
  after a process crash / restart, ``resume`` continues executing unfinished tasks;
- **priority**: submit supports priority (0 highest; larger numbers run later);
- **task lifecycle**: pending / running / done / failed / stopped / cancelled;
- **query interface**: data source of the task_* tools (submit/list/status/cancel).

Replacement works the same: ``registry.register_scheduler("persistent", factory)``.
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
import uuid
from typing import Any, Callable, Dict, List, Optional

from norpagent.protocols.scheduler import AgentTask, TaskResult, TaskScheduler

_SCHEMA = """
CREATE TABLE IF NOT EXISTS tasks (
    id TEXT PRIMARY KEY,
    user_input TEXT NOT NULL,
    preset_name TEXT NOT NULL DEFAULT '',
    session_id TEXT,
    params TEXT NOT NULL DEFAULT '{}',
    priority INTEGER NOT NULL DEFAULT 5,
    status TEXT NOT NULL DEFAULT 'pending',
    error TEXT NOT NULL DEFAULT '',
    result TEXT NOT NULL DEFAULT '',
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    started_at REAL,
    finished_at REAL
);
CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status, priority, created_at);
"""

_TERMINAL_STATUSES = {"done", "failed", "stopped", "cancelled"}


def _task_to_row(task: AgentTask, now: float) -> tuple:
    return (
        task.id,
        task.user_input,
        task.preset_name or "",
        task.session_id,
        json.dumps(task.params or {}, ensure_ascii=False),
        int(task.params.get("priority", 5)) if task.params else 5,
        task.status,
    )


class PersistentTaskScheduler(TaskScheduler):
    """SQLite persistent task scheduler (priority queue + restart resume)."""

    def __init__(self, path: Optional[str] = None) -> None:
        self.path = path or os.path.join(
            os.path.expanduser("~"), ".norpagent", "tasks.db"
        )
        parent = os.path.dirname(os.path.abspath(self.path))
        os.makedirs(parent, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.executescript(_SCHEMA)
            self._conn.commit()

    # ── TaskScheduler protocol ────────────────────────────

    def submit(self, task: AgentTask) -> str:
        if not task.id:
            task.id = uuid.uuid4().hex[:12]
        task.status = "pending"
        now = time.time()
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO tasks (id, user_input, preset_name,"
                " session_id, params, priority, status, created_at, updated_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    *_task_to_row(task, now), now, now,
                ),
            )
            self._conn.commit()
        return task.id

    def pending(self) -> int:
        with self._lock:
            row = self._conn.execute(
                "SELECT COUNT(*) AS n FROM tasks WHERE status IN ('pending','running')"
            ).fetchone()
            return int(row["n"])

    def drain(
        self, run_task: Callable[[AgentTask], TaskResult]
    ) -> List[TaskResult]:
        """Execute all pending tasks by priority.

        - reentrancy protection: only one drain at a time (in-process lock);
        - crash recovery: when drain starts, leftover running tasks are reset to
          pending (a crashed process never got a chance to mark them finished);
        - each task is independently try/except'd; a failure never blocks the queue.
        """
        with self._lock:
            if getattr(self, "_draining", False):
                raise RuntimeError("PersistentTaskScheduler.drain is already running (concurrent drain not supported)")
            self._draining = True
            self._conn.execute(
                "UPDATE tasks SET status='pending', updated_at=? WHERE status='running'",
                (time.time(),),
            )
            self._conn.commit()
        results: List[TaskResult] = []
        try:
            while True:
                with self._lock:
                    row = self._conn.execute(
                        "SELECT * FROM tasks WHERE status='pending'"
                        " ORDER BY priority ASC, created_at ASC LIMIT 1"
                    ).fetchone()
                    if row is None:
                        break
                    self._conn.execute(
                        "UPDATE tasks SET status='running', started_at=?, updated_at=?"
                        " WHERE id=?",
                        (time.time(), time.time(), row["id"]),
                    )
                    self._conn.commit()
                task = self._row_to_task(row)
                try:
                    task_result = run_task(task)
                except Exception as exc:  # noqa: BLE001 — a single task failure must not block the queue
                    task_result = TaskResult(task_id=task.id, status="failed", error=str(exc))
                self._finish(task.id, task_result)
                results.append(task_result)
        finally:
            with self._lock:
                self._draining = False
        return results

    # ── task lifecycle (data source of the task_* tools) ──

    def status(self, task_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM tasks WHERE id = ?", (task_id,)
            ).fetchone()
            return self._row_to_dict(row) if row is not None else None

    def list_tasks(
        self,
        status: Optional[str] = None,
        limit: int = 20,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        sql = "SELECT * FROM tasks"
        args: List[Any] = []
        if status:
            sql += " WHERE status = ?"
            args.append(status)
        sql += " ORDER BY priority ASC, created_at ASC LIMIT ? OFFSET ?"
        args += [max(1, min(int(limit), 200)), max(0, int(offset))]
        with self._lock:
            rows = self._conn.execute(sql, args).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def cancel(self, task_id: str) -> bool:
        """Cancel a pending task (running / finished tasks cannot be cancelled)."""
        with self._lock:
            cur = self._conn.execute(
                "UPDATE tasks SET status='cancelled', updated_at=?, finished_at=?"
                " WHERE id=? AND status='pending'",
                (time.time(), time.time(), task_id),
            )
            self._conn.commit()
            return cur.rowcount > 0

    def stop(self, task_id: str, reason: str = "") -> bool:
        """Mark a task as stopped (called when the host application stops a long-run task)."""
        with self._lock:
            cur = self._conn.execute(
                "UPDATE tasks SET status='stopped', error=?, updated_at=?, finished_at=?"
                " WHERE id=? AND status='running'",
                (reason, time.time(), time.time(), task_id),
            )
            self._conn.commit()
            return cur.rowcount > 0

    def counts(self) -> Dict[str, int]:
        with self._lock:
            out: Dict[str, int] = {}
            for r in self._conn.execute(
                "SELECT status, COUNT(*) AS n FROM tasks GROUP BY status"
            ).fetchall():
                out[r["status"]] = int(r["n"])
        return out

    def resume(self) -> int:
        """Reset running tasks left over from a crash to pending; returns the number recovered.

        Core capability of long-run task cooperation: call once after a process
        restart and unfinished tasks are automatically requeued (the host application
        calls this at startup).
        """
        with self._lock:
            cur = self._conn.execute(
                "UPDATE tasks SET status='pending', updated_at=? WHERE status='running'",
                (time.time(),),
            )
            self._conn.commit()
            return cur.rowcount

    def clear(self) -> None:
        """Clear all tasks (tests and data resets)."""
        with self._lock:
            self._conn.execute("DELETE FROM tasks")
            self._conn.commit()

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    # ── internals ────────────────────────────────────────

    def _finish(self, task_id: str, task_result: TaskResult) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE tasks SET status=?, error=?, result=?, updated_at=?,"
                " finished_at=? WHERE id=?",
                (
                    task_result.status,
                    task_result.error or "",
                    self._dump_result(task_result),
                    time.time(),
                    time.time(),
                    task_id,
                ),
            )
            self._conn.commit()

    @staticmethod
    def _dump_result(task_result: TaskResult) -> str:
        run_result = task_result.run_result
        summary = ""
        if run_result is not None:
            summary = getattr(run_result, "final_content", "") or ""
        return json.dumps(
            {
                "status": task_result.status,
                "error": task_result.error,
                "summary": summary[:2000],
            },
            ensure_ascii=False,
        )

    @staticmethod
    def _row_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
        out = dict(row)
        try:
            out["params"] = json.loads(out.get("params") or "{}")
        except json.JSONDecodeError:
            out["params"] = {}
        return out

    @staticmethod
    def _row_to_task(row: sqlite3.Row) -> AgentTask:
        try:
            params = json.loads(row["params"] or "{}")
        except json.JSONDecodeError:
            params = {}
        return AgentTask(
            id=row["id"],
            user_input=row["user_input"],
            preset_name=row["preset_name"] or "",
            session_id=row["session_id"],
            params=params,
            status=row["status"],
        )
