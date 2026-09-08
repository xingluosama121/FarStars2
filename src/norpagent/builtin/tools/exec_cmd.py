# Copyright (c) 2026 xingluosama121, MIT Licensed
"""exec_cmd tool: executes shell commands in the task sandbox.

Command execution does not call subprocess directly; it goes through
ctx.sandbox (Sandbox protocol): when the sandbox implementation is replaced
(e.g. the P3 sandbox pool / containers / resource-limited version), neither
tools nor presets need changes.

The cwd parameter is also subject to workspace path safety constraints.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from norpagent.builtin.tools.pathsafe import PathSafetyError, resolve_safe_path
from norpagent.protocols.tool import Tool, ToolResult

_MAX_TIMEOUT = 300.0
_DEFAULT_TIMEOUT = 60.0


class ExecCmdTool:
    name = "exec_cmd"

    def schema(self) -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": (
                    "Executes a shell command in the sandbox and returns stdout / stderr / exit code. "
                    "Cross-platform: cmd on Windows, /bin/sh on POSIX. "
                    "Suitable for engineering commands such as tests, builds and version control; "
                    "for long-running tasks use background mode or split into multiple steps."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "command": {"type": "string", "description": "The shell command to execute"},
                        "timeout": {"type": "number", "description": f"Timeout in seconds (default {_DEFAULT_TIMEOUT}, max {_MAX_TIMEOUT})"},
                        "cwd": {"type": "string", "description": "Working directory (relative to the workspace root, optional)"},
                    },
                    "required": ["command"],
                    "additionalProperties": False,
                },
            },
        }

    def run(self, args: Dict[str, Any], ctx: Any) -> ToolResult:
        command = (args.get("command") or "").strip()
        if not command:
            return ToolResult(output="command parameter is empty", success=False, error="missing command")

        timeout = _clamp_timeout(args.get("timeout"))

        cwd: Optional[str] = None
        raw_cwd = args.get("cwd")
        if raw_cwd:
            try:
                cwd = str(resolve_safe_path(ctx, str(raw_cwd), must_exist=True))
            except PathSafetyError as exc:
                return ToolResult(output=str(exc), success=False, error=str(exc))

        sandbox = getattr(ctx, "sandbox", None)
        if sandbox is None or not hasattr(sandbox, "run_shell"):
            return ToolResult(
                output="The current task has no sandbox configured; commands cannot be executed. "
                "Specify a sandbox in the preset (e.g. 'subprocess').",
                success=False,
                error="no_sandbox",
            )

        try:
            result = sandbox.run_shell(command, timeout=timeout, cwd=cwd)
        except Exception as exc:  # noqa: BLE001
            return ToolResult(output=f"command execution error: {exc}", success=False, error=str(exc))

        parts: list[str] = [f"[exec_cmd] $ {command}"]
        if result.stdout:
            parts.append("[stdout]\n" + result.stdout)
        if result.stderr:
            parts.append("[stderr]\n" + result.stderr)
        if result.timed_out:
            parts.append(f"(command timed out, terminated: {timeout}s)")
        parts.append(f"(exit_code={result.exit_code})")
        output = "\n".join(parts)
        return ToolResult(
            output=output,
            success=result.ok,
            error="" if result.ok else (result.stderr or f"exit_code={result.exit_code}"),
        )


def _clamp_timeout(raw: Any) -> float:
    try:
        timeout = float(raw)
    except (TypeError, ValueError):
        return _DEFAULT_TIMEOUT
    if timeout <= 0:
        return _DEFAULT_TIMEOUT
    return min(timeout, _MAX_TIMEOUT)
