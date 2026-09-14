# Copyright (c) 2026 xingluosama121, MIT Licensed
"""norpagent.evolution.engines — 四类进化的执行器（2A 记忆 / 2B 技能 / 2C 配置 / 2D 代码）。

架构书 §7.2 ~ §7.5 的工程落地。四个执行器都满足：

- 无槽位外特权、无设置源外写入权（写设置库走同一守卫链）；
- 动作先留回退方案、后应用；失败自动回滚（由 ProposalBoard 统一编排）；
- 全部动作可审计、可日志、可取证。

    MemoryEvolver   2A：长期记忆的固化 / 去重 / 遗忘（软删 + 可恢复 + 审计）
    SkillEvolver    2B：重复手工模式 → 技能提案 → 登记装载（技能登记表 + .fspack 存档）
    ConfigEvolver   2C：可进化设置项的小步调参（只允许 schema 标记 evolvable 的项）
    CodeEvolver     2D：代码进化提案包装（产出/激活/回退由 hotswap 管线承担）
"""

from __future__ import annotations

import json
import os
import time
from typing import Any, Dict, List, Optional

from .store import SettingsStore, append_log, get_store

_MISS = object()

# 2A：被遗忘条目的副本前缀（软删 = 从长期记忆移出、副本留在设置库可恢复）
_FORGOTTEN_PREFIX = "memory.forgotten."


# ══════════════════════════════════════════════════════════
# 2A 记忆进化
# ══════════════════════════════════════════════════════════

class MemoryEvolver:
    """长期记忆（FTS5 上下文库）的固化 / 去重 / 遗忘执行器。

    - 扫描：读取上下文库条目，识别完全重复（规范化后相同）的分组；
    - 遗忘：从长期记忆删除前先把原文副本存入设置库（``memory.forgotten.<id>``）
      —— 软删 + 审计，「被遗忘项可查、可恢复」；
    - 恢复：``restore(origin_id)`` 把副本重新写入长期记忆。
    """

    def __init__(self, store: Optional[SettingsStore] = None,
                 context_path: Optional[str] = None) -> None:
        self.store = store or get_store()
        self.context_path = context_path

    # ── 上下文库访问（每次操作短连接；不长期持有句柄） ──

    def _open(self):
        from norpagent.builtin.context.fts5 import FTS5ContextStore

        return FTS5ContextStore(self.context_path)

    def _list_all(self, limit: int = 500) -> List[Dict[str, Any]]:
        api = self._open()
        try:
            out: List[Dict[str, Any]] = []
            offset = 0
            while len(out) < limit:
                batch = api.list(limit=200, offset=offset)
                out.extend(batch)
                if len(batch) < 200:
                    break
                offset += 200
            return out[:limit]
        finally:
            try:
                api.close()
            except Exception:  # noqa: BLE001
                pass

    # ── 扫描 / 计划 ──────────────────────────────────────

    @staticmethod
    def _norm(text: str) -> str:
        return " ".join(str(text or "").split()).lower()

    def scan(self, limit: int = 500) -> Dict[str, Any]:
        """扫描记忆库：返回重复分组等反思结果（不改动任何数据）。"""
        entries = self._list_all(limit=limit)
        groups: Dict[str, List[Dict[str, Any]]] = {}
        for e in entries:
            key = self._norm(e.get("text"))
            if not key:
                continue
            groups.setdefault(key, []).append(e)
        duplicate_groups = [g for g in groups.values() if len(g) > 1]
        return {
            "ok": True,
            "entries": len(entries),
            "duplicate_groups": len(duplicate_groups),
            "duplicates": [
                {
                    "keep": max(g, key=lambda x: x.get("id") or 0)["id"],
                    "forget": [x["id"] for x in g
                               if x["id"] != max(g, key=lambda y: y.get("id") or 0)["id"]],
                }
                for g in duplicate_groups
            ],
        }

    def plan(self, limit: int = 500) -> Dict[str, Any]:
        """产出记忆进化动作计划（去重遗忘；不含删除动作的执行）。"""
        scan = self.scan(limit=limit)
        actions: List[Dict[str, Any]] = []
        for dup in scan.get("duplicates") or []:
            if dup.get("forget"):
                actions.append({
                    "action": "forget",
                    "ids": list(dup["forget"]),
                    "reason": f"duplicate of #{dup['keep']}",
                })
        return {"ok": True, "entries": scan.get("entries"), "actions": actions,
                "count": len(actions)}

    # ── 执行 / 恢复 ──────────────────────────────────────

    def apply_payload(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """执行一个记忆进化动作载荷（由提案板调用）。

        支持：``{"action": "forget", "ids": [...]}``（软删：副本入设置库）。
        """
        payload = dict(payload or {})
        action = str(payload.get("action") or "forget")
        ids = [int(i) for i in (payload.get("ids") or [])]
        if action == "forget":
            if not ids:
                return {"ok": False, "error": "forget needs non-empty ids"}
            api = self._open()
            forgotten: List[Dict[str, Any]] = []
            try:
                for doc_id in ids:
                    entry = api.get(doc_id)
                    if entry is None:
                        continue
                    copy_key = f"{_FORGOTTEN_PREFIX}{doc_id}"
                    self.store.set(copy_key, {
                        "origin_id": doc_id,
                        "text": entry.get("text") or "",
                        "source": entry.get("source") or "",
                        "title": entry.get("title") or "",
                        "metadata": entry.get("metadata") or {},
                        "forgotten_at": time.time(),
                        "reason": payload.get("reason") or "",
                    }, actor="evolution:memory",
                        reason=f"forget (soft delete) memory #{doc_id}")
                    if api.delete(doc_id):
                        forgotten.append({"origin_id": doc_id, "copy_key": copy_key})
            finally:
                try:
                    api.close()
                except Exception:  # noqa: BLE001
                    pass
            append_log({"event": "evolution.memory.forget", "ids": ids,
                        "forgotten": [f["origin_id"] for f in forgotten]})
            return {"ok": True, "action": "forget", "forgotten": forgotten,
                    "restorable": True}
        if action == "restore":
            restored = [self.restore(int(i)) for i in ids]
            return {"ok": all(r.get("ok") for r in restored) if restored else False,
                    "action": "restore", "restored": restored}
        return {"ok": False, "error": f"unsupported memory action: {action!r}"}

    def forgotten(self) -> List[Dict[str, Any]]:
        """已遗忘（软删）条目清单（可查：白盒 + 可恢复）。"""
        out: List[Dict[str, Any]] = []
        for key, value in (self.store.all() or {}).items():
            if key.startswith(_FORGOTTEN_PREFIX) and isinstance(value, dict):
                out.append({"copy_key": key, **value})
        return sorted(out, key=lambda x: x.get("forgotten_at") or 0, reverse=True)

    def restore(self, origin_id: int) -> Dict[str, Any]:
        """恢复一条被遗忘的记忆（副本重新写回长期记忆，副本键清除）。"""
        copy_key = f"{_FORGOTTEN_PREFIX}{int(origin_id)}"
        copy = self.store.get_raw(copy_key, None)
        if not isinstance(copy, dict):
            return {"ok": False, "error": f"no forgotten copy for #{origin_id}"}
        api = self._open()
        try:
            new_id = api.add(
                copy.get("text") or "",
                source=str(copy.get("source") or "restored"),
                title=str(copy.get("title") or ""),
                metadata=dict(copy.get("metadata") or {}),
            )
        finally:
            try:
                api.close()
            except Exception:  # noqa: BLE001
                pass
        self.store.delete(copy_key, actor="user",
                          reason=f"restore memory #{origin_id} as #{new_id}")
        append_log({"event": "evolution.memory.restore",
                    "origin_id": int(origin_id), "new_id": new_id})
        return {"ok": True, "origin_id": int(origin_id), "new_id": new_id}


# ══════════════════════════════════════════════════════════
# 2B 技能进化
# ══════════════════════════════════════════════════════════

class SkillEvolver:
    """技能进化执行器：技能登记表（设置库）+ .fspack 存档（可分享/署名）。

    执行载荷：``{"name": ..., "artifact": {"kind": ..., "feature": ..., ...}}``
    —— 登记装载（同名替换）并落一份 .fspack 存档；``remove(name)`` 回退。
    """

    REGISTRY_KEY = "skills.registry"

    def __init__(self, store: Optional[SettingsStore] = None,
                 skills_dir: Optional[str] = None) -> None:
        self.store = store or get_store()
        self.skills_dir = skills_dir

    def _dir(self) -> str:
        base = (os.environ.get("NORPAGENT_SKILLS_DIR") or "").strip()
        if base:
            return base
        home = (os.environ.get("NORPAGENT_UNBOX_HOME") or "").strip() or \
            os.path.join(os.path.expanduser("~"), ".norpagent")
        return self.skills_dir or os.path.join(home, "skills")

    def registry(self) -> List[Dict[str, Any]]:
        raw = self.store.get_raw(self.REGISTRY_KEY, None)
        return list(raw) if isinstance(raw, list) else []

    def apply_payload(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        name = str((payload or {}).get("name") or "").strip()
        if not name:
            return {"ok": False, "error": "skill needs a name"}
        artifact = dict((payload or {}).get("artifact") or {})
        entry = {
            "name": name,
            "artifact": artifact,
            "feature": artifact.get("feature") or "",
            "created_at": time.time(),
            "source": "evolution",
        }
        reg = [e for e in self.registry() if e.get("name") != name]
        reg.append(entry)
        self.store.set(self.REGISTRY_KEY, reg, actor="evolution:skill",
                       reason=f"register skill {name}")
        archive = None
        try:
            from .packages import export_fspack

            os.makedirs(self._dir(), exist_ok=True)
            archive = os.path.join(self._dir(), f"skill-{name}.fspack")
            export_fspack({"kind": "skill", "name": name, "artifact": artifact},
                          archive, author=str(payload.get("author") or "evolution"))
        except Exception as exc:  # noqa: BLE001 — 存档失败不否决登记（如实记录）
            append_log({"event": "skill.archive.failed", "name": name,
                        "error": f"{type(exc).__name__}: {exc}"})
        append_log({"event": "evolution.skill.registered", "name": name,
                    "archive": archive})
        return {"ok": True, "name": name, "archive": archive,
                "registry_size": len(reg)}

    def remove(self, name: str) -> Dict[str, Any]:
        name = str(name or "").strip()
        reg = [e for e in self.registry() if e.get("name") != name]
        self.store.set(self.REGISTRY_KEY, reg, actor="evolution:skill",
                       reason=f"remove skill {name}")
        return {"ok": True, "removed": name, "registry_size": len(reg)}

    # 反思辅助：常用（≥3 次）功能 → 技能提案载荷
    def candidate_payloads(self, tracker: Any) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        try:
            candidates = tracker.candidates()
        except Exception:  # noqa: BLE001
            return out
        for c in candidates or []:
            feature = str(c.get("feature") or "")
            if not feature:
                continue
            out.append({
                "name": "skill-" + feature.replace(" ", "-").replace("/", "-"),
                "artifact": {
                    "kind": "prompt-template",
                    "feature": feature,
                    "uses": c.get("count"),
                    "note": "generated from repeated usage (>= threshold)",
                },
            })
        return out


# ══════════════════════════════════════════════════════════
# 2C 配置进化
# ══════════════════════════════════════════════════════════

class ConfigEvolver:
    """配置 / 人格进化执行器：只允许触碰 schema 标记 ``evolvable`` 的设置项。

    标为 ``locked`` 的项任何进化器不可写（内核拒绝 + 审计告警，§7.6）。
    """

    def __init__(self, store: Optional[SettingsStore] = None,
                 board: Any = None) -> None:
        self.store = store or get_store()
        self._board = board

    def _board_or_default(self):
        if self._board is not None:
            return self._board
        from .proposals import ProposalBoard

        return ProposalBoard(self.store)

    def check_target(self, key: str) -> Dict[str, Any]:
        """校验目标键是否可被配置进化触碰（evolvable / locked）。"""
        from norpagent.settings import schema_item

        item = schema_item(key)
        if item is None:
            return {"ok": False, "error": f"unknown setting key: {key}"}
        if item.get("locked"):
            return {"ok": False,
                    "error": f"{key} is LOCKED: evolution writers are refused"}
        if not item.get("evolvable"):
            return {"ok": False,
                    "error": f"{key} is not marked evolvable"}
        return {"ok": True, "item": item}

    def propose(self, key: str, value: Any, *, reason: str = "",
                point: str = "kernel.models", **kw: Any) -> Dict[str, Any]:
        """创建配置进化提案（裁决 / 执行 / 回滚由提案板统一编排）。"""
        check = self.check_target(key)
        if not check.get("ok"):
            raise ValueError(check.get("error"))
        board = self._board_or_default()
        return board.propose_config(key, value, point=point, reason=reason, **kw)


# ══════════════════════════════════════════════════════════
# 2D 代码进化（提案包装；产出/激活/回退由 hotswap 管线承担）
# ══════════════════════════════════════════════════════════

class CodeEvolver:
    """代码进化执行器包装：产出新文件 → 验证 → 激活；原文件字节不动、可一键回退。"""

    def __init__(self, store: Optional[SettingsStore] = None,
                 board: Any = None) -> None:
        self.store = store or get_store()
        self._board = board

    def _board_or_default(self):
        if self._board is not None:
            return self._board
        from .proposals import ProposalBoard

        return ProposalBoard(self.store)

    def propose(self, target_path: str, new_code: str, *, reason: str = "",
                point: str = "kernel.agent", tag: str = "",
                **kw: Any) -> Dict[str, Any]:
        """创建代码进化提案（应用前先产出新版本文件；原文件只读不动）。"""
        board = self._board_or_default()
        try:
            old_lines = len(open(target_path, encoding="utf-8",
                                 errors="replace").read().splitlines())
        except Exception:  # noqa: BLE001
            old_lines = 0
        new_lines = len(str(new_code).splitlines())
        diff = f"-{old_lines} lines / +{new_lines} lines (new file; original untouched)"
        return board.propose_code(target_path, new_code, point=point,
                                  reason=reason, tag=tag, diff=diff, **kw)


__all__ = [
    "MemoryEvolver",
    "SkillEvolver",
    "ConfigEvolver",
    "CodeEvolver",
]
