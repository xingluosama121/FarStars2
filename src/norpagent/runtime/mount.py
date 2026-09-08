# Copyright (c) 2026 xingluosama121, MIT Licensed
"""Slot assembler: assembles architecture-layer slot implementations into a registry + preset overrides.

After ArchLayer connects, this module "installs" every slot's implementation into
the registry and the preset declaration, producing:

    (registry, preset, extras)

- registry: a registry with built-in components, presets, plugins and security policy installed;
- preset: the final preset object after slot overrides (directly usable by AgentRuntime);
- extras: non-registry objects (logger / storage / error_handler etc.), consumed by the engine (runtime.engine).

Default logic always goes through "preset declarations": a slot left empty = the
preset decides; a filled slot = overrides the preset (the address is mounted directly).

This module is also the assembly surface of "runtime hot mount"
(norpagent.runtime.remount): ``apply_slot_overrides`` can run repeatedly against
an **already running registry**; old architecture-level subscriptions (hooks /
security kit / plugins) are unsubscribed first and then remounted, so runtime
replacement of any slot never stacks duplicate subscriptions.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Callable, Dict, List, Optional, Tuple

from norpagent.arch.address import (
    AddressError,
    is_address_like,
    resolve_address,
)
from norpagent.arch.layer import call_factory
from norpagent.arch.slots import snapshot_slots
from norpagent.builtin import install_defaults
from norpagent.kernel.presets import Preset
from norpagent.kernel.registry import ComponentError, Registry
from norpagent.modes import register_all_presets

# preset field name -> registry registration method mapping (capability component slots)
_FIELD_SLOTS = {
    "session": ("register_session", "build_session"),
    "sandbox": ("register_sandbox", "build_sandbox"),
    "scheduler": ("register_scheduler", "build_scheduler"),
}

# environment variables treated as "model credentials provided"
_CREDENTIAL_ENV_KEYS = (
    "OPENAI_API_KEY",
    "DEEPSEEK_API_KEY",
    "ANTHROPIC_API_KEY",
    "DASHSCOPE_API_KEY",
    "NORPAGENT_API_KEY",
)


def _has_model_credentials(params: Dict[str, Any]) -> bool:
    """Decide whether model credentials are provided (parameters or environment variables)."""
    if params.get("api_key"):
        return True
    return any(os.environ.get(key) for key in _CREDENTIAL_ENV_KEYS)


def _arch_meta(reg: Registry) -> Dict[str, Any]:
    """Get the registry's "architecture assembly metadata" container (created lazily).

    Records the unsubscribable objects mounted by the architecture layer (hook
    subscriptions / security kits / plugin loaders); on hot remount they are
    unsubscribed first per these records to prevent stacking. Public alias:
    ``arch_meta`` (custom-slot appliers use it to record their own
    unsubscribable objects, ensuring repeated np.remount applications never stack side effects).
    """
    meta = getattr(reg, "_arch_meta", None)
    if meta is None:
        meta = {}
        reg._arch_meta = meta
    return meta


# public alias: the ctx["meta"] handed to custom-slot appliers is this container.
arch_meta = _arch_meta


def _apply_model_options(reg: Registry, overrides: Dict[str, Any],
                         params: Dict[str, Any]) -> None:
    """Apply the model_name / base_url / api_key shortcut parameters to model adapters.

    When the final model is a built-in adapter name (openai_compat / anthropic),
    reconstruct the provider with these parameters and override the registration,
    making np() and CLI behave the same:
    np(model="openai_compat", model_name="deepseek-v4-flash", api_key="...").
    """
    model_name = overrides.get("model")
    if model_name not in ("openai_compat", "anthropic"):
        return
    kwargs = {
        k: params[k]
        for k in ("model_name", "base_url", "api_key")
        if params.get(k) is not None
    }
    if not kwargs:
        return
    if model_name == "openai_compat":
        from norpagent.builtin.models.openai_compat import OpenAICompatProvider

        reg.register_model("openai_compat", OpenAICompatProvider(**kwargs))
    else:
        from norpagent.builtin.models.anthropic import AnthropicProvider

        reg.register_model("anthropic", AnthropicProvider(**kwargs))


def _register_instance_or_factory(reg: Registry, kind: str, name: str,
                                  value: Any) -> None:
    """Register an "instance / factory / class" as a named component.

    - callable (class / factory function) → registered directly as the factory;
    - non-callable instance → wrapped into a factory returning the same instance.
    """
    if callable(value):
        factory = value
    else:
        factory = lambda: value  # noqa: E731
    if kind == "session":
        reg.register_session(name, factory)
    elif kind == "sandbox":
        reg.register_sandbox(name, factory)
    elif kind == "scheduler":
        reg.register_scheduler(name, factory)
    else:  # pragma: no cover — defensive
        raise ComponentError(f"unknown component kind {kind}")


def build_registry(layer: Any,
                   params: Optional[Dict[str, Any]] = None) -> Tuple[Registry, Preset, Dict[str, Any]]:
    """Assemble a brand-new registry and the final preset (np() startup path)."""
    params = params or {}
    reg = Registry()
    install_defaults(reg)
    register_all_presets(reg)
    final, extras = apply_slot_overrides(reg, layer, params)
    return reg, final, extras


def apply_slot_overrides(reg: Registry, layer: Any,
                         params: Optional[Dict[str, Any]] = None) -> Tuple[Preset, Dict[str, Any]]:
    """Apply architecture-layer slot values to the registry, producing the final preset and extras.

    Repeatable (hot mount): before each run, the architecture-level subscriptions
    mounted by the previous run of this function (hook extensions / security kit /
    plugins) are unsubscribed first, so subscriptions never stack.
    """
    params = params or {}
    meta = _arch_meta(reg)

    # ── preset slot: decides the baseline preset ──
    # name_or_address (v0.9.1): strings resolve first as registered preset names;
    # if not found, as module addresses (an address may point at a factory returning a Preset instance).
    preset_value = layer.get("preset")
    if isinstance(preset_value, Preset):
        reg.register_preset(preset_value)
        base_name = preset_value.name
    elif isinstance(preset_value, str):
        if preset_value in reg.list_presets():
            base_name = preset_value  # reference to a registered preset name
        else:
            # string is not a registered preset name → resolve as a module address
            resolved = resolve_address(preset_value, slot="preset")
            if not isinstance(resolved, Preset) and callable(resolved):
                resolved = call_factory(
                    resolved, layer._context("preset", {}))
            if not isinstance(resolved, Preset):
                raise ComponentError(
                    f"preset slot address {preset_value!r} did not resolve to a "
                    f"Preset instance (got {type(resolved).__name__})"
                )
            reg.register_preset(resolved)
            base_name = resolved.name
    elif preset_value is None:
        base_name = "standard"  # default logic: the fully featured standard preset (full tool set)
    else:
        raise ComponentError(f"preset slot needs a preset name or a Preset instance, got {type(preset_value)}")
    base: Preset = reg.resolve_preset(base_name)

    overrides: Dict[str, Any] = {}
    components: Dict[str, str] = dict(base.components or {})
    extras: Dict[str, Any] = {}

    # ── model ──
    model = layer.get("model")
    if model is not None:
        if isinstance(model, str):
            if model in reg.list_models():
                overrides["model"] = model  # reference to a registered name
            else:
                # string is not a registered name → resolve as a module address
                reg.register_model("_arch_model",
                                   resolve_address(model, slot="model"))
                overrides["model"] = "_arch_model"
        else:
            reg.register_model("_arch_model", model)
            overrides["model"] = "_arch_model"
    elif base.model == "openai_compat" and not _has_model_credentials(params):
        # no model specified and no API credentials at all → fall back to mock:
        # the tool set stays complete (the model knows all available tools) and
        # replies are guidance hints; once the user configures a model + key in
        # the frontend, it switches to the real model.
        overrides["model"] = "mock"

    # ── model shortcut parameters (aligned with CLI --model-name/--base-url/--api-key) ──
    if any(k in params for k in ("model_name", "base_url", "api_key")):
        _apply_model_options(reg, overrides, params)

    # ── tool set ──
    # v0.9.1: list elements and single strings support pure-address loading —
    # an element/value shaped like a pure address (pkg.mod[:attr]) resolves by
    # address into a tool (resolution failures raise); other strings reference
    # registered tool names. dict values have their addresses resolved uniformly
    # in the architecture layer (layer._resolve_dict_values); this function receives objects.
    tools = layer.get("tools")
    if tools is not None:
        if isinstance(tools, dict):
            for tname, tool in tools.items():
                reg.register_tool(tname, tool)
            overrides["tools"] = list(tools.keys())
        elif isinstance(tools, (list, tuple)):
            names = []
            for item in tools:
                if isinstance(item, str):
                    if is_address_like(item):
                        impl = resolve_address(item, slot="tools")
                        if callable(impl):
                            sub = (
                                layer._parse_subconfig(item)
                                if ";" in item else {}
                            )
                            impl = call_factory(
                                impl, layer._context("tools", sub))
                        tname = (
                            getattr(impl, "name", "")
                            or impl.__class__.__name__
                        )
                        reg.register_tool(tname, impl)
                        names.append(tname)
                    else:
                        names.append(item)  # reference to a registered tool name
                else:
                    tname = (
                        getattr(item, "name", "")
                        or item.__class__.__name__
                    )
                    reg.register_tool(tname, item)
                    names.append(tname)
            overrides["tools"] = names
        elif isinstance(tools, str):
            # a single string: an address or a tool name
            if is_address_like(tools):
                impl = resolve_address(tools, slot="tools")
                if callable(impl):
                    sub = layer._parse_subconfig(tools) if ";" in tools else {}
                    impl = call_factory(impl, layer._context("tools", sub))
                tname = getattr(impl, "name", "") or impl.__class__.__name__
                reg.register_tool(tname, impl)
                overrides["tools"] = [tname]
            else:
                overrides["tools"] = [tools]  # reference to a single tool name
        else:  # a single Tool instance
            tname = getattr(tools, "name", "") or tools.__class__.__name__
            reg.register_tool(tname, tools)
            overrides["tools"] = [tname]

    # ── session / sandbox / scheduler ──
    # registry list methods use the slot's plural; sandbox's plural is irregular (sandboxes)
    _slot_plural = {"sandbox": "sandboxes"}
    for slot in ("session", "sandbox", "scheduler"):
        value = layer.get(slot)
        if value is None:
            continue
        lister = _slot_plural.get(slot, f"{slot}s")
        if isinstance(value, str):
            if value in getattr(reg, f"list_{lister}")():
                overrides[slot] = value  # reference to a registered name
            else:
                # string is not a registered name → resolve as a module address
                _register_instance_or_factory(
                    reg, slot, f"_arch_{slot}",
                    resolve_address(value, slot=slot),
                )
                overrides[slot] = f"_arch_{slot}"
        else:
            _register_instance_or_factory(reg, slot, f"_arch_{slot}", value)
            overrides[slot] = f"_arch_{slot}"

    # ── UI rendering adapter ──
    # name_or_address (v0.9.1): strings resolve first as registered UI names; if
    # not found, as module addresses (an address may point at a factory returning a UIAdapter).
    ui = layer.get("ui")
    if ui is not None:
        if isinstance(ui, str):
            if ui in reg.list_uis():
                overrides["ui"] = ui  # reference to a registered name
            else:
                impl = resolve_address(ui, slot="ui")
                if callable(impl):
                    impl = call_factory(impl, layer._context("ui", {}))
                reg.register_ui("_arch_ui", impl)
                overrides["ui"] = "_arch_ui"
                extras["ui_adapter"] = impl
        else:
            reg.register_ui("_arch_ui", ui)
            overrides["ui"] = "_arch_ui"
            extras["ui_adapter"] = ui

    # ── context store / project management (generic component namespace) ──
    for slot, kind in (("context_store", "context_store"),
                       ("project_manager", "project_manager")):
        value = layer.get(slot)
        if value is None:
            continue
        factory = value if callable(value) else (lambda v=value: v)
        reg.register_component(kind, f"_arch_{slot}", factory)
        components[kind] = f"_arch_{slot}"
        extras[slot] = value

    # ── hook extensions (unsubscribe the previous architecture-level subscriptions first; no stacking) ──
    hooks = layer.get("hooks")
    for fn, event_name in meta.pop("hook_subs", ()):
        try:
            reg.bus.unsubscribe(fn, event_name)
        except Exception:  # noqa: BLE001
            pass
    if hooks is not None:
        if callable(hooks) and not isinstance(hooks, dict):
            hooks = hooks(reg)
        if isinstance(hooks, dict):
            subs: List[Tuple[Any, str]] = []
            for hook_name, fn in hooks.items():
                reg.bus.subscribe(fn, hook_name)
                subs.append((fn, hook_name))
            meta["hook_subs"] = subs

    # ── security (uninstall the previous architecture-level kit first; no hook stacking) ──
    # zero hook intervention by default: a string level only mounts runtime
    # policies; for hook intervention use the dict form {"level": ..., "hooks": True}
    # or a callable custom assembly.
    security = layer.get("security")
    prev_kit = meta.pop("safety_kit", None)
    if prev_kit is not None:
        try:
            prev_kit.uninstall(reg)
        except Exception:  # noqa: BLE001
            pass
    if security is not None:
        if isinstance(security, str):
            from norpagent import safe

            kit = safe(reg, level=security)
            meta["safety_kit"] = kit
        elif isinstance(security, dict):
            from norpagent import safe

            kit = safe(
                reg,
                level=security.get("level", "standard"),
                config=security.get("config"),
                hooks=security.get("hooks"),
            )
            meta["safety_kit"] = kit
        elif callable(security):
            security(reg)
        else:  # SecurityContext / other objects: install directly
            reg.security = security

    # ── external plugins (unload the previous architecture-level plugins first, then reinstall) ──
    plugins = layer.get("plugins")
    prev_loader = meta.pop("plugin_loader", None)
    if prev_loader is not None:
        _unload_arch_plugins(reg, prev_loader)
    if plugins is not None:
        if callable(plugins) and not isinstance(plugins, (list, tuple)):
            plugins = plugins(reg)
        if isinstance(plugins, (list, tuple)):
            from norpagent.plugins import install_plugin_dirs

            loader = install_plugin_dirs(reg, list(plugins), config={
                "plugin_security_audit": "warn",
                "plugin_signature_verify": True,
            })
            meta["plugin_loader"] = loader

    # ── base-service slots ──
    logger = layer.get("logger")
    extras["logger"] = logger if logger is not None else logging.getLogger("norpagent")
    extras["storage"] = layer.get("storage")
    extras["error_handler"] = layer.get("error_handler")

    # ── custom slots (v0.9 hot-pluggable slot table): applied per spec applier ──
    # the slot table can extend at runtime: this loop walks the live snapshot.
    # Built-in slot appliers are all None (the framework handles them internally);
    # custom slots are applied here uniformly during assembly and hot mount — the
    # applier receives the resolved slot value (address semantics already
    # instantiated; sub-configs available via layer.subconfig(slot); name /
    # literal semantics as raw values) plus four mutable containers (components /
    # extras / overrides / meta). The same registry may be called repeatedly
    # (np.remount hot mount); appliers must be reentrant-safe; exceptions are
    # uniformly wrapped into ComponentError for easy slot identification.
    for slot, spec in snapshot_slots().items():
        applier = getattr(spec, "applier", None)
        if applier is None:
            continue
        value = layer.get(slot)
        if value is None:
            continue
        ctx = {
            "components": components,
            "extras": extras,
            "overrides": overrides,
            "meta": meta,
        }
        try:
            applier(reg, layer, value, params, ctx)
        except Exception as exc:  # noqa: BLE001 — uniformly wrapped for identification
            raise ComponentError(
                f"custom slot '{slot}' application logic failed: {exc}"
            ) from exc

    # ── assemble the final preset ──
    final = Preset(
        name=f"{base.name}_arch" if overrides or components != dict(base.components or {})
        else base.name,
        description=base.description,
        model=overrides.get("model", base.model),
        tools=list(overrides.get("tools", base.tools)),
        session=overrides.get("session", base.session),
        sandbox=overrides.get("sandbox", base.sandbox),
        scheduler=overrides.get("scheduler", base.scheduler),
        ui=overrides.get("ui", base.ui),
        mode=base.mode,
        params=dict(base.params),
        components=components,
    )
    reg.register_preset(final)
    return final, extras


def _unload_arch_plugins(reg: Registry, loader: Any) -> None:
    """Unload the plugins installed by the architecture layer (prerequisite for hot-remounting the plugins slot).

    - unsubscribe every plugin's hook subscriptions (Registry.unregister_plugin);
    - pop plugins' sys.modules caches (loader.unload);
    - release process-isolation host child processes (loader.shutdown).

    Tool entries stay in the registry (name-overwrite semantics: a same-named
    plugin reinstalled naturally overwrites; old tool names no longer loaded stay
    in the table but are unreachable since they are not in the preset tool set).
    """
    try:
        for info in list(getattr(loader, "plugins", ()) or ()):
            reg.unregister_plugin(getattr(info, "name", ""))
            try:
                loader.unload(reg, getattr(info, "name", ""))
            except Exception:  # noqa: BLE001
                pass
    except Exception:  # noqa: BLE001
        pass
    try:
        loader.shutdown()
    except Exception:  # noqa: BLE001
        pass


def default_loop_factory(layer: Any, config: Optional[Dict[str, Any]] = None) -> Any:
    """Default implementation of the async_loop slot (self-developed nasyncio core adapter,
    no dependency on the standard asyncio).

    Loop-specific tuning passes through the ``loop`` key of config (embedded /
    high-concurrency tuning):
    ``np(config={"loop": {"max_workers": 1, "poll_interval": 0.5}})``;
    equivalent env vars: NORPAGENT_MAX_WORKERS / NORPAGENT_SUBMIT_POLL.
    """
    from norpagent.loops.nasyncio import NasyncioLoopRuntime

    loop_cfg = (config or {}).get("loop")
    if isinstance(loop_cfg, dict):
        return NasyncioLoopRuntime(config=loop_cfg)
    return NasyncioLoopRuntime()


def default_frontend_factory(layer: Any, prompt: Optional[str] = None,
                             config: Optional[Dict[str, Any]] = None) -> Any:
    """Default implementation of the frontend slot.

    Single task (prompt mode) → headless (output printed to stdout);
    embedded preset → headless (no HTTP service by default in embedded);
    interactive mode → web (HTTP + SSE serving front.html, zero dependencies).
    """
    if prompt is not None:
        from norpagent.frontends.headless import HeadlessFrontend

        return HeadlessFrontend()
    cfg = dict(config or {})
    # embedded preset: no listening port by default (pure API mode). When a
    # frontend address is explicitly given, this default factory is not run
    # (slot addresses take priority).
    if cfg.get("preset") == "embedded":
        from norpagent.frontends.headless import HeadlessFrontend

        return HeadlessFrontend()
    web_cfg = cfg.get("web") if isinstance(cfg.get("web"), dict) else {}
    from norpagent.frontends.web import WebFrontend

    return WebFrontend(**web_cfg)


def coerce_frontend(impl: Any, subconfig: Optional[Dict[str, Any]] = None) -> Any:
    """Semantics of the frontend slot's "HTML path direct mount" (v0.9).

    An .html/.htm file path string passed through the architecture layer is
    converted here into WebFrontend(html=<path>), equivalent to address-style
    mounting ("norpagent.frontends.web:WebFrontend;html=..."); other
    implementations (address instance / instance / None) pass through unchanged.

    A nonexistent file raises ValueError (fail fast; never silently falls back to
    the default frontend — so users are not fooled into thinking their page is
    mounted when the built-in page is actually running).
    """
    if not (isinstance(impl, str)
            and ";" not in impl.strip()          # containing a clause = address-style mount
            and (impl.strip().lower().endswith(".html")
                 or impl.strip().lower().endswith(".htm"))):
        return impl
    path = impl.strip()
    if not os.path.isfile(path):
        # diagnostic hint: Windows backslash paths are often escaped by Python
        # literals into control characters (\n, \t, \x00, \x0c etc.); give an
        # actionable suggestion.
        ctrls = sorted({c for c in path if ord(c) < 32})
        hint = (
            "（path contains control characters: "
            + "/".join(f"\\{ord(c):02X}" for c in ctrls)
            + "; the backslashes were likely treated as escape sequences. "
            "Use forward slashes like H:/dir/file.html or a raw string "
            "r'H:\\dir\\file.html'）"
            if ctrls else
            "（check whether the file exists; for Windows paths, prefer forward "
            "slashes like H:/dir/file.html）"
        )
        raise ValueError(
            f"the frontend slot's HTML path does not exist: {path!r}, {hint}"
        )
    from norpagent.frontends.web import WebFrontend

    return WebFrontend(html=path, **(dict(subconfig) if subconfig else {}))


def mount_defaults(layer: Any, prompt: Optional[str] = None) -> None:
    """Register the library's built-in default logic as each slot's default implementation.

    Only takes effect when the user did not fill in an address (ArchLayer prefers user addresses).
    """
    layer.set_default("async_loop", default_loop_factory)
    layer.set_default("frontend",
                      lambda ctx: default_frontend_factory(
                          ctx.get("layer"), prompt, ctx.get("config")))
    # agent_runtime default implementation = kernel.agent.AgentRuntime,
    # constructed directly by the engine (construction context carries registry /
    # preset / task_params).
    from norpagent.kernel.agent import AgentRuntime

    layer.set_default("agent_runtime", lambda ctx: AgentRuntime)


__all__ = ["build_registry", "apply_slot_overrides", "mount_defaults"]
