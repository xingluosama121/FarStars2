# Copyright (c) 2026 xingluosama121, MIT Licensed
"""Architecture layer: the address function system.

The realization of "everything except what is minimally needed to run is modular":

- every capability = one slot (see norpagent.arch.slots.SLOT_SPECS);
- a slot without an address = runs the default logic; with an address = mounts the
  implementation by address;
- address shapes: ``"pkg.mod"`` / ``"pkg.mod:attr"`` / factory / instance;
- the assembly manifest is observable: layer.describe() prints line by line what
  each slot is connected to;
- hot-pluggable slot table (v0.9): register_slot / unregister_slot register custom
  slots at runtime; registration plugs into the whole assembly / hot-mount /
  manifest pipeline;
- all slots support address-based loading (v0.9.1): literal / name slots and dict
  key-value values also accept pure addresses (pkg.mod[:attr]); see
  norpagent.arch.address.is_address_like.

The minimal kernel required for runtime operation (not replaceable; only four
items): ArchLayer, the address resolver, Registry, EventBus.
"""

from norpagent.arch.address import (
    AddressError,
    is_address_like,
    resolve_address,
)
from norpagent.arch.layer import ArchLayer, call_factory
from norpagent.arch.slots import (
    SLOT_SPECS,
    SlotError,
    SlotSpec,
    all_slot_names,
    get_slot,
    is_builtin_slot,
    register_slot,
    snapshot_slots,
    unregister_slot,
)

__all__ = [
    "ArchLayer",
    "SlotSpec",
    "SlotError",
    "SLOT_SPECS",
    "get_slot",
    "all_slot_names",
    "snapshot_slots",
    "is_builtin_slot",
    "register_slot",
    "unregister_slot",
    "resolve_address",
    "is_address_like",
    "call_factory",
    "AddressError",
]
