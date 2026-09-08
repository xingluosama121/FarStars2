# -*- coding: utf-8 -*-
"""
norpagent.cnb.cli — 中枢神经总线命令行入口

用法示例：

  1. 启动大脑皮层（根节点，level 0）：
     python -m norpagent.cnb.cli cortex --port 17800 --repl

  2. 启动一个节点实例（原子，挂到皮层下）：
     python -m norpagent.cnb.cli node --id norpbot-01 --kind bot \
         --parent http://127.0.0.1:17800 --port 17801 --level 3

  3. 启动深一层节点（树状拓扑链：皮层 -> bot -> pilot）：
     python -m norpagent.cnb.cli node --id norpilot-01 --kind pilot \
         --parent http://127.0.0.1:17801 --port 17802 --level 4

  4. 查看拓扑：
     python -m norpagent.cnb.cli topo --root http://127.0.0.1:17800

  5. 皮层下发指令（探活 / 执行 / 停止）：
     python -m norpagent.cnb.cli ping  --root http://127.0.0.1:17800 --node norpbot-01
     python -m norpagent.cnb.cli exec  --root http://127.0.0.1:17800 --node norpbot-01 --action run_task
     python -m norpagent.cnb.cli stop  --root http://127.0.0.1:17800 --node norpbot-01

  6. 皮层控制任意层级任意原子的操作权限：
     python -m norpagent.cnb.cli perm --root http://127.0.0.1:17800 \
         --grant --target-type node_kind --target bot --perm file_write
     python -m norpagent.cnb.cli perm --root http://127.0.0.1:17800 \
         --revoke --target-type node_id --target norpbot-01 --perm process_shell
     python -m norpagent.cnb.cli perm --root http://127.0.0.1:17800 \
         --set --target-type node_kind --target bot \
         --allows '{"process_shell": false, "file_delete": false}'

  7. 查看皮层收到的上报：
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
    """调用皮层控制端点 /cnb/ctrl。"""
    return BusClient(timeout=15.0).post_ctrl(base_url, req)


def _print(obj: Dict):
    print(json.dumps(obj, ensure_ascii=False, indent=2))


# ----------------------------------------------------------------------
# 子命令
# ----------------------------------------------------------------------

# ----------------------------------------------------------------------
# 内核引擎装配（v1.0.7 内核集成：皮层/节点进程默认携带完整 norpagent 内核）
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
      节点/皮层由本 CLI 显式装配（防双重挂载）。
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
                    meta={"desc": args.desc or "大脑皮层",
                          "engine": "norpagent", "cli": True})
    if engine is not None:
        # 皮层 = 最高级 norpagent 实例：绑定内核动作面（本机引擎）。
        # 皮层是树根（无父），不注册挂载——只绑定能力与审计回调。
        from .engine import CnbAdapter

        adapter = CnbAdapter(engine, cortex, {})
        with engine._cnb_lock:
            engine._cnb = adapter
        print(f"[cnb] cortex engine ready (preset={getattr(engine.preset, 'name', '?')}, "
              f"actions={len(cortex.list_actions())})")
    cortex.start()
    print(f"大脑皮层已上线：{cortex.base_url} (node_id={cortex.node_id}, level=0"
          + (", engine=on" if engine is not None else ", engine=off(bare)") + ")")
    print("按 Ctrl+C 退出")
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
        print("大脑皮层已下线")


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
    print(f"节点已上线：{node.base_url} (node_id={node.node_id}, kind={node.kind}, "
          f"level={node.level}, parent={node.parent_url}"
          + (", engine=on" if engine is not None else ", engine=off(bare)") + ")")
    print("按 Ctrl+C 退出")
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
        print(f"节点 {node.node_id} 已下线")


def cmd_topo(args):
    r = _ctrl(args.root, {"op": "topo"})
    if not r.get("ok"):
        _print(r)
        return
    print(r.get("tree"))
    print(f"(共 {r.get('size')} 个节点)")


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
        print("请指定 --grant / --revoke / --set 之一")


def cmd_reports(args):
    r = _ctrl(args.root, {"op": "reports", "n": args.n})
    if not r.get("ok"):
        _print(r)
        return
    for rep in r.get("reports", []):
        p = rep.get("payload") or {}
        # 心跳/事件附加状态（v1.0.7 内核集成：心跳携带内核深度状态，
        # 皮层运维视图直接可见 engine_state / active_tasks / version）
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
    """皮层签发传票（level 0 专属最高取证权限）。

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
        print(f"\n[提示] 证据在隔离取证箱（RAW/UNTRUSTED）：\n"
              f"  python -m norpagent.cnb.cli subpoena_box "
              f"--root {args.root} --subpoena-id {r['subpoena_id']} --destroy"
              f"\n  读取即焚（用后即毁）；签发记录: subpoena_audit")


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
    """行为基线分级视图（黄劣化/黑疑似恶意）。"""
    r = _ctrl(args.root, {"op": "behavior"})
    if not r.get("ok"):
        _print(r)
        return
    print(f"行为基线分级（{r.get('count')} 个节点，统计随心跳上汇）：")
    marks = {"ok": "[OK]", "yellow": "[黄·复核]", "black": "[黑·隔离]"}
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
# 主入口
# ----------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="norpagent",
        description="中枢神经总线 CNB — norpagent 多实例神经树控制台"
                    "（v2.0.0 内核集成：cortex/node 默认装配完整内核引擎）")
    sub = p.add_subparsers(dest="cmd", required=True)

    # cortex
    pc = sub.add_parser("cortex", help="启动大脑皮层（根节点，默认装配完整内核引擎）")
    pc.add_argument("--id", default="cortex", help="皮层节点 id（默认 cortex）")
    pc.add_argument("--host", default=protocol.DEFAULT_HOST)
    pc.add_argument("--port", type=int, default=protocol.DEFAULT_CORTEX_PORT)
    pc.add_argument("--desc", default="")
    pc.add_argument("--repl", action="store_true", help="启动交互控制台")
    pc.add_argument("--bare", action="store_true",
                    help="纯神经空壳（不装配内核引擎，探针场景）")
    pc.add_argument("--mode", default=None,
                    help="内核引擎预设（默认 minimal；mock 模型零依赖）")
    pc.add_argument("--model", default=None,
                    help="内核引擎模型槽（如 mock / openai_compat）")
    pc.set_defaults(func=cmd_cortex)

    # node
    pn = sub.add_parser("node", help="启动一个节点实例（原子，默认装配完整内核引擎）")
    pn.add_argument("--id", required=True, help="节点 id，如 norpbot-01")
    pn.add_argument("--kind", default="node", help="原子类型：bot/pilot/memory/voice/vision/...")
    pn.add_argument("--level", type=int, default=protocol.LEVEL_ATOM,
                    help=f"等级（默认 {protocol.LEVEL_ATOM}，须大于父节点等级）")
    pn.add_argument("--parent", required=True, help="父节点总线地址，如 http://127.0.0.1:17800")
    pn.add_argument("--host", default=protocol.DEFAULT_HOST)
    pn.add_argument("--port", type=int, required=True, help="本节点总线端口")
    pn.add_argument("--desc", default="")
    pn.add_argument("--heartbeat", type=float, default=5.0, help="心跳间隔秒数")
    pn.add_argument("--bare", action="store_true",
                    help="纯神经空壳（不装配内核引擎，探针场景）")
    pn.add_argument("--mode", default=None,
                    help="内核引擎预设（默认 minimal；mock 模型零依赖）")
    pn.add_argument("--model", default=None,
                    help="内核引擎模型槽（如 mock / openai_compat）")
    pn.set_defaults(func=cmd_node)

    # 公共根参数
    def add_root(sp):
        sp.add_argument("--root", default=f"http://{protocol.DEFAULT_HOST}:{protocol.DEFAULT_CORTEX_PORT}",
                        help="皮层总线地址")

    # topo
    pt = sub.add_parser("topo", help="查看皮层拓扑")
    add_root(pt)
    pt.set_defaults(func=cmd_topo)

    # ping
    pp = sub.add_parser("ping", help="皮层探活指定节点")
    add_root(pp)
    pp.add_argument("--node", required=True)
    pp.set_defaults(func=cmd_ping)

    # exec
    pe = sub.add_parser("exec", help="皮层下发执行指令（内核动作面：run_task/"
                        "status/snapshot/rollback/remount/...；--bare 节点为占位动作）")
    add_root(pe)
    pe.add_argument("--node", required=True)
    pe.add_argument("--action", required=True)
    pe.add_argument("--args", default=None, help="JSON 参数字符串，如 "
                    "'{\"prompt\": \"hello\"}' / '{\"description\": \"before upgrade\"}'")
    pe.add_argument("--perm", default="process_exec", help="所需权限原子")
    pe.set_defaults(func=cmd_exec)

    # stop / reload
    ps = sub.add_parser("stop", help="皮层下令停止节点任务")
    add_root(ps)
    ps.add_argument("--node", required=True)
    ps.set_defaults(func=cmd_stop)

    pr = sub.add_parser("reload", help="皮层下令重载节点配置")
    add_root(pr)
    pr.add_argument("--node", required=True)
    pr.set_defaults(func=cmd_reload)

    # perm
    pm = sub.add_parser("perm", help="皮层控制任意层级任意原子操作权限")
    add_root(pm)
    pm.add_argument("--grant", action="store_true", help="授予权限")
    pm.add_argument("--revoke", action="store_true", help="撤销权限")
    pm.add_argument("--set", action="store_true", help="整体覆盖权限")
    pm.add_argument("--target-type", default="*", choices=["node_id", "node_kind", "*"])
    pm.add_argument("--target", default="*", help="目标节点 id / 原子类型 / *")
    pm.add_argument("--perm", default="", help="权限原子（grant/revoke 用）")
    pm.add_argument("--scope", default=None, help="可选 JSON 作用域 {\"whitelist\": [], \"blacklist\": []}")
    pm.add_argument("--allows", default="{}", help="整体覆盖 JSON，如 {\"process_shell\": false}")
    pm.set_defaults(func=cmd_perm)

    # reports / audit / sync
    prt = sub.add_parser("reports", help="查看皮层收到的上报")
    add_root(prt)
    prt.add_argument("--n", type=int, default=20)
    prt.set_defaults(func=cmd_reports)

    pau = sub.add_parser("audit", help="查看皮层审计")
    add_root(pau)
    pau.add_argument("--n", type=int, default=20)
    pau.set_defaults(func=cmd_audit)

    psy = sub.add_parser("sync", help="皮层向全部后代广播拓扑")
    add_root(psy)
    psy.set_defaults(func=cmd_sync)

    # freeze / unfreeze（隔离冻结态）
    pfz = sub.add_parser("freeze", help="皮层签发冻结（拒新任务、保活取证）")
    add_root(pfz)
    pfz.add_argument("--node", required=True, help="目标节点 id")
    pfz.add_argument("--reason", default="", help="冻结原因（隔离处置语义）")
    pfz.set_defaults(func=cmd_freeze)

    puf = sub.add_parser("unfreeze", help="皮层解除冻结（康复回树）")
    add_root(puf)
    puf.add_argument("--node", required=True, help="目标节点 id")
    puf.add_argument("--reason", default="", help="解除原因（复核通过）")
    puf.set_defaults(func=cmd_unfreeze)

    # subpoena 传票取证
    psp = sub.add_parser("subpoena", help="皮层签发传票取证（level 0 "
                         "专属最高取证权限，原始审计直传皮层）")
    add_root(psp)
    psp.add_argument("--node", required=True, help="目标节点 id（取证对象）")
    psp.add_argument("--basis", required=True,
                     choices=list(protocol.SUBPOENA_BASIS.keys()),
                     help="签发判据：confidence_low / vote_tie / "
                          "evidence_conflict / human_named")
    psp.add_argument("--scope", default="audit",
                     choices=["audit", "reports", "both"],
                     help="取证范围（默认 audit=本地原始审计）")
    psp.add_argument("--tier-kb", type=int, default=64,
                     help="容量档 KB（64/128/256/512；>128 需 --approved-by-human）")
    psp.add_argument("--approved-by-human", action="store_true",
                     help=">128KB 档的人工批准标记")
    psp.add_argument("--skip-summary", action="store_true",
                     help="（危险）跳过「已穷尽摘要裁决」声明——正常签发不要用")
    psp.add_argument("--event", default=None, help="事件类型过滤（子串匹配）")
    psp.add_argument("--note", default="", help="签发备注")
    psp.add_argument("--actor", default=None,
                     help="实际签发人身份（默认皮层 node_id；人工批准/点名"
                          "取证时传操作者，审计留痕完整）")
    psp.set_defaults(func=cmd_subpoena)

    psb = sub.add_parser("subpoena_box", help="读取皮层隔离取证箱（"
                         "RAW/UNTRUSTED 隔离帧；--destroy 读取即焚）")
    add_root(psb)
    psb.add_argument("--subpoena-id", default=None)
    psb.add_argument("--destroy", action="store_true",
                     help="读取后销毁（用后即毁）")
    psb.set_defaults(func=cmd_subpoena_box)

    pspg = sub.add_parser("subpoena_purge", help="销毁隔离取证箱内容")
    add_root(pspg)
    pspg.add_argument("--subpoena-id", default=None)
    pspg.set_defaults(func=cmd_subpoena_purge)

    pspa = sub.add_parser("subpoena_audit", help="传票签发记录（谁/何时/判据/"
                          "范围/字节，黑级事件）")
    add_root(pspa)
    pspa.add_argument("--n", type=int, default=20)
    pspa.set_defaults(func=cmd_subpoena_audit)

    # behavior 行为基线分级
    pbh = sub.add_parser("behavior", help="行为基线分级视图（黄劣化/黑疑似恶意）")
    add_root(pbh)
    pbh.set_defaults(func=cmd_behavior)

    return p


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
