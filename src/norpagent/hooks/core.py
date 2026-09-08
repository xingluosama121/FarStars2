# Copyright (c) 2026 xingluosama121, MIT Licensed
"""Hook system core: Hook / HookLayer / HookSystem / BoundHook / HookVeto.

Design goals (the "exposed surface" principle of systematic engineering):

- **every hook is an independent API**: the 9-layer 29 standard hooks under
  ``norpagent.hooks`` are all importable first-class objects, subscribable /
  triggerable / interceptable individually, without scattered string literals;
- **every execution structure can be intervened**: each input, session creation,
  message persistence, message assembly, step, model call, tool call and result
  finalization of AgentRuntime goes through a named hook; mutating hooks can
  rewrite the data flow and ``HookVeto`` can veto with one vote;
- **custom layers / custom hooks**: third parties can declare their own layers
  with ``HookLayer``, or ``define_hook`` directly on a ``HookSystem``; undefined
  named events automatically become dynamic-layer hooks when fired, so
  "fire the event first, define it later" also works;
- **bidirectionally compatible with EventBus**: hook subscribe/publish ultimately
  lands on EventBus, so legacy plugins (15 hook names) and the new hook system
  coexist seamlessly.

Subscription target resolution (the ``system`` parameter) accepts: HookSystem /
EventBus / Registry / AgentRuntime / None (default system).
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from norpagent.kernel.events import EventBus, HookVeto  # noqa: F401 — veto-semantics core type (re-exported from events)

# the layer where dynamic (not pre-defined) hooks live
DYNAMIC_LAYER = "dynamic"


@dataclass
class Hook:
    """The canonical definition of a hook (module-level standalone API).

    - ``name``: hook name (i.e. the EventBus event name);
    - ``layer``: the layer it belongs to;
    - ``order``: in-layer ordering weight;
    - ``mutating``: True means subscribers can rewrite the data flow via return values;
    - ``payload_keys``: documented event payload keys.

    ``subscribe / unsubscribe / emit / intercept`` need a ``system`` to locate the
    bus: pass HookSystem / EventBus / Registry / AgentRuntime; defaults to the
    process-wide default system (``norpagent.hooks.get_default_system()``).
    """

    name: str
    layer: str
    order: int = 0
    mutating: bool = False
    description: str = ""
    payload_keys: tuple = ()

    # ── standalone API: subscribe / publish / intercept ──

    def subscribe(self, fn: Callable, system: Any = None) -> None:
        _resolve_bus(system).subscribe(fn, self.name)

    def unsubscribe(self, fn: Callable, system: Any = None) -> None:
        _resolve_bus(system).unsubscribe(fn, self.name)

    def emit(self, system: Any = None, **payload: Any) -> None:
        _resolve_bus(system).emit(self.name, **payload)

    def intercept(self, system: Any = None, **payload: Any) -> Any:
        return _resolve_bus(system).intercept(self.name, **payload)

    def bind(self, bus: EventBus) -> "BoundHook":
        """Bind to a concrete bus and get the runtime API."""
        return BoundHook(self, bus)

    def __repr__(self) -> str:
        return f"<Hook {self.name} [{self.layer}] mutating={self.mutating}>"


@dataclass
class BoundHook:
    """A hook bound to an EventBus (what AgentRuntime exposes)."""

    definition: Hook
    bus: EventBus

    @property
    def name(self) -> str:
        return self.definition.name

    @property
    def layer(self) -> str:
        return self.definition.layer

    @property
    def mutating(self) -> bool:
        return self.definition.mutating

    @property
    def description(self) -> str:
        return self.definition.description

    @property
    def payload_keys(self) -> tuple:
        return self.definition.payload_keys

    def subscribe(self, fn: Callable) -> None:
        self.bus.subscribe(fn, self.name)

    def unsubscribe(self, fn: Callable) -> None:
        self.bus.unsubscribe(fn, self.name)

    def emit(self, **payload: Any) -> None:
        self.bus.emit(self.name, **payload)

    def intercept(self, **payload: Any) -> Any:
        return self.bus.intercept(self.name, **payload)

    def __repr__(self) -> str:
        return f"<BoundHook {self.name} [{self.layer}] mutating={self.mutating}>"


@dataclass
class HookLayer:
    """A layer of hooks: a group of named hooks around one concern.

    Custom layer example::

        layer = HookLayer("L10_network", order=100, description="network access layer")
        layer.hook("before_network_call", mutating=True,
                   description="before a network request is sent (may rewrite the URL or veto)")
        agent.hooks.install_layer(layer)
        agent.hooks.before_network_call.subscribe(monitor)
    """

    name: str
    order: int = 0
    description: str = ""
    hooks: Dict[str, Hook] = field(default_factory=dict)

    def hook(
        self,
        name: str,
        mutating: bool = False,
        description: str = "",
        payload_keys: tuple = (),
        order: int = 0,
    ) -> Hook:
        """Declare a hook inside the layer (returns the Hook definition, i.e. the standalone API)."""
        h = Hook(
            name=name,
            layer=self.name,
            order=order,
            mutating=mutating,
            description=description,
            payload_keys=payload_keys,
        )
        self.hooks[name] = h
        return h

    def names(self) -> List[str]:
        return list(self.hooks)

    def __repr__(self) -> str:
        return f"<HookLayer {self.name} order={self.order} hooks={len(self.hooks)}>"


class HookSystem:
    """The hook view over one bus: 9 standard layers + an assembly bench for custom layers/hooks.

    ``AgentRuntime.hooks`` / ``Registry.hooks`` expose instances of this class:
    ``runtime.hooks.before_model_call.subscribe(fn)`` is the standard hook API
    usage. The 9 standard layers are installed automatically at construction.
    """

    def __init__(self, bus: EventBus, install_standard: bool = True) -> None:
        self.bus = bus
        self._hooks: Dict[str, BoundHook] = {}
        self._layers: List[HookLayer] = []
        self._lock = threading.RLock()
        if install_standard:
            from norpagent.hooks.standard import STANDARD_LAYERS

            for layer in STANDARD_LAYERS:
                self.install_layer(layer)

    # ── assembly ─────────────────────────────────────────

    def install_layer(self, layer: HookLayer) -> List[BoundHook]:
        """Install a layer (standard or custom). When a same-named hook already
        exists, the original definition is kept, but the layer metadata is
        recorded. Returns the bound objects of this layer's hooks."""
        with self._lock:
            if layer not in self._layers:
                self._layers.append(layer)
            self._layers.sort(key=lambda l: l.order)
            bound: List[BoundHook] = []
            for name, hook in layer.hooks.items():
                if name not in self._hooks:
                    bound_hook = BoundHook(hook, self.bus)
                    self._hooks[name] = bound_hook
                bound.append(self._hooks[name])
            return bound

    def define_hook(
        self,
        name: str,
        *,
        layer: Optional[str] = None,
        mutating: bool = False,
        description: str = "",
        payload_keys: tuple = (),
        order: int = 0,
    ) -> BoundHook:
        """Define a custom hook (may belong to a custom layer); returns the bound API."""
        with self._lock:
            hook = Hook(
                name=name,
                layer=layer or DYNAMIC_LAYER,
                order=order,
                mutating=mutating,
                description=description,
                payload_keys=payload_keys,
            )
            self._hooks[name] = BoundHook(hook, self.bus)
            return self._hooks[name]

    def hook(self, name: str) -> BoundHook:
        """Get a hook; undefined names automatically become dynamic-layer hooks."""
        with self._lock:
            if name not in self._hooks:
                return self.define_hook(name, layer=DYNAMIC_LAYER)
            return self._hooks[name]

    def get(self, name: str, default: Any = None) -> Optional[BoundHook]:
        with self._lock:
            return self._hooks.get(name, default)

    def __getattr__(self, name: str) -> BoundHook:
        """Attribute access: ``hooks.before_step`` gets the bound API directly."""
        with self._lock:
            if name in self._hooks:
                return self._hooks[name]
        raise AttributeError(f"HookSystem has no hook '{name}'")

    # ── queries ──────────────────────────────────────────

    def layers(self) -> List[HookLayer]:
        with self._lock:
            return list(self._layers)

    def list_hooks(self) -> List[BoundHook]:
        with self._lock:
            return sorted(
                self._hooks.values(),
                key=lambda h: (h.definition.order, h.name),
            )

    def list_hook_names(self) -> List[str]:
        with self._lock:
            return sorted(self._hooks)

    def layer_of(self, name: str) -> Optional[HookLayer]:
        with self._lock:
            for layer in self._layers:
                if name in layer.hooks:
                    return layer
            return None


# ── default system (the default landing spot of module-level standalone APIs) ──

_default_system: Optional[HookSystem] = None
_default_lock = threading.Lock()


def get_default_system() -> HookSystem:
    """The process-wide default hook system (with its own dedicated bus).

    Module-level hook APIs (e.g. ``norpagent.hooks.before_model_call.subscribe(fn)``)
    land here when called without a ``system`` parameter. When explicitly using a
    Registry / AgentRuntime, pass ``system=...`` (the registry uses a private bus
    by default to guarantee isolation).
    """
    global _default_system
    with _default_lock:
        if _default_system is None:
            _default_system = HookSystem(EventBus())
        return _default_system


def _resolve_bus(system: Any) -> EventBus:
    if system is None:
        return get_default_system().bus
    if isinstance(system, EventBus):
        return system
    if isinstance(system, HookSystem):
        return system.bus
    hooks = getattr(system, "hooks", None)
    if hooks is not None:
        return hooks.bus
    bus = getattr(system, "bus", None)
    if isinstance(bus, EventBus):
        return bus
    raise TypeError(
        f"cannot resolve hook subscription target: {type(system).__name__}. "
        "Pass a HookSystem / EventBus / Registry / AgentRuntime."
    )
