# Copyright (c) 2026 xingluosama121, MIT Licensed
"""norpagent.cnb.slots — 通用槽位（Universal Slots）：CNB 节点的 ≤64 槽位挂载面。

R-024（2026-09-11 修订版）：
- 神经总线上每一节点不再「硬挂」固定的 agent 实例形态，而是提供最多 64 个
  通用槽位；槽位走神经总线，什么都可以挂载：model、tools、plugins、自定义
  模块……CNB 由此成为「槽位连接器」的多实例延伸扩展（单实例时槽位连接本地
  部件，多实例时经神经树跨进程连接同一套槽位协议）。
- 国王 2026-09-11 口谕修订：**norpagent 完整实例不被抛弃**——它被包装为
  ``NorpAgentModule``，作为一个标准可插拔模块挂入任意节点的任意空闲槽位。
  换言之，「不再挂 agent 实例」的正确读法是「agent 实例从节点的硬编码内置
  形态，变为槽位上的一个普通模块」：可插、可拔、可描述、可替换。

模块协议（MountableModule）：
    kind        模块种类标识（"norpagent-instance" / "model" / "tools" /
                "plugins" / "generic" / 任意自定义）
    describe()  白盒描述（可看）
    on_mount()  挂载回调（节点侧生效逻辑）
    on_unmount() 卸载回调
    actions()   该模块提供的 exec 动作表（node.exec 路由可达）
    heartbeat() 心跳附加贡献（随节点心跳压缩上汇）

槽位协议（SlotBay）：
    mount(slot_id, module)    挂载（容量 ≤64、id 唯一、动作名不冲突；事务性）
    unmount(slot_id)          卸载（回调 + 审计）
    describe() / list() / count() / free()
    action_index()            槽位动作总表（node.exec 路由的二级命中面）
    heartbeat()               模块心跳贡献聚合（slot_id -> dict）

所有挂载/卸载动作进入节点审计环（可溯）；槽位状态经 ``slot_list`` /
``slot_describe`` exec 动作上总线（可查）。本模块零第三方依赖。
"""

from __future__ import annotations

import time
from typing import Any, Callable, Dict, List, Optional

# 单节点通用槽位上限（R-024 裁决：≤64）
MAX_SLOTS = 64

# 模块种类：norpagent 完整实例（口谕：可插入 CNB 节点的标准模块）
KIND_NORPAGENT = "norpagent-instance"
KIND_GENERIC = "generic"


class SlotError(RuntimeError):
    """槽位操作错误（容量满 / id 冲突 / 动作冲突 / 模块非法等）。"""


# ─────────────────────────────────────────────────────────
# 模块协议
# ─────────────────────────────────────────────────────────

class MountableModule:
    """可挂载模块基类（协议的最小实现；自定义模块可 duck-typing 直接实现同名方法）。"""

    kind = KIND_GENERIC

    def __init__(self, label: str = "", meta: Optional[Dict[str, Any]] = None) -> None:
        self.label = label or self.kind
        self.meta = dict(meta or {})

    # ── 白盒 ──────────────────────────────────────────────

    def describe(self) -> Dict[str, Any]:
        return {
            "kind": self.kind,
            "label": self.label,
            "meta": dict(self.meta),
            "ok": self.ok(),
        }

    def ok(self) -> bool:
        """模块健康自述（默认 True；模块可覆写做轻量自检）。"""
        return True

    # ── 生命周期（默认无操作） ───────────────────────────

    def on_mount(self, node: Any) -> None:
        """挂载回调：模块在节点侧生效逻辑（异常 → 挂载失败，事务不提交）。"""

    def on_unmount(self, node: Any) -> None:
        """卸载回调（尽力而为；异常不阻塞卸载，由槽位层记审计）。"""

    # ── 能力面 ───────────────────────────────────────────

    def actions(self) -> Dict[str, Callable[[Dict[str, Any]], Any]]:
        """该模块提供的 exec 动作表（动作名 -> handler(payload) -> dict）。"""
        return {}

    def heartbeat(self) -> Optional[Dict[str, Any]]:
        """心跳附加贡献（返回 None 表示无贡献）。"""
        return None


class GenericModule(MountableModule):
    """通用模块：任意可挂载物（model / tools / plugins / 自定义载荷）。

    载荷是自描述 JSON（``payload``），随槽位描述上总线——「什么都可以挂载」
    的最小可信形态：不预设字段、不做语义裁剪、如实呈现挂载了什么。
    """

    def __init__(self, kind: str = KIND_GENERIC, label: str = "",
                 payload: Optional[Dict[str, Any]] = None,
                 meta: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(label=label or kind, meta=meta)
        self.kind = str(kind or KIND_GENERIC)
        self.payload = dict(payload or {})

    def describe(self) -> Dict[str, Any]:
        d = super().describe()
        d["payload"] = _jsonable_light(self.payload)
        return d


class NorpAgentModule(MountableModule):
    """norpagent 完整实例模块（国王 2026-09-11 修订：实例可插入 CNB 节点）。

    把一个真实运行的 NorpEngine（完整 norpagent 实例）包装成标准模块：
    - ``actions()``：内核动作面（KERNEL_ACTIONS）全量导出——挂到节点后，
      cmd.exec 经槽位面即可操作该实例（任务 / 快照 / 回滚 / 维护）；
    - ``describe()``：实例状态白盒（引擎态 / 任务数 / 版本 / 预设 / 动作数）；
    - ``heartbeat()``：实例忙闲随节点心跳压缩上汇。

    两种使用方式等价：
    1. CnbAdapter.bind_actions 自动把引擎实例挂入节点槽位（默认槽位
       ``norpagent``）——CLI 神经进程 / env 自动挂载路径；
    2. 手工 ``node.mount_module("norpagent", NorpAgentModule(engine))``——
       自定义节点装配 / 多实例编排（一个节点一个实例模块，动作名唯一）。
    """

    kind = KIND_NORPAGENT

    def __init__(self, engine: Any, adapter: Any = None, label: str = "",
                 meta: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(label=label or "norpagent complete instance", meta=meta)
        self.engine = engine
        if adapter is None:
            # 独立处理器宿主（node=None）：动作处理器只依赖引擎公开 API，
            # 审计面为空时安全跳过（见 CnbAdapter 的 node 空值保护）。
            from .engine import CnbAdapter

            adapter = CnbAdapter(engine, None, {})
        self.adapter = adapter

    # ── 白盒 ──────────────────────────────────────────────

    def describe(self) -> Dict[str, Any]:
        d = super().describe()
        state = "?"
        tasks: Any = None
        preset = None
        version = None
        try:
            state = self.engine.state.value
        except Exception:  # noqa: BLE001 — 描述永不抛错
            pass
        try:
            tasks = len(self.engine.active_tasks())
        except Exception:  # noqa: BLE001
            pass
        try:
            preset = getattr(self.engine.preset, "name", None)
        except Exception:  # noqa: BLE001
            pass
        try:
            from norpagent import __version__ as ver

            version = str(ver)
        except Exception:  # noqa: BLE001
            pass
        d.update({
            "engine_state": state,
            "active_tasks": tasks,
            "preset": preset,
            "version": version,
            "actions": sorted(self.actions().keys()),
        })
        return d

    def ok(self) -> bool:
        try:
            return bool(self.engine.is_running())
        except Exception:  # noqa: BLE001
            return True

    # ── 能力面 ───────────────────────────────────────────

    def actions(self) -> Dict[str, Callable[[Dict[str, Any]], Any]]:
        try:
            from .engine import KERNEL_ACTIONS
        except Exception:  # noqa: BLE001 — 极端导入失败时无动作面
            return {}
        out: Dict[str, Callable[[Dict[str, Any]], Any]] = {}
        for action in sorted(KERNEL_ACTIONS):
            handler = getattr(self.adapter, f"_action_{action}", None)
            if callable(handler):
                out[action] = handler
        return out

    def heartbeat(self) -> Optional[Dict[str, Any]]:
        try:
            return {
                "module": "norpagent",
                "engine_state": self.engine.state.value,
                "active_tasks": len(self.engine.active_tasks()),
            }
        except Exception:  # noqa: BLE001 — 心跳贡献永不打断节点心跳
            return None


def build_module_from_spec(spec: Dict[str, Any]) -> MountableModule:
    """由自描述 JSON 规格构建模块（bus 侧 slot_mount 动作使用）。

    规格：{"kind": "model"|"tools"|"plugins"|..., "label": ..., "payload": {...}}
    norpagent 完整实例模块需要活的引擎对象，不能经 JSON 规格构建——如实拒绝。
    """
    if not isinstance(spec, dict):
        raise SlotError(f"module spec must be a dict, got {type(spec).__name__}")
    kind = str(spec.get("kind") or KIND_GENERIC).strip() or KIND_GENERIC
    if kind in (KIND_NORPAGENT, "norpagent", "engine"):
        raise SlotError(
            "norpagent-instance modules cannot be built from a JSON spec "
            "(a live engine is required); mount NorpAgentModule directly")
    payload = spec.get("payload")
    if payload is not None and not isinstance(payload, dict):
        raise SlotError("module spec payload must be a dict")
    return GenericModule(kind=kind, label=str(spec.get("label") or ""),
                         payload=payload or {})


# ─────────────────────────────────────────────────────────
# 槽位与槽位湾
# ─────────────────────────────────────────────────────────

class UniversalSlot:
    """一个通用槽位：槽位号 + 已挂模块 + 挂载元数据。"""

    def __init__(self, slot_id: str, module: MountableModule,
                 meta: Optional[Dict[str, Any]] = None) -> None:
        self.slot_id = str(slot_id)
        self.module = module
        self.meta = dict(meta or {})
        self.mounted_at = time.time()

    def describe(self) -> Dict[str, Any]:
        d = {
            "slot_id": self.slot_id,
            "kind": getattr(self.module, "kind", KIND_GENERIC),
            "label": getattr(self.module, "label", ""),
            "mounted_at": self.mounted_at,
            "meta": dict(self.meta),
        }
        try:
            d["module"] = self.module.describe()
        except Exception as exc:  # noqa: BLE001 — 描述失败如实入白盒
            d["module"] = {"error": f"{type(exc).__name__}: {exc}"[:300]}
        return d


class SlotBay:
    """节点槽位湾：≤64 通用槽位的挂载管理（事务性 + 审计 + 动作索引）。"""

    def __init__(self, owner: Any = None, max_slots: int = MAX_SLOTS) -> None:
        self.owner = owner
        self.max_slots = int(max_slots)
        self._slots: Dict[str, UniversalSlot] = {}
        self._action_index: Dict[str, Callable[[Dict[str, Any]], Any]] = {}

    # ── 查询面 ───────────────────────────────────────────

    def count(self) -> int:
        return len(self._slots)

    def free(self) -> int:
        return max(0, self.max_slots - len(self._slots))

    def get(self, slot_id: str) -> Optional[UniversalSlot]:
        return self._slots.get(str(slot_id))

    def list(self) -> List[UniversalSlot]:
        return list(self._slots.values())

    def describe(self) -> List[Dict[str, Any]]:
        return [s.describe() for s in self._slots.values()]

    def action_index(self) -> Dict[str, Callable[[Dict[str, Any]], Any]]:
        return self._action_index

    def heartbeat(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {}
        for slot in self._slots.values():
            try:
                contrib = self.module_of(slot).heartbeat()
            except Exception as exc:  # noqa: BLE001 — 如实降级
                contrib = {"error": f"{type(exc).__name__}: {exc}"[:200]}
            if contrib is not None:
                out[slot.slot_id] = contrib
        return out

    @staticmethod
    def module_of(slot: UniversalSlot) -> MountableModule:
        return slot.module

    # ── 变更面 ───────────────────────────────────────────

    def mount(self, slot_id: str, module: Any,
              meta: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """挂载模块（事务性）：容量 / id / 模块协议 / 动作冲突全部先校验。

        校验通过才执行 module.on_mount，随后提交槽位与动作索引；
        on_mount 抛错 => 挂载失败、槽位不提交（原状态零变化）。
        """
        sid = str(slot_id or "").strip()
        if not sid:
            raise SlotError("slot_id must be a non-empty string")
        if sid in self._slots:
            raise SlotError(f"slot {sid!r} is already occupied "
                            f"(unmount it first)")
        if len(self._slots) >= self.max_slots:
            raise SlotError(
                f"slot capacity exceeded: {len(self._slots)}/{self.max_slots} "
                f"(R-024: at most {self.max_slots} universal slots per node)")
        if module is None:
            raise SlotError("module must not be None")
        for attr in ("describe", "actions"):
            if not callable(getattr(module, attr, None)):
                raise SlotError(
                    f"module {type(module).__name__} does not satisfy the "
                    f"mountable protocol (missing {attr}())")
        actions = module.actions()
        if not isinstance(actions, dict):
            raise SlotError("module.actions() must return a dict")
        conflicts = sorted(set(actions) & set(self._action_index))
        if conflicts:
            raise SlotError(f"action name conflict on mount: {conflicts} "
                            f"(already provided by existing slots)")
        # on_mount（失败 => 不提交）
        on_mount = getattr(module, "on_mount", None)
        if callable(on_mount):
            on_mount(self.owner)
        slot = UniversalSlot(sid, module, meta=meta)
        self._slots[sid] = slot
        for name, handler in actions.items():
            if not callable(handler):
                # 回滚刚提交的槽位（不可达分支的防御：协议实现者违约）
                del self._slots[sid]
                raise SlotError(f"action {name!r} handler is not callable")
            self._action_index[str(name)] = handler
        self._audit(f"slot mounted: {sid} <- {getattr(module, 'kind', '?')} "
                    f"({getattr(module, 'label', '')})")
        return self.get(sid).describe()

    def unmount(self, slot_id: str) -> Dict[str, Any]:
        """卸载模块：回调（尽力而为）→ 移除槽位与动作索引 → 审计。"""
        sid = str(slot_id or "").strip()
        slot = self._slots.get(sid)
        if slot is None:
            raise SlotError(f"slot {sid!r} is not occupied")
        on_unmount = getattr(slot.module, "on_unmount", None)
        if callable(on_unmount):
            try:
                on_unmount(self.owner)
            except Exception as exc:  # noqa: BLE001 — 卸载不被回调异常阻塞
                self._audit(f"slot unmount callback error on {sid}: "
                            f"{type(exc).__name__}: {exc}")
        del self._slots[sid]
        self._rebuild_action_index()
        self._audit(f"slot unmounted: {sid}")
        return {
            "slot_id": sid,
            "kind": getattr(slot.module, "kind", KIND_GENERIC),
            "label": getattr(slot.module, "label", ""),
            "unmounted": True,
        }

    def _rebuild_action_index(self) -> None:
        index: Dict[str, Callable[[Dict[str, Any]], Any]] = {}
        for slot in self._slots.values():
            try:
                actions = slot.module.actions() or {}
            except Exception:  # noqa: BLE001 — 违约模块不拖垮索引重建
                actions = {}
            for name, handler in actions.items():
                if callable(handler):
                    index[str(name)] = handler
        self._action_index = index

    def _audit(self, msg: str) -> None:
        owner = self.owner
        if owner is None:
            return
        try:
            owner.audit(msg)
        except Exception:  # noqa: BLE001 — 审计失败不影响槽位操作
            pass


def _jsonable_light(obj: Any, depth: int = 0) -> Any:
    """轻量 JSON 收敛（槽位描述用；深对象截断为字符串，防描述爆炸）。"""
    if depth > 4:
        return str(obj)[:300]
    if isinstance(obj, dict):
        return {str(k): _jsonable_light(v, depth + 1)
                for k, v in list(obj.items())[:64]}
    if isinstance(obj, (list, tuple)):
        return [_jsonable_light(v, depth + 1) for v in list(obj)[:64]]
    if isinstance(obj, (bool, int, float)) or obj is None:
        return obj
    s = str(obj)
    return s if len(s) <= 300 else s[:300] + "..."


__all__ = [
    "MAX_SLOTS",
    "KIND_NORPAGENT",
    "KIND_GENERIC",
    "SlotError",
    "MountableModule",
    "GenericModule",
    "NorpAgentModule",
    "build_module_from_spec",
    "UniversalSlot",
    "SlotBay",
]
