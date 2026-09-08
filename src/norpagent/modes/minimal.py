# Copyright (c) 2026 xingluosama121, MIT Licensed
"""Minimal mode: only the most basic tools, used for model benchmarks.

Design goals: maximize environment determinism, minimize variables.
- default model mock (replaceable with any registered model, e.g. openai_compat from P2)
- tools are only echo / get_time: no side effects, no network, no disk
- benchmark flow: fixed input set + fixed tool set, compare output quality,
  step count and token consumption across models / component implementations
"""

from norpagent.kernel.presets import Preset, MODE_SINGLE

_SYSTEM_PROMPT = (
    "You are a minimal benchmark assistant. Answer user questions directly and concisely. "
    "Only call tools when explicitly requested. Answer in the user's language."
)


def build_minimal_preset(model: str = "mock") -> Preset:
    return Preset(
        name="minimal",
        description="Minimal mode: only basic tools (echo/get_time), deterministic environment, for model benchmarks",
        model=model,
        tools=["echo", "get_time"],
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
        },
    )
