# Copyright (c) 2026 xingluosama121, MIT Licensed
"""Task cancellation signal: the cancellation event context inside submitted tasks (Ctrl+C / engine stop).

The default loop runtime (norpagent.loops.nasyncio.NasyncioLoopRuntime, whose
scheduling core is the library's built-in self-developed norpagent.nasyncio)
wraps every submitted task in a contextvars context carrying a cancel event;
task bodies (sandboxes / model adapters / tools) can read ``cancel_requested()``
at any time to check whether cancellation was requested and exit by themselves as
soon as possible — force-killing child processes, interrupting streamed reads —
instead of waiting for timeout fallbacks.

Implementation details: contextvars flow into the worker thread via
``contextvars.copy_context().run(fn)``, so reads inside a worker thread see the
cancel event of the current task; reads outside a worker thread see the default
None (treated as not cancelled / not inside a task).
"""
from __future__ import annotations

import contextvars
import threading
from typing import Optional

_current_cancel: "contextvars.ContextVar[Optional[threading.Event]]" = (
    contextvars.ContextVar("norpagent_current_cancel", default=None)
)


def current_cancel_event() -> Optional[threading.Event]:
    """The cancel event of the current submitted task; None when not inside a submitted task."""
    return _current_cancel.get()


def cancel_requested() -> bool:
    """Whether the current task has been asked to cancel (Ctrl+C / engine stop / interrupt).

    Returning True means the caller has given up waiting for this task; the task
    body should exit by itself as soon as possible.
    """
    event = _current_cancel.get()
    return event is not None and event.is_set()


__all__ = ["current_cancel_event", "cancel_requested"]
