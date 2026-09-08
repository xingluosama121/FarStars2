# Copyright (c) 2026 xingluosama121, MIT Licensed
"""run_python tool: the execution core of PTC mode (sandboxed execution since P4).

PTC (Programmatic Tool Composition): the model does not issue multiple tool calls
directly; it generates a piece of Python code and composes multi-step tool calls
(conditions, loops, aggregation) inside the code via ``call_tool(name, **args)``;
the framework executes the code and returns the result.

P4 execution model: the code executes in isolation in a **sandbox child process**
(AST static precheck + restricted builtins + clean function namespace + process
isolation + timeout force-kill + output cap); ``call_tool`` calls inside the code
are relayed back to the host through a protocol channel (going through the
registry, sharing the same tools/components as the Agent). When the sandbox does
not implement ``run_python``, it falls back to in-process restricted execution
(P1-compatible path; output marks isolation=inproc).
"""

from __future__ import annotations

import contextlib
import io
from typing import Any, Dict

from norpagent.builtin.sandboxes.isolated_python import (
    _ALLOWED_BUILTIN_NAMES,
    check_ptc_source,
)
from norpagent.protocols.tool import Tool, ToolResult

# restricted builtins allowlist: no import / open / exec / eval / type and other dangerous entries
_ALLOWED_BUILTINS: Dict[str, Any] = {
    name: getattr(__import__("builtins"), name)
    for name in _ALLOWED_BUILTIN_NAMES
}


class RunPythonTool:
    name = "run_python"

    def schema(self) -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": (
                    "Executes a piece of Python code (sandbox-isolated). Inside the code, "
                    "call_tool(tool_name, **args) can compose any of the Agent's registered tools, "
                    "enabling multi-step, conditional, loop-style tool orchestration."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "code": {
                            "type": "string",
                            "description": "The Python code to execute. May call tools via call_tool(name, **args).",
                        },
                    },
                    "required": ["code"],
                    "additionalProperties": False,
                },
            },
        }

    def run(self, args: Dict[str, Any], ctx: Any) -> ToolResult:
        code = args.get("code", "")
        if not code or not isinstance(code, str):
            return ToolResult(output="code parameter is empty", success=False, error="missing code")

        # ── AST static precheck (main security boundary; shared by sandbox and fallback paths) ──
        allowed, reason = check_ptc_source(code)
        if not allowed:
            return ToolResult(
                output=f"[run_python security blocked] {reason}",
                success=False,
                error=reason,
            )

        params = getattr(ctx, "params", {}) or {}
        timeout = float(params.get("ptc_timeout", 60) or 60)

        # ── sandboxed execution (preferred): the preset's sandbox if it implements run_python ──
        sandbox = getattr(ctx, "sandbox", None)
        runner = getattr(sandbox, "run_python", None)
        if callable(runner):
            result = runner(code, self._make_dispatcher(ctx), timeout)
            output = result.stdout.strip()
            if result.timed_out:
                return ToolResult(
                    output=(
                        (output + "\n" if output else "")
                        + f"[run_python timeout] execution exceeded {timeout}s; process force-killed"
                    ).strip(),
                    success=False,
                    error=f"timeout: ptc_timeout({timeout}s), process force-killed",
                )
            if result.exit_code != 0:
                err = result.stderr.strip() or "sandbox execution failed"
                return ToolResult(
                    output=(
                        (output + "\n" if output else "") + f"[run_python error] {err}"
                    ).strip(),
                    success=False,
                    error=err,
                )
            if not output:
                output = "(code executed successfully, no output)"
            return ToolResult(output=output)

        # ── fallback: in-process restricted execution (P1-compatible; marks the isolation level) ──
        return self._run_inproc(code, ctx)

    @staticmethod
    def _make_dispatcher(ctx: Any):
        """Build the host-side tool dispatcher (the RPC server of call_tool inside the code)."""

        def dispatch(name: str, args: Dict[str, Any]) -> str:
            tool = ctx.registry.resolve_tool(name)
            result = tool.run(args or {}, ctx)
            if result.success:
                return result.output
            raise RuntimeError(result.error or result.output)

        return dispatch

    def _run_inproc(self, code: str, ctx: Any) -> ToolResult:
        def call_tool(name: str, **kwargs: Any) -> str:
            """Unified entry to call registered tools inside PTC code."""
            tool = ctx.registry.resolve_tool(name)
            result = tool.run(kwargs, ctx)
            if result.success:
                return result.output
            raise RuntimeError(result.error or result.output)

        sandbox_globals: Dict[str, Any] = {
            "__builtins__": _ALLOWED_BUILTINS,
            "call_tool": call_tool,
        }
        buffer = io.StringIO()
        try:
            with contextlib.redirect_stdout(buffer):
                exec(compile(code, "<run_python>", "exec"), sandbox_globals)  # noqa: S102
        except Exception as exc:  # noqa: BLE001
            printed = buffer.getvalue()
            return ToolResult(
                output=(printed + f"\n[run_python error] {type(exc).__name__}: {exc}").strip(),
                success=False,
                error=f"{type(exc).__name__}: {exc}",
            )
        output = buffer.getvalue().strip()
        if not output:
            output = "(code executed successfully, no output)"
        return ToolResult(output=output)
