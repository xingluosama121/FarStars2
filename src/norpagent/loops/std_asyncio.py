# Copyright (c) 2026 xingluosama121, MIT Licensed
"""Compatibility shim: historical module name of the old default async_loop slot address.

Since 0.8 the default loop implementation has moved entirely to the library's
built-in **self-developed nasyncio core** (norpagent.nasyncio +
norpagent.loops.nasyncio.NasyncioLoopRuntime). This module no longer imports
the standard asyncio; it only re-exports the old class name ``StdLoopRuntime``
pointing to the new implementation so that historical code keeps working:

    np(async_loop='norpagent.loops.std_asyncio:StdLoopRuntime')
    from norpagent.loops.std_asyncio import StdLoopRuntime

New code should use directly:

    from norpagent.loops.nasyncio import NasyncioLoopRuntime

The norpagent library has **zero asyncio imports** — the scheduling core embraces
the self-developed nasyncio; see norpagent.nasyncio and DEVELOPER_MANUAL ch. 4.
"""
from __future__ import annotations

from norpagent.loops.nasyncio import NasyncioLoopRuntime, StdLoopRuntime

__all__ = ["StdLoopRuntime", "NasyncioLoopRuntime"]
