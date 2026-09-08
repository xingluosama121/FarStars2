# -*- coding: utf-8 -*-
"""
nervous_bus.test_deep_tree — 深树回归测试（>=4 层链式转发场景）

体检结论「浅树自洽、深树断裂」（B1-B9）的回归防线。官方 51+13+12 项自测
全部是 <=2 层扁平场景（原子直挂皮层），从未覆盖 >=3 层链式转发。本套件
专门构造 cortex -> tech -> rnd -> dev 四层链，逐项验证：

  D01-D03  深层注册父子关系正确（B1：via 逐级转发不再被每跳覆盖坍缩）
  D04      祖先链无重复（B6：hello 不再把父节点重复进链）
  D05      深层心跳/事件/请求上行汇聚到皮层（B2：中间层只记录不转发 -> 全盲）
  D06      中间层正常退出 -> 活子树救树提升，不被级联注销（B3）
  D07      中间层崩溃（无 deregister）-> 皮层失联清扫 + 救树（B3 crash / B5 接线）
  D08      权限纯时间序判定：类型级 revoke 不再被旧 node_id grant 屏蔽（B4）
  D09      心跳状态自定义位透传（B7：status/额外字段上行可见）
  D10      注册/注销后皮层自动广播拓扑（B8：不再依赖手动 sync）
  D11      心跳被拒自动重新注册（父重启/皮层视图重建后节点自愈）
  D12      真死节点（无子可救）由清扫线程收敛注销（B5 sweep 闭环）
  D13      皮层清扫后中间层本地缓存收敛（缺口 A：probe-x 强杀 -> 皮层
           注销并广播 -> rnd 本地拓扑/心跳 descendants 不再残留 stale
           节点；cmd.topology.sync 权威快照镜像：剪枝 + 父指针收敛）

运行：PYTHONPATH=src python -m nervous_bus.test_deep_tree
"""

import socket
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


def wait_until(cond, timeout=8.0, interval=0.1):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if cond():
            return True
        time.sleep(interval)
    return False


def free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def crash(node: NervousNode):
    """模拟进程崩溃：停心跳线程 + 关总线，不发送 deregister。"""
    node._running = False
    node._stop_event.set()
    try:
        node._bus.shutdown()
        node._bus.server_close()
    except Exception:
        pass


def main():
    global PASS, FAIL
    print("=" * 64)
    print("CNB 深树回归测试（4 层链：cortex -> tech -> rnd -> dev）")
    print("=" * 64)

    # ---- 动态端口：皮层 + 四层节点 ----
    p_cortex, p_tech, p_rnd, p_dev = (free_port(), free_port(),
                                      free_port(), free_port())
    cortex = Cortex(node_id="cortex", port=p_cortex,
                    sweep_interval=0.4, dead_timeout=1.2, drop_grace=2.5)
    cortex.start()
    base = f"http://127.0.0.1:{p_cortex}"

    tech = NervousNode(node_id="tech", kind="tech", level=3,
                       parent_url=base, port=p_tech, heartbeat_interval=0.4)
    tech.start()
    rnd = NervousNode(node_id="rnd", kind="rnd", level=4,
                      parent_url=f"http://127.0.0.1:{p_tech}", port=p_rnd,
                      heartbeat_interval=0.4)
    rnd.start()
    dev = NervousNode(node_id="dev", kind="dev", level=5,
                      parent_url=f"http://127.0.0.1:{p_rnd}", port=p_dev,
                      heartbeat_interval=0.4)
    dev.start()

    # ---- D01-D03: 四层注册 + 父子关系（B1） ----
    check("D01 四层注册完成（皮层拓扑 4 节点）",
          wait_until(lambda: cortex.topology.size() == 4),
          f"size={cortex.topology.size()}")
    dv = cortex.topology.get("dev")
    rv = cortex.topology.get("rnd")
    tv = cortex.topology.get("tech")
    check("D02 深层父子关系不被坍缩：dev.parent=rnd", dv is not None and dv.parent_id == "rnd",
          f"dev.parent={dv.parent_id if dv else None}（期望 rnd）")
    check("D03 中间父链正确：rnd.parent=tech, tech.parent=cortex",
          rv is not None and rv.parent_id == "tech"
          and tv is not None and tv.parent_id == "cortex",
          f"rnd.parent={rv.parent_id if rv else None}, tech.parent={tv.parent_id if tv else None}")

    # ---- D04: 祖先链无重复（B6） ----
    check("D04 dev 祖先链无重复且完整", dev._ancestors == ["rnd", "tech", "cortex"],
          f"dev._ancestors={dev._ancestors}")

    # ---- D05: 深层上行汇聚（B2） ----
    dev.report_event("deep_event", {"from": "dev"})
    dev.report_request("启动新任务", reason="深树请求")
    check("D05a dev 事件到达皮层",
          wait_until(lambda: any(r.get("from") == "dev" and r.get("type") == "report.event"
                                 for r in cortex.get_reports())))
    check("D05b dev 请求到达皮层",
          wait_until(lambda: any(r.get("from") == "dev" and r.get("type") == "report.request"
                                 for r in cortex.get_reports())))
    check("D05c dev 心跳持续汇聚到皮层（非全盲）",
          wait_until(lambda: sum(1 for r in cortex.get_reports()
                                 if r.get("from") == "dev"
                                 and r.get("type") == "report.heartbeat") >= 2))
    check("D05d 中间层也汇聚（rnd 心跳在皮层可见）",
          any(r.get("from") == "rnd" and r.get("type") == "report.heartbeat"
              for r in cortex.get_reports()))

    # ---- D08: 权限纯时间序（B4） ----
    # 1) 先 grant node_id，后 revoke node_kind -> 类型级收紧必须生效
    cortex.perm_grant("node_id", "dev", "file_read")
    cortex.perm_revoke("node_kind", "dev", "file_read")
    check("D08a 先特批后类型级收紧 -> 收紧生效",
          wait_until(lambda: dev.permissions.check("file_read") is False))
    # 2) 先 revoke node_kind，后 grant node_id -> 最新特批生效
    cortex.perm_revoke("node_kind", "dev", "file_write")
    cortex.perm_grant("node_id", "dev", "file_write")
    check("D08b 先类型收紧后精确特批 -> 特批生效",
          wait_until(lambda: dev.permissions.check("file_write") is True))
    # 3) set 整体收紧 -> 后写覆盖
    cortex.perm_set("node_kind", "dev", {"process_exec": False})
    check("D08c 整体收紧生效",
          wait_until(lambda: dev.permissions.check("process_exec") is False))
    cortex.perm_grant("node_id", "dev", "process_exec")
    check("D08d 特批恢复",
          wait_until(lambda: dev.permissions.check("process_exec") is True))

    # ---- D09: 心跳状态自定义位（B7） ----
    r = dev.report_heartbeat(status="busy", task_count=3)
    check("D09a 自定义心跳上报成功", r.get("ok"), str(r))
    check("D09b 皮层收到自定义 status/extra 字段",
          wait_until(lambda: any(
              (p.get("payload") or {}).get("status") == "busy"
              and (p.get("payload") or {}).get("task_count") == 3
              for p in cortex.get_reports())))

    # ---- D10: 注册/注销自动广播（B8） ----
    check("D10 注册触发皮层自动拓扑广播（防抖后）",
          wait_until(lambda: any("拓扑广播完成" in a.get("msg", "")
                                 for a in cortex.get_audit()), timeout=8.0))

    # ---- D06: 中间层正常退出 -> 救树（B3 deregister 路径） ----
    tech.stop()
    check("D06a tech 注销并从皮层拓扑移除",
          wait_until(lambda: cortex.topology.get("tech") is None))
    rnd_after = cortex.topology.get("rnd")
    dev_after = cortex.topology.get("dev")
    check("D06b 活子 rnd 被救树提升挂皮层",
          rnd_after is not None and rnd_after.parent_id == "cortex",
          f"rnd.parent={rnd_after.parent_id if rnd_after else None}")
    check("D06c dev 保持挂 rnd（不陪葬不悬空）",
          dev_after is not None and dev_after.parent_id == "rnd",
          f"dev.parent={dev_after.parent_id if dev_after else None}")
    check("D06d 被救节点心跳续传（rnd 直连皮层）",
          wait_until(lambda: any(r.get("from") == "rnd"
                                 and r.get("type") == "report.heartbeat"
                                 for r in cortex.get_reports())))
    check("D06e 皮层仍可探活整支", cortex.ping("rnd").get("ok")
          and cortex.ping("dev").get("ok"))

    # ---- D07: 中间层崩溃（无 deregister）-> 清扫 + 救树（B3 crash / B5） ----
    # 新增一支：cortex -> tech2 -> rnd2 -> dev2
    p_tech2, p_rnd2, p_dev2 = free_port(), free_port(), free_port()
    tech2 = NervousNode(node_id="tech2", kind="tech", level=3,
                        parent_url=base, port=p_tech2, heartbeat_interval=0.4)
    tech2.start()
    rnd2 = NervousNode(node_id="rnd2", kind="rnd", level=4,
                       parent_url=f"http://127.0.0.1:{p_tech2}", port=p_rnd2,
                       heartbeat_interval=0.4)
    rnd2.start()
    dev2 = NervousNode(node_id="dev2", kind="dev", level=5,
                       parent_url=f"http://127.0.0.1:{p_rnd2}", port=p_dev2,
                       heartbeat_interval=0.4)
    dev2.start()
    check("D07a 第二支注册完成",
          wait_until(lambda: cortex.topology.get("dev2") is not None
                     and cortex.topology.get("dev2").parent_id == "rnd2"))
    crash(tech2)  # 模拟进程崩溃：不发 deregister
    check("D07b 皮层清扫识别 tech2 失联并救树（rnd2 提升挂皮层）",
          wait_until(lambda: cortex.topology.get("tech2") is None
                     and (cortex.topology.get("rnd2") or {}).parent_id == "cortex",
                     timeout=15.0))
    check("D07c dev2 仍挂 rnd2 存活",
          (cortex.topology.get("dev2") or {}).parent_id == "rnd2")
    check("D07d 被救 rnd2 心跳恢复上报皮层",
          wait_until(lambda: any(r.get("from") == "rnd2"
                                 and r.get("type") == "report.heartbeat"
                                 for r in cortex.get_reports()), timeout=10.0))
    check("D07e 皮层探活被救整支", cortex.ping("rnd2").get("ok")
          and cortex.ping("dev2").get("ok"))

    # ---- D11: 心跳被拒 -> 自动重新注册（父/皮层视图重建后自愈） ----
    cortex.topology.unregister("dev")  # 模拟皮层视图异常丢失（竞争/误删）
    check("D11a 皮层拓扑已移除 dev（构造失忆场景）",
          cortex.topology.get("dev") is None)
    check("D11b dev 心跳被拒后自动重新注册（自愈重挂）",
          wait_until(lambda: cortex.topology.get("dev") is not None, timeout=10.0))
    check("D11c 重挂后皮层可探活 dev", cortex.ping("dev").get("ok"))

    # ---- D12: 真死节点（无子）由清扫收敛注销（B5 闭环） ----
    z = NervousNode(node_id="zombie", kind="node", level=3,
                    parent_url=base, port=free_port(), heartbeat_interval=0.4)
    z.start()
    check("D12a zombie 注册完成",
          wait_until(lambda: cortex.topology.get("zombie") is not None))
    crash(z)  # 崩溃且无子可救 -> 清扫应注销
    check("D12b 真死节点被清扫收敛注销",
          wait_until(lambda: cortex.topology.get("zombie") is None, timeout=15.0))

    # ---- D13: 皮层清扫后中间层本地缓存收敛（缺口 A） ----
    # 叶子 probe-x 直挂中间层 rnd。强杀（无 deregister）后皮层清扫注销并
    # 广播快照，rnd 本地拓扑与心跳 descendants 必须同步收敛，不得残留
    # stale 节点（修复前：sync 只增不删，rnd 心跳持续携带 probe-x 150s+）。
    p_probe = free_port()
    probe = NervousNode(node_id="probe-x", kind="node", level=5,
                        parent_url=f"http://127.0.0.1:{p_rnd}", port=p_probe,
                        heartbeat_interval=0.4)
    probe.start()
    check("D13a probe-x 注册完成（皮层 + 中间层 rnd 双视图可见）",
          wait_until(lambda: cortex.topology.get("probe-x") is not None
                     and rnd.topology.get("probe-x") is not None))
    check("D13b rnd 心跳 descendants 基线含 probe-x",
          wait_until(lambda: "probe-x"
                     in rnd.topology.subtree("rnd")))
    crash(probe)  # 模拟强杀：不发 deregister
    check("D13c 皮层清扫收敛注销 probe-x",
          wait_until(lambda: cortex.topology.get("probe-x") is None,
                     timeout=20.0))
    check("D13d 中间层 rnd 本地拓扑同步剪枝（probe-x 被移除）",
          wait_until(lambda: rnd.topology.get("probe-x") is None,
                     timeout=15.0))
    check("D13e rnd 心跳 descendants 不再含 probe-x",
          wait_until(lambda: "probe-x"
                     not in rnd.topology.subtree("rnd"), timeout=8.0))
    check("D13f rnd 子树视图与皮层一致（同 id 集合）",
          set(rnd.topology.subtree("rnd")) == set(cortex.topology.subtree("rnd")),
          f"rnd={rnd.topology.subtree('rnd')} cortex={cortex.topology.subtree('rnd')}")

    # ---- 清理 ----
    for n in (probe, z, dev2, rnd2, dev, rnd, tech):
        try:
            n.stop()
        except Exception:
            pass
    cortex.stop()
    time.sleep(0.4)

    print("=" * 64)
    print(f"深树回归测试结束：{PASS} 通过，{FAIL} 失败")
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
