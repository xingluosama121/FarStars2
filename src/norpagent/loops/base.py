# Copyright (c) 2026 xingluosama121, MIT Licensed
"""LoopRuntime protocol: the unified contract of the event loop system.

Implementations of the ``async_loop`` slot (i.e. the architecture function
norpagent.nasyncio()) must satisfy this protocol. The default implementation is
the library's built-in **self-developed nasyncio adapter**
(norpagent.loops.nasyncio.NasyncioLoopRuntime; scheduling core is
norpagent.nasyncio, no dependency on the standard asyncio); filling in an address
replaces it with any event loop system, swapping out the whole scheduling core.

The loop system is fully decoupled from agent logic: the engine (runtime.engine)
interacts with the loop only through this protocol and never imports any concrete
loop implementation.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class LoopRuntime(Protocol):
    """Event loop runtime interface.

    The implementation approach is free (standard asyncio / self-developed coroutine
    trampoline / thread pool); it only needs to satisfy the contract:

    - after start(), the loop is in a submittable state;
    - submit() executes a synchronous function in the loop context and returns its
      result (implementations may choose real async or a thread pool simulation;
      the default self-developed nasyncio = self-developed event loop thread +
      daemon worker pool);
    - stop() and join() are callable from any thread for cleanup.
    """

    name: str

    def start(self) -> None:
        """Start the loop (usually holds a dedicated thread running run_forever)."""
        ...

    def stop(self) -> None:
        """Request the loop to stop (thread-safe)."""
        ...

    def is_running(self) -> bool:
        """Whether the loop is still running."""
        ...

    def join(self, timeout: float = None) -> None:
        """Wait for the loop thread to exit."""
        ...

    def submit(self, fn, *args, **kwargs) -> Any:
        """Execute the synchronous function fn in the loop context and return its result.

        Blocks the caller until fn finishes; calling after the loop has stopped
        raises RuntimeError.
        """
        ...

    # ── optional extensions (not mandatory; the engine probes with hasattr) ──
    def interrupt(self) -> None:
        """Request cancellation of all in-flight submit tasks (Ctrl+C / engine-stop path).

        The default implementation sets each task's cancel event (propagated via
        contextvars; see norpagent.loops.cancel): sandboxes force-kill child
        processes, model streams interrupt, task bodies exit early. Does not wait
        for tasks to actually finish. When not implemented, the engine falls back
        to waiting for tasks to time out on their own.
        """
        ...

    def submit_async(self, fn, *args, **kwargs) -> Any:
        """Optional: submit fn in the loop context and return immediately with a cancellable handle.

        Handle contract (implemented by the default loop as
        ``norpagent.loops.nasyncio.NasyncTaskHandle``): ``cancel()`` cancels
        exactly this task (task bodies read norpagent.loops.cancel.cancel_requested
        and exit early), ``cancelled()`` / ``done()`` are booleans, ``wait(timeout)``
        blocks until done, ``result(timeout)`` returns the task's value / re-raises
        its exception. When not implemented, the engine falls back to running the
        task in a dedicated worker thread and cancellation degrades to a request
        flag (engine.stop() / stop_all_tasks() still cancel in-flight tasks through
        interrupt()).
        """
        ...


__all__ = ["LoopRuntime"]
