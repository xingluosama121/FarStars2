# Copyright (c) 2026 xingluosama121, MIT Licensed
"""Simple task scheduler: FIFO sequential execution.

P3 will extend: queue priorities, concurrency caps, long-running task cooperation
(task splitting / resume), multi-agent orchestration (child agents reuse the same
registry and submit subtasks through RunContext.scheduler).
"""

from __future__ import annotations

import queue
import uuid
from typing import Callable, List, Optional

from norpagent.protocols.scheduler import AgentTask, TaskResult


class SimpleTaskScheduler:
    """FIFO sequential task scheduler (thread-safe)."""

    def __init__(self) -> None:
        self._queue: "queue.Queue[AgentTask]" = queue.Queue()

    def submit(self, task: AgentTask) -> str:
        if not task.id:
            task.id = uuid.uuid4().hex[:12]
        task.status = "pending"
        self._queue.put(task)
        return task.id

    def pending(self) -> int:
        return self._queue.qsize()

    def drain(self, run_task: Callable[[AgentTask], TaskResult]) -> List[TaskResult]:
        results: List[TaskResult] = []
        while True:
            try:
                task = self._queue.get_nowait()
            except queue.Empty:
                break
            task.status = "running"
            try:
                task_result = run_task(task)
            except Exception as exc:  # noqa: BLE001 — a single task failure must not block the queue
                task_result = TaskResult(task_id=task.id, status="failed", error=str(exc))
            task.status = task_result.status
            task.result = task_result
            results.append(task_result)
            self._queue.task_done()
        return results
