# -*- coding: utf-8 -*-
"""
nervous_bus.test_cnb — 中枢神经总线自测

覆盖需求点：
  R1 树状拓扑链：每节点唯一父节点，根为大脑皮层；深层注册沿树逐级上报
  R2 分层等级：level 越小等级越高；子级必须大于父级；等级不可篡改
  R3 上行只读：低层级只能 report.*，控制字段被总线拒绝
  R4 下行服从：皮层可对任意层级任意节点下发指令，节点无条件执行
  R5 权限控制：皮层可对任意层级任意单位原子 grant/revoke/set 操作权限
  R6 越权拦截：非祖先的下行拒绝；非后代的 uplink 拒绝；低等级不可改写高等级
  R7 权限面审计上行：perm.denied / perm.changed 经父链
     汇聚皮层 reports，皮层 ctrl op=perm_audit 提供统一权限面审计视图

运行：python -m nervous_bus.test_cnb
"""

import json
import time
import traceback
from typing import List

from . import protocol
from .bus import BusClient
from .cortex import Cortex
from .node import NervousNode

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


def wait_until(cond, timeout=5.0, interval=0.1):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if cond():
            return True
        time.sleep(interval)
    return False


def main():
    global PASS, FAIL
    print("=" * 64)
    print("中枢神经总线 CNB 自测开始")
    print("=" * 64)

    client = BusClient(timeout=8.0)
    cortex = Cortex(node_id="cortex", port=17800)
    cortex.start()
    check("T01 皮层上线", cortex._bus is not None)
    h = client.health("http://127.0.0.1:17800")
    check("T02 皮层健康检查", h.get("ok") and h.get("node_id") == "cortex"
          and h.get("level") == 0, str(h))

    # ---- 树状拓扑链：皮层 -> bot -> pilot；皮层 -> memory ----
    bot = NervousNode(node_id="norpbot-01", kind="bot", level=3,
                      parent_url="http://127.0.0.1:17800", port=17801,
                      heartbeat_interval=1.0)
    exec_log = []
    bot.on("exec", lambda p: exec_log.append(p) or {"echo": p.get("action")})
    bot.on("stop", lambda: {"stopped": True})
    bot.on("reload", lambda: {"reloaded": True})
    bot.start()

    pilot = NervousNode(node_id="norpilot-01", kind="pilot", level=4,
                        parent_url="http://127.0.0.1:17801", port=17802,
                        heartbeat_interval=1.0)
    pilot_exec_log = []
    pilot.on("exec", lambda p: pilot_exec_log.append(p) or {"echo": p.get("action")})
    pilot.on("stop", lambda: {"stopped": True})
    pilot.start()

    mem = NervousNode(node_id="norpmemory-01", kind="memory", level=3,
                      parent_url="http://127.0.0.1:17800", port=17803,
                      heartbeat_interval=1.0)
    mem.start()

    # R1：注册沿树逐级上报，皮层拥有全量拓扑
    check("T03 bot 注册进皮层拓扑",
          wait_until(lambda: cortex.topology.get("norpbot-01") is not None))
    check("T04 深层 pilot 注册（bot 转发到皮层）",
          wait_until(lambda: cortex.topology.get("norpilot-01") is not None))
    check("T05 memory 注册进皮层拓扑",
          wait_until(lambda: cortex.topology.get("norpmemory-01") is not None))
    check("T06 皮层拓扑共 4 节点", cortex.topology.size() == 4,
          f"size={cortex.topology.size()}")
    check("T07 pilot 的父节点是 bot",
          cortex.topology.get("norpilot-01").parent_id == "norpbot-01")
    check("T08 bot 的父节点是皮层",
          cortex.topology.get("norpbot-01").parent_id == "cortex")
    tree = cortex.topology.render_ascii()
    check("T09 拓扑树渲染含三层", "[3] norpbot-01" in tree and "[4] norpilot-01" in tree,
          tree)

    # R2：分层等级
    check("T10 皮层 level=0 最高", cortex.level == 0)
    check("T11 bot level=3 > 皮层", bot.level > cortex.level)
    check("T12 pilot level=4 > bot", pilot.level > bot.level)

    # R3：上行只读 —— 心跳/事件上报
    time.sleep(1.6)  # 等一轮心跳
    check("T13 皮层收到心跳上报",
          wait_until(lambda: any(r.get("type") == "report.heartbeat"
                                 and r.get("from") == "norpbot-01"
                                 for r in cortex.get_reports())))

    r = bot.report_event("task_done", {"task": "build"})
    check("T14 事件上报成功", r.get("ok"), str(r))
    check("T15 皮层记录到事件",
          any(r2.get("type") == "report.event" and r2.get("from") == "norpbot-01"
              for r2 in cortex.get_reports()))

    r = pilot.report_request("启动新任务", reason="需要皮层批准")
    check("T16 深层请求沿树到达皮层", r.get("ok"), str(r))

    # R4：下行服从 —— 皮层控制任意层级
    r = cortex.ping("norpbot-01")
    check("T17 皮层探活 bot", r.get("ok") and r.get("node_id") == "norpbot-01", str(r))
    r = cortex.ping("norpilot-01")
    check("T18 皮层探活深层 pilot（跨级直达）",
          r.get("ok") and r.get("node_id") == "norpilot-01", str(r))

    r = cortex.exec_cmd("norpbot-01", "run_task", {"task": "write docs"})
    check("T19 皮层下发执行指令到 bot", r.get("ok") and exec_log, str(r))
    check("T20 bot 无条件执行（回调触发）",
          exec_log and exec_log[-1].get("action") == "run_task")

    r = cortex.exec_cmd("norpilot-01", "fly", {"route": "A-B"})
    check("T21 皮层跨级执行到 pilot", r.get("ok") and pilot_exec_log, str(r))

    r = cortex.stop_node("norpilot-01")
    check("T22 皮层下令停止 pilot", r.get("ok"), str(r))

    r = cortex.reload_node("norpbot-01")
    check("T23 皮层下令重载 bot", r.get("ok"), str(r))

    # R5：操作权限控制 —— 任意层级任意单位原子
    r = cortex.perm_grant("node_id", "norpbot-01", "file_write")
    check("T24 皮层授予 bot file_write", r.get("ok"), str(r))
    check("T25 bot 权限表生效",
          bot.permissions.check("file_write") is True)

    r = cortex.perm_revoke("node_id", "norpbot-01", "process_shell")
    check("T26 皮层撤销 bot process_shell", r.get("ok"), str(r))
    check("T27 bot 权限表生效（process_shell 被禁）",
          bot.permissions.check("process_shell") is False)

    # 撤销后，需要 process_shell 权限的 exec 被拒绝
    r = cortex.exec_cmd("norpbot-01", "run_shell", {"cmd": "dir"},
                        perm="process_shell")
    check("T28 权限收紧后 exec 被拒绝",
          (not r.get("ok")) and "permission denied" in str(r.get("error")), str(r))

    # 按原子类型（node_kind）通配控制：所有 bot
    r = cortex.perm_set("node_kind", "bot", {"file_delete": False})
    check("T29 皮层按原子类型整体设置 bot 权限", r.get("ok"), str(r))
    check("T30 bot 的 file_delete 被禁", bot.permissions.check("file_delete") is False)

    # 全量通配 *
    r = cortex.perm_set("*", "*", {"network_out": False})
    check("T31 皮层全量收紧 network_out", r.get("ok"), str(r))
    check("T32 深层 pilot 也被全量规则约束",
          pilot.permissions.check("network_out") is False)

    # 权限指令落在权限表后，exec 检查生效（network_out 相关 action）
    r = cortex.exec_cmd("norpilot-01", "fetch_url", {"url": "http://x"},
                        perm="network_out")
    check("T33 深层 pilot 权限被控后拒绝执行",
          (not r.get("ok")) and "permission denied" in str(r.get("error")), str(r))

    # 恢复：重新授予
    r = cortex.perm_grant("node_id", "norpbot-01", "process_shell")
    check("T34 皮层重新授予 process_shell", r.get("ok"), str(r))
    check("T35 恢复后 exec 放行",
          cortex.exec_cmd("norpbot-01", "run_shell", {"cmd": "dir"},
                          perm="process_shell").get("ok"))

    # ---- 权限面审计上行（perm 拒绝/变更上汇皮层） ----

    def _perm_audit_events(node_id, event):
        return [r for r in cortex.get_reports()
                if r.get("type") == "report.audit" and r.get("from") == node_id
                and (r.get("payload") or {}).get("event") == event]

    # 触发一次 exec 权限拒绝 + 一次 perm 变更（撤销再恢复，不留副作用）
    cortex.perm_revoke("node_id", "norpbot-01", "process_shell")
    r = cortex.exec_cmd("norpbot-01", "run_shell", {"cmd": "dir"},
                        perm="process_shell")
    check("T-A0 撤销后 exec 被拒（构造审计事件）",
          (not r.get("ok")) and "permission denied" in str(r.get("error")), str(r))
    check("T-A1 皮层可见节点上行 perm.denied 审计",
          wait_until(lambda: bool(_perm_audit_events("norpbot-01", "perm.denied"))))
    check("T-A2 皮层可见节点上行 perm.changed 审计（撤销事件）",
          wait_until(lambda: bool(_perm_audit_events("norpbot-01", "perm.changed"))))
    r = cortex.perm_grant("node_id", "norpbot-01", "process_shell")
    check("T-A2b 重新授予 process_shell（恢复现场）", r.get("ok"), str(r))
    # 深层节点（pilot 经 bot 转发）：权限面审计同样汇聚皮层
    cortex.perm_revoke("node_id", "norpilot-01", "network_out")
    r = cortex.exec_cmd("norpilot-01", "fetch_url", {"url": "http://x"},
                        perm="network_out")
    check("T-A3 深层 pilot 权限拒绝",
          (not r.get("ok")) and "permission denied" in str(r.get("error")), str(r))
    check("T-A4 深层 pilot 的 perm.denied 经中间层转发到皮层",
          wait_until(lambda: bool(_perm_audit_events("norpilot-01", "perm.denied"))))
    # 皮层 ctrl 权限面审计视图
    r = client.post_ctrl("http://127.0.0.1:17800", {"op": "perm_audit", "n": 50})
    check("T-A5 皮层 ctrl op=perm_audit 返回权限面审计",
          r.get("ok") and isinstance(r.get("audit"), list)
          and len(r.get("audit", [])) >= 1, str(r)[:200])
    check("T-A6 perm_audit 视图同时含皮层操作与节点上行事件",
          any("perm.op." in str(a.get("event", "")) for a in r.get("audit", []))
          and any("perm.denied" in str(a.get("event", ""))
                  for a in r.get("audit", [])))

    # R6：越权拦截
    # 6a. 低等级向皮层发下行指令 -> 拒绝（皮层无祖先）
    env = protocol.make_envelope(protocol.DIR_DOWNLINK,
                                 {"node_id": "norpbot-01", "level": 3, "kind": "bot"},
                                 "cortex", "cmd.ping", {})
    r = client.post_msg("http://127.0.0.1:17800", env)
    check("T36 低等级向皮层发指令被拒",
          (not r.get("ok")) and "not my ancestor" in str(r.get("error")), str(r))

    # 6b. 平级节点互发指令 -> 拒绝（同级不可互控）
    env = protocol.make_envelope(protocol.DIR_DOWNLINK,
                                 {"node_id": "norpbot-01", "level": 3, "kind": "bot"},
                                 "norpmemory-01", "cmd.ping", {})
    r = client.post_msg("http://127.0.0.1:17803", env)
    check("T37 平级节点互发指令被拒",
          (not r.get("ok")) and "not my ancestor" in str(r.get("error")), str(r))

    # 6c. 低等级向上行消息中夹带控制字段 -> 拒绝
    env = protocol.make_envelope(protocol.DIR_UPLINK,
                                 {"node_id": "norpbot-01", "level": 3, "kind": "bot"},
                                 "parent", "report.heartbeat",
                                 {"status": "running", "cmd.exec": {"action": "x"},
                                  "perm.grant": {"perm": "file_write"}})
    r = client.post_msg("http://127.0.0.1:17800", env)
    check("T38 上行夹带控制字段被拒",
          (not r.get("ok")) and "control field" in str(r.get("error")), str(r))

    # 6d. 低等级试图提升自己等级（改写身份）-> 拒绝
    env = protocol.make_envelope(protocol.DIR_UPLINK,
                                 {"node_id": "norpbot-01", "level": 3, "kind": "bot"},
                                 "parent", "report.register",
                                 {"node_id": "norpbot-01", "level": 1,
                                  "kind": "bot", "parent_id": "cortex",
                                  "meta": {}})
    r = client.post_msg("http://127.0.0.1:17800", env)
    check("T39 等级篡改被拒", (not r.get("ok")), str(r))
    check("T40 拓扑中等级未被改写",
          cortex.topology.get("norpbot-01").level == 3)

    # 6e. 低等级试图更换父节点（改嫁）-> 拒绝
    env = protocol.make_envelope(protocol.DIR_UPLINK,
                                 {"node_id": "norpbot-01", "level": 3, "kind": "bot"},
                                 "parent", "report.register",
                                 {"node_id": "norpbot-01", "level": 3,
                                  "kind": "bot", "parent_id": "norpmemory-01",
                                  "meta": {}})
    r = client.post_msg("http://127.0.0.1:17800", env)
    check("T41 父节点篡改被拒", (not r.get("ok")), str(r))
    check("T42 拓扑中父节点未被改写",
          cortex.topology.get("norpbot-01").parent_id == "cortex")

    # 6f. 下行消息类型伪装（上行通道发 downlink 类型）-> 拒绝
    env = protocol.make_envelope(protocol.DIR_UPLINK,
                                 {"node_id": "norpbot-01", "level": 3, "kind": "bot"},
                                 "parent", "cmd.ping", {})
    r = client.post_msg("http://127.0.0.1:17800", env)
    check("T43 上行通道伪装下行类型被拒",
          (not r.get("ok")) and "illegal uplink" in str(r.get("error")), str(r))

    # 6g. 子节点向上级之外发心跳（发给自己的父的父？不，发给平级/上级以外的节点）
    env = protocol.make_envelope(protocol.DIR_UPLINK,
                                 {"node_id": "norpbot-01", "level": 3, "kind": "bot"},
                                 "norpmemory-01", "report.heartbeat",
                                 {"status": "running"})
    r = client.post_msg("http://127.0.0.1:17803", env)
    check("T44 非祖先的上行上报被拒",
          (not r.get("ok")) and "not my descendant" in str(r.get("error")), str(r))

    # R1 补充：级联注销与转发
    r = mem.deregister()
    check("T45 memory 注销", r.get("ok"), str(r))
    check("T46 皮层拓扑移除 memory",
          wait_until(lambda: cortex.topology.get("norpmemory-01") is None))

    # 级联保护（B3 修复）：bot 注销，其活子 pilot 被救树提升挂皮层，
    # 不再随中间层一起被级联注销成孤岛。
    r = bot.deregister()
    check("T47 bot 注销", r.get("ok"), str(r))
    check("T48 pilot 存活并提升挂皮层（活子树不陪葬）",
          wait_until(lambda: cortex.topology.get("norpilot-01") is not None
                     and cortex.topology.get("norpilot-01").parent_id == "cortex"))
    check("T48b 皮层可继续探活被救的 pilot",
          cortex.ping("norpilot-01").get("ok") is True)

    # 拓扑同步广播（皮层 -> 后代）
    r = cortex.sync_topology()
    check("T49 皮层拓扑广播", r.get("ok"), str(r))

    # 皮层控制端点（CLI 通道）
    c = BusClient(timeout=8.0)
    r = c.post_ctrl("http://127.0.0.1:17800", {"op": "topo"})
    check("T50 皮层控制端点 topo", r.get("ok") and r.get("size") >= 1, str(r))

    # 上报记录查询
    r = c.post_ctrl("http://127.0.0.1:17800", {"op": "reports", "n": 50})
    check("T51 皮层上报记录可查", r.get("ok") and len(r.get("reports", [])) > 0, str(r))

    # 清理
    pilot.stop()
    bot.stop()
    mem.stop()
    cortex.stop()
    time.sleep(0.3)

    print("=" * 64)
    print(f"自测结束：{PASS} 通过，{FAIL} 失败")
    if FAILURES:
        print("失败明细：")
        for f in FAILURES:
            print(f"  - {f}")
    print("=" * 64)
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception:
        traceback.print_exc()
        raise SystemExit(1)
