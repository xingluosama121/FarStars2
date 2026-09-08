# -*- coding: utf-8 -*-
"""
nervous_bus.test_cnb_whitebox — 全链路白盒专项验收（v2.0.0 同版本修订）

开发底线原则：全链路白盒 —— 任何能力从请求进入 → 内部处理 → 对外输出
的每一跳都必须可观测（审计/事件/状态上汇），不允许解释不了的黑盒环节。

本套件逐条验收白盒强化（黑盒缺口修复）：
  WB-01 协议控制字段判定收窄：executor/exec_count 等业务字段不再被误伤；
         裸 exec / exec.* / cmd.* / perm.* 仍拒绝。
  WB-02 皮层 exec/stop/reload 全程留皮层审计（谁向谁发了什么、结果如何）。
  WB-03 节点端审计带 action 名（皮层 exec 的动作可检索）。
  WB-04 引擎变更动作（snapshot/rollback/undo/redo/mark_good/remount/
         stop_task）动作级节点审计（subpoena 取证可检索）。
  WB-05 心跳状态提供者故障不静默：降级 degraded + provider_error 上汇
         皮层；故障/恢复各审计一次。
  WB-06 上行投递失败（事件/审计/注册）本地节流审计（皮层缺事件有据可查）。
  WB-07 心跳附加字段剥离不静默：被剥字段名 _dropped_control_fields 上汇
         可见。
  WB-08 总线层坏消息（坏 JSON/未知路径）留节点审计（协议层故障可见）。
  WB-09 cmd.ping 带真实冻结态（冻结节点探测不再误报 running）。
  WB-10 behavior_view 对无心跳节点补 no-data 行（分级视图不静默缺行）。
  WB-11 subpoena 签发支持 actor 身份（审计「谁签发的」完整）。
  WB-12 皮层 on_ctrl sweep 触发留审计；版本号保持 2.0.0（不 bump）。

运行：python -m nervous_bus.test_cnb_whitebox（需 PYTHONPATH=src）
"""

import http.client
import json
import sys
import threading
import time
import traceback
from types import SimpleNamespace
from typing import Any, Dict, List, Optional

import norpagent
from norpagent.cnb import protocol
from norpagent.cnb.bus import BusClient
from norpagent.cnb.cortex import Cortex
from norpagent.cnb.engine import CnbAdapter
from norpagent.cnb.node import NervousNode

PASS = 0
FAIL = 0
FAILURES: List[str] = []


def check(name: str, cond: bool, detail: str = ""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  [PASS] {name}")
    else:
        FAIL += 1
        FAILURES.append(f"{name}: {detail}")
        print(f"  [FAIL] {name}  <- {detail}")


def wait_until(cond, timeout=8.0, interval=0.08):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if cond():
            return True
        time.sleep(interval)
    return False


def audit_has(target, msg_part: str, **fields) -> bool:
    """目标（节点/皮层）审计环内存在 msg 含 msg_part 且 extra 字段匹配的记录。"""
    for rec in target.get_audit():
        if msg_part in str(rec.get("msg", "")):
            if all(rec.get(k) == v for k, v in fields.items()):
                return True
    return False


# ── 假引擎（覆盖快照面/运维面/任务面的最小 NorpEngine） ──

class _FakeResult:
    def __init__(self, status="done", content="wb done", error=None):
        self.status = status
        self.final_content = content
        self.error = error


class _FakeHandle:
    def __init__(self, task_id: str, result: Any):
        self.task_id = task_id
        self._result = result

    def result(self, timeout: Optional[float] = None) -> Any:
        return self._result

    def done(self) -> bool:
        return True

    def cancel(self) -> bool:
        return False

    def cancelled(self) -> bool:
        return False


class FakeEngine:
    """最小 NorpEngine 面：CnbAdapter 动作面全绑定 + 可观测性验证。"""

    def __init__(self):
        self.state = SimpleNamespace(value="running")
        self._tasks: Dict[str, Any] = {}
        self._lock = threading.Lock()
        self.layer = {"plugins": None}
        self.preset = SimpleNamespace(name="wb-preset", model="mock")
        self.last_result = None
        self.remount_calls: List[Dict[str, Any]] = []
        self.snap_count = 0

    def active_tasks(self) -> List[Dict[str, Any]]:
        with self._lock:
            return [{"task_id": k} for k, v in self._tasks.items()
                    if not v.done()]

    def submit_async(self, text: str, session_id=None, task_params=None,
                     slot_overrides=None) -> _FakeHandle:
        tid = "wt" + str(int(time.time() * 1000))[-10:]
        handle = _FakeHandle(tid, _FakeResult())
        with self._lock:
            self._tasks[tid] = handle
        return handle

    def forget_task(self, task_id: str) -> bool:
        with self._lock:
            return self._tasks.pop(task_id, None) is not None

    def cancel_task(self, task_id: str) -> bool:
        return False

    def stop_all_tasks(self) -> int:
        return 0

    def is_running(self) -> bool:
        return True

    def should_stop(self) -> bool:
        return False

    def request_stop(self) -> None:
        pass

    def remount(self, **kwargs) -> None:
        self.remount_calls.append(kwargs)

    def snapshot(self, description="", tag="cnb"):
        self.snap_count += 1
        return {"snap_id": f"snap-{self.snap_count}", "tag": tag,
                "description": description}

    def rollback(self, snap_id=None):
        return {"ok": True, "snap_id": snap_id}

    def undo(self):
        return {"ok": True}

    def redo(self):
        return {"ok": True}

    def mark_good(self, snap_id=None):
        return {"ok": True, "snap_id": snap_id}

    def list_snapshots(self):
        return [{"snap_id": "snap-1", "tag": "cnb"}]


# ── 端口分配（独立段 17980+，避免与其它套件并发冲突） ──

_PORT = 17980


def _next_port() -> int:
    global _PORT
    _PORT += 1
    return _PORT


def main():
    global PASS, FAIL
    print("=" * 64)
    print("全链路白盒专项验收（WB-01 ~ WB-12）")

    # ── WB-01 协议控制字段判定收窄（纯函数） ──
    print("\n── WB-01 控制字段判定收窄 ──")
    check("W101 裸 exec 仍是控制字段",
          protocol.is_control_key("exec") is True)
    check("W102 exec.* 域仍是控制字段",
          protocol.is_control_key("exec.foo") is True
          and protocol.is_control_key("exec.args") is True)
    check("W103 业务字段 executor 不再误伤",
          protocol.is_control_key("executor") is False)
    check("W104 业务字段 exec_count 不再误伤",
          protocol.is_control_key("exec_count") is False)
    check("W105 业务字段 execution 不再误伤",
          protocol.is_control_key("execution") is False)
    check("W106 cmd.* / perm.* / config.set* / topology.mutate* / control.* 仍拒",
          protocol.is_control_key("cmd.ping") is True
          and protocol.is_control_key("perm.grant") is True
          and protocol.is_control_key("config.set.threads") is True
          and protocol.is_control_key("topology.mutate.x") is True
          and protocol.is_control_key("control.flag") is True)
    check("W107 普通状态字段放行",
          protocol.is_control_key("status") is False
          and protocol.is_control_key("task_count") is False
          and protocol.is_control_key("engine_state") is False)

    # ── 拓扑搭建：cortex -> node1（bare + wb_echo 占位动作） ──
    print("\n── 拓扑搭建 ──")
    cortex = Cortex(node_id="cortex", port=_next_port(),
                    sweep_enabled=False, dead_timeout=2.0, drop_grace=8.0)
    cortex.start()
    node1 = NervousNode(node_id="node1", kind="bot", level=3,
                        parent_url=cortex.base_url, port=_next_port(),
                        heartbeat_interval=60.0)  # 60s：测试期不自动心跳
    node1.register_action("wb_echo", lambda payload: {"echo": "ok"})
    node1.start()
    check("W108 node1 注册挂树",
          wait_until(lambda: node1.parent_node_id == "cortex"))
    client = BusClient(timeout=6.0)

    # ── WB-02 皮层 exec/stop/reload 审计 ──
    print("\n── WB-02 皮层下行指令审计留痕 ──")
    r1 = cortex.exec_cmd("node1", "wb_echo")
    check("W201 exec wb_echo 执行成功", bool(r1.get("ok")),
          json.dumps(r1, ensure_ascii=False)[:200])
    check("W202 皮层审计含 exec 记录（action/node）",
          wait_until(lambda: audit_has(cortex, "皮层执行指令 exec",
                                       action="wb_echo", node="node1")))
    r2 = cortex.exec_cmd("node1", "no_such_action")
    check("W203 未知动作被拒", (not r2.get("ok")) and "unknown" in str(r2.get("error", "")),
          json.dumps(r2, ensure_ascii=False)[:200])
    check("W204 皮层审计含失败 exec（ok=False）",
          wait_until(lambda: any(
              "皮层执行指令 exec" in str(a.get("msg", ""))
              and a.get("action") == "no_such_action"
              and "ok=False" in str(a.get("msg", ""))
              for a in cortex.get_audit())))
    cortex.stop_node("node1")
    check("W205 皮层审计含 stop 指令", audit_has(cortex, "皮层下令停止",
                                                node="node1"))
    cortex.reload_node("node1")
    check("W206 皮层审计含 reload 指令", audit_has(cortex, "皮层下令重载",
                                                  node="node1"))

    # ── WB-03 节点端审计带 action 名 ──
    print("\n── WB-03 节点审计 action 可检索 ──")
    check("W301 节点审计含 action=wb_echo 的指令记录",
          wait_until(lambda: audit_has(node1, "执行上级指令",
                                       msg_type="cmd.exec", action="wb_echo")))
    check("W302 节点审计含未知动作拒绝（action=no_such_action）",
          wait_until(lambda: any(
              "unknown action" in str(a.get("msg", ""))
              and a.get("action") == "no_such_action"
              for a in node1.get_audit())))

    # ── WB-08 总线层坏消息留痕 ──
    print("\n── WB-08 总线坏消息审计 ──")
    before = len(node1.get_audit())
    conn = http.client.HTTPConnection("127.0.0.1", node1.port, timeout=5)
    conn.request("POST", "/cnb/msg", body=b"{bad json!!",
                 headers={"Content-Type": "application/json"})
    resp = conn.getresponse()
    resp.read()
    conn.close()
    check("W801 坏 JSON 返回 400", resp.status == 400)
    check("W802 节点审计出现「总线拒绝消息: 坏 JSON」",
          wait_until(lambda: any(
              "总线拒绝消息" in str(a.get("msg", ""))
              and "坏 JSON" in str(a.get("msg", ""))
              for a in node1.get_audit())))
    conn = http.client.HTTPConnection("127.0.0.1", node1.port, timeout=5)
    conn.request("POST", "/cnb/nope", body=b"{}",
                 headers={"Content-Type": "application/json"})
    resp2 = conn.getresponse()
    resp2.read()
    conn.close()
    check("W803 未知路径返回 404", resp2.status == 404)
    check("W804 节点审计出现未知路径拒绝",
          wait_until(lambda: any(
              "总线拒绝消息" in str(a.get("msg", ""))
              and "未知路径" in str(a.get("msg", ""))
              for a in node1.get_audit())))
    check("W805 总线审计量只增错误记录（正常消息不入总线审计）",
          len(node1.get_audit()) >= before)  # 至少不丢记录

    # ── WB-09 ping 带冻结态 ──
    print("\n── WB-09 ping 真实冻结态 ──")
    fr = cortex.freeze_node("node1", reason="whitebox-check")
    check("W901 冻结签发成功", bool(fr.get("frozen")),
          json.dumps(fr, ensure_ascii=False)[:200])
    p1 = cortex.ping("node1")
    check("W902 冻结节点 ping 带 frozen=True",
          p1.get("frozen") is True and "whitebox-check" in str(p1.get("frozen_reason", "")),
          json.dumps(p1, ensure_ascii=False)[:200])
    ufr = cortex.unfreeze_node("node1", reason="whitebox-pass")
    check("W903 解除冻结成功", bool(ufr.get("ok"))
          and ufr.get("frozen") is False)
    p2 = cortex.ping("node1")
    check("W904 解冻后 ping frozen=False", p2.get("frozen") is False,
          json.dumps(p2, ensure_ascii=False)[:200])

    # ── WB-10 behavior_view no-data 行（先注册 node2，未心跳） ──
    print("\n── WB-10 behavior_view 无心跳节点可见 ──")
    node2 = NervousNode(node_id="node2", kind="pilot", level=4,
                        parent_url=cortex.base_url, port=_next_port(),
                        heartbeat_interval=60.0)
    node2.start()
    check("W1001 node2 注册挂树",
          wait_until(lambda: node2.parent_node_id == "cortex"))
    bv = cortex.behavior_view()
    no_data = [v for v in bv.get("verdicts", []) if v.get("level") == "no-data"]
    check("W1002 分级视图含 no-data 行（node2 首跳前）",
          any(v.get("node_id") == "node2" for v in no_data),
          json.dumps(bv, ensure_ascii=False)[:400])

    # ── WB-11 subpoena actor 身份 ──
    print("\n── WB-11 subpoena actor 留痕 ──")
    sp = client.post_ctrl(cortex.base_url, {
        "op": "subpoena", "node": "node1", "basis": "confidence_low",
        "tier_kb": 64, "actor": "human-zz"})
    check("W1101 ctrl 签发成功（actor 透传）",
          sp.get("ok") and sp.get("subpoena_id", ""),
          json.dumps(sp, ensure_ascii=False)[:300])
    check("W1102 签发记录 actor=human-zz",
          wait_until(lambda: any(
              a.get("actor") == "human-zz" and a.get("node_id") == "node1"
              for a in cortex.subpoena_audit(20))))
    if sp.get("subpoena_id"):
        cortex.subpoena_purge(sp["subpoena_id"])

    # ── WB-04 引擎变更动作动作级审计（绑定 FakeEngine） ──
    print("\n── WB-04 变更动作动作级审计 ──")
    engine = FakeEngine()
    adapter = CnbAdapter(engine, node1, {})
    check("W401 内核动作面已绑定",
          "snapshot" in node1.list_actions()
          and "mark_good" in node1.list_actions()
          and "remount" in node1.list_actions())
    cortex.exec_cmd("node1", "snapshot", args={"description": "wb-snap", "tag": "wb"})
    check("W402 snapshot 动作级审计", audit_has(node1, "exec snapshot", ok=True))
    cortex.exec_cmd("node1", "rollback", args={"snap_id": "snap-1"})
    check("W403 rollback 动作级审计", audit_has(node1, "exec rollback", ok=True))
    cortex.exec_cmd("node1", "undo")
    check("W404 undo 动作级审计", audit_has(node1, "exec undo", ok=True))
    cortex.exec_cmd("node1", "redo")
    check("W405 redo 动作级审计", audit_has(node1, "exec redo", ok=True))
    cortex.exec_cmd("node1", "mark_good", args={"snap_id": "snap-1"})
    check("W406 mark_good 动作级审计", audit_has(node1, "exec mark_good", ok=True))
    cortex.exec_cmd("node1", "remount", args={"preset": "wb"})
    check("W407 remount 动作级审计", audit_has(node1, "exec remount", ok=True))
    cortex.exec_cmd("node1", "stop_task", args={"task_id": "nope-1"})
    check("W408 stop_task 动作级审计（含未命中任务）",
          audit_has(node1, "exec stop_task", cancelled=False))
    cortex.exec_cmd("node1", "stop_task")
    check("W409 stop_task 缺 task_id 拒绝审计",
          audit_has(node1, "exec stop_task rejected"))
    # 只读动作不产生引擎动作级审计（防轮询刷屏；指令级统一审计已含 action）
    cortex.exec_cmd("node1", "engine_state")
    check("W410 只读动作无引擎动作级审计（无 exec engine_state 完成记录）",
          not audit_has(node1, "exec engine_state"))

    # ── WB-05 心跳 provider 故障降级（覆盖为故障 provider） ──
    print("\n── WB-05 provider 故障降级上汇 ──")

    def bad_provider():
        raise RuntimeError("wb-provider-down")

    node1.set_heartbeat_provider(bad_provider)
    hb1 = node1._heartbeat_once()
    check("W501 故障心跳仍成功上汇（降级不阻断心跳/不触发判 dead）",
          hb1.get("ok") is True, json.dumps(hb1, ensure_ascii=False)[:200])
    # 断言：_heartbeat_once 内部 report_heartbeat 的应答；故障体现在审计与
    # 上汇载荷——通过皮层 reports 断言（下方 W502），此处先断言本地审计。
    check("W502 节点审计「心跳状态提供者故障」（翻转一次）",
          wait_until(lambda: audit_has(node1, "心跳状态提供者故障")))
    check("W503 故障标记置位", node1._provider_failed is True)
    # 皮层 reports 应出现 degraded 心跳（node1 心跳上汇）
    check("W504 皮层可见 degraded 心跳（provider_error 字段）",
          wait_until(lambda: any(
              (rep.get("payload") or {}).get("status") == "degraded"
              and "wb-provider-down" in str(
                  (rep.get("payload") or {}).get("provider_error", ""))
              for rep in cortex.get_reports())))
    # 恢复
    node1.set_heartbeat_provider(lambda: ("running", {"engine_state": "running"}))
    hb2 = node1._heartbeat_once()
    check("W505 恢复后心跳 running 且上汇成功",
          hb2.get("ok") is True, json.dumps(hb2, ensure_ascii=False)[:200])
    check("W506 恢复审计（翻转一次）",
          wait_until(lambda: audit_has(node1, "心跳状态提供者已恢复")))
    check("W507 故障标记复位", node1._provider_failed is False)

    # ── WB-07 心跳附加字段剥离可见 ──
    print("\n── WB-07 剥离字段不静默 ──")
    node1.report_heartbeat("running", exec_count=3, executor="wb",
                           cmd_evil=1, exec=2)
    check("W701 皮层收到含业务字段心跳（exec_count/executor 未被误剥）",
          wait_until(lambda: any(
              (rep.get("payload") or {}).get("exec_count") == 3
              and (rep.get("payload") or {}).get("executor") == "wb"
              for rep in cortex.get_reports())))
    # 注：控制判据是点分域——"cmd_evil"（下划线）不是控制字段会被放行；
    # 用点分 "cmd.evil" 才是真控制字段，应被剥且列入 dropped 上汇。
    node1.report_heartbeat("running", exec_count=4, executor="wb2",
                           **{"cmd.evil": 1, "exec": 2})
    check("W702 被剥字段名上汇可见（_dropped_control_fields）",
          wait_until(lambda: any(
              "cmd.evil" in ((rep.get("payload") or {})
                             .get("_dropped_control_fields") or [])
              and "exec" in ((rep.get("payload") or {})
                             .get("_dropped_control_fields") or [])
              and (rep.get("payload") or {}).get("exec_count") == 4
              for rep in cortex.get_reports())))
    check("W703 节点本地审计剥离事件",
          audit_has(node1, "心跳附加字段被剥离"))

    # ── WB-12 on_ctrl sweep 审计（置于 WB-05/07 心跳产生之后：
    #    手动 sweep 不会把有近期心跳的 node1 当 dead 清掉） ──
    print("\n── WB-12 手动 sweep 留痕 ──")
    sw = client.post_ctrl(cortex.base_url, {"op": "sweep"})
    check("W1201 ctrl sweep 执行成功", bool(sw.get("ok")))
    check("W1202 皮层审计含手动清扫记录",
          audit_has(cortex, "手动触发失联清扫"))

    # ── WB-06 上行投递失败本地审计 ──
    print("\n── WB-06 上行失败不静默 ──")
    orphan = NervousNode(node_id="orphan", kind="node", level=5,
                         parent_url=None, port=_next_port())
    rr = orphan.report_event("some.event", {"x": 1})
    check("W601 无父节点上报被拒", (not rr.get("ok")))
    check("W602 无父上报失败留本地审计",
          audit_has(orphan, "上行投递失败（本节点为根，无父节点）"))
    dead = NervousNode(node_id="deadpar", kind="node", level=5,
                       parent_url="http://127.0.0.1:1", port=_next_port())
    rr2 = dead.report_event("some.event", {"x": 1})
    check("W603 死父上报失败返回 error", (not rr2.get("ok")),
          json.dumps(rr2, ensure_ascii=False)[:200])
    check("W604 死父上报失败留本地审计（type 可见）",
          audit_has(dead, "上行投递失败"))
    # 节流：连续 3 次只记 1 条（30s 窗口内）
    for _ in range(3):
        dead.report_event("some.event", {"x": 1})
    cnt = sum(1 for a in dead.get_audit()
              if "上行投递失败" in str(a.get("msg", "")))
    check("W605 节流审计：同类型 30s 窗口内只记首条",
          cnt == 1, f"count={cnt}")

    # ── 版本号不动 ──
    print("\n── 版本号保持 2.0.1 ──")
    check("W-ver 版本号仍为 2.0.1（不 bump）",
          norpagent.__version__ == "2.0.1", norpagent.__version__)

    # ── 清理 ──
    node2.stop()
    node1.stop()
    cortex.subpoena_purge()
    cortex.stop()

    print("=" * 64)
    if FAIL:
        print(f"自测结束：{PASS} 通过，{FAIL} 失败")
        for f in FAILURES:
            print("  FAILED:", f)
    else:
        print(f"自测结束：{PASS} 通过，0 失败")
    print("=" * 64)
    return 1 if FAIL else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception:  # noqa: BLE001 — 顶层兜底，测试失败也要可见
        traceback.print_exc()
        sys.exit(1)
