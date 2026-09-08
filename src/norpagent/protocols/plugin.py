# Copyright (c) 2026 xingluosama121, MIT Licensed
"""Plugin protocol: the packaging and distribution unit of tools.

A plugin = a set of tools + a set of lifecycle hooks + metadata.
After registration in the Registry, its tools enter the tool registry and its
hooks subscribe to the event bus.

P1 is in-process plugins (objects registered directly). P3 will migrate the
existing plugin_system: single-file plugins / manifest package plugins / signature
verification / process isolation / network policy / human approval, giving external
plugins of this library the same security protections as the existing application.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Protocol, runtime_checkable

from norpagent.protocols.tool import Tool


@runtime_checkable
class Plugin(Protocol):
    """Plugin interface. All methods are optional (an empty plugin = metadata only)."""

    name: str
    version: str = "0.0.0"
    publisher: str = ""
    description: str = ""

    def get_tools(self) -> List[Tool]:
        """Return the list of tools provided by this plugin."""
        return []

    def get_hooks(self) -> Dict[str, Callable[[Any], None]]:
        """Return the hook mapping: event name -> callback(event).

        Event names align with the 15 hooks of the existing plugin_system
        (on_task_start / before_step / after_tool_call, etc.).
        """
        return {}

    def execute(self, tool_name: str, args: Dict[str, Any], ctx: Any) -> Optional[str]:
        """Unified entry compatible with the existing single-file plugin style (optional).

        Returning None means this plugin does not handle the given tool name.
        """
        return None
