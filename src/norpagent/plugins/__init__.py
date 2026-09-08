# Copyright (c) 2026 xingluosama121, MIT Licensed
"""norpagent.plugins — external plugin system (library form: loader + facade + process isolation).

Security pipeline: signature verification → AST audit → permission declaration → import restrictions → registration.
Process-level plugin isolation is supported since P4 (plugin code runs only in a child process, JSON-lines RPC).

    # Convenience entry
    from norpagent.plugins import install_plugin_dirs
    loader = install_plugin_dirs(registry, ["my_plugins"], config={...})

    # Library facade (lifecycle + state + hot reload)
    from norpagent.plugins import PluginSystem
    ps = PluginSystem(registry, ["my_plugins"])
    ps.load(); ps.status(); ps.shutdown()

    # Process-level isolation (plugin module-level ISOLATION = "process" or forced by config)
    from norpagent.plugins.isolation import ProcessIsolationManager

Every stage of the load pipeline is a hook (PLUGIN_PIPELINE_LAYER custom layer);
HookVeto can veto loading / registration with a single vote.
"""

from norpagent.plugins.loader import (
    HOOK_NAMES,
    PIPELINE_HOOK_NAMES,
    PLUGIN_MODULE_PREFIX,
    PluginContext,
    PluginInfo,
    PluginLoader,
    install_plugin_dirs,
)
from norpagent.plugins.manager import (
    PLUGIN_PIPELINE_LAYER,
    PluginSystem,
    before_plugin_discover,
    after_plugin_discover,
    before_plugin_load,
    after_plugin_load,
    before_plugin_audit,
    after_plugin_audit,
    before_plugin_register,
    after_plugin_register,
)
from norpagent.plugins.isolation import (
    DEFAULT_RPC_TIMEOUT,
    HOOK_TIMEOUT,
    ProcessIsolationManager,
    ProcessPluginHost,
)

__all__ = [
    "HOOK_NAMES",
    "PIPELINE_HOOK_NAMES",
    "PLUGIN_MODULE_PREFIX",
    "PluginContext",
    "PluginInfo",
    "PluginLoader",
    "install_plugin_dirs",
    "PluginSystem",
    "PLUGIN_PIPELINE_LAYER",
    "before_plugin_discover",
    "after_plugin_discover",
    "before_plugin_load",
    "after_plugin_load",
    "before_plugin_audit",
    "after_plugin_audit",
    "before_plugin_register",
    "after_plugin_register",
    "ProcessIsolationManager",
    "ProcessPluginHost",
    "HOOK_TIMEOUT",
    "DEFAULT_RPC_TIMEOUT",
]
