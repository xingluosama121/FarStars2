# Copyright (c) 2026 xingluosama121, MIT Licensed
"""Human rescue: manually operate every registered tool when the model is dead.

This module is the framework-dependent half of the rescue story. The crash-rescue
CLI (:mod:`norpagent.rescue`) keeps its snapshot commands pure-standard-library;
the *human takeover* commands (``tools`` / ``tool-call`` / ``manual`` / ``serve``)
lazily import this module and build a real tool environment.

Scenario: the model provider is down (invalid API key / unreachable endpoint /
broken model output) but the operator still needs the agent's hands — read a
workspace file, run a build, inspect the context store, submit a task. Instead of
waiting for the model, a human drives the same tools through the exact same
:class:`~norpagent.kernel.context.RunContext` the agent kernel would construct,
so manual calls behave identically to model-issued calls and write to the same
state (workspace files / context store / scheduler queue).

Custom tools are fully supported: tools registered in the registry, tools
mounted through the ``tools`` slot (names or module addresses) and tools
provided by external plugins are all manually callable — see
:class:`RescueToolEnvironment` parameters ``extra_tools`` / ``tools`` /
``plugin_dirs`` and the ``--tools`` / ``--plugin-dirs`` CLI options.

Entry points::

    norpagent-rescue tools                              # tool inventory
    norpagent-rescue tool-call echo --args '{"text":"ping"}'
    norpagent-rescue tool-call --tools mypkg.mytools:create ...
    norpagent-rescue manual                             # interactive console
    norpagent-rescue serve --port 8799                  # HTTP API + operator page
    norpagent-rescue serve --plugin-dirs ./my_plugins   # + external plugins

Programmatic::

    from norpagent.rescue_api import RescueToolEnvironment, RescueToolAPI

    env = RescueToolEnvironment(workspace_root=".")
    print(env.call_tool("echo", {"text": "ping"}))
    env2 = RescueToolEnvironment(extra_tools={"my_tool": MyTool()},
                                 plugin_dirs=["./my_plugins"])
    api = RescueToolAPI(env2, port=0, token="secret")
    port = api.start()        # returns the actual port (0 = ephemeral)
    ...                       # GET /api/tools  POST /api/tools/<name>/call
    api.shutdown()

Isolation and safety:

- no model is involved; plugins are **not** loaded by default (pass
  ``plugin_dirs`` explicitly to load them through the same security pipeline as
  the host application);
- every call runs in a dedicated worker thread with a hard timeout. On timeout the
  caller gives up (daemon orphan thread, the same pattern as the model-call
  timeout in the agent kernel), the cancel event is set so well-behaved tools /
  sandboxes exit early, and the sandbox force-kills its child processes;
- the HTTP server binds 127.0.0.1 by default and supports an optional bearer
  token — this endpoint executes real commands and must never be exposed beyond
  localhost.
"""

from __future__ import annotations

import contextvars
import json
import sys
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from norpagent.builtin import install_defaults
from norpagent.kernel.context import RunContext
from norpagent.kernel.registry import ComponentError, Registry
from norpagent.loops.cancel import _current_cancel  # noqa: F401  # private but same-library
from norpagent.protocols.tool import ToolResult, tool_error

RESCUE_PRESET_NAME = "rescue"
DEFAULT_TOOL_TIMEOUT = 300.0
_MAX_JSON_BODY = 1024 * 1024  # 1 MB per request body

# tool categories for the inventory / operator page
_TOOL_CATEGORIES = (
    ("basic", ("echo", "get_time")),
    ("code", ("run_python",)),
    ("files", ("file_read", "file_write", "file_list", "file_delete", "file_surgeon", "search_in_file")),
    ("shell", ("exec_cmd",)),
    ("web", ("web_search", "web_fetch", "web_extract_links")),
    ("context", ("context_add", "context_search", "context_list", "context_delete")),
    ("project", ("project_status",)),
    ("task", ("task_submit", "task_list", "task_status", "task_cancel")),
)


def _category_of(name: str) -> str:
    for category, names in _TOOL_CATEGORIES:
        if name in names:
            return category
    return "other"


class RescueToolEnvironment:
    """Standalone tool environment for manual rescue calls (human as the model).

    Assembles the full built-in registry (all 22 built-in tools) plus one shared
    sandbox / session manager / scheduler / context store / project manager, and
    optionally any **custom tools** the operator needs:

    - ``extra_tools``: registered directly — a ``{name: tool}`` mapping, a list
      of ``Tool`` instances, or a list of tool names / module addresses
      (``"pkg.mod:attr"``, resolved exactly like the ``tools`` slot of ``np()``);
    - ``tools``: an alias of the ``tools`` slot — names of already-registered
      tools or module addresses, merged into the registry before plugins load;
    - ``plugin_dirs``: external plugin directories, loaded through the same
      security pipeline as the host application (signature -> audit -> import
      restriction -> register), so plugin-registered tools are manually callable
      too.

    ``inventory()`` tags every tool with ``origin`` (builtin / custom / plugin)
    so the operator page can tell apart built-ins from third-party tools.

    Consecutive calls share the environment, so multi-step manual work behaves
    like a real task: ``context_add`` then ``context_search`` finds it,
    ``file_write`` then ``file_read`` reads it, ``task_submit`` lands on the same
    scheduler queue the host application may be draining.
    """

    def __init__(
        self,
        workspace_root: Optional[str] = None,
        sandbox: str = "subprocess",
        session: str = "memory",
        scheduler: str = "persistent",
        scheduler_db: Optional[str] = None,
        context_db: Optional[str] = None,
        with_components: bool = True,
        params: Optional[Dict[str, Any]] = None,
        extra_tools: Any = None,
        tools: Optional[List[str]] = None,
        plugin_dirs: Optional[List[str]] = None,
        plugin_config: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.registry: Registry = Registry()
        install_defaults(self.registry)
        # custom tools: extra_tools first (so "tools" name refs can point at
        # them), then the "tools slot" aliases (names / module addresses)
        self._origin: Dict[str, str] = {}
        if extra_tools:
            self._register_extra_tools(extra_tools)
        if tools:
            self._register_tool_refs(list(tools))
        self._plugin_loader: Any = None
        if plugin_dirs:
            self._load_plugin_dirs(list(plugin_dirs), plugin_config)
        self.sandbox = self.registry.build_sandbox(sandbox)
        self.session_manager = self.registry.build_session(session)
        # default scheduler = persistent: all task_* tools (submit/list/status/
        # cancel) work out of the box and share the main app's queue DB
        # (~/.norpagent/tasks.db), so the operator can inspect the tasks the
        # agent submitted before the model died.
        if scheduler_db and scheduler == "persistent":
            from norpagent.builtin.scheduler.persistent import PersistentTaskScheduler

            self.scheduler = PersistentTaskScheduler(path=scheduler_db)
        else:
            self.scheduler = self.registry.build_scheduler(scheduler)
        # default per-call params (workspace root drives the file-tool path
        # safety boundary; ptc_timeout drives sandboxed run_python execution)
        self.params: Dict[str, Any] = {
            "max_steps": 1,
            "ptc_timeout": 60,
            "task_timeout": 0,
        }
        if workspace_root:
            self.params["workspace_root"] = str(workspace_root)
        if params:
            self.params.update(params)
        self.components: Dict[str, Any] = {}
        if with_components:
            from norpagent.builtin.context.fts5 import FTS5ContextStore
            from norpagent.builtin.projects.basic import BasicProjectManager

            # default path (context_db=None) is ~/.norpagent/context.db — the
            # same store the engine uses, so the operator can inspect what the
            # agent saved; pass an explicit path to isolate.
            self.components["context_store"] = FTS5ContextStore(path=context_db)
            self.components["project_manager"] = BasicProjectManager(
                workspace_root=workspace_root
            )
        self._session: Any = None
        self._session_lock = threading.Lock()
        # abandoned worker threads from hard timeouts (daemon; pruned per call)
        self._orphan_threads: List[threading.Thread] = []
        self._closed = False

    # ── custom tool registration ─────────────────────────

    def _register_tool_refs(self, refs: List[str]) -> None:
        """Register tools by name (already in the registry) or module address.

        Mirrors the ``tools`` slot semantics of ``np(tools=[...])``: strings
        that look like an address (``pkg.mod[:attr]``) are resolved through
        ``norpagent.arch.address.resolve_address``; anything else is treated as
        an already-registered tool name. Address resolution failures raise a
        clear error instead of silently skipping the tool.
        """
        from norpagent.arch.address import (
            AddressError,
            is_address_like,
            resolve_address,
        )

        for ref in refs:
            if not isinstance(ref, str) or not ref.strip():
                continue
            ref = ref.strip()
            if is_address_like(ref):
                try:
                    impl = resolve_address(ref, slot="tools")
                except AddressError as exc:
                    raise ValueError(
                        f"rescue: cannot resolve tool address {ref!r}: {exc}"
                    ) from exc
                if callable(impl):
                    impl = impl()
                tname = getattr(impl, "name", "") or impl.__class__.__name__
                self.registry.register_tool(tname, impl)
                self._origin[tname] = "custom"
            elif ref in self.registry.list_tools():
                self._origin[ref] = "custom"  # already registered (e.g. by extra_tools)
            else:
                raise ValueError(
                    f"rescue: tool {ref!r} is not registered and not a module "
                    f"address. Registered tools: {self.registry.list_tools()}"
                )

    def _register_extra_tools(self, extra_tools: Any) -> None:
        """Register custom tools given as {name: tool}, [tool, ...], or [name, ...]."""
        if isinstance(extra_tools, dict):
            for name, tool in extra_tools.items():
                self.registry.register_tool(name, tool)
                self._origin[name] = "custom"
            return
        for item in extra_tools or ():
            if isinstance(item, str):
                self._register_tool_refs([item])
                continue
            tname = getattr(item, "name", "") or item.__class__.__name__
            self.registry.register_tool(tname, item)
            self._origin[tname] = "custom"

    def _load_plugin_dirs(
        self,
        plugin_dirs: List[str],
        plugin_config: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Load external plugin directories through the host security pipeline.

        Uses the same loader as ``np(plugins=[...])`` (signature -> audit ->
        import restriction -> register). Default config matches the host:
        audit=warn, signature verification on. Plugin-registered tools keep the
        ``plugin`` origin and remain manually callable through this environment.
        """
        from norpagent.plugins import install_plugin_dirs

        config = dict(plugin_config or {})
        config.setdefault("plugin_security_audit", "warn")
        config.setdefault("plugin_signature_verify", True)
        self._plugin_loader = install_plugin_dirs(
            self.registry, plugin_dirs, config=config,
        )
        for info in self._plugin_loader.plugins:
            if not info.enabled:
                print(f"[rescue] plugin skipped: {info.name} ({info.error})")
                continue
            for tname in info.tools:
                if tname in self.registry.list_tools():
                    self._origin[tname] = "plugin"

    # ── inventory ─────────────────────────────────────────

    def inventory(self) -> List[Dict[str, Any]]:
        """All registered tools with their OpenAI schemas (sorted by category / name).

        Each item carries ``origin``: ``builtin`` (framework built-ins),
        ``custom`` (tools slot / extra_tools) or ``plugin`` (loaded from an
        external plugin directory).
        """
        items: List[Dict[str, Any]] = []
        builtin_names = {
            "echo", "get_time", "run_python",
            "file_read", "file_write", "file_list", "file_delete",
            "file_surgeon", "search_in_file",
            "exec_cmd",
            "web_search", "web_fetch", "web_extract_links",
            "context_add", "context_search", "context_list", "context_delete",
            "project_status",
            "task_submit", "task_list", "task_status", "task_cancel",
        }
        for name in self.registry.list_tools():
            try:
                tool = self.registry.resolve_tool(name)
                schema = tool.schema() or {}
            except Exception as exc:  # noqa: BLE001 — one broken tool must not hide the rest
                schema = {}
                schema_error = str(exc)
            else:
                schema_error = ""
            fn = schema.get("function", {}) if isinstance(schema, dict) else {}
            parameters = fn.get("parameters", {}) if isinstance(fn, dict) else {}
            required = parameters.get("required", []) or []
            items.append({
                "name": name,
                "description": fn.get("description", ""),
                "parameters": parameters,
                "required": list(required),
                "category": _category_of(name),
                "origin": self._origin.get(
                    name, "builtin" if name in builtin_names else "custom"),
                "schema_error": schema_error,
            })
        items.sort(key=lambda it: (_category_of(it["name"]), it["name"]))
        return items

    def _ensure_session(self) -> Any:
        with self._session_lock:
            if self._session is None:
                self._session = self.session_manager.create_session(
                    title="rescue-manual"
                )
            return self._session

    # ── manual call ───────────────────────────────────────

    def call_tool(
        self,
        name: str,
        args: Optional[Dict[str, Any]] = None,
        timeout: Optional[float] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Run one tool by hand and return a structured result dict.

        ``args``: tool arguments (parsed dict, exactly what the model would emit).
        ``timeout``: hard wall-clock limit in seconds (default 300, <=0 = default).
            On timeout the call is abandoned: the cancel event is set (sandboxes
            force-kill child processes, streaming loops exit early) and the worker
            thread becomes a daemon orphan.
        ``params``: optional per-call task parameter merge (workspace_root /
            ptc_timeout / ...) layered over the environment defaults.

        Result dict: ``{ok, tool, task_id, output, error, success, timed_out, duration_ms}``.
        ``ok`` is False for unknown tools, tool failures and timeouts alike.
        """
        self._orphan_threads = [t for t in self._orphan_threads if t.is_alive()]
        try:
            tool = self.registry.resolve_tool(name)
        except ComponentError as exc:
            return {
                "ok": False, "tool": name, "task_id": "",
                "output": "", "error": str(exc), "success": False,
                "timed_out": False, "duration_ms": 0.0,
            }
        try:
            timeout = float(timeout if timeout is not None else DEFAULT_TOOL_TIMEOUT)
        except (TypeError, ValueError):
            timeout = DEFAULT_TOOL_TIMEOUT
        if timeout <= 0:
            timeout = DEFAULT_TOOL_TIMEOUT

        task_id = uuid.uuid4().hex[:12]
        cancel_event = threading.Event()
        call_params = dict(self.params)
        if params:
            call_params.update(params)
        call_params["_cancel_event"] = cancel_event
        ctx = RunContext(
            registry=self.registry,
            session_manager=self.session_manager,
            session_id=self._ensure_session().id,
            sandbox=self.sandbox,
            scheduler=self.scheduler,
            ui=None,
            params=call_params,
            task_id=task_id,
            preset_name=RESCUE_PRESET_NAME,
            components=dict(self.components),
        )
        box: Dict[str, Any] = {}
        context_copy = contextvars.copy_context()

        def _runner() -> None:
            # run inside a copied context so the cancel-event ContextVar is set
            # for this worker thread only (cancel_requested() sees it; other
            # threads are unaffected)
            _current_cancel.set(cancel_event)
            started = time.monotonic()
            try:
                result = tool.run(args or {}, ctx)
                if not isinstance(result, ToolResult):
                    result = ToolResult(output=str(result))
            except Exception as exc:  # noqa: BLE001
                result = tool_error(name, exc)
            box["result"] = result
            box["duration_ms"] = round((time.monotonic() - started) * 1000, 1)

        worker = threading.Thread(
            target=context_copy.run, args=(_runner,), daemon=True
        )
        worker.start()
        worker.join(timeout)
        if worker.is_alive():
            cancel_event.set()
            self._orphan_threads.append(worker)
            return {
                "ok": False, "tool": name, "task_id": task_id,
                "output": "", "success": False, "timed_out": True,
                "error": (
                    f"tool call exceeded {timeout}s; abandoned (cancel event set, "
                    "sandbox processes force-killed)"
                ),
                "duration_ms": round(timeout * 1000, 1),
            }
        result = box.get("result") or ToolResult(
            output="(no result)", success=False, error="no result produced"
        )
        return {
            "ok": bool(result.success),
            "tool": name,
            "task_id": task_id,
            "output": str(result.output),
            "error": str(result.error or ""),
            "success": bool(result.success),
            "timed_out": False,
            "duration_ms": float(box.get("duration_ms") or 0.0),
        }

    def close(self) -> None:
        """Release the shared environment (sandbox / scheduler / context store / plugins)."""
        if self._closed:
            return
        self._closed = True
        for resource in (self.sandbox, self.scheduler):
            closer = getattr(resource, "close", None)
            if callable(closer):
                try:
                    closer()
                except Exception:  # noqa: BLE001
                    pass
        for component in self.components.values():
            closer = getattr(component, "close", None)
            if callable(closer):
                try:
                    closer()
                except Exception:  # noqa: BLE001
                    pass
        loader = self._plugin_loader
        if loader is not None:
            try:
                loader.shutdown()
            except Exception:  # noqa: BLE001
                pass
            self._plugin_loader = None


# ────────────────────────────────────────────────────────
#  HTTP API + operator page
# ────────────────────────────────────────────────────────

class _QuietHTTPServer(ThreadingHTTPServer):
    """ThreadingHTTPServer tuned for the rescue console (no request-log noise).

    - daemon request threads: process exit never hangs on an open keep-alive;
    - allow_reuse_address: the port is reusable immediately after a restart;
    - client disconnects are swallowed silently (curl interrupts / tab closes).
    """

    daemon_threads = True
    allow_reuse_address = True
    request_queue_size = 64
    block_on_close = False

    def handle_error(self, request: Any, client_address: Any) -> None:
        exc = sys.exc_info()[1]
        if isinstance(
            exc,
            (
                BrokenPipeError,
                ConnectionResetError,
                ConnectionAbortedError,
                ConnectionError,
                TimeoutError,
            ),
        ):
            return
        # any other per-request error is logged nowhere: the rescue console
        # must not die or spam because of one bad request


def _make_handler(api: "RescueToolAPI") -> type:
    class Handler(BaseHTTPRequestHandler):
        api_ref = api
        server_version = "norpagent-rescue/0.9"

        def log_message(self, fmt: str, *args: Any) -> None:  # silence access log
            return None

        # ── plumbing ──

        def _send(self, code: int, body: bytes, ctype: str = "application/json; charset=utf-8") -> None:
            try:
                self.send_response(code)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                pass

        def _json(self, code: int, payload: Any) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self._send(code, body)

        def _error(self, code: int, message: str) -> None:
            self._json(code, {"ok": False, "error": message})

        def _authorized(self) -> bool:
            token = self.api_ref.token
            if not token:
                return True
            header = self.headers.get("Authorization", "")
            return header == f"Bearer {token}"

        def _read_body(self) -> Optional[Dict[str, Any]]:
            try:
                length = int(self.headers.get("Content-Length") or 0)
            except (TypeError, ValueError):
                self._error(400, "invalid Content-Length")
                return None
            if length <= 0:
                return {}
            if length > _MAX_JSON_BODY:
                self._error(413, f"request body too large (limit {_MAX_JSON_BODY} bytes)")
                return None
            try:
                raw = self.rfile.read(length)
                payload = json.loads(raw.decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                self._error(400, "request body must be valid UTF-8 JSON")
                return None
            if not isinstance(payload, dict):
                self._error(400, "request body must be a JSON object")
                return None
            return payload

        # ── GET ──

        def do_GET(self) -> None:
            path = urlparse(self.path).path
            if path == "/":
                self._send(200, self.api_ref.page_html().encode("utf-8"),
                           "text/html; charset=utf-8")
                return
            if not path.startswith("/api/"):
                self._error(404, "not found")
                return
            if not self._authorized():
                self._error(401, "missing or invalid bearer token")
                return
            if path == "/api/health":
                tools = self.api_ref.env.inventory()
                self._json(200, {
                    "ok": True, "status": "ok", "mode": "human-rescue",
                    "tools": len(tools),
                    "custom_tools": sum(
                        1 for it in tools if it.get("origin") != "builtin"),
                    "workspace_root": self.api_ref.env.params.get("workspace_root", ""),
                })
                return
            if path == "/api/tools":
                self._json(200, {"ok": True, "tools": self.api_ref.env.inventory()})
                return
            if path.startswith("/api/tools/"):
                name = path[len("/api/tools/"):].strip()
                for item in self.api_ref.env.inventory():
                    if item["name"] == name:
                        self._json(200, {"ok": True, "tool": item})
                        return
                self._error(404, f"tool '{name}' is not registered")
                return
            self._error(404, "not found")

        # ── POST ──

        def do_POST(self) -> None:
            path = urlparse(self.path).path
            if not path.startswith("/api/"):
                self._error(404, "not found")
                return
            if not self._authorized():
                self._error(401, "missing or invalid bearer token")
                return
            body = self._read_body()
            if body is None:
                return
            args = body.get("args")
            if args is not None and not isinstance(args, dict):
                self._error(400, "'args' must be a JSON object")
                return
            timeout = body.get("timeout")
            params = body.get("params")
            if params is not None and not isinstance(params, dict):
                self._error(400, "'params' must be a JSON object")
                return
            if path == "/api/tools/call":
                name = body.get("tool")
                if not isinstance(name, str) or not name.strip():
                    self._error(400, "'tool' (string) is required")
                    return
            elif path.startswith("/api/tools/"):
                name = path[len("/api/tools/"):].rstrip("/")
                if name.endswith("/call"):
                    name = name[: -len("/call")]
                else:
                    self._error(404, "not found")
                    return
            else:
                self._error(404, "not found")
                return
            try:
                self.api_ref.env.registry.resolve_tool(name)
            except ComponentError:
                self._error(404, f"tool '{name}' is not registered")
                return
            result = self.api_ref.env.call_tool(
                name, args=args, timeout=timeout, params=params
            )
            self._json(200, result)

        def do_PUT(self) -> None:
            self._error(405, "method not allowed")

        do_DELETE = do_PUT
        do_PATCH = do_PUT

    return Handler


class RescueToolAPI:
    """HTTP API + operator page exposing every tool for manual rescue calls.

    Endpoints (all JSON unless noted):

    - ``GET /``            operator page (inline HTML, no dependencies)
    - ``GET /api/health``  status / tool count / workspace root
    - ``GET /api/tools``   inventory: ``{tools: [{name, description, parameters,
      required, category}]}``
    - ``GET /api/tools/<name>``  single tool
    - ``POST /api/tools/call``   body ``{"tool": name, "args": {...}, "timeout": N}``
    - ``POST /api/tools/<name>/call``  body ``{"args": {...}, "timeout": N}``

    When ``token`` is set, every ``/api/*`` request must carry
    ``Authorization: Bearer <token>`` (401 otherwise). ``port=0`` binds an
    ephemeral port; ``start()`` returns the actual port.
    """

    def __init__(
        self,
        env: Optional[RescueToolEnvironment] = None,
        port: int = 8799,
        host: str = "127.0.0.1",
        token: Optional[str] = None,
    ) -> None:
        self.env = env or RescueToolEnvironment()
        self.port = int(port)
        self.host = host or "127.0.0.1"
        self.token = token or None
        self._server: Optional[_QuietHTTPServer] = None
        self._thread: Optional[threading.Thread] = None
        self._closed = False

    # ── lifecycle ─────────────────────────────────────────

    def start(self) -> int:
        """Bind and serve on a daemon thread; returns the actual port."""
        if self._server is not None:
            return self.port
        handler = _make_handler(self)
        server = _QuietHTTPServer((self.host, self.port), handler)
        self._server = server
        self.port = int(server.server_address[1])
        self._thread = threading.Thread(
            target=server.serve_forever, daemon=True, name="rescue-tool-api"
        )
        self._thread.start()
        return self.port

    def shutdown(self) -> None:
        if self._closed:
            return
        self._closed = True
        server = self._server
        if server is not None:
            try:
                server.shutdown()
            except Exception:  # noqa: BLE001
                pass
            try:
                server.server_close()
            except Exception:  # noqa: BLE001
                pass
            self._server = None
        self.env.close()

    # ── operator page ─────────────────────────────────────

    @staticmethod
    def page_html() -> str:
        return _OPERATOR_PAGE


_OPERATOR_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>norpagent rescue - manual tool console</title>
<style>
  body { font-family: "Segoe UI", system-ui, sans-serif; margin: 0; background: #111827;
         color: #e5e7eb; }
  header { padding: 12px 20px; background: #0b1220; border-bottom: 1px solid #1f2937; }
  h1 { margin: 0; font-size: 18px; font-weight: 600; }
  .sub { color: #9ca3af; font-size: 12px; margin-top: 2px; }
  main { display: flex; gap: 16px; padding: 16px; align-items: flex-start; flex-wrap: wrap; }
  .panel { background: #0b1220; border: 1px solid #1f2937; border-radius: 8px;
           padding: 14px; min-width: 320px; }
  .panel.left { flex: 1 1 380px; max-width: 560px; }
  .panel.right { flex: 1 1 420px; }
  label { display: block; font-size: 12px; color: #9ca3af; margin: 8px 0 4px; }
  select, input, textarea { width: 100%; box-sizing: border-box; background: #111827;
    color: #e5e7eb; border: 1px solid #374151; border-radius: 6px; padding: 8px;
    font-family: Consolas, monospace; font-size: 13px; }
  textarea { resize: vertical; }
  .row { display: flex; gap: 8px; align-items: flex-end; }
  .row .grow { flex: 1; }
  button { background: #2563eb; border: 0; color: white; padding: 8px 18px;
           border-radius: 6px; cursor: pointer; font-size: 13px; }
  button.ghost { background: #374151; }
  button:disabled { background: #1f2937; cursor: wait; }
  #schema { background: #0f172a; border-radius: 6px; padding: 8px; font-size: 11px;
            color: #93c5fd; white-space: pre-wrap; max-height: 160px; overflow: auto; }
  #status { font-size: 12px; color: #9ca3af; }
  #out { background: #0f172a; border-radius: 6px; padding: 10px; min-height: 160px;
         max-height: 420px; overflow: auto; white-space: pre-wrap; word-break: break-all;
         font-family: Consolas, monospace; font-size: 12px; }
  #out.err { color: #fca5a5; }
  #out.timeout { color: #fbbf24; }
  .hist-item { border-top: 1px solid #1f2937; padding: 6px 0; font-size: 12px; }
  .hist-meta { color: #9ca3af; }
  .hist-body { white-space: pre-wrap; word-break: break-all; max-height: 120px;
               overflow: auto; }
</style>
</head>
<body>
<header>
  <h1>norpagent rescue - manual tool console</h1>
  <div class="sub">Model-independent takeover: call any registered tool by hand and read the raw result.</div>
</header>
<main>
  <div class="panel left">
    <label>Auth token (only needed when the server requires one)</label>
    <input id="token" type="password" placeholder="bearer token" autocomplete="off">
    <label>Tool</label>
    <div class="row">
      <select id="tool" class="grow"></select>
      <button id="refresh" class="ghost" type="button">Refresh</button>
    </div>
    <label>Schema</label>
    <div id="schema">(loading...)</div>
    <label>Args (JSON)</label>
    <textarea id="args" rows="7">{
}</textarea>
    <label>Timeout (seconds)</label>
    <input id="timeout" type="number" min="1" value="300">
    <div class="row" style="margin-top:12px;">
      <button id="call" type="button">Call tool</button>
      <span id="status"></span>
    </div>
  </div>
  <div class="panel right">
    <label>Result</label>
    <pre id="out">(no call yet)</pre>
    <label>Call history</label>
    <div id="history"></div>
  </div>
</main>
<script>
(function () {
  var tools = [];
  var history = [];
  var $ = function (id) { return document.getElementById(id); };
  function authHeaders() {
    var t = $("token").value.trim();
    var h = {"Content-Type": "application/json"};
    if (t) { h["Authorization"] = "Bearer " + t; }
    return h;
  }
  function loadTools() {
    $("status").textContent = "loading tools...";
    fetch("/api/tools", {headers: authHeaders()}).then(function (r) {
      if (!r.ok) { throw new Error("HTTP " + r.status); }
      return r.json();
    }).then(function (data) {
      tools = data.tools || [];
      var sel = $("tool");
      sel.innerHTML = "";
      var lastCategory = "";
      tools.forEach(function (t) {
        if (t.category !== lastCategory) {
          var opt = document.createElement("option");
          opt.disabled = true;
          opt.textContent = "── " + t.category + " ──";
          sel.appendChild(opt);
          lastCategory = t.category;
        }
        var opt = document.createElement("option");
        opt.value = t.name;
        var tag = t.origin && t.origin !== "builtin" ? " [" + t.origin + "]" : "";
        opt.textContent = t.name + tag;
        sel.appendChild(opt);
      });
      $("status").textContent = tools.length + " tools available";
      showSchema();
    }).catch(function (e) {
      $("status").textContent = "failed to load tools: " + e.message;
    });
  }
  function showSchema() {
    var name = $("tool").value;
    var item = null;
    tools.forEach(function (t) { if (t.name === name) { item = t; } });
    if (!item) { $("schema").textContent = "(no tool selected)"; return; }
    var text = item.description || "(no description)";
    if (item.origin && item.origin !== "builtin") {
      text = "[origin: " + item.origin + "] " + text;
    }
    if (item.required && item.required.length) {
      text += "\\nrequired: " + item.required.join(", ");
    }
    text += "\\nparameters: " + JSON.stringify(item.parameters, null, 2);
    $("schema").textContent = text;
  }
  function callTool() {
    var name = $("tool").value;
    var argsText = $("args").value;
    var timeout = parseFloat($("timeout").value) || 300;
    var args;
    try { args = JSON.parse(argsText); } catch (e) {
      $("status").textContent = "args are not valid JSON: " + e.message;
      return;
    }
    $("call").disabled = true;
    $("status").textContent = "calling " + name + "...";
    fetch("/api/tools/" + encodeURIComponent(name) + "/call", {
      method: "POST",
      headers: authHeaders(),
      body: JSON.stringify({args: args, timeout: timeout})
    }).then(function (r) {
      if (!r.ok) { throw new Error("HTTP " + r.status); }
      return r.json();
    }).then(function (res) {
      var out = $("out");
      out.className = "";
      var text = "";
      if (res.timed_out) {
        out.className = "timeout";
        text = "[TIMED OUT] " + (res.error || "");
      } else if (!res.ok) {
        out.className = "err";
        text = "[FAILED] " + (res.error || res.output || "unknown error");
      } else {
        text = res.output || "(empty result)";
      }
      text += "\\n\\n[task " + res.task_id + " | " + res.duration_ms + " ms]";
      out.textContent = text;
      $("status").textContent = res.ok ? "done" : (res.timed_out ? "timed out" : "failed");
      addHistory(res);
    }).catch(function (e) {
      var out = $("out");
      out.className = "err";
      out.textContent = "request failed: " + e.message;
      $("status").textContent = "request failed";
    }).finally(function () {
      $("call").disabled = false;
    });
  }
  function addHistory(res) {
    history.unshift({tool: res.tool, ok: res.ok, timed_out: res.timed_out,
                     output: res.output, error: res.error, task_id: res.task_id});
    if (history.length > 20) { history.pop(); }
    var box = $("history");
    box.innerHTML = "";
    history.forEach(function (h) {
      var div = document.createElement("div");
      div.className = "hist-item";
      var meta = document.createElement("div");
      meta.className = "hist-meta";
      var state = h.timed_out ? "TIMED OUT" : (h.ok ? "ok" : "failed");
      meta.textContent = h.tool + " [" + state + "] task " + h.task_id;
      var body = document.createElement("div");
      body.className = "hist-body";
      body.textContent = h.error || h.output || "";
      div.appendChild(meta);
      div.appendChild(body);
      box.appendChild(div);
    });
  }
  $("refresh").addEventListener("click", loadTools);
  $("tool").addEventListener("change", showSchema);
  $("call").addEventListener("click", callTool);
  loadTools();
})();
</script>
</body>
</html>
"""


__all__ = [
    "RescueToolEnvironment",
    "RescueToolAPI",
    "DEFAULT_TOOL_TIMEOUT",
    "RESCUE_PRESET_NAME",
]
