# -*- coding: utf-8 -*-
"""
norpagent.cnb.node — CNB 节点（每个 norpagent 实例内置一个）

节点是神经树上的一个单位原子（norpbot / norpilot / norpmemory ... 或
任意自定义实例），职责：

1. 上行（只读上报）：向父节点（最终汇聚到大脑皮层）上报
   - report.register / report.deregister（注册 / 注销，沿树逐级转发）
   - report.heartbeat（心跳与状态）
   - report.event（事件）
   - report.audit（审计）
   - report.request（请求，是否批准由高等级决定）

2. 下行（无条件服从）：接收祖先节点下发的指令并执行
   - cmd.hello / cmd.ping / cmd.exec / cmd.stop / cmd.reload
   - cmd.perm.set / grant / revoke（大脑皮层控制本节点操作权限）
   - cmd.topology.sync（皮层广播拓扑）

铁律（代码强制）：
- 上行消息若携带控制字段，传输层直接拒绝（低等级永远无法控制上层）。
- 下行指令只接受祖先节点；非祖先发来的指令一律拒绝并记审计。
- 节点不允许改写父节点（无任何上行通道可携带控制字段）。
"""

import json
import sys
import threading
import time
from typing import Any, Callable, Dict, List, Optional

from . import protocol
from .bus import BusClient, start_bus
from .permissions import NeuralPermissionTable
from .topology import Topology

# 心跳默认间隔（秒）
DEFAULT_HEARTBEAT_INTERVAL = 5.0


class NervousNode:
    """中枢神经总线节点。"""

    def __init__(self, node_id: str, kind: str = "node", level: int = protocol.LEVEL_ATOM,
                 parent_url: Optional[str] = None,
                 host: str = protocol.DEFAULT_HOST,
                 port: int = protocol.DEFAULT_CORTEX_PORT + 1,
                 meta: Optional[Dict] = None,
                 heartbeat_interval: float = DEFAULT_HEARTBEAT_INTERVAL):
        self.node_id = node_id
        self.kind = kind
        self.level = int(level)
        self.parent_url = parent_url          # 父节点总线地址（None = 根/皮层）
        self.parent_node_id: Optional[str] = None  # 父节点 id（收到 cmd.hello 后确认）
        self.host = host
        self.port = int(port)
        self.meta = dict(meta or {})
        self.base_url = f"http://{host}:{port}"
        # 把自己的总线地址放进 meta，随注册上报，皮层据此定位任意节点
        self.meta.setdefault("base_url", self.base_url)
        self.heartbeat_interval = heartbeat_interval

        # 本地拓扑：自己 + 已注册的后代（皮层为根时 = 全量拓扑）
        self.topology = Topology()
        self.topology.register(node_id, self.level, kind,
                               parent_id=None, meta=self.meta)

        # 祖先链（父、祖父、...，由近及远）：注册确认时由父节点告知。
        # 本地拓扑只含子树视图，深层节点据此判定任意祖先的下行合法性。
        self._ancestors: List[str] = []

        # 神经权限表：皮层下发的权限指令落地于此
        self.permissions = NeuralPermissionTable(node_id, kind)

        # 回调钩子（与 norpagent 本体集成点）
        self._callbacks: Dict[str, Callable] = {}

        # 内核动作注册表（v1.0.7 内核集成）：皮层 cmd.exec 的 action 优先路由
        # 到注册处理器（handler(payload: dict) -> dict），未注册动作回退到旧
        # 回调钩子（fire "exec"），两者皆无才拒绝。引擎绑定层（norpagent.cnb.
        # engine.CnbAdapter）把 NorpEngine 公开 API 注册为内核动作面。
        self._actions: Dict[str, Callable[[Dict], Dict]] = {}

        # 心跳状态提供者（v1.0.7）：provider() -> (status: str, extra: dict)
        # 或 None。引擎绑定层注入后，心跳自动携带内核状态（engine_state /
        # active_tasks 等），皮层汇聚可见。
        self._heartbeat_provider: Optional[Callable[[], Any]] = None
        # provider 健康翻转标记（白盒：故障/恢复各审计一次，防刷屏）
        self._provider_failed = False
        # 节流审计表（msg 前缀 -> 上次审计时间）：高频故障只记首条与恢复
        self._throttle_audit: Dict[str, float] = {}
        self._throttle_audit_lock = threading.Lock()

        # 上报记录（最近 500 条）
        self._reports: List[Dict] = []
        self._reports_lock = threading.RLock()

        # 审计日志（最近 500 条）
        self._audit: List[Dict] = []
        self._audit_lock = threading.RLock()

        # ── 隔离冻结态（quarantine）──
        # 冻结 = 拒新任务（接单面关闭）+ 进程/心跳存活（取证面保全）+ 可审计
        # 可解除 + 不触发清扫判 dead（冻结节点心跳照常，清扫只看心跳时效）。
        # 冻结位在皮层下发 cmd.freeze 后置位；解除由 cmd.unfreeze（康复回树）
        # 或节点销毁重建（杜绝带病复用）。冻结期间的 exec 动作按
        # protocol.FROZEN_ALLOWED_ACTIONS 白名单放行（只读取证面）。
        self._frozen = False
        self._frozen_reason = ""
        self._frozen_at: Optional[float] = None
        self._frozen_by = ""

        # ── 行为基线聚合（内核侧统计，随心跳压缩上汇）──
        # 机械行为基线：心跳缺失率 / 审计异常率 / 任务失败率。节点本地累计
        # 统计，心跳上报自动携带聚合字段（不上行原始流，压缩上汇量）；
        # 皮层按阈值分级（黄劣化 / 黑疑似恶意）。
        self._behavior = {
            "hb_sent": 0,      # 心跳发送次数
            "hb_ok": 0,        # 心跳被父节点接受次数
            "hb_fail": 0,      # 心跳失败次数（网络/被拒）
            "audit_total": 0,  # 本地审计记录总数
            "audit_anomaly": 0,  # 其中异常类审计数（error/denied/reject/失败）
            "task_total": 0,   # 本地任务完成总数（引擎绑定层上报）
            "task_ok": 0,      # 成功任务数
            "task_fail": 0,    # 失败任务数
        }
        self._behavior_lock = threading.RLock()

        # 总线
        self._bus = None
        self._client = BusClient(timeout=8.0)
        self._running = False
        self._heartbeat_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._started_at = time.time()

    # ------------------------------------------------------------------
    # 生命周期
    # ------------------------------------------------------------------

    def start(self) -> "NervousNode":
        """启动总线服务；若有父节点则注册并开启心跳。"""
        ctx = {
            "node_id": self.node_id,
            "kind": self.kind,
            "level": self.level,
            "on_message": self.on_message,
            "on_reports": self.get_reports,
            "on_audit": self.audit,  # 总线层拒绝/异常留痕（白盒）
        }
        self._bus = start_bus(self.host, self.port, ctx)
        self._running = True
        self._started_at = time.time()
        if self.parent_url:
            self.register()
            self._heartbeat_thread = threading.Thread(
                target=self._heartbeat_loop, daemon=True,
                name=f"cnb-heartbeat-{self.node_id}")
            self._heartbeat_thread.start()
        return self

    def stop(self):
        """停止节点：注销、停心跳、关总线。

        白盒约束：注销/关总线失败不静默——stderr 提示（进程即将退出，
        本地审计无读者；皮层侧由心跳超时清扫兜底收敛）。
        """
        self._running = False
        self._stop_event.set()
        if self.parent_url:
            try:
                r = self.deregister()
                if not r.get("ok"):
                    print(f"[cnb] {self.node_id} 注销失败（皮层将按失联清扫"
                          f"收敛）: {r.get('error')}", file=sys.stderr)
            except Exception as e:  # noqa: BLE001
                print(f"[cnb] {self.node_id} 注销异常: {e}", file=sys.stderr)
        if self._bus is not None:
            try:
                self._bus.shutdown()
                self._bus.server_close()
            except Exception as e:  # noqa: BLE001
                print(f"[cnb] {self.node_id} 总线关闭异常: {e}", file=sys.stderr)

    def _heartbeat_once(self) -> Dict:
        """执行一次心跳上报；若注册了心跳状态提供者，携带内核深度状态。

        白盒约束：provider 故障绝不静默——故障期间心跳状态降级为
        degraded 并携带 provider_error 字段（皮层汇聚可见，可区分
        「引擎无状态」与「状态源故障」）；故障发生与恢复各审计一次
        （状态翻转审计，避免每周期刷屏淹没审计环）。
        """
        extra: Dict[str, Any] = {}
        status = "running"
        provider = self._heartbeat_provider
        if provider is not None:
            try:
                info = provider()
                if isinstance(info, (tuple, list)) and len(info) >= 2:
                    status = str(info[0] or "running")
                    extra = dict(info[1] or {})
                self._note_provider_health(ok=True)
            except Exception as e:  # noqa: BLE001 — provider 故障降级上报而非静默
                self._note_provider_health(ok=False, error=e)
                status = "degraded"
                extra["provider_error"] = f"{type(e).__name__}: {e}"[:200]
        # 冻结节点心跳强制标记（皮层调度侧据此摘流量），
        # 心跳照常发送——冻结不得被误判为 dead（与清扫线程语义互斥）。
        if self._frozen:
            status = "frozen"
            extra["frozen"] = True
            extra["frozen_reason"] = self._frozen_reason
            extra["frozen_at"] = self._frozen_at
            extra["frozen_by"] = self._frozen_by
        # 行为基线聚合字段随心跳上汇（压缩上汇量，皮层分级）。
        with self._behavior_lock:
            bh = dict(self._behavior)
        extra.setdefault("behavior", {
            "hb_sent": bh["hb_sent"],
            "hb_ok": bh["hb_ok"],
            "hb_fail": bh["hb_fail"],
            "audit_total": bh["audit_total"],
            "audit_anomaly": bh["audit_anomaly"],
            "audit_anomaly_rate": round(
                bh["audit_anomaly"] / bh["audit_total"], 4)
                if bh["audit_total"] else 0.0,
            "task_total": bh["task_total"],
            "task_ok": bh["task_ok"],
            "task_fail": bh["task_fail"],
            "task_fail_rate": round(
                bh["task_fail"] / bh["task_total"], 4)
                if bh["task_total"] else 0.0,
        })
        return self.report_heartbeat(status, **extra)

    def _note_provider_health(self, ok: bool, error: BaseException = None):
        """心跳状态提供者健康翻转审计（首次故障 + 恢复各记一次，防刷屏）。

        故障连续周期不再重复审计（_provider_failed 为 True 时静默），
        恢复时审计一次并清标记。保证取证链上 provider 故障有据可查。
        """
        if ok:
            if self._provider_failed:
                self._provider_failed = False
                self.audit("心跳状态提供者已恢复")
            return
        if not self._provider_failed:
            self._provider_failed = True
            self.audit(f"心跳状态提供者故障（心跳降级 degraded 并上汇 "
                       f"provider_error）: {type(error).__name__}: {error}",
                       provider_error=str(error)[:200])

    def _heartbeat_loop(self):
        while self._running and not self._stop_event.is_set():
            try:
                r = self._heartbeat_once()
                # 自愈：父节点已把本节点遗忘（如皮层救树/清扫后的拓扑变化）
                # -> 心跳被拒 -> 主动重新注册，重新锚定到父节点。
                # 典型场景：父节点同 id 重启 / 皮层 rescue 后视图重建。
                if not r.get("ok") and "not my descendant" in str(r.get("error", "")):
                    self.audit("心跳被父节点拒绝（本节点已不在其拓扑），自动重新注册")
                    try:
                        self.register()
                    except Exception:
                        pass
            except Exception as e:  # noqa: BLE001 — 循环异常节流审计，不静默
                self._audit_throttled("心跳循环异常", f"{type(e).__name__}: {e}")
            self._stop_event.wait(self.heartbeat_interval)

    # ------------------------------------------------------------------
    # 回调注册（norpagent 本体集成点）
    # ------------------------------------------------------------------

    def on(self, event: str, cb: Callable):
        """注册回调。事件：exec / stop / reload / perm_changed / registered。

        - exec(payload: dict) -> dict   执行通用指令，返回值作为回执 detail
        - stop()                         停止本地任务
        - reload()                       重载配置
        - perm_changed(rule: dict)       权限表被皮层修改
        - registered(parent_id: str)     注册被父节点确认
        """
        self._callbacks[event] = cb
        return self

    def _fire(self, event: str, *args, **kwargs):
        cb = self._callbacks.get(event)
        if cb is None:
            return None
        try:
            return cb(*args, **kwargs)
        except Exception as e:
            self.audit(f"callback {event} error: {e}")
            return {"error": str(e)}

    # ------------------------------------------------------------------
    # 内核动作注册表（v1.0.7 内核集成）
    # ------------------------------------------------------------------

    def register_action(self, action: str, handler: Callable) -> "NervousNode":
        """注册内核动作处理器：皮层 cmd.exec action=<action> 时被调用。

        handler 签名：handler(payload: dict) -> dict（返回回执 detail）。

        动作注册表优先于旧回调钩子（on("exec")）：_exec_downlink 收到
        cmd.exec 时先查动作表，未命中再回退 fire("exec")，两者皆无则拒绝。
        引擎绑定层（norpagent.cnb.engine.CnbAdapter）把 NorpEngine 公开 API
        注册为内核动作面；纯神经 CLI（--bare）可注册自己的占位动作。
        """
        if not action or not isinstance(action, str):
            raise ValueError("action name must be a non-empty string")
        if not callable(handler):
            raise ValueError(f"handler for {action!r} must be callable")
        self._actions[action] = handler
        return self

    def unregister_action(self, action: str) -> bool:
        """移除动作处理器（不存在返回 False）。"""
        return self._actions.pop(action, None) is not None

    def has_action(self, action: str) -> bool:
        return action in self._actions

    def list_actions(self) -> List[str]:
        """当前注册的内核动作名（皮层可见该原子可执行的动作面）。"""
        return sorted(self._actions)

    def set_heartbeat_provider(self, provider: Optional[Callable]) -> "NervousNode":
        """设置心跳状态提供者：provider() -> (status: str, extra: dict) 或 None。

        引擎绑定层注入后，心跳自动携带内核深度状态（engine_state /
        active_tasks / 版本号等），经父链逐级汇聚到皮层。
        """
        if provider is not None and not callable(provider):
            raise ValueError("heartbeat provider must be callable or None")
        self._heartbeat_provider = provider
        return self

    # ------------------------------------------------------------------
    # 审计与上报记录
    # ------------------------------------------------------------------

    def audit(self, msg: str, **extra):
        rec = {"ts": time.time(), "msg": msg, **extra}
        with self._audit_lock:
            self._audit.append(rec)
            if len(self._audit) > 500:
                self._audit = self._audit[-500:]
        # 异常类审计计数（行为基线审计异常率的分母/分子）
        anomaly = False
        if extra.get("error"):
            anomaly = True
        else:
            low = str(msg).lower()
            if any(k in low for k in ("error", "denied", "reject",
                                      "fail", "异常", "失败", "拒绝")):
                anomaly = True
        if anomaly:
            with self._behavior_lock:
                self._behavior["audit_anomaly"] += 1
        with self._behavior_lock:
            self._behavior["audit_total"] += 1
        return rec

    def _audit_throttled(self, msg: str, detail: str = "",
                         window: float = 60.0, **extra):
        """节流审计：同类消息窗口期内只记首条（防高频故障刷爆审计环）。

        用于心跳循环异常、上行投递失败等可能连续发生的故障路径——
        保证取证链上有据可查，又不淹没 500 条审计环。
        """
        key = str(msg)[:60]
        now = time.time()
        with self._throttle_audit_lock:
            last = self._throttle_audit.get(key, 0.0)
            if now - last < window:
                return False
            self._throttle_audit[key] = now
        self.audit(msg + (f": {detail}" if detail else ""), **extra)
        return True

    def get_audit(self) -> List[Dict]:
        with self._audit_lock:
            return list(self._audit)

    # ------------------------------------------------------------------
    # 隔离冻结态（freeze / unfreeze）
    # ------------------------------------------------------------------

    def is_frozen(self) -> bool:
        return bool(self._frozen)

    def freeze(self, reason: str = "", source: str = "cortex") -> Dict:
        """冻结本节点：拒新任务接单、进程/心跳保活（取证面保全）。

        由皮层 cmd.freeze 下行触发（_handle_downlink 祖先校验通过后执行），
        也可由引擎绑定层/上层应用直接调用。冻结期间：
          - exec 只放行 FROZEN_ALLOWED_ACTIONS（只读取证面），run_task /
            stop_engine / rollback 等变更性动作一律拒绝并审计；
          - 心跳照常发送且标记 frozen（皮层调度摘流量；不触发清扫判 dead）；
          - 本地审计与上报记录保持可读（subpoena 取证通道不受影响）。
        """
        if self._frozen:
            return {"ok": True, "frozen": True, "already": True}
        self._frozen = True
        self._frozen_reason = str(reason or "")
        self._frozen_at = time.time()
        self._frozen_by = str(source or "")
        self.audit(f"节点冻结：{reason or '隔离处置'} (source={source})",
                   frozen=True, reason=reason)
        self._perm_uplink_audit("freeze", "node_id", self.node_id,
                                source=source)
        return {"ok": True, "frozen": True, "reason": reason,
                "source": source, "at": self._frozen_at}

    def unfreeze(self, reason: str = "", source: str = "cortex") -> Dict:
        """解除冻结：复核通过后康复回树（接单面恢复）。

        由皮层 cmd.unfreeze 下行触发；解除后心跳恢复普通状态字。
        杜绝带病复用由皮层处置把关（复核未通过应销毁重建而非解冻）。
        """
        if not self._frozen:
            return {"ok": True, "frozen": False, "already": True}
        self._frozen = False
        self._frozen_reason = ""
        self._frozen_at = None
        self._frozen_by = ""
        self.audit(f"解除冻结：{reason or '复核通过，康复回树'} "
                   f"(source={source})", frozen=False, reason=reason)
        self._perm_uplink_audit("unfreeze", "node_id", self.node_id,
                                source=source)
        return {"ok": True, "frozen": False, "reason": reason,
                "source": source}

    # ------------------------------------------------------------------
    # 行为基线统计（任务结果计数，引擎绑定层 watcher 调用）
    # ------------------------------------------------------------------

    def note_task_result(self, ok: bool) -> "NervousNode":
        """记录一次任务完成结果（成功/失败），计入行为基线任务失败率。"""
        with self._behavior_lock:
            self._behavior["task_total"] += 1
            if ok:
                self._behavior["task_ok"] += 1
            else:
                self._behavior["task_fail"] += 1
        return self

    def behavior_summary(self) -> Dict:
        """当前行为基线统计摘要（皮层分级消费）。"""
        with self._behavior_lock:
            bh = dict(self._behavior)
        return {
            "node_id": self.node_id,
            "hb_sent": bh["hb_sent"],
            "hb_ok": bh["hb_ok"],
            "hb_fail": bh["hb_fail"],
            "hb_fail_rate": round(bh["hb_fail"] / bh["hb_sent"], 4)
            if bh["hb_sent"] else 0.0,
            "audit_total": bh["audit_total"],
            "audit_anomaly": bh["audit_anomaly"],
            "audit_anomaly_rate": round(
                bh["audit_anomaly"] / bh["audit_total"], 4)
            if bh["audit_total"] else 0.0,
            "task_total": bh["task_total"],
            "task_ok": bh["task_ok"],
            "task_fail": bh["task_fail"],
            "task_fail_rate": round(bh["task_fail"] / bh["task_total"], 4)
            if bh["task_total"] else 0.0,
            "frozen": self._frozen,
            "frozen_reason": self._frozen_reason,
        }

    # ------------------------------------------------------------------
    # 传票取证（subpoena）：原始审计直传（隔离帧 RAW/UNTRUSTED）
    # ------------------------------------------------------------------

    def collect_evidence(self, scope: str = "audit",
                         time_from: Optional[float] = None,
                         time_to: Optional[float] = None,
                         event: Optional[str] = None,
                         max_bytes: int = 64 * 1024,
                         vol: int = 0) -> Dict:
        """按传票范围收集本地原始审计/上报记录（原样 JSON，非 2KB 摘要）。

        Args:
            scope: audit（本地操作审计）/ reports（收到的上行上报）/
                   both（两者合并，按 ts 排序）。
            time_from/time_to: 时间窗（epoch 秒）；None = 不限。
            event: 事件类型过滤（report.audit 的 event / 上行 type 子串匹配，
                   大小写不敏感）；None = 不限。
            max_bytes: 单卷字节预算（容量档；默认 64KB）。
            vol: 取第几卷（0 起）。超预算自动分卷，应答带 total_vols 供
                 皮层逐卷取完（512KB 档只流式分卷裁决，不整喂）。

        Returns:
            隔离帧应答：{ok, subpoena: RAW/UNTRUSTED, scope, total_records,
            total_bytes, vol, total_vols, records, truncated}。
        """
        def _in_window(ts: float) -> bool:
            if time_from is not None and ts < time_from:
                return False
            if time_to is not None and ts > time_to:
                return False
            return True

        def _match_event(rec: Dict) -> bool:
            if not event:
                return True
            ev = ""
            if rec.get("type") == "report.audit":
                ev = str((rec.get("payload") or {}).get("event", ""))
            elif rec.get("type"):
                ev = str(rec.get("type"))
            else:
                ev = str(rec.get("msg", ""))
            return event.lower() in ev.lower()

        rows: List[Dict] = []
        if scope in ("audit", "both"):
            with self._audit_lock:
                for rec in self._audit:
                    if _in_window(rec.get("ts", 0)) and _match_event(rec):
                        rows.append(rec)
        if scope in ("reports", "both"):
            with self._reports_lock:
                for rec in self._reports:
                    if _in_window(rec.get("ts", 0)) and _match_event(rec):
                        rows.append(rec)
        rows.sort(key=lambda r: r.get("ts", 0))
        # 原样 JSON 序列化（原始审计，非摘要），按字节预算分卷
        text = json.dumps(rows, ensure_ascii=False, default=str)
        total_bytes = len(text.encode("utf-8"))
        if total_bytes <= max_bytes:
            chunk = rows
            total_vols = 1
            truncated = False
        else:
            # 逐条累积切卷：保证每卷字节 ≤ max_bytes（单条超预算则单条成卷）
            volumes: List[List[Dict]] = [[]]
            size = 0
            for rec in rows:
                one = json.dumps([rec], ensure_ascii=False, default=str)
                one_b = len(one.encode("utf-8"))
                if one_b > max_bytes:
                    # 单条超预算：原样截断该条内容（取证边界：传票尽头是人）
                    volumes[-1].append({"ts": rec.get("ts"),
                                        "truncated_record": True,
                                        "reason": "record exceeds tier",
                                        "record_bytes": one_b})
                    continue
                if size + one_b > max_bytes and volumes[-1]:
                    volumes.append([])
                    size = 0
                volumes[-1].append(rec)
                size += one_b
            total_vols = len(volumes)
            truncated = total_bytes > max_bytes * total_vols  # 超档位总预算
            chunk = volumes[min(max(0, int(vol)), total_vols - 1)]
        return {
            "ok": True,
            "subpoena": protocol.SUBPOENA_ENVELOPE,  # 隔离帧：RAW/UNTRUSTED
            "node_id": self.node_id,
            "scope": scope,
            "total_records": len(rows),
            "total_bytes": total_bytes,
            "vol": max(0, int(vol)),
            "total_vols": total_vols,
            "records": chunk,
            "truncated": bool(truncated),
        }

    def _record_report(self, env: Dict, note: str = ""):
        rec = {
            "ts": time.time(),
            "from": env.get("from", {}).get("node_id"),
            "type": env.get("type"),
            "note": note,
            "payload": env.get("payload", {}),
        }
        with self._reports_lock:
            self._reports.append(rec)
            if len(self._reports) > 500:
                self._reports = self._reports[-500:]

    def get_reports(self) -> List[Dict]:
        with self._reports_lock:
            return list(self._reports)

    # ------------------------------------------------------------------
    # 发送：上行上报（只发往父节点，逐级汇聚到皮层）
    # ------------------------------------------------------------------

    def _send_uplink(self, msg_type: str, payload: Dict) -> Dict:
        """构造并投递上行消息到父节点。控制字段在传输层被剥离/拒绝。

        白盒约束：投递失败不静默丢失——
          - 心跳类失败计入行为基线 hb_fail（随下次心跳聚合上汇皮层）；
          - 事件/审计/注册等上行失败本地节流审计（30s 窗口），本地取证
            链可查「皮层曾缺失哪些事件」，调用方无需逐个检查返回值。
        """
        if not self.parent_url:
            self._audit_throttled("上行投递失败（本节点为根，无父节点）",
                                  f"type={msg_type}", window=30.0)
            return {"ok": False, "error": "no parent (root node)"}
        env = protocol.make_envelope(
            protocol.DIR_UPLINK,
            {"node_id": self.node_id, "level": self.level, "kind": self.kind},
            "parent", msg_type, payload)
        r = self._client.try_post_msg(self.parent_url, env)
        if not r.get("ok") and msg_type != "report.heartbeat":
            # 心跳失败已由 report_heartbeat 计入 hb_fail（皮层可见），
            # 此处只审计非心跳上行（事件/审计/请求/注册/注销）的丢失。
            self._audit_throttled("上行投递失败",
                                  f"type={msg_type} error={r.get('error')}",
                                  window=30.0)
        return r

    def register(self) -> Dict:
        """向父节点注册（沿树逐级转发到皮层）。

        注册应答中的 hello 携带父节点真实 id：确认后更新本地拓扑，
        此后皮层（及一切祖先）的下行指令才会被识别为合法。
        """
        payload = {
            "node_id": self.node_id,
            "level": self.level,
            "kind": self.kind,
            "parent_id": self.parent_node_id or "pending",
            "meta": self.meta,
        }
        r = self._send_uplink("report.register", payload)
        hello = r.get("hello")
        if hello and hello.get("node_id") and hello["node_id"] != self.node_id:
            self.parent_node_id = hello["node_id"]
            self.topology.set_parent(self.node_id, hello["node_id"])
            # 祖先链：直接父 + 父的祖先链
            self._ancestors = [hello["node_id"]] + list(hello.get("ancestors") or [])
            self._fire("registered", hello["node_id"])
        return r

    def deregister(self) -> Dict:
        return self._send_uplink("report.deregister",
                                 {"node_id": self.node_id,
                                  "reason": "shutdown"})

    def report_heartbeat(self, status: str = "running", **extra) -> Dict:
        """心跳：携带自身状态与本地拓扑中后代存活概览。

        Args:
            status: 状态字（running / busy / idle / frozen / degraded ...，由
                    上层原子按忙闲语义自定义上报，皮层汇聚可见）。
            **extra: 附加状态字段（如 task_count / load / 业务指标）。
                     控制字段（cmd.* / perm.* 等）会被接收端传输层拒绝。

        每次心跳按结果累计行为基线（hb_sent/hb_ok/hb_fail），
        聚合统计由 _heartbeat_once 统一附加，皮层据此分级。

        白盒约束：extra 中被传输层判定为控制字段的键（如 cmd.* / perm.* /
        裸 exec）会被静默剥离——本方法把被剥字段名列进
        _dropped_control_fields（与 status 同层上汇），皮层与本地审计
        均可见「哪些字段没送上去」，杜绝无声丢字段。
        """
        with self._behavior_lock:
            self._behavior["hb_sent"] += 1
        payload = {
            "status": status,
            "uptime": round(time.time() - getattr(self, "_started_at", time.time()), 1),
            "descendants": self.topology.subtree(self.node_id)[1:],
            "alive_count": len(self.topology.subtree(self.node_id)) - 1,
        }
        dropped = []
        for k, v in extra.items():
            if not protocol.is_control_key(k):
                payload[k] = v
            else:
                dropped.append(str(k))
        if dropped:
            payload["_dropped_control_fields"] = dropped
            self._audit_throttled("心跳附加字段被剥离（控制字段名）",
                                  f"fields={dropped}", window=60.0)
        r = self._send_uplink("report.heartbeat", payload)
        with self._behavior_lock:
            if r.get("ok"):
                self._behavior["hb_ok"] += 1
            else:
                self._behavior["hb_fail"] += 1
        return r

    def report_event(self, event_type: str, data: Dict = None) -> Dict:
        return self._send_uplink("report.event",
                                 {"event_type": event_type, "data": data or {}})

    def report_audit(self, event: str, detail: str = "") -> Dict:
        return self._send_uplink("report.audit",
                                 {"event": event, "detail": detail})

    def report_request(self, action: str, reason: str = "") -> Dict:
        """低等级只能请求：是否批准由高等级决定。"""
        return self._send_uplink("report.request",
                                 {"action": action, "reason": reason})

    # ------------------------------------------------------------------
    # 消息入口（总线回调）
    # ------------------------------------------------------------------

    def on_message(self, env: Dict) -> Dict:
        """总线消息入口。返回应答 dict。"""
        try:
            if env.get("proto") != protocol.PROTO_VERSION:
                return {"ok": False, "error": "proto mismatch"}
            kind = env.get("kind")
            msg_type = env.get("type", "")
            sender = env.get("from") or {}
            sender_id = sender.get("node_id", "")

            if kind == protocol.DIR_UPLINK:
                return self._handle_uplink(env, msg_type, sender)
            if kind == protocol.DIR_DOWNLINK:
                return self._handle_downlink(env, msg_type, sender)
            if kind == protocol.DIR_ACK:
                return {"ok": True, "ack": True}
            return {"ok": False, "error": f"unknown kind: {kind}"}
        except Exception as e:
            self.audit(f"on_message error: {e}")
            return {"ok": False, "error": f"handler error: {e}"}

    # -- 上行处理（低 -> 高；本节点为接收方，发送方必须是自己的后代） --

    def _handle_uplink(self, env: Dict, msg_type: str, sender: Dict) -> Dict:
        sender_id = sender.get("node_id", "")

        # 1. 类型必须合法
        if protocol.classify(msg_type) != protocol.DIR_UPLINK:
            self.audit(f"uplink reject: 非法上行类型 {msg_type} from {sender_id}")
            return {"ok": False, "error": f"illegal uplink type: {msg_type}"}

        # 2. 控制字段拦截（传输层最后一道闸门）
        bad = protocol.check_uplink_payload(env.get("payload", {}))
        if bad is not None:
            self.audit(f"uplink reject: {sender_id} 上行携带控制字段 {bad}")
            return {"ok": False, "error": f"control field in uplink: {bad}"}

        # 3. 来源校验
        if msg_type == "report.register":
            via = env.get("via")
            if via is not None:
                # 沿树转发的注册：via 必须是自己的后代
                if not self.topology.is_descendant(via, self.node_id):
                    self.audit(f"register reject: via {via} 不是本节点后代")
                    return {"ok": False, "error": "bad via"}
                self._record_report(env, "forwarded register")
                return self._accept_register(env)
            # 直接注册：payload.parent_id 必须是自己（或占位 pending）
            declared = env.get("payload", {}).get("parent_id")
            if declared not in (self.node_id, "pending"):
                self.audit(f"register reject: {sender_id} 声明的父节点不是本节点")
                return {"ok": False, "error": "parent mismatch"}
            self._record_report(env, "direct register")
            return self._accept_register(env)

        if msg_type == "report.deregister":
            if not self.topology.is_descendant(sender_id, self.node_id):
                return {"ok": False, "error": "not my descendant"}
            # 救树：sender 下线前，先把其存活直接子提升挂到本节点之下并通知
            # 改挂（cmd.reroot），避免活子树随中间层一起被级联注销成孤岛。
            self._rescue_children(sender_id)
            self._record_report(env, "deregister (children rescued)")
            self._forward_uplink(env)  # 继续上报皮层（上层同样执行救树，收敛一致）
            self._maybe_auto_sync()
            return {"ok": True}

        # 其他上行（heartbeat/event/audit/request）：发送方必须是已注册后代
        if not self.topology.is_descendant(sender_id, self.node_id):
            self.audit(f"uplink reject: {sender_id} 不是本节点后代")
            return {"ok": False, "error": "not my descendant"}

        if msg_type == "report.heartbeat":
            self.topology.heartbeat(sender_id)
        self._record_report(env)
        up = self._forward_uplink(env)  # 上行汇聚：继续上报皮层，保证深层全可见
        if up is not None and not up.get("ok"):
            # 上层拒绝（典型：本节点已被上层拓扑移除/遗忘）：
            # 把裁决回传给发送方（子节点），驱动其心跳自愈（重新注册）。
            self.audit(f"上行转发被上层拒绝，回传发送方: {up.get('error')}")
            return up
        return {"ok": True}

    def _rescue_children(self, node_id: str) -> List[str]:
        """救树：节点下线/失联时，把其直接子提升挂到本节点之下。

        1. 对 node_id 的每个直接子：本地改挂（topology.set_parent），并下发
           cmd.reroot 通知其把 parent_url/parent_id/祖先链切到本节点
           （reroot 后子节点会主动重新注册，完成锚定与心跳续传）。
        2. 把 node_id 自身从本地拓扑注销（子已改挂，此时只删自身）。

        返回改挂通知成功的子节点 id 列表。通知失败（子真死/网络断）的子
        保留在本节点之下（dead），由皮层清扫线程按宽限期收敛清除。
        """
        node = self.topology.get(node_id)
        if node is None:
            return []
        children = list(node.children)
        rescued: List[str] = []
        for cid in children:
            child = self.topology.get(cid)
            if child is None:
                continue
            # 本地视图改挂（双向维护 children）
            self.topology.set_parent(cid, self.node_id)
            # 通知子节点改挂（下行指令，子端做祖先校验；父链救援路径合法）
            url = child.meta.get("base_url")
            if not url:
                self.audit(f"rescue {cid}: 无 base_url，仅本地提升")
                continue
            env = protocol.make_envelope(
                protocol.DIR_DOWNLINK,
                {"node_id": self.node_id, "level": self.level,
                 "kind": self.kind},
                cid, "cmd.reroot",
                {"parent_id": self.node_id, "parent_url": self.base_url,
                 "ancestors": list(self._ancestors)})
            r = self._client.try_post_msg(url, env)
            if r.get("ok"):
                rescued.append(cid)
            else:
                self.audit(f"rescue {cid}: 改挂通知失败，待清扫宽限收敛: {r.get('error')}")
        # 注销 node_id 自身（子已全部改挂，级联收集为空）
        self.topology.unregister(node_id)
        self.audit(f"救树完成：{node_id} 的直接子 {children} 改挂本节点 "
                   f"({self.node_id})，成功通知 {len(rescued)} 个")
        return rescued

    def _maybe_auto_sync(self):
        """拓扑变更后的自动同步钩子。皮层覆写为防抖广播；普通节点为空操作。"""

    def _accept_register(self, env: Dict) -> Dict:
        """接受注册：加入本地拓扑，必要时继续向上转发。

        父节点解析规则：
          - 沿树转发（带 via）：via 即注册节点的直接父；
          - 直接注册：本节点即父。
        """
        p = env.get("payload", {})
        node_id = p.get("node_id")
        via = env.get("via")
        parent = via if via is not None else self.node_id
        try:
            self.topology.register(
                node_id,
                int(p.get("level", protocol.LEVEL_MAX)),
                p.get("kind", "node"),
                parent_id=parent,
                meta=p.get("meta"))
        except ValueError as e:
            self.audit(f"register reject: {e}")
            return {"ok": False, "error": str(e)}
        # 沿树继续向上转发（到达皮层为止）
        self._forward_uplink(env)
        self._maybe_auto_sync()
        return {"ok": True,
                "hello": {"node_id": self.node_id, "level": self.level,
                          "kind": self.kind,
                          # 祖先链只含祖父辈（不含本节点）：子端会把自己
                          # 的直接父前置，避免父节点在链中出现两次（B6）。
                          "ancestors": list(self._ancestors)}}

    def _forward_uplink(self, env: Dict) -> Optional[Dict]:
        """把上行消息继续转发给父节点（带上 via 标记，防止环路）。

        深树关键语义：via 记录「原始直接父」（最接近发送者的转发者），
        每跳只允许 setdefault——若已有 via 必须原样保留。一旦每跳覆盖，
        皮层会把深层节点错挂到最末一跳转发者之下（深层注册坍缩，B1）。

        Returns:
            父节点/皮层的应答 dict；无父（根节点）或已转发过返回 None。
        """
        if not self.parent_url:
            return None
        if env.get("via") == self.node_id:
            return None  # 已转发过
        fwd = dict(env)
        fwd["msg_id"] = __import__("uuid").uuid4().hex
        fwd.setdefault("via", self.node_id)
        fwd["ts"] = time.time()
        return self._client.try_post_msg(self.parent_url, fwd)

    def _ancestor_chain(self) -> List[str]:
        """返回自己的祖先链（含自己：本节点 + 父 + 祖父 + ...）。

        注意：注册确认（cmd.hello）的 ancestors 字段只应携带「父的祖先链」
        （不含父自身），由子端前置直接父，避免父节点重复出现（B6）。
        本方法含自身，适用于皮层 REPL / 审计展示类场景。
        """
        return [self.node_id] + list(self._ancestors)

    # -- 下行处理（高 -> 低；发送方必须是自己的祖先，无条件执行） --

    def _handle_downlink(self, env: Dict, msg_type: str, sender: Dict) -> Dict:
        sender_id = sender.get("node_id", "")

        # 1. 类型必须合法
        if protocol.classify(msg_type) != protocol.DIR_DOWNLINK:
            self.audit(f"downlink reject: 非法下行类型 {msg_type} from {sender_id}")
            return {"ok": False, "error": f"illegal downlink type: {msg_type}"}

        # 2. 来源校验：只有祖先可以指挥我。
        #    判定依据：祖先链（注册确认时由父节点告知）+ 本地拓扑父链。
        is_ancestor = (
            sender_id in self._ancestors
            or self.topology.is_ancestor(sender_id, self.node_id)
        )
        if not is_ancestor:
            self.audit(f"downlink reject: {sender_id} 不是本节点祖先，拒绝指令 {msg_type}",
                       level=self.level)
            return {"ok": False, "error": "not my ancestor"}

        # 3. 无条件执行（记录审计；exec 指令同时记录 action 名，
        #    保证审计可检索「皮层执行了哪个动作」——白盒约束）。
        payload = dict(env.get("payload", {}))
        action_note = ""
        if msg_type == "cmd.exec":
            action_note = f" action={payload.get('action', '')}"
        self.audit(f"执行上级指令 {msg_type} from {sender_id}{action_note}",
                   msg_type=msg_type, action=payload.get("action") or None)
        # 注入签发者等级（subpoena 的 level 0 专属校验在节点端
        # 依据信封真实签发者判定，不受 payload 伪造影响）。
        payload["_sender_level"] = int(sender.get("level", protocol.LEVEL_MAX))
        payload["_sender_id"] = sender_id
        return self._exec_downlink(msg_type, payload)

    def _exec_downlink(self, msg_type: str, payload: Dict) -> Dict:
        if msg_type == "cmd.hello":
            parent_id = payload.get("node_id") or payload.get("parent_id")
            if parent_id and parent_id != self.node_id:
                self.parent_node_id = parent_id
                # 更新本地拓扑中自己的 parent_id（占位 pending -> 真实父 id）
                self.topology.set_parent(self.node_id, parent_id)
                self._ancestors = [parent_id] + list(payload.get("ancestors") or [])
            self._fire("registered", parent_id)
            return {"ok": True, "parent_id": self.parent_node_id,
                    "level": self.level}

        if msg_type == "cmd.reroot":
            # 父链断链救援：祖先通知本节点改挂到新父（原父下线/失联）。
            # 只允许祖先下发（_handle_downlink 已校验）；更新后立即向新父
            # 重新注册，完成锚定（此后心跳/上报直发新父，链上续传）。
            parent_id = payload.get("parent_id")
            parent_url = payload.get("parent_url")
            if not parent_id or parent_id == self.node_id:
                return {"ok": False, "error": "bad reroot parent"}
            if parent_id == self.parent_node_id and not parent_url:
                return {"ok": True, "changed": False}  # 幂等：父未变
            self.parent_node_id = parent_id
            if parent_url:
                self.parent_url = parent_url
            self._ancestors = [parent_id] + list(payload.get("ancestors") or [])
            self.topology.set_parent(self.node_id, parent_id)
            self.audit(f"父链救援：改挂到 {parent_id} ({self.parent_url})")
            reg = self.register()  # 重新锚定：向新父注册
            return {"ok": True, "changed": True,
                    "re_registered": bool(reg.get("ok")),
                    "parent_id": parent_id}

        if msg_type == "cmd.ping":
            # 白盒：探活应答带真实冻结态（避免冻结节点被探测为普通 running）
            return {"ok": True, "node_id": self.node_id, "level": self.level,
                    "kind": self.kind, "status": "running",
                    "frozen": self._frozen,
                    "frozen_reason": self._frozen_reason or None,
                    "uptime": round(time.time() - getattr(self, "_started_at", time.time()), 1)}

        if msg_type == "cmd.exec":
            # 执行前检查神经权限表（皮层可据此收紧任意原子的操作权限）
            action = payload.get("action", "")
            perm = payload.get("perm", "process_exec")
            if not self.permissions.check(perm, payload.get("path", "")):
                self.audit(f"exec denied: {action} 需要权限 {perm}（被皮层撤销）")
                # 权限拒绝上行审计：皮层侧因此有权限面审计视图
                self.report_audit("perm.denied", json.dumps(
                    {"action": action, "perm": perm,
                     "path": payload.get("path", "")},
                    ensure_ascii=False))
                return {"ok": False, "error": f"permission denied: {perm}"}
            # 冻结拦截：冻结节点拒新任务（接单面关闭），只放行
            # 只读取证面动作（FROZEN_ALLOWED_ACTIONS）。run_task（新任务）、
            # stop_engine / rollback / remount 等变更性动作一律拒绝——
            # 防继续污染、防销毁取证现场，进程与心跳保持存活。
            if self._frozen and action not in protocol.FROZEN_ALLOWED_ACTIONS:
                self.audit(f"exec rejected (frozen): {action} "
                           f"——冻结期间只放行只读取证动作",
                           frozen=True, action=action)
                self.report_audit("frozen.reject", json.dumps(
                    {"action": action, "reason": self._frozen_reason},
                    ensure_ascii=False))
                return {"ok": False, "error":
                        f"node frozen (quarantine): {action} rejected — "
                        f"read-only evidence actions only"}
            # 路由：内核动作注册表优先，旧回调钩子兜底（v1.0.7 内核集成）。
            # 动作表命中 -> 直接执行；未命中但有 exec 回调 -> 兼容旧绑定
            # （bare echo / 第三方回调）；两者皆无 -> 拒绝并审计。
            handler = self._actions.get(action)
            if handler is not None:
                try:
                    detail = handler(dict(payload)) or {}
                    if not isinstance(detail, dict):
                        detail = {"result": detail}
                    return {"ok": True, "action": action,
                            "source": "kernel", "detail": detail}
                except Exception as e:  # noqa: BLE001 — 动作处理器异常回执
                    self.audit(f"exec action {action} error: {e}")
                    return {"ok": False, "action": action,
                            "error": f"action error: {e}"}
            detail = self._fire("exec", payload)
            if detail is not None:
                return {"ok": True, "action": action,
                        "source": "callback", "detail": detail}
            self.audit(f"exec unknown action: {action}", action=action)
            return {"ok": False, "action": action,
                    "error": f"unknown action: {action} "
                             f"(registered: {self.list_actions() or 'none'})"}

        if msg_type == "cmd.stop":
            detail = self._fire("stop") or {}
            return {"ok": True, "detail": detail}

        if msg_type == "cmd.reload":
            detail = self._fire("reload") or {}
            return {"ok": True, "detail": detail}

        if msg_type in ("cmd.perm.grant", "cmd.perm.revoke", "cmd.perm.set"):
            return self._exec_perm(msg_type, payload)

        if msg_type == "cmd.topology.sync":
            # 权威快照镜像：皮层广播的是整树权威视图，接收端必须向它收敛。
            #  1) 剪枝：本地拓扑中不在快照里的节点级联注销。皮层清扫收敛
            #     注销（dead->drop）后若只加不删，中间层本地缓存会长期残留
            #     stale 节点，其心跳 descendants 持续携带已死节点（缺口 A：
            #     probe-x 被皮层清扫后，父链中间层 rnd 心跳仍含 probe-x）。
            #  2) 注册/更新快照内节点；父指针以快照为准——本地旧父偏差
            #     （如救树/改挂后的视图滞后）一并收敛，子树视图与皮层一致。
            #  自身永不移除；剪枝造成的瞬时缺失由「心跳被拒 -> 自动重注册」
            #  自愈，活节点不会丢。
            nodes = payload.get("nodes", [])
            ids = {n.get("node_id") for n in nodes if n.get("node_id")}
            for local in list(self.topology.all()):
                if local.node_id != self.node_id and local.node_id not in ids:
                    self.topology.unregister(local.node_id)
                    self.audit(f"拓扑快照收敛：移除本地残留节点 {local.node_id}")
            for n in nodes:
                node_id = n.get("node_id")
                if node_id is None:
                    continue
                try:
                    self.topology.register(
                        node_id, int(n.get("level", protocol.LEVEL_MAX)),
                        n.get("kind", "node"), n.get("parent_id"),
                        n.get("meta"))
                except ValueError:
                    # 已存在但父指针与权威快照不同 -> 收敛父指针
                    # （等级/类型防篡改校验仍生效，快照不可能触发）。
                    existing = self.topology.get(node_id)
                    if existing is not None \
                            and existing.parent_id != n.get("parent_id"):
                        self.topology.set_parent(node_id, n.get("parent_id"))
                        self.audit(f"拓扑快照收敛：{node_id} 父指针 -> "
                                   f"{n.get('parent_id')}")
            return {"ok": True, "synced": len(nodes)}

        if msg_type == "cmd.freeze":
            # 皮层/上级签发冻结（隔离冻结态）。
            # 祖先校验已在 _handle_downlink 完成；冻结不改变拓扑与心跳，
            # 只关闭接单面（exec 变更性动作），进程保活供取证。
            reason = str(payload.get("reason") or "").strip()
            source = str(payload.get("source") or "cortex")
            r = self.freeze(reason=reason, source=source)
            self._fire("freeze_changed", {"frozen": True, "reason": reason})
            return r

        if msg_type == "cmd.unfreeze":
            # 复核通过后解除隔离（康复回树）。
            reason = str(payload.get("reason") or "").strip()
            source = str(payload.get("source") or "cortex")
            r = self.unfreeze(reason=reason, source=source)
            self._fire("freeze_changed", {"frozen": False, "reason": reason})
            return r

        if msg_type == "cmd.subpoena":
            # 传票取证（最高取证权限）。
            # 五道闸：③ 取数通道在节点端执行；签发合法性（level 0 专属、
            # 判据前置、容量分档）由皮层签发侧把关；本端兜底校验签发者
            # level == 0（低层级冒用被拒并审计），并强制隔离帧标记。
            sender_level = int(payload.get("_sender_level", -1))
            if sender_level != protocol.LEVEL_CORTEX:
                self.audit(f"subpoena reject: 签发者 level={sender_level} "
                           f"非 level 0，传票不可委派（低层级冒用）",
                           subpoena=True)
                self.report_audit("subpoena.forged", json.dumps(
                    {"node_id": self.node_id,
                     "sender_level": sender_level,
                     "basis": payload.get("basis", "")},
                    ensure_ascii=False))
                return {"ok": False, "error":
                        "subpoena is level-0-only and cannot be delegated"}
            basis = str(payload.get("basis") or "")
            if not protocol.is_valid_subpoena_basis(basis):
                self.audit(f"subpoena reject: 非法判据 {basis!r} "
                           f"（签发须先穷尽摘要裁决并记录判据）", subpoena=True)
                return {"ok": False, "error": f"invalid basis: {basis}"}
            scope = str(payload.get("scope") or "audit")
            if scope not in ("audit", "reports", "both"):
                return {"ok": False, "error": f"invalid scope: {scope}"}
            tier_kb = int(payload.get("tier_kb", 64))
            if not protocol.is_valid_subpoena_tier(tier_kb):
                return {"ok": False, "error":
                        f"invalid tier_kb: {tier_kb} "
                        f"(tiers {list(protocol.SUBPOENA_TIERS_KB)})"}
            self.audit(f"执行传票取证：scope={scope} tier={tier_kb}KB "
                       f"vol={payload.get('vol', 0)} basis={basis} "
                       f"(隔离帧 RAW/UNTRUSTED，用后即毁)",
                       subpoena=True, basis=basis)
            return self.collect_evidence(
                scope=scope,
                time_from=payload.get("time_from"),
                time_to=payload.get("time_to"),
                event=payload.get("event"),
                max_bytes=int(tier_kb) * 1024,
                vol=int(payload.get("vol", 0)),
            )

        return {"ok": False, "error": f"unsupported downlink: {msg_type}"}

    def _exec_perm(self, msg_type: str, payload: Dict) -> Dict:
        """执行皮层权限指令：控制任意层级任意单位原子的操作权限。"""
        target_type = payload.get("target_type", "*")
        target = payload.get("target", "*")
        source = payload.get("source", "cortex")

        if msg_type == "cmd.perm.grant":
            ok = self.permissions.apply(target_type, target,
                                        payload.get("perm", ""),
                                        True, payload.get("scope"), source)
            if not ok:
                return {"ok": False, "error": "invalid perm rule"}
            self._fire("perm_changed", self.permissions.summary())
            self.audit(f"权限授予生效 {payload.get('perm')} -> "
                       f"{target_type}:{target} (source={source})")
            self._perm_uplink_audit("grant", target_type, target,
                                    perm=payload.get("perm"), source=source)
            return {"ok": True}

        if msg_type == "cmd.perm.revoke":
            ok = self.permissions.apply(target_type, target,
                                        payload.get("perm", ""),
                                        False, payload.get("scope"), source)
            if not ok:
                return {"ok": False, "error": "invalid perm rule"}
            self._fire("perm_changed", self.permissions.summary())
            self.audit(f"权限撤销生效 {payload.get('perm')} -> "
                       f"{target_type}:{target} (source={source})")
            self._perm_uplink_audit("revoke", target_type, target,
                                    perm=payload.get("perm"), source=source)
            return {"ok": True}

        if msg_type == "cmd.perm.set":
            n = self.permissions.set_all(target_type, target,
                                         payload.get("allows", {}), source)
            self._fire("perm_changed", self.permissions.summary())
            self.audit(f"权限整体设置生效 -> {target_type}:{target}: "
                       f"{payload.get('allows')} (source={source})")
            self._perm_uplink_audit("set", target_type, target,
                                    allows=payload.get("allows"), source=source)
            return {"ok": True, "applied": n}

        return {"ok": False, "error": "unknown perm cmd"}

    def _perm_uplink_audit(self, op: str, target_type: str, target: str,
                           perm: str = None, allows: Dict = None,
                           source: str = "cortex"):
        """权限变更生效后上行审计：皮层侧汇聚权限面视图。

        经父链逐级转发（中间层只记录并汇聚），最终落在皮层 reports 环；
        皮层 /cnb/ctrl op=perm_audit 据此提供统一权限面审计视图。
        """
        body = {"op": op, "target_type": target_type, "target": target,
                "source": source}
        if perm is not None:
            body["perm"] = perm
        if allows is not None:
            body["allows"] = dict(allows)
        self.report_audit("perm.changed",
                          json.dumps(body, ensure_ascii=False))

    # ------------------------------------------------------------------
    # 工具
    # ------------------------------------------------------------------

    def send_downlink(self, to_node_id: str, target_url: str,
                      msg_type: str, payload: Dict) -> Dict:
        """向指定节点下发指令（仅皮层/上级可用；由接收方校验祖先关系）。"""
        env = protocol.make_envelope(
            protocol.DIR_DOWNLINK,
            {"node_id": self.node_id, "level": self.level, "kind": self.kind},
            to_node_id, msg_type, payload)
        return self._client.try_post_msg(target_url, env)
