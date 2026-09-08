# Copyright (c) 2026 xingluosama121, MIT Licensed
"""Creative mode: for debugging and creating brand-new custom modes.

- Minimal and deterministic component set (mock model) for reproducible debugging;
- load a custom mode file via CLI ``--mode-file my_mode.py``,
  or register a new mode in code via ``registry.register_preset(MyPreset)``;
- mode file convention: module-level variable ``PRESET`` is a Preset instance (or dict).
"""

from norpagent.kernel.presets import Preset, MODE_CUSTOM

_SYSTEM_PROMPT = (
    "You are running in creative mode (debug environment). Describe your behavior "
    "truthfully to help the developer verify that tools and mode configuration "
    "work as expected."
)


def build_creative_preset() -> Preset:
    return Preset(
        name="creative",
        description="Creative mode: debug and create custom modes (supports loading custom mode files via --mode-file)",
        model="mock",
        tools=["echo", "get_time", "run_python"],
        session="memory",
        sandbox="subprocess",
        scheduler="simple",
        ui="console",
        mode=MODE_CUSTOM,
        params={
            "max_steps": 32,
            "temperature": 0.0,
            "system_prompt": _SYSTEM_PROMPT,
            "task_timeout": 0,
        },
    )
