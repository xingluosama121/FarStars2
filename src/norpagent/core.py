# Copyright (c) 2026 xingluosama121, MIT Licensed
"""norpagent.core — 元框架态命名空间：最小内核四构件 + 注册三件套。

架构书 §3.1（拍板 3A，2026-09-09）：三态同核共存，元框架态的入口面为
``norpagent.core`` 命名空间、``npa()`` 的裸装配路径与注册三件套
``register_slot() / register_layer() / register_hook()``。

- 最小内核四构件：槽位表（arch）/ 注册表（kernel）/ 事件总线（kernel）/
  地址函数（arch）；
- 注册三件套：槽位热插拔（register_slot）、钩子层注册（register_layer）、
  自定义钩子注册（register_hook）；
- 裸装配路径：install_core()（零磁盘依赖最小装配）+ build_embedded_preset()
  （嵌入式预设）——不经前端/UI 的最小可用装配。

用法::

    import norpagent.core as core

    core.register_slot("my_slot", ...)                    # 槽位表热插拔
    layer = core.register_layer("L10_net", order=100)     # 注册自定义钩子层
    hook = core.register_hook("before_net_call", mutating=True)  # 注册自定义钩子
    hook.subscribe(my_fn)

    reg = core.Registry()
    core.install_core(reg)                                # 裸装配（最小内核）
    reg.register_preset(core.build_embedded_preset())
"""

from __future__ import annotations

from typing import Any, Callable, Dict, Optional

from norpagent.arch import (  # noqa: F401  — 槽位表 + 地址函数（最小内核四构件之二）
    ArchLayer,
    SlotSpec,
    SlotError,
    SLOT_SPECS,
    get_slot,
    all_slot_names,
    snapshot_slots,
    is_builtin_slot,
    register_slot,
    unregister_slot,
    resolve_address,
    is_address_like,
    call_factory,
    AddressError,
)
from norpagent.kernel import (  # noqa: F401  — 注册表 + 事件总线（最小内核四构件之二）
    Registry,
    EventBus,
    EventType,
    AgentEvent,
    ComponentError,
)
from norpagent.builtin import install_core  # noqa: F401  — 裸装配路径：零磁盘依赖最小装配
from norpagent.modes import build_embedded_preset  # noqa: F401  — 裸装配路径：嵌入式预设
from norpagent.hooks import HookLayer, HookSystem, get_default_system


def _hook_system(system: Any = None) -> HookSystem:
    """把 system 参数解析为 HookSystem（None = 进程默认钩子系统）。"""
    if system is None:
        return get_default_system()
    if isinstance(system, HookSystem):
        return system
    hooks = getattr(system, "hooks", None)
    if isinstance(hooks, HookSystem):
        return hooks
    raise TypeError(
        "cannot resolve hook system: pass a HookSystem / Registry / AgentRuntime "
        f"(got {type(system).__name__})"
    )


def register_layer(layer: Any = None, *, name: Optional[str] = None,
                   order: int = 0, description: str = "",
                   hooks: Optional[Dict[str, Any]] = None,
                   system: Any = None) -> HookLayer:
    """注册一个钩子层（元框架态入口；架构书 §3.1 注册三件套之一）。

    - ``layer`` 为 HookLayer 实例：直接装入目标钩子系统；
    - 否则以 name / order / description 构造新层；``hooks`` 为可选声明表
      ``{钩子名: {mutating: bool, description: str, payload_keys: tuple, order: int}}``
      （spec 为 bool 时等价于 ``{"mutating": bool}``）。

    返回该 HookLayer；重名钩子保留既有定义（与 HookSystem.install_layer 语义一致）。
    """
    if isinstance(layer, HookLayer):
        target_layer = layer
    else:
        layer_name = str(name or layer or "").strip()
        if not layer_name:
            raise ValueError(
                "register_layer needs a layer name or a HookLayer instance")
        target_layer = HookLayer(layer_name, order=int(order),
                                 description=str(description or ""))
        for hook_name, spec in dict(hooks or {}).items():
            if isinstance(spec, bool):
                spec = {"mutating": spec}
            spec = dict(spec or {})
            target_layer.hook(
                str(hook_name),
                mutating=bool(spec.get("mutating", False)),
                description=str(spec.get("description", "")),
                payload_keys=tuple(spec.get("payload_keys", ())),
                order=int(spec.get("order", 0)),
            )
    _hook_system(system).install_layer(target_layer)
    return target_layer


def register_hook(name: str, fn: Optional[Callable] = None, *,
                  layer: Optional[str] = None, mutating: bool = False,
                  description: str = "", payload_keys: tuple = (),
                  order: int = 0, system: Any = None):
    """注册一个自定义钩子（元框架态入口；架构书 §3.1 注册三件套之一）。

    - 钩子未定义则定义（归属自定义层或 dynamic 层）；
    - 已定义则保留既有定义（不覆盖标准钩子）；
    - 传入 ``fn`` 时同时订阅该钩子。

    返回钩子的绑定式 API（BoundHook）。
    """
    target = _hook_system(system)
    bound = target.get(name)
    if bound is None:
        bound = target.define_hook(
            str(name), layer=layer, mutating=mutating,
            description=description, payload_keys=payload_keys, order=order,
        )
    if fn is not None:
        bound.subscribe(fn)
    return bound


__all__ = [
    # ── 注册三件套（元框架态入口） ──
    "register_slot",
    "register_layer",
    "register_hook",
    "unregister_slot",
    # ── 最小内核四构件：槽位表 ──
    "ArchLayer",
    "SlotSpec",
    "SlotError",
    "SLOT_SPECS",
    "get_slot",
    "all_slot_names",
    "snapshot_slots",
    "is_builtin_slot",
    # ── 最小内核四构件：地址函数 ──
    "resolve_address",
    "is_address_like",
    "call_factory",
    "AddressError",
    # ── 最小内核四构件：注册表 / 事件总线 ──
    "Registry",
    "EventBus",
    "EventType",
    "AgentEvent",
    "ComponentError",
    # ── 裸装配路径 ──
    "install_core",
    "build_embedded_preset",
    # ── 钩子基础设施 ──
    "HookLayer",
    "HookSystem",
    "get_default_system",
]
