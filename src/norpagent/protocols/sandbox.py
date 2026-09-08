# Copyright (c) 2026 xingluosama121, MIT Licensed
"""Sandbox protocol: the "isolated execution environment" abstraction of an Agent.

P1 provides a subprocess command sandbox (cross-platform, no third-party dependencies).
P3 will migrate the existing application's sandbox pool, resource limits and
process-level plugin isolation capabilities.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Dict, Optional, Protocol, runtime_checkable


@dataclass
class SandboxResult:
    """Sandbox execution result."""

    stdout: str = ""
    stderr: str = ""
    exit_code: int = 0
    timed_out: bool = False

    @property
    def ok(self) -> bool:
        return self.exit_code == 0 and not self.timed_out


@runtime_checkable
class Sandbox(Protocol):
    """A created sandbox instance."""

    def run_shell(
        self,
        command: str,
        timeout: float = 60.0,
        cwd: Optional[str] = None,
        env: Optional[Dict[str, str]] = None,
    ) -> SandboxResult:
        """Execute a shell command in the sandbox and return the result."""
        ...

    def close(self) -> None:
        """Release sandbox resources."""
        ...


@runtime_checkable
class PythonSandbox(Protocol):
    """A sandbox supporting isolated Python execution (PTC / code-execution tools).

    Optional capability: sandboxes that do not implement ``run_python`` are
    handled by tool-side fallbacks (e.g. RunPythonTool falls back to in-process
    restricted execution).
    """

    def run_python(
        self,
        code: str,
        tool_dispatch: Callable[[str, Dict[str, Any]], str],
        timeout: float = 60.0,
    ) -> SandboxResult:
        """Execute Python code in the sandbox.

        ``tool_dispatch(name, args) -> str`` is the host-side tool-call service:
        ``call_tool(...)`` requests inside the code are forwarded through the
        sandbox to this callback, and the return value is passed back to the code;
        when the callback raises, the code side receives a RuntimeError.
        """
        ...


@runtime_checkable
class SandboxProvider(Protocol):
    """Sandbox provider: creates sandbox instances on demand (pooling, container policies etc. are implementation-defined)."""

    kind: str  # e.g. "subprocess" / "docker" / "pooled"

    def create(self) -> Sandbox:
        """Create (or borrow from the pool) a sandbox."""
        ...
