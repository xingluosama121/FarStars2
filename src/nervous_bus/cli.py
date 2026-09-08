# -*- coding: utf-8 -*-
"""nervous_bus.cli — v1.0.7 兼容 shim（实现已内核化迁入 norpagent.cnb.cli）。"""

from norpagent.cnb.cli import *  # noqa: F401,F403
from norpagent.cnb.cli import (  # noqa: F401
    main,
    build_parser,
    cmd_cortex,
    cmd_node,
    cmd_topo,
    cmd_ping,
    cmd_exec,
    cmd_stop,
    cmd_reload,
    cmd_perm,
    cmd_reports,
    cmd_audit,
    cmd_sync,
)

if __name__ == "__main__":
    main()
