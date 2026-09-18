# Copyright (c) 2026 xingluosama121, MIT Licensed
"""norpagent.evolution.points — 可进化点注册表 + 逐项勾选审批制。

架构书 §7.5（2026-09-09 裁决）：
- 设置面板对**每一个可能存在自进化的项目**提供手动勾选：
  勾了 = 该项目人工批准（提案先出待批卡片，人确认后才执行）；
  不勾 = 自动批准（快照 → 应用 → 验证 → 失败自动回滚）；
- 默认档位：重大类默认勾选（人工），普通类默认不勾选（自动）；
- 分类口径（重大/普通）本身是设置项，用户可逐项改；
- 勾选态变更入审计（设置事实源天然审计）。

本模块定义可进化点清单（按远星内核动点盘点）与审批策略读写；
设置键 ``evolution.approval.<point_id>``（bool，True=人工）与
``evolution.category.<point_id>``（"major"/"normal"）由用户掌控，
进化器不可写（schema 标记非可进化，内核拒绝 + 审计）。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from .store import SettingsStore, get_store

# 分类口径
CATEGORY_MAJOR = "major"
CATEGORY_NORMAL = "normal"
VALID_CATEGORIES = (CATEGORY_MAJOR, CATEGORY_NORMAL)

# 可进化点英文标题（面板 en 语言环境的展示用；键 = point id）
TITLES_EN = {
    "kernel.loops": "Kernel loops & scheduling",
    "kernel.agent": "Agent runtime",
    "kernel.context": "Context & memory",
    "kernel.tools": "Toolset",
    "kernel.models": "Model adapters",
    "kernel.hooks": "Hook surface",
    "kernel.cnb": "Neural bus (CNB)",
    "kernel.recovery": "Snapshots & rollback",
    "kernel.security": "Security suite",
    "kernel.plugins": "Plugin pipeline",
    "builtin.ui": "Built-in frontend & settings panel",
    "frontends": "Frontend family",
    "modes": "Preset modes",
    "evolution.self": "Evolvers themselves",
}


class EvolutionPoint:
    """一个可进化点（id 稳定；title/target 供面板与提案展示）。"""

    def __init__(self, point_id: str, title: str, category: str,
                 target: str, description: str = "",
                 default_manual: Optional[bool] = None,
                 locked: bool = False) -> None:
        self.id = str(point_id)
        self.title = str(title)
        self.category = category if category in VALID_CATEGORIES else CATEGORY_NORMAL
        self.target = str(target)
        self.description = str(description)
        # 默认档位：重大人工、普通自动（可被 default_manual 显式覆盖）
        self.default_manual = (self.category == CATEGORY_MAJOR
                               if default_manual is None else bool(default_manual))
        self.locked = bool(locked)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "title_en": TITLES_EN.get(self.id, self.title),
            "category": self.category,
            "target": self.target,
            "description": self.description,
            "default_manual": self.default_manual,
            "locked": self.locked,
        }


# ── 可进化点清单（内核动点盘点，初版 14 项） ─────────────

EVOLUTION_POINTS: List[EvolutionPoint] = [
    EvolutionPoint(
        "kernel.loops", "Kernel loop & scheduling", CATEGORY_MAJOR,
        "norpagent.loops / norpagent.nasyncio",
        "Event loop, cancellation propagation, task scheduling core"),
    EvolutionPoint(
        "kernel.agent", "Agent runtime", CATEGORY_MAJOR,
        "norpagent.kernel.agent",
        "Step loop, tool-call orchestration, run context"),
    EvolutionPoint(
        "kernel.context", "Context & memory", CATEGORY_NORMAL,
        "norpagent.kernel.context / builtin.context",
        "Context management, FTS5 memory organization and consolidation (2A memory-evolution domain)"),
    EvolutionPoint(
        "kernel.tools", "Toolset", CATEGORY_NORMAL,
        "norpagent.builtin.tools",
        "Built-in tools and tool registry (2B skill-evolution domain)"),
    EvolutionPoint(
        "kernel.models", "Model adapter layer", CATEGORY_NORMAL,
        "norpagent.builtin.models / protocols.model",
        "Model protocol and adapters (multimodal direct pass / external service routing)"),
    EvolutionPoint(
        "kernel.hooks", "Hook surface", CATEGORY_MAJOR,
        "norpagent.hooks",
        "Subscribe/rewrite/veto surface of 9 layers and 29 hooks"),
    EvolutionPoint(
        "kernel.cnb", "Neural bus (CNB)", CATEGORY_MAJOR,
        "norpagent.cnb",
        "Neural tree, generic slot surface, kernel action surface"),
    EvolutionPoint(
        "kernel.recovery", "Snapshots & rollback", CATEGORY_MAJOR,
        "norpagent.recovery",
        "Snapshot timeline, undo/redo/rollback, crash rescue"),
    EvolutionPoint(
        "kernel.security", "Security", CATEGORY_MAJOR,
        "norpagent.security / norpagent.safe",
        "Approval, audit, guardrails, network policy, signatures",
        default_manual=True),
    EvolutionPoint(
        "kernel.plugins", "Plugin pipeline", CATEGORY_MAJOR,
        "norpagent.plugins",
        "Secure pipeline: signature -> audit -> import restrictions -> registration"),
    EvolutionPoint(
        "builtin.ui", "Built-in frontend & settings panel", CATEGORY_NORMAL,
        "norpagent.builtin.ui",
        "Warm-sun frontend, settings panel, console page"),
    EvolutionPoint(
        "frontends", "Frontend family", CATEGORY_NORMAL,
        "norpagent.frontends",
        "Console/headless/web frontend adapters"),
    EvolutionPoint(
        "modes", "Preset modes", CATEGORY_NORMAL,
        "norpagent.modes",
        "Six presets and product profile assembly (2C personality/config evolution)"),
    EvolutionPoint(
        "evolution.self", "The evolver itself", CATEGORY_MAJOR,
        "norpagent.evolution",
        "Evolution loop, hot reload, evolution packages, rhythm policy",
        default_manual=True, locked=True),
]

_POINTS_BY_ID = {p.id: p for p in EVOLUTION_POINTS}


def get_point(point_id: str) -> Optional[EvolutionPoint]:
    return _POINTS_BY_ID.get(str(point_id))


def list_point_dicts() -> List[Dict[str, Any]]:
    return [p.to_dict() for p in EVOLUTION_POINTS]


# ── 审批策略（勾选制） ───────────────────────────────────

def _approval_key(point_id: str) -> str:
    return f"evolution.approval.{point_id}"


def _category_key(point_id: str) -> str:
    return f"evolution.category.{point_id}"


class ApprovalPolicy:
    """逐项勾选审批制：勾了 = 人工批准；不勾 = 自动批准。"""

    def __init__(self, store: Optional[SettingsStore] = None) -> None:
        self.store = store or get_store()

    # 分类口径（重大/普通本身可设）
    def category(self, point_id: str) -> str:
        point = get_point(point_id)
        override = self.store.get_raw(_category_key(point_id), None)
        if override in VALID_CATEGORIES:
            return override
        return point.category if point else CATEGORY_NORMAL

    def set_category(self, point_id: str, category: str,
                     actor: str = "user") -> str:
        if get_point(point_id) is None:
            raise KeyError(f"unknown evolution point: {point_id}")
        if category not in VALID_CATEGORIES:
            raise ValueError(f"category must be one of {VALID_CATEGORIES}")
        self.store.set(_category_key(point_id), category, actor=actor,
                       reason="evolution category override")
        return category

    # 勾选态（True = 人工批准；False = 自动批准）
    def is_manual(self, point_id: str) -> bool:
        point = get_point(point_id)
        default = point.default_manual if point else False
        # 显式勾选覆盖（kv 原始值；不被 schema 默认混淆）
        override = self.store.get_raw(_approval_key(point_id), None)
        if isinstance(override, bool):
            return override
        # 分类被显式改过时：默认档位随新分类（重大人工 / 普通自动）
        if get_point(point_id) is not None and \
                self.store.get_raw(_category_key(point_id), None) in VALID_CATEGORIES:
            return self.category(point_id) == CATEGORY_MAJOR
        return bool(default)

    def set_manual(self, point_id: str, manual: bool,
                   actor: str = "user") -> bool:
        if get_point(point_id) is None:
            raise KeyError(f"unknown evolution point: {point_id}")
        self.store.set(_approval_key(point_id), bool(manual), actor=actor,
                       reason="evolution approval checkbox")
        return bool(manual)

    def clear_manual(self, point_id: str, actor: str = "user") -> bool:
        """恢复默认档位（删除显式勾选覆盖；此后随分类口径）。"""
        if get_point(point_id) is None:
            raise KeyError(f"unknown evolution point: {point_id}")
        return self.store.delete(_approval_key(point_id), actor=actor,
                                 reason="evolution approval reset to default")

    # 裁决
    def decide(self, point_id: str) -> Dict[str, Any]:
        """返回该点的裁决口径：mode=manual/auto、category、default 等。"""
        point = get_point(point_id)
        if point is None:
            raise KeyError(f"unknown evolution point: {point_id}")
        manual = self.is_manual(point_id)
        return {
            "point": point_id,
            "title": point.title,
            "title_en": TITLES_EN.get(point_id, point.title),
            "category": self.category(point_id),
            "mode": "manual" if manual else "auto",
            "requires_human": manual,
            "default_manual": point.default_manual,
            "locked": point.locked,
            "target": point.target,
        }

    def decisions(self) -> List[Dict[str, Any]]:
        """全部可进化点的当前裁决视图（设置面板数据源）。"""
        return [self.decide(p.id) for p in EVOLUTION_POINTS]

    def can_evolve(self, point_id: str) -> Dict[str, Any]:
        """evolution.enabled 总开关 + 单点裁决的合并执行口径。"""
        enabled = bool(self.store.get("evolution.enabled", True))
        d = self.decide(point_id)
        d["enabled"] = enabled
        d["executable"] = enabled
        return d


# ── schema 注册 ──────────────────────────────────────────

def register_evolution_schema(store: Optional[SettingsStore] = None) -> int:
    """注册进化域 schema（含每点勾选/分类键；进化器不可写）。"""
    s = store or get_store()
    specs: List[Dict[str, Any]] = [
        {
            "key": "evolution.enabled", "title": "Self-evolution master switch",
            "category": "evolution", "evolvable": False, "default": True,
            "description": ": master switch; when off, all evolvers stop",
        },
        {
            "key": "evolution.idle_policy", "title": "Idle-time evolution policy",
            "category": "evolution", "evolvable": False, "default": "reduced",
            "description": "reduced = reduce or skip on idle; off = no evolution; auto = keep",
        },
        {
            "key": "evolution.idle_min_seconds", "title": "Idle threshold (seconds)",
            "category": "evolution", "evolvable": False, "default": 600,
            "description": "no demand for this duration counts as idle",
        },
        {
            "key": "evolution.candidate_threshold", "title": "Evolution candidate trigger count",
            "category": "evolution", "evolvable": False, "default": 3,
            "description": "frequently used features (>=3 times) become evolution candidates",
        },
    ]
    for point in EVOLUTION_POINTS:
        specs.append({
            "key": _approval_key(point.id),
            "title": f"{point.title}·manual approval",
            "category": "evolution.approval",
            "evolvable": False,
            "default": point.default_manual,
            "description": "checked = manual approval; unchecked = auto approval ",
        })
        specs.append({
            "key": _category_key(point.id),
            "title": f"{point.title}·category policy",
            "category": "evolution.approval",
            "evolvable": False,
            "default": point.category,
            "description": "The major/normal classification policy is itself configurable ",
        })
    return s.register_schema(specs)


__all__ = [
    "CATEGORY_MAJOR",
    "CATEGORY_NORMAL",
    "VALID_CATEGORIES",
    "EvolutionPoint",
    "EVOLUTION_POINTS",
    "get_point",
    "list_point_dicts",
    "ApprovalPolicy",
    "register_evolution_schema",
]
