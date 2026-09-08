# Copyright (c) 2026 xingluosama121, MIT Licensed
"""Long-run task cooperation tools: task_submit / task_list / task_status / task_cancel.

In long-run tasks the Agent can submit subtasks to the scheduler queue
(task_submit), executed by the host application / background drain loop, enabling:

- task decomposition: big tasks split into subtasks, queued and executed by priority;
- multi-agent orchestration: subtasks can specify a different preset (task_submit's
  preset parameter) and be executed by the corresponding mode's Agent;
- checkpoint resume: with the persistent scheduler, tasks survive process restarts.

Tools access the scheduler via ``ctx.scheduler``; the query tools (list/status/cancel)
require the scheduler to provide same-named methods (all supported by the persistent
scheduler).
"""

from __future__ import annotations

from typing import Any, Dict, List

from norpagent.protocols.scheduler import AgentTask
from norpagent.protocols.tool import Tool, ToolResult


def _schedule(scheduler: Any, task: AgentTask) -> str:
    task.id = task.id or ""
    task.params = dict(task.params or {})
    task.params.setdefault("priority", 5)
    return scheduler.submit(task)


def _fmt_task(t: Dict[str, Any]) -> str:
    params = t.get("params") or {}
    parts = [
        f"{t.get('id')}  [{t.get('status')}]  pri={params.get('priority', '-')}"
        f"  preset={t.get('preset_name') or '(inherited)'}"
    ]
    text = t.get("user_input") or ""
    if len(text) > 80:
        text = text[:80] + "..."
    parts.append(f"      {text}")
    error = t.get("error") or ""
    if error:
        parts.append(f"      error: {error}")
    return "\n".join(parts)


class TaskSubmitTool:
    name = "task_submit"

    def schema(self) -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": (
                    "Submits a subtask to the task queue (long-run task cooperation / multi-agent orchestration). "
                    "Subtasks are scheduled by the host application by priority; the preset parameter can pick the "
                    "execution mode and session_id can reuse an existing session. Returns the task id after submission; "
                    "query progress with task_status."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "input": {"type": "string", "description": "Full self-contained description of the subtask (the executor cannot see the parent task's context)"},
                        "preset": {"type": "string", "description": "Preset mode name that executes this task; defaults to inheriting the current mode"},
                        "priority": {"type": "integer", "description": "Priority (0 highest, default 5)"},
                        "session_id": {"type": "string", "description": "Session id to reuse (optional; default creates a new session)"},
                    },
                    "required": ["input"],
                    "additionalProperties": False,
                },
            },
        }

    def run(self, args: Dict[str, Any], ctx: Any) -> ToolResult:
        if ctx.scheduler is None:
            return ToolResult(
                output="The current mode has no task scheduler assembled.", success=False,
                error="scheduler not assembled",
            )
        user_input = str(args.get("input") or "").strip()
        if not user_input:
            return ToolResult(output="input parameter is empty.", success=False, error="empty_input")
        preset = str(args.get("preset") or "") or ctx.preset_name
        params: Dict[str, Any] = {}
        try:
            params["priority"] = max(0, min(int(args.get("priority") or 5), 99))
        except (TypeError, ValueError):
            params["priority"] = 5
        try:
            task_id = _schedule(ctx.scheduler, AgentTask(
                id="",
                user_input=user_input,
                preset_name=preset,
                session_id=str(args.get("session_id") or "") or None,
                params=params,
            ))
        except Exception as exc:  # noqa: BLE001
            return ToolResult(output=f"submit failed: {exc}", success=False, error=str(exc))
        return ToolResult(
            output=(
                f"subtask enqueued: id={task_id}, mode={preset}, priority={params['priority']}. "
                "Executed when the host application drains the queue; query progress with task_status."
            )
        )


class TaskListTool:
    name = "task_list"

    def schema(self) -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": "Lists tasks in the task queue (sorted by priority); filterable by status.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "status": {"type": "string", "description": "Filter by status: pending/running/done/failed/stopped/cancelled (optional)"},
                        "limit": {"type": "integer", "description": "Max entries to return (default 20, max 200)"},
                    },
                    "additionalProperties": False,
                },
            },
        }

    def run(self, args: Dict[str, Any], ctx: Any) -> ToolResult:
        scheduler = ctx.scheduler
        if scheduler is None:
            return ToolResult(output="The current mode has no task scheduler assembled.", success=False, error="scheduler not assembled")
        list_fn = getattr(scheduler, "list_tasks", None)
        if not callable(list_fn):
            return ToolResult(
                output=(
                    f"The current scheduler ({type(scheduler).__name__}) does not support task queries. "
                    "Use the persistent scheduler (preset scheduler=\"persistent\")."
                ),
                success=False,
                error="scheduler does not support queries",
            )
        try:
            tasks = list_fn(
                status=str(args.get("status") or "") or None,
                limit=int(args.get("limit") or 20),
            )
            counts = getattr(scheduler, "counts", None)
            counts = counts() if callable(counts) else {}
        except Exception as exc:  # noqa: BLE001
            return ToolResult(output=f"read failed: {exc}", success=False, error=str(exc))
        lines = ["[task queue]", "", f"stats: {counts or 'unavailable'}", ""]
        if not tasks:
            lines.append("(queue empty)")
        for t in tasks:
            lines.append(_fmt_task(t))
            lines.append("")
        return ToolResult(output="\n".join(lines).rstrip())


class TaskStatusTool:
    name = "task_status"

    def schema(self) -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": "Queries the status and result of a single task (long-run task progress tracking).",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "task_id": {"type": "string", "description": "Task id (returned by task_submit)"},
                    },
                    "required": ["task_id"],
                    "additionalProperties": False,
                },
            },
        }

    def run(self, args: Dict[str, Any], ctx: Any) -> ToolResult:
        scheduler = ctx.scheduler
        if scheduler is None:
            return ToolResult(output="The current mode has no task scheduler assembled.", success=False, error="scheduler not assembled")
        status_fn = getattr(scheduler, "status", None)
        if not callable(status_fn):
            return ToolResult(
                output=f"The current scheduler ({type(scheduler).__name__}) does not support status queries; use the persistent scheduler.",
                success=False,
                error="scheduler does not support status queries",
            )
        task_id = str(args.get("task_id") or "").strip()
        if not task_id:
            return ToolResult(output="task_id parameter is empty.", success=False, error="empty_task_id")
        try:
            status = status_fn(task_id)
        except Exception as exc:  # noqa: BLE001
            return ToolResult(output=f"query failed: {exc}", success=False, error=str(exc))
        if status is None:
            return ToolResult(output=f"task {task_id} does not exist.", success=False, error="not_found")
        lines = [_fmt_task(status)]
        result = status.get("result") or ""
        if result:
            lines.append(f"result summary: {result}")
        return ToolResult(output="\n".join(lines))


class TaskCancelTool:
    name = "task_cancel"

    def schema(self) -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": "Cancels a task still queued (pending).",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "task_id": {"type": "string", "description": "Task id"},
                    },
                    "required": ["task_id"],
                    "additionalProperties": False,
                },
            },
        }

    def run(self, args: Dict[str, Any], ctx: Any) -> ToolResult:
        scheduler = ctx.scheduler
        if scheduler is None:
            return ToolResult(output="The current mode has no task scheduler assembled.", success=False, error="scheduler not assembled")
        cancel_fn = getattr(scheduler, "cancel", None)
        if not callable(cancel_fn):
            return ToolResult(
                output=f"The current scheduler ({type(scheduler).__name__}) does not support cancellation; use the persistent scheduler.",
                success=False,
                error="scheduler does not support cancellation",
            )
        task_id = str(args.get("task_id") or "").strip()
        if not task_id:
            return ToolResult(output="task_id parameter is empty.", success=False, error="empty_task_id")
        try:
            ok = cancel_fn(task_id)
        except Exception as exc:  # noqa: BLE001
            return ToolResult(output=f"cancel failed: {exc}", success=False, error=str(exc))
        if not ok:
            return ToolResult(
                output=f"task {task_id} does not exist or is not in pending state (running/finished tasks cannot be cancelled).",
                success=False,
                error="not_cancellable",
            )
        return ToolResult(output=f"task {task_id} cancelled.")
