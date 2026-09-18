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
import inspect
import json
import os
import re
import sys
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from norpagent.protocols.tool import Tool, ToolResult
from norpagent.security.audit import Severity, SourceAuditor
from norpagent.security.approval import ApprovalPolicy
from norpagent.security.network_policy import NetworkPolicy
from norpagent.security.signature import SignatureResult, SignatureStatus, SignatureVerifier

# ── plugin hook surface ─────────────────────────────────────────────
# LEGACY (16): hook names aligned with the existing application (same event
#   names; legacy argument signatures preserved by the bridge).
# NATIVE (29): the kernel's complete 9-layer hook surface — plugins may define
#   any of these names; the 13 native-only hooks use the payload-derived
#   argument mapping (business arguments first, PluginContext last).
LEGACY_HOOK_NAMES = [
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

# the kernel's full standard hook surface (9 layers / 29 hooks; see hooks/standard.py)
NATIVE_HOOK_NAMES = [
    "on_agent_init",
    "on_agent_shutdown",
    "on_task_start",
    "on_task_done",
    "on_task_error",
    "on_task_stopped",
    "on_task_timeout",
    "before_input",
    "after_input",
    "on_user_input_required",
    "before_session_create",
    "after_session_create",
    "before_message_append",
    "after_message_append",
    "before_build_messages",
    "after_build_messages",
    "before_step",
    "after_step",
    "before_model_call",
    "after_model_call",
    "on_reasoning",
    "on_content",
    "on_event",
    "on_usage_update",
    "before_tool_call",
    "after_tool_call",
    "on_tool_error",
    "before_result",
    "after_result",
]

# external modules / the host child process detect plugin hooks through this name
HOOK_NAMES = NATIVE_HOOK_NAMES

# every hook that can rewrite the data flow through return values
_MUTATING_HOOKS = {
    "before_step", "before_tool_call", "after_tool_call",
    "before_input", "before_session_create", "before_message_append",
    "before_build_messages", "after_build_messages",
    "before_model_call", "after_model_call",
    "before_result", "after_result",
}

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


class PluginLogger:
    """Per-plugin logger handed to plugins as ``ctx.logger`` / ``api.logger``.

    Writes to stdout and, best-effort, to a per-plugin log file under the host
    log directory (config ``plugin_log_dir``; default ``~/.norpagent/plugin_logs``).
    Never raises into plugin code.
    """

    def __init__(self, plugin_name: str, log_dir: str = "") -> None:
        self._name = plugin_name
        self._log_dir = log_dir
        self._path = ""
        if log_dir:
            safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", plugin_name) or "plugin"
            self._path = os.path.join(log_dir, safe + ".log")

    def _emit(self, level: str, msg: Any) -> None:
        try:
            from datetime import datetime
            ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            line = f"[{ts}] [{level.upper()}] [{self._name}] {msg}"
            print(line)
            if self._path:
                os.makedirs(self._log_dir, exist_ok=True)
                with open(self._path, "a", encoding="utf-8") as fh:
                    fh.write(line + "\n")
        except Exception:
            pass

    def debug(self, msg: Any) -> None:
        self._emit("debug", msg)

    def info(self, msg: Any) -> None:
        self._emit("info", msg)

    def warn(self, msg: Any) -> None:
        self._emit("warn", msg)

    def error(self, msg: Any) -> None:
        self._emit("error", msg)


@dataclass
class PluginContext:
    """Context passed to external plugin hooks / execute.

    Aligned with the existing application's PluginContext and extended with
    ``storage`` (per-plugin state store that survives across hooks/tools) and
    ``logger`` (per-plugin logger) — both are part of the compatibility
    contract, plugins written against the legacy format rely on them.
    """

    plugin_name: str = ""
    project_root: str = ""
    app_dir: str = ""
    config: Dict[str, Any] = field(default_factory=dict)
    current_step: int = 0
    total_usage: Dict[str, Any] = field(default_factory=dict)
    storage: Dict[str, Any] = field(default_factory=dict)
    logger: Any = None
    api: Any = None


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
    warnings: List[str] = field(default_factory=list)
    approval_hints: Dict[str, dict] = field(default_factory=dict)
    audit_issues: List[dict] = field(default_factory=list)
    # ── isolation / capability / diagnostics surface (2026-09-11 plugin overhaul) ──
    isolation: str = "inproc"                      # actual runtime mode: inproc / process
    capabilities: List[str] = field(default_factory=list)   # declared capability surface (setup API gates)
    requires: Dict[str, Any] = field(default_factory=dict)  # dependency declarations (requires / min_norpagent)
    diagnostics: List[Dict[str, Any]] = field(default_factory=list)  # bounded runtime failure records
    counts: Dict[str, int] = field(default_factory=dict)    # hook / tool call counters
    module: Any = None
    api: Any = None

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
            "warnings": list(self.warnings),
            "approval_hints": dict(self.approval_hints),
            "audit_issues": list(self.audit_issues),
            "isolation": self.isolation,
            "capabilities": list(self.capabilities),
            "requires": dict(self.requires),
            "diagnostics": list(self.diagnostics[-20:]),
            "counts": dict(self.counts),
        }


# ── import blocker (consistent with the existing application's PluginImportBlocker / StrictImportBlocker) ─


class _ImportBlocker:
    """sys.meta_path import blocker: only affects plugin modules (stack-frame probing)."""

    def __init__(self, blocked: Set[str], strict: bool = False,
                 warn_only: bool = False,
                 warnings: Optional[List[str]] = None) -> None:
        self.blocked = blocked
        self.strict = strict
        # soft 挡（2026-09-15）：命中受限导入时只记录、不拦截（放行并转成警告）
        self.warn_only = warn_only
        self.warnings: List[str] = warnings if warnings is not None else []
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
            if self.warn_only:
                self.warnings.append(
                    f"restricted import '{fullname}' allowed "
                    "(soft mode: recorded only, not blocked)"
                )
                return None
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
        self._loader.bump_count(self._plugin_name, f"tool:{self.name}")
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


# event payload → plugin hook argument conversion table.
# value = the payload keys taken (in order); PluginContext is appended last.
# The 16 legacy hooks keep the existing application's signature convention; the
# 13 native-only hooks follow the same "business arguments first" style
# (derived from the kernel hook payload keys, see hooks/standard.py payload_keys).
_HOOK_ARG_KEYS: Dict[str, Tuple[str, ...]] = {
    # ── legacy 16 (existing-application plugin signatures; full compatibility) ──
    "on_agent_init": (),
    "on_agent_shutdown": (),
    "on_task_start": ("user_input",),
    "on_task_done": ("content",),
    "on_task_error": ("error",),
    "on_task_stopped": (),            # legacy signature is (context); a 2+ positional function gets (reason, context)
    "on_task_timeout": ("timeout",),
    "before_step": ("step", "messages"),
    "after_step": ("step", "reasoning", "content", "tool_calls"),
    "before_tool_call": ("tool_name", "args"),
    "after_tool_call": ("tool_name", "args"),
    "on_user_input_required": ("question",),
    "on_reasoning": ("content",),
    "on_content": ("content",),
    "on_event": ("event_type", "data"),
    "on_usage_update": (),            # converted below (legacy usage dict, both key styles)
    # ── native-only 13 (the kernel's remaining 9-layer hook surface) ──
    "before_input": ("user_input", "session_id", "params"),
    "after_input": ("user_input", "session_id"),
    "before_session_create": ("session_id", "title", "params"),
    "after_session_create": ("session_id", "title"),
    "before_message_append": ("session_id", "message"),
    "after_message_append": ("session_id", "message"),
    "before_build_messages": ("system_prompt", "session_id", "step", "tool_names"),
    "after_build_messages": ("messages", "system_prompt", "step"),
    "before_model_call": ("step", "messages", "tool_schemas", "params"),
    "after_model_call": ("step", "output"),
    "on_tool_error": ("tool_name", "error", "args"),
    "before_result": ("result",),
    "after_result": ("result",),
}


def _positional_capacity(fn: Callable) -> Optional[int]:
    """Max positional arguments *fn* accepts (excluding *args); None when unknown.

    A function declaring *args returns a large sentinel (accepts everything).
    """
    try:
        sig = inspect.signature(fn)
    except (TypeError, ValueError):
        return None
    count = 0
    for param in sig.parameters.values():
        if param.kind in (param.POSITIONAL_ONLY, param.POSITIONAL_OR_KEYWORD):
            count += 1
        elif param.kind == param.VAR_POSITIONAL:
            return 10 ** 6
    return count


def _build_hook_args(hook_name: str, payload: Dict[str, Any]) -> List[Any]:
    """Build the positional argument list from an event payload (PluginContext appended by the caller).

    Legacy signature: business arguments first, PluginContext last — fully
    consistent with the existing application's plugin_system dispatch logic.
    """
    keys = _HOOK_ARG_KEYS.get(hook_name, ())
    args: List[Any] = [payload.get(k) for k in keys]
    if hook_name == "after_tool_call":
        # legacy format: (tool_name, args, result, ctx)
        args.append(str(payload.get("result") or ""))
    elif hook_name == "on_task_done":
        # legacy format: (summary, final_reply, ctx); the kernel reports one
        # content value, so both positional slots carry it
        args.append(payload.get("content") or "")
    elif hook_name == "after_step":
        # legacy format: (step, reasoning, content, tool_calls, ctx)
        tool_calls = payload.get("tool_calls")
        if isinstance(tool_calls, int):
            tool_calls = []  # older kernel payloads carried only the count
        args = [
            payload.get("step", 0),
            payload.get("reasoning", "") or "",
            payload.get("content", "") or "",
            tool_calls or [],
        ]
    elif hook_name == "on_usage_update":
        # both key styles are provided: legacy (input_tokens / output_tokens /
        # tool_call_tokens) and kernel (input / output / total)
        args = [{
            "input_tokens": payload.get("input", 0),
            "output_tokens": payload.get("output", 0),
            "tool_call_tokens": 0,
            "input": payload.get("input", 0),
            "output": payload.get("output", 0),
            "total": payload.get("total", 0),
        }]
    return args


def _hook_args_for_callable(hook_name: str, payload: Dict[str, Any],
                            fn: Callable) -> List[Any]:
    """Build the positional argument list for a concrete hook *fn*.

    Compatibility shims on top of ``_build_hook_args``:

    - ``on_task_stopped``: the legacy signature is ``(context)``; a function
      accepting two or more positional arguments is treated as the extended
      form ``(reason, context)`` — both styles are supported.
    """
    if hook_name == "on_task_stopped":
        capacity = _positional_capacity(fn)
        if capacity is None:
            return []
        return [payload.get("reason")] if capacity >= 2 else []
    return _build_hook_args(hook_name, payload)


# ── pass-through normalization (legacy compatibility) ────────────────
# A mutating hook returning its own input unchanged (the legacy "return
# messages / return args / return result" idiom) is treated as "no rewrite"
# (None): otherwise it would occupy the bus's first-non-None slot and shadow
# later subscribers' rewrites. Keys map to the payload values to compare.
_PASSTHROUGH_COMPARE: Dict[str, Callable[[Dict[str, Any]], Tuple[Any, ...]]] = {
    "before_step": lambda p: (p.get("messages"),),
    "before_tool_call": lambda p: (p.get("args"),),
    "after_tool_call": lambda p: (str(p.get("result") or ""),),
    "before_input": lambda p: (p.get("user_input"),),
    "before_session_create": lambda p: (p.get("title"),),
    "before_message_append": lambda p: (p.get("message"),),
    "before_build_messages": lambda p: (p.get("system_prompt"),),
    "after_build_messages": lambda p: (p.get("messages"),),
    "before_result": lambda p: (p.get("result"),),
    "after_result": lambda p: (p.get("result"),),
}


def _normalize_mutating_result(hook_name: str, payload: Dict[str, Any],
                               result: Any) -> Any:
    """Legacy pass-through normalization for mutating-hook return values."""
    if result is None or hook_name not in _PASSTHROUGH_COMPARE:
        return result
    try:
        candidates = _PASSTHROUGH_COMPARE[hook_name](payload)
    except Exception:  # noqa: BLE001
        return result
    for candidate in candidates:
        if result is candidate:
            return None
        try:
            if result == candidate:
                return None
        except Exception:  # noqa: BLE001
            pass
    return result


def _version_tuple(version: str) -> Tuple[int, ...]:
    """Parse a dotted version into a comparable tuple ("2.0.1" -> (2, 0, 1))."""
    parts: List[int] = []
    for chunk in str(version or "").split("."):
        digits = "".join(ch for ch in chunk if ch.isdigit())
        parts.append(int(digits) if digits else 0)
    return tuple(parts)


def _wrap_hook(hook_name: str, fn: Callable, loader: "PluginLoader",
               plugin_name: str) -> Callable:
    """Wrap a legacy hook function into an EventBus subscriber (receiving an AgentEvent).

    Signature convention: business arguments first, PluginContext last; return
    values of mutating hooks pass through to the kernel via EventBus.intercept
    (first non-None wins; pass-through returns are normalized to None so they do
    not shadow later subscribers); return values of observation hooks are
    ignored. Hook failures are reported through the loader diagnostics channel —
    never silently swallowed.
    """

    def listener(event: Any) -> Any:
        payload = getattr(event, "payload", {}) or {}
        try:
            args = _hook_args_for_callable(hook_name, payload, fn)
            ctx = loader.plugin_context(plugin_name, payload.get("context"))
            args.append(ctx)
        except Exception as exc:  # noqa: BLE001 — argument building must never break the bus
            loader.report_hook_failure(plugin_name, hook_name, exc)
            return None
        loader.bump_count(plugin_name, f"hook:{hook_name}")
        try:
            result = fn(*args)
        except Exception as exc:  # noqa: BLE001 — plugin errors must never break the main loop
            loader.report_hook_failure(plugin_name, hook_name, exc)
            return None
        return _normalize_mutating_result(hook_name, payload, result)

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
        self._tools_cache: Optional[List[Tool]] = None
        self._hooks_cache: Optional[Dict[str, Callable]] = None

    def get_tools(self) -> List[Tool]:
        if self._tools_cache is not None:
            return list(self._tools_cache)
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
        self._tools_cache = list(tools)
        return tools

    def get_hooks(self) -> Dict[str, Callable]:
        # cached: every call returns the same listener objects, so
        # EventBus.unsubscribe can actually remove them on unload / hot reload
        # (2026-09-11 fix: rebuilding wrappers per call made unload a no-op).
        if self._hooks_cache is not None:
            return dict(self._hooks_cache)
        hooks: Dict[str, Callable] = {}
        for hook_name in HOOK_NAMES:
            fn = getattr(self.module, hook_name, None)
            if callable(fn):
                hooks[hook_name] = _wrap_hook(hook_name, fn, self.loader, self.info.name)
        self._hooks_cache = dict(hooks)
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
        self._tools_cache: Optional[List[Tool]] = None
        self._hooks_cache: Optional[Dict[str, Callable]] = None

    def get_tools(self) -> List[Tool]:
        if self._tools_cache is not None:
            return list(self._tools_cache)
        tools: List[Tool] = []
        for tool_def in self._tool_schemas:
            func = tool_def.get("function", {}) if isinstance(tool_def, dict) else {}
            tname = func.get("name", "")
            if tname:
                tools.append(_RemoteToolAdapter(
                    tname, tool_def, self.name, self._manager, self._loader,
                ))
        self._tools_cache = list(tools)
        return tools

    def get_hooks(self) -> Dict[str, Callable]:
        """Hook bridge: event → argument list → host child fire_hook RPC.

        Cached (same listener objects returned on every call, so unload can
        unsubscribe them). Mutating hooks' return values pass through to the
        kernel via EventBus.intercept; fire_hook executes in a daemon thread with
        a bounded wait (HOOK_TIMEOUT) and returns None on timeout abandonment —
        plugin hooks never stall the main loop.
        """
        if self._hooks_cache is not None:
            return dict(self._hooks_cache)
        loader = self._loader
        manager = self._manager
        plugin_name = self.name

        def bridge(hook_name: str):
            def listener(event: Any) -> Any:
                payload = getattr(event, "payload", {}) or {}
                # remote path: full-information args; the host child trims them to
                # the plugin function's positional capacity (on_task_stopped)
                args = _build_hook_args(hook_name, payload)
                if hook_name == "on_task_stopped":
                    args = [payload.get("reason")]
                plugin_ctx = loader.plugin_context(
                    plugin_name, payload.get("context")
                )
                loader.bump_count(plugin_name, f"hook:{hook_name}")
                result = manager.fire_hook(
                    plugin_name, hook_name, args,
                    _plugin_ctx_dict(plugin_ctx),
                )
                return _normalize_mutating_result(hook_name, payload, result)

            return listener

        hooks: Dict[str, Callable] = {}
        for hook_name in self._hook_names:
            hooks[hook_name] = bridge(hook_name)
        self._hooks_cache = dict(hooks)
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


# ── setup(api) registration facade (2026-09-11 plugin overhaul) ──


class PluginCapabilityError(RuntimeError):
    """Raised when a plugin calls a setup API beyond its declared capability surface."""


def _default_tool_schema(name: str, description: str) -> Dict[str, Any]:
    """Minimal OpenAI function schema for dynamically registered tools."""
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description or f"Plugin tool {name}",
            "parameters": {
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
        },
    }


class _FunctionTool:
    """Tool adapter for handlers registered dynamically via ``api.register_tool``.

    Handler signature: ``handler(args)`` or ``handler(args, plugin_ctx)`` — the
    two-argument form is detected from the function signature. Return values:
    str / ToolResult / None (None becomes an empty successful result).
    """

    def __init__(self, name: str, schema: Dict[str, Any], handler: Callable,
                 loader: "PluginLoader", plugin_name: str) -> None:
        self.name = name
        self._schema = schema
        self._handler = handler
        self._loader = loader
        self._plugin_name = plugin_name

    def schema(self) -> Dict[str, Any]:
        return self._schema

    def run(self, args: Dict[str, Any], ctx: Any) -> ToolResult:
        plugin_ctx = self._loader.plugin_context(self._plugin_name, ctx)
        self._loader.bump_count(self._plugin_name, f"tool:{self.name}")
        try:
            capacity = _positional_capacity(self._handler)
            if capacity is not None and capacity >= 2:
                output = self._handler(args or {}, plugin_ctx)
            else:
                output = self._handler(args or {})
        except Exception as exc:  # noqa: BLE001 — plugin errors become failed ToolResults
            return ToolResult(
                output=f"plugin tool execution error: {type(exc).__name__}: {exc}",
                success=False,
                error=f"{type(exc).__name__}: {exc}",
            )
        if isinstance(output, ToolResult):
            return output
        return ToolResult(output=str(output))


class PluginAPI:
    """Registration facade handed to a plugin's ``setup(api)`` (in-process plugins).

    Everything a plugin registers through this object is attributed to the plugin:
    bus subscriptions / custom slots / services are undone on unload; tool /
    component / model / session / sandbox / scheduler / UI / hook registrations
    use the framework's name-overwrite semantics (a same-named registration
    replaces the previous one).

    Capability gates: ``PLUGIN_CAPABILITIES`` (list) or ``manifest.capabilities``
    declares the surface; absent declarations grant the base set
    (tools / hooks / events). Undeclared advanced capabilities raise
    :class:`PluginCapabilityError` at registration time. ``"*"`` / ``"all"``
    declares everything; the host may further restrict via the
    ``plugin_capabilities`` config key.

    Supported capability names: tools / hooks / events / slots / components /
    models / sessions / sandboxes / schedulers / uis / services / pages / cli /
    settings.
    """

    _SAFE_NAME = re.compile(r"[^A-Za-z0-9_.-]+")

    def __init__(self, loader: "PluginLoader", info: PluginInfo, module: Any,
                 registry: Any) -> None:
        self._loader = loader
        self._info = info
        self._module = module
        self._registry = registry
        self.name = info.name
        self.package_dir = os.path.dirname(os.path.abspath(info.path)) if info.path else ""
        self.config = dict(loader.config)
        ctx = loader.plugin_context(info.name)
        self.logger = ctx.logger
        ctx.api = self
        self._subscriptions: List[Tuple[str, Callable]] = []
        self._slots: List[str] = []
        self._services: List[str] = []
        self._commands: List[str] = []
        self._tools: List[str] = []
        self._components: List[Tuple[str, str]] = []

    # ── gate ─────────────────────────────────────────────

    def _require(self, capability: str) -> None:
        if not self._loader.allows_capability(self._info, capability):
            raise PluginCapabilityError(
                f"plugin {self.name!r} did not declare the {capability!r} capability "
                f"(add it to PLUGIN_CAPABILITIES / manifest.capabilities)"
            )

    # ── tools ────────────────────────────────────────────

    def register_tool(self, name: str, handler: Callable, *,
                      schema: Optional[Dict[str, Any]] = None,
                      description: str = "") -> None:
        """Register a dynamic tool with a direct handler (beyond the static TOOLS list)."""
        self._require("tools")
        if not name or not callable(handler):
            raise ValueError("register_tool requires a name and a callable handler")
        if schema is None:
            schema = _default_tool_schema(name, description)
        elif isinstance(schema, dict) and "function" not in schema:
            schema = {"type": "function", "function": schema}
        self._registry.register_tool(name, _FunctionTool(
            name, schema, handler, self._loader, self.name,
        ))
        if name not in self._info.tools:
            self._info.tools.append(name)
        if name not in self._tools:
            self._tools.append(name)

    # ── slots / components / models / sessions / sandboxes / schedulers / uis ──

    def register_slot(self, spec: Any) -> None:
        """Register a custom architecture slot (a SlotSpec instance or a field dict)."""
        self._require("slots")
        from norpagent.arch.slots import SlotSpec, register_slot
        if isinstance(spec, dict):
            spec = SlotSpec(**spec)
        register_slot(spec)
        self._slots.append(spec.name)

    def unregister_slot(self, name: str) -> None:
        self._require("slots")
        from norpagent.arch.slots import unregister_slot
        unregister_slot(name)
        if name in self._slots:
            self._slots.remove(name)

    def register_component(self, kind: str, name: str, factory: Callable) -> None:
        """Register a generic component (kind + name + factory)."""
        self._require("components")
        self._registry.register_component(kind, name, factory)
        if (kind, name) not in self._components:
            self._components.append((kind, name))

    def register_model(self, name: str, provider: Any) -> None:
        self._require("models")
        self._registry.register_model(name, provider)

    def register_session(self, name: str, factory: Callable) -> None:
        self._require("sessions")
        self._registry.register_session(name, factory)

    def register_sandbox(self, name: str, factory: Callable) -> None:
        self._require("sandboxes")
        self._registry.register_sandbox(name, factory)

    def register_scheduler(self, name: str, factory: Callable) -> None:
        self._require("schedulers")
        self._registry.register_scheduler(name, factory)

    def register_ui(self, name: str, adapter: Any) -> None:
        self._require("uis")
        self._registry.register_ui(name, adapter)

    # ── hooks / events ───────────────────────────────────

    def define_hook(self, name: str, *, mutating: bool = False,
                    description: str = "") -> None:
        """Define a custom hook on the engine hook system (dynamic layer when unnamed elsewhere)."""
        self._require("hooks")
        self._registry.hooks.define_hook(
            name, mutating=mutating, description=description,
        )

    def subscribe(self, event: str, fn: Callable) -> None:
        """Subscribe to any bus event (standard hooks / custom hooks / custom events)."""
        self._require("events")
        self._registry.bus.subscribe(fn, event)
        self._subscriptions.append((event, fn))

    def emit(self, event: str, **payload: Any) -> None:
        """Publish an event on the engine bus."""
        self._require("events")
        self._registry.bus.emit(event, **payload)

    # ── services ─────────────────────────────────────────

    def provide(self, name: str, obj: Any) -> None:
        """Provide a service object (plugin-to-plugin / plugin-to-host communication)."""
        self._require("services")
        self._registry.register_service(name, obj)
        self._services.append(name)

    def get(self, name: str, default: Any = None) -> Any:
        """Resolve a service registered by this or another plugin / the host."""
        self._require("services")
        return self._registry.resolve_service(name, default)

    # ── pages / cli / settings ───────────────────────────

    def mount_page(self, page: str, html: Any) -> bool:
        """Mount an HTML page onto the Web UI ("front" / "flow" / "farstars").

        When no Web frontend is attached yet (plugins loaded before the engine
        starts), the request is queued on the registry and consumed by the Web
        frontend at attach time. Returns whether the mount applied immediately.
        """
        self._require("pages")
        frontend = self._find_web_frontend()
        if frontend is not None:
            frontend.mount_page(page, html)
            return True
        pending = getattr(self._registry, "_pending_page_mounts", None)
        if pending is None:
            pending = {}
            setattr(self._registry, "_pending_page_mounts", pending)
        pending[page] = html
        return False

    def register_cli_command(self, name: str, handler: Callable, *,
                             help: str = "") -> None:
        """Register a CLI command (listed by ``norpagent plugins commands``)."""
        self._require("cli")
        if not name or not callable(handler):
            raise ValueError("register_cli_command requires a name and a callable handler")
        self._registry.register_command(name, handler, help)
        self._commands.append(name)

    def register_settings(self, schema: Dict[str, Any]) -> None:
        """Declare a settings schema for this plugin (stored for the Web plugin panel)."""
        self._require("settings")
        store = getattr(self._registry, "_plugin_settings_schemas", None)
        if store is None:
            store = {}
            setattr(self._registry, "_plugin_settings_schemas", store)
        store[self.name] = dict(schema or {})

    def get_setting(self, key: str, default: Any = None) -> Any:
        """Read a persisted plugin setting (stored under ~/.norpagent/plugin_settings)."""
        data = self._read_settings()
        return data.get(key, default)

    def set_setting(self, key: str, value: Any) -> None:
        """Persist a plugin setting (host-side storage; plugins never touch the file)."""
        data = self._read_settings()
        data[key] = value
        self._write_settings(data)

    # ── teardown ─────────────────────────────────────────

    def teardown(self) -> None:
        """Undo the registrations done through this API (best effort; never raises).

        Cleans bus subscriptions / custom slots / services / commands / dynamic
        tools / components. Model / session / sandbox / scheduler / UI
        registrations follow the framework's name-overwrite semantics and are
        not removed (documented).
        """
        for event, fn in list(self._subscriptions):
            try:
                self._registry.bus.unsubscribe(fn, event)
            except Exception:  # noqa: BLE001
                pass
        self._subscriptions.clear()
        for slot_name in list(self._slots):
            try:
                from norpagent.arch.slots import unregister_slot
                unregister_slot(slot_name)
            except Exception:  # noqa: BLE001
                pass
        self._slots.clear()
        for svc in list(self._services):
            try:
                self._registry.remove_service(svc)
            except Exception:  # noqa: BLE001
                pass
        self._services.clear()
        for cname in list(self._commands):
            try:
                self._registry.remove_command(cname)
            except Exception:  # noqa: BLE001
                pass
        self._commands.clear()
        for tname in list(self._tools):
            try:
                self._registry.unregister_tool(tname)
            except Exception:  # noqa: BLE001
                pass
        self._tools.clear()
        for kind, cname in list(self._components):
            try:
                self._registry.unregister_component(kind, cname)
            except Exception:  # noqa: BLE001
                pass
        self._components.clear()

    # ── internals ────────────────────────────────────────

    def _find_web_frontend(self) -> Any:
        try:
            from norpagent.runtime import current as _current_engine
            engine = _current_engine()
        except Exception:  # noqa: BLE001
            engine = None
        if engine is None:
            return None
        frontend = getattr(engine, "frontend", None)
        if frontend is not None and hasattr(frontend, "mount_page"):
            return frontend
        return None

    def _settings_path(self) -> str:
        safe = self._SAFE_NAME.sub("_", self.name) or "plugin"
        return os.path.join(
            os.path.expanduser("~"), ".norpagent", "plugin_settings", safe + ".json",
        )

    def _read_settings(self) -> Dict[str, Any]:
        path = self._settings_path()
        try:
            with open(path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    def _write_settings(self, data: Dict[str, Any]) -> None:
        path = self._settings_path()
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            tmp = path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(data, fh, ensure_ascii=False, indent=2)
            os.replace(tmp, path)
        except OSError:
            pass


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
        # ── host policy / diagnostics (2026-09-11 plugin overhaul) ──
        self.plugin_log_dir = str(config.get("plugin_log_dir") or
                                  os.path.join(os.path.expanduser("~"),
                                               ".norpagent", "plugin_logs"))
        self.disabled_plugins: Set[str] = {
            str(n) for n in (config.get("plugin_disabled") or []) if str(n).strip()
        }
        self.host_capabilities = config.get("plugin_capabilities")
        self._reported_hook_errors: Dict[Tuple[str, str, str], int] = {}
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

    # ── diagnostics / counters (never raise into the bus) ──

    def _find_info(self, plugin_name: str) -> Optional[PluginInfo]:
        for info in self.plugins:
            if info.name == plugin_name:
                return info
        return None

    def report_hook_failure(self, plugin_name: str, hook_name: str,
                            exc: Exception) -> None:
        """Report a plugin hook failure: counted, printed once per error kind,
        recorded into PluginInfo.diagnostics (bounded). Never raises.

        Replaces the old silent ``except: return None`` swallow — plugin errors
        are now visible (stdout + diagnostics + PluginInfo).
        """
        try:
            key = (plugin_name, hook_name, type(exc).__name__)
            count = self._reported_hook_errors.get(key, 0) + 1
            self._reported_hook_errors[key] = count
            if count == 1:
                message = (f"[plugin] hook {hook_name!r} of {plugin_name!r} failed: "
                           f"{type(exc).__name__}: {exc}")
                print(message)
            info = self._find_info(plugin_name)
            if info is not None:
                info.diagnostics.append({
                    "hook": hook_name,
                    "error": f"{type(exc).__name__}: {exc}",
                    "count": count,
                    "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
                })
                if len(info.diagnostics) > 50:
                    del info.diagnostics[:-50]
        except Exception:  # noqa: BLE001 — diagnostics must never break the pipeline
            pass

    def bump_count(self, plugin_name: str, key: str) -> None:
        """Increment a per-plugin call counter (hook: / tool: prefixes)."""
        try:
            info = self._find_info(plugin_name)
            if info is not None:
                info.counts[key] = info.counts.get(key, 0) + 1
        except Exception:  # noqa: BLE001
            pass

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
        """Build (or fetch from cache) the plugin context.

        The context carries the full compatibility surface: config snapshot,
        ``storage`` (per-plugin state store that survives across hooks / tools)
        and ``logger`` (per-plugin logger writing to stdout + plugin_log_dir).
        """
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
                storage={},
                logger=PluginLogger(plugin_name, self.plugin_log_dir),
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

        # host-level disable list: the plugin is listed (with its status) but not loaded
        if name in self.disabled_plugins:
            info.enabled = False
            info.error = "disabled by host configuration (plugin_disabled)"
            self.plugins.append(info)
            return

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

        # 未签名插件**仅警告**、默认不阻止加载。
        # 默认策略下 unsigned / untrusted / unavailable 一律放行但留警告
        # （info.warnings 随 /api/plugins 与 CLI 输出可见）；高安全档
        # （signature_required，上一分支）是显式收紧，不是默认。
        if not sig.is_trusted:
            warn = (
                f"plugin {name!r} is {sig.status or 'unsigned'} "
                f"(signature not trusted, reason: {sig.reason or 'n/a'}); "
                f"loading is allowed by default — add a signature or a trusted "
                f"key when ready (warn only, never block by default)"
            )
            info.warnings.append(warn)
            print(f"[plugin] warning: {warn}")

        # ── 2. trust tiering: trusted signatures get relaxed audit ──
        effective_audit = "warn" if sig.is_trusted else self.auditor.audit_level

        # ── 3. AST audit ──
        self._emit("before_plugin_audit", name=name, path=path,
                   audit_level=effective_audit)
        issues, allowed = self.auditor.audit_file(path, audit_level=effective_audit)
        # 四挡（2026-09-15）：off = 连记录都不留；notice 及以上才写入审计结果
        if effective_audit != "off":
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
        info.isolation = isolation
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

        # host-level disable list (second check: PLUGIN_NAME may differ from the file name)
        if info.name in self.disabled_plugins:
            info.enabled = False
            info.error = "disabled by host configuration (plugin_disabled)"
            self.plugins.append(info)
            return

        # ── 7.5 declarations: capability surface / dependencies / minimum version ──
        self._apply_declarations(info, module, manifest)
        problem = self._check_requirements(info)
        if problem:
            info.enabled = False
            info.error = problem
            self.plugins.append(info)
            return

        # ── 7.6 setup(api): the registration facade (tools / slots / components /
        #        models / hooks / events / services / pages / cli / settings).
        #        A setup() failure rejects the plugin and rolls back the
        #        registrations it already made (atomic-by-convention).
        if callable(getattr(module, "setup", None)):
            plugin_api = PluginAPI(self, info, module, registry)
            try:
                module.setup(plugin_api)
                info.api = plugin_api
            except Exception as exc:  # noqa: BLE001 — a failed setup rejects the plugin
                try:
                    plugin_api.teardown()
                except Exception:  # noqa: BLE001
                    pass
                info.enabled = False
                info.error = f"setup() failed: {type(exc).__name__}: {exc}"
                self.plugins.append(info)
                return

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

        # ── 9. on_load lifecycle (best effort: failures are recorded, not fatal) ──
        self._run_lifecycle(info, module, "on_load")

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
        info.isolation = "process"

        # host-level disable list (second check)
        if info.name in self.disabled_plugins:
            info.enabled = False
            info.error = "disabled by host configuration (plugin_disabled)"
            self.plugins.append(info)
            return

        # process-isolated plugins run entirely in the child process: the setup(api)
        # registration facade is not offered there (recorded as a warning, not an error)
        if meta.get("has_setup"):
            warn = (f"plugin {info.name!r} defines setup() but runs under process "
                    f"isolation; setup registration is skipped (use ISOLATION=inproc "
                    f"or the tool/hook surface instead)")
            info.warnings.append(warn)
            print(f"[plugin] warning: {warn}")

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

        # ── on_load lifecycle (relayed into the host child; best effort) ──
        try:
            manager = self.isolation_manager()
            manager.fire_hook(info.name, "on_load", [],
                              self._base_ctx_dict(info.name))
            self.bump_count(info.name, "lifecycle:on_load")
        except Exception as exc:  # noqa: BLE001 — lifecycle failure does not reject the plugin
            self.report_hook_failure(info.name, "on_load", exc)

    def _base_ctx_dict(self, plugin_name: str) -> Dict[str, Any]:
        return {
            "plugin_name": plugin_name,
            "project_root": "",
            "app_dir": os.path.expanduser("~"),
            "config": dict(self.config),
            "plugin_log_dir": self.plugin_log_dir,
        }

    # ── declarations / capabilities / lifecycle (2026-09-11 plugin overhaul) ──

    def allows_capability(self, info: PluginInfo, capability: str) -> bool:
        """Whether *info* may use *capability* (declared surface + host policy).

        Declarations come from PLUGIN_CAPABILITIES / manifest.capabilities; when
        absent, the base set (tools / hooks / events) applies. "*" / "all"
        declares everything. The host may further restrict via config
        plugin_capabilities (None = no host restriction).
        """
        declared = set(info.capabilities or [])
        if declared:
            allowed = ("all" in declared) or ("*" in declared) or (capability in declared)
        else:
            allowed = capability in ("tools", "hooks", "events")
        if allowed and self.host_capabilities is not None:
            host_set = {str(x) for x in self.host_capabilities}
            allowed = ("all" in host_set) or ("*" in host_set) or (capability in host_set)
        return allowed

    def _apply_declarations(self, info: PluginInfo, module: Any,
                            manifest: Optional[dict]) -> None:
        """Read capability / dependency declarations from the module + manifest."""
        caps = getattr(module, "PLUGIN_CAPABILITIES", None)
        if not isinstance(caps, (list, tuple)):
            caps = (manifest or {}).get("capabilities")
        if isinstance(caps, (list, tuple)):
            info.capabilities = [str(c) for c in caps]
        else:
            info.capabilities = ["tools", "hooks", "events"]

        requires: Dict[str, Any] = {}
        req = getattr(module, "PLUGIN_REQUIRES", None)
        if isinstance(req, (list, tuple)):
            requires["plugins"] = [str(r) for r in req]
        elif isinstance(req, dict):
            requires.update(req)
        min_ver = getattr(module, "PLUGIN_MIN_NORPAGENT", None)
        if isinstance(min_ver, str) and min_ver.strip():
            requires["min_norpagent"] = min_ver.strip()
        if manifest:
            m_req = manifest.get("requires")
            if isinstance(m_req, (list, tuple)):
                requires["plugins"] = [str(r) for r in m_req]
            elif isinstance(m_req, dict):
                requires.update(m_req)
            m_min = manifest.get("min_norpagent")
            if isinstance(m_min, str) and m_min.strip():
                requires["min_norpagent"] = m_min.strip()
        info.requires = requires

    def _check_requirements(self, info: PluginInfo) -> Optional[str]:
        """Validate dependency declarations; returns an error string when unmet."""
        req = info.requires or {}
        min_ver = req.get("min_norpagent")
        if isinstance(min_ver, str) and min_ver.strip():
            try:
                import norpagent as _norp
                current = str(getattr(_norp, "__version__", "") or "")
            except Exception:  # noqa: BLE001
                current = ""
            if current and _version_tuple(current) < _version_tuple(min_ver):
                return f"requires norpagent >= {min_ver.strip()} (current: {current})"
        dep_plugins = req.get("plugins") or []
        if isinstance(dep_plugins, (list, tuple)) and dep_plugins:
            loaded = {p.name for p in self.plugins if p.enabled}
            missing = [str(d) for d in dep_plugins if str(d) not in loaded]
            if missing:
                return f"missing plugin dependencies: {', '.join(missing)}"
        return None

    def _run_lifecycle(self, info: PluginInfo, module: Any,
                       hook_name: str) -> None:
        """Run an in-process plugin lifecycle function (on_load / on_unload).

        Failures are recorded through the diagnostics channel and never reject
        or break the pipeline.
        """
        fn = getattr(module, hook_name, None)
        if not callable(fn):
            return
        ctx = self.plugin_context(info.name)
        if info.api is not None:
            ctx.api = info.api
        try:
            fn(ctx)
            self.bump_count(info.name, f"lifecycle:{hook_name}")
        except Exception as exc:  # noqa: BLE001 — lifecycle failure must not break the pipeline
            self.report_hook_failure(info.name, hook_name, exc)

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
        #   sys.modules hits directly), so under soft/safe/strict modes the plugin
        #   source's imports are first checked statically via AST; restricted
        #   modules reject loading outright.
        if self.import_restriction in ("soft", "safe", "strict"):
            violation = self._static_import_violation(path)
            if violation:
                if self.import_restriction == "soft":
                    # soft 挡：只记录、不拦截
                    info.warnings.append(
                        f"restricted import '{violation}' allowed (soft mode)"
                    )
                else:
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
        if self.import_restriction in ("soft", "safe", "strict"):
            blocked = set(DANGEROUS_IMPORTS_FOR_BLOCK)
            blocker = _ImportBlocker(
                blocked,
                strict=(self.import_restriction == "strict"),
                warn_only=(self.import_restriction == "soft"),
                warnings=info.warnings,
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
        """Unload a single plugin: hooks unsubscribe, tools are removed, lifecycle runs.

        2026-09-11 clean hot reload: the plugin's hook subscriptions are really
        removed (cached listener objects), its tools are deleted from the tool
        table, setup(api) registrations are torn down (subscriptions / custom
        slots / services), on_unload runs (in-process or relayed to the host
        child), and the plugin module is dropped from sys.modules.
        """
        with self._lock:
            info = next((p for p in self.plugins if p.name == plugin_name), None)
        if info is None:
            return False

        # ── on_unload lifecycle first (the plugin is still alive) ──
        if info.isolation == "process":
            try:
                manager = self.isolation_manager()
                manager.fire_hook(info.name, "on_unload", [],
                                  self._base_ctx_dict(info.name))
                self.bump_count(info.name, "lifecycle:on_unload")
            except Exception as exc:  # noqa: BLE001
                self.report_hook_failure(info.name, "on_unload", exc)
        elif info.module is not None:
            self._run_lifecycle(info, info.module, "on_unload")

        # ── setup-registration teardown (bus subscriptions / slots / services) ──
        if info.api is not None:
            try:
                info.api.teardown()
            except Exception:  # noqa: BLE001
                pass

        # ── unregister from the registry (hook subscriptions + plugin record) ──
        try:
            registry.unregister_plugin(info.name)
        except Exception:  # noqa: BLE001 — a single plugin error must not block unloading
            pass

        # ── remove this plugin's tools ──
        for tname in list(info.tools or []):
            try:
                registry.unregister_tool(tname)
            except Exception:  # noqa: BLE001
                pass

        # ── module / context cleanup ──
        sys.modules.pop(f"{PLUGIN_MODULE_PREFIX}{info.name}", None)
        sys.modules.pop(f"{PLUGIN_MODULE_PREFIX}{plugin_name}", None)
        with self._lock:
            self.plugins = [p for p in self.plugins if p.name != plugin_name]
            self._contexts.pop(plugin_name, None)
            self._contexts.pop(info.name, None)
        return True

    def reload(self, registry: Any, plugin_name: str) -> bool:
        """Reload a single plugin: clean unload → full security pipeline again.

        2026-09-11: works for real now — unload removes hooks / tools /
        registrations, then the same-named file re-enters the complete pipeline
        (signature → audit → import restrictions → setup → register → on_load).
        To pick up added / removed / renamed plugins use ``discover_and_load``
        or the plugins slot remount (``np.remount(plugins=[...])``).
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
        """Release resources: on_unload for every plugin + the process-isolation host child."""
        for info in list(self.plugins):
            if not info.enabled:
                continue
            try:
                if info.isolation == "process":
                    manager = self._isolation_manager
                    if manager is not None:
                        manager.fire_hook(info.name, "on_unload", [],
                                          self._base_ctx_dict(info.name))
                elif info.module is not None:
                    self._run_lifecycle(info, info.module, "on_unload")
            except Exception:  # noqa: BLE001
                pass
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


def install_plugin_file(registry: Any, path: str,
                        config: Optional[dict] = None) -> "tuple[PluginLoader, Optional[PluginInfo]]":
    """Load a **single plugin file** through the full security pipeline.

    Programmatic hot-install entry (2026-09-11, used by evolution flows and
    external orchestrators): the file enters exactly the same pipeline as
    directory loading (signature → audit → permissions → isolation → import
    restrictions → setup → register → on_load). Only this one file is loaded —
    other files in the same directory are not touched.

    Returns ``(loader, PluginInfo | None)``; check ``info.enabled`` / ``info.error``.
    """
    path = os.path.abspath(str(path or ""))
    if not os.path.isfile(path):
        raise FileNotFoundError(f"plugin file not found: {path}")
    directory = os.path.dirname(path)
    loader = PluginLoader([directory], config)
    name = os.path.splitext(os.path.basename(path))[0]
    with loader._lock:  # same package: reuse the single-file pipeline step
        loader._registry = registry
        loader._load_from_file(registry, name, path, manifest=None)
    try:
        setattr(registry, "plugin_loader", loader)
    except Exception:  # noqa: BLE001
        pass
    info = loader.plugins[0] if loader.plugins else None
    return loader, info
