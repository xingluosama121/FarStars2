# -*- coding: utf-8 -*-
"""
norpagent.cnb.permissions — 神经权限表

大脑皮层通过中枢神经总线对「任意层级任意单位原子」进行操作权限控制。

权限模型：
- 权限原子与 permission_cascade.Permission 语义对齐（file_read / file_write /
  process_exec / process_shell / network_out ...）。
- 每个目标（node_id 精确匹配，或 node_kind 通配，或 "*" 全量通配）维护
  一组权限状态：allow=True 表示授予，allow=False 表示撤销。
- 判定规则（B4 修订）：**纯时间序**——命中本节点且权限原子相同的规则中，
  最近写入的一条生效（后写覆盖先写，跨 target 粒度同样生效）。皮层按时间
  顺序下发指令，最新一条代表最新管理意图：先特批 node_id 再收紧 node_kind
  会收紧；先收紧再特批会放开；不会被更早的旧规则屏蔽。
- 默认策略：allow-by-default（未受控的权限默认允许，由皮层显式收紧）。
  皮层可通过 cmd.perm.set 对某目标一次性整体覆盖，实现「白名单收紧」。
"""

import threading
import time
from typing import Any, Dict, List, Optional

from .protocol import PERMISSION_ATOMS, is_valid_perm


class PermRule:
    """一条权限规则。"""

    def __init__(self, target_type: str, target: str, perm: str,
                 allow: bool, scope: Optional[Dict] = None,
                 source: str = "cortex", ts: Optional[float] = None):
        self.target_type = target_type      # "node_id" | "node_kind" | "*"
        self.target = target
        self.perm = perm
        self.allow = bool(allow)
        self.scope = dict(scope or {})      # 可选：{"whitelist": [...], "blacklist": [...]}
        self.source = source                # 下发指令的节点
        self.ts = ts if ts is not None else time.time()

    def to_dict(self) -> Dict:
        return {
            "target_type": self.target_type,
            "target": self.target,
            "perm": self.perm,
            "allow": self.allow,
            "scope": self.scope,
            "source": self.source,
            "ts": self.ts,
        }


class NeuralPermissionTable:
    """神经权限表（线程安全）。

    这是每个 CNB 节点本地持有的权限视图：皮层下发的权限指令（cmd.perm.*）
    落地为本表规则；本地工具/动作执行前调用 check() 判定是否被允许。
    """

    def __init__(self, node_id: str, node_kind: str = "node"):
        self.node_id = node_id
        self.node_kind = node_kind
        self._lock = threading.RLock()
        self._rules: List[PermRule] = []          # 按写入顺序追加（后写覆盖先写）
        self._history: List[Dict] = []            # 审计历史（最近 200 条）
        self._changed_at = time.time()

    # ------------------------------------------------------------------
    # 规则写入（仅由下行指令 cmd.perm.* 驱动）
    # ------------------------------------------------------------------

    def apply(self, target_type: str, target: str, perm: str,
              allow: bool, scope: Optional[Dict] = None,
              source: str = "cortex") -> bool:
        """应用一条权限规则。返回是否合法（perm 原子是否有效）。"""
        if not is_valid_perm(perm):
            self._history.append({
                "ts": time.time(), "op": "apply_rejected",
                "reason": f"未知权限原子: {perm}", "source": source,
            })
            return False
        if target_type not in ("node_id", "node_kind", "*"):
            self._history.append({
                "ts": time.time(), "op": "apply_rejected",
                "reason": f"非法目标类型: {target_type}", "source": source,
            })
            return False

        with self._lock:
            rule = PermRule(target_type, target, perm, allow, scope, source)
            self._rules.append(rule)
            self._changed_at = time.time()
            self._history.append({
                "ts": rule.ts, "op": "grant" if allow else "revoke",
                "target_type": target_type, "target": target,
                "perm": perm, "scope": scope, "source": source,
            })
            # 审计历史最多保留 200 条
            if len(self._history) > 200:
                self._history = self._history[-200:]
            return True

    def set_all(self, target_type: str, target: str,
                allows: Dict[str, bool], source: str = "cortex") -> int:
        """整体覆盖：对目标一次性设置多组权限（cmd.perm.set）。

        先清除该目标旧规则，再写入新规则。返回写入成功的条数。
        """
        with self._lock:
            # 清除该目标旧规则
            self._rules = [r for r in self._rules
                           if not (r.target_type == target_type and r.target == target)]
            ok = 0
            for perm, allow in (allows or {}).items():
                if self.apply_locked(target_type, target, perm, allow, None, source):
                    ok += 1
            return ok

    def apply_locked(self, target_type: str, target: str, perm: str,
                     allow: bool, scope: Optional[Dict], source: str) -> bool:
        """锁内写入（供 set_all 复用）。"""
        if not is_valid_perm(perm):
            return False
        rule = PermRule(target_type, target, perm, allow, scope, source)
        self._rules.append(rule)
        self._changed_at = time.time()
        self._history.append({
            "ts": rule.ts, "op": "grant" if allow else "revoke",
            "target_type": target_type, "target": target,
            "perm": perm, "scope": scope, "source": source,
        })
        if len(self._history) > 200:
            self._history = self._history[-200:]
        return True

    # ------------------------------------------------------------------
    # 权限判定
    # ------------------------------------------------------------------

    def check(self, perm: str, path: str = "", actor: Optional[Dict] = None) -> bool:
        """检查当前节点是否被允许执行 perm 操作。

        判定规则（B4 修订，纯时间序）：
          - 遍历全部规则（node_id / node_kind / * 均参与），命中本节点
            （精确 id / 类型通配 / 全量通配）且 perm 相同者中，取
            「最近写入」的一条为准 —— 后写覆盖先写，跨粒度同样生效。
          - 语义：皮层按时间顺序下发指令，最近一条代表最新管理意图；
            无论其粒度（先特批 node_id 后收紧 node_kind 会收紧，
            先收紧后特批会放开），都不会被更早的旧规则屏蔽。
          - 无任何规则命中 => 默认允许（allow-by-default，由皮层显式收紧）。
        """
        if not is_valid_perm(perm):
            return False

        with self._lock:
            best = None  # 最近写入的命中规则
            for i, r in enumerate(self._rules):
                if r.perm != perm:
                    continue
                if r.target_type == "node_id" and r.target == self.node_id:
                    pass
                elif r.target_type == "node_kind" and r.target == self.node_kind:
                    pass
                elif r.target_type == "*":
                    pass
                else:
                    continue
                if best is None or i > best[0]:
                    best = (i, r)

            if best is None:
                return True  # 默认允许

            # 作用域（路径白/黑名单）检查
            rule = best[1]
            if path:
                wl = rule.scope.get("whitelist") or []
                bl = rule.scope.get("blacklist") or []
                if wl and not any(path.startswith(p) for p in wl):
                    return False
                if bl and any(path.startswith(p) for p in bl):
                    return False

            return rule.allow

    # ------------------------------------------------------------------
    # 查询与导出
    # ------------------------------------------------------------------

    def rules(self) -> List[Dict]:
        with self._lock:
            return [r.to_dict() for r in self._rules]

    def history(self) -> List[Dict]:
        with self._lock:
            return list(self._history)

    def summary(self) -> Dict:
        """导出给上层（皮层）看的权限视图。"""
        with self._lock:
            return {
                "node_id": self.node_id,
                "node_kind": self.node_kind,
                "rules": [r.to_dict() for r in self._rules],
                "changed_at": self._changed_at,
            }
