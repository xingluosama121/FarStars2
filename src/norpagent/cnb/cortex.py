# -*- coding: utf-8 -*-
"""
norpagent.cnb.cortex — 大脑皮层（最高级 norpagent 实例，神经树根节点）

大脑皮层是整棵神经树的根（level 0，无父节点），拥有：

1. 全量拓扑：所有层级的注册消息沿树逐级上报，最终汇聚于此，
   皮层持有任意层级任意单位原子的完整拓扑视图与总线地址。

2. 任意层级控制：通过中枢神经总线向任意节点下发指令
   - cmd.ping / cmd.exec / cmd.stop / cmd.reload
   - cmd.perm.set / grant / revoke（控制任意层级任意单位原子的操作权限）
   - cmd.topology.sync（向全部后代广播拓扑视图）

3. 控制端点 /cnb/ctrl：供 CLI / REPL / 外部控制台调用（仅本机回环信任）。

皮层自身不可被任何节点控制：下行指令要求发送方必须是接收方的祖先，
皮层没有祖先，天然不受任何下级指令影响（低等级不允许改写高等级）。

REPL 交互控制台命令：
  topo                 查看拓扑树
  ping <node_id>       探活
  exec <node_id> <action> [perm]   下发执行指令
  stop <node_id>       停止任务
  reload <node_id>     重载配置
  grant <type> <target> <perm>     授予权限（type: node_id/node_kind/*）
  revoke <type> <target> <perm>    撤销权限
  set <type> <target> <json>       整体覆盖权限
  reports [n]          查看最近上报（默认 20 条）
  audit [n]            查看皮层审计
  perm_audit [n]       查看权限面审计（皮层权限操作 + 节点上行
                       perm.denied / perm.changed 汇聚）
  sync                 向全部后代广播拓扑
  help / quit
"""

import json
import threading
import time
from typing import Any, Dict, List, Optional

from . import protocol
from .node import NervousNode
from .topology import NodeInfo


class Cortex(NervousNode):
    """大脑皮层：神经树根节点。"""

    def __init__(self, node_id: str = "cortex",
                 host: str = protocol.DEFAULT_HOST,
                 port: int = protocol.DEFAULT_CORTEX_PORT,
                 meta: Optional[Dict] = None,
                 sweep_enabled: bool = True,
                 sweep_interval: float = 10.0,
                 dead_timeout: float = 30.0,
                 drop_grace: float = 90.0):
        """皮层（神经树根）。

        Args:
            sweep_enabled: 是否启用失联清扫守护线程（测试可关闭/调小周期）。
            sweep_interval: 清扫周期（秒）。
            dead_timeout:   超过该时长未收到心跳视为失联（dead）。
            drop_grace:     dead 节点超过该时长仍无心跳（且救援失败）才整支
                            清除，防止误杀「父断链导致上报中断」的活节点。
        """
        super().__init__(
            node_id=node_id,
            kind="cortex",
            level=protocol.LEVEL_CORTEX,
            parent_url=None,          # 根节点：无父
            host=host,
            port=port,
            meta=meta,
            heartbeat_interval=0,     # 根节点不上报心跳
        )
        self._started_at = time.time()
        self.sweep_enabled = sweep_enabled
        self.sweep_interval = float(sweep_interval)
        self.dead_timeout = float(dead_timeout)
        self.drop_grace = float(drop_grace)
        self._sweep_stop = threading.Event()
        self._sweep_thread: Optional[threading.Thread] = None
        self._sync_timer: Optional[threading.Timer] = None
        self._sync_pending = False
        self._sync_lock = threading.Lock()
        # 权限面审计：皮层自身发出的权限操作（结构化记录），与节点上行
        # 汇聚的 perm.denied / perm.changed 事件共同构成统一权限面视图。
        self._perm_audit: List[Dict] = []
        self._perm_audit_lock = threading.RLock()

        # ── 传票（subpoena）签发记录 + 隔离取证箱 ──
        # 签发即留痕：谁/何时/判据/取数范围/容量档/实际字节，
        # 全部结构化记录，且签发记「黑」级事件。
        self._subpoena_audit: List[Dict] = []
        self._subpoena_audit_lock = threading.RLock()
        # 隔离帧（quarantine envelope）：直传包 = RAW/UNTRUSTED 标记 +
        # 一次性裁决实例用后销毁（读取即焚 / TTL 过期自清）+ 不落长期记忆
        # （正文只存于本箱，不进 audit/perm_audit 长期视图）。
        self._subpoena_box: Dict[str, Any] = {}   # subpoena_id -> envelope
        self._subpoena_box_lock = threading.RLock()
        self.subpoena_ttl = 300.0                 # 隔离箱默认 TTL（秒）

        # ── 行为基线分级阈值（皮层判定侧策略，可调）──
        # 依据节点心跳上汇的聚合统计（审计异常率/任务失败率/心跳失败率）
        # 判定：黄 = 劣化（人工复核）、黑 = 疑似恶意（隔离处置）。
        self.behavior_thresholds: Dict[str, float] = {
            "yellow_audit_anomaly_rate": 0.20,   # 审计异常率 ≥20% → 黄
            "black_audit_anomaly_rate": 0.60,    # 审计异常率 ≥60% → 黑
            "yellow_task_fail_rate": 0.30,       # 任务失败率 ≥30% → 黄
            "black_task_fail_rate": 0.70,        # 任务失败率 ≥70% → 黑
            "yellow_hb_fail_rate": 0.30,         # 心跳失败率 ≥30% → 黄
        }

    # ------------------------------------------------------------------
    # 生命周期
    # ------------------------------------------------------------------

    def start(self) -> "Cortex":
        ctx = {
            "node_id": self.node_id,
            "kind": self.kind,
            "level": self.level,
            "on_message": self.on_message,
            "on_reports": self.get_reports,
            "on_ctrl": self.on_ctrl,
            "on_audit": self.audit,  # 总线层拒绝/异常留痕（白盒）
        }
        from .bus import start_bus
        self._bus = start_bus(self.host, self.port, ctx)
        self._running = True
        self._started_at = time.time()
        self.audit("大脑皮层上线")
        if self.sweep_enabled and self.sweep_interval > 0:
            self._sweep_thread = threading.Thread(
                target=self._sweep_loop, daemon=True,
                name=f"cnb-sweep-{self.node_id}")
            self._sweep_thread.start()
        return self

    def stop(self):
        self._sweep_stop.set()
        super().stop()
        with self._sync_lock:
            if self._sync_timer is not None:
                self._sync_timer.cancel()
                self._sync_timer = None
            self._sync_pending = False
        self.audit("大脑皮层下线")

    # ------------------------------------------------------------------
    # 失联清扫 + 救树（B3 崩溃路径 / B5 dead 检测接线）
    # ------------------------------------------------------------------

    def _sweep_loop(self):
        """周期清扫：处置失联（dead）后代。

        - 失联超 drop_grace 的节点：判定真死，整支（含子树）注销。
        - 失联但在宽限期内：执行救树（_rescue_children）——把其直接子提升
          挂到皮层下并通知改挂；真死子节点的改挂通知失败，保留在皮层下
          （dead），待超过宽限期后整支清除（递归每轮收敛一层）。
        注：中间层失联时其子树心跳断链，深层节点会集体显示 dead——这是
        「上报中断」而非「节点真死」；救树 + 宽限期正是为区分二者而设。
        """
        while not self._sweep_stop.is_set():
            try:
                self._sweep_once()
            except Exception as e:
                self.audit(f"清扫异常: {e}")
            self._sweep_stop.wait(self.sweep_interval)

    def _sweep_once(self):
        """单轮清扫：失联标记 + 处置。

        判定：sweep_dead 把超过 dead_timeout 未心跳的节点标记 dead（B5 接线）。
        处置（按失联节点的子孙结构分派）：
          - 有子且失联未超宽限期：救树（_rescue_children）——把其直接子提升
            挂到皮层并下发 cmd.reroot，活子重新锚定后心跳续传；树逐层塌缩，
            真死子（reroot 不可达）逐层上提到皮层后按叶子清除。
          - 有子但失联超宽限期：整支真死，级联注销。
          - 无子叶子且失联超宽限期：注销（宽限期是给「父断链导致上报中断」
            的活叶子留的窗口——其父被救后转发恢复，心跳即续上）。
        """
        now = time.time()
        self.topology.sweep_dead(timeout=self.dead_timeout)
        changed = False
        for n in list(self.topology.all()):
            if n.node_id == self.node_id or n.alive:
                continue
            age = now - n.last_seen
            if n.children:
                if age > self.drop_grace:
                    # 整支失联超宽限：真死，级联注销
                    self.topology.unregister(n.node_id)
                    self.audit(f"失联超宽限期，整支注销: {n.node_id}")
                else:
                    self._rescue_children(n.node_id)  # 提升子 + reroot + 注销自身
                changed = True
            elif age > self.drop_grace:
                self.topology.unregister(n.node_id)
                self.audit(f"失联叶子超宽限期，注销: {n.node_id}")
                changed = True
            # 宽限期内的 dead 叶子：等待（父被救后心跳续传 / 直连父自愈）
        if changed:
            self._maybe_auto_sync()

    # ------------------------------------------------------------------
    # 自动拓扑广播（B8：注册/注销/救树后自动 sync，防抖合并）
    # ------------------------------------------------------------------

    def _maybe_auto_sync(self):
        """拓扑变更后自动广播（防抖 0.5s 合并突发注册/注销风暴）。"""
        with self._sync_lock:
            if self._sync_pending:
                return
            self._sync_pending = True
            self._sync_timer = threading.Timer(0.5, self._sync_due)
            self._sync_timer.daemon = True
            self._sync_timer.start()

    def _sync_due(self):
        with self._sync_lock:
            self._sync_pending = False
            self._sync_timer = None
        try:
            self.sync_topology()
        except Exception as e:
            self.audit(f"自动拓扑广播失败: {e}")

    # ------------------------------------------------------------------
    # 控制 API（皮层 -> 任意层级任意节点）
    # ------------------------------------------------------------------

    def _node_url(self, node_id: str) -> Optional[str]:
        """根据拓扑找到节点的总线地址。"""
        node: Optional[NodeInfo] = self.topology.get(node_id)
        if node is None:
            return None
        return node.meta.get("base_url")

    def _require_node(self, node_id: str) -> NodeInfo:
        node = self.topology.get(node_id)
        if node is None:
            raise ValueError(f"节点不存在于拓扑：{node_id}")
        return node

    def ping(self, node_id: str) -> Dict:
        node = self._require_node(node_id)
        url = self._node_url(node_id)
        if not url:
            return {"ok": False, "error": f"节点 {node_id} 未上报总线地址"}
        return self.send_downlink(node_id, url, "cmd.ping", {})

    def exec_cmd(self, node_id: str, action: str, args: Dict = None,
                 perm: str = "process_exec", path: str = "") -> Dict:
        node = self._require_node(node_id)
        url = self._node_url(node_id)
        if not url:
            return {"ok": False, "error": f"节点 {node_id} 未上报总线地址"}
        r = self.send_downlink(node_id, url, "cmd.exec", {
            "action": action, "args": args or {}, "perm": perm, "path": path,
        })
        # 白盒：皮层发出的 exec 指令全程留痕（谁向谁执行了什么动作、
        # 结果如何），与 perm/freeze/subpoena 的皮层审计视图对齐。
        self.audit(f"皮层执行指令 exec -> {node_id} action={action} "
                   f"(ok={bool(r.get('ok'))})", action=action, node=node_id)
        return r

    def stop_node(self, node_id: str) -> Dict:
        node = self._require_node(node_id)
        url = self._node_url(node_id)
        if not url:
            return {"ok": False, "error": f"节点 {node_id} 未上报总线地址"}
        r = self.send_downlink(node_id, url, "cmd.stop", {})
        self.audit(f"皮层下令停止 -> {node_id} (ok={bool(r.get('ok'))})",
                   node=node_id)
        return r

    def reload_node(self, node_id: str) -> Dict:
        node = self._require_node(node_id)
        url = self._node_url(node_id)
        if not url:
            return {"ok": False, "error": f"节点 {node_id} 未上报总线地址"}
        r = self.send_downlink(node_id, url, "cmd.reload", {})
        self.audit(f"皮层下令重载 -> {node_id} (ok={bool(r.get('ok'))})",
                   node=node_id)
        return r

    # -- 权限控制（任意层级任意单位原子） --

    def _note_perm_op(self, op: str, target_type: str, target: str,
                      perm: str = None, allows: Dict = None,
                      results: List[Dict] = None):
        """皮层自身发出的权限操作 -> 结构化权限面审计记录。"""
        rec = {"ts": time.time(), "op": op, "target_type": target_type,
               "target": target, "perm": perm, "allows": allows,
               "results": list(results or []), "actor": self.node_id}
        with self._perm_audit_lock:
            self._perm_audit.append(rec)
            if len(self._perm_audit) > 500:
                self._perm_audit = self._perm_audit[-500:]
        return rec

    def perm_audit(self, n: int = 50) -> List[Dict]:
        """权限面审计视图：皮层发出的权限操作 + 节点上行汇聚的
        perm.denied / perm.changed 事件（统一视图）。

        每条记录含 ts / from（cortex 或节点 id）/ event / detail，
        供同权限审计读取方直接消费（/cnb/ctrl op=perm_audit）。
        """
        rows: List[Dict] = []
        # 1) 节点上行汇聚：report.audit 中 perm.* 事件
        for r in self.get_reports():
            p = r.get("payload") or {}
            if r.get("type") == "report.audit" \
                    and str(p.get("event", "")).startswith("perm."):
                rows.append({
                    "ts": r.get("ts"), "from": r.get("from"),
                    "event": p.get("event"), "detail": p.get("detail", ""),
                })
        # 2) 皮层自身权限操作（结构化记录）
        with self._perm_audit_lock:
            for rec in self._perm_audit:
                rows.append({
                    "ts": rec["ts"], "from": rec["actor"],
                    "event": f"perm.op.{rec['op']}",
                    "detail": json.dumps(
                        {k: rec[k] for k in ("target_type", "target", "perm",
                                             "allows", "results")
                         if rec.get(k) is not None},
                        ensure_ascii=False),
                })
        rows.sort(key=lambda x: x.get("ts", 0), reverse=True)
        return rows[:max(1, int(n))]

    def perm_grant(self, target_type: str, target: str, perm: str,
                   scope: Dict = None) -> Dict:
        """向目标授予操作权限。target_type: node_id / node_kind / *。"""
        if not protocol.is_valid_perm(perm):
            return {"ok": False, "error": f"未知权限原子: {perm}"}
        results = self._dispatch_perm("cmd.perm.grant", target_type, target,
                                      perm, True, scope)
        self.audit(f"皮层授予权限 {perm} -> {target_type}:{target}")
        self._note_perm_op("grant", target_type, target, perm=perm,
                           results=results)
        return {"ok": True, "results": results}

    def perm_revoke(self, target_type: str, target: str, perm: str) -> Dict:
        """撤销目标的操作权限。"""
        if not protocol.is_valid_perm(perm):
            return {"ok": False, "error": f"未知权限原子: {perm}"}
        results = self._dispatch_perm("cmd.perm.revoke", target_type, target,
                                      perm, False, None)
        self.audit(f"皮层撤销权限 {perm} -> {target_type}:{target}")
        self._note_perm_op("revoke", target_type, target, perm=perm,
                           results=results)
        return {"ok": True, "results": results}

    def perm_set(self, target_type: str, target: str,
                 allows: Dict[str, bool]) -> Dict:
        """整体覆盖目标权限（白名单收紧模式）。"""
        results = self._dispatch_perm_set(target_type, target, allows)
        self.audit(f"皮层整体设置权限 -> {target_type}:{target}: {allows}")
        self._note_perm_op("set", target_type, target, allows=allows,
                           results=results)
        return {"ok": True, "results": results}

    def _dispatch_perm(self, msg_type: str, target_type: str, target: str,
                       perm: str, allow: bool, scope: Optional[Dict]) -> List[Dict]:
        """把权限指令下发到匹配目标的所有节点（含通配展开）。"""
        targets = self._match_targets(target_type, target)
        results = []
        payload = {
            "target_type": target_type, "target": target,
            "perm": perm, "scope": scope or {},
            "source": self.node_id,
        }
        for node_id in targets:
            url = self._node_url(node_id)
            if not url:
                results.append({"node": node_id, "ok": False,
                                "error": "no url"})
                continue
            r = self.send_downlink(node_id, url, msg_type, payload)
            results.append({"node": node_id, **r})
        return results

    def _dispatch_perm_set(self, target_type: str, target: str,
                           allows: Dict[str, bool]) -> List[Dict]:
        targets = self._match_targets(target_type, target)
        results = []
        payload = {
            "target_type": target_type, "target": target,
            "allows": allows, "source": self.node_id,
        }
        for node_id in targets:
            url = self._node_url(node_id)
            if not url:
                results.append({"node": node_id, "ok": False,
                                "error": "no url"})
                continue
            r = self.send_downlink(node_id, url, "cmd.perm.set", payload)
            results.append({"node": node_id, **r})
        return results

    def _match_targets(self, target_type: str, target: str) -> List[str]:
        """展开权限指令的目标节点列表（node_id 精确 / node_kind 通配 / * 全量）。"""
        if target_type == "node_id":
            node = self.topology.get(target)
            return [target] if node else []
        if target_type == "node_kind":
            return [n.node_id for n in self.topology.all()
                    if n.kind == target]
        if target_type == "*":
            return [n.node_id for n in self.topology.all()
                    if n.node_id != self.node_id]
        return []

    # -- 拓扑广播 --

    def sync_topology(self) -> Dict:
        """向全部后代广播拓扑视图（cmd.topology.sync）。"""
        nodes = [n.to_dict() for n in self.topology.all()]
        sent, failed = 0, 0
        for n in self.topology.all():
            if n.node_id == self.node_id:
                continue
            url = n.meta.get("base_url")
            if not url:
                failed += 1
                continue
            r = self.send_downlink(n.node_id, url, "cmd.topology.sync",
                                   {"nodes": nodes, "source": self.node_id})
            if r.get("ok"):
                sent += 1
            else:
                failed += 1
        self.audit(f"拓扑广播完成：{sent} 成功，{failed} 失败")
        return {"ok": True, "sent": sent, "failed": failed}

    def topology_view(self) -> Dict:
        return {
            "ok": True,
            "size": self.topology.size(),
            "tree": self.topology.render_ascii(),
            "nodes": self.topology.render_tree(),
        }

    # ------------------------------------------------------------------
    # 冻结控制（皮层 -> 任意层级节点）
    # ------------------------------------------------------------------

    def freeze_node(self, node_id: str, reason: str = "",
                    source: str = "cortex") -> Dict:
        """签发冻结：节点拒新任务接单、进程/心跳保活取证（隔离冻结态）。

        语义：不杀不死、可审计可解除、不触发清扫判 dead（心跳照常且标记
        frozen，皮层调度侧据此摘流量）。解除由 unfreeze_node（康复回树）
        或销毁重建（复核未通过，杜绝带病复用）。
        """
        node = self._require_node(node_id)
        url = self._node_url(node_id)
        if not url:
            return {"ok": False, "error": f"节点 {node_id} 未上报总线地址"}
        r = self.send_downlink(node_id, url, "cmd.freeze",
                               {"reason": reason, "source": source})
        self.audit(f"皮层签发冻结：{node_id} reason={reason or '隔离处置'} "
                   f"(ok={r.get('ok')})")
        self._note_perm_op("freeze", "node_id", node_id, perm=None,
                           results=[{"node": node_id, **r}])
        return {"ok": bool(r.get("ok")), "node": node_id,
                "frozen": bool(r.get("frozen")), "result": r}

    def unfreeze_node(self, node_id: str, reason: str = "",
                      source: str = "cortex") -> Dict:
        """解除冻结：复核通过后康复回树（接单面恢复）。"""
        node = self._require_node(node_id)
        url = self._node_url(node_id)
        if not url:
            return {"ok": False, "error": f"节点 {node_id} 未上报总线地址"}
        r = self.send_downlink(node_id, url, "cmd.unfreeze",
                               {"reason": reason, "source": source})
        self.audit(f"皮层解除冻结：{node_id} reason={reason or '复核通过'} "
                   f"(ok={r.get('ok')})")
        self._note_perm_op("unfreeze", "node_id", node_id, perm=None,
                           results=[{"node": node_id, **r}])
        return {"ok": bool(r.get("ok")), "node": node_id,
                "frozen": bool(r.get("frozen")), "result": r}

    # ------------------------------------------------------------------
    # 传票（subpoena）最高取证权限签发（level 0 专属，不可委派）
    # ------------------------------------------------------------------

    def _note_subpoena(self, rec: Dict) -> None:
        """签发即留痕：结构化记录（谁/何时/判据/范围/字节/容量档）。"""
        with self._subpoena_audit_lock:
            self._subpoena_audit.append(rec)
            if len(self._subpoena_audit) > 200:
                self._subpoena_audit = self._subpoena_audit[-200:]

    def subpoena_audit(self, n: int = 50) -> List[Dict]:
        """传票签发记录（含黑级事件标记），供最高权限审计。"""
        with self._subpoena_audit_lock:
            rows = list(self._subpoena_audit)
        rows.sort(key=lambda x: x.get("ts", 0), reverse=True)
        return rows[:max(1, int(n))]

    def subpoena(self, node_id: str, basis: str,
                 scope: str = "audit",
                 time_from: Optional[float] = None,
                 time_to: Optional[float] = None,
                 event: Optional[str] = None,
                 tier_kb: int = 64,
                 approved_by_human: bool = False,
                 summary_exhausted: bool = True,
                 actor: Optional[str] = None,
                 note: str = "") -> Dict:
        """签发传票：强制命令目标节点把原始审计（非 2KB 摘要）直传皮层。

        五道闸（防围栏反噬）：
          ① 判据前置：basis 必须是 SUBPOENA_BASIS 四类之一，且签发记录
             summary_exhausted（已穷尽摘要裁决：2KB → 按需片段 → 仍无法
             定谳）；
          ② 隔离帧：直传包 = RAW/UNTRUSTED 标记 + 一次性裁决实例（读取
             即焚 / TTL 过期自清）+ 不落长期记忆；
          ③ 取数通道：cmd.subpoena 下行指令（本方法）；
          ④ 容量分档：64/128/256/512KB；≤128KB level 0 自行批准；
             >128KB 需人工批准（approved_by_human=True）；超 512KB
             强制转人工终裁；
          ⑤ 签发即留痕：subpoena_audit() 全审计 + 「黑」级事件。

        Args:
            actor: 实际签发人身份（默认本皮层 node_id）。CLI/上层控制台
                   传真实操作者（如人工批准者），审计「谁签发的」才完整。

        低层级冒用：节点端校验签发者 level==0（不可委派），非 level 0
        拒绝并上行审计（subpoena.forged）。
        """
        # ① 判据前置
        if not protocol.is_valid_subpoena_basis(basis):
            return {"ok": False, "error":
                    f"invalid basis: {basis}（四类判据: "
                    f"{list(protocol.SUBPOENA_BASIS)}）"}
        if not summary_exhausted:
            return {"ok": False, "error":
                    "summary_exhausted=False：签发前须先穷尽摘要裁决 "
                    "（2KB → 按需片段 → 仍无法定谳）并记录判据"}
        # ④ 容量分档
        try:
            tier_kb = int(tier_kb)
        except (TypeError, ValueError):
            return {"ok": False, "error": f"invalid tier_kb: {tier_kb!r}"}
        if not protocol.is_valid_subpoena_tier(tier_kb):
            return {"ok": False, "error": f"invalid tier_kb: {tier_kb} "
                    f"（容量档 {list(protocol.SUBPOENA_TIERS_KB)}KB）"}
        if tier_kb > 128 and not approved_by_human:
            return {"ok": False, "error":
                    f"tier {tier_kb}KB > 128KB：需人工批准 "
                    "(approved_by_human=True)"}
        if tier_kb > protocol.SUBPOENA_MAX_KB:
            return {"ok": False, "error":
                    f"tier {tier_kb}KB > 512KB：强制转人工终裁（传票尽头是人）"}
        if scope not in ("audit", "reports", "both"):
            return {"ok": False, "error": f"invalid scope: {scope}"}
        # ⑤ 签发即留痕（先于取数，防最高权限滥用；黑级事件）
        rec = {
            "ts": time.time(),
            "actor": str(actor or self.node_id),
            "basis": basis,
            "scope": scope,
            "tier_kb": tier_kb,
            "approved_by_human": bool(approved_by_human),
            "summary_exhausted": bool(summary_exhausted),
            "node_id": node_id,
            "event": event,
            "note": note,
            "immunity": "black",
            "subpoena_id": __import__("uuid").uuid4().hex[:12],
        }
        self._note_subpoena(rec)
        self.audit(f"签发传票 subpoena_id={rec['subpoena_id']} -> {node_id} "
                   f"basis={basis} scope={scope} tier={tier_kb}KB "
                   f"approved={approved_by_human} [immunity:black]")
        # ② 取数通道：逐卷取完（512KB 档只流式分卷，不整喂）
        node = self._require_node(node_id)
        url = self._node_url(node_id)
        if not url:
            rec["error"] = "no url"
            return {"ok": False, "error": f"节点 {node_id} 未上报总线地址",
                    "subpoena_id": rec["subpoena_id"]}
        payload = {
            "basis": basis, "scope": scope, "tier_kb": tier_kb,
            "time_from": time_from, "time_to": time_to, "event": event,
            "vol": 0,
        }
        volumes: List[Dict] = []
        first = self.send_downlink(node_id, url, "cmd.subpoena", payload)
        if not first.get("ok"):
            rec["error"] = first.get("error", "subpoena rejected")
            return {"ok": bool(first.get("ok")), **first,
                    "subpoena_id": rec["subpoena_id"]}
        total_vols = int(first.get("total_vols", 1) or 1)
        volumes.append(first)
        for v in range(1, total_vols):
            payload["vol"] = v
            part = self.send_downlink(node_id, url, "cmd.subpoena", payload)
            if part.get("ok"):
                volumes.append(part)
            else:
                rec["error"] = f"vol {v} fetch failed: {part.get('error')}"
                break
        total_bytes = sum(int(v.get("total_bytes", 0)) for v in volumes)
        total_records = sum(len(v.get("records", [])) for v in volumes)
        # ② 隔离帧入箱（RAW/UNTRUSTED + TTL 一次性；正文不进长期记忆）
        envelope = {
            "subpoena_id": rec["subpoena_id"],
            "envelope": protocol.SUBPOENA_ENVELOPE,
            "node_id": node_id,
            "basis": basis,
            "scope": scope,
            "tier_kb": tier_kb,
            "approved_by_human": bool(approved_by_human),
            "fetched_at": time.time(),
            "ttl": self.subpoena_ttl,
            "volumes": volumes,
            "total_vols": total_vols,
            "total_bytes": total_bytes,
            "total_records": total_records,
            "truncated": bool(any(v.get("truncated") for v in volumes)),
            "note": note,
        }
        self._purge_expired_boxes()
        with self._subpoena_box_lock:
            self._subpoena_box[rec["subpoena_id"]] = envelope
        rec["total_bytes"] = total_bytes
        rec["total_records"] = total_records
        # 超 512KB 强制转人工终裁（隔离箱保留供人工复核，标记 human_adjudication）
        forced_human = total_bytes > protocol.SUBPOENA_MAX_KB * 1024
        rec["forced_human"] = forced_human
        if forced_human:
            envelope["human_adjudication"] = True
            self.audit(f"传票 {rec['subpoena_id']} 实际 {total_bytes}B 超 "
                       f"512KB：强制转人工终裁")
        return {
            "ok": True,
            "subpoena_id": rec["subpoena_id"],
            "envelope": protocol.SUBPOENA_ENVELOPE,  # RAW/UNTRUSTED
            "node_id": node_id,
            "basis": basis,
            "scope": scope,
            "tier_kb": tier_kb,
            "total_bytes": total_bytes,
            "total_records": total_records,
            "total_vols": total_vols,
            "truncated": envelope["truncated"],
            "forced_human": forced_human,
            "ttl": self.subpoena_ttl,
            "message": "证据已入隔离取证箱（RAW/UNTRUSTED，一次性裁决，"
                       "用后即毁；读取见 subpoena_box）",
        }

    def _purge_expired_boxes(self) -> int:
        """隔离箱 TTL 过期自清（惰性；读取/签发时触发）。"""
        now = time.time()
        expired = [k for k, v in self._subpoena_box.items()
                   if now - v.get("fetched_at", 0) > v.get("ttl", self.subpoena_ttl)]
        for k in expired:
            with self._subpoena_box_lock:
                self._subpoena_box.pop(k, None)
        if expired:
            self.audit(f"隔离取证箱过期自清 {len(expired)} 个传票包（用后即毁）")
        return len(expired)

    def subpoena_box(self, subpoena_id: Optional[str] = None,
                     destroy: bool = False) -> Dict:
        """读取隔离取证箱（一次性裁决实例）。

        destroy=True（默认读取即焚语义由调用方选择）：读取后销毁该包，
        保证用后即毁、裁决上下文不落长期记忆。返回 RAW/UNTRUSTED 隔离帧
        摘要 + 分卷（供流式裁决，不整喂 LLM）。
        """
        self._purge_expired_boxes()
        with self._subpoena_box_lock:
            if subpoena_id:
                env = self._subpoena_box.get(subpoena_id)
                if env is None:
                    return {"ok": False, "error":
                            f"subpoena {subpoena_id} not in box "
                            f"(expired or destroyed)"}
                if destroy:
                    self._subpoena_box.pop(subpoena_id, None)
                    self.audit(f"传票包 {subpoena_id} 读取即焚（用后即毁）")
                return {"ok": True, **env}
            ids = list(self._subpoena_box.keys())
            return {"ok": True, "in_box": ids,
                    "count": len(ids),
                    "envelope": protocol.SUBPOENA_ENVELOPE}

    def subpoena_purge(self, subpoena_id: Optional[str] = None) -> Dict:
        """销毁隔离取证箱内容（裁决完成后的用后即毁 / 强制清理）。"""
        with self._subpoena_box_lock:
            if subpoena_id:
                gone = self._subpoena_box.pop(subpoena_id, None) is not None
            else:
                gone = bool(self._subpoena_box)
                self._subpoena_box.clear()
        self.audit(f"隔离取证箱销毁：{subpoena_id or '全部'} "
                   f"({'已销毁' if gone else '无内容'})")
        return {"ok": True, "destroyed": gone}

    # ------------------------------------------------------------------
    # 行为基线分级视图（皮层消费节点心跳聚合统计）
    # ------------------------------------------------------------------

    def behavior_view(self) -> Dict:
        """全树行为基线分级：黄劣化（人工复核）/ 黑疑似恶意（隔离处置）。

        数据源：节点心跳上汇的 behavior 聚合统计（内核侧聚合，不上行
        原始流）。分级为皮层判定侧策略（阈值 behavior_thresholds 可调），
        统计口径与内核原始事件一致（心跳 reports 环内逐节点取最近一条）。
        """
        th = self.behavior_thresholds
        latest: Dict[str, Dict] = {}
        for r in self.get_reports():
            p = r.get("payload") or {}
            if r.get("type") != "report.heartbeat":
                continue
            node_id = r.get("from")
            if not node_id:
                continue
            prev = latest.get(node_id)
            if prev is None or r.get("ts", 0) >= prev.get("ts", 0):
                latest[node_id] = {
                    "ts": r.get("ts", 0), "status": p.get("status"),
                    "behavior": p.get("behavior") or {},
                    "frozen": bool(p.get("frozen")),
                }
        verdicts = []
        for node_id, info in sorted(latest.items()):
            bh = info.get("behavior") or {}
            ar = float(bh.get("audit_anomaly_rate", 0.0) or 0.0)
            fr = float(bh.get("task_fail_rate", 0.0) or 0.0)
            hr = float(bh.get("hb_fail_rate", 0.0) or 0.0)
            level = "ok"
            reasons = []
            if ar >= th["black_audit_anomaly_rate"]:
                level = "black"
                reasons.append(f"审计异常率 {ar:.1%} ≥ "
                               f"{th['black_audit_anomaly_rate']:.0%}（疑似恶意）")
            elif ar >= th["yellow_audit_anomaly_rate"]:
                level = "yellow"
                reasons.append(f"审计异常率 {ar:.1%} ≥ "
                               f"{th['yellow_audit_anomaly_rate']:.0%}（劣化）")
            if fr >= th["black_task_fail_rate"]:
                level = "black"
                reasons.append(f"任务失败率 {fr:.1%} ≥ "
                               f"{th['black_task_fail_rate']:.0%}（疑似恶意）")
            elif fr >= th["yellow_task_fail_rate"]:
                level = "yellow" if level == "ok" else level
                reasons.append(f"任务失败率 {fr:.1%} ≥ "
                               f"{th['yellow_task_fail_rate']:.0%}（劣化）")
            if hr >= th["yellow_hb_fail_rate"]:
                if level == "ok":
                    level = "yellow"
                reasons.append(f"心跳失败率 {hr:.1%} ≥ "
                               f"{th['yellow_hb_fail_rate']:.0%}")
            verdicts.append({
                "node_id": node_id,
                "level": level,
                "status": info.get("status"),
                "frozen": info.get("frozen", False),
                "behavior": bh,
                "reasons": reasons,
                "last_seen": info.get("ts"),
            })
        # 白盒：拓扑内已注册但尚无心跳上行的节点补 no-data 行——
        # 分级视图不静默缺行（注册后首跳心跳前的窗口也可见，不误导）。
        for n in list(self.topology.all()):
            nid = n.node_id
            if nid == self.node_id or nid in latest:
                continue
            verdicts.append({
                "node_id": nid,
                "level": "no-data",
                "status": None,
                "frozen": False,
                "behavior": {},
                "reasons": ["已注册但尚无心跳上报（首跳前窗口）"],
                "last_seen": None,
            })
        verdicts.sort(key=lambda v: v["node_id"])
        return {"ok": True, "count": len(verdicts), "verdicts": verdicts}

    # ------------------------------------------------------------------
    # 控制端点 /cnb/ctrl（CLI / REPL / 外部控制台）
    # ------------------------------------------------------------------

    def on_ctrl(self, req: Dict) -> Dict:
        """皮层控制端点处理。仅接受本机回环访问（bus 默认绑定 127.0.0.1）。"""
        op = req.get("op", "")
        try:
            if op == "topo":
                return self.topology_view()
            if op == "nodeinfo":
                node = self._require_node(req.get("node", ""))
                return {"ok": True, "node": node.to_dict()}
            if op == "ping":
                return self.ping(req.get("node", ""))
            if op == "exec":
                return self.exec_cmd(req.get("node", ""),
                                     req.get("action", ""),
                                     req.get("args"),
                                     req.get("perm", "process_exec"),
                                     req.get("path", ""))
            if op == "stop":
                return self.stop_node(req.get("node", ""))
            if op == "reload":
                return self.reload_node(req.get("node", ""))
            if op == "grant":
                return self.perm_grant(req.get("target_type", "*"),
                                       req.get("target", "*"),
                                       req.get("perm", ""),
                                       req.get("scope"))
            if op == "revoke":
                return self.perm_revoke(req.get("target_type", "*"),
                                        req.get("target", "*"),
                                        req.get("perm", ""))
            if op == "set":
                return self.perm_set(req.get("target_type", "*"),
                                     req.get("target", "*"),
                                     req.get("allows", {}))
            if op == "sync":
                return self.sync_topology()
            if op == "freeze":
                # 签发冻结（拒新任务、保活取证）
                return self.freeze_node(req.get("node", ""),
                                        req.get("reason", ""),
                                        req.get("source", "cortex"))
            if op == "unfreeze":
                # 解除冻结（康复回树）
                return self.unfreeze_node(req.get("node", ""),
                                          req.get("reason", ""),
                                          req.get("source", "cortex"))
            if op == "subpoena":
                # 签发传票（level 0 专属；五道闸在 subpoena() 把关）
                return self.subpoena(
                    req.get("node", ""),
                    req.get("basis", ""),
                    scope=req.get("scope", "audit"),
                    time_from=req.get("time_from"),
                    time_to=req.get("time_to"),
                    event=req.get("event"),
                    tier_kb=int(req.get("tier_kb", 64)),
                    approved_by_human=bool(req.get("approved_by_human")),
                    summary_exhausted=bool(req.get("summary_exhausted", True)),
                    actor=req.get("actor") or None,
                    note=req.get("note", ""),
                )
            if op == "subpoena_box":
                # 读取隔离取证箱（destroy=True 读取即焚）
                return self.subpoena_box(req.get("subpoena_id"),
                                         destroy=bool(req.get("destroy")))
            if op == "subpoena_purge":
                # 销毁隔离取证箱（裁决完成用后即毁）
                return self.subpoena_purge(req.get("subpoena_id"))
            if op == "subpoena_audit":
                # 传票签发记录（谁/何时/判据/范围/字节，黑级事件）
                n = int(req.get("n", 50))
                return {"ok": True,
                        "audit": self.subpoena_audit(n)}
            if op == "behavior":
                # 行为基线分级视图（黄劣化/黑疑似恶意）
                return self.behavior_view()
            if op == "config":
                # 皮层只读配置（控制台展示：清扫参数 + 行为分级阈值 + 身份）
                return {
                    "ok": True,
                    "node_id": self.node_id,
                    "kind": self.kind,
                    "host": self.host,
                    "port": self.port,
                    "proto": protocol.PROTO_VERSION,
                    "started_at": self._started_at,
                    "uptime": round(time.time() - self._started_at, 1),
                    "topology_size": self.topology.size(),
                    "sweep": {
                        "sweep_interval": self.sweep_interval,
                        "dead_timeout": self.dead_timeout,
                        "drop_grace": self.drop_grace,
                    },
                    "behavior_thresholds": dict(self.behavior_thresholds),
                }
            if op == "set_thresholds":
                # 皮层运行参数热调整（控制台真实操作；键白名单 + 范围校验 +
                # 审计留痕）。thresholds=行为分级阈值（0~1 比率）；
                # sweep=清扫参数（秒，>0）。
                th = req.get("thresholds") or {}
                sweep = req.get("sweep") or {}
                if not isinstance(th, dict) or not isinstance(sweep, dict):
                    raise ValueError("thresholds/sweep 必须为对象")
                allowed_th = {
                    "yellow_audit_anomaly_rate", "black_audit_anomaly_rate",
                    "yellow_task_fail_rate", "black_task_fail_rate",
                    "yellow_hb_fail_rate",
                }
                allowed_sweep = {"dead_timeout", "drop_grace", "sweep_interval"}
                changed = []
                for key, val in th.items():
                    if key not in allowed_th:
                        raise ValueError(f"未知行为阈值键: {key}")
                    try:
                        val = float(val)
                    except (TypeError, ValueError) as exc:
                        raise ValueError(f"非法阈值 {key}={val!r}") from exc
                    if not (0.0 <= val <= 1.0):
                        raise ValueError(f"阈值必须在 0~1 之间: {key}={val}")
                    self.behavior_thresholds[key] = val
                    changed.append(f"thresholds.{key}={val}")
                for key, val in sweep.items():
                    if key not in allowed_sweep:
                        raise ValueError(f"未知清扫参数键: {key}")
                    try:
                        val = float(val)
                    except (TypeError, ValueError) as exc:
                        raise ValueError(f"非法清扫参数 {key}={val!r}") from exc
                    if val <= 0:
                        raise ValueError(f"清扫参数必须为正数: {key}={val}")
                    setattr(self, key, val)
                    changed.append(f"sweep.{key}={val}")
                if not changed:
                    raise ValueError("无可变更键（白名单内未提供任何值）")
                self.audit(
                    "皮层运行参数更新（ctrl set_thresholds）",
                    changed=", ".join(changed),
                )
                return {
                    "ok": True,
                    "changed": changed,
                    "sweep": {
                        "sweep_interval": self.sweep_interval,
                        "dead_timeout": self.dead_timeout,
                        "drop_grace": self.drop_grace,
                    },
                    "behavior_thresholds": dict(self.behavior_thresholds),
                }
            if op == "sweep":
                """手动触发一次失联清扫 + 救树（运维/测试用）。"""
                self._sweep_once()
                self.audit(f"手动触发失联清扫完成（当前拓扑 "
                           f"{self.topology.size()} 节点）")
                return {"ok": True, "size": self.topology.size()}
            if op == "reports":
                n = int(req.get("n", 20))
                return {"ok": True, "reports": self.get_reports()[-n:]}
            if op == "audit":
                n = int(req.get("n", 20))
                return {"ok": True, "audit": self.get_audit()[-n:]}
            if op == "perm_audit":
                n = int(req.get("n", 50))
                return {"ok": True, "audit": self.perm_audit(n)}
            return {"ok": False, "error": f"未知控制操作: {op}"}
        except ValueError as e:
            return {"ok": False, "error": str(e)}
        except Exception as e:
            return {"ok": False, "error": f"{type(e).__name__}: {e}"}

    # ------------------------------------------------------------------
    # REPL 交互控制台
    # ------------------------------------------------------------------

    def repl(self):
        """交互式皮层控制台。"""
        import sys
        print("=" * 60)
        print(f"大脑皮层控制台 — {self.node_id} (level {self.level})")
        print(f"总线端点: {self.base_url}  输入 help 查看命令")
        print("=" * 60)
        while True:
            try:
                line = input("cortex> ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\n皮层控制台退出")
                break
            if not line:
                continue
            parts = line.split()
            cmd = parts[0].lower()
            args = parts[1:]
            try:
                if cmd in ("quit", "exit", "q"):
                    print("皮层控制台退出")
                    break
                elif cmd == "help" or cmd == "?":
                    self._repl_help()
                elif cmd == "topo":
                    print(self.topology.render_ascii())
                    print(f"(共 {self.topology.size()} 个节点)")
                elif cmd == "ping":
                    print(json.dumps(self.ping(args[0]), ensure_ascii=False, indent=2))
                elif cmd == "exec":
                    if len(args) < 2:
                        print("用法: exec <node_id> <action> [perm]")
                        continue
                    perm = args[2] if len(args) > 2 else "process_exec"
                    print(json.dumps(self.exec_cmd(args[0], args[1], perm=perm),
                                     ensure_ascii=False, indent=2))
                elif cmd == "stop":
                    print(json.dumps(self.stop_node(args[0]), ensure_ascii=False, indent=2))
                elif cmd == "reload":
                    print(json.dumps(self.reload_node(args[0]), ensure_ascii=False, indent=2))
                elif cmd == "grant":
                    if len(args) < 3:
                        print("用法: grant <node_id|node_kind|*> <target> <perm>")
                        continue
                    print(json.dumps(self.perm_grant(args[0], args[1], args[2]),
                                     ensure_ascii=False, indent=2))
                elif cmd == "revoke":
                    if len(args) < 3:
                        print("用法: revoke <node_id|node_kind|*> <target> <perm>")
                        continue
                    print(json.dumps(self.perm_revoke(args[0], args[1], args[2]),
                                     ensure_ascii=False, indent=2))
                elif cmd == "set":
                    if len(args) < 3:
                        print("用法: set <node_id|node_kind|*> <target> <json>")
                        continue
                    allows = json.loads(args[2])
                    print(json.dumps(self.perm_set(args[0], args[1], allows),
                                     ensure_ascii=False, indent=2))
                elif cmd == "sync":
                    print(json.dumps(self.sync_topology(), ensure_ascii=False, indent=2))
                elif cmd == "freeze":
                    # freeze <node_id> [reason]
                    reason = " ".join(args[1:]) if len(args) > 1 else ""
                    print(json.dumps(self.freeze_node(args[0], reason),
                                     ensure_ascii=False, indent=2))
                elif cmd == "unfreeze":
                    # unfreeze <node_id> [reason]
                    reason = " ".join(args[1:]) if len(args) > 1 else ""
                    print(json.dumps(self.unfreeze_node(args[0], reason),
                                     ensure_ascii=False, indent=2))
                elif cmd == "subpoena":
                    # subpoena <node_id> <basis> [tier_kb] [approved]
                    # basis: confidence_low / vote_tie / evidence_conflict / human_named
                    if len(args) < 2:
                        print("用法: subpoena <node_id> <basis> [tier_kb] "
                              "[approved]  (basis: confidence_low/vote_tie/"
                              "evidence_conflict/human_named)")
                        continue
                    tier = int(args[2]) if len(args) > 2 else 64
                    approved = args[3].lower() in ("1", "true", "yes") \
                        if len(args) > 3 else False
                    print(json.dumps(
                        self.subpoena(args[0], args[1], tier_kb=tier,
                                      approved_by_human=approved),
                        ensure_ascii=False, indent=2))
                elif cmd == "box":
                    # box [subpoena_id] 查看隔离取证箱（不销毁）
                    sid = args[0] if args else None
                    print(json.dumps(self.subpoena_box(sid, destroy=False),
                                     ensure_ascii=False, indent=2))
                elif cmd == "box_read":
                    # box_read <subpoena_id> 读取即焚（用后即毁）
                    print(json.dumps(self.subpoena_box(args[0], destroy=True),
                                     ensure_ascii=False, indent=2)[:2000])
                elif cmd == "box_purge":
                    # box_purge [subpoena_id] 销毁取证包
                    sid = args[0] if args else None
                    print(json.dumps(self.subpoena_purge(sid),
                                     ensure_ascii=False, indent=2))
                elif cmd == "subpoena_audit":
                    # 签发记录（黑级事件）
                    n = int(args[0]) if args else 20
                    for a in self.subpoena_audit(n):
                        print(f"[{time.strftime('%H:%M:%S', time.localtime(a['ts']))}] "
                              f"{a.get('actor')} -> {a.get('node_id')} "
                              f"basis={a.get('basis')} tier={a.get('tier_kb')}KB "
                              f"bytes={a.get('total_bytes', '?')} "
                              f"[immunity:{a.get('immunity')}]")
                elif cmd == "behavior":
                    # 行为基线分级视图（黄劣化/黑疑似恶意）
                    r = self.behavior_view()
                    print(f"行为基线分级（{r.get('count')} 个节点）：")
                    for v in r.get("verdicts", []):
                        marks = {"ok": "[OK]", "yellow": "[黄·复核]",
                                 "black": "[黑·隔离]"}
                        print(f"  {marks.get(v['level'], v['level'])} "
                              f"{v['node_id']} status={v.get('status')} "
                              f"frozen={v.get('frozen')} "
                              f"audit_anomaly={v.get('behavior', {}).get('audit_anomaly_rate')} "
                              f"task_fail={v.get('behavior', {}).get('task_fail_rate')} "
                              f"hb_fail={v.get('behavior', {}).get('hb_fail_rate')}")
                        for reason in v.get("reasons", []):
                            print(f"       - {reason}")
                elif cmd == "sweep":
                    self._sweep_once()
                    print(self.topology.render_ascii())
                    print(f"(清扫完成，共 {self.topology.size()} 个节点)")
                elif cmd == "reports":
                    n = int(args[0]) if args else 20
                    for r in self.get_reports()[-n:]:
                        p = r.get("payload") or {}
                        extra = f" status={p.get('status')}" if p.get("status") else ""
                        print(f"[{time.strftime('%H:%M:%S', time.localtime(r['ts']))}] "
                              f"{r.get('from')} -> {r.get('type')}  "
                              f"{r.get('note')}{extra}")
                elif cmd == "audit":
                    n = int(args[0]) if args else 20
                    for a in self.get_audit()[-n:]:
                        print(f"[{time.strftime('%H:%M:%S', time.localtime(a['ts']))}] {a.get('msg')}")
                elif cmd == "perm_audit":
                    n = int(args[0]) if args else 50
                    for a in self.perm_audit(n):
                        print(f"[{time.strftime('%H:%M:%S', time.localtime(a['ts']))}] "
                              f"{a.get('from')} {a.get('event')}  {a.get('detail', '')[:200]}")
                else:
                    print(f"未知命令: {cmd}（输入 help 查看帮助）")
            except IndexError:
                print("参数不足（输入 help 查看用法）")
            except Exception as e:
                print(f"错误: {e}")

    def _repl_help(self):
        print("""命令：
  topo                         查看拓扑树
  ping <node_id>               探活指定节点
  exec <node_id> <action> [perm]   下发执行指令
  stop <node_id>               停止节点任务
  reload <node_id>             重载节点配置
  grant <type> <target> <perm> 授予权限（type: node_id / node_kind / *）
  revoke <type> <target> <perm> 撤销权限
  set <type> <target> <json>   整体覆盖权限，如: set node_kind bot '{"process_shell": false}'
  freeze <node_id> [reason]    签发冻结（拒新任务、保活取证）
  unfreeze <node_id> [reason]  解除冻结（复核后康复回树）
  subpoena <node_id> <basis> [tier_kb] [approved]
                               签发传票（level 0 专属）
                               basis: confidence_low/vote_tie/
                               evidence_conflict/human_named
                               tier_kb: 64/128/256/512（>128 需 approved）
  box [subpoena_id]            查看隔离取证箱（RAW/UNTRUSTED，不销毁）
  box_read <subpoena_id>       读取取证包（读取即焚，用后即毁）
  box_purge [subpoena_id]      销毁取证包
  subpoena_audit [n]           传票签发记录（黑级事件）
  behavior                     行为基线分级（黄劣化/黑疑似恶意）
  sync                         向全部后代广播拓扑
  sweep                        手动执行一次失联清扫 + 救树
  reports [n]                  查看最近上报
  audit [n]                    查看皮层审计
  perm_audit [n]               查看权限面审计（皮层权限操作 + 节点上行
                               perm.denied / perm.changed 汇聚）
  help / quit                  帮助 / 退出""")
