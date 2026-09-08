# Copyright (c) 2026 xingluosama121, MIT Licensed
"""get_time tool: returns the current local time. One of the basic tools of minimal mode."""

from __future__ import annotations

import time
from typing import Any, Dict

from norpagent.protocols.tool import Tool, ToolResult


class GetTimeTool:
    name = "get_time"

    def schema(self) -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": "Returns the current local date and time (ISO 8601 format).",
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "additionalProperties": False,
                },
            },
        }

    def run(self, args: Dict[str, Any], ctx: Any) -> ToolResult:
        return ToolResult(
            output=time.strftime("%Y-%m-%d %H:%M:%S (%A)", time.localtime())
        )
