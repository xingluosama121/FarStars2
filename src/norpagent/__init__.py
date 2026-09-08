# Copyright (c) 2026 xingluosama121, MIT Licensed
"""norpagent — pluggable, brick-style Agent framework (module as entry point).

Build an Agent like building with LEGO:

    import norpagent as np

    np()                       # run the simplest Agent entirely by default logic (default web frontend)
    running = True
    while running:
        if np.stop() == True:  # lifecycle function: exit when the application ends
            running = False

The default frontend is Web (HTTP + SSE, zero dependencies): np() starts a
background service and prints the listening address; the main thread polls the
lifecycle with np.stop(). When explicitly using the console frontend
(frontend="norpagent.frontends.console:ConsoleFrontend"), it automatically
switches to synchronous mode inside the Python interactive interpreter (>>> REPL):
np() blocks until the user exits (/exit, exit(), Ctrl+C or EOF); no polling loop needed.

Swapping parts only requires "filling in an address"; zero core-code changes:

    np(preset="standard")                        # swap the preset mode
    np(model="openai_compat")                    # swap the brain (model)
    np(async_loop="myapp.loop:create")           # swap the event loop system
    np(frontend="norpagent.frontends.web:WebFrontend")  # swap the frontend (web by default)
    np(session="sqlite", sandbox="pooled")       # swap session and sandbox

Parts can also be swapped at runtime (hot mount, no restart):

    np.remount(model="openai_compat")            # swap the model: takes effect on the next run
    np.remount(frontend="norpagent.frontends.console:ConsoleFrontend")
    np.remount(model="myapp.model:create")       # editing a module file then remounting = hot reload
    np.remount(flow_html="H:/path/flow.html")    # swap the flow page at runtime (HTTP not restarted)
    np.remount(html="H:/path/front.html")        # swap the main page at runtime

The event loop system is an independent architecture function:

    loop = np.nasyncio()                         # default loop (self-developed nasyncio core, zero asyncio dependency)
    loop = np.nasyncio("myapp.nasync:create")    # custom loop pointed to by an address

Capability overview:
- architecture layer + address functions: apart from the minimal bottom kernel
  (ArchLayer / address resolution / registry / event bus), every component is a
  slot; fill in an address to replace it;
- hot-pluggable slot table (v0.9): register_slot() / unregister_slot() register /
  unregister custom slots at runtime — registration plugs into the whole pipeline
  of np() parameter validation, assembly, np.remount() hot replacement and
  layer.describe() listing (the 18 built-in slots are protected; their values can
  be hot-replaced at any time);
- work rollback (v0.9): snapshot timeline + Undo / Redo / Rollback (np.undo() /
  np.redo() / np.rollback(), Web UI buttons / Ctrl+Z, in-process immediate);
  crash-rescue CLI norpagent-rescue (pure standard library); safe mode
  np(safemode="on") loads only the minimal kernel — see manual ch. 15;
- human rescue manual tool API (v0.9.3): when the model provider fails, take
  over every tool call by hand — norpagent-rescue tools / tool-call / manual /
  serve (HTTP API + operator page); programmatic: norpagent.rescue_api
  (RescueToolEnvironment / RescueToolAPI); no plugins, localhost-only by
  default, hard per-call timeouts;
- self-developed async scheduling core: norpagent.nasyncio (originally nasync_io,
  now packaged into the library) is the default event loop core — no dependency
  on or import of the standard asyncio;
- embedded & high concurrency (v0.9): install_core() minimal assembly + embedded
  preset (pure in-memory, headless by default, zero disk dependencies); EventBus
  copy-on-write, SSE bounded queue + batched flush, HTTP concurrency tuning — see
  the manual's "Embedded and high-concurrency deployment" chapter;
- context management: FTS5 context store (context_add / context_search / ...)
- project management: project_status (git-aware)
- long-run task cooperation: persistent scheduler (task_submit / task_list / ...)
- sandbox pool and PTC sandbox execution: pooled sandbox / run_python child-process isolation
- 9-layer 29-hook system: every execution structure is an independent API,
  subscribable / rewritable / vetoable, with custom hooks and custom layers
  (norpagent.hooks)
- security system as a whole plug: norpagent.safe() mounts the full security
  policy in one call; zero hook intervention by default (no hooks); hooks=True /
  kit.install_hooks() only then intervenes in hooks
- external plugins: norpagent.plugins (signature → audit → import restrictions →
  registration; supports process-level isolation and the PluginSystem facade)
- frontend family: console / headless / web / any custom frontend
- Web UI: ui="web" (HTTP + SSE, zero dependencies)
"""

import sys
import types as _types
from typing import Any, Dict, Optional

from norpagent.kernel import (
    Registry,
    EventBus,
    EventType,
    AgentEvent,
    Preset,
    load_preset_file,
    RunContext,
    AgentRuntime,
    RunResult,
    ComponentError,
)
from norpagent.builtin import install_defaults, install_core
from norpagent.modes import register_all_presets, build_embedded_preset
from norpagent.safe import safe, SafetyKit, SecurityContext
from norpagent import hooks  # noqa: F401  # 9-layer hook system (submodule API)
from norpagent.arch import (  # noqa: F401  # architecture layer
    ArchLayer,
    SlotSpec,
    SlotError,
    SLOT_SPECS,
    register_slot,
    unregister_slot,
    is_builtin_slot,
    snapshot_slots,
)
from norpagent.loops import (  # noqa: F401  # event loop architecture function
    nasyncio as _arch_nasyncio,
    LoopRuntime,
    NasyncioLoopRuntime,
    StdLoopRuntime,
)
# top-level np.nasyncio binds to the library's built-in self-developed scheduling
# core module (norpagent.nasyncio, originally nasync_io, now packaged into the
# library). The core module is callable: np.nasyncio() is equivalent to the
# architecture function (returns a LoopRuntime); np.nasyncio.EventLoop / Future /
# Task and other self-developed types are directly accessible. The architecture
# function itself lives in norpagent.loops.nasyncio.
nasyncio = sys.modules["norpagent.nasyncio"]
from norpagent.runtime import (
    launch,
    current,
    stop,
    submit,
    remount,
    shutdown,
    is_running,
    NorpEngine,
    EngineState,
    EngineError,
)
# work rollback (v0.9): snapshots / Undo / Redo / Rollback / crash rescue / safe mode
from norpagent import recovery
from norpagent.recovery import (  # noqa: F401
    RecoveryError,
    snapshot_system,
    undo,
    redo,
    rollback,
    list_snapshots,
    mark_good as mark_good_snapshot,
    last_good_id as last_good_snapshot,
    register_snapshot_provider,
    set_snapshot_dir,
)
from norpagent.frontends import (  # noqa: F401
    Frontend,
    ConsoleFrontend,
    HeadlessFrontend,
    WebFrontend,
)
# Central Nervous Bus (CNB) — v1.0.7 内核集成：神经实现（protocol/topology/
# permissions/bus/node/cortex）与引擎绑定层（engine.CnbAdapter）已内化为
# norpagent.cnb 子模块，import norpagent 即就绪；旧独立包名 nervous_bus
# 保留为兼容 shim（re-export 本子模块）。
from norpagent import cnb  # noqa: E402,F401  # CNB 内核子模块（中枢神经总线）

# ═══════════════════════════════════════════════════════
# 版本与品牌
# ═══════════════════════════════════════════════════════
# v2.0.0（2026-09-05）：
#   - 正式宣传名「远星 / FarStars」：norpagent 调用方式与内核名称不变，
#     FarStars 仅作宣传名/品牌冠名；代码、导入、PyPI 包名保持 norpagent。
#   - 新增能力（见 norpagent.cnb 与开发者手册 §30.17）：
#       任务分子（mol）结构化 task_params 通道 + task_records 验收回执
#       动作（audit/事件 mol_id 贯穿可追溯）；
#       隔离冻结态 freeze/unfreeze（拒新任务、保活取证、可审计可解除、
#       不触发清扫判 dead）；
#       行为基线内核侧聚合（心跳压缩上汇 + 皮层分级视图黄劣化/黑疑似恶意）；
#       subpoena 传票最高取证权限（level 0 专属不可委派、五道闸、容量分档、
#       隔离帧 RAW/UNTRUSTED、签发全审计）。
__version__ = "2.0.1"
__brand_cn__ = "远星"
__brand_en__ = "FarStars"
__display_name__ = "FarStars（远星）· norpagent"


# ═══════════════════════════════════════════════════════
#  module as entry: np() one-click start + np.stop() lifecycle polling
# ═══════════════════════════════════════════════════════

class _NorpAgentModule(_types.ModuleType):
    """Make ``np(...)`` directly usable after ``import norpagent as np``.

    Only replaces the module's __class__ (keeping module attributes such as
    __path__; submodule imports are unaffected), attaching __call__ and
    convenience methods to the module object: np() / np.stop() / np.nasyncio() etc.
    """

    def __call__(self, *args: Any, **kwargs: Any) -> NorpEngine:
        """np(...) = assemble and start the default Agent application per the architecture layer.

        Equivalent to norpagent.launch(**kwargs); returns the current engine.
        """
        return launch(*args, **kwargs)

    # stop() is shadowed by the module-level function: module attribute lookup
    # takes priority over class methods, so np.stop() actually calls the
    # module-level stop() below. The same-named method is declared here for
    # documentation purposes (never used).

    def launch(self, **kwargs: Any) -> NorpEngine:
        return launch(**kwargs)

    def nasyncio(self, address: Any = None, **config: Any) -> Any:
        """np.nasyncio(...) documentation declaration.

        The actual call is shadowed by the module-level attribute ``nasyncio``
        (the self-developed core module, callable): module attribute lookup takes
        priority over class methods, so np.nasyncio() goes through the core
        module's __call__ (delegating to the norpagent.loops.nasyncio
        architecture function).
        """
        return nasyncio(address, **config)

    def shutdown(self) -> None:
        shutdown()

    def current(self) -> Optional[NorpEngine]:
        return current()

    def submit(self, text: str, session_id: Optional[str] = None,
               task_params: Optional[Dict[str, Any]] = None,
               slot_overrides: Optional[Dict[str, Any]] = None) -> Any:
        return submit(
            text, session_id=session_id,
            task_params=task_params, slot_overrides=slot_overrides,
        )

    def remount(self, **slot_values: Any) -> NorpEngine:
        """Runtime hot mount: replace any slot implementation of the current engine.

        Usage::

            np.remount(model="openai_compat")      # swap the model (takes effect on the next run)
            np.remount(tools=["echo"])             # swap the tool set
            np.remount(security="high")            # swap the security level
            np.remount(frontend="...:ConsoleFrontend")  # swap the frontend
            np.remount(model="myapp.model:create") # replace the module file at runtime
            np.remount(flow_html="/path/flow.html") # swap the flow page at runtime (HTTP not restarted)
            np.remount(html="/path/front.html")     # swap the main page at runtime

        See the slot-group semantics and page hot-replace keys in norpagent.runtime.remount.
        """
        return remount(**slot_values)

    @property
    def version(self) -> str:
        return __version__


sys.modules[__name__].__class__ = _NorpAgentModule

__all__ = [
    "__version__",
    # 品牌（v2.0.0 宣传名：远星 / FarStars）
    "__brand_cn__",
    "__brand_en__",
    "__display_name__",
    # kernel
    "Registry",
    "EventBus",
    "EventType",
    "AgentEvent",
    "Preset",
    "load_preset_file",
    "RunContext",
    "AgentRuntime",
    "RunResult",
    "ComponentError",
    "install_defaults",
    "install_core",
    "register_all_presets",
    "build_embedded_preset",
    "safe",
    "SafetyKit",
    "SecurityContext",
    "hooks",
    # architecture layer
    "ArchLayer",
    "SlotSpec",
    "SlotError",
    "SLOT_SPECS",
    "register_slot",
    "unregister_slot",
    "is_builtin_slot",
    "snapshot_slots",
    "nasyncio",
    "LoopRuntime",
    "NasyncioLoopRuntime",
    "StdLoopRuntime",
    "Frontend",
    "ConsoleFrontend",
    "HeadlessFrontend",
    "WebFrontend",
    # Central Nervous Bus (v1.0.7 内核集成)
    "cnb",
    # runtime (np() entry)
    "launch",
    "current",
    "stop",
    "submit",
    "remount",
    "shutdown",
    "is_running",
    "NorpEngine",
    "EngineState",
    "EngineError",
    # work rollback (v0.9)
    "recovery",
    "RecoveryError",
    "snapshot_system",
    "undo",
    "redo",
    "rollback",
    "list_snapshots",
    "mark_good_snapshot",
    "last_good_snapshot",
    "register_snapshot_provider",
    "set_snapshot_dir",
]
