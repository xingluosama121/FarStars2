# Copyright (c) 2026 xingluosama121, MIT Licensed
"""PluginSystem — the library facade of the plugin system (one object manages the full lifecycle).

    from norpagent.plugins import PluginSystem

    ps = PluginSystem(registry, ["my_plugins"], config={"plugin_isolation": "auto"})
    infos = ps.load()
    print(ps.status())
    ps.reload("my_tool")
    ps.shutdown()

Relationship with PluginLoader: PluginSystem is the facade (configuration /
lifecycle / status queries); PluginLoader is the execution engine (security
pipeline). Every stage of the pipeline is a hook: ``PLUGIN_PIPELINE_LAYER`` is a
custom layer declared with HookLayer (the standard-library use case of the hook
system's "custom layer" capability). Once installed, you can intervene in the
load process via ``registry.hooks.before_plugin_audit.subscribe(fn)``, and raising
HookVeto can veto the loading / registration of a single plugin.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from norpagent.hooks.core import HookLayer
from norpagent.plugins.loader import (
    PIPELINE_HOOK_NAMES,
    PluginInfo,
    PluginLoader,
)

# ── custom layer for the plugin load pipeline (standard-library use of the hook custom-layer capability) ──

PLUGIN_PIPELINE_LAYER = HookLayer(
    "plugin_pipeline", order=200,
    description="Plugin load pipeline (discover→signature→audit→register); HookVeto can veto with one vote",
)

before_plugin_discover = PLUGIN_PIPELINE_LAYER.hook(
    "before_plugin_discover", mutating=True,
    description="Before plugin directory scanning (HookVeto = cancel this discovery)",
    payload_keys=("dirs",),
)
after_plugin_discover = PLUGIN_PIPELINE_LAYER.hook(
    "after_plugin_discover",
    description="Plugin directory scanning finished",
    payload_keys=("loaded", "enabled"),
)
before_plugin_load = PLUGIN_PIPELINE_LAYER.hook(
    "before_plugin_load", mutating=True,
    description="Before a single plugin enters the security pipeline (HookVeto = reject loading this plugin)",
    payload_keys=("name", "path"),
)
after_plugin_load = PLUGIN_PIPELINE_LAYER.hook(
    "after_plugin_load",
    description="A single plugin finished the pipeline",
    payload_keys=("name", "enabled"),
)
before_plugin_audit = PLUGIN_PIPELINE_LAYER.hook(
    "before_plugin_audit", mutating=True,
    description="Before AST audit (HookVeto = reject loading this plugin)",
    payload_keys=("name", "path", "audit_level"),
)
after_plugin_audit = PLUGIN_PIPELINE_LAYER.hook(
    "after_plugin_audit",
    description="AST audit finished",
    payload_keys=("name", "path", "allowed", "issues"),
)
before_plugin_register = PLUGIN_PIPELINE_LAYER.hook(
    "before_plugin_register", mutating=True,
    description="Before registration into the Registry (HookVeto = reject registration)",
    payload_keys=("name", "tools", "isolation"),
)
after_plugin_register = PLUGIN_PIPELINE_LAYER.hook(
    "after_plugin_register",
    description="Registration into the Registry finished",
    payload_keys=("name", "enabled", "tools", "isolation"),
)


class PluginSystem:
    """Plugin system facade: discover → secure load → register → lifecycle management."""

    def __init__(
        self,
        registry: Any,
        plugin_dirs: Optional[List[str]] = None,
        config: Optional[dict] = None,
    ) -> None:
        self.registry = registry
        self.plugin_dirs = [str(d) for d in (plugin_dirs or [])]
        self.config: Dict[str, Any] = dict(config or {})
        # install the pipeline layer into the registry hook system (keep original definition if a same-name hook exists)
        registry.hooks.install_layer(PLUGIN_PIPELINE_LAYER)
        self._loader: Optional[PluginLoader] = None

    # ── configuration ────────────────────────────────────

    def configure(self, config: dict) -> "PluginSystem":
        self.config.update(config or {})
        self._loader = None  # rebuild the loader after configuration changes
        return self

    @property
    def loader(self) -> PluginLoader:
        if self._loader is None:
            self._loader = PluginLoader(self.plugin_dirs, self.config)
        return self._loader

    @property
    def plugins(self) -> List[PluginInfo]:
        return self.loader.plugins

    # ── lifecycle ────────────────────────────────────────

    def load(self) -> List[PluginInfo]:
        """Scan all directories and register into the Registry; returns plugin metadata."""
        return self.loader.discover_and_load(self.registry)

    def reload(self, plugin_name: str) -> bool:
        """Hot-reload a single plugin (for development; production should rebuild the Registry)."""
        return self.loader.reload(self.registry, plugin_name)

    def unload(self, plugin_name: str) -> bool:
        return self.loader.unload(self.registry, plugin_name)

    def status(self) -> Dict[str, Any]:
        """System status: plugin list + isolation host status."""
        loader = self.loader
        iso_status = None
        if loader._isolation_manager is not None:
            try:
                iso_status = loader._isolation_manager.status()
            except Exception:
                iso_status = {"alive": False}
        return {
            "dirs": list(loader._plugin_dirs),
            "config": dict(loader.config),
            "isolation": iso_status,
            "plugins": [
                {
                    "name": p.name,
                    "version": p.version,
                    "enabled": p.enabled,
                    "tools": list(p.tools),
                    "hook_names": list(p.hook_names),
                    "signature_status": p.signature_status,
                    "trusted": p.trusted,
                    "error": p.error,
                }
                for p in loader.plugins
            ],
        }

    def shutdown(self) -> None:
        """Release all resources (process-isolation host child processes)."""
        if self._loader is not None:
            self._loader.shutdown()


__all__ = [
    "PluginSystem",
    "PLUGIN_PIPELINE_LAYER",
    "PIPELINE_HOOK_NAMES",
    "before_plugin_discover",
    "after_plugin_discover",
    "before_plugin_load",
    "after_plugin_load",
    "before_plugin_audit",
    "after_plugin_audit",
    "before_plugin_register",
    "after_plugin_register",
]
