# Copyright (c) 2026 xingluosama121, MIT Licensed
"""Task scheduling protocol: the "orchestration" abstraction of an Agent.

P1 provides a FIFO sequential scheduler. P3 will extend queue priorities,
concurrency caps, long-running task cooperation and multi-agent orchestration
(child agents reuse the same registry).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Optional, Protocol, runtime_checkable


@dataclass
class AgentTask:
    """A pending (or executed) Agent task.

    ``runtime`` is injected by the scheduler: the scheduler hands the task to the
    AgentRuntime for execution.
    """

    id: str
    user_input: str
    preset_name: str = ""
    session_id: Optional[str] = None
    params: Dict[str, Any] = field(default_factory=dict)
    status: str = "pending"  # pending | running | done | failed | stopped
    result: Optional["TaskResult"] = None


@dataclass
class TaskResult:
    """Task execution result. ``run_result`` is the return value of AgentRuntime.run."""

    task_id: str
    status: str
    error: str = ""
    run_result: Any = None


@runtime_checkable
class TaskScheduler(Protocol):
    """Task scheduler interface.

    P1 contract: ``submit`` enqueues, ``drain`` executes all pending tasks in order.
    ``run_task`` is the callback the scheduler uses to execute a single task (injected
    by the runtime, decoupling the scheduler from the agent loop: in future
    multi-agent orchestration the callback can point to different agents).
    """

    def submit(self, task: AgentTask) -> str:
        """Enqueue a task and return its id."""
        ...

    def pending(self) -> int:
        """Number of pending tasks."""
        ...

    def drain(self, run_task: Callable[[AgentTask], TaskResult]) -> List[TaskResult]:
        """Execute all pending tasks sequentially and return the result list."""
        ...
