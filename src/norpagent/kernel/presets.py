# Copyright (c) 2026 xingluosama121, MIT Licensed
"""Preset mode system: a mode = a declarative component composition.

A preset contains no implementation; it only declares "which components + what
behavior parameters". Adding a new mode = creating a new Preset (see the built-in
modes under modes/, or use creative mode to load a custom file via --mode-file).
"""

from __future__ import annotations

import importlib.util
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from norpagent.kernel.registry import ComponentError

# mode types
MODE_SINGLE = "single"   # conversational: direct model dialogue + tool calls
MODE_PTC = "ptc"         # PTC: the model generates Python code composing multi-step tool calls
MODE_CUSTOM = "custom"   # user-defined mode


@dataclass
class Preset:
    """A preset mode.

    Common ``params`` keys:
        max_steps: max steps per task
        temperature / max_tokens: model sampling parameters
        system_prompt: system prompt
        task_timeout: task timeout in seconds (0 = unlimited, checked at turn boundaries)
        call_timeout: hard timeout in seconds for a single model call (0 = unlimited, force-kill mid-block)
        workspace_root: workspace root for file tools (default: process working directory)

    ``components`` declares additional assembly of "component kind -> component name" (since P3):
        generic components such as context_store / project_manager / task_store are
        built by name at runtime and injected into RunContext; tools access them via ctx.
    """

    name: str
    description: str
    model: str
    tools: List[str] = field(default_factory=list)
    session: str = "memory"
    sandbox: str = "subprocess"
    scheduler: str = "simple"
    ui: str = "console"
    mode: str = MODE_SINGLE
    params: Dict[str, Any] = field(default_factory=dict)
    components: Dict[str, str] = field(default_factory=dict)

    def merged_params(self, task_params: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """Merge preset params with task-level params (task-level wins)."""
        merged = dict(self.params)
        if task_params:
            merged.update(task_params)
        return merged

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "model": self.model,
            "tools": list(self.tools),
            "session": self.session,
            "sandbox": self.sandbox,
            "scheduler": self.scheduler,
            "ui": self.ui,
            "mode": self.mode,
            "params": dict(self.params),
            "components": dict(self.components),
        }


def load_preset_file(path: str) -> Preset:
    """Load a custom mode from a .py file (core capability of creative mode).

    File convention: module-level variable ``PRESET`` is a Preset instance (or a
    dict with the same field names). See examples/custom_mode_file.py.
    """
    spec = importlib.util.spec_from_file_location("norpagent_user_mode", path)
    if spec is None or spec.loader is None:
        raise ComponentError(f"cannot load mode file: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    preset = getattr(module, "PRESET", None)
    if preset is None:
        raise ComponentError(f"mode file {path} does not define PRESET")
    if isinstance(preset, dict):
        preset = Preset(**preset)
    if not isinstance(preset, Preset):
        raise ComponentError(f"PRESET in mode file {path} has an invalid type: {type(preset)}")
    return preset
