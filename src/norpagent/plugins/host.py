# Copyright (c) 2026 xingluosama121, MIT Licensed
"""Plugin host child process (P4 process-level plugin isolation, zero third-party dependencies).

Core goal: plugins that opt into process isolation are **never mounted into the
main process**.

Architecture::

    main process (norpagent.plugins.isolation)  —— JSON-lines protocol (stdin/stdout) ——>  this child process
      (RPC client, only keeps metadata)                                               (actually loads and runs plugins)

Protocol (one JSON object per line):
    request {id, op, ...}  →  response {id, ok, result|error}
    op ∈ {load, call_tool, fire_hook, set_context, shutdown}

Isolation guarantees:
    - plugin module objects exist only in the child process; the main process
      cannot be directly accessed or modified by plugins;
    - a plugin crash / infinite loop / memory leak only affects the child process;
      the main process can kill and restart it;
    - plugin import restrictions keep applying inside the child process (defense in depth).

Entry: ``python -m norpagent.plugins.host`` (host-side client in isolation).
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
import traceback
from typing import Any, Dict, List, Optional

from norpagent.plugins.loader import (
    ALWAYS_BLOCKED,
    DANGEROUS_IMPORTS_FOR_BLOCK,
    HOOK_NAMES,
    PLUGIN_MODULE_PREFIX,
    PluginContext,
    _ImportBlocker,
    _loading_plugin,
)

# protocol operations
OP_LOAD = "load"
OP_CALL_TOOL = "call_tool"
OP_FIRE_HOOK = "fire_hook"
OP_SET_CONTEXT = "set_context"
OP_SHUTDOWN = "shutdown"


def _safe_json(obj: Any) -> Any:
    """Convert any return value into a JSON-serializable object."""
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


class PluginHostProcess:
    """Plugin host running in the child process.

    Responsibilities: load plugin modules, execute tools, fire hooks.
    The main process interacts with this class over JSON-lines stdin/stdout.
    """

    def __init__(self) -> None:
        self._modules: Dict[str, Any] = {}          # plugin_name -> module
        self._contexts: Dict[str, PluginContext] = {}
        self._blocker: Optional[_ImportBlocker] = None
        self._import_restrict = "off"

    # ── main loop ────────────────────────────────────────

    def serve(self) -> None:
        """Read requests line by line from stdin and process them until shutdown or stdin closes."""
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            try:
                req = json.loads(line)
            except json.JSONDecodeError as exc:
                self._reply({"id": None, "ok": False, "error": f"bad request: {exc}"})
                continue
            resp = self.handle(req)
            self._reply(resp)
            if req.get("op") == OP_SHUTDOWN:
                return

    @staticmethod
    def _reply(resp: dict) -> None:
        try:
            sys.stdout.write(json.dumps(resp, ensure_ascii=False) + "\n")
            sys.stdout.flush()
        except Exception:
            pass

    # ── request dispatch ─────────────────────────────────

    def handle(self, req: dict) -> dict:
        req_id = req.get("id")
        op = req.get("op", "")
        try:
            if op == OP_LOAD:
                return {"id": req_id, "ok": True, "result": self._do_load(req)}
            if op == OP_CALL_TOOL:
                return {"id": req_id, "ok": True, "result": self._do_call_tool(req)}
            if op == OP_FIRE_HOOK:
                return {"id": req_id, "ok": True, "result": self._do_fire_hook(req)}
            if op == OP_SET_CONTEXT:
                self._do_set_context(req)
                return {"id": req_id, "ok": True, "result": None}
            if op == OP_SHUTDOWN:
                return {"id": req_id, "ok": True, "result": None}
            return {"id": req_id, "ok": False, "error": f"unknown op: {op}"}
        except Exception as exc:  # noqa: BLE001 — any error is relayed back; never kill the host
            return {"id": req_id, "ok": False,
                    "error": f"{exc}\n{traceback.format_exc(limit=5)}"}

    # ── security config (import restrictions that keep applying in the child) ──

    def _apply_security(self, req: dict) -> None:
        sec = req.get("security_config") or {}
        self._import_restrict = sec.get("import_restrict", "off")
        if self._blocker is not None:
            self._blocker.unregister()
            self._blocker = None
        if self._import_restrict in ("safe", "strict"):
            self._blocker = _ImportBlocker(
                set(DANGEROUS_IMPORTS_FOR_BLOCK) | set(ALWAYS_BLOCKED),
                strict=(self._import_restrict == "strict"),
            )
            self._blocker.register()

    # ── operation implementations ────────────────────────

    def _do_load(self, req: dict) -> dict:
        """Load a plugin module in the child process; returns the interface description."""
        plugin_name = req.get("plugin_name", "")
        path = req.get("path", "")
        self._apply_security(req)

        if not path or not os.path.isfile(path):
            raise RuntimeError(f"plugin file does not exist: {path}")

        mod_name = f"{PLUGIN_MODULE_PREFIX}{plugin_name}"
        spec = importlib.util.spec_from_file_location(mod_name, path)
        if spec is None or spec.loader is None:
            raise RuntimeError(f"cannot create a module spec for {path}")

        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module

        _loading_plugin.active = True
        try:
            spec.loader.exec_module(module)
        except ImportError as exc:
            raise RuntimeError(f"import blocked: {exc}") from exc
        finally:
            _loading_plugin.active = False

        self._modules[plugin_name] = module

        name = plugin_name
        header_name = getattr(module, "PLUGIN_NAME", None)
        if isinstance(header_name, str) and header_name.strip():
            name = header_name.strip()

        # header-name alias: the main process may locate via PLUGIN_NAME for RPC
        if name != plugin_name:
            self._modules[name] = module

        publisher = getattr(module, "PLUGIN_PUBLISHER", None)
        version = getattr(module, "PLUGIN_VERSION", None)
        description = getattr(module, "PLUGIN_DESCRIPTION", None)

        tools = getattr(module, "TOOLS", None)
        if not isinstance(tools, list):
            tools = []

        hook_names = [
            h for h in HOOK_NAMES if callable(getattr(module, h, None))
        ]
        has_execute = callable(getattr(module, "execute", None))

        # tool approval hints (APPROVAL_HINTS)
        approval_hints: Dict[str, dict] = {}
        raw_hints = getattr(module, "APPROVAL_HINTS", None)
        if isinstance(raw_hints, dict):
            for tname, hint in raw_hints.items():
                if not isinstance(tname, str):
                    continue
                if isinstance(hint, str):
                    approval_hints[tname] = {"approval": hint}
                elif isinstance(hint, dict):
                    approval_hints[tname] = {
                        "approval": str(hint.get("approval", "plugin")),
                        "risk": str(hint.get("risk", "")),
                    }

        # pre-create the context (storage persists inside the child process)
        ctx = self._make_context(plugin_name, req)
        self._contexts.setdefault(plugin_name, ctx)
        if name != plugin_name:
            self._contexts.setdefault(name, ctx)

        return {
            "name": name,
            "tools": _safe_json(tools),
            "hook_names": hook_names,
            "has_execute": has_execute,
            "publisher": (publisher if isinstance(publisher, str) else ""),
            "version": (version if isinstance(version, str) else ""),
            "description": (description if isinstance(description, str) else ""),
            "approval_hints": _safe_json(approval_hints),
        }

    def _make_context(self, plugin_name: str, req: dict) -> PluginContext:
        c = req.get("context") or {}
        return PluginContext(
            plugin_name=plugin_name,
            project_root=str(c.get("project_root", "")),
            app_dir=str(c.get("app_dir", "")),
            config=(c.get("config") or {}),
        )

    def _sync_context(self, plugin_name: str, req: dict) -> PluginContext:
        ctx = self._contexts.get(plugin_name)
        if ctx is None:
            ctx = self._make_context(plugin_name, req)
            self._contexts[plugin_name] = ctx
        c = req.get("context") or {}
        if c.get("project_root"):
            ctx.project_root = str(c["project_root"])
        if c.get("app_dir"):
            ctx.app_dir = str(c["app_dir"])
        if c.get("config"):
            ctx.config = c["config"]
        ctx.current_step = c.get("current_step", ctx.current_step)
        ctx.total_usage = c.get("total_usage", ctx.total_usage)
        return ctx

    def _do_call_tool(self, req: dict) -> dict:
        plugin_name = req.get("plugin", "")
        module = self._modules.get(plugin_name)
        if module is None:
            raise RuntimeError(f"plugin not loaded: {plugin_name}")
        execute_fn = getattr(module, "execute", None)
        if not callable(execute_fn):
            raise RuntimeError(f"plugin {plugin_name} has no execute() function")

        tool = req.get("tool", "")
        args = req.get("args") or {}
        ctx = self._sync_context(plugin_name, req)
        try:
            output = execute_fn(tool, args, ctx)
        except Exception:  # noqa: BLE001 — fallback inside the child; errors are relayed, never kill the host
            return {"output": f"Plugin execution failed:\n{traceback.format_exc()}"}
        return {"output": _safe_json(output)}

    def _do_fire_hook(self, req: dict) -> dict:
        plugin_name = req.get("plugin", "")
        module = self._modules.get(plugin_name)
        if module is None:
            raise RuntimeError(f"plugin not loaded: {plugin_name}")
        hook = req.get("hook", "")
        fn = getattr(module, hook, None)
        if not callable(fn):
            return {"result": None}

        args = req.get("args") or []
        if not isinstance(args, (list, tuple)):
            args = [args]
        args = list(args)
        ctx = self._sync_context(plugin_name, req)
        try:
            result = fn(*args, ctx)
        except Exception as exc:  # noqa: BLE001
            return {"result": None, "error": str(exc)}
        return {"result": _safe_json(result)}

    def _do_set_context(self, req: dict) -> None:
        for plugin_name in list(self._contexts.keys()):
            self._sync_context(plugin_name, req)


def main() -> None:
    """Child process entry point (python -m norpagent.plugins.host)."""
    # ★ force UTF-8 on stdin/stdout/stderr: Windows child processes inherit the
    #   GBK locale by default, which would make the parent (utf-8) misread protocol
    #   messages. Unify everything to UTF-8 here.
    import io

    try:
        sys.stdout = io.TextIOWrapper(
            sys.stdout.buffer, encoding="utf-8", errors="replace", newline="\n")
        sys.stderr = io.TextIOWrapper(
            sys.stderr.buffer, encoding="utf-8", errors="replace", newline="\n")
        sys.stdin = io.TextIOWrapper(
            sys.stdin.buffer, encoding="utf-8", errors="replace", newline="\n")
    except Exception:
        pass
    host = PluginHostProcess()
    host.serve()


if __name__ == "__main__":
    main()
