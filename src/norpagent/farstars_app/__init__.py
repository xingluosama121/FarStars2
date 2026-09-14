# Copyright (c) 2026 xingluosama121, MIT Licensed
"""norpagent.farstars_app — 成品态（成品发行版）独立入口模块。

架构书 §3.1（拍板 3A / O5，2026-09-09）：代码目录预留独立入口模块
（``norpagent/farstars_app/``）与 frame 基座分离，避免未来拆分伤筋动骨。
本包承载「成品发行版」入口面：

    norpagent unbox                  终端入口（norpagent.cli 转发到本包）
    farstars_app.entry               入口实现（装配档案 / 全量工具 / CNB 两形态 / 冒烟自检）
    farstars_app.main(["--smoke"])   程序化入口（等价 norpagent unbox）

兼容：``norpagent.unbox`` 保留为同名导出的转发层（历史导入路径继续可用）。

用法::

    import norpagent.farstars_app as app

    app.main(["--smoke"])             # 自检拉起
    prof = app.load_profile()         # 读取成品档案
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
