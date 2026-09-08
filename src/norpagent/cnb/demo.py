# -*- coding: utf-8 -*-
"""
norpagent.cnb.demo — 快速演示：1 个皮层 + 树状三级节点（同进程模拟）

演示神经树：
  cortex (level 0)
   ├── norpbot-01 (level 3, bot)
   │    └── norpilot-01 (level 4, pilot)   <- 树状拓扑链
   └── norpmemory-01 (level 3, memory)

展示：注册逐级上报、皮层全量拓扑、探活、执行指令、权限控制、
越权拦截（低等级向皮层发指令被拒、平级互发被拒、上行夹带控制字段被拒）。

运行：python -m norpagent.cnb.demo
"""

import time

from .bus import BusClient
from .cortex import Cortex
from .node import NervousNode
from . import protocol


def main():
    print("=" * 60)
    print("中枢神经总线 CNB 快速演示")
    print("=" * 60)

    cortex = Cortex(node_id="cortex", port=17800)
    cortex.start()

    bot = NervousNode(node_id="norpbot-01", kind="bot", level=3,
                      parent_url="http://127.0.0.1:17800", port=17801,
                      heartbeat_interval=1.0)
    bot.on("exec", lambda p: {"echo": p.get("action"), "node": "norpbot-01"})
    bot.start()

    pilot = NervousNode(node_id="norpilot-01", kind="pilot", level=4,
                        parent_url="http://127.0.0.1:17801", port=17802,
                        heartbeat_interval=1.0)
    pilot.on("exec", lambda p: {"echo": p.get("action"), "node": "norpilot-01"})
    pilot.start()

    mem = NervousNode(node_id="norpmemory-01", kind="memory", level=3,
                      parent_url="http://127.0.0.1:17800", port=17803,
                      heartbeat_interval=1.0)
    mem.start()
    time.sleep(1.5)

    print("\n[1] 皮层全量拓扑（注册沿树逐级上报汇聚）：")
    print(cortex.topology.render_ascii())

    print("\n[2] 皮层探活任意层级任意原子：")
    print("  ping norpbot-01    ->", cortex.ping("norpbot-01").get("ok"))
    print("  ping norpilot-01   ->", cortex.ping("norpilot-01").get("ok"))

    print("\n[3] 皮层下发执行指令（低等级无条件服从）：")
    print("  exec norpbot-01    ->", cortex.exec_cmd("norpbot-01", "run_task"))
    print("  exec norpilot-01   ->", cortex.exec_cmd("norpilot-01", "fly"))

    print("\n[4] 皮层控制操作权限（任意层级任意单位原子）：")
    cortex.perm_revoke("node_id", "norpbot-01", "process_shell")
    print("  revoke norpbot-01 process_shell")
    print("  exec norpbot-01 run_shell (perm=process_shell) ->",
          cortex.exec_cmd("norpbot-01", "run_shell", perm="process_shell"))
    cortex.perm_grant("node_id", "norpbot-01", "process_shell")
    print("  grant norpbot-01 process_shell（恢复）")
    cortex.perm_set("node_kind", "bot", {"file_delete": False})
    print("  set node_kind bot file_delete=false ->",
          "bot.file_delete =", bot.permissions.check("file_delete"))

    print("\n[5] 越权拦截（低等级不可控制上层 / 同级不可互控）：")
    client = BusClient(timeout=8)
    env = protocol.make_envelope(
        protocol.DIR_DOWNLINK,
        {"node_id": "norpbot-01", "level": 3, "kind": "bot"},
        "cortex", "cmd.ping", {})
    r = client.post_msg("http://127.0.0.1:17800", env)
    print("  bot -> cortex 发指令    ->", r)
    env = protocol.make_envelope(
        protocol.DIR_DOWNLINK,
        {"node_id": "norpbot-01", "level": 3, "kind": "bot"},
        "norpmemory-01", "cmd.ping", {})
    r = client.post_msg("http://127.0.0.1:17803", env)
    print("  bot -> memory 平级发指令 ->", r)
    env = protocol.make_envelope(
        protocol.DIR_UPLINK,
        {"node_id": "norpbot-01", "level": 3, "kind": "bot"},
        "parent", "report.heartbeat",
        {"status": "running", "cmd.exec": {"action": "x"}})
    r = client.post_msg("http://127.0.0.1:17800", env)
    print("  bot 上行夹带控制字段    ->", r)

    pilot.stop()
    bot.stop()
    mem.stop()
    cortex.stop()
    print("\n演示结束（全部节点已下线）")


if __name__ == "__main__":
    main()
