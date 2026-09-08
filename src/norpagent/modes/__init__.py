# Copyright (c) 2026 xingluosama121, MIT Licensed
"""Preset mode package: six built-in modes, all registered through the registry.

How to add a frequently used mode:
    1. Add build_xxx_preset() in this package and register it in register_all_presets;
    2. Use creative mode: --mode-file to load a custom mode file;
    3. Developers call registry.register_preset(Preset(...)) in their own code.
"""

from __future__ import annotations

from typing import Any

from norpagent.modes.minimal import build_minimal_preset
from norpagent.modes.standard import build_standard_preset
from norpagent.modes.ptc import build_ptc_preset
from norpagent.modes.creative import build_creative_preset
from norpagent.modes.longrun import build_longrun_preset
from norpagent.modes.embedded import build_embedded_preset


def register_all_presets(registry: Any) -> Any:
    """Register all built-in preset modes; returns the registry itself (for chaining)."""
    registry.register_preset(build_minimal_preset())
    registry.register_preset(build_standard_preset())
    registry.register_preset(build_ptc_preset())
    registry.register_preset(build_creative_preset())
    registry.register_preset(build_longrun_preset())
    registry.register_preset(build_embedded_preset())
    return registry


__all__ = [
    "register_all_presets",
    "build_minimal_preset",
    "build_standard_preset",
    "build_ptc_preset",
    "build_creative_preset",
    "build_longrun_preset",
    "build_embedded_preset",
]
