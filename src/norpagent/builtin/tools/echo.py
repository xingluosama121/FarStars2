# Copyright (c) 2026 xingluosama121, MIT Licensed
"""echo tool: echoes text back. One of the basic tools of minimal mode; has no side effects."""

from __future__ import annotations

from typing import Any, Dict

from norpagent.protocols.tool import Tool, ToolResult


class EchoTool:
    name = "echo"

    def schema(self) -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": "Echoes the input text back unchanged. Used for connectivity checks and benchmarks.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "text": {"type": "string", "description": "The text to echo"},
                    },
                    "required": ["text"],
                    "additionalProperties": False,
                },
            },
        }

    def run(self, args: Dict[str, Any], ctx: Any) -> ToolResult:
        return ToolResult(output=f"[echo] {args.get('text', '')}")
