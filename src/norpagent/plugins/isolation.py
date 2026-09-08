# Copyright (c) 2026 xingluosama121, MIT Licensed
"""Host-side plugin client (P4 process-level plugin isolation, zero third-party dependencies).

    from norpagent.plugins.isolation import ProcessIsolationManager

    iso = ProcessIsolationManager(config={"plugin_security_import_restrict": "safe"})
    meta = iso.load("my_plugin", "/path/plugin.py", ctx_dict, security_config)
    iso.call_tool("my_plugin", "tool_x", {"a": 1}, ctx_dict)
    iso.shutdown()

Features:

- **one child process hosts multiple plugins**: JSON-lines protocol RPC (stdin/stdout);
- **crash self-healing**: when a request finds the child process dead → auto-restart,
  reload all plugins → retry once;
- **hook timeout**: fire_hook executes in a daemon thread with a bounded wait; on
  timeout it gives up (zombie threads are reaped at shutdown); plugin hooks never
  stall the main loop;
- **tool errors never bubble up**: remote exceptions become failed ToolResults,
  consistent with in-process plugins.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
from typing import Any, Callable, Dict, List, Optional

# max wait time for a single hook invocation (consistent with the existing application's HOOK_TIMEOUT)
HOOK_TIMEOUT = 5.0
# default RPC timeout
DEFAULT_RPC_TIMEOUT = 120.0
# child process idle timeout (host-side self-exit, avoiding zombie hosts)
HOST_IDLE_TIMEOUT = 600.0

# background threads abandoned due to hook timeouts (reaped at shutdown)
_zombie_threads: List[threading.Thread] = []
_zombie_lock = threading.Lock()


def _safe_json(obj: Any) -> Any:
    if obj is None or isinstance(obj, (str, int, float, bool)):
        return obj
    if isinstance(obj, (dict, list, tuple)):
        try:
            if isinstance(obj, tuple):
                obj = list(obj)
            json.dumps(obj)
            return obj
        except (TypeError, ValueError):
            pass
    try:
        return str(obj)
    except Exception:
        return f"<unserializable {type(obj).__name__}>"


def reap_zombies() -> None:
    """Reap finished timeout-hook threads (called at framework shutdown)."""
    with _zombie_lock:
        still: List[threading.Thread] = []
        for t in _zombie_threads:
            if t.is_alive():
                t.join(0.1)
                still.append(t)
        _zombie_threads[:] = still


class ProcessPluginHost:
    """RPC client of a single plugin-host child process."""

    def __init__(
        self,
        security_config: Optional[dict] = None,
        cwd: Optional[str] = None,
        rpc_timeout: float = DEFAULT_RPC_TIMEOUT,
    ) -> None:
        self.security_config = security_config or {}
        self.cwd = cwd or os.getcwd()
        self.rpc_timeout = rpc_timeout
        self._proc: Optional[subprocess.Popen] = None
        self._lock = threading.Lock()
        self._next_id = 0
        self._pending: Dict[int, Dict[str, Any]] = {}
        self._reader: Optional[threading.Thread] = None
        self._err_reader: Optional[threading.Thread] = None
        self._alive = False
        self._loaded: Dict[str, dict] = {}  # plugin_name -> load metadata

    # ── lifecycle ────────────────────────────────────────

    def start(self) -> bool:
        with self._lock:
            if self._alive:
                return True
            try:
                self._proc = subprocess.Popen(
                    self._build_command(),
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    cwd=self.cwd,
                    bufsize=0,
                )
            except Exception:
                self._proc = None
                return False
            # binary pipes + manual text wrapping: newline="\n" disables os.linesep translation
            import io as _io

            try:
                self._proc.stdin = _io.TextIOWrapper(
                    self._proc.stdin, encoding="utf-8", errors="replace",
                    newline="\n", write_through=True,
                )
                self._proc.stdout = _io.TextIOWrapper(
                    self._proc.stdout, encoding="utf-8", errors="replace",
                    newline="\n",
                )
                self._proc.stderr = _io.TextIOWrapper(
                    self._proc.stderr, encoding="utf-8", errors="replace",
                    newline="",
                )
            except Exception:
                pass
            self._alive = True
            self._reader = threading.Thread(target=self._read_loop, daemon=True)
            self._reader.start()
            self._err_reader = threading.Thread(target=self._drain_stderr, daemon=True)
            self._err_reader.start()
            return True

    @staticmethod
    def _build_command() -> List[str]:
        """Build the child process launch command: python -m norpagent.plugins.host.

        The plugin-host child process must be able to import norpagent (same
        interpreter environment as the main process).
        """
        return [sys.executable, "-m", "norpagent.plugins.host"]

    def _read_loop(self) -> None:
        try:
            assert self._proc and self._proc.stdout
            for line in self._proc.stdout:
                line = line.strip()
                if not line:
                    continue
                try:
                    resp = json.loads(line)
                except json.JSONDecodeError:
                    continue
                rid = resp.get("id")
                with self._lock:
                    entry = self._pending.get(rid)
                if entry is not None:
                    entry["resp"] = resp
                    entry["event"].set()
        except Exception:
            pass

    def _drain_stderr(self) -> None:
        try:
            if self._proc and self._proc.stderr:
                for _ in self._proc.stderr:
                    pass
        except Exception:
            pass

    # ── requests ─────────────────────────────────────────

    def request(self, req: dict, timeout: Optional[float] = None) -> Any:
        """Send a request and wait synchronously for the response; returns result (errors raise RuntimeError)."""
        if not self._alive or self._proc is None or self._proc.stdin is None:
            raise RuntimeError("plugin host process is not running")
        with self._lock:
            self._next_id += 1
            rid = self._next_id
            req = dict(req)
            req["id"] = rid
            event = threading.Event()
            self._pending[rid] = {"event": event, "resp": None}
            try:
                self._proc.stdin.write(json.dumps(req, ensure_ascii=False) + "\n")
                self._proc.stdin.flush()
            except Exception as exc:
                self._pending.pop(rid, None)
                raise RuntimeError(f"failed to write to plugin host process: {exc}") from exc

        if not event.wait(timeout if timeout is not None else self.rpc_timeout):
            with self._lock:
                self._pending.pop(rid, None)
            raise TimeoutError(
                f"plugin host process response timed out ({timeout or self.rpc_timeout}s)"
            )
        with self._lock:
            entry = self._pending.pop(rid, None)
        resp = entry["resp"] if entry else None
        if resp is None:
            raise RuntimeError("plugin host process returned an empty response")
        if not resp.get("ok", False):
            raise RuntimeError(resp.get("error", "plugin host process returned an error"))
        return resp.get("result")

    def is_alive(self) -> bool:
        with self._lock:
            if not self._alive or self._proc is None:
                return False
            return self._proc.poll() is None

    def shutdown(self) -> None:
        """Close the child process (send a shutdown request first; force-kill on timeout)."""
        with self._lock:
            if not self._alive or self._proc is None:
                self._alive = False
                return
            try:
                self._proc.stdin.write(
                    json.dumps({"id": -1, "op": "shutdown"}) + "\n"
                )
                self._proc.stdin.flush()
            except Exception:
                pass
            try:
                self._proc.stdin.close()
            except Exception:
                pass
            try:
                self._proc.wait(timeout=3)
            except Exception:
                self._kill()
            self._alive = False
            self._proc = None

    def _kill(self) -> None:
        if self._proc is not None:
            try:
                self._proc.kill()
            except Exception:
                pass
        self._alive = False
        self._proc = None


class ProcessIsolationManager:
    """Process-level plugin isolation manager: one host child process + auto reload."""

    def __init__(
        self,
        security_config: Optional[dict] = None,
        cwd: Optional[str] = None,
        rpc_timeout: float = DEFAULT_RPC_TIMEOUT,
    ) -> None:
        self.security_config = dict(security_config or {})
        self.cwd = cwd or os.getcwd()
        self.rpc_timeout = rpc_timeout
        self._host = ProcessPluginHost(
            security_config=self.security_config,
            cwd=self.cwd,
            rpc_timeout=rpc_timeout,
        )
        self._plugins: Dict[str, dict] = {}   # plugin_name -> {path, context}
        self._lock = threading.Lock()

    # ── plugin loading ───────────────────────────────────

    def load(
        self,
        plugin_name: str,
        path: str,
        context: Optional[dict] = None,
        security_config: Optional[dict] = None,
    ) -> dict:
        """Load a plugin in the child process; returns interface metadata (name/tools/hook_names...)."""
        req = {
            "op": "load",
            "plugin_name": plugin_name,
            "path": path,
            "context": context or {},
            "security_config": security_config or self.security_config,
        }
        result = self._request_with_respawn(req)
        with self._lock:
            self._plugins[plugin_name] = {"path": path, "context": context or {}}
        return result

    def set_context(self, context: dict) -> None:
        """Refresh the read-only context fields shared by all plugins."""
        try:
            self._request_with_respawn({"op": "set_context", "context": context})
        except RuntimeError:
            pass

    def context_for(self, plugin_name: str, context: Optional[dict] = None) -> dict:
        """Merge the plugin base context with this task's context."""
        base = self._plugins.get(plugin_name, {}).get("context", {}) or {}
        merged = dict(base)
        if context:
            merged.update(context)
        merged["plugin_name"] = plugin_name
        return merged

    # ── RPC ─────────────────────────────────────────────

    def call_tool(
        self,
        plugin_name: str,
        tool: str,
        args: dict,
        context: Optional[dict] = None,
        timeout: Optional[float] = None,
    ) -> Any:
        """Execute a plugin tool and return output (host errors raise RuntimeError)."""
        result = self._request_with_respawn({
            "op": "call_tool",
            "plugin": plugin_name,
            "tool": tool,
            "args": _safe_json(args) if isinstance(args, dict) else args,
            "context": self.context_for(plugin_name, context),
        }, timeout=timeout)
        if isinstance(result, dict) and "output" in result:
            return result["output"]
        return result

    def fire_hook(
        self,
        plugin_name: str,
        hook: str,
        args: List[Any],
        context: Optional[dict] = None,
        hook_timeout: float = HOOK_TIMEOUT,
    ) -> Any:
        """Fire a plugin hook; returns the result (None on timeout abandonment; plugin exceptions relay as None)."""
        box: Dict[str, Any] = {}

        def worker() -> None:
            try:
                box["result"] = self._request_with_respawn({
                    "op": "fire_hook",
                    "plugin": plugin_name,
                    "hook": hook,
                    "args": _safe_json(args),
                    "context": self.context_for(plugin_name, context),
                }, timeout=max(hook_timeout, 1.0))
            except Exception:  # noqa: BLE001
                box["result"] = None

        t = threading.Thread(
            target=worker, daemon=True,
            name=f"norpagent-pluginhook-{plugin_name}-{hook}",
        )
        t.start()
        t.join(hook_timeout)
        if t.is_alive():
            with _zombie_lock:
                _zombie_threads.append(t)
            return None
        result = box.get("result")
        if isinstance(result, dict):
            return result.get("result")
        return result

    def _request_with_respawn(self, req: dict, timeout: Optional[float] = None) -> Any:
        """Request + crash self-healing: restart the child on death, reload all plugins, retry once."""
        if not self._host.is_alive():
            self._respawn()
        else:
            self._host.start()
        try:
            return self._host.request(req, timeout=timeout)
        except (RuntimeError, TimeoutError, OSError, ValueError):
            # child process died or pipe broken: restart and retry once
            if not self._host.is_alive():
                self._respawn()
                return self._host.request(req, timeout=timeout)
            raise

    def _respawn(self) -> None:
        """Restart the child process and reload all plugins."""
        self._host._kill()
        if not self._host.start():
            raise RuntimeError("plugin host child process failed to start")
        with self._lock:
            plugins = {
                name: dict(meta) for name, meta in self._plugins.items()
            }
        for name, meta in plugins.items():
            self._host.request({
                "op": "load",
                "plugin_name": name,
                "path": meta["path"],
                "context": meta["context"],
                "security_config": self.security_config,
            })

    def is_alive(self) -> bool:
        return self._host.is_alive()

    def status(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "alive": self._host.is_alive(),
                "plugins": sorted(self._plugins),
            }

    def shutdown(self) -> None:
        self._host.shutdown()
        reap_zombies()
