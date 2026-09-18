# Copyright (c) 2026 xingluosama121, MIT Licensed
"""norpagent.evolution — 自进化子系统。

的工程落地，四类进化（2A 记忆 / 2B 技能 / 2C 配置 /
2D 代码）共享的底座：

    store.py     设置事实源（SQLite + JSON 导入导出；可进化/锁定一等字段）；
    points.py    可进化点注册表 + 逐项勾选审批制（勾 = 人工、不勾 = 自动，
                 默认重大人工、普通自动；分类口径本身可设）；
    hotswap.py   代码进化热重载（新文件新逻辑；原文件字节不动、可一键回退）；
    packages.py  进化包 .fspack（兼容 json / py）+ 整合包 .zip（≤1024，
                 失败不阻塞、失败项完全不使用、如实入日志）；
    rhythm.py    节奏与方向（闲时减少/不进化；≥3 次常用功能候选；命令式进化）。

``bootstrap(profile)`` 由 ``norpagent unbox`` 调用：建库 + 注册 schema +
把成品档案里的进化开关/审批口径写进设置事实源。
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from .store import (
    SettingsError,
    SettingsLockedError,
    SettingsStore,
    append_log,
    default_db_path,
    evolution_log_path,
    get_store,
    read_log,
    set_store_path,
)
from .points import (
    CATEGORY_MAJOR,
    CATEGORY_NORMAL,
    EVOLUTION_POINTS,
    VALID_CATEGORIES,
    ApprovalPolicy,
    EvolutionPoint,
    get_point,
    list_point_dicts,
    register_evolution_schema,
)
from .hotswap import (
    HotswapError,
    activate,
    list_versions,
    load_module_from_file,
    original_intact,
    rollback,
    stage_new_version,
    verify_active,
)
from .packages import (
    BUNDLE_SUFFIX,
    FSPACK_FORMAT,
    FSPACK_SUFFIXES,
    MAX_BUNDLE_ENTRIES,
    PackageError,
    build_fspack,
    export_bundle,
    export_fspack,
    import_bundle,
    import_fspack,
    read_fspack,
    verify_fspack,
    write_fspack,
)
from .rhythm import (
    DEFAULT_CANDIDATE_THRESHOLD,
    IdlePlanner,
    UsageTracker,
    command_evolution,
)
from .proposals import (
    STATUS_APPLIED,
    STATUS_APPROVED,
    STATUS_AWAITING,
    STATUS_DISABLED,
    STATUS_FAILED,
    STATUS_PAUSED,
    STATUS_PROPOSED,
    STATUS_REJECTED,
    STATUS_ROLLED_BACK,
    STATUS_ROLLBACK_FAILED,
    CircuitBreaker,
    ProposalBoard,
    ProposalError,
)
from .engines import (
    CodeEvolver,
    ConfigEvolver,
    MemoryEvolver,
    SkillEvolver,
)

__version__ = "0.1.0"


def bootstrap(profile: Optional[Dict[str, Any]] = None,
              store: Optional[SettingsStore] = None) -> SettingsStore:
    """初始化进化底座（幂等）：设置库 + schema + 成品档案口径。

    由 ``norpagent unbox`` 启动时调用；失败可重试，不影响内核加载。
    ``profile``（成品档案 evolution 节）支持的键：
        enabled (bool)       总开关；
        approval (str)       "major-manual"（默认）/ "all-manual" / "all-auto"；
        idle_policy (str)    "reduced" / "off" / "auto"。
    """
    s = store or get_store()
    register_evolution_schema(s)
    # 内核动点全量清单一并入册（§5；失败不阻塞进化底座）
    try:
        from norpagent.settings import register_kernel_schema

        register_kernel_schema(s)
    except Exception:  # noqa: BLE001
        pass
    profile = dict(profile or {})
    if "enabled" in profile:
        s.set("evolution.enabled", bool(profile.get("enabled")), actor="user",
              reason="unbox profile: evolution.enabled")
    if profile.get("idle_policy"):
        s.set("evolution.idle_policy", str(profile["idle_policy"]),
              actor="user", reason="unbox profile: idle policy")
    approval = str(profile.get("approval") or "major-manual").strip().lower()
    policy = ApprovalPolicy(s)
    if approval == "all-manual":
        for point in EVOLUTION_POINTS:
            policy.set_manual(point.id, True, actor="user")
    elif approval == "all-auto":
        for point in EVOLUTION_POINTS:
            policy.set_manual(point.id, False, actor="user")
    # "major-manual"（默认档）：schema 默认值即为「重大人工、普通自动」，无需写入
    s.set("evolution.bootstrap.last_at",
          __import__("time").time(), actor="user",
          reason="evolution bootstrap marker")
    # 运行期加固（2026-09-12）：启动巡检已应用代码提案的活跃版本——
    # 发现损坏（新文件丢失/不可加载、原文件被改动）自动回退标记 + 熔断。
    # 巡检失败不阻塞底座初始化。
    try:
        ProposalBoard(s).health_sweep()
    except Exception:  # noqa: BLE001 — 巡检尽力而为
        pass
    return s


__all__ = [
    "__version__",
    "bootstrap",
    # store
    "SettingsStore",
    "SettingsError",
    "SettingsLockedError",
    "get_store",
    "set_store_path",
    "default_db_path",
    "evolution_log_path",
    "append_log",
    "read_log",
    # points / approval
    "CATEGORY_MAJOR",
    "CATEGORY_NORMAL",
    "VALID_CATEGORIES",
    "EvolutionPoint",
    "EVOLUTION_POINTS",
    "get_point",
    "list_point_dicts",
    "ApprovalPolicy",
    "register_evolution_schema",
    # hotswap
    "HotswapError",
    "stage_new_version",
    "load_module_from_file",
    "activate",
    "rollback",
    "original_intact",
    "verify_active",
    "list_versions",
    # packages
    "FSPACK_FORMAT",
    "FSPACK_SUFFIXES",
    "BUNDLE_SUFFIX",
    "MAX_BUNDLE_ENTRIES",
    "PackageError",
    "build_fspack",
    "write_fspack",
    "export_fspack",
    "read_fspack",
    "verify_fspack",
    "import_fspack",
    "export_bundle",
    "import_bundle",
    # rhythm
    "DEFAULT_CANDIDATE_THRESHOLD",
    "UsageTracker",
    "IdlePlanner",
    "command_evolution",
    # proposals（提案引擎 + 熔断）
    "ProposalBoard",
    "CircuitBreaker",
    "ProposalError",
    "STATUS_PROPOSED",
    "STATUS_AWAITING",
    "STATUS_APPROVED",
    "STATUS_REJECTED",
    "STATUS_APPLIED",
    "STATUS_FAILED",
    "STATUS_ROLLED_BACK",
    "STATUS_PAUSED",
    "STATUS_DISABLED",
    # engines（2A/2B/2C/2D 执行器）
    "MemoryEvolver",
    "SkillEvolver",
    "ConfigEvolver",
    "CodeEvolver",
]
