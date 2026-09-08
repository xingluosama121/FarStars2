# Copyright (c) 2026 xingluosama121, MIT Licensed
"""Address resolver.

Architecture slots accept four shapes of "address":

    None           -> use the slot's default implementation (library built-in logic)
    "pkg.mod"      -> load that file (module): prefer the module's conventional factory
                      attributes ``create`` / ``build`` / ``default``;
                      if none exist, mount the whole module as the implementation
    "pkg.mod:attr" -> load that file and take the named attribute as the implementation
    callable       -> use directly as the implementation (factory function / class)
    other objects  -> use directly as the implementation (instance / value)

String addresses support an additional config clause (slot mount parameters):
the ``key=value`` pairs after the semicolon are not part of the address itself;
the architecture layer parses them and injects them into the factory's ``config``
parameter (see ``norpagent.arch.layer.ArchLayer``), e.g.
``"pkg.mod:create;timeout=5"``, ``"pkg.mod:attr;html=/path/to/page.html"``.
This module strips the semicolon clause before parsing the address, so
sub-configs never interfere with module path / attribute resolution.

Semantics of "address functions": not filling in (None) just runs the default
logic; filling in an address makes the architecture layer mount that file (or an
object inside it) directly onto the slot, with zero core-code changes.

This module only handles "resolve address → obtain object"; it does not call
factories. Factory context injection and calling rules live in
``norpagent.arch.layer.call_factory``.
"""

from __future__ import annotations

import importlib
import re
from typing import Any

# conventional module-level factory attributes: when an address points at a file
# without ":attr", look for a factory entry inside the file in this order.
_FACTORY_ATTRS = ("create", "build", "default")

# "pure address" shape: dot-separated identifiers (each segment a valid Python
# identifier), with an optional ":attr" segment. Used for the structural check in
# is_address_like.
_PURE_ADDRESS_RE = re.compile(
    r"[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*(?::[A-Za-z_]\w*)?"
)


def is_address_like(value: Any) -> bool:
    """Whether a string looks like a "pure address" (``pkg.mod[:attr]``).

    Pure structural check: no module imports, no side effects, no exceptions.

    - after stripping the ``;key=value`` clause, the whole string is a dot-separated
      identifier (each segment a valid Python identifier) containing at least one
      ``.`` or ``:``;
    - therefore literals like ``"high"`` / ``"./data"`` / ``"my_tool"`` /
      ``"https://api.example.com"`` (values, paths, URLs) are never misclassified;
    - ``"myapp.security:high"`` / ``"myapp.tools"`` / ``"pkg:attr"`` are addresses.

    Used for the "address-first" decision in literal/name semantic slots and dict
    key-value pairs: address-shaped strings load as addresses; everything else
    keeps its original semantics.
    """
    if not isinstance(value, str):
        return False
    addr = value.strip().split(";", 1)[0].strip()
    if not addr:
        return False
    if not _PURE_ADDRESS_RE.fullmatch(addr):
        return False
    return "." in addr or ":" in addr


class AddressError(ImportError):
    """The address cannot be resolved (module missing / attribute missing / empty address)."""


def resolve_address(address: Any, *, slot: str) -> Any:
    """Resolve an "address" into an implementation object.

    Args:
        address: the address value. None means "use the default implementation"
                 (handled by the caller); strings resolve as module paths; any
                 other value is returned as-is.
        slot: slot name, used only in error messages.

    Returns:
        The implementation object (module / factory / instance / value).
        Raises AddressError on failure.
    """
    if address is None:
        return None
    if isinstance(address, str):
        return _resolve_string(address, slot)
    return address


def _resolve_string(address: str, slot: str) -> Any:
    addr = address.strip()
    if not addr:
        raise AddressError(f"slot '{slot}' has an empty address string")
    # strip the ";key=value" config clause: key-value pairs after the semicolon are
    # factory parameters, not part of the module address; ArchLayer parses and
    # injects them into the factory's config (see norpagent.arch.layer.ArchLayer._parse_subconfig).
    addr = addr.split(";", 1)[0].strip()
    if not addr:
        raise AddressError(
            f"slot '{slot}' address '{address}' is missing the module path"
            " (before the semicolon should be 'pkg.mod[:attr]'; after it, the config clause)"
        )
    module_name, sep, attr = addr.partition(":")
    try:
        module = importlib.import_module(module_name)
    except Exception as exc:  # noqa: BLE001 — uniformly wrapped into AddressError
        raise AddressError(
            f"slot '{slot}' address '{address}' cannot import module "
            f"'{module_name}': {exc}"
        ) from exc
    if sep:
        try:
            return getattr(module, attr)
        except AttributeError as exc:
            raise AddressError(
                f"slot '{slot}' address '{address}': module "
                f"'{module_name}' has no attribute '{attr}'"
            ) from exc
    # no ":attr": prefer the module's conventional factory entry
    for name in _FACTORY_ATTRS:
        obj = getattr(module, name, None)
        if obj is not None:
            return obj
    # fallback: mount the whole file (the module itself) as the implementation.
    # the module itself must implement the slot's protocol (e.g. a full LoopRuntime module).
    return module


__all__ = ["AddressError", "resolve_address", "is_address_like"]
