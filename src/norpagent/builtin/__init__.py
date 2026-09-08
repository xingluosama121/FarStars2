# Copyright (c) 2026 xingluosama121, MIT Licensed
"""Built-in component package: ready-to-use default components, all plugged in through the registry.

``install_defaults(registry)`` registers all built-in components;
``install_core(registry)`` registers the embedded minimal components (see its
docstring); you can also pick selectively: register only what you need and
replace the rest with custom implementations.

Since P2 the model adapters (openai_compat / anthropic) ship with the package;
their SDKs are lazily loaded on demand: without the corresponding extras,
registration and listing work normally; only actual calls give a clear
installation hint.

P3 additions:
- context management component (context_store=fts5) + context_* tools;
- project management component (project_manager=basic) + project_status tool;
- persistent task scheduler (scheduler=persistent) + task_* tools;
- pooled sandbox (sandbox=pooled);
- Web UI adapter (ui=web, zero-dependency HTTP + SSE).

Embedded optimization (v0.9):

- this package's **top-level import no longer imports** sqlite3 / http.server
  related components (FTS5 context store / SQLite sessions / persistent
  scheduler / Web UI are all on-demand imports inside install_defaults plus
  module-level __getattr__ lazy resolution) — just `import norpagent.builtin`
  pulls up no heavy dependencies;
- ``install_core()`` offers a minimal assembly that completely avoids these
  components (no disk dependencies, pure in-memory), suitable for embedded /
  edge devices / constrained environments.
"""

from __future__ import annotations

from typing import Any

from norpagent.builtin.models.mock import MockModelProvider
from norpagent.builtin.models.openai_compat import OpenAICompatProvider
from norpagent.builtin.models.anthropic import AnthropicProvider
from norpagent.builtin.tools import (
    EchoTool,
    GetTimeTool,
    RunPythonTool,
    FileReadTool,
    FileWriteTool,
    FileListTool,
    FileDeleteTool,
    FileSurgeonTool,
    SearchInFileTool,
    ExecCmdTool,
    WebSearchTool,
    WebFetchTool,
    WebExtractLinksTool,
    ContextAddTool,
    ContextSearchTool,
    ContextListTool,
    ContextDeleteTool,
    ProjectStatusTool,
    TaskSubmitTool,
    TaskListTool,
    TaskStatusTool,
    TaskCancelTool,
)
from norpagent.builtin.sessions.memory import MemorySessionManager
from norpagent.builtin.sandboxes.subprocess import SubprocessSandboxProvider
from norpagent.builtin.scheduler.simple import SimpleTaskScheduler
from norpagent.builtin.ui.console import ConsoleUI

# ── lazy import map (PEP 562 __getattr__): heavy components import only when actually used ──
_LAZY_EXPORTS = {
    "FTS5ContextStore": (
        "norpagent.builtin.context", "FTS5ContextStore"),
    "BasicProjectManager": (
        "norpagent.builtin.projects", "BasicProjectManager"),
    "SQLiteSessionManager": (
        "norpagent.builtin.sessions.sqlite", "SQLiteSessionManager"),
    "PooledSandboxProvider": (
        "norpagent.builtin.sandboxes.pooled", "PooledSandboxProvider"),
    "PersistentTaskScheduler": (
        "norpagent.builtin.scheduler.persistent", "PersistentTaskScheduler"),
    "WebUI": ("norpagent.builtin.ui.web", "WebUI"),
}


def __getattr__(name: str) -> Any:
    """Lazily import heavy components by name (compatible with from norpagent.builtin import XXX)."""
    entry = _LAZY_EXPORTS.get(name)
    if entry is None:
        raise AttributeError(f"module 'norpagent.builtin' has no attribute '{name}'")
    import importlib

    module = importlib.import_module(entry[0])
    value = getattr(module, entry[1])
    globals()[name] = value  # cache; later accesses go through the global namespace
    return value


def _all_lazy_entries() -> dict:
    """Aggregate all lazy-load maps of this package and its subpackages (context / sessions)."""
    entries = dict(_LAZY_EXPORTS)
    for sub in ("norpagent.builtin.context", "norpagent.builtin.sessions"):
        try:
            mod = __import__(sub, fromlist=["_LAZY_EXPORTS"])
            entries.update(getattr(mod, "_LAZY_EXPORTS", {}))
        except Exception:  # noqa: BLE001 — subpackage errors do not affect the main flow
            pass
    return entries


def list_loaded_lazy_modules() -> list:
    """Return the lazily-loaded module names actually imported in this process (hit via sys.modules).

    Used by the frontend / CLI to print diagnostics after startup: which heavy
    components (sqlite3 / http.server related) were really used. Unloaded lazy
    modules do not appear in the result.
    """
    import sys

    loaded = {mod for mod, _ in _all_lazy_entries().values() if mod in sys.modules}
    return sorted(loaded)


def install_defaults(registry: Any) -> Any:
    """Register all built-in components into the registry; returns the registry itself (for chaining)."""
    # heavy components imported on demand: sqlite3 / http.server dependencies only enter on full assembly
    from norpagent.builtin.context import FTS5ContextStore
    from norpagent.builtin.projects import BasicProjectManager
    from norpagent.builtin.sessions.sqlite import SQLiteSessionManager
    from norpagent.builtin.sandboxes.pooled import PooledSandboxProvider
    from norpagent.builtin.scheduler.persistent import PersistentTaskScheduler
    from norpagent.builtin.ui.web import WebUI

    # models
    registry.register_model("mock", MockModelProvider())
    registry.register_model("openai_compat", OpenAICompatProvider())
    registry.register_model("anthropic", AnthropicProvider())
    # tools (basic)
    registry.register_tool("echo", EchoTool())
    registry.register_tool("get_time", GetTimeTool())
    registry.register_tool("run_python", RunPythonTool())
    # tools (files: workspace path safety constraints)
    registry.register_tool("file_read", FileReadTool())
    registry.register_tool("file_write", FileWriteTool())
    registry.register_tool("file_list", FileListTool())
    registry.register_tool("file_delete", FileDeleteTool())
    # tools (files: surgical line-level edits + in-file keyword search)
    registry.register_tool("file_surgeon", FileSurgeonTool())
    registry.register_tool("search_in_file", SearchInFileTool())
    # tools (commands: sandbox protocol)
    registry.register_tool("exec_cmd", ExecCmdTool())
    # tools (web: SSRF protection, usable with zero dependencies)
    registry.register_tool("web_search", WebSearchTool())
    registry.register_tool("web_fetch", WebFetchTool())
    registry.register_tool("web_extract_links", WebExtractLinksTool())
    # tools (context management: context_store component)
    registry.register_tool("context_add", ContextAddTool())
    registry.register_tool("context_search", ContextSearchTool())
    registry.register_tool("context_list", ContextListTool())
    registry.register_tool("context_delete", ContextDeleteTool())
    # tools (project management: project_manager component)
    registry.register_tool("project_status", ProjectStatusTool())
    # tools (long-run task cooperation: scheduler)
    registry.register_tool("task_submit", TaskSubmitTool())
    registry.register_tool("task_list", TaskListTool())
    registry.register_tool("task_status", TaskStatusTool())
    registry.register_tool("task_cancel", TaskCancelTool())
    # sessions
    registry.register_session("memory", MemorySessionManager)
    registry.register_session("sqlite", SQLiteSessionManager)
    # sandboxes
    registry.register_sandbox("subprocess", SubprocessSandboxProvider().create)
    registry.register_sandbox("pooled", PooledSandboxProvider().create)
    # schedulers
    registry.register_scheduler("simple", SimpleTaskScheduler)
    registry.register_scheduler("persistent", PersistentTaskScheduler)
    # UIs
    registry.register_ui("console", ConsoleUI())
    registry.register_ui("web", WebUI())
    # generic components (context store / project management)
    registry.register_component("context_store", "fts5", FTS5ContextStore)
    registry.register_component("project_manager", "basic", BasicProjectManager)
    return registry


def install_core(registry: Any) -> Any:
    """Embedded minimal assembly: registers only the components needed for the minimal agent loop.

    Differences from ``install_defaults`` (embedded / edge / low-resource scenarios):

    - **zero disk dependencies**: does not import the FTS5 context store / SQLite
      sessions / persistent scheduler (avoids sqlite3 and filesystem persistence;
      runs purely in memory);
    - **no HTTP components**: does not import the Web UI (avoids http.server; no listening port);
    - **minimal tool set**: echo / get_time / run_python + file read/write tools
      plus streaming file_surgeon / search_in_file;
      does not register web (web_*), context (context_*), project management
      (project_status) or task cooperation (task_*) tools;
    - **empty component namespace**: context_store / project_manager are not
      registered — presets declaring them (standard etc.) cannot be assembled on
      this registry; pair with the embedded preset or a custom minimal Preset.

    Usage::

        reg = Registry()
        install_core(reg)
        from norpagent.modes import build_embedded_preset
        reg.register_preset(build_embedded_preset())
        agent = AgentRuntime(reg, preset="embedded")
        agent.run("hello")
    """
    # tools (embedded minimal set: no web / no context store / no task cooperation)
    registry.register_model("mock", MockModelProvider())
    registry.register_model("openai_compat", OpenAICompatProvider())
    registry.register_tool("echo", EchoTool())
    registry.register_tool("get_time", GetTimeTool())
    registry.register_tool("run_python", RunPythonTool())
    registry.register_tool("file_read", FileReadTool())
    registry.register_tool("file_write", FileWriteTool())
    registry.register_tool("file_list", FileListTool())
    registry.register_tool("file_delete", FileDeleteTool())
    registry.register_tool("file_surgeon", FileSurgeonTool())
    registry.register_tool("search_in_file", SearchInFileTool())
    # sessions / sandboxes / schedulers: all pure in-memory, no persistence components
    registry.register_session("memory", MemorySessionManager)
    registry.register_sandbox("subprocess", SubprocessSandboxProvider().create)
    registry.register_scheduler("simple", SimpleTaskScheduler)
    # UIs: console renderer only (no HTTP service)
    registry.register_ui("console", ConsoleUI())
    return registry


__all__ = [
    "install_defaults",
    "install_core",
    "MockModelProvider",
    "OpenAICompatProvider",
    "AnthropicProvider",
    "EchoTool",
    "GetTimeTool",
    "RunPythonTool",
    "FileReadTool",
    "FileWriteTool",
    "FileListTool",
    "FileDeleteTool",
    "FileSurgeonTool",
    "SearchInFileTool",
    "ExecCmdTool",
    "WebSearchTool",
    "WebFetchTool",
    "WebExtractLinksTool",
    "ContextAddTool",
    "ContextSearchTool",
    "ContextListTool",
    "ContextDeleteTool",
    "ProjectStatusTool",
    "TaskSubmitTool",
    "TaskListTool",
    "TaskStatusTool",
    "TaskCancelTool",
    "FTS5ContextStore",
    "BasicProjectManager",
    "MemorySessionManager",
    "SQLiteSessionManager",
    "SubprocessSandboxProvider",
    "PooledSandboxProvider",
    "SimpleTaskScheduler",
    "PersistentTaskScheduler",
    "ConsoleUI",
    "WebUI",
]
