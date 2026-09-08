# Copyright (c) 2026 xingluosama121, MIT Licensed
"""norpagent.cnb.engine — CNB 引擎绑定层（v1.0.7 内核集成核心）。

职责：把 norpagent 内核（NorpEngine）的公开能力注册为神经节点的内核动作面。
CNB 从此不再只是「站在节点外下发 HTTP 的外挂传输层」——皮层 cmd.exec 的
动作直接路由到本层注册的处理器，处理器直连 NorpEngine 公开 API（任务 /
快照 / 回滚 / 重载 / 运维），执行结果作为回执经神经树逐级返回皮层。

两种装配入口共用本层（同一套内核动作面）：
1. env 自动挂载（手册 §30.8）：设 NORP_CNB_NODE 等 env 后启动
   普通 norpagent 实例，NorpEngine.start() -> setup_cnb(engine) 自动建
   NervousNode 并挂树（单实例可选装配）；
2. CLI 神经进程（norpagent cortex/node 子命令）：默认装配完整内核引擎，
   由 norpagent.cnb.cli 构造引擎后经 CnbAdapter 绑定到 Cortex/NervousNode。

内核动作面（皮层可对任意层级任意原子下发；perm=process_exec，皮层 revoke
后整体失去 exec 能力——explorer 剥夺语义不变）：
  任务面   run_task / status / stop_task
  状态面   engine_state / inspect
  快照面   snapshot / rollback / undo / redo / list_snapshots / mark_good
  运维面   remount / reload_plugins / stop_engine
  （cmd.stop / cmd.reload 下行保持独立语义：停全部会话任务 / 重读 env 并
    热重载插件——引擎保持 RUNNING）

心跳融合：mount 后节点心跳自动携带 engine_state / active_tasks / 版本号，
经父链逐级汇聚到皮层（皮层 reports 可见各原子内核忙闲与任务数）。

设计边界（如实记录，无虚构声称）：
- kind / level / parent / port 注册时固定（神经树身份保护），reload 只热更新
  运行旋钮（心跳间隔 / desc）；
- 权限表管辖 CNB 指令面（cmd.exec 前置查表）；皮层权限同步进进程内工具调用
  链属未来 permission_cascade 集成（perm_changed 回调即钩子，留 1.0.8）；
- 本模块只经 NorpEngine 公开成员（start/stop 生命周期、submit_async、
  cancel_task、stop_all_tasks、active_tasks、forget_task、remount、
  snapshot/rollback/undo/redo/list_snapshots/mark_good、layer、state）通信，
  不触碰 engine 内部（_cnb 字段除外，由 engine._setup_cnb/_teardown_cnb 契约使用）。
- 皮层权限同步进进程内工具调用链（permission_cascade）留后续版本接入
  （perm_changed 回调即预留钩子）。
"""

from __future__ import annotations

import os
import threading
import time
from collections import deque
from typing import Any, Callable, Dict, Optional

# ── env keys & defaults (mirrored in docs/DEVELOPER_MANUAL.md §30.8) ──

ENV_NODE = "NORP_CNB_NODE"            # node id; set = enable auto-mount
ENV_KIND = "NORP_CNB_KIND"            # atom kind (bot / pilot / memory / ...)
ENV_LEVEL = "NORP_CNB_LEVEL"          # tree level (must exceed the parent's)
ENV_PARENT = "NORP_CNB_PARENT"        # parent bus address
ENV_PORT = "NORP_CNB_PORT"            # this node's bus port
ENV_HEARTBEAT = "NORP_CNB_HEARTBEAT"  # heartbeat interval in seconds
ENV_DESC = "NORP_CNB_DESC"            # optional node meta description
ENV_MANAGED = "NORP_CNB_MANAGED"      # 1 = kernel skips mounting (upper layer builds its own node)
ENV_CLI = "NORP_CNB_CLI"              # set by the CNB CLI (norpagent node/cortex) on its engine

CNB_ENV_KEYS = (
    ENV_NODE, ENV_KIND, ENV_LEVEL, ENV_PARENT,
    ENV_PORT, ENV_HEARTBEAT, ENV_DESC, ENV_MANAGED, ENV_CLI,
)

DEFAULT_KIND = "agent"
DEFAULT_LEVEL = 3
DEFAULT_PARENT = "http://127.0.0.1:17800"
DEFAULT_PORT = 17801
DEFAULT_HEARTBEAT = 5.0

# registration retry budget (≈ 30 s) before a node with an unreachable parent
# degrades to a plain instance
REGISTER_RETRY_SECONDS = 5.0
REGISTER_ATTEMPTS = 6

# 内核动作面（v1.0.7）：皮层 cmd.exec action 白名单。全部直连 NorpEngine
# 公开 API；纯神经 CLI（--bare）没有引擎，不受本表约束（可注册占位动作）。
# v2.0.0：新增 task_records —— 任务分子（mol）结构化载荷与验收
# 回执查询动作（皮层对任意原子可见「吸收位收到的完整 mol 六要素 + 结果」）。
KERNEL_ACTIONS = frozenset({
    # 任务面
    "run_task", "status", "stop_task",
    # 任务分子通道：已受理任务载荷原样 + 完成结果（验收回执）
    "task_records",
    # 状态面
    "engine_state", "inspect",
    # 快照面（work rollback / crash rescue 体系）
    "snapshot", "rollback", "undo", "redo",
    "list_snapshots", "mark_good",
    # 运维面
    "remount", "reload_plugins", "stop_engine",
})

# 回执 JSON 序列化保护：单个字段上限字符（防超长对象打爆总线应答）
_DETAIL_FIELD_LIMIT = 4000


# ── env reading ─────────────────────────────────────────

def _env_flag(name: str) -> bool:
    raw = (os.environ.get(name) or "").strip().lower()
    return raw in ("1", "true", "yes", "on")


def _env_int(name: str, default: int, floor: int, ceiling: int) -> int:
    raw = (os.environ.get(name) or "").strip()
    if not raw:
        return default
    try:
        return max(floor, min(int(raw), ceiling))
    except (TypeError, ValueError):
        print(f"[cnb] env {name}={raw!r} invalid; using default {default}")
        return default


def _env_float(name: str, default: float, floor: float, ceiling: float) -> float:
    raw = (os.environ.get(name) or "").strip()
    if not raw:
        return default
    try:
        return max(floor, min(float(raw), ceiling))
    except (TypeError, ValueError):
        print(f"[cnb] env {name}={raw!r} invalid; using default {default}")
        return default


def read_env_config() -> Dict[str, Any]:
    """Read the NORP_CNB_* env config (the single source of truth for auto-mount)."""
    node_id = (os.environ.get(ENV_NODE) or "").strip()
    return {
        "enabled": bool(node_id),
        "managed": _env_flag(ENV_MANAGED),
        "node_id": node_id,
        "kind": (os.environ.get(ENV_KIND) or DEFAULT_KIND).strip() or DEFAULT_KIND,
        "level": _env_int(ENV_LEVEL, DEFAULT_LEVEL, 1, 63),
        "parent": (os.environ.get(ENV_PARENT) or DEFAULT_PARENT).strip() or DEFAULT_PARENT,
        "port": _env_int(ENV_PORT, DEFAULT_PORT, 1, 65535),
        "heartbeat": _env_float(ENV_HEARTBEAT, DEFAULT_HEARTBEAT, 0.5, 3600.0),
        "desc": (os.environ.get(ENV_DESC) or "").strip(),
    }


# ── JSON 序列化保护 ─────────────────────────────────────

def _jsonable(obj: Any, _depth: int = 0) -> Any:
    """把引擎返回对象收敛为可 JSON 序列化的结构（防总线应答炸序列化）。"""
    if _depth > 6:
        return str(obj)[:_DETAIL_FIELD_LIMIT]
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            out[str(k)] = _jsonable(v, _depth + 1)
        return out
    if isinstance(obj, (list, tuple)):
        return [_jsonable(v, _depth + 1) for v in obj][:_DETAIL_FIELD_LIMIT]
    if isinstance(obj, bool) or obj is None:
        return obj
    if isinstance(obj, (int, float)):
        return obj
    s = str(obj)
    return s if len(s) <= _DETAIL_FIELD_LIMIT else s[:_DETAIL_FIELD_LIMIT] + "..."


def _np_version() -> str:
    try:
        from norpagent import __version__ as ver

        return str(ver)
    except Exception:  # noqa: BLE001
        return "?"


# ── the adapter ─────────────────────────────────────────

class CnbAdapter:
    """NorpEngine <-> NervousNode/Cortex 绑定：注册内核动作面 + 生命周期。

    Status lifecycle: mounting → mounted | failed → stopped.

    用法（三种入口共用）：
      - env 自动挂载：setup_cnb(engine)（engine.start -> _setup_cnb 调用）；
      - CLI 节点：engine 装配后 CnbAdapter(engine, node, cfg).mount()；
      - CLI 皮层：CnbAdapter.bind_actions(engine, cortex)（根节点无父，不注册）。
    """

    def __init__(self, engine: Any, node: Any, cfg: Dict[str, Any]) -> None:
        self.engine = engine
        self.node: Optional[Any] = node
        self.cfg = cfg
        self.status = "mounting"  # mounting / mounted / failed / stopped
        self.error: Optional[str] = None
        self.perm_summary: Dict[str, Any] = {}
        self._lock = threading.Lock()
        self._stopped = threading.Event()
        self._mount_thread: Optional[threading.Thread] = None
        self._actions_bound = False
        # 已受理任务记录（task_params 结构化载荷原样 + 完成结果）。
        # 皮层 exec task_records 即可读取「原子吸收位收到的完整 mol 六要素 +
        # 验收回执」——任务分子通道的端到端可追溯（audit 中 mol_id 贯穿）。
        self._task_records: deque = deque(maxlen=100)
        self._task_records_lock = threading.Lock()
        if node is not None:
            self.bind_actions(engine, node)

    # ── 内核动作面绑定（幂等） ───────────────────────────

    def bind_actions(self, engine: Any, node: Any) -> None:
        """把内核动作面注册到节点（exec 动作表）+ 挂三个下行事件回调。

        - exec 动作：注册到 node 动作注册表，cmd.exec 直达 NorpEngine API；
        - stop：cmd.stop 下行（停全部会话任务，引擎保持 RUNNING）；
        - reload：cmd.reload 下行（重读 env + 热重载外部插件）；
        - perm_changed：皮层改写本节点权限表后的审计记录。
        """
        if self._actions_bound:
            return
        # 下行事件（非 exec 指令面）
        node.on("stop", self._on_stop)
        node.on("reload", self._on_reload)
        node.on("perm_changed", self._on_perm_changed)
        # 内核动作面（exec 指令面）
        for action in KERNEL_ACTIONS:
            handler = getattr(self, f"_action_{action}", None)
            if callable(handler):
                node.register_action(action, handler)
        # 心跳携带内核深度状态
        node.set_heartbeat_provider(self._heartbeat_info)
        self._actions_bound = True

    def _heartbeat_info(self) -> Any:
        """心跳 provider：返回 (status, extra)。故障不静默——返回
        degraded + provider_error（皮层可见「状态源故障」，非无状态）。"""
        try:
            engine = self.engine
            state = engine.state.value
            tasks = engine.active_tasks()
            return state, {
                "engine_state": state,
                "active_tasks": len(tasks),
                "version": _np_version(),
                "mount": self.status,
                "actions": len(node_actions(self.node)),
            }
        except Exception as exc:  # noqa: BLE001 — 显式降级而非静默无状态
            return "degraded", {
                "provider_error": f"{type(exc).__name__}: {exc}"[:200],
                "mount": self.status,
            }

    # ── lifecycle ────────────────────────────────────────

    def mount(self) -> None:
        """Start the node bus and register under the parent (daemon thread; never delays startup)."""

        def _run() -> None:
            node = self.node
            if node is None or self._stopped.is_set():
                return
            try:
                node.start()
            except Exception as exc:  # port busy / bind failure → degrade
                self._fail(f"node start failed: {exc}")
                return
            try:
                if not self._wait_registered(node):
                    try:
                        node.stop()
                    except Exception:  # noqa: BLE001
                        pass
                    # engine teardown during the mounting window is not a failure
                    if not self._stopped.is_set():
                        self._fail("parent unreachable within the retry budget; node stopped")
                    return
            except Exception as exc:  # noqa: BLE001
                try:
                    node.stop()
                except Exception:  # noqa: BLE001
                    pass
                self._fail(f"registration error: {exc}")
                return
            if self._stopped.is_set():
                try:
                    node.stop()
                except Exception:  # noqa: BLE001
                    pass
                return
            self.status = "mounted"
            print(
                f"[cnb] mounted node {node.node_id} (kind={node.kind}, "
                f"level={node.level}, parent={node.parent_url}, port={node.port})"
            )

        self._mount_thread = threading.Thread(
            target=_run, daemon=True,
            name=f"cnb-mount-{getattr(self.node, 'node_id', 'node')}",
        )
        self._mount_thread.start()

    def _wait_registered(self, node: Any) -> bool:
        """Wait until the parent accepted the registration (node.parent_node_id set)."""
        deadline = time.monotonic() + REGISTER_ATTEMPTS * REGISTER_RETRY_SECONDS
        while not self._stopped.is_set():
            if getattr(node, "parent_node_id", None):
                return True
            if time.monotonic() >= deadline:
                return False
            time.sleep(REGISTER_RETRY_SECONDS)
            if getattr(node, "parent_node_id", None):
                return True
            try:
                node.register()
            except Exception:  # noqa: BLE001 — retried on the next round
                pass
        return False

    def _fail(self, reason: str) -> None:
        self.status = "failed"
        self.error = reason
        print(f"[cnb] mount failed; degrading to a plain instance: {reason}")

    def shutdown(self, join_timeout: float = 3.0) -> None:
        """Unmount: deregister + close the node bus (idempotent, best-effort)."""
        with self._lock:
            if self._stopped.is_set():
                return
            self._stopped.set()
            node = self.node
            self.node = None
        if node is None:
            return

        def _close() -> None:
            try:
                node.stop()
            except Exception:  # noqa: BLE001 — best-effort
                pass

        t = threading.Thread(
            target=_close, daemon=True,
            name=f"cnb-stop-{getattr(node, 'node_id', 'node')}",
        )
        t.start()
        t.join(join_timeout)
        self.status = "stopped"

    # ── 任务面动作 ───────────────────────────────────────

    def _action_run_task(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        node = self.node
        engine = self.engine
        args = payload.get("args")
        if not isinstance(args, dict):
            args = {}
        prompt = str(args.get("prompt") or "").strip()
        if not prompt:
            detail = {
                "ok": False,
                "accepted": False,
                "error": "missing prompt (args.prompt is required)",
            }
            if node is not None:
                node.audit("exec run_task rejected: missing prompt")
            self._uplink_audit(node, "exec.rejected", "run_task missing prompt")
            return detail
        session_id = args.get("session_id") or None
        task_params = args.get("task_params")
        task_params = dict(task_params) if isinstance(task_params, dict) else None
        # 任务分子（mol）结构化通道。task_params 原样承载任意
        # 结构化 JSON（mol_id / objective / acceptance / context_capsule /
        # depends_on / budget / model_tier 六要素等），随引擎任务原样到达
        # 吸收位；本层保存完整载荷副本供 task_records 验收回执查询。
        mol_id = ""
        if task_params:
            mol_id = str(task_params.get("mol_id")
                         or (task_params.get("mol") or {}).get("mol_id")
                         or "").strip()
        if not mol_id:
            mol_id = str(args.get("mol_id") or "").strip()
        rec = {
            "task_id": None,
            "ts": time.time(),
            "mol_id": mol_id,
            "prompt": prompt,
            "session_id": session_id,
            "task_params": dict(task_params or {}),
            "status": "accepted",
            "error": None,
            "content_len": 0,
            "acceptance": None,
        }
        if node is not None:
            node.audit(
                f"exec run_task accepted"
                + (f" mol_id={mol_id}" if mol_id else ""),
                task_params_keys=sorted(task_params) if task_params else [],
                mol_id=mol_id or None,
            )
        try:
            handle = engine.submit_async(
                prompt, session_id=session_id, task_params=task_params)
        except Exception as exc:  # noqa: BLE001 — engine not running etc.
            detail = {"ok": False, "accepted": False, "error": f"submit failed: {exc}"}
            if node is not None:
                node.audit("exec run_task submit failed", error=str(exc))
            return detail
        rec["task_id"] = handle.task_id
        self._remember_task(rec)
        # 任务已受理 -> 上行事件（皮层可见任务开始；事件带 mol_id 贯穿
        # 可追溯）
        if node is not None:
            ev = {
                "task_id": handle.task_id,
                "session_id": session_id,
                "node_id": node.node_id,
            }
            if mol_id:
                ev["mol_id"] = mol_id
            node.report_event("task_started", ev)
        self._spawn_watcher(handle, rec)
        return {
            "ok": True,
            "accepted": True,
            "action": "run_task",
            "task_id": handle.task_id,
            "node_id": getattr(node, "node_id", None),
            "mol_id": mol_id or None,
            "engine_state": engine.state.value,
            "message": ("mol accepted; acceptance receipt via task_records "
                        "when done" if mol_id else None),
        }

    def _remember_task(self, rec: Dict[str, Any]) -> None:
        """保存任务载荷记录（验收回执数据面，上限 100 条）。"""
        with self._task_records_lock:
            self._task_records.append(rec)

    def _find_task_record(self, task_id: Optional[str],
                          mol_id: Optional[str]) -> Optional[Dict[str, Any]]:
        with self._task_records_lock:
            for rec in reversed(self._task_records):
                if task_id and rec.get("task_id") == task_id:
                    return rec
                if mol_id and rec.get("mol_id") == mol_id:
                    return rec
            return None

    def _action_task_records(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """验收回执查询：本原子吸收位受理过的任务分子记录。

        皮层对任意原子 exec task_records，即可读取：
          - task_params 原样（完整 mol 六要素，无字段丢失——通道承载实证）；
          - 任务完成结果摘要（status / error / content_len——acceptance
            自检依据）；
        args: task_id=精确查询单个；mol_id=按分子号查询；n=最近 N 条。
        """
        args = payload.get("args")
        if not isinstance(args, dict):
            args = {}
        task_id = str(args.get("task_id") or "").strip() or None
        mol_id = str(args.get("mol_id") or "").strip() or None
        if task_id or mol_id:
            rec = self._find_task_record(task_id, mol_id)
            if rec is None:
                return {"ok": True, "action": "task_records",
                        "found": False, "records": []}
            return {"ok": True, "action": "task_records",
                    "found": True,
                    "records": [_jsonable(rec)]}
        n = int(args.get("n", 20))
        with self._task_records_lock:
            rows = list(self._task_records)[-max(1, n):]
        return {"ok": True, "action": "task_records",
                "count": len(rows),
                "records": [_jsonable(r) for r in rows]}

    def _action_status(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        node = self.node
        engine = self.engine
        return {
            "ok": True,
            "action": "status",
            "node_id": getattr(node, "node_id", None),
            "mount": self.status,
            "engine_state": engine.state.value,
            "version": _np_version(),
            "perm": dict(self.perm_summary),
            "tasks": engine.active_tasks(),
        }

    def _action_stop_task(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        engine = self.engine
        args = payload.get("args")
        if not isinstance(args, dict):
            args = {}
        task_id = str(args.get("task_id") or "").strip()
        if not task_id:
            self._node_audit("exec stop_task rejected: missing task_id")
            return {"ok": False, "action": "stop_task",
                    "error": "missing task_id (args.task_id is required)"}
        cancelled = engine.cancel_task(task_id)
        self._node_audit("exec stop_task",
                         task_id=task_id, cancelled=bool(cancelled))
        if cancelled:
            self._uplink_audit(self.node, "exec.stop_task",
                               f"task {task_id} cancel requested")
        return {
            "ok": cancelled,
            "action": "stop_task",
            "task_id": task_id,
            "message": "cancel requested" if cancelled else "no such active task",
        }

    # ── 状态面动作 ───────────────────────────────────────

    def _action_engine_state(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        engine = self.engine
        node = self.node
        return {
            "ok": True,
            "action": "engine_state",
            "state": engine.state.value,
            "running": engine.is_running(),
            "should_stop": engine.should_stop(),
            "active_tasks": len(engine.active_tasks()),
            "version": _np_version(),
            "mount": self.status,
        }

    def _action_inspect(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        engine = self.engine
        node = self.node
        preset = getattr(engine, "preset", None)
        last = None
        try:
            lr = engine.last_result
            if lr is not None:
                last = {
                    "status": getattr(lr, "status", None),
                    "error": str(getattr(lr, "error", "") or "")[:200] or None,
                    "content_len": len(getattr(lr, "final_content", "") or ""),
                }
        except Exception:  # noqa: BLE001
            last = None
        return {
            "ok": True,
            "action": "inspect",
            "node_id": getattr(node, "node_id", None),
            "kind": getattr(node, "kind", None),
            "level": getattr(node, "level", None),
            "parent": getattr(node, "parent_url", None),
            "mount": self.status,
            "engine_state": engine.state.value,
            "version": _np_version(),
            "preset": getattr(preset, "name", None),
            "preset_model": getattr(preset, "model", None),
            "slots": sorted(
                getattr(engine, "layer", None).keys()
                if hasattr(getattr(engine, "layer", None), "keys") else []
            ),
            "last_result": last,
            "actions": node_actions(node),
        }

    # ── 快照面动作（work rollback / crash rescue） ──────

    def _action_snapshot(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        engine = self.engine
        args = payload.get("args")
        if not isinstance(args, dict):
            args = {}
        description = str(args.get("description") or args.get("desc") or "").strip()
        tag = str(args.get("tag") or "cnb").strip() or "cnb"
        try:
            snap = engine.snapshot(description=description, tag=tag)
            self._node_audit("exec snapshot", tag=tag,
                             ok=True, detail=str(snap)[:300])
            return {"ok": True, "action": "snapshot", "tag": tag,
                    "result": _jsonable(snap)}
        except Exception as exc:  # noqa: BLE001
            self._node_audit("exec snapshot failed", tag=tag, error=str(exc))
            return {"ok": False, "action": "snapshot", "error": f"snapshot failed: {exc}"}

    def _action_rollback(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        engine = self.engine
        args = payload.get("args")
        if not isinstance(args, dict):
            args = {}
        snap_id = str(args.get("snap_id") or "").strip() or None
        try:
            result = engine.rollback(snap_id)
            self._node_audit("exec rollback", snap_id=snap_id,
                             ok=True, detail=str(result)[:300])
            return {"ok": True, "action": "rollback", "snap_id": snap_id,
                    "result": _jsonable(result)}
        except Exception as exc:  # noqa: BLE001
            self._node_audit("exec rollback failed", snap_id=snap_id,
                             error=str(exc))
            return {"ok": False, "action": "rollback", "error": f"rollback failed: {exc}"}

    def _action_undo(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        engine = self.engine
        try:
            result = engine.undo()
            self._node_audit("exec undo", ok=True, detail=str(result)[:300])
            return {"ok": True, "action": "undo", "result": _jsonable(result)}
        except Exception as exc:  # noqa: BLE001
            self._node_audit("exec undo failed", error=str(exc))
            return {"ok": False, "action": "undo", "error": f"undo failed: {exc}"}

    def _action_redo(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        engine = self.engine
        try:
            result = engine.redo()
            self._node_audit("exec redo", ok=True, detail=str(result)[:300])
            return {"ok": True, "action": "redo", "result": _jsonable(result)}
        except Exception as exc:  # noqa: BLE001
            self._node_audit("exec redo failed", error=str(exc))
            return {"ok": False, "action": "redo", "error": f"redo failed: {exc}"}

    def _action_list_snapshots(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        engine = self.engine
        try:
            snaps = engine.list_snapshots()
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "action": "list_snapshots",
                    "error": f"list_snapshots failed: {exc}"}
        # 摘要化：只取前 20 条的轻量字段（快照对象形态不定，统一 _jsonable）
        if isinstance(snaps, (list, tuple)):
            rows = []
            for s in snaps[:20]:
                if isinstance(s, dict):
                    rows.append({str(k): _jsonable(v)
                                 for k, v in list(s.items())[:6]})
                else:
                    rows.append(str(s)[:300])
            return {"ok": True, "action": "list_snapshots",
                    "count": len(snaps), "shown": len(rows),
                    "snapshots": rows}
        return {"ok": True, "action": "list_snapshots",
                "result": _jsonable(snaps)}

    def _action_mark_good(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        engine = self.engine
        args = payload.get("args")
        if not isinstance(args, dict):
            args = {}
        snap_id = str(args.get("snap_id") or "").strip() or None
        try:
            result = engine.mark_good(snap_id)
            self._node_audit("exec mark_good", snap_id=snap_id,
                             ok=True, detail=str(result)[:300])
            return {"ok": True, "action": "mark_good", "snap_id": snap_id,
                    "result": _jsonable(result)}
        except Exception as exc:  # noqa: BLE001
            self._node_audit("exec mark_good failed", snap_id=snap_id,
                             error=str(exc))
            return {"ok": False, "action": "mark_good",
                    "error": f"mark_good failed: {exc}"}

    # ── 运维面动作 ───────────────────────────────────────

    def _action_remount(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """皮层热改本原子引擎槽：args 直接作为 slot_values 透传 engine.remount。

        例：{"model": "openai_compat", "plugins": ["my_plugin.py"]}
        """
        engine = self.engine
        args = payload.get("args")
        if not isinstance(args, dict):
            args = {}
        slot_values = {k: v for k, v in args.items() if not k.startswith("_")}
        if not slot_values:
            self._node_audit("exec remount rejected: empty slot values")
            return {"ok": False, "action": "remount",
                    "error": "empty slot values (args = {slot: value, ...})"}
        try:
            engine.remount(**slot_values)
            self._node_audit("exec remount", slots=sorted(slot_values), ok=True)
            return {"ok": True, "action": "remount", "slots": sorted(slot_values)}
        except Exception as exc:  # noqa: BLE001
            self._node_audit("exec remount failed", slots=sorted(slot_values),
                             error=str(exc))
            return {"ok": False, "action": "remount",
                    "slots": sorted(slot_values),
                    "error": f"remount failed: {exc}"}

    def _action_reload_plugins(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """热重载外部插件：按引擎当前 plugins 槽值 remount（模块缓存失效后
        重装，编辑过的插件文件被拾取）。无外部插件时返回提示。"""
        engine = self.engine
        node = self.node
        plugins_result: Any = "no external plugins declared on this instance"
        try:
            plugins_val = engine.layer.get("plugins", None)
            if plugins_val is not None:
                engine.remount(plugins=plugins_val)
                declared = plugins_val if not callable(plugins_val) else "<factory>"
                plugins_result = {"remounted": True, "declared": declared}
        except Exception as exc:  # noqa: BLE001
            plugins_result = {"remounted": False, "error": str(exc)}
        if node is not None:
            node.audit("action reload_plugins", detail=str(plugins_result)[:400])
        return {"ok": True, "action": "reload_plugins", "plugins": plugins_result,
                "engine_state": engine.state.value}

    def _action_stop_engine(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """皮层下令停止本原子引擎（优雅关闭：停全部任务 -> 注销节点 -> 停引擎）。

        应答先返回皮层，引擎关闭延迟 1s 执行（保证回执送达）；
        CLI 神经进程收到后自然退出进程（主循环监控 should_stop）。
        """
        engine = self.engine
        node = self.node
        if node is not None:
            node.audit("action stop_engine from cortex")

        def _stop() -> None:
            time.sleep(1.0)
            try:
                engine.request_stop()
            except Exception:  # noqa: BLE001
                pass

        threading.Thread(target=_stop, daemon=True,
                         name=f"cnb-stop-engine-{getattr(node, 'node_id', '?')}").start()
        return {"ok": True, "action": "stop_engine",
                "message": "engine stop requested (graceful)",
                "engine_state": engine.state.value}

    # ── 任务 watcher ─────────────────────────────────────

    def _spawn_watcher(self, handle: Any, rec: Optional[Dict] = None) -> None:
        """Wait for an async task to finish; audit + report the result uplink.

        task_done 事件与审计携带 mol_id / acceptance（验收回执沿
        树回传皮层）；任务记录回填完成状态（task_records 可查）。
        任务成败计入节点行为基线（任务失败率聚合数据源）。
        """

        def _watch() -> None:
            try:
                result = handle.result()
            except BaseException as exc:  # noqa: BLE001
                result = exc
            failed = isinstance(result, BaseException)
            error = str(result) if failed else (getattr(result, "error", None) or "")
            status = "error" if failed else getattr(result, "status", "done")
            content = "" if failed else (getattr(result, "final_content", "") or "")
            summary = {
                "task_id": handle.task_id,
                "status": status,
                "error": error or None,
                "content_len": len(content),
            }
            # 任务成败计入行为基线（皮层分级消费）
            node = self.node
            if node is not None:
                try:
                    node.note_task_result(ok=(status != "error"))
                except Exception:  # noqa: BLE001
                    pass
            # 回填任务记录（验收回执数据面）
            mol_id = ""
            acceptance = None
            if rec is not None:
                mol_id = str(rec.get("mol_id") or "")
                tp = rec.get("task_params") or {}
                acceptance = tp.get("acceptance") or None
                if acceptance is None and isinstance(tp.get("mol"), dict):
                    acceptance = tp["mol"].get("acceptance")
                rec["status"] = status
                rec["error"] = error or None
                rec["content_len"] = len(content)
                rec["finished_at"] = time.time()
            if node is not None:
                try:
                    node.audit(
                        f"task finished {handle.task_id}"
                        + (f" mol_id={mol_id}" if mol_id else ""),
                        **summary)
                except Exception:  # noqa: BLE001
                    pass
                try:
                    ev = dict(summary)
                    if mol_id:
                        ev["mol_id"] = mol_id
                    if acceptance is not None:
                        # 验收规格原样回传（acceptance 自检依据；是否判定
                        # 通过由皮层/上层策略消费，内核不替裁决）
                        ev["acceptance"] = acceptance
                    node.report_event("task_done", ev)
                except Exception:  # noqa: BLE001 — uplink is best-effort
                    pass
            try:
                self.engine.forget_task(handle.task_id)
            except Exception:  # noqa: BLE001
                pass

        threading.Thread(target=_watch, daemon=True,
                         name=f"cnb-watch-{handle.task_id[:8]}").start()

    # ── 下行事件回调（cmd.stop / cmd.reload / perm_changed） ──

    def _on_stop(self) -> Dict[str, Any]:
        node = self.node
        engine = self.engine
        stopped = engine.stop_all_tasks()
        if node is not None:
            node.audit("cmd.stop", stopped=stopped)
        return {
            "ok": True,
            "stopped": stopped,
            "engine_state": engine.state.value,
            "message": "in-flight session tasks stopped; the instance stays running",
        }

    def _on_reload(self) -> Dict[str, Any]:
        node = self.node
        engine = self.engine
        cfg = read_env_config()
        applied: Dict[str, Any] = {
            "env": bool(cfg.get("enabled")),
            "managed": bool(cfg.get("managed")),
        }
        if cfg.get("enabled") and node is not None:
            # hot-updatable runtime knobs only — kind / level / parent / port are
            # fixed at registration (nervous-tree identity protection)
            node.heartbeat_interval = float(cfg["heartbeat"])
            if cfg.get("desc"):
                node.meta["desc"] = cfg["desc"]
            applied["heartbeat"] = node.heartbeat_interval
            applied["desc"] = node.meta.get("desc", "")
        # component / plugin hot reload: re-run the plugins literal slot through
        # the engine remount machinery (string addresses invalidate the module
        # cache, so edited plugin files are picked up). Only when the instance
        # actually declared external plugins.
        plugins_result: Any = "no external plugins declared on this instance"
        try:
            plugins_val = engine.layer.get("plugins", None)
            if plugins_val is not None:
                engine.remount(plugins=plugins_val)
                declared = (
                    plugins_val
                    if not callable(plugins_val)
                    else "<factory>"
                )
                plugins_result = {"remounted": True, "declared": declared}
        except Exception as exc:  # noqa: BLE001
            plugins_result = {"remounted": False, "error": str(exc)}
        detail = {
            "ok": True,
            "action": "reload",
            "config": applied,
            "plugins": plugins_result,
            "engine_state": engine.state.value,
        }
        if node is not None:
            node.audit("cmd.reload", detail=str(detail)[:400])
        return detail

    def _on_perm_changed(self, summary: Any) -> None:
        self.perm_summary = dict(summary or {})
        node = self.node
        if node is not None:
            node.audit("perm_changed", summary=self.perm_summary)

    # ── helpers ──────────────────────────────────────────

    def _node_audit(self, msg: str, **extra) -> None:
        """节点本地审计（node 可能为 None 时安全跳过）。

        供各变更动作记录「执行了什么、结果如何」——皮层 exec 的变更
        动作在节点审计环留痕，subpoena 取证（audit scope）可检索。
        """
        node = self.node
        if node is None:
            return
        try:
            node.audit(msg, **extra)
        except Exception:  # noqa: BLE001 — 审计失败不影响动作回执
            pass

    @staticmethod
    def _uplink_audit(node: Optional[Any], event: str, detail: str) -> None:
        if node is None:
            return
        try:
            node.report_audit(event, detail)
        except Exception:  # noqa: BLE001 — uplink is best-effort
            pass


def node_actions(node: Optional[Any]) -> list:
    """节点已注册的内核动作名（皮层 inspect 可见原子能力面）。"""
    if node is None:
        return []
    try:
        return node.list_actions()
    except Exception:  # noqa: BLE001
        return []


# ── engine hook ─────────────────────────────────────────

def setup_cnb(engine: Any) -> None:
    """Auto-mount hook called by NorpEngine.start() (runtime.engine._setup_cnb).

    Returns immediately; mounting runs on a background thread inside CnbAdapter.
    Never raises — every failure path degrades to a plain single instance.
    """
    cfg = read_env_config()
    if cfg.get("managed"):
        engine._cnb_managed = True
        print(
            "[cnb] NORP_CNB_MANAGED=1: kernel mounting skipped "
            "(managed mode; the upper layer builds its own node)"
        )
        return
    if not cfg.get("enabled"):
        return
    try:
        from norpagent.cnb import NervousNode
    except Exception as exc:  # noqa: BLE001 — package not installed
        print(f"[cnb] norpagent.cnb unavailable; degrading to a plain instance: {exc}")
        return
    meta: Dict[str, Any] = {"engine": "norpagent", "auto": True}
    if cfg.get("desc"):
        meta["desc"] = cfg["desc"]
    try:
        node = NervousNode(
            node_id=cfg["node_id"],
            kind=cfg["kind"],
            level=cfg["level"],
            parent_url=cfg["parent"],
            port=cfg["port"],
            meta=meta,
            heartbeat_interval=cfg["heartbeat"],
        )
    except Exception as exc:  # noqa: BLE001
        print(f"[cnb] node build failed; degrading to a plain instance: {exc}")
        return
    adapter = CnbAdapter(engine, node, cfg)
    with engine._cnb_lock:
        engine._cnb = adapter
    adapter.mount()


__all__ = [
    "CnbAdapter",
    "setup_cnb",
    "read_env_config",
    "KERNEL_ACTIONS",
    "CNB_ENV_KEYS",
    "ENV_NODE",
    "ENV_KIND",
    "ENV_LEVEL",
    "ENV_PARENT",
    "ENV_PORT",
    "ENV_HEARTBEAT",
    "ENV_DESC",
    "ENV_MANAGED",
    "ENV_CLI",
]
