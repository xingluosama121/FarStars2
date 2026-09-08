# Copyright (c) 2026 xingluosama121, MIT Licensed
"""PTC mode (Programmatic Tool Composition):
the model composes multi-step tool calls by generating Python code.

Difference from standard mode: instead of issuing tool calls one by one, the model
writes "which tools to call and how to combine results" as a code snippet, executed
by the run_python tool. Suitable for multi-step orchestration tasks needing
conditions, loops and batched aggregation.
"""

from norpagent.kernel.presets import Preset, MODE_PTC

_SYSTEM_PROMPT = (
    "You are a PTC (Programmatic Tool Composition) assistant.\n"
    "When a task needs multiple tools working together, do not issue tool calls one by one; instead:\n"
    "1. Generate a piece of Python code;\n"
    "2. In the code, call the Agent's registered tools via call_tool(tool_name, **args);\n"
    "3. Organize call order, conditionals and result aggregation in code;\n"
    "4. Execute the code with the run_python tool and continue or answer based on the output.\n"
    "Simple questions can be answered directly without writing code."
)


def build_ptc_preset(model: str = "openai_compat") -> Preset:
    return Preset(
        name="ptc",
        description="PTC mode: the model generates Python code to compose multi-step tool calls",
        model=model,
        tools=[
            "run_python",  # PTC execution core
            # orchestrated business tools (full P2 set + P3 context/project/task)
            "echo",
            "get_time",
            "file_read",
            "file_write",
            "file_list",
            "file_delete",
            "file_surgeon",
            "search_in_file",
            "exec_cmd",
            "web_search",
            "web_fetch",
            "web_extract_links",
            "context_add",
            "context_search",
            "context_list",
            "context_delete",
            "project_status",
            "task_submit",
            "task_list",
            "task_status",
            "task_cancel",
        ],
        session="sqlite",
        sandbox="pooled",
        scheduler="persistent",
        ui="console",
        mode=MODE_PTC,
        components={
            "context_store": "fts5",
            "project_manager": "basic",
        },
        params={
            "max_steps": 64,
            "temperature": 1.0,
            "system_prompt": _SYSTEM_PROMPT,
            "task_timeout": 0,
        },
    )
