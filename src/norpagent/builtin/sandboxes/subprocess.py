# Copyright (c) 2026 xingluosama121, MIT Licensed
"""Subprocess sandbox: cross-platform command execution sandbox (no third-party dependencies).

P1 provides basic isolation (separate process + timeout + output capture).
P3 will migrate the existing application's sandbox pool (reuse / concurrency caps),
resource limits and network policy.

Cancellation semantics: run_shell waits in slices (checks the cancel event every
≤0.5s); on Ctrl+C / engine stop it force-kills the process tree immediately and
returns exit_code=-1 (stderr notes "task cancelled"); timeouts also force-kill
the process tree. A per-slice TimeoutExpired merely means "this slice expired";
a real timeout only occurs when the accumulated time reaches timeout.

Encoding notes: subprocess output is decoded in the order utf-8 → gbk → latin-1
to avoid mojibake from Windows Chinese code pages (consistent with the existing
application's robust_decode).
"""

from __future__ import annotations

import subprocess
import threading
import time
from typing import Any, Callable, Dict, List, Optional

from norpagent.builtin.sandboxes.pooled import (
    _kill_process_tree,
    _robust_decode,
    _stream_reader,
)
from norpagent.loops.cancel import cancel_requested
from norpagent.protocols.sandbox import SandboxResult


class SubprocessSandbox:
    """A single subprocess sandbox instance (starts a new process per run_shell).

    Supports ``run_python`` since P4: PTC code executes in a separate child
    process, and tool calls are relayed back to the host via a length-prefixed
    protocol (see isolated_python).
    """

    def run_shell(
        self,
        command: str,
        timeout: float = 60.0,
        cwd: Optional[str] = None,
        env: Optional[Dict[str, str]] = None,
    ) -> SandboxResult:
        try:
            proc = subprocess.Popen(
                command,
                shell=True,  # cross-platform: cmd on Windows, /bin/sh on POSIX
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=cwd,
                env=env,
            )
        except OSError as exc:
            return SandboxResult(stderr=str(exc), exit_code=-1)

        out_buf: List[bytes] = []
        err_buf: List[bytes] = []
        done_out = threading.Event()
        done_err = threading.Event()
        readers = [
            threading.Thread(
                target=_stream_reader, args=(proc.stdout, out_buf, done_out),
                daemon=True,
            ),
            threading.Thread(
                target=_stream_reader, args=(proc.stderr, err_buf, done_err),
                daemon=True,
            ),
        ]
        for t in readers:
            t.start()

        try:
            cancelled = False
            timed_out = False
            exit_code = 0
            started = time.monotonic()
            while True:
                if cancel_requested():
                    _kill_process_tree(proc)
                    cancelled = True
                    exit_code = -1
                    break
                remaining = timeout - (time.monotonic() - started)
                if remaining <= 0:
                    timed_out = True
                    _kill_process_tree(proc)
                    try:
                        proc.wait(3)
                    except Exception:
                        pass
                    exit_code = -1
                    break
                try:
                    exit_code = proc.wait(timeout=min(remaining, 0.5))
                    break
                except subprocess.TimeoutExpired:
                    continue  # slice expired; continue with the next slice
        finally:
            for t, done in ((readers[0], done_out), (readers[1], done_err)):
                if t.is_alive():
                    done.wait(1.0)
            for stream in (proc.stdout, proc.stderr):
                try:
                    if stream is not None:
                        stream.close()
                except Exception:
                    pass

        stdout = _robust_decode(b"".join(out_buf)).strip()
        stderr = _robust_decode(b"".join(err_buf)).strip()
        if cancelled:
            stderr = stderr or "task cancelled (Ctrl+C), command process terminated"
        elif timed_out:
            stderr = stderr or f"command timed out ({timeout}s)"
        return SandboxResult(
            stdout=stdout, stderr=stderr,
            exit_code=exit_code, timed_out=timed_out,
        )

    def run_python(
        self,
        code: str,
        tool_dispatch: Callable[[str, Dict[str, Any]], str],
        timeout: float = 60.0,
    ) -> SandboxResult:
        """Isolated PTC code execution: separate child process + tool RPC relay."""
        from norpagent.builtin.sandboxes.isolated_python import (
            IsolatedPythonRunner,
        )

        return IsolatedPythonRunner().execute(code, tool_dispatch, timeout)

    def close(self) -> None:
        """P1 holds no resident resources; returns immediately."""
        return None


class SubprocessSandboxProvider:
    """Subprocess sandbox provider: creates new instances on demand."""

    kind = "subprocess"

    def create(self) -> SubprocessSandbox:
        return SubprocessSandbox()
