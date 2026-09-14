# -*- coding: utf-8 -*-
"""
norpagent.cnb.demo — 快速演示：1 个中枢 + 树状三级节点（同进程模拟）

演示神经树：
  cortex (level 0)
   ├── norpbot-01 (level 3, bot)
   │    └── norpilot-01 (level 4, pilot)   <- 树状拓扑链
   └── norpmemory-01 (level 3, memory)

展示：注册逐级上报、中枢全量拓扑、探活、执行指令、权限控制、
越权拦截（低等级向中枢sends command被拒、平级互发被拒、smuggles a control field upstream被拒）。

运行：python -m norpagent.cnb.demo
"""

import time

from .bus import BusClient
from .cortex import Cortex
from .node import NervousNode
from . import protocol


def main():
    print("=" * 60)
    print("Central Nervous Bus (CNB) quick demo")
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

    print("\n[1] Cortex full topology (registrations converge up the tree):")
    print(cortex.topology.render_ascii())

    print("\n[2] Cortex probes liveness of any atom at any level:")
    print("  ping norpbot-01    ->", cortex.ping("norpbot-01").get("ok"))
    print("  ping norpilot-01   ->", cortex.ping("norpilot-01").get("ok"))

    print("\n[3] Cortex issues an execution command (lower levels obey unconditionally):")
    print("  exec norpbot-01    ->", cortex.exec_cmd("norpbot-01", "run_task"))
    print("  exec norpilot-01   ->", cortex.exec_cmd("norpilot-01", "fly"))

    print("\n[4] Cortex controls permissions of any atom at any level:")
    cortex.perm_revoke("node_id", "norpbot-01", "process_shell")
    print("  revoke norpbot-01 process_shell")
    print("  exec norpbot-01 run_shell (perm=process_shell) ->",
          cortex.exec_cmd("norpbot-01", "run_shell", perm="process_shell"))
    cortex.perm_grant("node_id", "norpbot-01", "process_shell")
    print("  grant norpbot-01 process_shell(restore)")
    cortex.perm_set("node_kind", "bot", {"file_delete": False})
    print("  set node_kind bot file_delete=false ->",
          "bot.file_delete =", bot.permissions.check("file_delete"))

    print("\n[5] Privilege escalation blocked (lower levels cannot control upper / peers cannot control each other):")
    client = BusClient(timeout=8)
    env = protocol.make_envelope(
        protocol.DIR_DOWNLINK,
        {"node_id": "norpbot-01", "level": 3, "kind": "bot"},
        "cortex", "cmd.ping", {})
    r = client.post_msg("http://127.0.0.1:17800", env)
    print("  bot -> cortex sends command    ->", r)
    env = protocol.make_envelope(
        protocol.DIR_DOWNLINK,
        {"node_id": "norpbot-01", "level": 3, "kind": "bot"},
        "norpmemory-01", "cmd.ping", {})
    r = client.post_msg("http://127.0.0.1:17803", env)
    print("  bot -> memory peer sends command ->", r)
    env = protocol.make_envelope(
        protocol.DIR_UPLINK,
        {"node_id": "norpbot-01", "level": 3, "kind": "bot"},
        "parent", "report.heartbeat",
        {"status": "running", "cmd.exec": {"action": "x"}})
    r = client.post_msg("http://127.0.0.1:17800", env)
    print("  bot smuggles a control field upstream    ->", r)

    pilot.stop()
    bot.stop()
    mem.stop()
    cortex.stop()
    print("\ndemo finished (all nodes are offline)")


if __name__ == "__main__":
    main()
