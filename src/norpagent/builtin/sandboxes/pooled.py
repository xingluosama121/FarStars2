# Copyright (c) 2026 xingluosama121, MIT Licensed
"""Pooled sandbox: reuse + concurrency cap + timeout force-kill of process trees (zero third-party dependencies).

Migrated from the existing application's sandbox_pool, reimplemented against this
library's Sandbox protocol:

- **pool reuse**: at most ``max_sandboxes`` sandbox instances, borrowed / returned;
  ``create()`` waits (with a configurable timeout) when no instance is free and the cap is reached;
- **concurrency cap**: pool capacity is the concurrent command cap, preventing a
  runaway model from saturating the machine;
- **timeout force-kill**: on command timeout the **whole process tree** is killed
  (Windows: taskkill /T, POSIX: process-group SIGKILL), eliminating orphan
  processes — force-killed instances are never reused;
- **cwd / env memory**: each instance remembers its last working directory, so
  consecutive commands behave like operating in the same terminal.

Registration: ``registry.register_sandbox("pooled", PooledSandboxProvider(...).create)``.
"""

from __future__ import annotations

import os
import platform
import subprocess
import threading
import time
import uuid
from typing import Any, Dict, List, Optional, Set

from norpagent.loops.cancel import cancel_requested
from norpagent.protocols.sandbox import SandboxResult

_IS_WINDOWS = platform.system() == "Windows"


def _robust_decode(data: bytes) -> str:
    if not data:
        return ""
    for enc in ("utf-8", "gbk", "cp936", "latin-1"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def _kill_process_tree(proc: subprocess.Popen) -> None:
    """Kill the entire process tree of a child process (cross-platform, best effort)."""
    try:
        if _IS_WINDOWS:
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                capture_output=True, timeout=10,
            )
        else:
            import signal

            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass


def _stream_reader(stream: Any, buf: List[bytes], done: threading.Event) -> None:
    """Read child-process output in the background into a byte list (prevents deadlock from a full pipe buffer)."""
    try:
        while True:
            chunk = stream.read(65536)
            if not chunk:
                break
            buf.append(chunk)
    except Exception:
        pass
    finally:
        done.set()


class PooledSandbox:
    """A single sandbox instance in the pool.

    ``close()`` semantics = return to the pool (a broken instance is destroyed instead).
    """

    def __init__(self, provider: "PooledSandboxProvider", sandbox_id: str) -> None:
        self._provider = provider
        self.sandbox_id = sandbox_id
        self._lock = threading.Lock()
        self.in_use = True
        self.owner_task_id = ""
        self.cwd: str = provider.workspace_root or os.getcwd()
        self.env: Optional[Dict[str, str]] = None
        self._broken = False

    # ── Sandbox protocol ─────────────────────────────────

    def run_shell(
        self,
        command: str,
        timeout: float = 60.0,
        cwd: Optional[str] = None,
        env: Optional[Dict[str, str]] = None,
    ) -> SandboxResult:
        with self._lock:
            if self._broken:
                return SandboxResult(
                    stderr="sandbox instance is broken (last command was force-killed on timeout); not reusable",
                    exit_code=-1,
                )
            if cwd:
                self.cwd = cwd
            if env:
                self.env = env

            creationflags = 0
            if _IS_WINDOWS:
                creationflags = subprocess.CREATE_NEW_PROCESS_GROUP | 0x08000000
            try:
                proc = subprocess.Popen(
                    command,
                    shell=True,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    cwd=self.cwd,
                    env=self.env,
                    creationflags=creationflags,
                    start_new_session=not _IS_WINDOWS,
                )
            except OSError as exc:
                return SandboxResult(stderr=f"failed to start command: {exc}", exit_code=-1)

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
                # slice-based waiting: once the Ctrl+C / engine-stop cancel event
                # is set, respond within at most 0.5s and force-kill the process tree.
                # note: a single slice's TimeoutExpired merely means "this slice
                # expired"; only the accumulated wait reaching timeout is a real timeout.
                cancelled = False
                timed_out = False
                exit_code = 0
                started = time.monotonic()
                while True:
                    if cancel_requested():
                        _kill_process_tree(proc)
                        self._broken = True
                        cancelled = True
                        exit_code = -1
                        break
                    remaining = timeout - (time.monotonic() - started)
                    if remaining <= 0:
                        timed_out = True
                        # ★ timeout: force-kill the whole process tree; mark the instance broken so it is never reused
                        _kill_process_tree(proc)
                        self._broken = True
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
                # the process is dead; reader threads exit naturally; brief wait for cleanup
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
                stderr = stderr or f"command timed out ({timeout}s), process tree force-killed"
            elif exit_code != 0 and not stderr:
                stderr = f"command exit code {exit_code}"
            return SandboxResult(
                stdout=stdout, stderr=stderr,
                exit_code=exit_code, timed_out=timed_out,
            )

    def run_python(
        self,
        code: str,
        tool_dispatch: Any,
        timeout: float = 60.0,
    ) -> SandboxResult:
        """Isolated PTC code execution (same isolator as the subprocess sandbox).

        Note: code execution uses "a separate child process per call" semantics;
        it does not occupy a pooled instance or reuse its cwd/env state — isolation
        strength for code execution takes priority over terminal session continuity.
        """
        from norpagent.builtin.sandboxes.isolated_python import (
            IsolatedPythonRunner,
        )

        return IsolatedPythonRunner().execute(code, tool_dispatch, timeout)

    def close(self) -> None:
        """Return the sandbox to the pool (a broken instance is destroyed instead)."""
        if self._broken:
            self._provider.discard(self)
            return
        self._provider.release(self)

    def destroy(self) -> None:
        """Destroy immediately (used when the pool is closed)."""
        self._broken = True
        self._provider.discard(self)


class PooledSandboxProvider:
    """Sandbox pool provider: manages borrowing / returning / reclaiming instances."""

    kind = "pooled"

    def __init__(
        self,
        max_sandboxes: int = 8,
        workspace_root: Optional[str] = None,
        acquire_timeout: float = 30.0,
    ) -> None:
        self.max_sandboxes = max(1, int(max_sandboxes))
        self.workspace_root = (
            os.path.abspath(workspace_root) if workspace_root else None
        )
        self.acquire_timeout = float(acquire_timeout)
        self._cond = threading.Condition(threading.Lock())
        self._available: List[PooledSandbox] = []
        self._all: Set[PooledSandbox] = set()

    # ── SandboxProvider protocol ─────────────────────────

    def create(self) -> PooledSandbox:
        """Borrow a sandbox; waits acquire_timeout seconds when nothing is free and the cap is reached."""
        with self._cond:
            deadline = time.monotonic() + self.acquire_timeout
            while not self._available and len(self._all) >= self.max_sandboxes:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise RuntimeError(
                        f"sandbox pool is full (capacity {self.max_sandboxes}); "
                        f"no free instance after waiting {self.acquire_timeout}s"
                    )
                self._cond.wait(remaining)
            if self._available:
                sb = self._available.pop()
                sb.in_use = True
                return sb
            sb = PooledSandbox(self, f"sb_{uuid.uuid4().hex[:8]}")
            self._all.add(sb)
            sb.in_use = True
            return sb

    # ── pool management ─────────────────────────────────

    def release(self, sandbox: PooledSandbox) -> None:
        """Return a sandbox (free instances are reused)."""
        with self._cond:
            if sandbox in self._all:
                sandbox.in_use = False
                sandbox.owner_task_id = ""
                self._available.append(sandbox)
                self._cond.notify_all()

    def discard(self, sandbox: PooledSandbox) -> None:
        """Remove a sandbox from the pool (broken instances)."""
        with self._cond:
            self._all.discard(sandbox)
            if sandbox in self._available:
                self._available.remove(sandbox)

    def kill_task(self, owner_task_id: str) -> int:
        """Force-remove sandboxes occupied by the given task (lifecycle management / cancellation semantics).

        Consistent with the existing application's kill_task_sandbox: terminated
        instances are not returned; the next create() builds a brand-new instance,
        avoiding reuse of empty shells.
        """
        removed = 0
        with self._cond:
            for sb in list(self._all):
                if sb.owner_task_id == owner_task_id and sb.in_use:
                    self._all.discard(sb)
                    removed += 1
        return removed

    def close_all(self) -> None:
        """Destroy all sandboxes (called at runtime shutdown / process exit)."""
        with self._cond:
            for sb in list(self._all):
                self._all.discard(sb)
            self._available.clear()

    def stats(self) -> Dict[str, Any]:
        with self._cond:
            in_use = sum(1 for s in self._all if s.in_use)
            return {
                "capacity": self.max_sandboxes,
                "created": len(self._all),
                "in_use": in_use,
                "available": len(self._available),
            }
