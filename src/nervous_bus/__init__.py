# -*- coding: utf-8 -*-
"""nervous_bus — 中枢神经总线兼容 shim（v1.0.7 内核集成后）。

v1.0.7 起 CNB 完成内核集成：神经实现（protocol/topology/permissions/bus/
node/cortex）、引擎绑定层（engine）与命令行（cli）全部迁入
``norpagent.cnb``（norpagent 内核子模块，版本跟随 norpagent）。

本包保留为**兼容 shim**：re-export norpagent.cnb 的全部符号与子模块，
保证 1.0.6 及更早的脚本、文档、测试零改动继续可用：

    from nervous_bus import NervousNode, Cortex        # OK
    from nervous_bus.node import NervousNode            # OK（子模块注入）
    from nervous_bus.cli import main                    # OK（薄文件转发）
    python -m nervous_bus.cli cortex ...                # OK（薄文件转发）
    python -m nervous_bus.demo                          # OK（薄文件转发）

新代码请直接使用内核模块：``from norpagent.cnb import ...`` /
``from norpagent import cnb``。
"""

import sys as _sys

# 顶层 re-export：norpagent.cnb 的全部公开符号（__all__ 同名）
from norpagent.cnb import *  # noqa: F401,F403
from norpagent.cnb import (  # noqa: F401
    PROTO_VERSION,
    LEVEL_CORTEX, LEVEL_DIRECTOR, LEVEL_AGENT, LEVEL_ATOM, LEVEL_MAX,
    DEFAULT_CORTEX_PORT, DEFAULT_HOST,
    DIR_UPLINK, DIR_DOWNLINK, DIR_ACK,
    UPLINK_TYPES, DOWNLINK_TYPES,
    PERMISSION_ATOMS, is_valid_perm,
    make_envelope, sanitize_uplink_payload, check_uplink_payload,
    Topology, NodeInfo,
    NeuralPermissionTable, PermRule,
    NervousNode, Cortex,
)

# 版本跟随 norpagent（无独立版本号）
from norpagent import __version__ as __version__  # noqa: F401

# 子模块别名注入：from nervous_bus.node import NervousNode 等旧引用继续可用。
# cli/demo 不在此注入——它们有物理薄文件（nervous_bus/cli.py、demo.py），
# 保证 python -m nervous_bus.cli / python -m nervous_bus.demo 的 runpy -m
# 执行路径 100% 走文件（若在此注入同名模块，runpy 会报 loader 不匹配）。
for _sub in ("protocol", "topology", "permissions", "bus",
             "node", "cortex", "engine"):
    _mod = getattr(__import__("norpagent.cnb", fromlist=[_sub]), _sub, None)
    if _mod is not None:
        _sys.modules[f"{__name__}.{_sub}"] = _mod
del _sub, _mod, _sys
