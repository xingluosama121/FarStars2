# Copyright (c) 2026 xingluosama121, MIT Licensed
"""External plugin loader: migrates the existing application's plugin security pipeline into a pip library capability.

Pipeline (consistent with the existing application's plugin_system.manager):

    discover (single-file / manifest packages) → signature verification → AST audit
    (block-level rejection) → permission declaration validation → load module under
    import restrictions → adapt to the Plugin protocol → register into the Registry
    (tools into the tool table; hooks subscribing to the event bus)

Supported plugin formats are fully compatible with the existing application:

- module-level constants: PLUGIN_NAME / PLUGIN_PUBLISHER / PLUGIN_VERSION /
  PLUGIN_DESCRIPTION;
- ``TOOLS``: OpenAI function schema list + ``execute(tool_name, args, ctx)``;
- 15 hook functions (on_task_start / before_step / after_tool_call etc.);
- ``APPROVAL_HINTS``: tool → approval hint (approval=none skips approval).

Config keys (config dict) follow the existing application:

- plugin_security_audit: off / warn / block (default warn)
- plugin_security_import_restrict: off / safe / strict (default off)
- plugin_security_require_permissions: bool (default False)
- plugin_signature_verify: bool (default True)
- plugin_trusted_keys: list[str]
- plugin_network_policy: deny / audited_public / public_only / allow_all
- approval_enabled: bool (default True)

Usage::

    from norpagent.plugins import install_plugin_dirs
    loader = install_plugin_dirs(registry, ["/path/to/plugins"], config={})
    for info in loader.plugins:
        print(info.name, info.signature_status, info.enabled)
"""

from __future__ import annotations

import ast
import importlib.util
import json
import os
import sys
import threading
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from norpagent.protocols.tool import Tool, ToolResult
from norpagent.security.audit import Severity, SourceAuditor
from norpagent.security.approval import ApprovalPolicy
from norpagent.security.network_policy import NetworkPolicy
from norpagent.security.signature import SignatureResult, SignatureStatus, SignatureVerifier

# aligned with the existing application's 15 hooks (same event names; see kernel/events.py)
HOOK_NAMES = [
    "on_agent_init",
    "on_agent_shutdown",
    "on_task_start",
    "on_task_done",
    "on_task_error",
    "on_task_stopped",
    "on_task_timeout",
    "before_step",
    "after_step",
    "before_tool_call",
    "after_tool_call",
    "on_user_input_required",
    "on_reasoning",
    "on_content",
    "on_event",
    "on_usage_update",
]

_MUTATING_HOOKS = {"before_step", "before_tool_call", "after_tool_call"}

# plugin load pipeline hooks (dynamic hooks: auto-registered via registry.hooks;
# part of the hook system's "custom hook" capability; PluginSystem installs a
# same-named custom layer)
PIPELINE_HOOK_NAMES = [
    "before_plugin_discover",
    "after_plugin_discover",
    "before_plugin_load",
    "after_plugin_load",
    "before_plugin_audit",
    "after_plugin_audit",
    "before_plugin_register",
    "after_plugin_register",
]

# module-name namespace: external plugin modules are uniformly named norpagent_ext_<name>
PLUGIN_MODULE_PREFIX = "norpagent_ext_"

_loading_plugin = threading.local()

# import restrictions (consistent with the existing application)
ALWAYS_BLOCKED = {"ctypes", "cffi"}

SAFE_MODULES: Set[str] = {
    "json", "re", "datetime", "math", "random", "collections",
    "itertools", "functools", "typing", "enum", "dataclasses",
    "pathlib", "os.path", "glob", "fnmatch",
    "textwrap", "string", "hashlib", "base64", "binascii",
    "traceback", "logging", "warnings",
    "copy", "pprint", "inspect", "contextlib",
    "uuid", "time", "calendar", "zoneinfo",
    "csv", "io", "tempfile", "shutil",
    "html", "xml.etree.ElementTree", "xml",
    "struct", "codecs", "unicodedata",
    "fractions", "decimal", "statistics",
    "norpagent", "norpagent.protocols", "norpagent.protocols.tool",
}

STRICT_SAFE_MODULES: Set[str] = {
    "json", "re", "datetime", "math", "random",
    "collections", "itertools", "functools", "typing", "enum",
    "pathlib", "os.path",
    "textwrap", "string", "hashlib", "base64",
    "traceback", "logging", "warnings", "copy",
    "uuid", "time",
    "norpagent.protocols.tool",
}

DANGEROUS_IMPORTS_FOR_BLOCK = {
    "subprocess", "ctypes", "cffi", "socket", "pickle", "marshal",
    "telnetlib", "ftplib", "smtplib",
}


@dataclass
class PluginContext:
    """Context passed to external plugin hooks / execute (aligned with the existing application's PluginContext)."""

    plugin_name: str = ""
    project_root: str = ""
    app_dir: str = ""
    config: Dict[str, Any] = field(default_factory=dict)
    current_step: int = 0
    total_usage: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PluginInfo:
    """Load-result metadata of one external plugin."""

    name: str
    path: str
    version: str = "0.0.0"
    publisher: str = ""
    description: str = ""
    enabled: bool = True
    error: str = ""
    tools: List[str] = field(default_factory=list)
    hook_names: List[str] = field(default_factory=list)
    signature_status: str = ""
    trusted: bool = False
    approval_hints: Dict[str, dict] = field(default_factory=dict)
    audit_issues: List[dict] = field(default_factory=list)
    module: Any = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "path": self.path,
            "version": self.version,
            "publisher": self.publisher,
            "description": self.description,
            "enabled": self.enabled,
            "error": self.error,
            "tools": list(self.tools),
            "hook_names": list(self.hook_names),
            "signature_status": self.signature_status,
            "trusted": self.trusted,
            "approval_hints": dict(self.approval_hints),
            "audit_issues": list(self.audit_issues),
        }


# ── import blocker (consistent with the existing application's PluginImportBlocker / StrictImportBlocker) ─


class _ImportBlocker:
    """sys.meta_path import blocker: only affects plugin modules (stack-frame probing)."""

    def __init__(self, blocked: Set[str], strict: bool = False) -> None:
        self.blocked = blocked
        self.strict = strict
        self._registered = False

    def register(self) -> None:
        if self._registered:
            return
        if self not in sys.meta_path:  # type: ignore[comparison-overlap]
            sys.meta_path.insert(0, self)  # type: ignore[arg-type]
        self._registered = True

    def unregister(self) -> None:
        if not self._registered:
            return
        try:
            sys.meta_path.remove(self)  # type: ignore[arg-type]
        except ValueError:
            pass
        self._registered = False

    def find_spec(self, fullname: str, path=None, target=None):
        if self.strict:
            allowed = fullname in STRICT_SAFE_MODULES or any(
                fullname.startswith(m + ".") for m in STRICT_SAFE_MODULES
            )
            if not allowed:
                if self._caller_is_plugin():
                    raise ImportError(
                        f"plugin security (strict): import of '{fullname}' is not allowed "
                        "(not in the safe-module allowlist)"
                    )
                return None
            return None

        should_block = fullname in self.blocked or any(
            fullname == b or fullname.startswith(b + ".") for b in self.blocked
        )
        if not should_block:
            should_block = any(
                fullname == ab or fullname.startswith(ab + ".")
                for ab in ALWAYS_BLOCKED
            )
        if not should_block:
            return None
        if self._caller_is_plugin():
            raise ImportError(
                f"plugin security: import of '{fullname}' is forbidden (plugin code may not use this module)"
            )
        return None

    @staticmethod
    def _caller_is_plugin() -> bool:
        if getattr(_loading_plugin, "active", False):
            return True
        try:
            frame = sys._getframe()
            depth = 0
            while frame is not None and depth < 80:
                mod_name = frame.f_globals.get("__name__", "")
                if mod_name.startswith(PLUGIN_MODULE_PREFIX):
                    return True
                frame = frame.f_back
                depth += 1
        except Exception:
            pass
        return False


# ── legacy-format plugin adapter (TOOLS + execute + 15 hooks → Plugin protocol) ───


class _LegacyToolAdapter:
    """Adapts a TOOLS schema + execute entry into the Tool protocol."""

    def __init__(self, name: str, schema: Dict[str, Any],
                 plugin_name: str, execute_fn: Optional[Callable],
                 loader: "PluginLoader"):
        self.name = name
        self._schema = schema
        self._plugin_name = plugin_name
        self._execute_fn = execute_fn
        self._loader = loader

    def schema(self) -> Dict[str, Any]:
        return self._schema

    def run(self, args: Dict[str, Any], ctx: Any) -> ToolResult:
        if self._execute_fn is None:
            return ToolResult(
                output=f"plugin '{self._plugin_name}' has no execute() function",
                success=False,
                error="no_execute",
            )
        plugin_ctx = self._loader.plugin_context(self._plugin_name, ctx)
        try:
            output = self._execute_fn(self.name, args or {}, plugin_ctx)
            if isinstance(output, ToolResult):
                return output
            return ToolResult(output=str(output))
        except Exception as exc:  # noqa: BLE001
            return ToolResult(
                output=f"plugin tool execution error: {type(exc).__name__}: {exc}",
                success=False,
                error=f"{type(exc).__name__}: {exc}",
            )


# event payload → legacy-format hook argument conversion table
# value = which keys to take from AgentEvent.payload, passed to the hook in order (ctx appended at the end)
_HOOK_ARG_KEYS: Dict[str, Tuple[str, ...]] = {
    "on_agent_init": (),
    "on_agent_shutdown": (),
    "on_task_start": ("user_input",),
    "on_task_done": ("content",),
    "on_task_error": ("error",),
    "on_task_stopped": ("reason",),
    "on_task_timeout": ("timeout",),
    "before_step": ("step", "messages"),
    "after_step": ("step", "content", "tool_calls"),
    "before_tool_call": ("tool_name", "args"),
    "after_tool_call": ("tool_name", "args"),
    "on_user_input_required": ("question",),
    "on_reasoning": ("content",),
    "on_content": ("content",),
    "on_event": ("event_type", "data"),
    "on_usage_update": ("total",),
}


def _build_hook_args(hook_name: str, payload: Dict[str, Any]) -> List[Any]:
    """Build the positional argument list from an event payload per the legacy hook signature convention.

    Legacy signature: business arguments first, PluginContext last (appended by the caller).
    Fully consistent with the existing application's plugin_system dispatch logic.
    """
    keys = _HOOK_ARG_KEYS.get(hook_name, ())
    args: List[Any] = [payload.get(k) for k in keys]
    if hook_name == "after_tool_call":
        # legacy format: (tool_name, args, result, ctx)
        args.append(str(payload.get("result") or ""))
    elif hook_name == "on_task_done":
        # legacy format: (summary, final_reply, ctx)
        args.append(payload.get("content") or "")
    elif hook_name == "after_step":
        # legacy format: (step, reasoning, content, tool_calls, ctx)
        args = [
            payload.get("step", 0),
            payload.get("content", ""),
            payload.get("tool_calls") or [],
        ]
    elif hook_name == "on_usage_update":
        args = [{
            "input": payload.get("input", 0),
            "output": payload.get("output", 0),
            "total": payload.get("total", 0),
        }]
    return args


def _wrap_hook(hook_name: str, fn: Callable, loader: "PluginLoader",
               plugin_name: str) -> Callable:
    """Wrap a legacy hook function into an EventBus subscriber (receiving an AgentEvent).

    Legacy signature convention: business arguments first, PluginContext last;
    return values of mutating hooks (before_step / before_tool_call /
    after_tool_call) pass through to the kernel via EventBus.intercept; return
    values of other hooks are ignored.
    """

    def listener(event: Any) -> Any:
        payload = getattr(event, "payload", {}) or {}
        args = _build_hook_args(hook_name, payload)
        ctx = loader.plugin_context(plugin_name, payload.get("context"))
        args.append(ctx)
        try:
            return fn(*args)
        except Exception:
            return None

    return listener


class _LegacyPluginAdapter:
    """Adapter from a legacy-format plugin module → Plugin protocol."""

    def __init__(self, info: PluginInfo, module: Any, loader: "PluginLoader"):
        self.info = info
        self.module = module
        self.loader = loader
        self.name = info.name
        self.version = info.version
        self.publisher = info.publisher
        self.description = info.description

    def get_tools(self) -> List[Tool]:
        tools: List[Tool] = []
        raw_tools = getattr(self.module, "TOOLS", None) or []
        execute_fn = getattr(self.module, "execute", None)
        if not callable(execute_fn):
            execute_fn = None
        for tool_def in raw_tools:
            func = tool_def.get("function", {}) if isinstance(tool_def, dict) else {}
            tname = func.get("name", "")
            if tname:
                tools.append(_LegacyToolAdapter(
                    tname, tool_def, self.info.name, execute_fn, self.loader,
                ))
        return tools

    def get_hooks(self) -> Dict[str, Callable]:
        hooks: Dict[str, Callable] = {}
        for hook_name in HOOK_NAMES:
            fn = getattr(self.module, hook_name, None)
            if callable(fn):
                hooks[hook_name] = _wrap_hook(hook_name, fn, self.loader, self.info.name)
        return hooks

    def execute(self, tool_name: str, args: Dict[str, Any], ctx: Any) -> Optional[str]:
        fn = getattr(self.module, "execute", None)
        if not callable(fn):
            return None
        plugin_ctx = self.loader.plugin_context(self.info.name, ctx)
        output = fn(tool_name, args or {}, plugin_ctx)
        return None if output is None else str(output)


# ── process-isolated plugin adapter (P4: plugin code exists only in the host child process) ──


def _plugin_ctx_dict(plugin_ctx: PluginContext) -> Dict[str, Any]:
    """PluginContext → JSON-serializable dict (RPC transport)."""
    return {
        "plugin_name": plugin_ctx.plugin_name,
        "project_root": plugin_ctx.project_root,
        "app_dir": plugin_ctx.app_dir,
        "config": plugin_ctx.config,
        "current_step": plugin_ctx.current_step,
        "total_usage": plugin_ctx.total_usage,
    }


class _RemoteToolAdapter:
    """Tool of a process-isolated plugin: execution is forwarded via RPC to the plugin host child process."""

    def __init__(self, name: str, schema: Dict[str, Any],
                 plugin_name: str, manager: Any, loader: "PluginLoader"):
        self.name = name
        self._schema = schema
        self._plugin_name = plugin_name
        self._manager = manager
        self._loader = loader

    def schema(self) -> Dict[str, Any]:
        return self._schema

    def run(self, args: Dict[str, Any], ctx: Any) -> ToolResult:
        plugin_ctx = self._loader.plugin_context(self._plugin_name, ctx)
        try:
            output = self._manager.call_tool(
                self._plugin_name, self.name, args or {},
                _plugin_ctx_dict(plugin_ctx),
            )
            if isinstance(output, ToolResult):
                return output
            return ToolResult(output=str(output))
        except Exception as exc:  # noqa: BLE001 — host dead / timeout / plugin error
            return ToolResult(
                output=f"plugin tool execution error (process isolation): {type(exc).__name__}: {exc}",
                success=False,
                error=f"{type(exc).__name__}: {exc}",
            )


class _RemotePluginAdapter:
    """Process-isolated plugin: tools go through RPC; hooks relay back to the main process via the host child."""

    def __init__(self, info: PluginInfo, tool_schemas: List[Dict[str, Any]],
                 hook_names: List[str], manager: Any, loader: "PluginLoader"):
        self.info = info
        self.name = info.name
        self.version = info.version
        self.publisher = info.publisher
        self.description = info.description
        self._tool_schemas = tool_schemas
        self._hook_names = hook_names
        self._manager = manager
        self._loader = loader

    def get_tools(self) -> List[Tool]:
        tools: List[Tool] = []
        for tool_def in self._tool_schemas:
            func = tool_def.get("function", {}) if isinstance(tool_def, dict) else {}
            tname = func.get("name", "")
            if tname:
                tools.append(_RemoteToolAdapter(
                    tname, tool_def, self.name, self._manager, self._loader,
                ))
        return tools

    def get_hooks(self) -> Dict[str, Callable]:
        """Hook bridge: event → argument list → host child fire_hook RPC.

        Mutating hooks' return values pass through to the kernel via
        EventBus.intercept; fire_hook executes in a daemon thread with a bounded
        wait (HOOK_TIMEOUT) and returns None on timeout abandonment — plugin hooks
        never stall the main loop.
        """
        loader = self._loader
        manager = self._manager
        plugin_name = self.name

        def bridge(hook_name: str, fn_self: "_RemotePluginAdapter" = None):
            def listener(event: Any) -> Any:
                payload = getattr(event, "payload", {}) or {}
                args = _build_hook_args(hook_name, payload)
                plugin_ctx = loader.plugin_context(
                    plugin_name, payload.get("context")
                )
                return manager.fire_hook(
                    plugin_name, hook_name, args,
                    _plugin_ctx_dict(plugin_ctx),
                )

            return listener

        hooks: Dict[str, Callable] = {}
        for hook_name in self._hook_names:
            hooks[hook_name] = bridge(hook_name)
        return hooks

    def execute(self, tool_name: str, args: Dict[str, Any], ctx: Any) -> Optional[str]:
        plugin_ctx = self._loader.plugin_context(self.name, ctx)
        try:
            output = self._manager.call_tool(
                self.name, tool_name, args or {}, _plugin_ctx_dict(plugin_ctx),
            )
            return None if output is None else str(output)
        except Exception:
            return None


# ── loader ────────────────────────────────────────────────


class PluginLoader:
    """External plugin loader: security pipeline + registration into the Registry.

    Security pipeline (every stage is a dynamic hook on registry.hooks,
    subscribable / vetoable with a single HookVeto vote):

        discover -> [signature verify -> AST audit -> permission declarations
        -> load under import restrictions] -> adapt to Plugin protocol
        -> register into the Registry

    Process-level plugin isolation is supported since P4: ``plugin_isolation:
    auto/inproc/process`` or the plugin's module-level ``ISOLATION = "process"``
    (effective under auto); plugins opting into isolation are loaded and executed
    in the host child process (see norpagent.plugins.host).
    """

    def __init__(self, plugin_dirs: List[str], config: Optional[dict] = None) -> None:
        config = config or {}
        self._plugin_dirs = [os.path.abspath(d) for d in plugin_dirs]
        self.config = config
        self.auditor = SourceAuditor(
            config.get("plugin_security_audit", "warn")
        )
        self.import_restriction = config.get("plugin_security_import_restrict", "off")
        self.require_permissions = bool(
            config.get("plugin_security_require_permissions", False)
        )
        self.signature_required = bool(
            config.get("plugin_signature_required", False)
        )
        self.plugin_isolation = str(
            config.get("plugin_isolation", "auto")
        )
        self.signature_verifier = SignatureVerifier(config)
        self.network_policy = NetworkPolicy(config)
        self.approval = ApprovalPolicy(config)
        self.plugins: List[PluginInfo] = []
        self._lock = threading.Lock()
        self._contexts: Dict[str, PluginContext] = {}
        self._isolation_manager: Any = None
        self._registry: Any = None

    # ── hook helpers ─────────────────────────────────────

    def _emit(self, hook_name: str, **payload: Any) -> None:
        """Publish a pipeline event to registry.hooks (dynamic hook; auto-registered when undefined)."""
        if self._registry is not None:
            try:
                self._registry.hooks.hook(hook_name).emit(**payload)
            except Exception:
                pass

    def _veto(self, hook_name: str, **payload: Any) -> Optional[str]:
        """Mutating pipeline hook: returns the reason when a subscriber raises HookVeto."""
        if self._registry is None:
            return None
        from norpagent.hooks.core import HookVeto

        try:
            self._registry.hooks.hook(hook_name).intercept(**payload)
            return None
        except HookVeto as veto:
            return str(veto)
        except Exception:
            return None

    # ── process-isolation management ─────────────────────

    def isolation_manager(self) -> Any:
        """Get (or lazily create) the process-isolation manager (all isolated plugins share the host child process)."""
        if self._isolation_manager is None:
            from norpagent.plugins.isolation import ProcessIsolationManager

            self._isolation_manager = ProcessIsolationManager(
                security_config={
                    "audit_level": self.auditor.audit_level,
                    "import_restrict": self.import_restriction,
                },
            )
        return self._isolation_manager

    # ── main flow ────────────────────────────────────────

    def discover_and_load(self, registry: Any) -> List[PluginInfo]:
        """Scan all plugin directories and register into the Registry; returns the plugin metadata list."""
        with self._lock:
            self._registry = registry
            self.plugins.clear()
            self._emit("before_plugin_discover", dirs=list(self._plugin_dirs))
            seen_files: Set[str] = set()
            for d in self._plugin_dirs:
                if not os.path.isdir(d):
                    continue
                for entry in sorted(os.listdir(d)):
                    full = os.path.join(d, entry)
                    if entry.endswith(".py") and os.path.isfile(full):
                        if entry == "__init__.py":
                            continue
                        real = os.path.realpath(full)
                        if real in seen_files:
                            continue
                        seen_files.add(real)
                        self._load_from_file(registry, entry[:-3], full, manifest=None)
                    elif os.path.isdir(full):
                        manifest_path = os.path.join(full, "manifest.json")
                        if not os.path.isfile(manifest_path):
                            continue
                        try:
                            with open(manifest_path, "r", encoding="utf-8") as fh:
                                manifest = json.load(fh)
                        except Exception:
                            continue
                        if not isinstance(manifest, dict):
                            continue
                        name = manifest.get("name", entry)
                        entry_file = manifest.get("entry", "plugin.py")
                        entry_path = os.path.join(full, entry_file)
                        if not os.path.isfile(entry_path):
                            continue
                        real = os.path.realpath(entry_path)
                        if real in seen_files:
                            continue
                        seen_files.add(real)
                        self._load_from_file(registry, name, entry_path, manifest=manifest)
            self._emit(
                "after_plugin_discover",
                loaded=len(self.plugins),
                enabled=sum(1 for p in self.plugins if p.enabled),
            )
            return list(self.plugins)

    def plugin_context(self, plugin_name: str, run_ctx: Any = None) -> PluginContext:
        """Build (or fetch from cache) the plugin context."""
        if plugin_name not in self._contexts:
            workspace = ""
            if run_ctx is not None:
                params = getattr(run_ctx, "params", {}) or {}
                workspace = str(params.get("workspace_root", ""))
            self._contexts[plugin_name] = PluginContext(
                plugin_name=plugin_name,
                project_root=workspace,
                app_dir=os.path.expanduser("~"),
                config=dict(self.config),
            )
        ctx = self._contexts[plugin_name]
        if run_ctx is not None:
            params = getattr(run_ctx, "params", {}) or {}
            if params.get("workspace_root"):
                ctx.project_root = str(params["workspace_root"])
        return ctx

    def approval_hints(self) -> Dict[str, dict]:
        """Merge the APPROVAL_HINTS of all enabled plugins (tool → approval hint)."""
        hints: Dict[str, dict] = {}
        for info in self.plugins:
            if not info.enabled:
                continue
            for tname, hint in (info.approval_hints or {}).items():
                if tname not in hints and isinstance(hint, dict):
                    hints[tname] = dict(hint)
        return hints

    # ── single plugin loading (security pipeline) ────────

    def _load_from_file(self, registry: Any, name: str, path: str,
                        manifest: Optional[dict]) -> None:
        info = PluginInfo(name=name, path=path)

        veto = self._veto("before_plugin_load", name=name, path=path)
        if veto is not None:
            info.enabled = False
            info.error = f"plugin loading vetoed by a hook: {veto}"
            self.plugins.append(info)
            return
        self._emit("before_plugin_load", name=name, path=path)

        # ── 1. signature verification (consistent with the existing application: invalid rejects) ──
        sig: SignatureResult = self.signature_verifier.verify(path, manifest)
        info.signature_status = sig.status
        info.trusted = sig.is_trusted
        if sig.status == SignatureStatus.INVALID:
            info.enabled = False
            info.error = f"plugin signature verification failed: {sig.reason}"
            self.plugins.append(info)
            return
        # P4 new capability: signature_required (enabled by safe(level="high")) —
        # only plugins with a trusted signature may load; unsigned / unavailable /
        # untrusted are all rejected
        if self.signature_required and sig.status != SignatureStatus.TRUSTED:
            info.enabled = False
            info.error = (
                f"security policy requires a trusted signature (current: {sig.status}): {sig.reason}"
            )
            self.plugins.append(info)
            return

        # ── 2. trust tiering: trusted signatures get relaxed audit ──
        effective_audit = "warn" if sig.is_trusted else self.auditor.audit_level

        # ── 3. AST audit ──
        self._emit("before_plugin_audit", name=name, path=path,
                   audit_level=effective_audit)
        issues, allowed = self.auditor.audit_file(path, audit_level=effective_audit)
        info.audit_issues = [i.to_dict() for i in issues]
        self._emit(
            "after_plugin_audit", name=name, path=path,
            allowed=allowed, issues=len(issues),
        )
        if not allowed:
            criticals = [i for i in issues if i.severity == Severity.CRITICAL]
            error_lines = "\n".join(
                f"  L{i.line}: [{i.category}] {i.message}" for i in criticals[:5]
            )
            info.enabled = False
            info.error = (
                f"security audit blocked ({len(criticals)} critical):\n{error_lines}"
            )
            self.plugins.append(info)
            return

        # ── 4. permission declaration validation ──
        if self.require_permissions and manifest:
            if not self.auditor.check_permissions(manifest, issues):
                info.enabled = False
                info.error = "missing permission declarations (manifest.json → permissions)"
                self.plugins.append(info)
                return

        # ── 5. isolation decision: process isolation goes to the host child process, never into the main process ──
        isolation = self._decide_isolation(path, manifest)
        if isolation == "process":
            self._load_remote(registry, info, path, manifest)
            return

        # ── 6. load the module under import restrictions (in-process path) ──
        module = self._exec_module(info, path)
        if module is None:
            # _exec_module already filled the error
            self.plugins.append(info)
            return

        # ── 7. read metadata and interfaces ──
        self._fill_metadata(info, module, manifest)

        # ── 8. adapt and register into the Registry ──
        veto = self._veto(
            "before_plugin_register", name=info.name,
            tools=info.tools, isolation="inproc",
        )
        if veto is not None:
            info.enabled = False
            info.error = f"plugin registration vetoed by a hook: {veto}"
            self.plugins.append(info)
            return
        adapter = _LegacyPluginAdapter(info, module, self)
        registry.register_plugin(adapter)
        info.module = module
        self.plugins.append(info)
        self._emit(
            "after_plugin_register", name=info.name,
            enabled=info.enabled, tools=info.tools, isolation="inproc",
        )

    def _load_remote(self, registry: Any, info: PluginInfo, path: str,
                     manifest: Optional[dict]) -> None:
        """Process-isolation path: the plugin module is loaded only in the host child process."""
        try:
            manager = self.isolation_manager()
            meta = manager.load(
                info.name, path,
                self._base_ctx_dict(info.name),
                security_config={
                    "audit_level": self.auditor.audit_level,
                    "import_restrict": self.import_restriction,
                },
            )
        except Exception as exc:  # noqa: BLE001
            info.enabled = False
            info.error = f"plugin host child process load failed: {type(exc).__name__}: {exc}"
            self.plugins.append(info)
            return

        header_name = meta.get("name") or info.name
        if isinstance(header_name, str) and header_name.strip():
            info.name = header_name.strip()
        if manifest:
            info.version = manifest.get("version", meta.get("version", info.version))
            info.publisher = manifest.get(
                "publisher",
                manifest.get("author", meta.get("publisher", info.publisher)),
            )
            info.description = manifest.get(
                "description", meta.get("description", info.description),
            )
        else:
            info.version = str(meta.get("version") or info.version)
            info.publisher = str(meta.get("publisher") or "")
            info.description = str(meta.get("description") or "")

        raw_tools = meta.get("tools") or []
        info.tools = [
            t.get("function", {}).get("name", "")
            for t in raw_tools
            if isinstance(t, dict) and t.get("function", {}).get("name")
        ]
        info.hook_names = list(meta.get("hook_names") or [])
        hints = meta.get("approval_hints") or {}
        if isinstance(hints, dict):
            for tname, hint in hints.items():
                if isinstance(tname, str) and isinstance(hint, dict):
                    info.approval_hints[tname] = {
                        "approval": str(hint.get("approval", "plugin")),
                        "risk": str(hint.get("risk", "")),
                    }

        veto = self._veto(
            "before_plugin_register", name=info.name,
            tools=info.tools, isolation="process",
        )
        if veto is not None:
            info.enabled = False
            info.error = f"plugin registration vetoed by a hook: {veto}"
            self.plugins.append(info)
            return
        adapter = _RemotePluginAdapter(
            info, raw_tools, info.hook_names,
            self.isolation_manager(), self,
        )
        registry.register_plugin(adapter)
        self.plugins.append(info)
        self._emit(
            "after_plugin_register", name=info.name,
            enabled=info.enabled, tools=info.tools, isolation="process",
        )

    def _base_ctx_dict(self, plugin_name: str) -> Dict[str, Any]:
        return {
            "plugin_name": plugin_name,
            "project_root": "",
            "app_dir": os.path.expanduser("~"),
            "config": dict(self.config),
        }

    def _fill_metadata(self, info: PluginInfo, module: Any,
                       manifest: Optional[dict]) -> None:
        """In-process path: read metadata from the module (consistent with P3 behavior)."""
        header_name = getattr(module, "PLUGIN_NAME", None)
        if isinstance(header_name, str) and header_name.strip():
            info.name = header_name.strip()
        pub = getattr(module, "PLUGIN_PUBLISHER", None)
        if isinstance(pub, str):
            info.publisher = pub.strip()
        if manifest:
            info.version = manifest.get("version", info.version)
            info.publisher = manifest.get("publisher",
                                         manifest.get("author", info.publisher))
            info.description = manifest.get("description", info.description)
        else:
            ver = getattr(module, "PLUGIN_VERSION", None)
            if isinstance(ver, str):
                info.version = ver.strip()
            dsc = getattr(module, "PLUGIN_DESCRIPTION", None)
            if isinstance(dsc, str):
                info.description = dsc.strip()

        raw_tools = getattr(module, "TOOLS", None)
        info.tools = [
            t.get("function", {}).get("name", "")
            for t in (raw_tools or [])
            if isinstance(t, dict) and t.get("function", {}).get("name")
        ]
        info.hook_names = [h for h in HOOK_NAMES if callable(getattr(module, h, None))]
        raw_hints = getattr(module, "APPROVAL_HINTS", None)
        if isinstance(raw_hints, dict):
            for tname, hint in raw_hints.items():
                if isinstance(tname, str) and isinstance(hint, dict):
                    info.approval_hints[tname] = {
                        "approval": str(hint.get("approval", "plugin")),
                        "risk": str(hint.get("risk", "")),
                    }

    def _decide_isolation(self, path: str,
                          manifest: Optional[dict]) -> str:
        """Isolation mode decision: config explicit value > manifest > plugin module constant."""
        if self.plugin_isolation in ("inproc", "process"):
            return self.plugin_isolation
        if manifest:
            declared = manifest.get("isolation")
            if declared in ("inproc", "process"):
                return declared
        pref = self._static_isolation_pref(path)
        return pref if pref in ("inproc", "process") else "inproc"

    @staticmethod
    def _static_isolation_pref(path: str) -> str:
        """Read the plugin's module-level ISOLATION constant via AST (without executing plugin code)."""
        try:
            with open(path, "r", encoding="utf-8") as fh:
                tree = ast.parse(fh.read())
        except Exception:
            return ""
        for node in tree.body:
            if isinstance(node, ast.Assign):
                targets = node.targets
                if len(targets) == 1 and isinstance(targets[0], ast.Name) \
                        and targets[0].id == "ISOLATION":
                    if isinstance(node.value, ast.Constant) \
                            and isinstance(node.value.value, str):
                        return node.value.value
        return ""

    def _exec_module(self, info: PluginInfo, path: str) -> Any:
        """Execute the plugin module under import-blocker protection."""
        # ★ static import precheck: the runtime meta_path blocker is ineffective
        #   for modules already cached by the main process (e.g. subprocess —
        #   sys.modules hits directly), so under safe/strict modes the plugin
        #   source's imports are first checked statically via AST; restricted
        #   modules reject loading outright.
        if self.import_restriction in ("safe", "strict"):
            violation = self._static_import_violation(path)
            if violation:
                info.enabled = False
                info.error = (
                    f"import blocked: '{violation}'"
                    " (plugin security import restrictions forbid loading this module)"
                )
                return None

        mod_name = f"{PLUGIN_MODULE_PREFIX}{info.name}"
        spec = importlib.util.spec_from_file_location(mod_name, path)
        if spec is None or spec.loader is None:
            info.enabled = False
            info.error = f"cannot construct a module spec: {path}"
            return None
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module

        blocker: Optional[_ImportBlocker] = None
        if self.import_restriction in ("safe", "strict"):
            blocked = set(DANGEROUS_IMPORTS_FOR_BLOCK)
            blocker = _ImportBlocker(
                blocked, strict=(self.import_restriction == "strict")
            )
            blocker.register()
        try:
            _loading_plugin.active = True
            spec.loader.exec_module(module)
        except ImportError as exc:
            info.enabled = False
            info.error = f"import blocked: {exc}"
            sys.modules.pop(spec.name, None)
            return None
        except Exception as exc:  # noqa: BLE001
            info.enabled = False
            info.error = f"plugin load failed: {type(exc).__name__}: {exc}"
            sys.modules.pop(spec.name, None)
            return None
        finally:
            _loading_plugin.active = False
            if blocker is not None:
                blocker.unregister()
        return module

    @staticmethod
    def _check_module_name(name: str, blocked: Set[str], strict: bool) -> Optional[str]:
        root = name.split(".")[0]
        if strict:
            if name in STRICT_SAFE_MODULES or any(
                name == m or name.startswith(m + ".") for m in STRICT_SAFE_MODULES
            ):
                return None
            return name
        if root in blocked:
            return name
        return None

    def _static_import_violation(self, path: str) -> Optional[str]:
        """Statically check the plugin source for restricted imports (safe / strict modes)."""
        import ast

        try:
            with open(path, "r", encoding="utf-8") as fh:
                source = fh.read()
            tree = ast.parse(source)
        except Exception:
            return None
        blocked = set(DANGEROUS_IMPORTS_FOR_BLOCK) | ALWAYS_BLOCKED
        strict = self.import_restriction == "strict"
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    violation = self._check_module_name(alias.name, blocked, strict)
                    if violation:
                        return violation
            elif isinstance(node, ast.ImportFrom):
                mod = node.module or ""
                if mod:
                    violation = self._check_module_name(mod, blocked, strict)
                    if violation:
                        return violation
        return None

    def unload(self, registry: Any, plugin_name: str) -> bool:
        """Unload a single plugin (for hot-reload development)."""
        mod_name = f"{PLUGIN_MODULE_PREFIX}{plugin_name}"
        sys.modules.pop(mod_name, None)
        with self._lock:
            before = len(self.plugins)
            self.plugins = [p for p in self.plugins if p.name != plugin_name]
            self._contexts.pop(plugin_name, None)
        if len(self.plugins) == before:
            return False
        # note: tools/hooks stay in the Registry (since EventBus has no
        # by-name unsubscribe, rebuilding the Registry is recommended in production).
        return True

    def reload(self, registry: Any, plugin_name: str) -> bool:
        """Reload a single plugin (rediscover the same-named file → rerun the full security pipeline).

        Note: the old instance's tools/hook subscriptions stay on the bus;
        rebuilding the Registry is recommended in production; this method is for
        dev-time hot reload.
        """
        info = next((p for p in self.plugins if p.name == plugin_name), None)
        if info is None:
            return False
        path = info.path
        manifest = None
        if not os.path.isfile(path):
            return False
        self.unload(registry, plugin_name)
        self._load_from_file(registry, plugin_name, path, manifest)
        return True

    def shutdown(self) -> None:
        """Release resources such as the process-isolation host child process."""
        if self._isolation_manager is not None:
            try:
                self._isolation_manager.shutdown()
            except Exception:
                pass
            self._isolation_manager = None


def install_plugin_dirs(registry: Any, plugin_dirs: List[str],
                        config: Optional[dict] = None) -> PluginLoader:
    """One-shot convenience entry: load plugin directories and register into the Registry.

    When ``config`` is absent, ``registry.security`` (the security policy installed
    by norpagent.safe()) is adopted automatically as the fallback config — with
    the security system as a plug, plugin loading inherits the global security
    posture by default.
    """
    if config is None:
        security = getattr(registry, "security", None)
        if security is not None:
            plugin_config = getattr(security, "plugin_config", None)
            if callable(plugin_config):
                config = plugin_config()
    loader = PluginLoader(plugin_dirs, config)
    loader.discover_and_load(registry)
    # work rollback: plugin installation = a system change → auto snapshot (failures silent)
    try:
        from norpagent.recovery import notify_system_change

        notify_system_change(
            description="plugin install: " + ", ".join(
                str(d) for d in (plugin_dirs or [])[:3]))
    except Exception:  # noqa: BLE001
        pass
    return loader
