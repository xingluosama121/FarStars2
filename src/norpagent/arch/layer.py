# Copyright (c) 2026 xingluosama121, MIT Licensed
"""Architecture layer (ArchLayer): the slot connector.

ArchLayer is the brick tray for "building blocks":

1. receives a set of slot values (keyword arguments / config dict);
2. a slot left empty → uses the default implementation (library built-in logic);
3. a filled address → resolves the address (norpagent.arch.address) and mounts
   the implementation onto the slot; exception (v0.9): a string value of the
   frontend slot that is an .html/.htm file path is passed through to the
   assembler per the "HTML path direct mount" semantics (equivalent to
   WebFrontend(html=<that path>)), coexisting with address-style mounting;
   v0.9.1: literal / name slots also accept addresses — strings shaped like a
   pure address (pkg.mod[:attr]; see address.is_address_like) load by address;
   otherwise the original semantics stand; dict slot values support pure-address
   resolution of key-value pairs (an address-shaped value resolves into an object;
   resolution failures raise AddressError; hooks-slot values are callbacks
   themselves and are not called);
4. factory-class addresses get context injected by signature (layer / slot /
   config / ...); keys the factory does not declare are ignored automatically, so
   factories of any style can plug in.

After assembly, ``layer[slot]`` directly yields the implementation object, and
``layer.describe()`` prints the full assembly manifest (observability of
systematic engineering).

The slot table itself is hot-pluggable (v0.9): beyond SLOT_SPECS, custom slots can
be registered at runtime via norpagent.arch.slots.register_slot(); connect /
remount / describe / set_default of this layer all work per the **live slot table
at call time** — connect idempotently fills in late-registered slots, and remount
applies to newly registered slots too.
"""

from __future__ import annotations

import inspect
import os
from typing import Any, Callable, Dict, Optional

from norpagent.arch.address import (
    AddressError,
    is_address_like,
    resolve_address,
)
from norpagent.arch.slots import (
    SlotSpec,
    all_slot_names,
    get_slot,
    snapshot_slots,
)

# remount()'s "no new value given" sentinel: distinguished from explicit None (clearing the slot).
_RAISE = object()

# slots with the "HTML path direct mount" semantics (v0.9): a string value of these
# slots that is an .html/.htm file path is no longer resolved as a module address;
# it is passed through to the assembler verbatim for semantic conversion
# (frontend → WebFrontend(html=<path>)).
_HTML_PATH_SLOTS = frozenset(("frontend",))


def _is_html_path(value: str) -> bool:
    """Whether a string is an HTML file path (existence not validated; the assembler validates it).

    Rule: no config clause (";" — that is address-style mounting's ;key=value,
    e.g. "WebFrontend;html=C:\\a\\b.html" also ends with .html and must be
    excluded), and ends with .html/.htm. Windows drive paths ("H:\\a\\b.html") and
    relative paths ("./page.html") both match; module addresses (containing ";")
    do not.
    """
    lowered = value.strip().lower()
    if ";" in lowered:
        return False
    return lowered.endswith(".html") or lowered.endswith(".htm")


def _resolve_dict_values(value: Dict[str, Any], slot: str,
                         ctx: Dict[str, Any]) -> Dict[str, Any]:
    """Recursively resolve pure-address strings inside dict slot values (key-value address resolution).

    Handled uniformly for all slots' dict-shaped values (tools mappings / hooks
    mappings / custom-slot dict values, etc.):

    - a string value **shaped like a pure address** (``pkg.mod[:attr]``) → resolved
      by address into an object (module / factory / instance); resolution failures
      raise AddressError (strict: an explicitly written address should error
      clearly, never silently fall back);
    - a resolved **callable** is called per the factory convention
      (``call_factory``, injecting layer / slot / config; the address's
      ``;key=value`` clause parses into the factory config) — **except the hooks
      slot**: its protocol explicitly says values are "callbacks themselves"
      (``{hook name: callback}``); an address-pointed callback is kept as-is, not called;
    - nested dicts recurse (any depth, inheriting the same calling context);
    - list elements are **not** resolved — lists keep literal semantics (e.g. the
      plugin directory path list; tools list elements are specially judged as
      "name or address" by the assembler);
    - non-string values are kept as-is.

    ctx is built by the caller (``ArchLayer._context``) with the layer / slot /
    config keys; the factory-clause config parsed here merges with ctx["config"]
    (the factory clause wins).
    """
    out: Dict[str, Any] = {}
    for key, item in value.items():
        if isinstance(item, str) and is_address_like(item):
            obj = resolve_address(item, slot=slot)
            if callable(obj) and slot != "hooks":
                cfg = dict(ctx.get("config") or {})
                if ";" in item:
                    cfg.update(_parse_subconfig_pairs(item))
                obj = call_factory(obj, {**ctx, "config": cfg})
            out[key] = obj
        elif isinstance(item, dict):
            out[key] = _resolve_dict_values(item, slot, ctx)
        else:
            out[key] = item
    return out


def _parse_subconfig_pairs(address: str) -> Dict[str, str]:
    """Parse the config clause (``;key=value`` pairs) in a string address."""
    cfg: Dict[str, str] = {}
    if ";" in address:
        for pair in address.split(";")[1:]:
            if "=" in pair:
                k, _, v = pair.partition("=")
                cfg[k.strip()] = v.strip()
    return cfg


def call_factory(factory: Any, ctx: Dict[str, Any]) -> Any:
    """Call a factory by signature (the standard calling convention of address functions).

    - a callable factory (function / class) → called, injecting the ctx keys its
      signature accepts; when the factory accepts no context at all, called with
      no arguments as fallback;
    - a non-callable factory (module / instance / value) → returned as-is.

    This way the same slot can accept a "file-level module implementation", a
    "context-aware factory function", or an "existing instance".
    """
    if not callable(factory):
        return factory
    try:
        sig = inspect.signature(factory)
    except (TypeError, ValueError):
        # callables without an introspectable signature (e.g. builtins): call with no args
        return factory()
    params = sig.parameters
    has_var_kw = any(
        p.kind is inspect.Parameter.VAR_KEYWORD for p in params.values()
    )
    kwargs: Dict[str, Any] = {}
    for key, value in ctx.items():
        param = params.get(key)
        if param is not None:
            if param.kind in (inspect.Parameter.POSITIONAL_OR_KEYWORD,
                              inspect.Parameter.KEYWORD_ONLY):
                kwargs[key] = value
        elif has_var_kw:
            kwargs[key] = value
    return factory(**kwargs)


class ArchLayer:
    """Architecture layer: the full assembly surface of one np() startup.

    Usage::

        layer = ArchLayer(async_loop="myapp.loop:create", preset="standard")
        layer.connect()
        loop = layer["async_loop"]        # the connected event loop system
        layer.describe()                  # print the assembly manifest
    """

    def __init__(
        self,
        config: Optional[Dict[str, Any]] = None,
        **slot_values: Any,
    ) -> None:
        # merge the config dict with keywords: keywords win (more specific)
        self.config: Dict[str, Any] = dict(config or {})
        self.config.update({k: v for k, v in slot_values.items() if v is not None})
        self._impls: Dict[str, Any] = {}
        self._defaults: Dict[str, Callable[[Dict[str, Any]], Any]] = {}
        # per-slot extra sub-configs parsed from addresses (";key=value" clause / config injection)
        self._subconfigs: Dict[str, Dict[str, Any]] = {}
        self._connected = False

    # ── default implementation registration ───────────────

    def set_default(self, slot: str, factory: Callable[[Dict[str, Any]], Any]) -> None:
        """Register the default implementation factory of a slot (ctx -> implementation).

        Called by the assembler (runtime.mount) before connecting, registering the
        "library built-in logic" as each slot's default implementation; user
        addresses take priority. Custom slots can also register defaults here
        (effective when the value is None).
        """
        if slot not in snapshot_slots():
            raise KeyError(f"unknown slot '{slot}'. Available slots: {all_slot_names()}")
        self._defaults[slot] = factory

    # ── connecting ────────────────────────────────────────

    def connect(self) -> "ArchLayer":
        """Resolve and assemble all slots (idempotent: repeated calls only fill in newly added slots).

        The slot table can extend at runtime: for slots registered after connect(),
        calling connect() again only connects the missing slots (assembled ones
        stay untouched) — no need to rebuild the whole architecture layer; you can
        also connect a single slot with remount(slot, value).
        """
        for slot in snapshot_slots():
            if self._connected and slot in self._impls:
                continue  # already assembled: skip (only late-registered slots keep connecting)
            self._impls[slot] = self._connect_slot(slot)
        self._connected = True
        return self

    def remount(self, slot: str, value: Any = _RAISE) -> Any:
        """Runtime hot mount: replace a slot implementation (any slot; no restart).

        - ``value`` omitted: re-resolve the implementation per the current config
          value. A string address first invalidates the corresponding module
          cache, so "edit a module file, then call remount" hot-loads the changed
          code at runtime (hot reload);
        - ``value`` None: clear the slot config (fall back to default logic);
        - other values: replace the slot config and resolve per the new value.

        When already connected, immediately rebuilds the slot implementation and
        returns it; when not connected, only updates the config (resolved
        uniformly at connect time; returns None).

        Hot-pluggable slot table (v0.9): custom slots registered at runtime can
        also be remounted — resolved per the spec at registration time; after a
        replace=True hot replacement of the spec, remounting again resolves per
        the new spec.
        """
        if slot not in snapshot_slots():
            raise KeyError(f"unknown slot '{slot}'. Available slots: {all_slot_names()}")
        if value is _RAISE:
            value = self.config.get(slot)
        if isinstance(value, str):
            self._invalidate_address_module(value)
        if value is None:
            self.config.pop(slot, None)
        else:
            self.config[slot] = value
        if not self._connected:
            return None
        impl = self._connect_slot(slot)
        self._impls[slot] = impl
        return impl

    @staticmethod
    def _invalidate_address_module(address: str) -> None:
        """Invalidate the module cache of a string address (prerequisite for hot mounts).

        Two-step invalidation:

        1. delete the module's bytecode cache (the .pyc at ``module.__cached__``) —
           without this, importlib validates by (mtime-seconds, size), and a
           same-size file rewritten within the same second is misjudged as "cache
           still fresh", so re-import yields the old code;
        2. pop the ``sys.modules`` entry; the next resolution re-imports from disk.

        Only the module name in the address is handled (the semicolon clause and
        :attr are not part of the module path).
        """
        import os
        import sys

        addr = address.split(";", 1)[0].strip()
        if not addr:
            return
        module_name = addr.partition(":")[0].strip()
        if not module_name:
            return
        module = sys.modules.get(module_name)
        if module is not None:
            cached = getattr(module, "__cached__", None)
            if cached:
                try:
                    os.remove(cached)
                except OSError:
                    pass
        sys.modules.pop(module_name, None)

    def _connect_slot(self, slot: str) -> Any:
        spec: SlotSpec = get_slot(slot)
        value = self.config.get(slot)
        if value is None:
            default_factory = self._defaults.get(slot)
            if default_factory is None:
                # semantics: the slot is unspecified → the implementation is None,
                # handled by the assembler per the "preset declarations" default
                # logic (e.g. the component slots model / tools / session).
                self._subconfigs[slot] = {}
                return None
            self._subconfigs[slot] = {}
            return default_factory(self._context(slot, {}))
        # address / value given: handle per the slot's declared string semantics
        semantics = spec.string_semantics
        if isinstance(value, str):
            # the frontend slot's "HTML path direct mount" semantics (v0.9):
            # when the value itself is an .html/.htm file path, it is no longer
            # resolved as a module address; it is passed through verbatim to the
            # assembler (runtime.mount.coerce_frontend assembles it into
            # WebFrontend(html=<that path>)). Equivalent to and coexisting with
            # address-style mounting ("pkg.mod:attr;html=...").
            if slot in _HTML_PATH_SLOTS and _is_html_path(value):
                self._subconfigs[slot] = {}
                return value
            if semantics in ("name", "name_or_address"):
                # a registry component name / name-then-address: passed through
                # verbatim, decided by the assembler (name_or_address address
                # resolution also happens in the assembler — it needs the registry
                # context for the "name first" decision).
                self._subconfigs[slot] = {}
                return value
            if semantics == "literal":
                # literal-value slots are "address-first" (v0.9.1): a string
                # shaped like a pure address (pkg.mod[:attr]) → load the
                # implementation by address (resolution failures raise
                # AddressError; never silently fall back); everything else
                # (security levels / storage paths / logger names etc.) keeps the
                # literal value passed through verbatim.
                if is_address_like(value):
                    impl = resolve_address(value, slot=slot)
                    sub_config = self._parse_subconfig(value)
                    self._subconfigs[slot] = sub_config
                    if callable(impl):
                        return call_factory(
                            impl, self._context(slot, sub_config))
                    return impl
                self._subconfigs[slot] = {}
                return value
            # default semantics "address": the string resolves as a module address
            impl = resolve_address(value, slot=slot)
            sub_config = {}
            if ";" in value:
                sub_config = self._parse_subconfig(value)
            self._subconfigs[slot] = sub_config
            # defer_factory slots (agent_runtime): only resolve the address, do
            # not instantiate. The factory call is deferred to the engine assembly
            # phase (NorpEngine._build_agent), when the full context (registry /
            # preset etc.) is ready.
            if callable(impl) and spec.defer_factory:
                return impl
            if callable(impl):
                return call_factory(impl, self._context(slot, sub_config))
            return impl
        # non-string values: dicts get uniform key-value address resolution
        # (v0.9.1) — an address-shaped string inside a dict value resolves by
        # address into an object (resolution failures raise AddressError; a
        # resolved callable is called per the factory convention, except the hooks
        # slot — its values are callbacks themselves). The resolved dict passes
        # through verbatim with name / literal / name_or_address semantics;
        # address semantics treat it as a direct implementation (factories called
        # per the convention).
        if isinstance(value, dict):
            value = _resolve_dict_values(
                value, slot, self._context(slot, {}))
        if semantics in ("name", "literal", "name_or_address"):
            # non-string values (instances / callbacks / classes / dicts): pass
            # through verbatim; the assembler decides how to register / call them
            # (cannot be treated as address factories).
            self._subconfigs[slot] = {}
            return value
        # address semantics: callables called as factories; otherwise as-is.
        impl = value
        self._subconfigs[slot] = {}
        if callable(impl) and spec.defer_factory:
            return impl
        if callable(impl):
            return call_factory(impl, self._context(slot, {}))
        return impl

    @staticmethod
    def _parse_subconfig(address: str) -> Dict[str, str]:
        """Parse the config clause in a string address.

        Shaped like ``"pkg.mod:create;port=9000;theme=dark"`` — the ``key=value``
        pairs after the semicolon are parsed as extra config injected into the
        factory's config parameter. Pure addresses (no semicolon) return an empty dict.
        """
        return _parse_subconfig_pairs(address)

    def _context(self, slot: str, sub_config: Dict[str, Any]) -> Dict[str, Any]:
        """Build the context passed to factories (uniformly injected keys)."""
        cfg = dict(sub_config)
        for key, value in self.config.items():
            if key != slot:
                cfg.setdefault(key, value)
        return {
            "layer": self,
            "slot": slot,
            "config": cfg,
        }

    # ── queries ───────────────────────────────────────────

    def __getitem__(self, slot: str) -> Any:
        if not self._connected:
            raise RuntimeError("the architecture layer is not connect()ed yet; call layer.connect() first")
        return self._impls[slot]

    def get(self, slot: str, default: Any = None) -> Any:
        if not self._connected:
            return default
        return self._impls.get(slot, default)

    def subconfig(self, slot: str) -> Dict[str, Any]:
        """Get the extra sub-config parsed from a slot's address (the ";key=value" clause).

        Consumed by the engine during assembly (e.g. the agent_runtime factory's
        config injection). Returns an empty dict when not resolved.
        """
        return dict(self._subconfigs.get(slot) or {})

    def describe(self) -> str:
        """Assembly manifest: each slot's source (default / address) and implementation.

        Output follows the live slot table (snapshot) at call time; custom slots
        registered at runtime also appear in the manifest.
        """
        lines = ["== NorpAgent architecture layer assembly manifest =="]
        for slot, spec in snapshot_slots().items():
            value = self.config.get(slot)
            impl = self._impls.get(slot)
            if value is None:
                source = "default logic"
            elif isinstance(value, str):
                source = f"address {value!r}"
            else:
                source = f"direct value {type(value).__name__}"
            impl_repr = (
                type(impl).__name__ if impl is not None else "(not connected)"
            )
            lines.append(f"  {slot:<16} <- {source:<28} => {impl_repr}")
        return "\n".join(lines)

    def is_connected(self) -> bool:
        return self._connected


__all__ = ["ArchLayer", "call_factory"]
