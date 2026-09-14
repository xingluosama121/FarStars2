# -*- coding: utf-8 -*-
"""
nervous_bus.test_cnb_slots — R-023 / R-024（2026-09-11 修订）/ R-025 验收

覆盖需求点：

  R-024 通用槽位（修订版：norpagent 完整实例 = 可插入 CNB 节点的模块）
        - 每节点 ≤64 槽位；容量满第 65 个拒绝；
        - 槽位号唯一、模块协议校验、动作名冲突拒绝、on_mount 失败事务不提交；
        - model / tools / plugins / 自定义模块均可槽位化挂载（总线 slot_mount）；
        - 完整 norpagent 实例包装为 NorpAgentModule：describe / actions /
          heartbeat 全白盒，挂到节点后内核动作面经槽位路由可达（source="slot"）；
        - CnbAdapter.bind_actions 自动把实例挂入默认槽位 "norpagent"；
        - slot_list / slot_describe / slot_mount / slot_unmount 总线动作；
        - 槽位挂载/卸载入节点审计。

  R-023 默认不携带 CNB
        - 默认 env/配置下 enabled=False、setup_cnb 静默返回（零挂载）；
        - 显式 {"cnb": True, ...} / env 才是启用通道。

  R-025 端口手动配置、缺省报错（2026-09-12 反馈轮修订错误语义）
        - read_env_config(strict=True) 缺端口抛 CnbConfigError；
        - validate_cnb_config 缺端口/缺节点标识抛错（直接调用的严格校验面）；
        - np(cnb={"cnb": True}) 缺端口：显式报错但不阻塞启动——宿主正常
          启动、神经树不加载（cnb_status=config-error、cnb_error 可查）；
        - cortex CLI --port required（子进程：缺参退出码非 0，提示 required）。

运行：python -m nervous_bus.test_cnb_slots（需 PYTHONPATH=src）
"""

import os
import socket
import subprocess
import sys
import time
import traceback
from types import SimpleNamespace
from typing import Any, Dict, List

from norpagent.cnb.engine import (
    CnbAdapter,
    CnbConfigError,
    apply_explicit_config,
    read_env_config,
    setup_cnb,
    validate_cnb_config,
)
from norpagent.cnb.node import NervousNode
from norpagent.cnb.slots import (
    KIND_NORPAGENT,
    MAX_SLOTS,
    GenericModule,
    MountableModule,
    NorpAgentModule,
    SlotError,
)

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


def free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def fresh_node(node_id: str = "t-node") -> NervousNode:
    return NervousNode(node_id=node_id, kind="test", level=3,
                       parent_url=None, port=free_port())


class _RecordingModule(MountableModule):
    """测试模块：记录挂载/卸载回调 + 提供动作 + 心跳贡献。"""

    def __init__(self, kind="test-module", label="", actions=None, fail_mount=False):
        super().__init__(label=label or kind)
        self.kind = kind
        self._actions = dict(actions or {})
        self.mounted = 0
        self.unmounted = 0
        self.fail_mount = fail_mount

    def on_mount(self, node):
        self.mounted += 1
        if self.fail_mount:
            raise RuntimeError("mount refused by module")

    def on_unmount(self, node):
        self.unmounted += 1

    def actions(self):
        return dict(self._actions)

    def heartbeat(self):
        return {"probe": self.kind}


class _FakeEngine:
    """最小引擎面（NorpAgentModule / CnbAdapter 动作处理器所需）。"""

    class _State:
        value = "running"

    def __init__(self):
        self.state = _FakeEngine._State()
        self.preset = SimpleNamespace(name="minimal")

    def active_tasks(self):
        return []

    def is_running(self):
        return True

    def should_stop(self):
        return False


def main() -> int:
    # ══════════════════════════════════════════════════════
    # A. 槽位核心（无网络）
    # ══════════════════════════════════════════════════════
    print("── A. 槽位核心 ──")
    check("A01 MAX_SLOTS == 64", MAX_SLOTS == 64, str(MAX_SLOTS))
    node = fresh_node()
    check("A02 fresh node empty", node.slots.count() == 0
          and node.slots.free() == MAX_SLOTS)

    m1 = _RecordingModule(kind="model", label="slot model")
    info = node.mount_module("m1", m1)
    check("A03 mount ok", node.slots.count() == 1 and info["slot_id"] == "m1")
    check("A04 mount callback", m1.mounted == 1)
    check("A05 describe carries kind/label", info["kind"] == "model"
          and info["label"] == "slot model")

    # 重复槽位号
    try:
        node.mount_module("m1", _RecordingModule(kind="x"))
        check("A06 duplicate slot id rejected", False)
    except SlotError:
        check("A06 duplicate slot id rejected", True)

    # 非法模块（缺协议）
    try:
        node.mount_module("bad", object())
        check("A07 invalid module rejected", False)
    except SlotError:
        check("A07 invalid module rejected", True)

    # 动作冲突
    node.mount_module("m2", _RecordingModule(
        kind="tools", actions={"probe_op": lambda p: {"ok": True}}))
    try:
        node.mount_module("m3", _RecordingModule(
            kind="plugins", actions={"probe_op": lambda p: {"ok": True}}))
        check("A08 action conflict rejected", False)
    except SlotError:
        check("A08 action conflict rejected", True)

    # on_mount 失败 -> 事务不提交
    try:
        node.mount_module("m4", _RecordingModule(kind="bad", fail_mount=True))
        check("A09 on_mount failure aborts", False)
    except RuntimeError:
        check("A09 on_mount failure aborts", node.slots.get("m4") is None)

    # 槽位动作面
    check("A10 slot action visible", node.has_action("probe_op"))
    check("A11 slot action in list", "probe_op" in node.list_actions())
    resp = node._exec_downlink("cmd.exec", {"action": "probe_op", "args": {}})
    check("A12 exec routes to slot", resp.get("ok") is True
          and resp.get("source") == "slot", str(resp))

    # slot_list / slot_describe 内置动作
    resp = node._exec_downlink("cmd.exec", {"action": "slot_list", "args": {}})
    d = resp.get("detail") or {}
    check("A13 slot_list", resp.get("ok") and d.get("count") == 2
          and d.get("max_slots") == 64 and d.get("free") == 62, str(resp))
    resp = node._exec_downlink("cmd.exec", {"action": "slot_describe",
                                            "args": {"slot_id": "m1"}})
    check("A14 slot_describe single", resp.get("ok")
          and (resp.get("detail") or {}).get("slot", {}).get("kind") == "model")

    # 总线槽位挂载（model / tools / plugins 均可）
    for idx, kind in enumerate(("model", "tools", "plugins")):
        sid = f"bus-{kind}"
        resp = node._exec_downlink("cmd.exec", {
            "action": "slot_mount",
            "args": {"slot_id": sid,
                     "module": {"kind": kind, "label": f"{kind} via bus",
                                "payload": {"name": f"{kind}-{idx}"}}}})
        check(f"A15 bus mount {kind}", resp.get("ok") is True
              and (resp.get("detail") or {}).get("slot", {}).get("kind") == kind,
              str(resp))
    # 总线不可挂 norpagent 实例（需活引擎，如实拒绝）
    resp = node._exec_downlink("cmd.exec", {
        "action": "slot_mount",
        "args": {"slot_id": "engine-via-bus",
                 "module": {"kind": KIND_NORPAGENT}}})
    check("A16 bus cannot build engine module",
          (resp.get("detail") or {}).get("ok") is False
          and "norpagent-instance" in str(resp), str(resp)[:200])

    # 总线卸载 + 动作面收回
    resp = node._exec_downlink("cmd.exec", {
        "action": "slot_unmount", "args": {"slot_id": "m2"}})
    check("A17 bus unmount", resp.get("ok") is True)
    check("A18 action face retracted", not node.has_action("probe_op"))
    resp = node._exec_downlink("cmd.exec", {"action": "probe_op", "args": {}})
    check("A19 unmounted action unknown", resp.get("ok") is False)

    # 容量：填满 64
    cap_node = fresh_node("cap-node")
    for i in range(MAX_SLOTS - 5):
        cap_node.mount_module(f"c{i}", _RecordingModule(kind="fill"))
    check("A20 fill to 61", cap_node.slots.count() == MAX_SLOTS - 5)
    for i in range(5):
        cap_node.mount_module(f"x{i}", _RecordingModule(kind="fill"))
    check("A21 fill to 64", cap_node.slots.count() == MAX_SLOTS
          and cap_node.slots.free() == 0)
    try:
        cap_node.mount_module("overflow", _RecordingModule(kind="fill"))
        check("A22 65th rejected", False)
    except SlotError as exc:
        check("A22 65th rejected", "capacity" in str(exc), str(exc))

    # 卸载回调 + 释放后重挂
    victim = cap_node.slots.get("c0").module
    cap_node.unmount_module("c0")
    check("A23 unmount callback", victim.unmounted == 1
          and cap_node.slots.free() == 1)
    cap_node.mount_module("c0", _RecordingModule(kind="fill"))
    check("A24 remount after free", cap_node.slots.count() == MAX_SLOTS)

    # 审计留痕
    audits = [a.get("msg", "") for a in node.get_audit()]
    check("A25 mount/unmount audited",
          any("slot mounted" in m for m in audits)
          and any("slot unmounted" in m for m in audits))

    # ══════════════════════════════════════════════════════
    # B. 完整 norpagent 实例模块（国王 2026-09-11 修订）
    # ══════════════════════════════════════════════════════
    print("── B. norpagent 完整实例模块 ──")
    eng = _FakeEngine()
    module = NorpAgentModule(eng)
    check("B01 kind is norpagent-instance", module.kind == KIND_NORPAGENT)
    desc = module.describe()
    check("B02 describe carries engine state", desc.get("engine_state") == "running"
          and desc.get("preset") == "minimal"
          and isinstance(desc.get("actions"), list) and desc["actions"],
          str(desc)[:200])
    acts = module.actions()
    check("B03 instance actions exported", "engine_state" in acts
          and "run_task" in acts and len(acts) >= 15, str(sorted(acts))[:200])
    check("B04 heartbeat contribution", (module.heartbeat() or {}).get(
        "engine_state") == "running")

    n2 = fresh_node("engine-node")
    n2.mount_module("norpagent", module)
    check("B05 instance mounted as slot module",
          n2.describe_slots()[0]["kind"] == KIND_NORPAGENT)
    check("B06 actions reachable via slot face",
          n2.has_action("engine_state") and "engine_state" in n2.list_actions())
    resp = n2._exec_downlink("cmd.exec", {"action": "engine_state", "args": {}})
    check("B07 slot-source exec", resp.get("ok") is True
          and resp.get("source") == "slot"
          and (resp.get("detail") or {}).get("state") == "running", str(resp))

    # 同一节点挂两个实例模块 -> 动作冲突拒绝（一节点一实例动作面）
    try:
        n2.mount_module("norpagent-2", NorpAgentModule(_FakeEngine()))
        check("B08 second instance module rejected", False)
    except SlotError as exc:
        check("B08 second instance module rejected",
              "conflict" in str(exc), str(exc))

    # 卸载后动作面收回
    n2.unmount_module("norpagent")
    check("B09 unmount retracts actions",
          not n2.has_action("engine_state")
          and n2.slots.count() == 0)

    # CnbAdapter 自动挂载：实例成为默认槽位模块
    n3 = fresh_node("adapter-node")
    adapter = CnbAdapter(_FakeEngine(), n3, {})
    check("B10 adapter binds actions", n3.has_action("run_task")
          and n3.has_action("engine_state"))
    check("B11 adapter mounts instance module", adapter.slot_mounted
          and n3.slots.get("norpagent") is not None
          and n3.slots.get("norpagent").module.kind == KIND_NORPAGENT)
    resp = n3._exec_downlink("cmd.exec", {"action": "engine_state", "args": {}})
    check("B12 directly-registered action keeps kernel source",
          resp.get("ok") is True and resp.get("source") == "kernel")
    resp = n3._exec_downlink("cmd.exec", {"action": "slot_list", "args": {}})
    check("B13 adapter node slot_list counts instance",
          (resp.get("detail") or {}).get("count") == 1, str(resp))

    # ══════════════════════════════════════════════════════
    # C. R-023 默认不携带 + R-025 端口缺失抛错
    # ══════════════════════════════════════════════════════
    print("── C. R-023 / R-025 ──")
    _saved = {k: os.environ.pop(k, None) for k in (
        "NORP_CNB_NODE", "NORP_CNB_PORT", "NORP_CNB_PARENT",
        "NORP_CNB_MANAGED", "NORP_CNB_KIND", "NORP_CNB_LEVEL")}
    try:
        cfg = read_env_config()
        check("C01 default off", cfg["enabled"] is False
              and cfg["port_configured"] is False)

        eng0 = SimpleNamespace()
        setup_cnb(eng0)  # default: silent return
        check("C02 default setup no-op", getattr(eng0, "_cnb", None) is None
              and not getattr(eng0, "_cnb_managed", False))

        # 显式关闭
        cfg = validate_cnb_config(False)
        check("C03 explicit off", cfg["enabled"] is False)

        # 缺端口：strict 读抛错（清洁 env：只设 NODE，不设 PORT）
        os.environ.pop("NORP_CNB_PORT", None)
        os.environ["NORP_CNB_NODE"] = "env-atom"
        try:
            read_env_config(strict=True)
            check("C04 strict missing port raises", False)
        except CnbConfigError as exc:
            check("C04 strict missing port raises",
                  "端口" in str(exc) or "port" in str(exc), str(exc)[:120])

        # env 启用 + 缺端口 -> setup_cnb 抛错（不静默）
        try:
            setup_cnb(SimpleNamespace())
            check("C05 env missing port raises", False)
        except CnbConfigError:
            check("C05 env missing port raises", True)

        # env 启用 + 端口 + managed -> 跳过（上层自装配）
        os.environ["NORP_CNB_PORT"] = "17901"
        os.environ["NORP_CNB_MANAGED"] = "1"
        eng1 = SimpleNamespace()
        setup_cnb(eng1)
        check("C06 managed skip", getattr(eng1, "_cnb_managed", False) is True)
        del os.environ["NORP_CNB_MANAGED"]

        # env 启用 + 端口（非 managed）—— 不实际挂载（无父可连）：
        # 仅验证配置合并通过、不会因缺端口报错。
        cfg = validate_cnb_config(None)
        check("C07 env enabled + port validates", cfg["enabled"] is True
              and cfg["port_configured"] is True and cfg["port"] == 17901)

        # 显式 dict 缺端口（清掉 env 端口）-> 抛错
        os.environ.pop("NORP_CNB_PORT", None)
        try:
            validate_cnb_config({"cnb": True, "node_id": "x"})
            check("C08 explicit missing port raises", False)
        except CnbConfigError:
            check("C08 explicit missing port raises", True)

        # 显式 dict 完整 -> 通过
        cfg = validate_cnb_config({"cnb": True, "node_id": "x", "port": 17902})
        check("C09 explicit complete", cfg["enabled"] and cfg["port_configured"]
              and cfg["port"] == 17902)

        # np(cnb=...) 缺端口（清洁 env：无端口可继承）——2026-09-12 反馈轮
        # 错误语义：显式报错但不阻塞主线程启动；宿主正常启动、神经树不加载
        # （cnb_status=config-error、cnb_error 可查、无任何挂载）。
        import norpagent as np

        eng = np(preset="minimal",
                 frontend="norpagent.frontends.headless:HeadlessFrontend",
                 cnb={"cnb": True, "node_id": "preflight"})
        try:
            cfg_err = getattr(eng, "cnb_error", None) or ""
            check("C10 np(cnb) missing port non-blocking",
                  eng.is_running()
                  and eng.cnb_status == "config-error"
                  and ("端口" in cfg_err or "port" in cfg_err)
                  and eng.cnb is None,
                  f"status={eng.cnb_status} err={cfg_err[:120]}")
        finally:
            try:
                np.shutdown()
            except Exception:  # noqa: BLE001
                pass

        # cortex CLI --port required（子进程）
        env = dict(os.environ)
        env["PYTHONPATH"] = os.path.abspath("src")
        env["PYTHONUTF8"] = "1"
        env["PYTHONIOENCODING"] = "utf-8"
        proc = subprocess.run(
            [sys.executable, "-m", "norpagent.cnb.cli", "cortex"],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30, env=env)
        out = (proc.stdout or "") + (proc.stderr or "")
        check("C11 cortex CLI requires --port",
              proc.returncode != 0 and ("--port" in out and "required" in out),
              f"rc={proc.returncode} out={out[-160:]}")
    finally:
        for k, v in _saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    print()
    print(f"PASS={PASS} FAIL={FAIL}")
    if FAILURES:
        print("failures:")
        for f in FAILURES:
            print("  -", f)
    return 1 if FAIL else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        traceback.print_exc()
        sys.exit(2)
