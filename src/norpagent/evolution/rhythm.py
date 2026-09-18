# Copyright (c) 2026 xingluosama121, MIT Licensed
"""norpagent.evolution.rhythm — 进化节奏与方向。

- 无需求闲时**减少或不进化**：``IdlePlanner`` 按闲时时长 + 策略档决定是否
  进入进化环（``reduced`` 减少 / ``off`` 停 / ``auto`` 维持）；
- 进化方向由**用户常用（≥3 次）功能**决定：``UsageTracker`` 统计功能使用
  次数，达阈值进入进化候选；
- 也可由用户**直接下达命令**进化：``command_evolution`` 记录命令式通道
  （直接入库日志 + 返回受理记录，命令式提案优先级最高）。
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from .store import append_log, get_store

DEFAULT_CANDIDATE_THRESHOLD = 3


class UsageTracker:
    """功能使用计数（≥3 次进入进化候选；阈值本身可设置）。"""

    def __init__(self, store: Optional[Any] = None) -> None:
        self.store = store or get_store()

    @staticmethod
    def _key(feature: str) -> str:
        return f"evolution.usage.{str(feature).strip()}"

    def note(self, feature: str, n: int = 1) -> int:
        """记一次功能使用（运行期写入；非进化器写入，不受锁定守卫限制）。"""
        feature = str(feature or "").strip()
        if not feature:
            raise ValueError("feature must be a non-empty string")
        key = self._key(feature)
        cur = int(self.store.get(key, 0) or 0)
        cur += max(1, int(n))
        self.store.set(key, cur, actor="runtime", reason="feature usage")
        return cur

    def count(self, feature: str) -> int:
        return int(self.store.get(self._key(feature), 0) or 0)

    def threshold(self) -> int:
        return int(self.store.get("evolution.candidate_threshold",
                                  DEFAULT_CANDIDATE_THRESHOLD)
                   or DEFAULT_CANDIDATE_THRESHOLD)

    def candidates(self, threshold: Optional[int] = None) -> List[Dict[str, Any]]:
        """达到使用阈值的功能列表（进化方向候选）。"""
        t = int(threshold if threshold is not None else self.threshold())
        out: List[Dict[str, Any]] = []
        for key, value in (self.store.all() or {}).items():
            if not str(key).startswith("evolution.usage."):
                continue
            try:
                count = int(value)
            except (TypeError, ValueError):
                continue
            if count >= t:
                out.append({"feature": str(key)[len("evolution.usage."):],
                            "count": count})
        out.sort(key=lambda r: -r["count"])
        return out


class IdlePlanner:
    """闲时进化策略（无需求闲时减少或不进化）。"""

    def __init__(self, store: Optional[Any] = None) -> None:
        self.store = store or get_store()

    def policy(self) -> str:
        return str(self.store.get("evolution.idle_policy", "reduced")
                   or "reduced").strip().lower()

    def min_idle_seconds(self) -> float:
        try:
            return float(self.store.get("evolution.idle_min_seconds", 600))
        except (TypeError, ValueError):
            return 600.0

    def plan(self, idle_seconds: float,
             candidates: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        """返回闲时进化决策：{should_evolve, reason, policy, candidates}。"""
        policy = self.policy()
        enabled = bool(self.store.get("evolution.enabled", True))
        cand = candidates if candidates is not None else UsageTracker(
            self.store).candidates()
        decision: Dict[str, Any] = {
            "policy": policy,
            "idle_seconds": float(idle_seconds),
            "min_idle_seconds": self.min_idle_seconds(),
            "candidates": cand,
            "enabled": enabled,
            "should_evolve": False,
            "reason": "",
        }
        if not enabled:
            decision["reason"] = "evolution disabled (total switch off)"
            return decision
        if policy == "off":
            decision["reason"] = "idle policy is off: no idle evolution"
            return decision
        if not cand:
            decision["reason"] = "no candidates (usage below threshold)"
            return decision
        if float(idle_seconds) < self.min_idle_seconds():
            decision["reason"] = "not idle long enough"
            return decision
        decision["should_evolve"] = True
        decision["reason"] = ("idle policy 'reduced': evolve only candidate-"
                              "driven items while idle" if policy == "reduced"
                              else "idle policy 'auto': evolve candidates")
        return decision


def command_evolution(command: str,
                      actor: str = "user") -> Dict[str, Any]:
    """命令式进化通道（用户可直接下达命令进化）。

    记录命令并返回受理记录；命令式提案不依赖使用计数与闲时策略
    （优先级最高，执行仍走 热重载 + 勾选审批）。
    """
    command = str(command or "").strip()
    if not command:
        raise ValueError("command must be a non-empty string")
    rec = {
        "event": "evolution.command",
        "command": command,
        "actor": actor,
        "ts": time.time(),
        "accepted": True,
    }
    append_log(rec)
    return rec


__all__ = [
    "DEFAULT_CANDIDATE_THRESHOLD",
    "UsageTracker",
    "IdlePlanner",
    "command_evolution",
]
