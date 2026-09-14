# Copyright (c) 2026 xingluosama121, MIT Licensed
"""norpagent.evolution.proposals — 进化提案引擎 + 熔断（架构书 §7.1 / §7.5 / §7.6）。

进化环（观测 → 反思 → 提案 → 裁决 → 执行 → 验证 → 固化）的中间环节：

    ProposalBoard.create(...)      提案（机器可读 JSON + 人可读摘要）
    ProposalBoard.decide(id)       裁决（勾选制：勾了 = 人工待批；不勾 = 自动放行）
    ProposalBoard.execute(id)      执行（先记录回退方案；失败自动回滚 + 熔断计次）
    ProposalBoard.verify(id)       验证（按 kind 的运行校验；并入 execute 成功路径）
    ProposalBoard.consolidate(id)  固化（标记 applied + 落进化日志与审计）

熔断（CircuitBreaker）：同一可进化点连续失败达到阈值
（``evolution.breaker_threshold``）自动暂停该点进化并通知
（``evolution.breaker_auto_pause`` 开关；阈值 / 开关本身是设置项）。

状态机：``proposed → awaiting（人工待批）/ rejected / approved → applied / failed / paused``。
全部动作写进化日志（JSONL）；失败自动回滚（kind 级回退方案在应用前捕获）。
"""

from __future__ import annotations

import json
import os
import time
import uuid
from typing import Any, Callable, Dict, List, Optional

from .points import EVOLUTION_POINTS, ApprovalPolicy, get_point
from .store import SettingsStore, append_log, get_store

# ── 状态常量 ─────────────────────────────────────────────

STATUS_PROPOSED = "proposed"
STATUS_AWAITING = "awaiting"
STATUS_APPROVED = "approved"
STATUS_REJECTED = "rejected"
STATUS_APPLIED = "applied"
STATUS_FAILED = "failed"
STATUS_ROLLED_BACK = "rolled_back"
STATUS_ROLLBACK_FAILED = "rollback_failed"
STATUS_PAUSED = "paused"
STATUS_DISABLED = "disabled"

_VALID_KINDS = ("code", "config", "memory", "skill")
_MISS = object()


class ProposalError(RuntimeError):
    """提案操作错误（非法 kind / 状态机不合法 / 未知提案等）。"""


# ══════════════════════════════════════════════════════════
# 熔断器
# ══════════════════════════════════════════════════════════

class CircuitBreaker:
    """按可进化点的熔断器（连续失败计数；状态持久在设置库，可审计）。"""

    def __init__(self, store: Optional[SettingsStore] = None) -> None:
        self.store = store or get_store()

    def _key(self, point: str) -> str:
        return f"evolution.breaker.{point}.state"

    def threshold(self) -> int:
        try:
            return max(1, int(self.store.get("evolution.breaker_threshold", 3) or 3))
        except Exception:  # noqa: BLE001
            return 3

    def state(self, point: str) -> Dict[str, Any]:
        raw = self.store.get_raw(self._key(point), None)
        if not isinstance(raw, dict):
            raw = {}
        return {
            "point": point,
            "consecutive_failures": int(raw.get("consecutive_failures") or 0),
            "paused": bool(raw.get("paused")),
            "opened_at": raw.get("opened_at"),
            "last_error": str(raw.get("last_error") or ""),
            "threshold": self.threshold(),
        }

    def note_success(self, point: str) -> Dict[str, Any]:
        raw = self.store.get_raw(self._key(point), None)
        if isinstance(raw, dict) and (raw.get("consecutive_failures") or raw.get("paused")):
            self.store.set(self._key(point),
                           {"consecutive_failures": 0, "paused": False,
                            "cleared_at": time.time()},
                           actor="evolution:breaker",
                           reason=f"success reset for {point}")
        return self.state(point)

    def note_failure(self, point: str, error: str = "") -> Dict[str, Any]:
        raw = self.store.get_raw(self._key(point), None)
        raw = dict(raw) if isinstance(raw, dict) else {}
        n = int(raw.get("consecutive_failures") or 0) + 1
        threshold = self.threshold()
        try:
            auto = bool(self.store.get("evolution.breaker_auto_pause", True))
        except Exception:  # noqa: BLE001
            auto = True
        paused = bool(raw.get("paused"))
        if auto and n >= threshold:
            paused = True
        raw.update({
            "consecutive_failures": n,
            "last_error": str(error)[:500],
            "updated_at": time.time(),
            "paused": paused,
        })
        if paused and not raw.get("opened_at"):
            raw["opened_at"] = time.time()
        self.store.set(self._key(point), raw, actor="evolution:breaker",
                       reason=f"failure #{n} for {point}")
        if paused:
            append_log({"event": "evolution.breaker.open", "point": point,
                        "failures": n, "threshold": threshold})
        return self.state(point)

    def resume(self, point: str, actor: str = "user") -> Dict[str, Any]:
        """人工恢复（解除熔断暂停）。"""
        self.store.set(self._key(point),
                       {"consecutive_failures": 0, "paused": False,
                        "resumed_at": time.time()},
                       actor=actor, reason=f"breaker resume for {point}")
        append_log({"event": "evolution.breaker.resume", "point": point})
        return self.state(point)

    def all_states(self) -> List[Dict[str, Any]]:
        return [self.state(p.id) for p in EVOLUTION_POINTS]


# ══════════════════════════════════════════════════════════
# 提案板（提案 → 裁决 → 执行 → 验证 → 固化）
# ══════════════════════════════════════════════════════════

class ProposalBoard:
    """进化提案板：全流程受控（勾选制裁决 / 失败回滚 / 熔断 / 日志审计）。

    ``notifier`` 为可选通知回调（如 Web 面板的 SSE 发布函数）：
    熔断打开与提案状态变化时调用，不阻塞主流程。
    """

    def __init__(self, store: Optional[SettingsStore] = None,
                 breaker: Optional[CircuitBreaker] = None,
                 notifier: Optional[Callable[[Dict[str, Any]], None]] = None) -> None:
        self.store = store or get_store()
        self.breaker = breaker or CircuitBreaker(self.store)
        self.policy = ApprovalPolicy(self.store)
        self.notifier = notifier

    # ── 通知（尽力而为） ─────────────────────────────────

    def _notify(self, kind: str, message: str, **extra: Any) -> None:
        if self.notifier is None:
            return
        try:
            self.notifier({"kind": kind, "message": message, **extra})
        except Exception:  # noqa: BLE001 — 通知失败不影响进化动作
            pass

    # ── 提案 ─────────────────────────────────────────────

    def create(self, point: str, kind: str, title: str, *,
               summary: str = "", payload: Optional[Dict[str, Any]] = None,
               reason: str = "", impact: str = "", risk: str = "medium",
               diff: str = "") -> Dict[str, Any]:
        """创建提案（机器可读 JSON + 人可读摘要；落库 + 日志）。"""
        if kind not in _VALID_KINDS:
            raise ProposalError(
                f"invalid proposal kind {kind!r} (use one of {_VALID_KINDS})")
        if get_point(point) is None:
            raise ProposalError(f"unknown evolution point: {point}")
        pid = ("prop-" + time.strftime("%Y%m%d%H%M%S")
               + "-" + uuid.uuid4().hex[:6])
        rec: Dict[str, Any] = {
            "id": pid,
            "point": point,
            "kind": kind,
            "title": str(title),
            "summary": str(summary),
            "reason": str(reason),
            "impact": str(impact),
            "risk": str(risk),
            "diff": str(diff),
            "payload": dict(payload or {}),
            "status": STATUS_PROPOSED,
            "created_at": time.time(),
            "decided_by": "",
            "decided_at": None,
            "applied_at": None,
            "error": "",
            "evidence": {},
        }
        self.store.proposal_add(rec)
        append_log({"event": "evolution.proposal.created", "proposal": rec})
        self._notify("proposal", f"proposal created: {title}", proposal=rec)
        return rec

    def get(self, proposal_id: str) -> Dict[str, Any]:
        rec = self.store.proposal_get(proposal_id)
        if rec is None:
            raise ProposalError(f"proposal not found: {proposal_id}")
        return rec

    def list(self, status: Optional[str] = None,
             limit: int = 100) -> List[Dict[str, Any]]:
        return self.store.proposal_list(status=status, limit=limit)

    # ── 裁决（勾选制） ───────────────────────────────────

    def decide(self, proposal_id: str, approve: Optional[bool] = None,
               actor: str = "user") -> Dict[str, Any]:
        """裁决一条提案。

        - 勾选制：该点勾选 = 人工批准 → 未显式 approve 时进入 awaiting（待批卡片）；
        - 不勾 = 自动批准 → 直接 approved；
        - ``approve=True/False`` 为人工显式裁决（待批卡片的确认 / 否决）。
        """
        rec = self.get(proposal_id)
        if rec["status"] in (STATUS_APPLIED, STATUS_REJECTED, STATUS_FAILED,
                             STATUS_ROLLED_BACK, STATUS_ROLLBACK_FAILED):
            return rec
        point_state = self.breaker.state(rec["point"])
        if point_state["paused"]:
            rec["status"] = STATUS_PAUSED
            rec["error"] = "circuit breaker open for this point (resume first)"
            self.store.proposal_update(rec)
            append_log({"event": "evolution.proposal.paused", "id": rec["id"]})
            self._notify("proposal", f"proposal paused by circuit breaker: {rec['title']}", proposal=rec)
            return rec
        decision = self.policy.decide(rec["point"])
        if decision.get("requires_human") and approve is None:
            rec["status"] = STATUS_AWAITING
            self.store.proposal_update(rec)
            append_log({"event": "evolution.proposal.awaiting", "id": rec["id"],
                        "point": rec["point"]})
            self._notify("proposal", f"proposal awaiting manual approval: {rec['title']}",
                         proposal=rec)
            return rec
        approved = True if approve is None else bool(approve)
        rec["status"] = STATUS_APPROVED if approved else STATUS_REJECTED
        rec["decided_by"] = str(actor)
        rec["decided_at"] = time.time()
        self.store.proposal_update(rec)
        append_log({"event": f"evolution.proposal.{rec['status']}",
                    "id": rec["id"], "by": actor})
        self._notify("proposal",
                     f"proposal {'approved' if approved else 'rejected'}: {rec['title']}",
                     proposal=rec)
        return rec

    # ── 执行（含验证 / 失败回滚 / 熔断计次） ──────────────

    def execute(self, proposal_id: str,
                executor: Optional[Callable[["ProposalBoard", Dict[str, Any]], Any]] = None
                ) -> Dict[str, Any]:
        """执行一条已批准提案：应用 → 验证 → 固化；失败自动回滚 + 熔断计次。"""
        rec = self.get(proposal_id)
        if rec["status"] == STATUS_AWAITING:
            return rec  # 待批：不执行
        if rec["status"] not in (STATUS_APPROVED, STATUS_FAILED):
            return rec
        if not bool(self.store.get("evolution.enabled", True)):
            rec["status"] = STATUS_DISABLED
            rec["error"] = "evolution is disabled (evolution.enabled = false)"
            self.store.proposal_update(rec)
            return rec
        point_state = self.breaker.state(rec["point"])
        if point_state["paused"]:
            rec["status"] = STATUS_PAUSED
            rec["error"] = "circuit breaker open for this point (resume first)"
            self.store.proposal_update(rec)
            return rec
        rec["status"] = STATUS_APPROVED
        rec["error"] = ""
        try:
            if executor is not None:
                result = executor(self, rec)
            else:
                result = self._default_apply(rec)
            rec["evidence"] = {"apply": _jsonable(result)}
            verify = self._default_verify(rec)
            rec["evidence"]["verify"] = _jsonable(verify)
            if not verify.get("ok"):
                raise ProposalError(f"verify failed: {verify.get('error') or verify}")
        except Exception as exc:  # noqa: BLE001 — 失败必须如实落账 + 回滚
            rec["status"] = STATUS_FAILED
            rec["error"] = f"{type(exc).__name__}: {exc}"
            rollback = self._safe_rollback(rec)
            rec["evidence"]["rollback"] = _jsonable(rollback)
            if rec.get("_rollback") and not rollback.get("ok"):
                # 有回退方案却回退失败：绝不谎报已回滚，如实置 rollback_failed。
                rec["status"] = STATUS_ROLLBACK_FAILED
                rec["error"] = (f"{rec['error']} | rollback FAILED: "
                                f"{rollback.get('error')}")
            self.store.proposal_update(rec)
            breaker_state = self.breaker.note_failure(rec["point"], rec["error"])
            append_log({"event": "evolution.proposal.failed", "id": rec["id"],
                        "error": rec["error"], "rollback": rollback})
            if breaker_state.get("paused"):
                self._notify("breaker",
                             f"circuit breaker open: {rec['point']} failed "
                             f"{breaker_state['consecutive_failures']} times in a row; "
                             f"evolution paused for this point",
                             point=rec["point"], state=breaker_state)
            return rec
        rec["status"] = STATUS_APPLIED
        rec["applied_at"] = time.time()
        self.store.proposal_update(rec)
        self.breaker.note_success(rec["point"])
        append_log({"event": "evolution.proposal.applied", "id": rec["id"],
                    "point": rec["point"], "kind": rec["kind"]})
        self._notify("proposal", f"proposal applied: {rec['title']}", proposal=rec)
        return rec

    def run(self, proposal_id: str, approve: Optional[bool] = None,
            actor: str = "user") -> Dict[str, Any]:
        """一键流程：裁决（含待批）→（批准后）执行。"""
        rec = self.decide(proposal_id, approve=approve, actor=actor)
        if rec["status"] == STATUS_APPROVED:
            rec = self.execute(proposal_id)
        return rec

    # ── 运行期加固：活跃版本巡检（2026-09-12） ─────────────

    def health_sweep(self, limit: int = 500) -> Dict[str, Any]:
        """巡检已应用（applied）代码提案的活跃版本；损坏则回退标记 + 熔断。

        运行期加固：新版本文件被删除/破坏、原文件被意外改动等「激活后才
        暴露」的问题，由本巡检在启动（bootstrap）或手动调用时统一发现处置：
          - kind=code 且 status=applied 的提案逐条核验（hotswap.verify_active：
            新文件存在 / 可加载 / 原文件 sha256 未变）；
          - 核验失败：状态置 rolled_back、错误如实记录、熔断计次并通知。
        返回 {'ok', 'checked', 'broken', 'details'}；不抛错（巡检失败不阻塞）。
        """
        from .hotswap import verify_active

        checked = 0
        broken = 0
        details: List[Dict[str, Any]] = []
        try:
            rows = self.store.proposal_list(limit=max(1, int(limit)))
        except Exception as exc:  # noqa: BLE001 — 巡检尽力而为，绝不阻塞
            return {"ok": False, "checked": 0, "broken": 0,
                    "error": f"{type(exc).__name__}: {exc}", "details": []}
        for rec in rows:
            if rec.get("kind") != "code" or rec.get("status") != STATUS_APPLIED:
                continue
            checked += 1
            code_record = ((rec.get("_rollback") or {}).get("record") or {})
            if not code_record:
                # 旧记录缺 _rollback：以 payload / evidence 重建最小核验记录
                payload = rec.get("payload") or {}
                staged = ((rec.get("evidence") or {}).get("apply") or {}).get("staged")
                code_record = {
                    "target_path": str(payload.get("target_path") or ""),
                    "new_path": str(staged or ""),
                    "old_sha256": None,
                }
            verify = verify_active(code_record)
            if verify.get("ok"):
                continue
            broken += 1
            rec["error"] = f"health sweep failed: {verify.get('error')}"
            evidence = rec.setdefault("evidence", {})
            if isinstance(evidence, dict):
                evidence["health_sweep"] = verify
            # 真正执行回退（此前只标状态不动作——会谎报“已回滚”）。
            rollback = self._safe_rollback(rec)
            if isinstance(evidence, dict):
                evidence["rollback"] = _jsonable(rollback)
            if rollback.get("ok"):
                rec["status"] = STATUS_ROLLED_BACK
                note = (f"runtime sweep found a problem and rolled back: "
                        f"{rec.get('title') or rec.get('id')}")
            else:
                rec["status"] = STATUS_ROLLBACK_FAILED
                rec["error"] = (f"{rec['error']} | rollback FAILED: "
                                f"{rollback.get('error')}")
                note = (f"runtime sweep found a problem; ROLLBACK FAILED "
                        f"(change may still be live): "
                        f"{rec.get('title') or rec.get('id')}")
            rec["swept_at"] = time.time()
            self.store.proposal_update(rec)
            state = self.breaker.note_failure(
                str(rec.get("point") or ""), rec["error"])
            append_log({"event": "evolution.health.sweep_failed",
                        "id": rec.get("id"), "error": rec["error"],
                        "rollback_ok": bool(rollback.get("ok"))})
            self._notify("breaker", note, proposal=rec, state=state)
            details.append({"id": rec.get("id"), "error": rec["error"],
                            "rollback_ok": bool(rollback.get("ok"))})
        return {"ok": True, "checked": checked, "broken": broken,
                "details": details}

    # ── kind 级默认执行 / 验证 / 回滚 ─────────────────────

    def _default_apply(self, rec: Dict[str, Any]) -> Dict[str, Any]:
        kind = rec.get("kind")
        payload = rec.get("payload") or {}
        if kind == "config":
            key = str(payload.get("key") or "").strip()
            if not key:
                raise ProposalError("config proposal needs payload.key")
            value = payload.get("value")
            old = self.store.get_raw(key, _MISS)
            rec["_rollback"] = {
                "kind": "config", "key": key,
                "had_value": old is not _MISS,
                "old_value": None if old is _MISS else old,
            }
            # 进化器写入：锁定 / 非可进化项被内核拒绝（§7.6 防线）
            self.store.set(key, value, actor=f"evolution:{rec['point']}",
                           reason=f"proposal {rec['id']}")
            return {"applied": {"key": key, "value": value}}
        if kind == "code":
            from .hotswap import (
                activate,
                original_intact,
                stage_new_version,
                verify_active,
            )

            target = str(payload.get("target_path") or "").strip()
            new_code = str(payload.get("new_code") or "")
            if not target or not new_code:
                raise ProposalError("code proposal needs payload.target_path/new_code")
            record = stage_new_version(target, new_code,
                                       tag=str(payload.get("tag") or "proposal"),
                                       description=rec.get("title") or "")
            # 激活 = 加载新文件（语法 / 导入错误在此抛出 → 失败自动回滚语义；
            # 原文件字节始终不动，可一键回退）。apply_fn 可由自定义执行器注入
            # 以把新逻辑切换到具体挂载点。
            apply_fn = payload.get("apply_fn")

            def _post_health(_module: Any) -> None:
                # 运行期加固（2026-09-12）：激活后核验活跃版本仍完好
                # （新文件存在 / 可加载 / 原文件未动）；失败触发自动回退。
                verify = verify_active(record)
                if not verify.get("ok"):
                    raise ProposalError(
                        f"post-activation verify failed: {verify.get('error')}")

            activate(record, validate=None, apply_fn=apply_fn,
                     health=_post_health)
            rec["_rollback"] = {"kind": "code", "record": record}
            return {"staged": record.get("new_path"),
                    "activated": True,
                    "health_ok": bool(record.get("health_ok")),
                    "original_intact": original_intact(record)}
        if kind == "memory":
            from .engines import MemoryEvolver

            evolver = MemoryEvolver(self.store,
                                    context_path=payload.get("context_path"))
            result = evolver.apply_payload(payload)
            rec["_rollback"] = {"kind": "memory", "result": result}
            return result
        if kind == "skill":
            from .engines import SkillEvolver

            evolver = SkillEvolver(self.store, skills_dir=payload.get("skills_dir"))
            result = evolver.apply_payload(payload)
            rec["_rollback"] = {"kind": "skill", "name": result.get("name")}
            return result
        raise ProposalError(f"unsupported proposal kind: {kind!r}")

    def _default_verify(self, rec: Dict[str, Any]) -> Dict[str, Any]:
        kind = rec.get("kind")
        payload = rec.get("payload") or {}
        try:
            if kind == "config":
                key = str(payload.get("key") or "")
                cur = self.store.get_raw(key, _MISS)
                ok = cur is not _MISS and cur == payload.get("value")
                return {"ok": bool(ok), "key": key,
                        "error": None if ok else "value not persisted"}
            if kind == "code":
                from .hotswap import original_intact

                record = (rec.get("_rollback") or {}).get("record") or {}
                ok = bool(record.get("new_path")) and os.path.exists(
                    str(record.get("new_path"))) and original_intact(record)
                return {"ok": ok, "new_path": record.get("new_path"),
                        "original_intact": original_intact(record) if record else False,
                        "error": None if ok else "new version file missing or original touched"}
            if kind == "memory":
                details = (rec.get("evidence") or {}).get("apply") or {}
                return {"ok": bool(details.get("ok", True)), "detail": details}
            if kind == "skill":
                from .engines import SkillEvolver

                evolver = SkillEvolver(self.store, skills_dir=payload.get("skills_dir"))
                ok = any(e.get("name") == payload.get("name")
                         for e in evolver.registry())
                return {"ok": ok, "name": payload.get("name"),
                        "error": None if ok else "skill not registered"}
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
        return {"ok": True}

    def _safe_rollback(self, rec: Dict[str, Any]) -> Dict[str, Any]:
        plan = rec.get("_rollback") or {}
        kind = plan.get("kind")
        try:
            if kind == "config":
                if plan.get("had_value"):
                    self.store.set(plan["key"], plan.get("old_value"),
                                   actor="rollback",
                                   reason=f"rollback {rec.get('id')}")
                else:
                    self.store.delete(plan["key"], actor="rollback",
                                      reason=f"rollback {rec.get('id')}")
                rec["status"] = STATUS_ROLLED_BACK
                return {"ok": True, "restored": plan.get("key")}
            if kind == "code":
                from .hotswap import rollback as hs_rollback

                record = plan.get("record") or {}
                # 运行态回退回调：应用与回退必须是同一个 apply_fn，否则不还原。
                apply_fn = (rec.get("payload") or {}).get("apply_fn")
                if not callable(apply_fn):
                    apply_fn = None
                try:
                    hs_rollback(record, apply_fn=apply_fn)
                except Exception as exc:  # noqa: BLE001 — 回退失败如实上报
                    return {"ok": False, "rolled_back": False,
                            "error": f"{type(exc).__name__}: {exc}"}
                rec["status"] = STATUS_ROLLED_BACK
                return {"ok": True, "rolled_back": record.get("new_path")}
            if kind == "memory":
                rec["status"] = STATUS_ROLLED_BACK
                return {"ok": True, "detail": "memory soft-delete is restorable "
                                              "via evolver.restore(origin_id)"}
            if kind == "skill":
                from .engines import SkillEvolver

                SkillEvolver(self.store).remove(str(plan.get("name") or ""))
                rec["status"] = STATUS_ROLLED_BACK
                return {"ok": True, "removed": plan.get("name")}
        except Exception as exc:  # noqa: BLE001 — 回滚失败如实记录
            return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
        return {"ok": False, "error": "no rollback plan"}

    # ── 反思辅助（一键提案） ─────────────────────────────

    def propose_config(self, key: str, value: Any, *,
                       point: str = "kernel.models", reason: str = "",
                       **kw: Any) -> Dict[str, Any]:
        """配置进化提案（2C；只允许 schema 标记 evolvable 的项被执行）。"""
        return self.create(
            point, "config", kw.pop("title", f"config tweak: {key}"),
            payload={"key": key, "value": value}, reason=reason, **kw)

    def propose_code(self, target_path: str, new_code: str, *,
                     point: str = "kernel.agent", reason: str = "",
                     tag: str = "", **kw: Any) -> Dict[str, Any]:
        """代码进化提案（2D；产出新文件、原文件字节不动、可一键回退）。"""
        return self.create(
            point, "code",
            kw.pop("title", f"code evolution: {os.path.basename(target_path)}"),
            payload={"target_path": target_path, "new_code": new_code,
                     "tag": tag}, reason=reason, **kw)

    def propose_memory(self, action: str, ids: List[Any], *,
                       point: str = "kernel.context", reason: str = "",
                       **kw: Any) -> Dict[str, Any]:
        """记忆进化提案（2A；软删 + 可恢复 + 审计）。"""
        return self.create(
            point, "memory",
            kw.pop("title", f"memory evolution: {action}"),
            payload={"action": action, "ids": list(ids)}, reason=reason, **kw)

    def propose_skill(self, name: str, artifact: Dict[str, Any], *,
                      point: str = "kernel.tools", reason: str = "",
                      **kw: Any) -> Dict[str, Any]:
        """技能进化提案（2B；登记装载 + .fspack 存档）。"""
        return self.create(
            point, "skill", kw.pop("title", f"skill evolution: {name}"),
            payload={"name": name, "artifact": artifact}, reason=reason, **kw)


def _jsonable(obj: Any, _depth: int = 0) -> Any:
    """收敛为可 JSON 序列化结构（防提案证据炸序列化）。"""
    if _depth > 6:
        return str(obj)[:2000]
    if isinstance(obj, dict):
        return {str(k): _jsonable(v, _depth + 1) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_jsonable(v, _depth + 1) for v in obj]
    if isinstance(obj, (bool, int, float)) or obj is None:
        return obj
    return str(obj)[:2000]


__all__ = [
    "ProposalError",
    "CircuitBreaker",
    "ProposalBoard",
    "STATUS_PROPOSED", "STATUS_AWAITING", "STATUS_APPROVED", "STATUS_REJECTED",
    "STATUS_APPLIED", "STATUS_FAILED", "STATUS_ROLLED_BACK", "STATUS_PAUSED",
    "STATUS_DISABLED",
]
