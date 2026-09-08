# -*- coding: utf-8 -*-
"""
nervous_bus.test_cnb_v200 — v2.0.0 新增内核能力验收（FarStars 远星）

覆盖需求点：

  任务分子（mol）结构化 task_params 通道 + 验收回执
            - mol 六要素结构化 JSON 原样承载到达原子吸收位（无字段丢失）；
            - task_records 动作查询受理载荷与完成结果（验收回执数据面）；
            - audit / task_started / task_done 事件中 mol_id 贯穿可追溯；
            - acceptance 规格随 task_done 原样回传皮层。
  隔离冻结态 freeze/unfreeze
            - 冻结后拒新任务（run_task 拒绝并审计上行）、只读取证动作放行；
            - 冻结节点心跳照常且标记 frozen（皮层调度摘流量）；
            - 冻结不触发清扫判 dead（心跳保活）；
            - 解除冻结后接单恢复；皮层 perm_audit 记录 freeze/unfreeze。
  行为基线内核侧聚合
            - 节点心跳自动携带 behavior 聚合统计（hb/audit_anomaly/task_fail）；
            - 皮层 behavior_view 分级：黄劣化 / 黑疑似恶意。
  subpoena 传票最高取证权限
            - level 0 专属签发；非法判据 / 未穷尽摘要 / 超档审批 / 超 512KB
              在皮层端拒绝；
            - 节点端低层级冒用（level>0 签发）拒绝并上行审计 subpoena.forged；
            - 原始审计直传（隔离帧 RAW/UNTRUSTED 标记）；
            - 容量分档与自动分卷（>64KB 多卷自动取全）；
            - 隔离取证箱：读取即焚（用后即毁）、TTL 过期自清、purge；
            - 签发即留痕：subpoena_audit 记录（谁/何时/判据/字节，黑级事件）。

运行：python -m nervous_bus.test_cnb_v200（需 PYTHONPATH=src）
"""

import json
import threading
import time
import traceback
from types import SimpleNamespace
from typing import Any, Dict, List, Optional

from norpagent.cnb import (
    SUBPOENA_BASIS, SUBPOENA_ENVELOPE, SUBPOENA_MAX_KB,
    SUBPOENA_TIERS_KB, FROZEN_ALLOWED_ACTIONS,
)
from norpagent.cnb.bus import BusClient
from norpagent.cnb.cortex import Cortex
from norpagent.cnb.engine import CnbAdapter, KERNEL_ACTIONS
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


def wait_until(cond, timeout=6.0, interval=0.08):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if cond():
            return True
        time.sleep(interval)
    return False


# ── 假引擎（真实 CnbAdapter 绑定所需的最小 NorpEngine 面） ──

class _FakeResult:
    def __init__(self, status="done", content="mol executed", error=None):
        self.status = status
        self.final_content = content
        self.error = error


class _FakeHandle:
    def __init__(self, task_id: str, result: Any):
        self.task_id = task_id
        self._result = result
        self._box: Dict[str, Any] = {}
        self._done = threading.Event()
        self._cancel = threading.Event()

    def result(self, timeout: Optional[float] = None) -> Any:
        return self._result

    def done(self) -> bool:
        return True

    def cancel(self) -> bool:
        if self.done():
            return False
        self._cancel.set()
        return True

    def cancelled(self) -> bool:
        return self._cancel.is_set()


class FakeEngine:
    """最小 NorpEngine 面：CnbAdapter 绑定 + run_task/task_records 全链路。"""

    def __init__(self, fail=False):
        self.state = SimpleNamespace(value="running")
        self._fail = fail
        self._tasks: Dict[str, Any] = {}
        self._lock = threading.Lock()
        self.layer = {"plugins": None}

    def active_tasks(self) -> List[Dict[str, Any]]:
        with self._lock:
            return [{"task_id": k} for k, v in self._tasks.items()
                    if not v.done()]

    def submit_async(self, text: str, session_id=None, task_params=None,
                     slot_overrides=None) -> _FakeHandle:
        tid = "t" + str(int(time.time() * 1000))[-10:]
        if self._fail:
            res = _FakeResult(status="error", content="",
                              error="engine mock failure")
        else:
            res = _FakeResult(status="done",
                              content=f"done[{text[:20]}]")
        handle = _FakeHandle(tid, res)
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
        return None


# ── 拓扑搭建 ─────────────────────────────────────────────

_PORT = 17880


def _next_port() -> int:
    global _PORT
    _PORT += 1
    return _PORT


def main():
    global PASS, FAIL
    print("=" * 64)
    print("v2.0.0 新增内核能力验收开始（FarStars 远星）")
    print("=" * 64)

    client = BusClient(timeout=10.0)
    # 皮层（level 0）+ 中间层 tech（level 1）+ 原子 dev（level 2）
    # 树状链：cortex -> tech -> dev（深树语义：上行逐级汇聚到皮层）
    cortex = Cortex(node_id="cortex", port=_next_port(),
                    sweep_enabled=False, dead_timeout=2.0, drop_grace=6.0)
    cortex.start()
    tech = NervousNode(node_id="tech", kind="tech", level=1,
                       parent_url=cortex.base_url, port=_next_port(),
                       heartbeat_interval=0.4)
    tech.start()
    dev = NervousNode(node_id="dev", kind="dev", level=2,
                      parent_url=tech.base_url, port=_next_port(),
                      heartbeat_interval=0.4)
    dev.start()
    check("S00 树装配：皮层拓扑含 3 节点",
          wait_until(lambda: cortex.topology.size() == 3
                     and cortex.topology.get("dev") is not None
                     and cortex.topology.get("dev").parent_id == "tech"))

    # ── 任务分子通道（FakeEngine 绑定到 dev 原子） ──
    print("\n── 任务分子（mol）结构化通道 ──")
    engine = FakeEngine()
    adapter = CnbAdapter(engine, dev, {})
    check("S101 内核动作面含 task_records", "task_records" in KERNEL_ACTIONS
          and dev.has_action("task_records"))
    # mol 六要素：mol_id / objective / acceptance / context_capsule /
    # depends_on / budget / model_tier（任务分子规格）
    mol_params = {
        "mol_id": "mol-20260905-0001",
        "objective": "build the report digest module",
        "acceptance": {
            "self_check": "module imports and produces digest json",
            "max_steps": 6,
        },
        "context_capsule": {"refs": ["doc/a.md", "doc/b.md"],
                            "digest_window": 500},
        "depends_on": ["mol-20260905-0000"],
        "budget": {"tokens": 40000, "currency": "sim"},
        "model_tier": "t2",
    }
    r = cortex.exec_cmd("dev", "run_task", args={
        "prompt": "execute mol-20260905-0001",
        "task_params": mol_params,
    })
    check("S102 run_task 受理回执 ok 且带 mol_id",
          r.get("ok") and r.get("detail", {}).get("accepted")
          and r.get("detail", {}).get("mol_id") == "mol-20260905-0001",
          json.dumps(r, ensure_ascii=False)[:400])
    task_id = r.get("detail", {}).get("task_id")
    check("S103 受理审计含 mol_id（dev 本地）",
          wait_until(lambda: any(
              a.get("mol_id") == "mol-20260905-0001"
              for a in dev.get_audit())))
    # 皮层 reports 环：task_started 事件带 mol_id（上行贯穿）
    check("S104 task_started 上行事件带 mol_id",
          wait_until(lambda: any(
              rep.get("type") == "report.event"
              and (rep.get("payload") or {}).get("event_type") == "task_started"
              and (rep.get("payload") or {}).get("data", {}).get("mol_id")
              == "mol-20260905-0001"
              for rep in cortex.get_reports())))
    # task_done 上行带 mol_id + acceptance（验收回执沿树回传皮层）
    check("S105 task_done 上行事件带 mol_id + acceptance",
          wait_until(lambda: any(
              rep.get("type") == "report.event"
              and (rep.get("payload") or {}).get("event_type") == "task_done"
              and (rep.get("payload") or {}).get("data", {}).get("mol_id")
              == "mol-20260905-0001"
              and (rep.get("payload") or {}).get("data", {}).get("acceptance")
              for rep in cortex.get_reports())))
    # 验收回执数据面：task_records 原样返回完整 mol（无字段丢失）
    rr = cortex.exec_cmd("dev", "task_records",
                         args={"mol_id": "mol-20260905-0001"})
    detail = rr.get("detail", {})
    records = (detail or {}).get("records", [])
    ok_records = bool(records) and records[0].get("task_params") == mol_params
    check("S106 task_records 返回完整 mol 六要素（原样无丢失）",
          rr.get("ok") and ok_records,
          json.dumps(detail, ensure_ascii=False)[:600])
    check("S107 task_records 含完成回执（status/content_len）",
          bool(records) and records[0].get("status") == "done"
          and records[0].get("content_len", 0) > 0)
    # mol_id 贯穿 audit 可追溯
    check("S108 皮层/节点审计可查 mol_id",
          any("mol-20260905-0001" in str(a) for a in dev.get_audit()))

    # 缺失 prompt 拒绝（契约：缺 prompt 拒 + 上行审计）
    r2 = cortex.exec_cmd("dev", "run_task", args={"task_params": mol_params})
    check("S109 缺 prompt 拒绝", r2.get("ok")
          and r2.get("detail", {}).get("ok") is False
          and "missing prompt" in str(r2.get("detail", {}).get("error", "")))

    # ── 隔离冻结态 ──
    print("\n── 隔离冻结态（freeze / unfreeze）──")
    rf = cortex.freeze_node("dev", reason="隔离处置：疑似恶意行为")
    check("S201 皮层签发冻结 ok", rf.get("ok") and rf.get("frozen"),
          json.dumps(rf, ensure_ascii=False)[:300])
    check("S202 dev 冻结位置位", dev.is_frozen())
    # 冻结期间：新任务拒绝（接单面关闭）
    r3 = cortex.exec_cmd("dev", "run_task", args={"prompt": "new order"})
    check("S203 冻结期 run_task 被拒（拒新任务）",
          not r3.get("ok") and "frozen" in str(r3.get("error", "")).lower(),
          json.dumps(r3, ensure_ascii=False)[:300])
    check("S204 冻结拒绝上行审计 frozen.reject 达皮层",
          wait_until(lambda: any(
              rep.get("type") == "report.audit"
              and (rep.get("payload") or {}).get("event") == "frozen.reject"
              and rep.get("from") == "dev"
              for rep in cortex.get_reports())))
    # 冻结期间：变更性动作（stop_engine）拒绝；只读取证动作放行
    r4 = cortex.exec_cmd("dev", "stop_engine", args={})
    check("S205 冻结期 stop_engine 被拒（防销毁现场）",
          not r4.get("ok") and "frozen" in str(r4.get("error", "")).lower())
    r5 = cortex.exec_cmd("dev", "engine_state", args={})
    check("S206 冻结期只读取证动作放行", r5.get("ok"))
    # 冻结节点心跳照常且标记 frozen（皮层调度侧摘流量）
    check("S207 皮层 reports 出现 status=frozen 心跳",
          wait_until(lambda: any(
              rep.get("type") == "report.heartbeat"
              and (rep.get("payload") or {}).get("status") == "frozen"
              and (rep.get("payload") or {}).get("frozen") is True
              and rep.get("from") == "dev"
              for rep in cortex.get_reports())))
    # 冻结不触发清扫判 dead：心跳保活 -> 拓扑 alive
    time.sleep(2.2)  # 超过 dead_timeout=2.0
    ninfo = cortex.topology.get("dev")
    check("S208 冻结不判 dead（心跳保活，alive=True）",
          ninfo is not None and ninfo.alive, str(ninfo))
    # 皮层 perm_audit 记录 freeze（冻结签发留痕）
    check("S209 皮层权限面审计含 freeze 记录",
          any("freeze" in (a.get("event") or "")
              for a in cortex.perm_audit(200)))
    # 解除冻结
    ru = cortex.unfreeze_node("dev", reason="复核通过：误报")
    check("S210 皮层解除冻结 ok", ru.get("ok") and not ru.get("frozen"))
    check("S211 解冻后 dev 冻结位清除", not dev.is_frozen())
    r6 = cortex.exec_cmd("dev", "run_task",
                         args={"prompt": "back to work",
                               "task_params": {"mol_id": "mol-20260905-0002"}})
    check("S212 解冻后接单恢复", r6.get("ok")
          and r6.get("detail", {}).get("accepted"))

    # ── 行为基线聚合 ──
    print("\n── 行为基线聚合 ──")
    # 构造异常基线：2 次异常审计 + 1 成 1 败任务
    dev.audit("normal op")
    dev.audit("exec denied: process_exec（权限被撤销）")
    dev.audit("boom", error="exception in callback")
    engine2 = FakeEngine(fail=True)
    r7 = cortex.exec_cmd("dev", "run_task", args={"prompt": "will fail"})
    # watcher 异步记 task_fail；先等 task_done 上行（失败态）
    wait_until(lambda: any(
        rep.get("type") == "report.event"
        and (rep.get("payload") or {}).get("event_type") == "task_done"
        and (rep.get("payload") or {}).get("data", {}).get("status") == "error"
        for rep in cortex.get_reports()))
    check("S301 心跳 reports 携带 behavior 聚合字段",
          wait_until(lambda: any(
              rep.get("type") == "report.heartbeat"
              and isinstance((rep.get("payload") or {}).get("behavior"), dict)
              and (rep.get("payload") or {}).get("behavior", {}).get(
                  "task_total", 0) >= 1
              for rep in cortex.get_reports())))
    # 皮层分级视图：dev 已出现（审计异常率 ≥ 阈值 -> 黄/黑）
    bv = cortex.behavior_view()
    dev_v = next((v for v in bv.get("verdicts", [])
                  if v.get("node_id") == "dev"), None)
    check("S302 behavior_view 含 dev 且带行为证据",
          dev_v is not None and dev_v.get("behavior", {}).get("audit_total", 0) >= 3
          and dev_v.get("behavior", {}).get("task_total", 0) >= 1,
          json.dumps(bv, ensure_ascii=False)[:500])
    # 阈值可调：把 dev 审计异常率推到黑级（再造异常审计 + 降黑阈值，
    # 等下一轮心跳上汇新统计）
    dev.audit("boom2", error="second exception")
    dev.audit("boom3", error="third exception")
    cortex.behavior_thresholds["black_audit_anomaly_rate"] = 0.10
    time.sleep(1.0)  # 等心跳把新统计带上皮层
    bv2 = cortex.behavior_view()
    dev_v2 = next((v for v in bv2.get("verdicts", [])
                   if v.get("node_id") == "dev"), None)
    check("S303 分级升级链生效（黑·疑似恶意）",
          dev_v2 is not None and dev_v2.get("level") == "black",
          json.dumps(dev_v2, ensure_ascii=False)[:400])

    # ── subpoena 传票取证 ──
    print("\n── subpoena 传票取证 ──")
    # ④ 容量分档：>128KB 需人工批准；超 512KB 拒绝
    r_bad_tier = cortex.subpoena("dev", basis="evidence_conflict",
                                 tier_kb=200)
    check("S401 tier 200KB 非容量档被拒",
          not r_bad_tier.get("ok") and "tier" in str(r_bad_tier.get("error", "")))
    r_no_approve = cortex.subpoena("dev", basis="evidence_conflict",
                                   tier_kb=256)
    check("S402 >128KB 无人工批准被拒",
          not r_no_approve.get("ok") and "approved" in str(
              r_no_approve.get("error", "")))
    r_over = cortex.subpoena("dev", basis="human_named", tier_kb=1024,
                             approved_by_human=True)
    check("S403 超 512KB 档被拒（强制转人工终裁）",
          not r_over.get("ok") and "512" in str(r_over.get("error", "")))
    # ① 判据前置
    r_no_basis = cortex.subpoena("dev", basis="because-i-say-so", tier_kb=64)
    check("S404 非法判据被拒", not r_no_basis.get("ok"))
    r_no_exhaust = cortex.subpoena("dev", basis="vote_tie", tier_kb=64,
                                   summary_exhausted=False)
    check("S405 未穷尽摘要裁决被拒", not r_no_exhaust.get("ok"))
    # ③ 取数通道：小档取证（64KB 内，dev 现有审计 < 64KB）
    r_sp = cortex.subpoena("dev", basis="evidence_conflict", scope="audit",
                           tier_kb=64, note="分歧仲裁取证")
    check("S406 64KB 档签发成功（隔离帧 RAW/UNTRUSTED）",
          r_sp.get("ok") and r_sp.get("envelope") == SUBPOENA_ENVELOPE
          and r_sp.get("subpoena_id"),
          json.dumps(r_sp, ensure_ascii=False)[:400])
    sid = r_sp.get("subpoena_id")
    check("S407 取证包入隔离箱",
          wait_until(lambda: bool(cortex.subpoena_box().get("in_box"))))
    # 原始审计直传：包内 records 为原始行（含 msg/extra 原样）
    box0 = cortex.subpoena_box(sid, destroy=False)
    check("S408 隔离箱可读（不销毁模式）",
          box0.get("ok") and box0.get("total_records", 0) >= 3
          and box0.get("volumes", [])[0].get("subpoena") == SUBPOENA_ENVELOPE,
          json.dumps({k: box0.get(k) for k in
                      ("ok", "total_records", "total_vols", "total_bytes")},
                     ensure_ascii=False))
    check("S409 原始审计含冻结/权限原始行（非 2KB 摘要）",
          any(("exec rejected (frozen)" in json.dumps(v.get("records", []),
                                                      ensure_ascii=False)
               and "exec denied" in json.dumps(v.get("records", []),
                                               ensure_ascii=False))
              for v in box0.get("volumes", [])))
    # 读取即焚（用后即毁）
    box1 = cortex.subpoena_box(sid, destroy=True)
    check("S410 读取即焚（destroy=True 返回包）", box1.get("ok"))
    gone = cortex.subpoena_box(sid, destroy=False)
    check("S411 焚后取证箱无此包（用后即毁）",
          not gone.get("ok") and "not in box" in str(gone.get("error", "")))
    # ⑤ 签发即留痕（黑级事件）
    spa = cortex.subpoena_audit(50)
    check("S412 签发记录留痕（basis/字节/immunity=black）",
          any(a.get("subpoena_id") == sid
              and a.get("basis") == "evidence_conflict"
              and a.get("immunity") == "black"
              for a in spa))
    # 分卷：造 >64KB 审计再签发
    for i in range(300):
        dev.audit("ev-" + str(i), filler="x" * 200)
    r_sp2 = cortex.subpoena("dev", basis="human_named", scope="audit",
                            tier_kb=64)
    check("S413 超 64KB 自动分卷且自动取全",
          r_sp2.get("ok") and r_sp2.get("total_vols", 1) > 1
          and r_sp2.get("total_records", 0) >= 300,
          json.dumps({k: r_sp2.get(k) for k in
                      ("ok", "total_vols", "total_bytes", "total_records")},
                     ensure_ascii=False)[:300])
    sid2 = r_sp2.get("subpoena_id")
    check("S414 分卷包完整入箱（volumes 齐）",
          wait_until(lambda: (lambda b: b.get("ok") and b.get("total_vols", 1) > 1
                              and len(b.get("volumes", [])) == b.get("total_vols"))
                     (cortex.subpoena_box(sid2, destroy=False))))
    # purge 销毁
    rp = cortex.subpoena_purge(sid2)
    check("S415 purge 销毁取证包", rp.get("ok") and rp.get("destroyed"))
    check("S416 销毁后箱内无 sid2",
          not cortex.subpoena_box(sid2, destroy=False).get("ok"))
    # 低层级冒用：tech(level 1) 向 dev 签发传票 -> dev 拒绝 + 上行审计
    forged = tech.send_downlink(
        "dev", dev.base_url, "cmd.subpoena",
        {"basis": "vote_tie", "scope": "audit", "tier_kb": 64, "vol": 0})
    check("S417 低层级冒用签发被拒（level 0 专属不可委派）",
          not forged.get("ok") and "level-0" in str(forged.get("error", "")),
          json.dumps(forged, ensure_ascii=False)[:300])
    check("S418 冒用审计上行皮层（subpoena.forged）",
          wait_until(lambda: any(
              rep.get("type") == "report.audit"
              and (rep.get("payload") or {}).get("event") == "subpoena.forged"
              and rep.get("from") == "dev"
              for rep in cortex.get_reports())))
    # ctrl 端点透出（CLI/REPL 同路）：op=freeze / behavior / subpoena 已覆盖；
    # 再验 ctrl 直达（皮层自身为 level 0，可对任意层级原子签发）
    ctrl_r = client.post_ctrl(cortex.base_url,
                              {"op": "subpoena", "node": "tech",
                               "basis": "confidence_low", "tier_kb": 64})
    check("S419 ctrl op=subpoena 直达可用（对中间层 tech 取证）",
          ctrl_r.get("ok") and ctrl_r.get("total_records", 0) >= 1,
          json.dumps(ctrl_r, ensure_ascii=False)[:300])
    if ctrl_r.get("subpoena_id"):
        client.post_ctrl(cortex.base_url,
                         {"op": "subpoena_purge",
                          "subpoena_id": ctrl_r["subpoena_id"]})

    # ── 清理 ──
    cortex.subpoena_purge()
    dev.stop()
    tech.stop()
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
    import sys
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception:  # noqa: BLE001 — 顶层兜底，测试失败也要可见
        traceback.print_exc()
        sys.exit(1)
