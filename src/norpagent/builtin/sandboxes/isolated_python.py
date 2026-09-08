# Copyright (c) 2026 xingluosama121, MIT Licensed
"""PTC isolated executor: model-generated Python code runs in a child process (zero third-party dependencies).

Threat model: model-generated code is untrusted (prompt injection may induce
escape attempts). Isolation design (defense in depth, four layers):

1. **AST static precheck** (host side, primary boundary): rejects import /
   double-underscore attribute access / dangerous builtin names / magic
   subscripts (``d["__globals__"]``) — blocking the classic escape entries;
2. **restricted builtins** (inside the child): no import/open/eval/exec/type/repr etc.;
3. **clean function namespace**: ``call_tool`` exposed to user code and its
   referenced helpers are all built by "compiling into an independent globals" —
   ``fn.__globals__`` cannot climb back into the module namespace containing sys/os;
4. **process-level isolation**: the code runs in a separate child process; the
   host serves its tool-call requests over a stdin/stdout length-prefixed
   protocol; timeout force-kills the process tree; output length is capped.

Protocol (host <-> child, text lines):
    child -> host:  JSON line {"op":"call_tool","name":..,"args":{..}}
                    or {"op":"done","output":..,"error":..}
    host   -> child:  "OK <n>" newline + output of n chars + newline
                      "ERR <n>" newline + error of n chars + newline

Note: this executor is "tool-level" isolation. For OS-level isolation (containers /
VMs), replace the sandbox component in the preset; the PTC tool signature stays
the same.
"""

from __future__ import annotations

import ast
import json
import os
import platform
import queue
import subprocess
import sys
import tempfile
import threading
import time
from typing import Any, Callable, Dict, Optional, Tuple

from norpagent.loops.cancel import cancel_requested
from norpagent.protocols.sandbox import SandboxResult

_IS_WINDOWS = platform.system() == "Windows"

# ── restricted builtins allowlist for user code (no module/IO/code-execution entries) ──

_ALLOWED_BUILTIN_NAMES = (
    "abs", "all", "any", "bool", "dict", "divmod", "enumerate", "filter",
    "float", "format", "frozenset", "int", "isinstance", "len", "list",
    "map", "max", "min", "pow", "print", "range", "reversed", "round",
    "set", "slice", "sorted", "str", "sum", "tuple", "zip",
    # exception types: allow try/except to catch tool-call failures
    "Exception", "RuntimeError", "ValueError", "TypeError",
    "KeyError", "IndexError", "AttributeError", "StopIteration",
    "ZeroDivisionError", "OverflowError", "LookupError",
)

# static precheck: forbidden names (in any context)
_FORBIDDEN_NAMES = {
    "__import__", "__builtins__", "eval", "exec", "compile", "open",
    "globals", "locals", "vars", "getattr", "setattr", "delattr",
    "input", "breakpoint", "memoryview", "type", "super", "object",
    "staticmethod", "classmethod", "property",
}


def check_ptc_source(code: str, max_len: int = 200_000) -> Tuple[bool, str]:
    """AST static precheck of PTC code.

    Returns (allowed or not, rejection reason). Empty code / overlong code / syntax
    errors are all rejected.
    """
    if not code or not isinstance(code, str):
        return False, "code is empty"
    if len(code) > max_len:
        return False, f"code too long ({len(code)} chars, limit {max_len})"
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        return False, f"syntax error: {exc}"

    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            return False, f"import is forbidden in the PTC sandbox (line {node.lineno})"
        if isinstance(node, ast.Name):
            if node.id in _FORBIDDEN_NAMES:
                return False, f"builtin name '{node.id}' is forbidden (line {node.lineno})"
        elif isinstance(node, ast.Attribute):
            if node.attr.startswith("__"):
                return False, (
                    f"double-underscore attribute access is forbidden (line {node.lineno}; "
                    "a sandbox escape entry)"
                )
        elif isinstance(node, ast.Subscript):
            if isinstance(node.slice, ast.Constant) \
                    and isinstance(node.slice.value, str) \
                    and node.slice.value.startswith("__"):
                return False, (
                    f"magic subscript access is forbidden (line {node.lineno}; "
                    "a sandbox escape entry)"
                )
    return True, ""


# ── support function sources (defined host-side; embedded into the wrapper via %r, auto-escaped) ──
# note: the values of these source strings are embedded into the child file via
# repr(); once the file is parsed, the string values are exactly identical to
# these, and are then handed to compile for execution.

_ENC_SRC = """\
def _enc(obj):
    if obj is None:
        return "null"
    if obj is True:
        return "true"
    if obj is False:
        return "false"
    if isinstance(obj, str):
        s = obj
        s = s.replace("\\\\", "\\\\\\\\")
        s = s.replace('"', '\\\\"')
        s = s.replace("\\n", "\\\\n")
        s = s.replace("\\r", "\\\\r")
        s = s.replace("\\t", "\\\\t")
        return '"' + s + '"'
    if isinstance(obj, (int, float, bool)):
        return str(obj)
    if isinstance(obj, dict):
        parts = [_enc(k) + ":" + _enc(v) for k, v in obj.items()]
        return "{" + ",".join(parts) + "}"
    if isinstance(obj, (list, tuple)):
        return "[" + ",".join(_enc(x) for x in obj) + "]"
    return _enc(str(obj))
"""

_WRITE_SRC = """\
def _write(out, obj):
    out.write(_enc(obj) + "\\n")
    out.flush()
"""

_READ_SRC = """\
def _read(inp):
    header = inp.readline()
    if not header:
        raise RuntimeError("host connection closed")
    status, num = header.split(" ", 1)
    n = int(num)
    data = inp.read(n)
    inp.read(1)
    if status == "ERR":
        raise RuntimeError(data)
    return data
"""

_CALLER_SRC = """\
def call_tool(name, **args):
    _write(_OUT, {"op": "call_tool", "name": name, "args": args})
    return _read(_INP)
"""

# child wrapper template: %% is a literal percent; %(...)r is auto-escaped by repr
_WRAPPER_TEMPLATE = """\
# -*- coding: utf-8 -*-
# generated by norpagent.builtin.sandboxes.isolated_python
import contextlib
import io
import sys

# force UTF-8: Windows child processes inherit the GBK locale by default; Chinese protocol messages would be mojibake
sys.stdout = io.TextIOWrapper(
    sys.stdout.buffer, encoding="utf-8", errors="replace", newline="\\n")
sys.stdin = io.TextIOWrapper(
    sys.stdin.buffer, encoding="utf-8", errors="replace", newline="\\n")

_ALLOWED = %(allowed)r


def _build_restricted():
    b = __builtins__
    if isinstance(b, dict):
        return {n: b[n] for n in _ALLOWED if n in b}
    return {n: getattr(b, n) for n in _ALLOWED}


def _mk(src, env):
    # compile the function into an independent globals: fn.__globals__ cannot climb back into this module's namespace
    code = compile(src, "<ptc_support>", "exec")
    g = dict(env)
    g["__builtins__"] = {
        "isinstance": isinstance, "str": str, "int": int, "len": len,
        "RuntimeError": RuntimeError, "ord": ord, "chr": chr,
        "float": float, "bool": bool, "list": list, "dict": dict,
        "Exception": Exception, "KeyError": KeyError, "ValueError": ValueError,
    }
    exec(code, g)
    return g


_ENC_SRC = %(enc_src)r
_enc = _mk(_ENC_SRC, {})["_enc"]

_WRITE_SRC = %(write_src)r
_write = _mk(_WRITE_SRC, {"_enc": _enc})["_write"]

_READ_SRC = %(read_src)r
_read = _mk(_READ_SRC, {})["_read"]

_CALLER_SRC = %(caller_src)r
call_tool = _mk(_CALLER_SRC, {
    "_write": _write, "_read": _read,
    "_OUT": sys.stdout, "_INP": sys.stdin,
})["call_tool"]


class _BlockAllImports(object):
    # reject every import inside user code directly (defense-in-depth layer 2)
    def find_spec(self, fullname, path=None, target=None):
        raise ImportError("import is forbidden in the PTC sandbox: " + str(fullname))


def _main():
    sys.meta_path.insert(0, _BlockAllImports())
    buffer = io.StringIO()
    globs = {
        "__builtins__": _build_restricted(),
        "call_tool": call_tool,
    }
    try:
        with contextlib.redirect_stdout(buffer):
            exec(compile(%(user_code)r, "<run_python>", "exec"), globs)
        _write(sys.stdout, {
            "op": "done",
            "output": buffer.getvalue(),
            "error": None,
        })
    except BaseException as exc:
        try:
            _write(sys.stdout, {
                "op": "done",
                "output": buffer.getvalue(),
                "error": "%%s: %%s" %% (type(exc).__name__, exc),
            })
        except BaseException:
            pass


if __name__ == "__main__":
    _main()
"""


def _render_wrapper(user_code: str) -> str:
    return _WRAPPER_TEMPLATE % {
        "allowed": list(_ALLOWED_BUILTIN_NAMES),
        "user_code": user_code,
        "enc_src": _ENC_SRC,
        "write_src": _WRITE_SRC,
        "read_src": _READ_SRC,
        "caller_src": _CALLER_SRC,
    }


class IsolatedPythonRunner:
    """Host-side PTC executor: spawns the child process, runs the code, serves tool RPC."""

    def __init__(
        self,
        max_output: int = 512 * 1024,
        max_tool_result: int = 128 * 1024,
    ) -> None:
        self.max_output = int(max_output)
        self.max_tool_result = int(max_tool_result)

    def execute(
        self,
        code: str,
        tool_dispatch: Callable[[str, Dict[str, Any]], str],
        timeout: float = 60.0,
    ) -> SandboxResult:
        """Execute the code. ``tool_dispatch(name, args) -> str`` is the host-side
        tool-call service: returns the output string; on exception the error is
        relayed back to the child process."""
        ok, reason = check_ptc_source(code)
        if not ok:
            return SandboxResult(stderr=reason, exit_code=-1)

        fd, path = tempfile.mkstemp(suffix=".py", prefix="norpagent_ptc_")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(_render_wrapper(code))
            return self._run_child(path, tool_dispatch, timeout)
        finally:
            try:
                os.unlink(path)
            except OSError:
                pass

    def _run_child(self, path: str, tool_dispatch, timeout: float) -> SandboxResult:
        try:
            proc = subprocess.Popen(
                [sys.executable, path],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                bufsize=0,
                cwd=os.getcwd(),
            )
        except OSError as exc:
            return SandboxResult(stderr=f"failed to start the PTC child process: {exc}", exit_code=-1)

        # binary pipes + manual text wrapping: newline="\n" disables os.linesep
        # translation, keeping character counts of the length-prefixed protocol
        # exact on Windows too.
        import io as _io

        try:
            proc.stdin = _io.TextIOWrapper(
                proc.stdin, encoding="utf-8", errors="replace",
                newline="\n", write_through=True,
            )
            proc.stdout = _io.TextIOWrapper(
                proc.stdout, encoding="utf-8", errors="replace",
                newline="\n",
            )
            proc.stderr = _io.TextIOWrapper(
                proc.stderr, encoding="utf-8", errors="replace",
                newline="",
            )
        except Exception:
            pass

        lines: "queue.Queue[Optional[str]]" = queue.Queue()
        stderr_chunks: list = []

        def _read_stdout() -> None:
            try:
                assert proc.stdout is not None
                for line in proc.stdout:
                    lines.put(line)
            except Exception:
                pass
            finally:
                lines.put(None)  # EOF sentinel

        def _drain_stderr() -> None:
            try:
                assert proc.stderr is not None
                for chunk in proc.stderr:
                    stderr_chunks.append(chunk)
            except Exception:
                pass

        reader = threading.Thread(target=_read_stdout, daemon=True)
        err_reader = threading.Thread(target=_drain_stderr, daemon=True)
        reader.start()
        err_reader.start()

        deadline = time.monotonic() + max(1.0, float(timeout))
        final_output = ""
        final_error = ""
        timed_out = False
        cancelled = False
        exit_code = 0
        try:
            while True:
                # Ctrl+C / engine stop: cancel event set → force-kill the child immediately
                if cancel_requested():
                    cancelled = True
                    _kill_child(proc)
                    break
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    timed_out = True
                    _kill_child(proc)
                    break
                try:
                    # slice-based waiting: cancellation requests are answered within at most 0.5s
                    line = lines.get(timeout=min(remaining, 0.5))
                except queue.Empty:
                    continue
                if line is None:  # child exited (stdout EOF)
                    break
                line = line.strip()
                if not line:
                    continue
                try:
                    msg = json.loads(line)
                except json.JSONDecodeError:
                    continue  # tolerate protocol noise (user code cannot write outside protocol stdout)
                op = msg.get("op")
                if op == "call_tool":
                    name = msg.get("name", "")
                    args = msg.get("args") or {}
                    try:
                        if not isinstance(args, dict):
                            raise TypeError("tool arguments must be a dict")
                        output = tool_dispatch(str(name), args)
                        if not isinstance(output, str):
                            output = str(output)
                        output = output[: self.max_tool_result]
                        self._reply(proc, "OK", output)
                    except Exception as exc:  # noqa: BLE001
                        self._reply(
                            proc, "ERR",
                            f"{type(exc).__name__}: {exc}"[: self.max_tool_result],
                        )
                elif op == "done":
                    final_output = str(msg.get("output") or "")[: self.max_output]
                    final_error = str(msg.get("error") or "")
                    break
        finally:
            if proc.poll() is None:
                try:
                    _kill_child(proc)
                except Exception:
                    pass
            try:
                proc.stdout.close()
                proc.stdin.close()
                proc.stderr.close()
            except Exception:
                pass

        if cancelled:
            stderr = "".join(stderr_chunks)[-2000:].strip()
            return SandboxResult(
                stdout=final_output,
                stderr=stderr or "task cancelled (Ctrl+C); PTC child process terminated",
                exit_code=-1,
            )
        if timed_out:
            stderr = "".join(stderr_chunks)[-2000:].strip()
            return SandboxResult(
                stdout=final_output,
                stderr=stderr or f"PTC code execution timed out ({timeout}s); process force-killed",
                exit_code=-1,
                timed_out=True,
            )
        try:
            # bounded wait: when the child is in an unkillable state (e.g. D state),
            # the worker thread must never block forever
            exit_code = proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            _kill_child(proc)
            exit_code = -1
        stderr = "".join(stderr_chunks).strip()
        if final_error:
            return SandboxResult(
                stdout=final_output,
                stderr=final_error,
                exit_code=-1,
            )
        if exit_code != 0 and not stderr:
            stderr = f"PTC child process exited abnormally (exit code {exit_code})"
        return SandboxResult(
            stdout=final_output,
            stderr=stderr,
            exit_code=exit_code,
        )

    @staticmethod
    def _reply(proc: subprocess.Popen, status: str, text: str) -> None:
        if proc.stdin is None or proc.poll() is not None:
            raise RuntimeError("PTC child process has exited")
        proc.stdin.write(f"{status} {len(text)}\n{text}\n")
        proc.stdin.flush()


def _kill_child(proc: subprocess.Popen) -> None:
    """Force-kill the entire process tree of the PTC child process."""
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
