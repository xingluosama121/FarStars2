# Copyright (c) 2026 xingluosama121, MIT Licensed
"""Embedded mode: a resource-minimal combination for edge devices / low memory / diskless environments.

Design goals (embedded / low-resource scenarios):
- all components pure in-memory: memory session + subprocess sandbox + simple scheduler;
  no generic components declared (context_store / project_manager both empty —
  disk-dependent components such as FTS5 / SQLite are never built);
- minimal tool set: echo / get_time / run_python + file read/write/surgery/search
  (file_surgeon and search_in_file are streaming tools, constant memory), no network;
- no HTTP service by default: np(preset="embedded") automatically falls back to
  headless for the frontend slot (pure API mode; no port listening, no browser UI
  disk configuration); for a web UI, explicitly use np(preset="embedded",
  frontend="norpagent.frontends.web:WebFrontend");
- model declared as openai_compat: same fallback semantics as standard — when no
  credentials are provided, the assembly layer automatically falls back to mock
  (embedded devices work out of the box with no network / no API key).

Works with ``install_core()``: for embedded scenarios it is recommended to build a
custom registry via ``install_core`` (even the install phase avoids sqlite3 /
http.server dependencies), then register this preset; the np(preset="embedded")
path goes through the full install_defaults (only registers, does not build heavy
components) and automatically uses the headless frontend.

Resource tuning (see the "Embedded and high-concurrency deployment" chapter of the manual):
- worker pool threads: environment variable NORPAGENT_MAX_WORKERS (e.g. =1) or
  np(config={"loop": {"max_workers": 1}});
- submit completion polling: NORPAGENT_SUBMIT_POLL (default 0.05s; embedded can increase it).
"""

from norpagent.kernel.presets import Preset, MODE_SINGLE

_SYSTEM_PROMPT = (
    "You are a lightweight assistant running on an embedded device. "
    "Answer directly and concisely, avoid unnecessary tool calls, and conserve resources. "
    "Only read/write files or execute code when explicitly requested. Answer in the user's language."
)


def build_embedded_preset(model: str = "openai_compat") -> Preset:
    return Preset(
        name="embedded",
        description=(
            "Embedded mode: pure in-memory components + minimal tool set, no disk / no network "
            "dependencies, friendly to edge devices and low-resource environments (headless frontend by default)"
        ),
        model=model,
        tools=[
            "echo",
            "get_time",
            "run_python",
            "file_read",
            "file_write",
            "file_list",
            "file_delete",
            "file_surgeon",
            "search_in_file",
        ],
        session="memory",
        sandbox="subprocess",
        scheduler="simple",
        ui="console",
        mode=MODE_SINGLE,
        params={
            "max_steps": 8,
            "temperature": 0.0,
            "system_prompt": _SYSTEM_PROMPT,
            "task_timeout": 0,
            "max_tokens": 2048,
        },
    )


__all__ = ["build_embedded_preset"]
