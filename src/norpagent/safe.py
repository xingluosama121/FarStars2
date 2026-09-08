# Copyright (c) 2026 xingluosama121, MIT Licensed
"""norpagent.safe() — the one-stop entry for the security system as a whole plug.

The entire security system (jailbreak protection / prompt hardening / human
approval / network policy / source audit / import restrictions / signature trust /
plugin isolation policy) is converged into one standalone function:

    from norpagent import safe, Registry

    reg = Registry()
    safe(reg, level="standard")        # one call to mount the full security policy; returns a SafetyKit

    kit = safe(level="high")           # or grab the kit first and install later
    kit.install(reg)                   # zero hook intervention by default (no hooks)
    kit.install_hooks(reg)             # explicitly mount when data-flow intervention is needed

Zero hook intervention (default): safe() subscribes to **no hooks** by default —
jailbreak protection and prompt hardening are no longer auto-mounted onto the bus
as hook subscribers; the hook pipeline stays pure, and intervention is entirely
the user's decision. The security system only provides runtime decisions through
``registry.security`` (SecurityContext): human approval / network policy / plugin
loading policy. Hook intervention is enabled explicitly by the user::

    safe(reg, level="standard", hooks=True)   # mount hooks immediately on install
    kit.install_hooks(reg)                    # or mount manually later
    kit.uninstall_hooks(reg)                  # unmount at any time; restore pure hooks

Hook intervention content (only when explicitly enabled):
- input protection = L3 ``before_input`` hook subscriber (HookVeto on a hit);
- prompt hardening = L5 ``before_build_messages`` mutating hook (rewrites the system prompt).
The protection capabilities themselves are always available as standalone APIs
(kit.scan_input / kit.harden / ...), callable freely from your own hook
subscribers or method overrides.

- human approval / network policy and other runtime decisions = ``registry.security``
  (SecurityContext), read by AgentRuntime and the plugin loader;
- plugin load pipeline = default config of ``SecurityContext.plugin_config()``,
  automatically adopted when ``norpagent.plugins.install_plugin_dirs`` gets no
  explicit config.

Three presets: basic (protection + hints) + standard (+ import restrictions /
network deny / approval) + high (+ audit block / permission declarations / forced
trusted signatures). Every policy can be overridden item by item with a config
dict, at the same granularity as the norpagent.security modules.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from norpagent.security.approval import ApprovalPolicy
from norpagent.security.guard import (
    harden_system_prompt as _harden_system_prompt,
)
from norpagent.security.guard import scan_message as _scan_message
from norpagent.security.network_policy import (
    NetworkPolicy,
    POLICY_DENY,
    POLICY_ALLOW_ALL,
)

# three security presets
LEVEL_BASIC = "basic"
LEVEL_STANDARD = "standard"
LEVEL_HIGH = "high"
VALID_LEVELS = (LEVEL_BASIC, LEVEL_STANDARD, LEVEL_HIGH)


@dataclass
class SecurityContext:
    """registry.security — the single source of truth for runtime security policy.

    AgentRuntime reads this object for tool approval; the plugin loader reads
    ``plugin_config()`` when the config is absent. Hook intervention (automatic
    subscription of input protection / prompt hardening) is controlled by
    ``hook_intervention``, default False — the security system mounts no hooks and
    the hook pipeline stays pure; users can set it True or enable it explicitly
    via ``kit.install_hooks()``. Explicit switches in ``params`` (jailbreak_guard /
    harden_prompt / approval_*) take priority over this context — security can be
    tightened, never quietly loosened by task parameters.
    """

    level: str = LEVEL_STANDARD
    guard_enabled: bool = True
    harden_enabled: bool = True
    audit_level: str = "warn"            # off / warn / block
    import_restrict: str = "safe"        # off / safe / strict
    require_permissions: bool = False
    signature_verify: bool = True
    signature_required: bool = False     # True: only trusted signatures may load
    trusted_keys: List[str] = field(default_factory=list)
    network_policy: str = POLICY_DENY    # deny / audited_public / public_only / allow_all
    approval_config: Optional[Dict[str, Any]] = None
    plugin_isolation: str = "auto"       # auto / inproc / process
    hook_intervention: bool = False      # True: mount protection hooks on install (no hooks by default)
    extra: Dict[str, Any] = field(default_factory=dict)

    def plugin_config(self) -> Dict[str, Any]:
        """Convert into the plugin-loader config (fallback when the config is absent)."""
        approval_enabled = True
        if isinstance(self.approval_config, dict):
            approval_enabled = bool(
                self.approval_config.get("approval_enabled", True)
            )
        return {
            "plugin_security_audit": self.audit_level,
            "plugin_security_import_restrict": self.import_restrict,
            "plugin_security_require_permissions": self.require_permissions,
            "plugin_signature_verify": self.signature_verify,
            "plugin_signature_required": self.signature_required,
            "plugin_trusted_keys": list(self.trusted_keys),
            "plugin_network_policy": self.network_policy,
            "approval_enabled": approval_enabled,
            "plugin_isolation": self.plugin_isolation,
        }

    def to_dict(self) -> Dict[str, Any]:
        data = self.plugin_config()
        data.update({
            "level": self.level,
            "guard_enabled": self.guard_enabled,
            "harden_enabled": self.harden_enabled,
            "hook_intervention": self.hook_intervention,
            "approval_config": dict(self.approval_config or {}),
            "extra": dict(self.extra),
        })
        return data


class SafetyKit:
    """The security kit: return value of safe().

    - ``install(registry, hooks=...)``: mounts the SecurityContext; no hooks by default;
    - ``install_hooks / uninstall_hooks``: explicitly mount/unmount hook intervention
      (L3 input protection + L5 prompt hardening);
    - a set of directly usable standalone security-check APIs (proxying norpagent.security).
    """

    def __init__(self, context: SecurityContext) -> None:
        self.context = context
        self._installed: List[Any] = []
        self._hook_registries: List[Any] = []
        self._hook_subscriptions: List[Tuple[Any, str]] = []
        self._approval_cache: Optional[ApprovalPolicy] = None
        self._network_cache: Optional[NetworkPolicy] = None

    # ── install ──────────────────────────────────────────

    def install(self, registry: Any, *, hooks: Optional[bool] = None) -> "SafetyKit":
        """Mount the security policy onto the registry: SecurityContext (+ optional hook subscribers).

        Default hooks=None → take ``context.hook_intervention`` (default False),
        i.e. **subscribe to no hooks**: jailbreak protection and prompt hardening
        do not intervene in the data flow as hook subscribers; the hook pipeline
        stays pure. When hooks=True (or the context is set), the before_input /
        before_build_messages subscribers are mounted synchronously, equivalent
        to calling install_hooks after install.
        """
        if registry in self._installed:
            self.uninstall(registry)
        registry.security = self.context
        self._installed.append(registry)
        want_hooks = self.context.hook_intervention if hooks is None else hooks
        if want_hooks:
            self.install_hooks(registry)
        return self

    def install_hooks(self, registry: Any) -> "SafetyKit":
        """Explicitly mount hook intervention: L3 input protection + L5 prompt hardening.

        The security system mounts no hooks by default; calling this method wires
        jailbreak blocking and prompt hardening into before_input /
        before_build_messages. Idempotent: repeated calls on the same registry do
        not stack subscribers. Install first (or pass hooks=True to install).
        """
        if registry in self._hook_registries:
            return self
        hooks = registry.hooks

        # L3 input protection: HookVeto on a hit (the task ends as stopped).
        # params["jailbreak_guard"]=False can disable it explicitly (task-level override).
        if self.context.guard_enabled:
            from norpagent.hooks.core import HookVeto

            def guard_input(event: Any) -> Any:
                params = (event.get("params") or {})
                if params.get("jailbreak_guard") is False:
                    return None
                user_input = event.get("user_input") or ""
                blocked, reason, _ = self.scan_input(user_input)
                if blocked:
                    raise HookVeto(reason or "input blocked by security protection")
                return None

            hooks.before_input.subscribe(guard_input)
            self._hook_subscriptions.append((guard_input, "before_input"))

        # L5 prompt hardening: rewrite the system prompt.
        if self.context.harden_enabled:
            def harden_messages(event: Any) -> Any:
                params = (event.get("params") or {})
                if params.get("harden_prompt") is False:
                    return None
                prompt = event.get("system_prompt") or ""
                tool_names = event.get("tool_names") or []
                return {"system_prompt": self.harden(prompt, tool_names)}

            def harden_wrapper(event: Any) -> Any:
                # compatible with payloads without tool_names: take it from the params side
                return harden_messages(event)

            hooks.before_build_messages.subscribe(harden_wrapper)
            self._hook_subscriptions.append(
                (harden_wrapper, "before_build_messages")
            )

        self._hook_registries.append(registry)
        return self

    def uninstall_hooks(self, registry: Any) -> "SafetyKit":
        """Unmount hook intervention: unsubscribe every hook subscriber mounted by this kit.

        Only removes this kit's own subscribers; the user's / plugins' other
        subscriptions are untouched — the hook pipeline is restored to purity. The
        security context (registry.security) is kept; runtime decisions
        (approval/network/plugin policy) are unaffected.
        """
        if registry not in self._hook_registries:
            return self
        for fn, event_name in self._hook_subscriptions:
            try:
                registry.bus.unsubscribe(fn, event_name)
            except Exception:  # noqa: BLE001 — an abnormal bus state must not block unmounting
                pass
        self._hook_subscriptions.clear()
        self._hook_registries.remove(registry)
        return self

    def hooks_installed(self, registry: Any) -> bool:
        """Whether this kit's hook-intervention subscribers are mounted on the registry."""
        return registry in self._hook_registries

    def uninstall(self, registry: Any) -> None:
        """Uninstall this kit: unsubscribe hook subscribers and clear the security context.

        When hot-mounting the security slot at runtime, uninstall the old kit
        first, then install the new one, avoiding stacked protection hooks on the
        same bus.
        """
        self.uninstall_hooks(registry)
        try:
            if getattr(registry, "security", None) is self.context:
                registry.security = None
        except Exception:  # noqa: BLE001
            pass
        if registry in self._installed:
            self._installed.remove(registry)

    # ── standalone security-check APIs (proxying norpagent.security) ──

    def scan_input(self, text: str) -> Tuple[bool, Optional[str], List[str]]:
        """Jailbreak / injection scan. Returns (blocked or not, reason, matched-description list)."""
        return _scan_message(text)

    def is_jailbreak_attempt(self, text: str) -> bool:
        blocked, _, _ = self.scan_input(text)
        return blocked

    def harden(self, prompt: str, tool_names: List[str]) -> str:
        """System prompt hardening (injects core rules and the tool list)."""
        return _harden_system_prompt(prompt, tool_names)

    def audit_file(self, path: str) -> List[dict]:
        """Plugin source AST audit. Returns the issue list (severity/line/code/message/category)."""
        from norpagent.security.audit import SourceAuditor

        auditor = SourceAuditor(self.context.audit_level)
        issues, _allowed = auditor.audit_file(path, audit_level=self.context.audit_level)
        return [i.to_dict() for i in issues]

    def audit_source(self, source: str) -> List[dict]:
        """Audit a source string. Returns the issue list."""
        from norpagent.security.audit import SourceAuditor

        auditor = SourceAuditor(self.context.audit_level)
        issues, _allowed = auditor.audit_source(source, audit_level=self.context.audit_level)
        return [i.to_dict() for i in issues]

    def verify_plugin(self, path: str, manifest: Optional[dict] = None) -> Any:
        """Plugin signature verification; returns a SignatureResult."""
        from norpagent.security.signature import SignatureVerifier

        verifier = SignatureVerifier({
            "plugin_signature_verify": self.context.signature_verify,
            "plugin_trusted_keys": self.context.trusted_keys,
        })
        return verifier.verify(path, manifest)

    def check_network(self, url: str) -> bool:
        """Decide one network access per the current network policy (SSRF protection)."""
        return self.network_policy().check_url(url).allowed

    def approval_policy(self, tool_hints: Optional[dict] = None) -> ApprovalPolicy:
        """Build an approval-policy instance consistent with the current config."""
        policy = ApprovalPolicy(self.context.approval_config or {})
        policy.set_tool_hints(tool_hints or {})
        return policy

    def network_policy(self) -> NetworkPolicy:
        """Build a network-policy instance consistent with the current config."""
        if self._network_cache is None:
            self._network_cache = NetworkPolicy({
                "plugin_network_policy": self.context.network_policy,
            })
        return self._network_cache

    def describe(self) -> Dict[str, Any]:
        """Human-readable description of the current security posture."""
        return self.context.to_dict()

    def __repr__(self) -> str:
        return f"<SafetyKit level={self.context.level}>"


# ── three presets ────────────────────────────────────────


def _build_context(level: str, config: Optional[dict],
                   overrides: Optional[dict]) -> SecurityContext:
    level = level or LEVEL_STANDARD
    if level not in VALID_LEVELS:
        raise ValueError(f"unknown security level '{level}'. Options: {VALID_LEVELS}")

    ctx = SecurityContext(level=level)
    if level == LEVEL_BASIC:
        ctx.import_restrict = "off"
        ctx.network_policy = POLICY_ALLOW_ALL
        ctx.approval_config = {"approval_enabled": False}
    elif level == LEVEL_STANDARD:
        pass  # standard by default
    elif level == LEVEL_HIGH:
        ctx.audit_level = "block"
        ctx.require_permissions = True
        ctx.signature_required = True

    if config:
        _apply_config(ctx, config)
    if overrides:
        _apply_config(ctx, overrides)
    return ctx


def _apply_config(ctx: SecurityContext, config: dict) -> None:
    """Map a config dict onto the SecurityContext (including plugin-loader style key names)."""
    mapping = {
        "guard_enabled": ("guard_enabled", bool),
        "harden_enabled": ("harden_enabled", bool),
        "plugin_security_audit": ("audit_level", str),
        "plugin_security_import_restrict": ("import_restrict", str),
        "plugin_security_require_permissions": ("require_permissions", bool),
        "plugin_signature_verify": ("signature_verify", bool),
        "plugin_signature_required": ("signature_required", bool),
        "plugin_network_policy": ("network_policy", str),
        "plugin_isolation": ("plugin_isolation", str),
        "hook_intervention": ("hook_intervention", bool),
    }
    for key, (attr, cast) in mapping.items():
        if key in config and config[key] is not None:
            setattr(ctx, attr, cast(config[key]))
    if "plugin_trusted_keys" in config:
        keys = config["plugin_trusted_keys"]
        if isinstance(keys, (list, tuple)):
            ctx.trusted_keys = [str(k) for k in keys if k]
    if "approval" in config and isinstance(config["approval"], dict):
        ctx.approval_config = dict(config["approval"])
    elif "approval_config" in config and isinstance(config["approval_config"], dict):
        ctx.approval_config = dict(config["approval_config"])


def safe(registry: Any = None, *, level: str = LEVEL_STANDARD,
         config: Optional[dict] = None, hooks: Optional[bool] = None,
         **overrides: Any) -> SafetyKit:
    """norpagent.safe() — one call to mount the full security system (zero hook intervention by default).

    Usage::

        safe(reg)                            # standard level; runtime policies only
        safe(reg, level="high")              # strict level; no hooks
        safe(reg, level="high", hooks=True)  # explicitly enable hook intervention
        kit = safe(level="basic", config={...})  # custom; install later with kit.install(reg)
        kit.install_hooks(reg)               # mount hooks manually at any time

    When ``registry`` is given, the SecurityContext is installed immediately; by
    default **no hooks are subscribed** (jailbreak protection and prompt hardening
    do not intervene in the data flow as hooks; the hook pipeline stays pure).
    ``hooks=True`` or ``hook_intervention=True`` in config/overrides mounts the
    before_input / before_build_messages subscribers synchronously on install; you
    can also mount them later with ``kit.install_hooks(reg)`` and unmount at any
    time with ``kit.uninstall_hooks(reg)``. Returns the SafetyKit; without a
    registry, an uninstalled kit is returned. ``config`` / ``**overrides`` can
    override the preset item by item (key names consistent with the
    norpagent.security / plugin-loader configs).
    """
    kit = SafetyKit(_build_context(level, config, overrides or None))
    if registry is not None:
        kit.install(registry, hooks=hooks)
    return kit


__all__ = [
    "safe",
    "SafetyKit",
    "SecurityContext",
    "LEVEL_BASIC",
    "LEVEL_STANDARD",
    "LEVEL_HIGH",
    "VALID_LEVELS",
]
