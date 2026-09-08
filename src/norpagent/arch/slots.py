# Copyright (c) 2026 xingluosama121, MIT Licensed
"""Architecture slot specification table.

Every part of an agent application is a "slot":

- every slot has a name, a protocol, a default implementation, a factory-context
  convention and documentation;
- a slot without an address → runs the library's built-in default logic;
- a slot with an address (string / factory / instance) → mounts the implementation by address;
- apart from the minimal kernel "required for runtime operation", **every**
  component is a slot, including the event loop (async_loop), the agent loop
  itself (agent_runtime), the frontend (frontend), the renderer (ui), etc.

Minimal kernel required for runtime operation (not replaceable; only four items):
    1. ArchLayer itself (the slot connector; norpagent.arch.layer)
    2. the address resolver (norpagent.arch.address)
    3. the registry (norpagent.kernel.registry.Registry)
    4. the event bus (norpagent.kernel.events.EventBus)

Everything else is a slot. Fill in an address for each slot and the whole agent
application becomes a completely different assembly, without modifying any core code.

**The slot table itself is also hot-pluggable (v0.9)**: besides the 18 built-in
slots (framework structural contracts; protected — cannot be unregistered or have
their specs overridden), third parties can register brand-new custom slots at
runtime (``register_slot``) — registration plugs into the full pipeline: ``np()``
parameter validation, ArchLayer assembly, ``np.remount()`` hot replacement, and
``layer.describe()`` listing. Custom slots declare assembly logic through
``SlotSpec.applier`` (mounting onto the registry / preset / engine); see the APIs
at the bottom of this module and Developer Manual section 3.8.

**All slots support address-based loading (v0.9.1)**:

- name / name_or_address slots: a string resolves first as a registered name,
  then, if not found, as a module address (``pkg.mod[:attr]``);
- literal slots (hooks / security / plugins / logger / storage / error_handler):
  a string **shaped like a pure address** (a dot-separated identifier containing
  ``.`` or ``:``; see ``norpagent.arch.address.is_address_like``) loads by
  address; otherwise the literal value stands (levels / paths / directories);
- **dict key-value pairs of any slot**: when a value is a pure-address string, it
  is uniformly resolved by address into an object (resolution failures raise
  ``AddressError``) — e.g.
  ``tools={"my_tool": "myapp.tools:create"}``,
  ``hooks={"before_model_call": "myapp.guard:fn"}``;
- tools list elements also support addresses: ``tools=["myapp.tools:create"]``.
"""

from __future__ import annotations

import keyword
import threading
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass(frozen=True)
class SlotSpec:
    """Specification of one architecture slot.

    Fields:
        name: slot name (the keyword-parameter name of np()).
        protocol: the interface contract the slot implementation must satisfy (documentation text).
        default_address: address of the default implementation (None means the default logic is inlined in the assembler).
        string_semantics: semantics of string values:
            "address"          -> the string is a module address ("pkg.mod[:attr]");
            "name"             -> the string is a registered component name (passed through verbatim);
            "name_or_address"  -> resolve first as a component name, then as a module address;
            "literal"          -> the string is a literal value (levels / paths etc.);
            **since v0.9.1 all slots support address-based loading**:
            - name / name_or_address slots: a string first checks the registry
              name; if not found, resolves as a module address ("pkg.mod[:attr]");
            - literal slots: a string **shaped like a pure address** (a
              dot-separated identifier containing "." or ":") loads as a module
              address; otherwise the literal value stands (address-first; see
              norpagent.arch.address.is_address_like);
            - **dict key-value pairs of any slot**: when a value is a pure-address
              string, it resolves uniformly by address into an object (resolution
              failures raise AddressError).
        factory_kwargs: documentation of injected factory-context keys ({key: description});
            factories declare same-named parameters to receive the context.
        description: the slot's responsibility description.
        examples: usage examples (list).
        defer_factory: True means this slot's factory call is **deferred to the
            engine assembly phase** (after the registry / preset context is ready;
            called by NorpEngine._build_agent with signature-based injection); at
            architecture-layer connect time only the address is resolved, no
            instantiation. Used for slots needing the full context, like agent_runtime.
        applier: assembly logic of custom slots (built-in slots are None; the
            framework handles them internally). Signature
            ``applier(reg, layer, value, params, ctx)``: called by
            runtime.mount.apply_slot_overrides during assembly and hot mount when
            the slot value is non-empty. **The same registry may be called
            repeatedly** (np.remount hot mount); appliers must be reentrant-safe
            (repeated execution must not stack side effects; use ctx["meta"] to
            record objects to unsubscribe). ``value`` is the resolved slot value:
            for address semantics it is the instantiated implementation (sub-config
            available via layer.subconfig(slot)); name / name_or_address / literal
            semantics pass the raw value. ``ctx`` holds four mutable containers:
            - components: the final preset's component declarations {kind: name} —
              an applier can register_component then record it here;
            - extras: the engine's extra-object dict (custom objects go here; the
              engine consumes extras[slot name]);
            - overrides: preset-field overrides (the final values of model/tools/...),
              sharing one dict with the built-in slots;
            - meta: the registry's architecture metadata (runtime.mount.arch_meta;
              records mounted objects to unsubscribe).
        remount_rebuild_agent: True means hot-mounting this slot requires a hot
            **AgentRuntime rebuild** (custom "assembly-type" slots — slots whose
            applier registers generic components into the preset's components
            should set True); False (default) means the next run() takes effect or
            only extras update; no runtime rebuild needed.
    """

    name: str
    description: str
    protocol: str
    default_address: Optional[str] = None
    string_semantics: str = "address"
    factory_kwargs: Dict[str, str] = field(default_factory=dict)
    examples: List[str] = field(default_factory=list)
    defer_factory: bool = False
    applier: Optional[Callable[..., None]] = None
    remount_rebuild_agent: bool = False

    def format_help(self) -> str:
        lines = [
            f"[{self.name}] {self.description}",
            f"  protocol: {self.protocol}",
            f"  default: {self.default_address or 'assembler built-in logic'}",
            f"  string semantics: {self.string_semantics}",
        ]
        for key, doc in self.factory_kwargs.items():
            lines.append(f"  factory param {key}: {doc}")
        for ex in self.examples:
            lines.append(f"  example: {ex}")
        return "\n".join(lines)


# ═══════════════════════════════════════════════════════════
#  the full slot set
# ═══════════════════════════════════════════════════════════

# slot-table thread safety: assembly / hot mount may happen on different threads than registration.
_LOCK = threading.RLock()

# full set of string semantics (validated by register_slot)
_STRING_SEMANTICS = ("address", "name", "name_or_address", "literal")

# launch()'s special keys (popped before slot splitting); cannot be slot names
_RESERVED_SLOT_NAMES = frozenset({"prompt", "config"})


class SlotError(ValueError):
    """Illegal slot-table hot-plug operation (registration / unregistration / illegal spec)."""


SLOT_SPECS: Dict[str, SlotSpec] = {}


def _slot(spec: SlotSpec) -> SlotSpec:
    with _LOCK:
        SLOT_SPECS[spec.name] = spec
    return spec


# ── execution-engine layer ────────────────────────────────

_slot(SlotSpec(
    name="async_loop",
    description="Event loop system: the async scheduling core the Agent runs on. "
                "Equivalent to the architecture function norpagent.nasyncio(). "
                "The default implementation runs the library's built-in "
                "self-developed nasyncio event loop core (norpagent.nasyncio; no "
                "dependency on the standard asyncio).",
    protocol=(
        "LoopRuntime protocol (norpagent.loops.base.LoopRuntime): "
        "start() starts the loop; stop() requests a stop; is_running(); join() for cleanup; "
        "submit(fn, *a, **kw) runs a synchronous function in the loop context and returns its result."
    ),
    default_address="norpagent.loops.nasyncio:NasyncioLoopRuntime",
    factory_kwargs={"layer": "the owning architecture layer", "config": "extra config dict of this slot"},
    examples=[
        "np(async_loop='norpagent.loops.nasyncio:NasyncioLoopRuntime')  # explicit default (self-developed nasyncio core)",
        "np(async_loop='norpagent.loops.std_asyncio:StdLoopRuntime')   # 0.7 legacy address (compat shim; same default)",
        "np(async_loop='myapp.nasync_loop:create')                     # a self-developed loop",
    ],
))

_slot(SlotSpec(
    name="agent_runtime",
    description="The agent loop body: the execution loop of input→session→messages→model→tools→result.",
    protocol=(
        "Provides run(user_input, session_id=None, task_id=None, task_params=None)"
        " returning a result object with .final_content / .status;"
        " provides shutdown() to release resources."
    ),
    default_address=None,  # default logic = kernel.agent.AgentRuntime
    defer_factory=True,    # the factory call is deferred to the engine assembly phase (needs registry/preset context)
    factory_kwargs={
        "registry": "the assembled registry",
        "preset": "the resolved preset object",
        "layer": "the owning architecture layer",
        "config": "extra config dict of this slot",
    },
    examples=[
        "np(agent_runtime='myapp.agent:MyAgentRuntime')  # replace the agent loop body",
    ],
))

# ── capability component layer ────────────────────────────

_slot(SlotSpec(
    name="model",
    description="Model provider (the Agent's \"brain\").",
    protocol="ModelProvider protocol (norpagent.protocols.model.ModelProvider): "
             "generate(messages, tool_schemas, params) / optional stream(...).",
    default_address=None,  # default logic = use the model declared by the preset
    string_semantics="name_or_address",
    factory_kwargs={"layer": "the owning architecture layer", "config": "extra config dict"},
    examples=[
        "np(model=MockModelProvider())                    # plug in an instance directly",
        "np(model='myapp.model:create')                   # plug in a factory address",
        "np(model='openai_compat')                        # use a registered model name",
    ],
))

_slot(SlotSpec(
    name="tools",
    description="Tool set (the Agent's \"hands\"). v0.9.1: list elements and dict "
                "values support pure-address loading — "
                "tools=['myapp.tools:create'] / "
                "tools={'my_tool': 'myapp.tools:create'} load tool implementations "
                "by address (other strings are registered tool names).",
    protocol="Tool protocol (norpagent.protocols.tool.Tool): name / schema() / run(args, ctx). "
             "Slot values allowed: a name list (registry references; elements may be pure addresses), "
             "{name: Tool} mappings (values may be pure addresses), or a Tool instance list.",
    default_address=None,  # default logic = use the tool set declared by the preset
    string_semantics="name",
    examples=[
        "np(tools=['echo', 'get_time'])                   # mount only two tools",
        "np(tools=['myapp.tools:create'])                 # list elements load by address",
        "np(tools={'my_tool': 'myapp.tools:create'})      # key-value values load by address",
        "np(tools={'my_tool': MyTool()})                  # register and enable a custom tool",
    ],
))

_slot(SlotSpec(
    name="session",
    description="Session management (the Agent's \"memory\").",
    protocol="SessionManager protocol (norpagent.protocols.session.SessionManager): "
             "create_session / get_session / append_message / history.",
    default_address=None,  # default logic = use the session component declared by the preset
    string_semantics="name_or_address",
    examples=[
        "np(session='sqlite')                             # switch to SQLite persistence",
        "np(session=MySessionManager())                   # a custom session instance",
    ],
))

_slot(SlotSpec(
    name="sandbox",
    description="Sandbox environment (the isolation boundary of tool execution).",
    protocol="Sandbox protocol (norpagent.protocols.sandbox.Sandbox): run / close.",
    default_address=None,  # default logic = use the sandbox declared by the preset
    string_semantics="name_or_address",
    examples=[
        "np(sandbox='pooled')                             # pooled sandbox",
        "np(sandbox='myapp.docker_sandbox:create')        # container sandbox",
    ],
))

_slot(SlotSpec(
    name="scheduler",
    description="Task scheduler (the base of long-run task cooperation / multi-agent orchestration).",
    protocol="TaskScheduler protocol (norpagent.protocols.scheduler.TaskScheduler): "
             "submit / drain / cancel.",
    default_address=None,  # default logic = use the scheduler declared by the preset
    string_semantics="name_or_address",
    examples=[
        "np(scheduler='persistent')                       # a scheduler that survives crashes",
    ],
))

_slot(SlotSpec(
    name="context_store",
    description="Context store (cross-session long-term memory; FTS5 full-text retrieval).",
    protocol="Provides add / search / list / delete interfaces; close() releases resources.",
    default_address=None,  # default logic = use the context component declared by the preset
    examples=[
        "np(context_store='norpagent.builtin.context:FTS5ContextStore')",
    ],
))

_slot(SlotSpec(
    name="project_manager",
    description="Project management (project metadata, directory scanning, git awareness).",
    protocol="Provides read-only interfaces such as status / scan; close() releases resources.",
    default_address=None,  # default logic = use the project-management component declared by the preset
    examples=[
        "np(project_manager='myapp.pm:create')",
    ],
))

# ── cross-cutting layer ───────────────────────────────────

_slot(SlotSpec(
    name="hooks",
    description="Hook-system extensions: custom subscriptions beyond the 9-layer "
                "29 hooks. v0.9.1: dict key-value values support pure-address "
                "resolution — {hook name: 'pkg.mod[:attr]'} loads callbacks by address.",
    protocol="{hook name: callback} mapping, or callable(registry) returning the subscription config.",
    default_address=None,  # default logic = the standard 9 layers, no extra subscriptions
    string_semantics="literal",
    examples=[
        "np(hooks={'before_model_call': my_guard})",
        "np(hooks={'before_model_call': 'myapp.guard:fn'})  # the value loads by address",
    ],
))

_slot(SlotSpec(
    name="security",
    description="Security system (the policy source of norpagent.safe(); zero hook "
                "intervention by default). v0.9.1 address-first: strings shaped like "
                "a pure address (pkg.mod[:attr]) load a security-kit factory by "
                "address; everything else is a level name (basic/standard/high).",
    protocol="A string level (basic/standard/high), a config dict (level/hooks/config), "
             "a SecurityContext instance, or callable(registry) completing the security assembly. "
             "Strings and dicts mount no hooks by default; hooks=True mounts hook intervention.",
    default_address=None,  # default logic = no extra security
    string_semantics="literal",
    examples=[
        "np(security='high')",
        "np(security={'level': 'high', 'hooks': True})",
        "np(security='myapp.sec:build_kit')   # load a security-kit factory by address",
        "np(security=lambda reg: norpagent.safe(reg, level='standard', hooks=True))",
    ],
))

_slot(SlotSpec(
    name="plugins",
    description="External plugins (the full pipeline: signature→audit→import restrictions→registration).",
    protocol="A directory-path list, or callable(registry) returning plugin load results.",
    default_address=None,  # default logic = no external plugins
    string_semantics="literal",
    examples=[
        "np(plugins=['./my_plugins'])",
    ],
))

# ── presentation layer ────────────────────────────────────

_slot(SlotSpec(
    name="frontend",
    description="Frontend: the user-facing input/output shell. Frontends must be "
                "highly swappable — console / headless / web / any custom frontend "
                "are the same slot. When a string value is an .html/.htm file path, "
                "it assembles per the \"HTML path direct mount\" semantics into "
                "WebFrontend(html=<that path>) (v0.9).",
    protocol=(
        "Frontend protocol (norpagent.frontends.base.Frontend): "
        "attach(engine) binds the engine; start() starts (background thread); stop() stops; "
        "is_alive() liveness query."
    ),
    default_address="norpagent.frontends.web:WebFrontend",
    factory_kwargs={"layer": "the owning architecture layer", "config": "extra config dict"},
    examples=[
        "np()                                                       # default web frontend",
        "np(frontend='norpagent.frontends.headless:HeadlessFrontend')  # pure API",
        "np(frontend='norpagent.frontends.console:ConsoleFrontend')    # command line",
        "np(frontend='myapp.my_ui:create')                             # fully custom",
        "np(frontend='norpagent.frontends.web:WebFrontend;html=/path/to/my.html')"
        "  # web frontend + custom main page (slot mount parameter; replaces the / route page)",
        "np(frontend='/path/to/my.html')   # HTML path direct mount (v0.9; equivalent to the line above)",
        "np(frontend='norpagent.frontends.web:WebFrontend;flow_html=/path/to/flow.html')"
        "  # web frontend + custom flow page (replaces the /flow route page)",
    ],
))

_slot(SlotSpec(
    name="ui",
    description="Event rendering adapter: the rendering layer under the frontend, "
                "rendering event-bus events into text / interface elements "
                "(ConsoleUI / WebUI / custom).",
    protocol="UIAdapter protocol (norpagent.protocols.ui.UIAdapter): "
             "on_event / ask_user / notify.",
    default_address=None,  # default logic = use the UI adapter declared by the preset
    string_semantics="name_or_address",
    examples=[
        "np(ui=MyRenderer())                              # a custom renderer instance",
        "np(ui='web')                                     # a registered renderer name",
        "np(ui='myapp.render:create')                     # load a renderer factory by address",
    ],
))

_slot(SlotSpec(
    name="preset",
    description="Preset mode: an out-of-the-box combination declaration of a whole component set.",
    protocol="A preset name (str; must be registered) or a Preset instance. Strings "
             "resolve first as registered preset names, then as module addresses "
             "(an address may point at a factory returning a Preset instance).",
    default_address=None,  # default logic = the 'standard' preset
    string_semantics="name_or_address",
    examples=[
        "np(preset='standard')                            # standard mode",
        "np(preset='ptc')                                 # PTC mode",
        "np(preset='myapp.presets:build_embedded')        # load a preset factory by address",
        "np(preset=Preset(name='mine', ...))               # a custom preset",
    ],
))

# ── base-service layer ────────────────────────────────────

_slot(SlotSpec(
    name="logger",
    description="Log logger. v0.9.1 address-first: strings shaped like a pure "
                "address load by address (the factory returns a logging.Logger); "
                "everything else is a literal value.",
    protocol="logging.Logger protocol: debug / info / warning / error.",
    default_address=None,  # default logic = logging.getLogger('norpagent')
    string_semantics="literal",
    examples=[
        "np(logger=logging.getLogger('my.app'))",
        "np(logger='myapp.log:get_logger')      # load a logger factory by address",
    ],
))

_slot(SlotSpec(
    name="storage",
    description="Persistent storage (where session databases, task states etc. "
                "land on disk). v0.9.1 address-first: strings shaped like a pure "
                "address load a storage factory by address; everything else "
                "(directory paths) keeps the literal value.",
    protocol="str (directory path) or a storage object with a .root / .path attribute.",
    default_address=None,  # default logic = ~/.norpagent
    string_semantics="literal",
    examples=[
        "np(storage='./my_data')",
        "np(storage='myapp.store:create')     # load a storage factory by address",
    ],
))

_slot(SlotSpec(
    name="error_handler",
    description="Error handling: the last line of defense for task-level "
                "exceptions. v0.9.1 address-first: strings shaped like a pure "
                "address load by address (an address should point at a factory "
                "returning a handler function, or a module-level handler called "
                "per the callable-factory convention).",
    protocol="callable(error, engine) -> None.",
    default_address=None,  # default logic = log and set the engine state
    string_semantics="literal",
    examples=[
        "np(error_handler=lambda exc, eng: print(exc))",
        "np(error_handler='myapp.handlers:get_handler')  # load a handler factory by address",
    ],
))


# snapshot of built-in slot names: these names are framework structural contracts
# (referenced by the engine / frontend / docs); protected — cannot be unregistered
# or have their specs overridden; their **values** can still be hot-replaced at
# any time (np.remount). Custom slot names have no such restriction.
_BUILTIN_SLOT_NAMES: frozenset = frozenset(SLOT_SPECS)


def get_slot(name: str) -> SlotSpec:
    """Get a slot spec by name; unknown slots raise KeyError."""
    with _LOCK:
        return SLOT_SPECS[name]


def all_slot_names() -> List[str]:
    """All slot names (in definition order; includes runtime-registered custom slots)."""
    with _LOCK:
        return list(SLOT_SPECS.keys())


def snapshot_slots() -> Dict[str, SlotSpec]:
    """Slot-table snapshot: a stable view during registration / unregistration.

    Assembly loops (ArchLayer.connect / describe / launch parameter splitting /
    hot-mount validation) iterate over snapshots, avoiding dict-iteration errors
    when running concurrently with register_slot / unregister_slot.
    """
    with _LOCK:
        return dict(SLOT_SPECS)


def is_builtin_slot(name: str) -> bool:
    """Whether the slot name is a protected built-in slot (the 18 framework structural contracts)."""
    return name in _BUILTIN_SLOT_NAMES


def register_slot(spec: SlotSpec | Dict[str, Any], *,
                  replace: bool = False) -> SlotSpec:
    """Register a custom slot — the hot-pluggable slot table (v0.9).

    - ``spec``: a SlotSpec instance or a field dict (dict auto-constructs);
    - takes effect immediately after registration: ``np(newslot=...)`` parameter
      validation, ArchLayer assembly, ``np.remount(newslot=...)`` hot replacement
      and ``layer.describe()`` listing all recognize the new slot; no process restart;
    - ``replace=True``: hot-replaces the spec of a same-named **custom** slot
      (default address / string semantics / applier / rebuild flag). Assembled
      implementations stay untouched; the next ``np.remount(slot=...)`` resolves
      per the new spec.

    Protection rules:
    - the 18 built-in slot names cannot be registered / overridden / unregistered
      (framework structural contracts; their values can be hot-replaced anytime
      with ``np.remount``);
    - slot names must be valid Python identifiers (np()'s keyword parameters), and
      cannot be Python keywords or ``prompt`` / ``config`` (launch's special keys);
    - ``applier`` must be None or callable; ``string_semantics`` must be one of
      address / name / name_or_address / literal.

    Assembly semantics:
    - ``applier(reg, layer, value, params, ctx)`` is called by
      runtime.mount.apply_slot_overrides during assembly and hot mount (when the
      slot value is non-empty). The same registry may be called repeatedly (hot
      mount); appliers must be reentrant-safe; ctx provides the four mutable
      containers components / extras / overrides / meta (see the SlotSpec.applier
      field docs);
    - ``remount_rebuild_agent=True``: hot-rebuild the AgentRuntime after a hot
      mount (slots whose applier registers generic components into the preset's
      components should set True);
    - string semantics are the same as built-in slots: address (module address) /
      name / name_or_address / literal (passed verbatim to the applier).
    """
    if isinstance(spec, dict):
        spec = SlotSpec(**spec)
    _validate_slot_spec(spec)
    with _LOCK:
        if spec.name in _BUILTIN_SLOT_NAMES:
            raise SlotError(
                f"slot '{spec.name}' is a built-in slot (framework structural contract); "
                "it cannot be registered or have its spec overridden; built-in slot "
                "values can be hot-replaced anytime with np.remount"
            )
        exists = spec.name in SLOT_SPECS
        if exists and not replace:
            raise SlotError(
                f"slot '{spec.name}' is already registered; replace=True can hot-replace its spec"
            )
        SLOT_SPECS[spec.name] = spec
        return spec


def unregister_slot(name: str) -> SlotSpec:
    """Unregister a custom slot; returns the removed spec.

    - built-in slot names are protected; unregistering raises SlotError;
    - implementations already assembled onto the architecture layer stay untouched
      (no longer appear in describe / slot validation); after re-registering the
      same name, np.remount can re-resolve it.
    """
    with _LOCK:
        if name in _BUILTIN_SLOT_NAMES:
            raise SlotError(
                f"slot '{name}' is a built-in slot (framework structural contract); it cannot be unregistered"
            )
        spec = SLOT_SPECS.pop(name, None)
        if spec is None:
            raise SlotError(f"slot '{name}' does not exist (cannot unregister)")
        return spec


def _validate_slot_spec(spec: SlotSpec) -> None:
    if not isinstance(spec, SlotSpec):
        raise SlotError(f"spec must be a SlotSpec instance, got {type(spec)}")
    name = spec.name
    if (not isinstance(name, str) or not name.isidentifier()
            or keyword.iskeyword(name)):
        raise SlotError(
            f"slot name {name!r} is illegal: must be a valid Python identifier "
            "(np() keyword parameter name) and must not be a Python keyword"
        )
    if name in _RESERVED_SLOT_NAMES:
        raise SlotError(
            f"slot name {name!r} is a launch special key (prompt / config); cannot register"
        )
    if spec.string_semantics not in _STRING_SEMANTICS:
        raise SlotError(
            f"slot '{name}' has illegal string semantics {spec.string_semantics!r}; "
            f"must be one of {list(_STRING_SEMANTICS)}"
        )
    if spec.applier is not None and not callable(spec.applier):
        raise SlotError(f"slot '{name}' applier must be callable or None")


__all__ = [
    "SlotSpec",
    "SlotError",
    "SLOT_SPECS",
    "get_slot",
    "all_slot_names",
    "snapshot_slots",
    "is_builtin_slot",
    "register_slot",
    "unregister_slot",
]
