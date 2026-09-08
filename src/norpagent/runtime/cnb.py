# Copyright (c) 2026 xingluosama121, MIT Licensed
"""CNB 引擎绑定层转发（v1.0.7 内核集成）。

v1.0.6 及更早的 CNB 自动挂载适配器（CnbAdapter / setup_cnb）本体已迁入
norpagent.cnb.engine —— CNB 从外挂独立包内化为 norpagent 内核子模块后，
引擎绑定层归属 CNB 模块自身。本模块保留原名原路径作为转发层：

- NorpEngine.start() 的 _setup_cnb() 仍 ``from norpagent.runtime.cnb import
  setup_cnb``（engine.py 零改动）；
- 1.0.6 时代 ``from norpagent.runtime.cnb import CnbAdapter, setup_cnb,
  read_env_config, EXEC_ACTIONS`` 等旧导入继续可用。

新代码建议直接 ``from norpagent.cnb.engine import ...``。
"""

from norpagent.cnb.engine import (  # noqa: F401
    CnbAdapter,
    setup_cnb,
    read_env_config,
    KERNEL_ACTIONS,
    CNB_ENV_KEYS,
    ENV_NODE,
    ENV_KIND,
    ENV_LEVEL,
    ENV_PARENT,
    ENV_PORT,
    ENV_HEARTBEAT,
    ENV_DESC,
    ENV_MANAGED,
    ENV_CLI,
)
from norpagent.cnb.engine import *  # noqa: F401,F403

# 1.0.6 兼容名：旧白名单被内核动作面（KERNEL_ACTIONS）取代，保留引用防断裂
EXEC_ACTIONS = frozenset(KERNEL_ACTIONS)

__all__ = [
    "CnbAdapter",
    "setup_cnb",
    "read_env_config",
    "KERNEL_ACTIONS",
    "EXEC_ACTIONS",
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
