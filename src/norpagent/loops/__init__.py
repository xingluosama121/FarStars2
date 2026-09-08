# Copyright (c) 2026 xingluosama121, MIT Licensed
"""Event loop system package: the landing spot of the architecture function norpagent.nasyncio().

::

    import norpagent as np

    loop = np.nasyncio()                    # default loop (self-developed nasyncio adapter)
    loop = np.nasyncio("myapp.nasync:create")  # custom loop pointed to by an address
    loop = np.nasyncio(MyLoopRuntime())     # an existing instance

Equivalence: ``np.nasyncio(address)`` and ``np(async_loop=address)`` are fully
equivalent; both go through the same architecture slot resolution and factory
calling convention.

The default implementation (NasyncioLoopRuntime, in the nasyncio module of this
package) runs the library's built-in **self-developed nasyncio event loop core**
(norpagent.nasyncio, originally nasync_io, now packaged into the library) — it
does not depend on or import the standard asyncio. See the norpagent.nasyncio
module docs and Developer Manual ch. 4.

Cancellation semantics: inside a submit task you can use ``cancel_requested()``
to check whether Ctrl+C / engine stop requested cancellation (the cancel event is
propagated via contextvars); the task body should exit by itself as soon as
possible (force-kill child processes / interrupt streamed reads). See
norpagent.loops.cancel.
"""

from __future__ import annotations

from typing import Any, Optional

from norpagent.arch.address import resolve_address
from norpagent.arch.layer import call_factory
from norpagent.loops.base import LoopRuntime
from norpagent.loops.cancel import cancel_requested, current_cancel_event
# note: import the submodule first (this triggers loading of
# norpagent.loops.nasyncio), then define the same-named function nasyncio —
# the function is defined later and overrides the name the submodule occupies
# in the package namespace, so that ``from norpagent.loops import nasyncio``
# gets the architecture function.
from norpagent.loops.nasyncio import NasyncioLoopRuntime, StdLoopRuntime  # noqa: F401


def nasyncio(address: Any = None, **config: Any) -> LoopRuntime:
    """Architecture function: obtain the event loop system (async_loop slot).

    Args:
        address: address of the event loop system.
            None           -> default implementation (a NasyncioLoopRuntime instance,
                              based on the library's built-in self-developed nasyncio core);
            "pkg.mod"      -> load the file, take the create/build/default factory,
                              or the whole module as the implementation if none exists;
            "pkg.mod:attr" -> a named object inside the file;
            factory / class / instance -> use directly (factories get the config context injected by signature).

    Returns:
        A loop runtime satisfying the LoopRuntime protocol (not started).
    """
    impl: Any = resolve_address(address, slot="async_loop")
    if impl is None:
        impl = NasyncioLoopRuntime
    if callable(impl):
        impl = call_factory(
            impl,
            {
                "layer": None,
                "slot": "async_loop",
                "config": dict(config),
            },
        )
    return impl


# convenience reference: the default implementation class is directly importable;
# StdLoopRuntime is the legacy 0.7 class name (compat alias; see norpagent.loops.nasyncio)
default = NasyncioLoopRuntime

__all__ = [
    "nasyncio",
    "LoopRuntime",
    "NasyncioLoopRuntime",
    "StdLoopRuntime",
    "default",
    "current_cancel_event",
    "cancel_requested",
]
