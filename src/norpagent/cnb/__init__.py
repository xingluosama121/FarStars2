# Copyright (c) 2026 xingluosama121, MIT Licensed
"""norpagent.cnb — 中枢神经总线（Central Nervous Bus, CNB）内核模块。

v1.0.7 起 CNB 完成内核集成：神经实现从外挂独立包（nervous_bus）内化为
norpagent 的内核子模块。与「外挂模块」时期的差异：

- 归属：nervous_bus 是 src/ 下与 norpagent 平级的独立顶层包，自带版本号；
  本包是 norpagent 内核的一部分，版本跟随 norpagent（无独立版本号）。
  ``import norpagent`` 即完成装配；旧名 nervous_bus 保留为兼容 shim
  （re-export 本包全部符号与子模块），1.0.6 及更早的脚本/命令零改动继续可用。
- 能力：NervousNode 提供 exec 动作注册表（register_action），皮层 cmd.exec
  的动作直接路由到注册处理器；引擎绑定层 norpagent.cnb.engine 把
  NorpEngine 公开 API（任务/快照/回滚/重载/运维）注册为节点的内核动作面，
  皮层可对任意层级原子下发——CNB 不再只是传输层外挂，而是可操作内核的能力面。
- 运行形态：norpagent cortex/node 子命令（本包 cli）默认装配完整内核引擎，
  每个神经原子都是一个真实可执行任务的 norpagent 实例；--bare 回到纯神经
  空壳（探针）。普通 GUI 实例仍按 NORP_CNB_* env 可选装配（单实例可选挂载）。

模块：
  protocol     协议层（消息信封、上行/下行、等级、权限原子）
  topology     树状拓扑链（注册/注销、祖先判定、无环与等级校验）
  permissions  神经权限表（皮层对任意层级任意原子的操作权限控制）
  bus          传输层（零依赖 HTTP，每节点一个总线端点）
  node         CNB 节点（总线/心跳/上行/下行 + exec 动作注册表）
  cortex       大脑皮层（根节点 + 控制 API + REPL）
  engine       引擎绑定层（CnbAdapter：内核动作面 + env 自动挂载；NorpEngine 集成）
  cli          命令行入口（cortex / node / topo / ping / exec / stop / ...）
  demo         快速演示（1 个皮层 + 树状三级节点，同进程模拟）

兼容说明：``python -m nervous_bus.cli``、``from nervous_bus import NervousNode``
等旧写法经由 nervous_bus shim 落到本包，行为与 1.0.6 一致。
"""

from .protocol import (
    PROTO_VERSION,
    LEVEL_CORTEX, LEVEL_DIRECTOR, LEVEL_AGENT, LEVEL_ATOM, LEVEL_MAX,
    DEFAULT_CORTEX_PORT, DEFAULT_HOST,
    DIR_UPLINK, DIR_DOWNLINK, DIR_ACK,
    UPLINK_TYPES, DOWNLINK_TYPES,
    PERMISSION_ATOMS, is_valid_perm,
    make_envelope, sanitize_uplink_payload, check_uplink_payload,
    # v2.0.0：冻结态 / 传票取证 / 行为基线
    FROZEN_ALLOWED_ACTIONS,
    SUBPOENA_BASIS, SUBPOENA_TIERS_KB, SUBPOENA_MAX_KB,
    SUBPOENA_ENVELOPE,
    is_valid_subpoena_basis, is_valid_subpoena_tier,
)
from .topology import Topology, NodeInfo
from .permissions import NeuralPermissionTable, PermRule
from .node import NervousNode
from .cortex import Cortex
# 引擎绑定层（NorpEngine 内核动作面注册 + env 自动挂载）。顶层不导入本包
# 其它符号，仅导入 engine 模块本身：setup_cnb 的导入路径保持延迟（由
# NorpEngine.start() 触发），此处导入只让 ``norpagent.cnb.CnbAdapter`` 等
# 在 import norpagent 后直接可用（内核集成体验：CNB 能力随包就绪）。
from . import engine  # noqa: E402,F401
from .engine import (  # noqa: E402,F401
    CnbAdapter,
    setup_cnb,
    read_env_config,
    KERNEL_ACTIONS,
)

# v1.0.7 起 CNB 并入内核：版本跟随 norpagent（publish_pypi.ps1 校验一致）。
# 与 norpagent/__init__.py 的 __version__ 保持同步。
__version__ = "2.0.1"

__all__ = [
    "__version__",
    "PROTO_VERSION",
    "LEVEL_CORTEX", "LEVEL_DIRECTOR", "LEVEL_AGENT", "LEVEL_ATOM", "LEVEL_MAX",
    "DEFAULT_CORTEX_PORT", "DEFAULT_HOST",
    "DIR_UPLINK", "DIR_DOWNLINK", "DIR_ACK",
    "UPLINK_TYPES", "DOWNLINK_TYPES",
    "PERMISSION_ATOMS", "is_valid_perm",
    "make_envelope", "sanitize_uplink_payload", "check_uplink_payload",
    # v2.0.0：冻结态 / 传票取证 / 行为基线
    "FROZEN_ALLOWED_ACTIONS",
    "SUBPOENA_BASIS", "SUBPOENA_TIERS_KB", "SUBPOENA_MAX_KB",
    "SUBPOENA_ENVELOPE",
    "is_valid_subpoena_basis", "is_valid_subpoena_tier",
    "Topology", "NodeInfo",
    "NeuralPermissionTable", "PermRule",
    "NervousNode", "Cortex",
    # 引擎绑定层（v1.0.7 内核集成）
    "CnbAdapter", "setup_cnb", "read_env_config", "KERNEL_ACTIONS",
]
