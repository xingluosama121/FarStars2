# Copyright (c) 2026 xingluosama121, MIT Licensed
"""Long-run mode: a preset optimized for long-period, multi-stage complex tasks.

Shares the full tool set and persistent components with standard mode; differences
are in behavior parameters:
- larger max_steps (512), complex tasks are less likely to be interrupted by the step cap;
- task_timeout = 0 (no task-level timeout; controlled by turn boundaries and the stop button);
- the system prompt emphasizes phased planning: decompose milestones first, execute
  step by step and persist intermediate conclusions, so long tasks can resume from
  checkpoints (persistent scheduler + sqlite sessions + fts5 context store).
"""

from norpagent.kernel.presets import Preset, MODE_SINGLE

_SYSTEM_PROMPT = (
    "You are a long-period task execution assistant. "
    "For complex tasks, first decompose them into clear phases and milestones, then execute step by step. "
    "Write intermediate conclusions of each phase into the context store (context_add) for later retrieval, "
    "and submit independent subtasks to the queue (task_submit) to advance in parallel. "
    "Report progress periodically during long executions; when blocked, record the state first and then continue. "
    "All file operations are strictly confined to the workspace root; use relative paths."
)


def build_longrun_preset(model: str = "openai_compat") -> Preset:
    return Preset(
        name="longrun",
        description="Long-run: long-period complex tasks (larger step cap + persistent scheduling + checkpoint resume)",
        model=model,
        tools=[
            # file operations (P2)
            "file_read",
            "file_write",
            "file_list",
            "file_delete",
            "file_surgeon",
            "search_in_file",
            # command execution (P2)
            "exec_cmd",
            # web retrieval (P2)
            "web_search",
            "web_fetch",
            "web_extract_links",
            # context management (P3)
            "context_add",
            "context_search",
            "context_list",
            "context_delete",
            # project management (P3)
            "project_status",
            # long-period task cooperation (P3)
            "task_submit",
            "task_list",
            "task_status",
            "task_cancel",
        ],
        session="sqlite",
        sandbox="pooled",
        scheduler="persistent",
        ui="console",
        mode=MODE_SINGLE,
        components={
            "context_store": "fts5",
            "project_manager": "basic",
        },
        params={
            "max_steps": 512,
            "temperature": 1.0,
            "system_prompt": _SYSTEM_PROMPT,
            "task_timeout": 0,
            "call_timeout": 0,
        },
    )


__all__ = ["build_longrun_preset"]
