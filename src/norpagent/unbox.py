# Copyright (c) 2026 xingluosama121, MIT Licensed
"""norpagent.unbox — 成品发行版入口（兼容转发层）。

架构书 §3.1（拍板 3A / O5，2026-09-09）：成品态入口的本体位于独立入口模块
``norpagent.farstars_app``（与 frame 基座分离，避免未来拆分伤筋动骨）。
本模块保留原导入路径与全部导出名（向后兼容）：

    from norpagent.unbox import main, DEFAULT_PROFILE, load_profile, save_profile

新代码推荐从 ``norpagent.farstars_app`` 导入（同一对象）：

    from norpagent.farstars_app import main, DEFAULT_PROFILE, load_profile, ...
"""

from norpagent.farstars_app.entry import (
    DEFAULT_PORT,
    DEFAULT_PROFILE,
    UnboxError,
    all_builtin_tools,
    load_profile,
    main,
    profile_path,
    run_unbox,
    save_profile,
    unbox_home,
)

__all__ = [
    "DEFAULT_PORT",
    "DEFAULT_PROFILE",
    "UnboxError",
    "unbox_home",
    "profile_path",
    "load_profile",
    "save_profile",
    "all_builtin_tools",
    "run_unbox",
    "main",
]
