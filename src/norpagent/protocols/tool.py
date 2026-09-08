# Copyright (c) 2026 xingluosama121, MIT Licensed
"""Tool protocol: the "skill" abstraction of an Agent.

Tool schemas follow the OpenAI function format (consistent with the existing
plugin system); ``run`` receives parsed dict arguments and a
:class:`~norpagent.kernel.context.RunContext`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Protocol, runtime_checkable


@dataclass
class ToolResult:
    """Tool execution result. ``output`` is fed back to the model as a tool-role message."""

    output: str = ""
    success: bool = True
    error: str = ""

    def __str__(self) -> str:
        if not self.success:
            return f"[tool execution failed] {self.error or self.output}"
        return self.output


def tool_error(tool_name: str, exc: Exception) -> ToolResult:
    """Build a unified tool exception result."""
    return ToolResult(output=f"{tool_name} execution error: {exc}", success=False, error=str(exc))


@runtime_checkable
class Tool(Protocol):
    """Single tool interface."""

    name: str

    def schema(self) -> Dict[str, Any]:
        """Return the OpenAI function schema (name/description/parameters)."""
        ...

    def run(self, args: Dict[str, Any], ctx: Any) -> ToolResult:
        """Execute the tool. ``ctx`` is a RunContext giving access to sandbox, session, registry, etc."""
        ...
