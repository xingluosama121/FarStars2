# Copyright (c) 2026 xingluosama121, MIT Licensed
"""Standard mode: a fully featured general coding assistant (full P3 capability set).

Component composition (all replaceable):
- model openai_compat (--model mock verifies the flow; norpagent[openai] provides the SDK)
- session sqlite: persistent task history, resume chat after restart
- scheduler persistent: long-run tasks persisted to disk, resume after crash
- sandbox pooled: reuse + concurrency cap + timeout force-kill of process trees
- components: context_store=fts5 (cross-session searchable knowledge base), project_manager=basic

Full tool set: files / commands / web / context management / project management / long-run task cooperation.
"""

from norpagent.kernel.presets import Preset, MODE_SINGLE

_SYSTEM_PROMPT = (
    "You are a fully featured general coding assistant. "
    "You can use file read/write, command execution, web retrieval and other tools to complete complex engineering tasks. "
    "For long-period tasks: write intermediate conclusions into the context store (context_add) for later retrieval, "
    "and submit independent subtasks to the queue (task_submit) to advance in parallel. "
    "Follow engineering best practices: understand before acting; state the plan before important operations. "
    "All file operations are strictly confined to the workspace root; use relative paths."
)


def build_standard_preset(model: str = "openai_compat") -> Preset:
    return Preset(
        name="standard",
        description="Standard mode: a fully featured general coding assistant (full tool set + persistence + long-run cooperation)",
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
            # long-run task cooperation (P3)
            "task_submit",
            "task_list",
            "task_status",
            "task_cancel",
        ],
        session="sqlite",  # persistent sessions; switch to "memory" for in-memory environments
        sandbox="pooled",  # pooled sandbox; switch to "subprocess" for simple environments
        scheduler="persistent",  # long-run tasks persisted to disk; switch to "simple" for lightweight scenarios
        ui="console",  # switch to "web" for the web UI (HTTP + SSE)
        mode=MODE_SINGLE,
        components={
            "context_store": "fts5",  # cross-session searchable context store
            "project_manager": "basic",  # project status / git awareness
        },
        params={
            "max_steps": 128,
            "temperature": 1.0,
            "system_prompt": _SYSTEM_PROMPT,
            "task_timeout": 0,
            # hard timeout for a single model call (seconds; 0 = unlimited): force-kill capability while blocked
            "call_timeout": 0,
            # security hardening (optional):
            #   "jailbreak_guard": True  blocks jailbreak / injection inputs
            #   "harden_prompt": True    appends non-overridable security rules to the system prompt
        },
    )
