# Copyright (c) 2026 xingluosama121, MIT Licensed
"""norpagent.whitebox — 白盒统一遍历（架构书 §4「每一环节可看、可测、可改、可设」）。

四维契约（对每一执行环节成立）：

    可看   环节当前状态 / 装配值 / 运行指标
    可测   离线 / 在线验证（快照回放、dry-run、回归套件）
    可改   运行中替换或干预（槽位热挂载、钩子订阅、插件管线、救援接管）
    可设   每个动点收敛为设置项（§5：norpagent.settings 全量清单）

三件套（``describe()`` 可看 / ``audit_trail()`` 可溯 / ``settings()`` 可设）由本层
**内核统一遍历**为每一环节生成（槽位 / 钩子 / 原子 / 进化器 / 前端 / 恢复），
无需为每个对象类重复植入同样的样板；对象自身既有的 describe 等入口保持原样。

用法::

    from norpagent.whitebox import overview

    tree = overview(engine)          # 环节树：各节 envs + settings 键 + audit 线索
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

# 槽位 → 设置类别（§5 全量清单的过滤辅助；决定「可设」列呈现哪些键）
SLOT_SETTING_CATEGORY = {
    "model": ("model",),
    "tools": ("tools",),
    "session": ("memory", "runtime"),
    "sandbox": ("tools", "runtime"),
    "scheduler": ("runtime",),
    "context_store": ("memory",),
    "project_manager": ("runtime",),
    "hooks": ("kernel",),
    "security": ("security",),
    "plugins": ("plugins",),
    "frontend": ("frontend", "runtime"),
    "ui": ("frontend",),
    "preset": ("runtime",),
    "async_loop": ("runtime",),
    "logger": ("runtime",),
    "storage": ("runtime",),
    "error_handler": ("runtime",),
    "agent_runtime": ("runtime",),
}


def _settings_keys_for_categories(categories: Any) -> List[str]:
    """按类别从内核全量清单取设置键（懒加载，失败返回空）。"""
    try:
        from norpagent.settings import KERNEL_SCHEMA

        cats = set(categories or ())
        return [s["key"] for s in KERNEL_SCHEMA if s.get("category") in cats]
    except Exception:  # noqa: BLE001
        return []


def env_describe(report: Dict[str, Any]) -> Dict[str, Any]:
    """环境对象三件套的规整视图（describe / audit_trail / settings 键）。"""
    return {
        "describe": report.get("describe"),
        "audit_trail": report.get("audit") or [],
        "settings": report.get("settings") or [],
    }


# ── 各环节遍历 ───────────────────────────────────────────

def slots_section(engine: Any) -> Dict[str, Any]:
    """槽位环节：装配了什么（可看）、怎么换（可改）、有哪些设置项（可设）。"""
    envs: List[Dict[str, Any]] = []
    try:
        from norpagent.arch import is_builtin_slot, snapshot_slots

        layer = engine.layer
        for name in sorted(snapshot_slots().keys()):
            value = layer.get(name)
            impl = value if not isinstance(value, str) else value
            builtin = False
            try:
                builtin = bool(is_builtin_slot(name))
            except Exception:  # noqa: BLE001
                pass
            envs.append({
                "name": name,
                "kind": "slot",
                "describe": {
                    "impl": type(impl).__name__ if not isinstance(value, str) else value,
                    "configured": not isinstance(value, str) or bool(value),
                    "builtin": builtin,
                },
                "change": f"np.remount({name}=...) / register_slot()",
                "settings": _settings_keys_for_categories(
                    SLOT_SETTING_CATEGORY.get(name, ("runtime",))),
                "audit": [],
            })
    except Exception as exc:  # noqa: BLE001
        return {"section": "slots", "title": "Slots", "error": str(exc), "envs": []}
    return {"section": "slots", "title": "Slots", "envs": envs}


def hooks_section(engine: Any) -> Dict[str, Any]:
    """钩子环节：9 层 29 钩子（含自定义层）的订阅面。"""
    envs: List[Dict[str, Any]] = []
    try:
        hooks = None
        try:
            hooks = engine.registry.hooks
        except Exception:  # noqa: BLE001
            hooks = getattr(getattr(engine, "agent", None), "hooks", None)
        if hooks is not None:
            for layer in hooks.layers():
                envs.append({
                    "name": layer.name,
                    "kind": "hook_layer",
                    "describe": {"hooks": list(layer.hooks), "order": layer.order,
                                 "description": layer.description},
                    "change": "register_layer() / register_hook() / hook.subscribe()",
                    "settings": [],
                    "audit": [],
                })
            envs.append({
                "name": "(hook counts)",
                "kind": "summary",
                "describe": {"total": len(hooks.list_hook_names()),
                             "layers": len(hooks.layers())},
                "change": "",
                "settings": [],
                "audit": [],
            })
    except Exception as exc:  # noqa: BLE001
        return {"section": "hooks", "title": "Hooks", "error": str(exc), "envs": []}
    return {"section": "hooks", "title": "Hooks", "envs": envs}


def cnb_section(engine: Any) -> Dict[str, Any]:
    """神经环节（原子）：状态、槽位用量、动作面、本地审计尾部。"""
    envs: List[Dict[str, Any]] = []
    adapter = None
    try:
        adapter = getattr(engine, "cnb", None)
    except Exception:  # noqa: BLE001
        adapter = None
    if adapter is not None:
        node = getattr(adapter, "node", None)
        slots_info = {}
        audit: List[Dict[str, Any]] = []
        actions: List[str] = []
        if node is not None:
            try:
                slots_info = {"count": node.slots.count(), "free": node.slots.free()}
            except Exception:  # noqa: BLE001
                pass
            try:
                audit = node.get_audit()[-50:]
            except Exception:  # noqa: BLE001
                pass
            try:
                actions = sorted(node.list_actions())
            except Exception:  # noqa: BLE001
                pass
        envs.append({
            "name": getattr(node, "node_id", "node") or "node",
            "kind": "cnb_atom",
            "describe": {
                "status": getattr(adapter, "status", ""),
                "level": getattr(node, "level", None),
                "kind": getattr(node, "kind", None),
                "parent": getattr(node, "parent_url", None),
                "port": getattr(node, "port", None),
                "slots": slots_info,
                "actions": actions,
            },
            "change": "np.remount(cnb=...) / CNB CLI exec / perm table",
            "settings": _settings_keys_for_categories(("cnb",)),
            "audit": audit,
        })
    return {"section": "cnb", "title": "Neural (CNB)", "envs": envs}


def evolution_section(engine: Any) -> Dict[str, Any]:
    """进化环节：可进化点勾选态 + 熔断 + 最近提案 + 进化日志尾部。"""
    envs: List[Dict[str, Any]] = []
    audit: List[Dict[str, Any]] = []
    settings = _settings_keys_for_categories(("evolution",))
    try:
        from norpagent.evolution import (
            ApprovalPolicy, CircuitBreaker, ProposalBoard, get_store, read_log,
        )

        store = get_store()
        policy = ApprovalPolicy(store)
        breaker = CircuitBreaker(store)
        board = ProposalBoard(store)
        envs.append({
            "name": "evolution.points",
            "kind": "evolver",
            "describe": {"points": policy.decisions()},
            "change": "checklist approval (checked = manual / unchecked = auto)",
            "settings": settings,
            "audit": [],
        })
        envs.append({
            "name": "evolution.breaker",
            "kind": "evolver",
            "describe": {"states": breaker.all_states()},
            "change": "breaker_resume(point)",
            "settings": [s for s in settings if "breaker" in s],
            "audit": [],
        })
        envs.append({
            "name": "evolution.proposals",
            "kind": "evolver",
            "describe": {"recent": board.list(limit=20)},
            "change": "decide / execute (proposal center)",
            "settings": settings,
            "audit": [],
        })
        audit = read_log(50)
    except Exception as exc:  # noqa: BLE001
        return {"section": "evolution", "title": "Evolver",
                "error": str(exc), "envs": envs, "audit": audit}
    return {"section": "evolution", "title": "Evolver", "envs": envs, "audit": audit}


def frontend_section(engine: Any) -> Dict[str, Any]:
    """前端环节：形态 / 端口 / 挂载页 / 可设项。"""
    envs: List[Dict[str, Any]] = []
    try:
        fe = getattr(engine, "frontend", None)
        if fe is not None:
            pages = {}
            for attr, key in (("_html", "front"), ("_flow_html", "flow"),
                              ("_farstars_html", "farstars")):
                try:
                    pages[key] = bool(getattr(fe, attr, None))
                except Exception:  # noqa: BLE001
                    pass
            envs.append({
                "name": getattr(fe, "frontend_id", type(fe).__name__),
                "kind": "frontend",
                "describe": {
                    "port": getattr(fe, "port", None),
                    "host": getattr(fe, "host", None),
                    "pages": pages,
                },
                "change": "np.remount(frontend=...) / remount(html=...) page hot-swap",
                "settings": _settings_keys_for_categories(("frontend", "runtime")),
                "audit": [],
            })
    except Exception as exc:  # noqa: BLE001
        return {"section": "frontend", "title": "Frontend", "error": str(exc), "envs": []}
    return {"section": "frontend", "title": "Frontend", "envs": envs}


def recovery_section(engine: Any) -> Dict[str, Any]:
    """恢复环节：快照时间线与救援通道（可测 / 可改）。"""
    envs: List[Dict[str, Any]] = []
    try:
        from norpagent.recovery import list_snapshots

        snaps = list_snapshots(limit=10)
        envs.append({
            "name": "recovery.snapshots",
            "kind": "recovery",
            "describe": {"count": len(snaps),
                         "recent": [s.get("id") for s in snaps[:5]]},
            "change": "undo / redo / rollback / norpagent-rescue",
            "settings": _settings_keys_for_categories(("runtime", "security")),
            "audit": [],
        })
    except Exception as exc:  # noqa: BLE001
        return {"section": "recovery", "title": "Recovery & Rescue",
                "error": str(exc), "envs": envs}
    return {"section": "recovery", "title": "Recovery & Rescue", "envs": envs}


# ── 统一遍历入口 ─────────────────────────────────────────

def overview(engine: Any = None) -> Dict[str, Any]:
    """白盒总览：按环节树统一遍历（可看 / 可测 / 可改 / 可设）。

    ``engine`` 为 None 时尝试使用当前引擎（np.current()）；不可用时仍返回
    进化器 / 恢复等进程级环节。
    """
    if engine is None:
        try:
            import norpagent as np

            engine = np.current()
        except Exception:  # noqa: BLE001
            engine = None
    sections: List[Dict[str, Any]] = []
    if engine is not None:
        sections.append(slots_section(engine))
        sections.append(hooks_section(engine))
        sections.append(cnb_section(engine))
    sections.append(evolution_section(engine))
    if engine is not None:
        sections.append(frontend_section(engine))
    sections.append(recovery_section(engine))
    version = "?"
    try:
        import norpagent as np

        version = np.__version__
    except Exception:  # noqa: BLE001
        pass
    return {
        "ok": True,
        "generated_at": time.time(),
        "version": version,
        "engine_running": bool(engine is not None and engine.is_running()),
        "sections": sections,
    }


__all__ = [
    "SLOT_SETTING_CATEGORY",
    "env_describe",
    "slots_section",
    "hooks_section",
    "cnb_section",
    "evolution_section",
    "frontend_section",
    "recovery_section",
    "overview",
]
