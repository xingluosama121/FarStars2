# Copyright (c) 2026 xingluosama121, MIT Licensed
"""Kernel layer: registry, event bus, presets and the generic agent loop.

Kernel code is the part developers never need to modify: it only knows protocols and the registry.
All capability differences are determined by "which components are registered, which preset is chosen".
"""

from norpagent.kernel.events import EventBus, EventType, AgentEvent
from norpagent.kernel.registry import Registry, ComponentError
from norpagent.kernel.presets import Preset, load_preset_file, MODE_SINGLE, MODE_PTC, MODE_CUSTOM
from norpagent.kernel.context import RunContext
from norpagent.kernel.agent import AgentRuntime, RunResult

__all__ = [
    "EventBus",
    "EventType",
    "AgentEvent",
    "Registry",
    "ComponentError",
    "Preset",
    "load_preset_file",
    "MODE_SINGLE",
    "MODE_PTC",
    "MODE_CUSTOM",
    "RunContext",
    "AgentRuntime",
    "RunResult",
]
