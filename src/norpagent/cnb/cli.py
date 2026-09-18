# -*- coding: utf-8 -*-
"""
norpagent.cnb.cli — 中枢神经总线命令行入口

用法示例：

  1. 启动中枢（根节点，level 0）：
     python -m norpagent.cnb.cli cortex --port 17800 --repl

  2. 启动一个节点实例（原子，挂到中枢下）：
     python -m norpagent.cnb.cli node --id norpbot-01 --kind bot \
         --parent http://127.0.0.1:17800 --port 17801 --level 3

  3. 启动深一层节点（树状拓扑链：中枢 -> bot -> pilot）：
     python -m norpagent.cnb.cli node --id norpilot-01 --kind pilot \
         --parent http://127.0.0.1:17801 --port 17802 --level 4

  4. 查看拓扑：
     python -m norpagent.cnb.cli topo --root http://127.0.0.1:17800

  5. 中枢下发指令（探活 / 执行 / 停止）：
     python -m norpagent.cnb.cli ping  --root http://127.0.0.1:17800 --node norpbot-01
     python -m norpagent.cnb.cli exec  --root http://127.0.0.1:17800 --node norpbot-01 --action run_task
     python -m norpagent.cnb.cli stop  --root http://127.0.0.1:17800 --node norpbot-01

  6. 中枢控制任意层级任意原子的操作权限：
     python -m norpagent.cnb.cli perm --root http://127.0.0.1:17800 \
         --grant --target-type node_kind --target bot --perm file_write
     python -m norpagent.cnb.cli perm --root http://127.0.0.1:17800 \
         --revoke --target-type node_id --target norpbot-01 --perm process_shell
     python -m norpagent.cnb.cli perm --root http://127.0.0.1:17800 \
         --set --target-type node_kind --target bot \
         --allows '{"process_shell": false, "file_delete": false}'

  7. show reports received by the cortex：
     python -m norpagent.cnb.cli reports --root http://127.0.0.1:17800
"""

import argparse
import json
import os
import sys
import time
from typing import Any, Callable, Dict, Optional

from . import protocol
from .bus import BusClient


def _ctrl(base_url: str, req: Dict) -> Dict:
    """调用中枢控制端点 /cnb/ctrl。"""
    return BusClient(timeout=15.0).post_ctrl(base_url, req)


def _print(obj: Dict):
    print(json.dumps(obj, ensure_ascii=False, indent=2))


# ----------------------------------------------------------------------
# 子命令
# ----------------------------------------------------------------------

# ----------------------------------------------------------------------
# 内核引擎装配（v1.0.7 内核集成：中枢/节点进程默认携带完整 norpagent 内核）
# ----------------------------------------------------------------------

_CLI_DEVNULL = None


def _devnull():
    global _CLI_DEVNULL
    if _CLI_DEVNULL is None:
        _CLI_DEVNULL = open(os.devnull, "w", encoding="utf-8")
    return _CLI_DEVNULL


def _start_cli_engine(args) -> Any:
    """装配完整 norpagent 内核引擎（headless、默认 minimal/mock 零依赖）。

    - preset 默认 minimal（mock 模型开箱即用，无第三方依赖）；--mode 可换。
    - frontend 固定 headless 且输出丢弃（神经服务不需要 UI 渲染）。
    - NORP_CNB_MANAGED=1 置入环境：引擎 start 的 env 自动挂载被跳过，
      节点/中枢由本 CLI 显式装配（防双重挂载）。
    - NORP_CNB_CLI=1 标记：stop_engine 动作后主循环据此退出进程。

    返回 NorpEngine；失败返回 None（调用方决定降级 bare / 退出）。
    """
    try:
        import io

        from norpagent import launch
        from norpagent.frontends.headless import HeadlessFrontend
    except Exception as exc:  # noqa: BLE001
        print(f"[cnb] engine assembly unavailable: {exc}; "
              f"running as a bare neural shell", file=sys.stderr)
        return None
    os.environ["NORP_CNB_MANAGED"] = "1"   # 防双重挂载（本 CLI 显式装配）
    os.environ["NORP_CNB_CLI"] = "1"       # stop_engine 后主循环据此退出
    kwargs: Dict[str, Any] = {}
    if getattr(args, "mode", None):
        kwargs["preset"] = args.mode
    if getattr(args, "model", None):
        kwargs["model"] = args.model
    try:
        frontend = HeadlessFrontend(stream=_devnull())
        engine = launch(frontend=frontend, **kwargs)
    except Exception as exc:  # noqa: BLE001
        print(f"[cnb] engine start failed: {exc}", file=sys.stderr)
        return None
    return engine


def _wait_cli_loop(engine: Any, extra_stop: Optional[Callable] = None) -> None:
    """常驻循环：Ctrl+C 退出；stop_engine 动作使引擎停止后自然退出进程。"""
    while True:
        try:
            if engine is not None and engine.should_stop():
                print("[cnb] engine stopped (stop_engine); exiting")
                return
            if extra_stop is not None and extra_stop():
                return
            time.sleep(0.5)
        except KeyboardInterrupt:
            return


def cmd_cortex(args):
    engine = None
    if not args.bare:
        engine = _start_cli_engine(args)
        if engine is None and (args.mode or args.model):
            print("[error] --mode/--model requested but the engine could not "
                  "start", file=sys.stderr)
            sys.exit(1)
    from .cortex import Cortex
    cortex = Cortex(node_id=args.id, host=args.host, port=args.port,
                    meta={"desc": args.desc or "cortex",
                          "engine": "norpagent", "cli": True})
    if engine is not None:
        # 中枢 = 最高级 norpagent 实例：绑定内核动作面（本机引擎）。
        # 中枢是树根（无父），不注册挂载——只绑定能力与审计回调。
        from .engine import CnbAdapter

        adapter = CnbAdapter(engine, cortex, {})
        with engine._cnb_lock:
            engine._cnb = adapter
        print(f"[cnb] cortex engine ready (preset={getattr(engine.preset, 'name', '?')}, "
              f"actions={len(cortex.list_actions())})")
    cortex.start()
    print(f"Cortex is online: {cortex.base_url} (node_id={cortex.node_id}, level=0"
          + (", engine=on" if engine is not None else ", engine=off(bare)") + ")")
    print("Press Ctrl+C to exit")
    try:
        if args.repl:
            cortex.repl()
        else:
            _wait_cli_loop(engine)
    except KeyboardInterrupt:
        pass
    finally:
        cortex.stop()
        if engine is not None:
            try:
                engine.request_stop()
            except Exception:  # noqa: BLE001
                pass
        print("Cortex is offline")


def cmd_node(args):
    engine = None
    if not args.bare:
        engine = _start_cli_engine(args)
        if engine is None and (args.mode or args.model):
            print("[error] --mode/--model requested but the engine could not "
                  "start", file=sys.stderr)
            sys.exit(1)
    from .node import NervousNode
    node = NervousNode(
        node_id=args.id, kind=args.kind, level=args.level,
        parent_url=args.parent, host=args.host, port=args.port,
        meta={"desc": args.desc or "", "engine": "norpagent", "cli": True},
        heartbeat_interval=args.heartbeat)
    if engine is not None:
        # 原子 = 完整内核实例：CnbAdapter 注册内核动作面 + 挂树（后台线程）。
        from .engine import CnbAdapter

        adapter = CnbAdapter(engine, node, {})
        with engine._cnb_lock:
            engine._cnb = adapter
        adapter.mount()
        print(f"[cnb] node engine ready (preset={getattr(engine.preset, 'name', '?')}, "
              f"actions={len(node.list_actions())})")
    else:
        # bare 探针模式：占位回调（echo 语义，无真实内核）
        node.on("exec", lambda p: {"echo": p.get("action"),
                                   "node": node.node_id,
                                   "ts": time.time()})
        node.on("stop", lambda: {"stopped": True})
        node.on("reload", lambda: {"reloaded": True})
        node.start()
    print(f"Node is online: {node.base_url} (node_id={node.node_id}, kind={node.kind}, "
          f"level={node.level}, parent={node.parent_url}"
          + (", engine=on" if engine is not None else ", engine=off(bare)") + ")")
    print("Press Ctrl+C to exit")
    try:
        _wait_cli_loop(engine)
    except KeyboardInterrupt:
        pass
    finally:
        node.stop()
        if engine is not None:
            try:
                engine.request_stop()
            except Exception:  # noqa: BLE001
                pass
        print(f"Node {node.node_id} is offline")


def cmd_topo(args):
    r = _ctrl(args.root, {"op": "topo"})
    if not r.get("ok"):
        _print(r)
        return
    print(r.get("tree"))
    print(f"({r.get('size')} nodes)")


def cmd_ping(args):
    _print(_ctrl(args.root, {"op": "ping", "node": args.node}))


def cmd_exec(args):
    _print(_ctrl(args.root, {"op": "exec", "node": args.node,
                             "action": args.action,
                             "args": json.loads(args.args) if args.args else {},
                             "perm": args.perm}))


def cmd_stop(args):
    _print(_ctrl(args.root, {"op": "stop", "node": args.node}))


def cmd_reload(args):
    _print(_ctrl(args.root, {"op": "reload", "node": args.node}))


def cmd_perm(args):
    if args.grant:
        _print(_ctrl(args.root, {"op": "grant", "target_type": args.target_type,
                                 "target": args.target, "perm": args.perm,
                                 "scope": json.loads(args.scope) if args.scope else None}))
    elif args.revoke:
        _print(_ctrl(args.root, {"op": "revoke", "target_type": args.target_type,
                                 "target": args.target, "perm": args.perm}))
    elif args.set:
        _print(_ctrl(args.root, {"op": "set", "target_type": args.target_type,
                                 "target": args.target,
                                 "allows": json.loads(args.allows)}))
    else:
        print("specify one of --grant / --revoke / --set")


def cmd_reports(args):
    r = _ctrl(args.root, {"op": "reports", "n": args.n})
    if not r.get("ok"):
        _print(r)
        return
    for rep in r.get("reports", []):
        p = rep.get("payload") or {}
        # 心跳/事件附加状态（v1.0.7 内核集成：心跳携带内核深度状态，
        # 中枢运维视图直接可见 engine_state / active_tasks / version）
        extra = ""
        if p.get("engine_state"):
            extra += f" engine_state={p.get('engine_state')}"
        if p.get("status") and p.get("status") != "running":
            extra += f" status={p.get('status')}"
        if p.get("active_tasks") is not None:
            extra += f" active_tasks={p.get('active_tasks')}"
        if p.get("version"):
            extra += f" version={p.get('version')}"
        if p.get("event_type"):
            extra += f" event={p.get('event_type')}"
        note = rep.get("note", "")
        if note:
            note += " |"
        print(f"[{time.strftime('%H:%M:%S', time.localtime(rep['ts']))}] "
              f"{rep.get('from')} -> {rep.get('type')}  {note}{extra}")


def cmd_audit(args):
    r = _ctrl(args.root, {"op": "audit", "n": args.n})
    if not r.get("ok"):
        _print(r)
        return
    for a in r.get("audit", []):
        print(f"[{time.strftime('%H:%M:%S', time.localtime(a['ts']))}] {a.get('msg')}")


def cmd_sync(args):
    _print(_ctrl(args.root, {"op": "sync"}))


def cmd_freeze(args):
    _print(_ctrl(args.root, {"op": "freeze", "node": args.node,
                             "reason": args.reason}))


def cmd_unfreeze(args):
    _print(_ctrl(args.root, {"op": "unfreeze", "node": args.node,
                             "reason": args.reason}))


def cmd_subpoena(args):
    """中枢签发传票（level 0 专属最高取证权限）。

    用法示例：
      python -m norpagent.cnb.cli subpoena --root http://127.0.0.1:17800 \
          --node rnd-01 --basis evidence_conflict --tier-kb 128
      （>128KB 需 --approved-by-human；超 512KB 强制转人工终裁）
    """
    r = _ctrl(args.root, {"op": "subpoena", "node": args.node,
                          "basis": args.basis, "scope": args.scope,
                          "tier_kb": args.tier_kb,
                          "approved_by_human": args.approved_by_human,
                          "summary_exhausted": not args.skip_summary,
                          "event": args.event or None,
                          "actor": args.actor or None,
                          "note": args.note})
    _print(r)
    if r.get("ok") and r.get("subpoena_id"):
        print(f"\n[note] evidence is in the isolated forensics box (RAW/UNTRUSTED):\n"
              f"  python -m norpagent.cnb.cli subpoena_box "
              f"--root {args.root} --subpoena-id {r['subpoena_id']} --destroy"
              f"\n  read-once-and-destroy; issuance record: subpoena_audit")


def cmd_subpoena_box(args):
    r = _ctrl(args.root, {"op": "subpoena_box",
                          "subpoena_id": args.subpoena_id or None,
                          "destroy": args.destroy})
    _print(r)


def cmd_subpoena_purge(args):
    _print(_ctrl(args.root, {"op": "subpoena_purge",
                             "subpoena_id": args.subpoena_id or None}))


def cmd_subpoena_audit(args):
    r = _ctrl(args.root, {"op": "subpoena_audit", "n": args.n})
    if not r.get("ok"):
        _print(r)
        return
    for a in r.get("audit", []):
        print(f"[{time.strftime('%H:%M:%S', time.localtime(a['ts']))}] "
              f"{a.get('actor')} -> {a.get('node_id')} "
              f"basis={a.get('basis')} tier={a.get('tier_kb')}KB "
              f"bytes={a.get('total_bytes', '?')} recs={a.get('total_records', '?')} "
              f"approved={a.get('approved_by_human')} "
              f"[immunity:{a.get('immunity')}]")


def cmd_behavior(args):
    """behavior-baseline grading view (yellow = degraded / black = suspected malicious)。"""
    r = _ctrl(args.root, {"op": "behavior"})
    if not r.get("ok"):
        _print(r)
        return
    print(f"behavior-baseline grading ({r.get('count')} nodes; stats converge via heartbeat):")
    marks = {"ok": "[OK]", "yellow": "[yellow · review]", "black": "[black · isolate]"}
    for v in r.get("verdicts", []):
        bh = v.get("behavior", {})
        print(f"  {marks.get(v['level'], v['level'])} {v['node_id']} "
              f"status={v.get('status')} frozen={v.get('frozen')} "
              f"audit_anomaly={bh.get('audit_anomaly_rate')} "
              f"task_fail={bh.get('task_fail_rate')} "
              f"hb_fail={bh.get('hb_fail_rate')} "
              f"hb_ok={bh.get('hb_ok')}/{bh.get('hb_sent')}")
        for reason in v.get("reasons", []):
            print(f"       - {reason}")


# ----------------------------------------------------------------------
# 神经树显式定义：validate / show / up
# ----------------------------------------------------------------------

def cmd_tree_validate(args):
    """校验神经树定义：缺必要参数逐条显式报错（退出码 0 通过 / 2 失败）。"""
    from .tree import TreeDefinitionError, parse_tree_definition, plan_table

    try:
        plan = parse_tree_definition(args.def_path)
    except TreeDefinitionError as exc:
        print("[cnb-tree][error] definition validation failed: ", file=sys.stderr)
        print(str(exc), file=sys.stderr)
        return 2
    print(plan_table(plan))
    print("validation passed: all required parameters present (level / count / port / low-level parent).")
    return 0


def cmd_tree_show(args):
    """展示规范化树计划（解析后的节点表；--json 输出机器可读）。"""
    from .tree import TreeDefinitionError, parse_tree_definition, plan_table

    try:
        plan = parse_tree_definition(args.def_path)
    except TreeDefinitionError as exc:
        print("[cnb-tree][error] definition validation failed: ", file=sys.stderr)
        print(str(exc), file=sys.stderr)
        return 2
    if args.json:
        _print(plan)
    else:
        print(plan_table(plan))
    return 0


def cmd_tree_up(args):
    """按定义拉起整棵神经树（inproc 进程内 / spawn 多进程）；Ctrl+C 退出。

    --watch：监视定义文件，内容变更时自动改形（错误保持现形并显式报错）。
    --reconcile SECONDS：启用自动收敛（节点掉线/进程退出时按定义恢复）。
    """
    from .tree import (
        TreeDefinitionError,
        build_in_process,
        parse_tree_definition,
        plan_table,
        spawn_tree,
    )

    try:
        plan = parse_tree_definition(args.def_path)
    except TreeDefinitionError as exc:
        print("[cnb-tree][error] definition validation failed: ", file=sys.stderr)
        print(str(exc), file=sys.stderr)
        return 2
    print(plan_table(plan))
    try:
        if args.mode == "spawn":
            tree = spawn_tree(plan, wait_timeout=args.wait,
                              log_dir=args.log_dir)
        else:
            tree = build_in_process(plan, wait_timeout=args.wait)
    except Exception as exc:  # noqa: BLE001 — 装配失败显式报错
        print(f"[cnb-tree][error] assembly failed: {type(exc).__name__}: {exc}",
              file=sys.stderr)
        return 2
    if args.watch:
        if os.path.isfile(args.def_path):
            tree.start_watcher(args.def_path)
        else:
            print("[cnb-tree][warn] --watch needs a definition file path (JSON text cannot be watched)",
                  file=sys.stderr)
    if args.reconcile:
        tree.start_reconciler(args.reconcile)
    mode_text = "in-process" if args.mode == "inproc" else "multi-process"
    print(f"neural tree assembled ({mode_text}, {len(plan['nodes'])} nodes). "
          f"Ctrl+C to exit.")
    try:
        while True:
            time.sleep(0.5)
    except KeyboardInterrupt:
        print()
    finally:
        tree.stop()
    return 0


# ----------------------------------------------------------------------
# 主入口
# ----------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="norpagent",
        description="Central Nervous Bus (CNB) — norpagent multi-instance neural-tree console"
                    " (v2.0.0 kernel integration: cortex/node assemble the full kernel engine by default)")
    sub = p.add_subparsers(dest="cmd", required=True)

    # cortex
    pc = sub.add_parser("cortex", help="start the cortex (root node; assembles the full kernel engine by default)")
    pc.add_argument("--id", default="cortex", help="cortex node id (default: cortex)")
    pc.add_argument("--host", default=protocol.DEFAULT_HOST)
    pc.add_argument("--port", type=int, required=True,
                    help="cortex bus port (never hardcoded, must be set manually; missing -> error)")
    pc.add_argument("--desc", default="")
    pc.add_argument("--repl", action="store_true", help="start the interactive console")
    pc.add_argument("--bare", action="store_true",
                    help="bare neural shell (no kernel engine; probe scenarios)")
    pc.add_argument("--mode", default=None,
                    help="kernel engine preset (default minimal; the mock model has zero dependencies)")
    pc.add_argument("--model", default=None,
                    help="kernel engine model slot (e.g. mock / openai_compat)")
    pc.set_defaults(func=cmd_cortex)

    # node
    pn = sub.add_parser("node", help="start a node instance (atom; assembles the full kernel engine by default)")
    pn.add_argument("--id", required=True, help="node id, e.g. norpbot-01")
    pn.add_argument("--kind", default="node", help="atom kind: bot/pilot/memory/voice/vision/...")
    pn.add_argument("--level", type=int, default=protocol.LEVEL_ATOM,
                    help=f"level (default {protocol.LEVEL_ATOM}; must be greater than the parent level)")
    pn.add_argument("--parent", required=True, help="parent bus address, e.g. http://127.0.0.1:17800")
    pn.add_argument("--host", default=protocol.DEFAULT_HOST)
    pn.add_argument("--port", type=int, required=True, help="this node's bus port")
    pn.add_argument("--desc", default="")
    pn.add_argument("--heartbeat", type=float, default=5.0, help="heartbeat interval in seconds")
    pn.add_argument("--bare", action="store_true",
                    help="bare neural shell (no kernel engine; probe scenarios)")
    pn.add_argument("--mode", default=None,
                    help="kernel engine preset (default minimal; the mock model has zero dependencies)")
    pn.add_argument("--model", default=None,
                    help="kernel engine model slot (e.g. mock / openai_compat)")
    pn.set_defaults(func=cmd_node)

    # 公共根参数
    def add_root(sp):
        sp.add_argument("--root", default=f"http://{protocol.DEFAULT_HOST}:{protocol.DEFAULT_CORTEX_PORT}",
                        help="cortex bus address")

    # topo
    pt = sub.add_parser("topo", help="show the cortex topology")
    add_root(pt)
    pt.set_defaults(func=cmd_topo)

    # ping
    pp = sub.add_parser("ping", help="cortex liveness-probe a given node")
    add_root(pp)
    pp.add_argument("--node", required=True)
    pp.set_defaults(func=cmd_ping)

    # exec
    pe = sub.add_parser("exec", help="cortex issues an execution command (kernel action surface: run_task/"
                        "status/snapshot/rollback/remount/...; --bare nodes get a placeholder action)")
    add_root(pe)
    pe.add_argument("--node", required=True)
    pe.add_argument("--action", required=True)
    pe.add_argument("--args", default=None, help="JSON argument string, e.g. "
                    "'{\"prompt\": \"hello\"}' / '{\"description\": \"before upgrade\"}'")
    pe.add_argument("--perm", default="process_exec", help="required permission atom")
    pe.set_defaults(func=cmd_exec)

    # stop / reload
    ps = sub.add_parser("stop", help="cortex orders a node task to stop")
    add_root(ps)
    ps.add_argument("--node", required=True)
    ps.set_defaults(func=cmd_stop)

    pr = sub.add_parser("reload", help="cortex orders a node config reload")
    add_root(pr)
    pr.add_argument("--node", required=True)
    pr.set_defaults(func=cmd_reload)

    # perm
    pm = sub.add_parser("perm", help="cortex controls permissions of any atom at any level")
    add_root(pm)
    pm.add_argument("--grant", action="store_true", help="grant permission")
    pm.add_argument("--revoke", action="store_true", help="revoke permission")
    pm.add_argument("--set", action="store_true", help="overwrite all permissions")
    pm.add_argument("--target-type", default="*", choices=["node_id", "node_kind", "*"])
    pm.add_argument("--target", default="*", help="target node id / atom kind / *")
    pm.add_argument("--perm", default="", help="permission atom (used by grant/revoke)")
    pm.add_argument("--scope", default=None, help="optional JSON scope {\"whitelist\": [], \"blacklist\": []}")
    pm.add_argument("--allows", default="{}", help="overwrite JSON, e.g. {\"process_shell\": false}")
    pm.set_defaults(func=cmd_perm)

    # reports / audit / sync
    prt = sub.add_parser("reports", help="show reports received by the cortex")
    add_root(prt)
    prt.add_argument("--n", type=int, default=20)
    prt.set_defaults(func=cmd_reports)

    pau = sub.add_parser("audit", help="show the cortex audit")
    add_root(pau)
    pau.add_argument("--n", type=int, default=20)
    pau.set_defaults(func=cmd_audit)

    psy = sub.add_parser("sync", help="cortex broadcasts the topology to all descendants")
    add_root(psy)
    psy.set_defaults(func=cmd_sync)

    # freeze / unfreeze（隔离冻结态）
    pfz = sub.add_parser("freeze", help="cortex issues a freeze (rejects new tasks, keeps alive for forensics)")
    add_root(pfz)
    pfz.add_argument("--node", required=True, help="target node id")
    pfz.add_argument("--reason", default="", help="freeze reason (isolation semantics)")
    pfz.set_defaults(func=cmd_freeze)

    puf = sub.add_parser("unfreeze", help="cortex lifts the freeze (returns to the tree)")
    add_root(puf)
    puf.add_argument("--node", required=True, help="target node id")
    puf.add_argument("--reason", default="", help="reason for lifting (review passed)")
    puf.set_defaults(func=cmd_unfreeze)

    # subpoena 传票取证
    psp = sub.add_parser("subpoena", help="cortex issues a subpoena for forensics (level 0 "
                         "only highest authority; raw audit goes straight to the cortex)")
    add_root(psp)
    psp.add_argument("--node", required=True, help="target node id (forensics target)")
    psp.add_argument("--basis", required=True,
                     choices=list(protocol.SUBPOENA_BASIS.keys()),
                     help="issuance basis: confidence_low / vote_tie / "
                          "evidence_conflict / human_named")
    psp.add_argument("--scope", default="audit",
                     choices=["audit", "reports", "both"],
                     help="forensics scope (default audit = local raw audit)")
    psp.add_argument("--tier-kb", type=int, default=64,
                     help="capacity tier KB (64/128/256/512; >128 needs --approved-by-human)")
    psp.add_argument("--approved-by-human", action="store_true",
                     help="human-approval flag for the >128KB tier")
    psp.add_argument("--skip-summary", action="store_true",
                     help="(danger) skip the 'summary ruling exhausted' declaration - do not use for normal issuance")
    psp.add_argument("--event", default=None, help="event type filter (substring match)")
    psp.add_argument("--note", default="", help="issuance note")
    psp.add_argument("--actor", default=None,
                     help="actual issuer identity (default cortex node_id; pass the operator for "
                          "human-approved/named forensics for a complete audit trail)")
    psp.set_defaults(func=cmd_subpoena)

    psb = sub.add_parser("subpoena_box", help="read the cortex isolated forensics box ("
                         "RAW/UNTRUSTED frames; --destroy reads and burns)")
    add_root(psb)
    psb.add_argument("--subpoena-id", default=None)
    psb.add_argument("--destroy", action="store_true",
                     help="destroy after reading (read-once-and-destroy)")
    psb.set_defaults(func=cmd_subpoena_box)

    pspg = sub.add_parser("subpoena_purge", help="destroy the isolated forensics box contents")
    add_root(pspg)
    pspg.add_argument("--subpoena-id", default=None)
    pspg.set_defaults(func=cmd_subpoena_purge)

    pspa = sub.add_parser("subpoena_audit", help="subpoena issuance log (who/when/basis/"
                          "scope/bytes; black-level events)")
    add_root(pspa)
    pspa.add_argument("--n", type=int, default=20)
    pspa.set_defaults(func=cmd_subpoena_audit)

    # behavior 行为基线分级
    pbh = sub.add_parser("behavior", help="behavior-baseline grading view (yellow = degraded / black = suspected malicious)")
    add_root(pbh)
    pbh.set_defaults(func=cmd_behavior)

    # tree 神经树显式定义：不预设形状，启动时显式传入
    ptree = sub.add_parser(
        "tree", help="neural-tree explicit definition: validate / show / up (no tree shape is preset)")
    t_sub = ptree.add_subparsers(dest="tree_cmd", required=True)

    tv = t_sub.add_parser("validate", help="validate a definition (missing required parameters are reported one by one)")
    tv.add_argument("--def", dest="def_path", required=True,
                    help="definition: JSON / PY file path or JSON text")
    tv.set_defaults(func=cmd_tree_validate)

    tsh = t_sub.add_parser("show", help="show the normalized tree plan (parsed node table)")
    tsh.add_argument("--def", dest="def_path", required=True,
                     help="definition: JSON / PY file path or JSON text")
    tsh.add_argument("--json", action="store_true", help="output machine-readable JSON")
    tsh.set_defaults(func=cmd_tree_show)

    tu = t_sub.add_parser(
        "up", help="bring up the whole tree from a definition (inproc / spawn; Ctrl+C to exit)")
    tu.add_argument("--def", dest="def_path", required=True,
                    help="definition: JSON / PY file path or JSON text")
    tu.add_argument("--mode", default="inproc", choices=["inproc", "spawn"],
                    help="assembly mode (default inproc; spawn = real multi-process tree)")
    tu.add_argument("--watch", action="store_true",
                    help="watch the definition file and reshape on change (errors keep the current shape and report)")
    tu.add_argument("--reconcile", type=float, default=None, metavar="SECONDS",
                    help="enable auto-convergence: restore offline/exited nodes per the definition (interval seconds)")
    tu.add_argument("--wait", type=float, default=15.0,
                    help="assembly wait seconds (default 15)")
    tu.add_argument("--log-dir", default=None,
                    help="spawn-mode subprocess log directory (output discarded by default)")
    tu.set_defaults(func=cmd_tree_up)

    return p


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    result = args.func(args)
    return result if isinstance(result, int) else 0


if __name__ == "__main__":
    sys.exit(main())
