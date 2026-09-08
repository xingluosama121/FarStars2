# -*- coding: utf-8 -*-
"""
nervous_bus.test_e2e — 端到端验证（真实多进程）

通过 norpagent 主入口 main.py 启动：
  1 个大脑皮层进程（--norp-cortex）
  2 个节点进程（--norp-node，树状拓扑链：皮层 -> bot -> pilot）

再用 nervous_bus.cli 命令（皮层控制端点）验证：拓扑、探活、执行、
权限控制、越权拦截、进程清理。

运行：python -m nervous_bus.test_e2e
"""

import json
import subprocess
import sys
import time
import urllib.request
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # 工作区根
# v1.0.2 起 nervous_bus 随包迁入 src/：__file__ 上溯两级落在 src/（无 main.py）。
# 向上爬升直到找到 main.py，使 python -m nervous_bus.test_e2e 在仓库任意布局下均可用。
while not os.path.exists(os.path.join(ROOT, "main.py")):
    parent = os.path.dirname(ROOT)
    if parent == ROOT:
        break
    ROOT = parent
PY = sys.executable

PASS = 0
FAIL = 0
FAILURES = []


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  [PASS] {name}")
    else:
        FAIL += 1
        FAILURES.append(f"{name}: {detail}")
        print(f"  [FAIL] {name}  <- {detail}")


def http_json(url, payload=None):
    if payload is None:
        with urllib.request.urlopen(url, timeout=10) as r:
            return json.loads(r.read().decode("utf-8"))
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url, data=data,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST")
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read().decode("utf-8"))


def wait_health(url, timeout=15):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            if http_json(url + "/cnb/health").get("ok"):
                return True
        except Exception:
            pass
        time.sleep(0.3)
    return False


def run_cli(*args, timeout=20):
    """运行 nervous_bus.cli 子命令，返回 (returncode, stdout)。"""
    p = subprocess.run([PY, "-m", "nervous_bus.cli", *args],
                       capture_output=True, text=True, timeout=timeout,
                       cwd=ROOT, encoding="utf-8", errors="replace")
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def main():
    global PASS, FAIL
    print("=" * 64)
    print("CNB 端到端测试（真实多进程，经 main.py 入口）")
    print("=" * 64)

    procs = []

    # 1. 启动皮层
    cortex = subprocess.Popen(
        [PY, "main.py", "--norp-cortex", "--port", "17900"],
        cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    procs.append(cortex)
    check("E01 皮层进程启动",
          wait_health("http://127.0.0.1:17900"))

    # 2. 启动两级节点（树状链：皮层 -> bot -> pilot）
    bot = subprocess.Popen(
        [PY, "main.py", "--norp-node", "--id", "norpbot-e2e", "--kind", "bot",
         "--parent", "http://127.0.0.1:17900", "--port", "17901", "--level", "3"],
        cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    procs.append(bot)
    pilot = subprocess.Popen(
        [PY, "main.py", "--norp-node", "--id", "norpilot-e2e", "--kind", "pilot",
         "--parent", "http://127.0.0.1:17901", "--port", "17902", "--level", "4"],
        cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    procs.append(pilot)

    time.sleep(2.5)  # 等注册与首轮心跳

    # 3. 拓扑
    rc, out = run_cli("topo", "--root", "http://127.0.0.1:17900")
    check("E02 CLI 查看拓扑",
          rc == 0 and "norpbot-e2e" in out and "norpilot-e2e" in out, out)
    check("E03 拓扑为树状链（bot 挂在皮层下，pilot 挂在 bot 下）",
          "[3] norpbot-e2e" in out and "[4] norpilot-e2e" in out, out)

    # 4. 探活
    rc, out = run_cli("ping", "--root", "http://127.0.0.1:17900",
                      "--node", "norpbot-e2e")
    check("E04 CLI 探活 bot", rc == 0 and '"ok": true' in out, out)
    rc, out = run_cli("ping", "--root", "http://127.0.0.1:17900",
                      "--node", "norpilot-e2e")
    check("E05 CLI 探活深层 pilot", rc == 0 and '"ok": true' in out, out)

    # 5. 执行指令
    rc, out = run_cli("exec", "--root", "http://127.0.0.1:17900",
                      "--node", "norpbot-e2e", "--action", "run_task")
    check("E06 CLI 下发执行指令", rc == 0 and '"ok": true' in out, out)

    # 6. 权限控制：撤销 bot 的 process_shell 后执行被拒
    rc, out = run_cli("perm", "--root", "http://127.0.0.1:17900",
                      "--revoke", "--target-type", "node_id",
                      "--target", "norpbot-e2e", "--perm", "process_shell")
    check("E07 CLI 撤销权限", rc == 0 and '"ok": true' in out, out)
    rc, out = run_cli("exec", "--root", "http://127.0.0.1:17900",
                      "--node", "norpbot-e2e", "--action", "run_shell",
                      "--perm", "process_shell")
    check("E08 权限收紧后执行被拒",
          rc == 0 and "permission denied" in out, out)

    # 7. 按原子类型通配授权
    rc, out = run_cli("perm", "--root", "http://127.0.0.1:17900",
                      "--grant", "--target-type", "node_kind",
                      "--target", "bot", "--perm", "file_write")
    check("E09 CLI 按原子类型授权", rc == 0 and '"ok": true' in out, out)

    # 8. 越权：低等级节点直接向皮层发下行指令 -> 拒绝
    from nervous_bus import protocol
    from nervous_bus.bus import BusClient
    env = protocol.make_envelope(
        protocol.DIR_DOWNLINK,
        {"node_id": "norpbot-e2e", "level": 3, "kind": "bot"},
        "cortex", "cmd.ping", {})
    r = BusClient(timeout=10).post_msg("http://127.0.0.1:17900", env)
    check("E10 低等级向皮层发指令被拒",
          (not r.get("ok")) and "not my ancestor" in str(r.get("error")), str(r))

    # 9. 平级节点互发指令 -> 拒绝（先起一个同级 memory 节点）
    mem = subprocess.Popen(
        [PY, "main.py", "--norp-node", "--id", "norpmemory-e2e", "--kind", "memory",
         "--parent", "http://127.0.0.1:17900", "--port", "17903", "--level", "3"],
        cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    procs.append(mem)
    time.sleep(1.5)
    env = protocol.make_envelope(
        protocol.DIR_DOWNLINK,
        {"node_id": "norpbot-e2e", "level": 3, "kind": "bot"},
        "norpmemory-e2e", "cmd.ping", {})
    r = BusClient(timeout=10).post_msg("http://127.0.0.1:17903", env)
    check("E11 平级节点互发指令被拒",
          (not r.get("ok")) and "not my ancestor" in str(r.get("error")), str(r))

    # 10. 上报汇聚：皮层能看到心跳
    rc, out = run_cli("reports", "--root", "http://127.0.0.1:17900", "--n", "50")
    check("E12 皮层上报记录含心跳",
          rc == 0 and "report.heartbeat" in out and "norpbot-e2e" in out, out)

    # 11. 拓扑广播
    rc, out = run_cli("sync", "--root", "http://127.0.0.1:17900")
    check("E13 皮层拓扑广播", rc == 0 and '"ok": true' in out, out)

    # 12. 清理
    for p in procs:
        try:
            p.terminate()
        except Exception:
            pass
    time.sleep(1.0)
    for p in procs:
        try:
            p.kill()
        except Exception:
            pass

    print("=" * 64)
    print(f"端到端测试结束：{PASS} 通过，{FAIL} 失败")
    for f in FAILURES:
        print(f"  - {f}")
    print("=" * 64)
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
