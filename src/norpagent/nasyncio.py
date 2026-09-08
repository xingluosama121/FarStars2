# ============================================================================
# norpagent.nasyncio — self-developed async IO library (packaged into the norpagent library)
#
# The event loop core is fully self-developed; it does not call or depend on the
# standard asyncio.
#
# Design goals:
#   1. The event loop scheduling core (Task coroutine trampoline / timer heap /
#      thread-safe wakeup) is fully self-developed, for complete control over the
#      async loop logic (freedom)
#   2. The low-level layer only depends on non-asyncio standard-library modules:
#      threading / queue / heapq / selectors / socket /
#      concurrent.futures / subprocess / os / time
#   3. Provides same-named APIs one-to-one with common asyncio usage; code
#      familiar with asyncio can migrate by replacing "import asyncio" with
#      "import norpagent.nasyncio" (no dependency on the standard asyncio)
#
# Thread model:
#   - one EventLoop is bound to one thread (consistent with the norpagent
#     architecture: one loop thread per session)
#   - the loop belongs to whichever thread calls run_forever
#   - cross-thread submission (call_soon_threadsafe / Event.set / Future
#     completion notification / Task.cancel / run_coroutine_threadsafe) wakes the
#     loop thread blocked in select via a "thread-safe queue + socketpair
#     self-pipe"
#
# Position in norpagent:
#   - this module is the scheduling core of the async_loop slot's default
#     implementation (norpagent.loops.nasyncio); the norpagent library no longer
#     imports the standard asyncio (zero dependency).
#   - the top-level ``norpagent.nasyncio`` (i.e. ``np.nasyncio``) binds to this
#     module: calling np.nasyncio() directly is equivalent to the architecture
#     function (returns a LoopRuntime); this module is also callable (see
#     _CallableCoreModule at the end), so:
#        import norpagent.nasyncio            → gets this core module
#        np.nasyncio.EventLoop                → the self-developed event loop class
#        np.nasyncio()                        → a LoopRuntime (default implementation)
#
# Copyright: Copyright (c) 2026 xingluosama
# ============================================================================

import concurrent.futures
import heapq
import itertools
import os
import queue as _queue
import selectors
import socket
import subprocess as _subprocess
import sys
import threading
import time as _time
import traceback as _traceback
from collections import deque

__version__ = "2.0.1"

__all__ = [
    # exceptions
    "CancelledError",
    "InvalidStateError",
    "TimeoutError",
    # loops
    "EventLoop",
    "AbstractEventLoop",
    "new_event_loop",
    "set_event_loop",
    "get_event_loop",
    "get_running_loop",
    # scheduling handles
    "Handle",
    "TimerHandle",
    # Future / Task
    "Future",
    "Task",
    "ensure_future",
    "run_coroutine_threadsafe",
    # synchronization primitives
    "Event",
    "Lock",
    "Condition",
    # utility functions
    "sleep",
    "wait_for",
    # subprocess
    "Process",
    "create_subprocess_shell",
    "create_subprocess_exec",
    "subprocess",
]


# ═══════════════════════════════════════════════════════════════
#  exception definitions
# ═══════════════════════════════════════════════════════════════

class CancelledError(BaseException):
    """A coroutine was cancelled (aligned with asyncio.CancelledError: inherits
    BaseException so ordinary except Exception does not swallow it; cancellation
    semantics always pierce through)."""


class InvalidStateError(Exception):
    """Illegal Future/Task state operation."""


# asyncio.TimeoutError was an alias of the built-in TimeoutError before 3.11;
# reuse the built-in class directly here so except TimeoutError stays compatible.
TimeoutError = TimeoutError


# ═══════════════════════════════════════════════════════════════
#  scheduling handles
# ═══════════════════════════════════════════════════════════════

class Handle:
    """Handle returned by call_soon / call_soon_threadsafe."""

    __slots__ = ("_cb", "_args", "_cancelled", "_loop")

    def __init__(self, cb, args, loop):
        self._cb = cb
        self._args = args
        self._cancelled = False
        self._loop = loop

    def cancel(self):
        """Cancel the callback. Already-executed or executing callbacks cannot be cancelled."""
        self._cancelled = True

    def cancelled(self) -> bool:
        return self._cancelled

    def _run(self):
        if not self._cancelled:
            self._cb(*self._args)


class TimerHandle(Handle):
    """Timer handle returned by call_later."""

    __slots__ = ("_when", "_seq")

    def __init__(self, when, seq, cb, args, loop):
        super().__init__(cb, args, loop)
        self._when = when
        self._seq = seq

    def when(self) -> float:
        return self._when

    def __lt__(self, other):
        return (self._when, self._seq) < (other._when, other._seq)


# ═══════════════════════════════════════════════════════════════
#  Future — awaitable result container
# ═══════════════════════════════════════════════════════════════

class Future:
    """Self-developed Future: a one-shot result container awaitable by coroutines.

    Completion notifications are uniformly scheduled to the owning event-loop
    thread via _schedule_callbacks, so set_result can be triggered from any thread
    (paired with call_soon_threadsafe).
    """

    _PENDING = "pending"
    _CANCELLED = "cancelled"
    _FINISHED = "finished"

    def __init__(self, loop=None):
        self._loop = loop
        self._state = Future._PENDING
        self._result = None
        self._exception = None
        self._callbacks = []
        # for run_in_executor: attempt to cancel the underlying thread task on cancel
        self._cancel_hook = None

    # ── state queries ──

    def done(self) -> bool:
        return self._state != Future._PENDING

    def cancelled(self) -> bool:
        return self._state == Future._CANCELLED

    def get_loop(self):
        return self._loop

    # ── completion setters ──

    def set_result(self, result):
        if self._state != Future._PENDING:
            raise InvalidStateError("invalid state: future already done")
        self._result = result
        self._state = Future._FINISHED
        self._schedule_callbacks()

    def set_exception(self, exception):
        if self._state != Future._PENDING:
            raise InvalidStateError("invalid state: future already done")
        if exception is None:
            raise TypeError("exception must not be None")
        self._exception = exception
        self._state = Future._FINISHED
        self._schedule_callbacks()

    def cancel(self) -> bool:
        """Cancel the Future. Only PENDING can be cancelled."""
        if self._state != Future._PENDING:
            return False
        if self._cancel_hook is not None:
            try:
                self._cancel_hook()
            except Exception:
                pass
        self._state = Future._CANCELLED
        self._schedule_callbacks()
        return True

    # ── result reads ──

    def result(self):
        if self._state == Future._CANCELLED:
            raise CancelledError()
        if self._state == Future._PENDING:
            raise InvalidStateError("result is not ready")
        if self._exception is not None:
            raise self._exception
        return self._result

    def exception(self):
        if self._state == Future._CANCELLED:
            raise CancelledError()
        if self._state == Future._PENDING:
            raise InvalidStateError("exception is not ready")
        return self._exception

    # ── callbacks ──

    def add_done_callback(self, cb):
        """Register a completion callback; when already done, schedule it immediately."""
        if self._state != Future._PENDING:
            self._invoke_callback(cb)
        else:
            self._callbacks.append(cb)

    def remove_done_callback(self, cb) -> int:
        removed = 0
        try:
            while True:
                self._callbacks.remove(cb)
                removed += 1
        except ValueError:
            pass
        return removed

    def _invoke_callback(self, cb):
        loop = self._loop
        if loop is None or loop.is_closed():
            # no loop or the loop is closed: run synchronously (safe fallback when no coroutine waits)
            try:
                cb(self)
            except Exception:
                pass
            return
        # ★ cross-thread completion fix: a Future may be set_result /
        #   set_exception / cancel from any thread (e.g. an external thread's
        #   immediate stop). It must then go through call_soon_threadsafe writing
        #   the self-pipe to wake the loop — with call_soon, the callback would sit
        #   in the _ready queue while the loop is still blocked in
        #   selector.select(), and waiters would never be woken (tasks appearing hung).
        if loop._thread_id is not None and loop._thread_id != threading.get_ident():
            loop.call_soon_threadsafe(cb, self)
        else:
            loop.call_soon(cb, self)

    def _schedule_callbacks(self):
        callbacks, self._callbacks = self._callbacks, []
        for cb in callbacks:
            self._invoke_callback(cb)

    # ── awaitable protocol ──

    def __await__(self):
        if not self.done():
            yield self
        return self.result()

    def __repr__(self):
        return f"<{type(self).__name__} state={self._state}>"


# ═══════════════════════════════════════════════════════════════
#  Task — coroutine driver (trampoline scheduling + cancellation injection)
# ═══════════════════════════════════════════════════════════════

class Task(Future):
    """Self-developed Task: hangs a coroutine on the event loop and advances it step by step.

    Scheduling mechanism (classic trampoline):
      - _step() calls coro.send(None) to advance the coroutine
      - when the coroutine yields a Future, it suspends and registers an
        _on_waiter_done callback
      - once the awaited Future completes, the callback re-queues _step into the
        ready queue to keep advancing
      - cancellation: throw(CancelledError) into the coroutine; the coroutine
        decides whether to honor it (same semantics as asyncio: swallowing the
        cancellation completes the task normally; otherwise it ends with CancelledError)
    """

    def __init__(self, coro, loop=None):
        super().__init__(loop)
        self._coro = coro
        self._fut_waiter = None
        self._must_cancel = False
        self._step_exc = None
        if self._loop is None or self._loop.is_closed():
            raise RuntimeError("Task requires a running event loop")
        self._loop.call_soon(self._step, None)

    # ── advancing the coroutine ──

    def _step(self, exc):
        if self.done():
            return
        self._fut_waiter = None
        loop = self._loop
        loop._current_task = self
        try:
            if exc is None:
                result = self._coro.send(None)
            else:
                result = self._coro.throw(exc)
        except StopIteration as si:
            self.set_result(si.value)
        except CancelledError as ce:
            # the coroutine did not swallow the cancellation: the task ends with CancelledError
            self.set_exception(ce)
            self._close_coro()
        except BaseException as e:
            self.set_exception(e)
            self._close_coro()
        else:
            if result is None:
                # the coroutine awaited something other than an awaitable internally (rare); keep advancing
                loop.call_soon(self._step, None)
            elif isinstance(result, Future):
                if result is self:
                    loop.call_soon(
                        self._step, RuntimeError("Task cannot await on itself"))
                else:
                    self._fut_waiter = result
                    result.add_done_callback(self._on_waiter_done)
            elif hasattr(result, "__next__") or hasattr(result, "send"):
                # generator-based coroutine compatibility: advance its inner yield chain serially
                loop.call_soon(self._step, None)
                self._fut_waiter = _chain_generator(loop, result, self)
            else:
                loop.call_soon(
                    self._step,
                    TypeError(f"coroutine yielded invalid object: {result!r}"))
        finally:
            loop._current_task = None
            if self._must_cancel and not self.done():
                self._must_cancel = False
                loop.call_soon(self._step, CancelledError())

    def _close_coro(self):
        try:
            self._coro.close()
        except Exception:
            pass

    def _on_waiter_done(self, fut):
        if self.done():
            return
        if fut.cancelled():
            self._loop.call_soon(self._step, CancelledError())
        elif fut.exception() is not None:
            self._loop.call_soon(self._step, fut.exception())
        else:
            self._loop.call_soon(self._step, None)

    # ── cancellation ──

    def cancel(self) -> bool:
        """Request task cancellation (thread-safe; callable from any thread).

        Returns False when the task is already done and cannot be cancelled.

        ★ key improvement for immediate stop (v1.1.0):
        the standard asyncio Task.cancel() is not thread-safe (it directly
        manipulates the loop thread's ready queue). This self-developed
        implementation auto-detects the calling thread:
          - called inside the loop thread → call_soon (zero overhead)
          - called from another thread   → call_soon_threadsafe (writes the
            self-pipe to wake the loop immediately)
        So external threads can cancel any task directly, no extra wrapping needed.
        """
        if self.done():
            return False
        self._must_cancel = True
        loop = self._loop
        if loop._thread_id is not None and loop._thread_id == threading.get_ident():
            loop.call_soon(self._throw_cancel)
        else:
            loop.call_soon_threadsafe(self._throw_cancel)
        return True

    def _throw_cancel(self):
        if not self.done() and self._must_cancel:
            self._must_cancel = False
            self._step(CancelledError())

    def cancelled(self) -> bool:
        return (
            self._state == Future._CANCELLED
            or isinstance(self._exception, CancelledError)
        )

    def get_coro(self):
        return self._coro


def _chain_generator(loop, gen, task):
    """Advance the yield chain of a generator-based coroutine serially (legacy-coroutine compatibility; not currently used by business code)."""
    fut = loop.create_future()

    def _advance(exc=None):
        try:
            if exc is None:
                result = gen.send(None)
            else:
                result = gen.throw(exc)
        except StopIteration as si:
            fut.set_result(si.value)
        except CancelledError as ce:
            fut.set_exception(ce)
        except BaseException as e:
            fut.set_exception(e)
        else:
            if isinstance(result, Future):
                result.add_done_callback(_on_sub_done)
            else:
                loop.call_soon(_advance, None)

    def _on_sub_done(sub_fut):
        if sub_fut.cancelled():
            loop.call_soon(_advance, CancelledError())
        elif sub_fut.exception() is not None:
            loop.call_soon(_advance, sub_fut.exception())
        else:
            loop.call_soon(_advance, None)

    loop.call_soon(_advance, None)
    return fut


def ensure_future(coro_or_future):
    """Wrap a coroutine into a Task; Futures/Tasks pass through unchanged."""
    if isinstance(coro_or_future, Future):
        return coro_or_future
    if hasattr(coro_or_future, "send"):
        loop = get_running_loop()
        return Task(coro_or_future, loop=loop)
    raise TypeError(
        f"expect coroutine or Future, got {type(coro_or_future).__name__}")


def run_coroutine_threadsafe(coro, loop) -> concurrent.futures.Future:
    """Thread-safely submit a coroutine to the target loop; returns a concurrent.futures.Future.

    Semantics aligned with asyncio.run_coroutine_threadsafe:
      - the coroutine runs in the target loop thread;
      - the returned Future carries the coroutine's return value; when the
        coroutine is cancelled it gets set_exception(CancelledError); on
        exception, set_exception(exception);
      - when the target loop is closed, set_exception(RuntimeError) immediately.

    Key points of this self-developed implementation (v2.0.0):
      - Task creation goes through call_soon_threadsafe (writes the self-pipe), so
        a loop blocked in select receives and starts advancing the coroutine
        immediately;
      - completion notifications are written by the Task's done callback into a
        concurrent.futures Future inside the loop thread (concurrent.futures is
        itself thread-safe); callers blocking on result() / exception() from any
        thread have no wakeup races.
    """
    cf = concurrent.futures.Future()

    if loop.is_closed():
        if not cf.done():
            cf.set_exception(RuntimeError("event loop is closed"))
        return cf

    def _on_task_done(task):
        if cf.done():
            return
        if task.cancelled():
            cf.set_exception(CancelledError())
            return
        exc = task.exception()
        if exc is not None:
            cf.set_exception(exc)
        else:
            cf.set_result(task.result())

    def _spawn():
        try:
            task = loop.create_task(coro)
        except RuntimeError as e:
            if not cf.done():
                cf.set_exception(e)
            return
        task.add_done_callback(_on_task_done)

    loop.call_soon_threadsafe(_spawn)
    return cf


# ═══════════════════════════════════════════════════════════════
#  synchronization primitives
# ═══════════════════════════════════════════════════════════════

class Event:
    """Self-developed event. set() is thread-safe: can wake waiters inside the loop from any thread.

    Key design (aligned with asyncio semantics and fixing cross-thread wakeup):
      - wait() registers a waiter future inside the loop
      - when set() is called from any thread, it schedules fut.set_result onto the
        loop thread via loop.call_soon_threadsafe; the self-pipe guarantees the
        blocked select wakes immediately
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._flag = False
        self._waiters = []  # [(loop, future)]

    def is_set(self) -> bool:
        return self._flag

    def set(self):
        with self._lock:
            self._flag = True
            waiters, self._waiters = self._waiters, []
        for loop, fut in waiters:
            if loop.is_closed():
                # loop closed: complete synchronously to avoid hanging
                if not fut.done():
                    fut.set_result(True)
            else:
                loop.call_soon_threadsafe(fut.set_result, True)

    def clear(self):
        with self._lock:
            self._flag = False

    async def wait(self) -> bool:
        loop = get_running_loop()
        with self._lock:
            if self._flag:
                return True
            fut = loop.create_future()
            self._waiters.append((loop, fut))
        try:
            await fut
        except CancelledError:
            # wait cancelled (wait_for timeout case): remove from the waiter list to avoid residue
            with self._lock:
                for item in self._waiters:
                    if item[1] is fut:
                        self._waiters.remove(item)
                        break
            raise
        return True


class Lock:
    """Self-developed async mutex (loop-thread-only; async with semantics)."""

    def __init__(self):
        self._locked = False
        self._waiters = deque()  # futures

    def locked(self) -> bool:
        return self._locked

    async def acquire(self) -> bool:
        if not self._locked and not self._waiters:
            self._locked = True
            return True
        loop = get_running_loop()
        fut = loop.create_future()
        self._waiters.append(fut)
        try:
            await fut
            self._locked = True
            return True
        except CancelledError:
            # cancelled while waiting: remove from the queue so the lock is not
            # handed to a cancelled waiter
            try:
                self._waiters.remove(fut)
            except ValueError:
                pass
            raise

    def release(self):
        # hand the lock directly to the head waiter (the lock always stays held;
        # only the holder changes)
        while self._waiters:
            fut = self._waiters.popleft()
            if not fut.done():
                fut.set_result(True)
                return
        self._locked = False

    async def __aenter__(self):
        await self.acquire()
        return self

    async def __aexit__(self, *exc_info):
        self.release()


class Condition:
    """Self-developed async condition variable (built on Lock)."""

    def __init__(self, lock=None):
        self._lock = lock if lock is not None else Lock()
        self._waiters = deque()

    @property
    def lock(self) -> Lock:
        return self._lock

    async def acquire(self):
        await self._lock.acquire()

    def release(self):
        self._lock.release()

    async def wait(self):
        if not self._lock.locked():
            raise RuntimeError("cannot wait on un-acquired lock")
        loop = get_running_loop()
        fut = loop.create_future()
        self._waiters.append(fut)
        self._lock.release()
        try:
            await fut
        except CancelledError:
            try:
                self._waiters.remove(fut)
            except ValueError:
                pass
            raise
        finally:
            await self._lock.acquire()

    def notify(self, n: int = 1):
        notified = 0
        while self._waiters and notified < n:
            fut = self._waiters.popleft()
            if not fut.done():
                fut.set_result(True)
                notified += 1

    def notify_all(self):
        waiters, self._waiters = self._waiters, deque()
        for fut in waiters:
            if not fut.done():
                fut.set_result(True)

    async def __aenter__(self):
        await self._lock.acquire()
        return self

    async def __aexit__(self, *exc_info):
        self._lock.release()


# ═══════════════════════════════════════════════════════════════
#  utility coroutines
# ═══════════════════════════════════════════════════════════════

async def _yield_control():
    """Yield control once (sleep(0) semantics)."""
    loop = get_running_loop()
    fut = loop.create_future()
    loop.call_soon(fut.set_result, None)
    await fut


async def sleep(seconds: float):
    """Sleep asynchronously for seconds. seconds <= 0 only yields control."""
    if seconds is None:
        raise TypeError("sleep() seconds must be a number")
    if seconds <= 0:
        await _yield_control()
        return
    loop = get_running_loop()
    fut = loop.create_future()

    def _wake():
        if not fut.done():
            fut.set_result(None)

    handle = loop.call_later(seconds, _wake)
    try:
        await fut
    finally:
        handle.cancel()


async def wait_for(awaitable, timeout):
    """Wait for an awaitable to finish; on timeout raise TimeoutError and cancel the inner task.

    Semantics aligned with asyncio.wait_for:
      - on timeout, cancel the inner Task (throw CancelledError; the coroutine handles it)
      - when the inner object is a Future, cancel() directly
      - returns the inner task's final result
    """
    if timeout is None:
        return await awaitable

    loop = get_running_loop()

    if isinstance(awaitable, Future):
        inner = awaitable
    else:
        inner = loop.create_task(awaitable)

    bridge = loop.create_future()

    def _on_inner_done(f):
        if bridge.done():
            return
        if f.cancelled():
            bridge.set_exception(CancelledError())
        elif f.exception() is not None:
            bridge.set_exception(f.exception())
        else:
            bridge.set_result(f.result())

    def _on_timeout():
        if bridge.done():
            return
        inner.cancel()
        bridge.set_exception(TimeoutError())

    inner.add_done_callback(_on_inner_done)
    timer = loop.call_later(timeout, _on_timeout)
    try:
        return await bridge
    except CancelledError:
        # outer cancellation: propagate to the inner task
        inner.cancel()
        raise
    finally:
        timer.cancel()


# ═══════════════════════════════════════════════════════════════
#  event loop — the self-developed core
# ═══════════════════════════════════════════════════════════════

# select() timeout ceiling: Windows select() overflows beyond ~2^31-1 ms
# (≈24.8 days of time_t). An absurdly-far timer (sleep(1e18), a far call_later)
# must not crash the loop — the loop simply re-checks the timer heap after each
# capped wait. 24h matches CPython asyncio's MAXIMUM_SELECT_TIMEOUT.
_MAX_SELECT_TIMEOUT = 24 * 3600.0


class EventLoop:
    """Self-developed single-threaded event loop.

    Core structures:
      - _ready: deque of callbacks ready to run (call_soon / due timers / Task advancement)
      - _scheduled: time heap [(when, seq, TimerHandle)] (call_later / sleep)
      - _ts_queue: thread-safe submission queue (call_soon_threadsafe)
      - self-pipe (socketpair): cross-thread wakeup of the loop blocked in selector.select
      - _selector: selectors.DefaultSelector (only listens for self-pipe readability)
    """

    def __init__(self):
        self._ready = deque()
        self._scheduled = []
        self._seq = itertools.count()
        self._selector = selectors.DefaultSelector()
        self._ssock, self._csock = socket.socketpair()
        self._ssock.setblocking(False)
        self._csock.setblocking(False)
        self._selector.register(self._ssock, selectors.EVENT_READ)
        self._ts_queue = _queue.Queue()
        self._running = False
        self._stopping = False
        self._closed = False
        self._thread_id = None
        self._current_task = None
        # the current main task of run_until_complete (abort_main's cancellation target)
        self._main_task = None

    # ── state ──

    def time(self) -> float:
        """Loop monotonic clock (seconds)."""
        return _time.monotonic()

    def is_running(self) -> bool:
        return self._running

    def is_closed(self) -> bool:
        return self._closed

    def close(self):
        """Close the loop (releases the selector and the self-pipe). A running loop cannot be closed."""
        if self._running:
            raise RuntimeError("cannot close a running event loop")
        if self._closed:
            return
        self._closed = True
        try:
            self._selector.unregister(self._ssock)
        except Exception:
            pass
        try:
            self._selector.close()
        except Exception:
            pass
        try:
            self._ssock.close()
        except Exception:
            pass
        try:
            self._csock.close()
        except Exception:
            pass

    # ── scheduling ──

    def call_soon(self, cb, *args) -> Handle:
        """Queue a callback into the ready queue (call only in the loop thread)."""
        handle = Handle(cb, args, self)
        self._ready.append(handle)
        return handle

    def call_later(self, delay: float, cb, *args) -> TimerHandle:
        """Run a callback after delay seconds (returns a cancellable TimerHandle)."""
        when = self.time() + max(0.0, delay)
        handle = TimerHandle(when, next(self._seq), cb, args, self)
        heapq.heappush(self._scheduled, (when, handle._seq, handle))
        return handle

    def call_soon_threadsafe(self, cb, *args) -> Handle:
        """Thread-safe scheduling: callable from any thread; wakes the loop thread immediately."""
        handle = Handle(cb, args, self)
        if self._closed:
            handle.cancel()
            return handle
        self._ts_queue.put(handle)
        self._wake()
        return handle

    def _wake(self):
        """Write one byte to the self-pipe to wake the loop thread blocked in select."""
        try:
            self._csock.send(b"\0")
        except OSError:
            pass  # pipe full (a wakeup signal is already in flight) or the loop is closed

    # ── Future / Task ──

    def create_future(self) -> Future:
        return Future(loop=self)

    def create_task(self, coro) -> Task:
        return Task(coro, loop=self)

    # ── executor execution ──

    def run_in_executor(self, executor, fn, *args) -> Future:
        """Run a synchronous function in an executor; returns an awaitable Future.

        When executor is None, a global shared ThreadPoolExecutor is used.
        Cancelling the returned Future best-effort cancels the underlying thread task.

        Note: norpagent's default loop runtime (norpagent.loops.nasyncio) does not
        use this method for submit tasks — task bodies may block on sandbox
        subprocess / HTTP I/O, and ThreadPoolExecutor worker threads are
        force-joined at interpreter exit (a stuck task freezes the process). The
        default runtime executes submits with a bare daemon-thread worker pool (see
        its module docstring). This method is for loop-internal coroutines running
        synchronous functions of controllable duration.
        """
        fut = Future(loop=self)
        if executor is None:
            executor = _get_default_executor()
        try:
            cf = executor.submit(fn, *args)
        except Exception as e:
            fut.set_exception(e)
            return fut

        def _on_done(cfut):
            # runs in the executor thread: results must be scheduled back to the loop thread
            if fut.cancelled():
                return
            try:
                result = cfut.result()
                self.call_soon_threadsafe(fut.set_result, result)
            except BaseException as e:
                self.call_soon_threadsafe(fut.set_exception, e)

        cf.add_done_callback(_on_done)

        def _cancel():
            return cf.cancel()

        fut._cancel_hook = _cancel
        return fut

    # ── main loop ──

    def run_forever(self):
        """Run the loop until stop(). Binds the current thread as the loop thread."""
        if self._running:
            raise RuntimeError("event loop already running")
        if self._closed:
            raise RuntimeError("event loop is closed")
        self._thread_id = threading.get_ident()
        _register_running_loop(self)
        self._running = True
        try:
            while True:
                self._run_once()
                if self._stopping and not self._ready:
                    break
        finally:
            self._running = False
            self._stopping = False
            self._current_task = None
            _unregister_running_loop(self)

    def run_until_complete(self, coro):
        """Run the loop until the coroutine completes; returns its result (raises on exception).

        ★ immediate-stop support (v1.1.0):
        the main task is registered to self._main_task; external threads can call
        abort_main() at any time to inject CancelledError and force an interrupt
        (no need to wait for the current await to finish).
        """
        task = self.create_task(coro)
        self._main_task = task
        task.add_done_callback(lambda t: self.stop())
        try:
            self.run_forever()
            return task.result()
        finally:
            if self._main_task is task:
                self._main_task = None

    def stop(self):
        """Request the loop to stop (exits after the current round's ready queue empties).

        Note: stop() is "graceful"; it does not cancel running tasks — if the main
        task is awaiting a long-unfinished Future, the loop thread still waits. For
        "immediate stop", use abort_main() (it cancels the main task first; once
        the task completes, its done callback triggers this stop() and the loop exits).
        """
        self._stopping = True
        self._wake()

    def abort_main(self) -> bool:
        """Thread-safe: immediately cancel the main task of run_until_complete (immediate stop).

        ★ a core capability of the self-developed architecture (v1.1.0):
        the standard asyncio has no public "cancel the main task" entry — external
        threads can only set a flag and wait for business code to check it; a
        coroutine stuck in await cannot be force-interrupted, and stop latency
        depends on the current operation (tool/API calls may take minutes).

        This method injects CancelledError into the main coroutine (via
        call_soon_threadsafe + self-pipe wakeup), immediately interrupting its
        current await (tool execution / API stream / user-input wait), and the
        coroutine stack unwinds layer by layer:
          - wait_for propagates the cancellation and cancels the inner Future
          - a cancelled subprocess communicate() auto-kills the process
          - business coroutines that catch CancelledError return "stopped" as closure

        After the main task completes, its done callback triggers stop() and the
        loop exits. Returns whether cancellation was actually initiated (False =
        no main task or already done).
        """
        task = self._main_task
        if task is None or task.done():
            return False
        return task.cancel()

    def _run_once(self):
        # 1. due timers → ready
        self._drain_scheduled()

        # 2. compute the select wait duration
        if self._ready:
            wait = 0.0
        elif self._scheduled:
            wait = max(0.0, self._scheduled[0][0] - self.time())
        else:
            wait = None
        # clamp to the platform-safe ceiling (see _MAX_SELECT_TIMEOUT): a far
        # timer must never overflow select(); after each capped wait the loop
        # re-checks the heap and keeps waiting.
        if wait is not None:
            wait = min(wait, _MAX_SELECT_TIMEOUT)

        # 3. drain the thread-safe queue once first (fewer pointless select wakeups)
        self._drain_threadsafe()

        # 4. block and wait (self-pipe readable or timer due)
        try:
            events = self._selector.select(wait)
        except (InterruptedError, OSError):
            events = []
        for _key, _mask in events:
            self._drain_wake_pipe()

        self._drain_threadsafe()

        # 5. run the ready queue (snapshot the length to prevent starvation)
        nready = len(self._ready)
        for _ in range(nready):
            handle = self._ready.popleft()
            if not handle.cancelled():
                try:
                    handle._run()
                except Exception:
                    # callback exceptions must not break the event loop: log and continue
                    _traceback.print_exc()

    def _drain_scheduled(self):
        now = self.time()
        while self._scheduled and self._scheduled[0][0] <= now:
            _when, _seq, handle = heapq.heappop(self._scheduled)
            if not handle.cancelled():
                self._ready.append(handle)
            now = self.time()

    def _drain_threadsafe(self):
        while True:
            try:
                handle = self._ts_queue.get_nowait()
            except _queue.Empty:
                break
            if not handle.cancelled():
                self._ready.append(handle)

    def _drain_wake_pipe(self):
        while True:
            try:
                data = self._ssock.recv(4096)
                if not data:
                    break
            except (BlockingIOError, InterruptedError):
                break
            except OSError:
                break


AbstractEventLoop = EventLoop


# ═══════════════════════════════════════════════════════════════
#  loop management (global state)
# ═══════════════════════════════════════════════════════════════

_running_loops = {}          # thread_id -> EventLoop
_running_loops_lock = threading.Lock()
_global_loop = None
_global_loop_lock = threading.Lock()


def _register_running_loop(loop):
    with _running_loops_lock:
        _running_loops[threading.get_ident()] = loop


def _unregister_running_loop(loop):
    with _running_loops_lock:
        tid = threading.get_ident()
        if _running_loops.get(tid) is loop:
            _running_loops.pop(tid, None)


def new_event_loop() -> EventLoop:
    """Create a new event loop."""
    return EventLoop()


def set_event_loop(loop):
    """Set the current thread's event loop (compat interface; loop binding is done by run_forever)."""
    global _global_loop
    with _global_loop_lock:
        _global_loop = loop


def get_event_loop() -> EventLoop:
    """Return the loop set by set_event_loop (compat interface)."""
    with _global_loop_lock:
        return _global_loop


def get_running_loop() -> EventLoop:
    """Return the event loop currently running on this thread (RuntimeError when none)."""
    with _running_loops_lock:
        loop = _running_loops.get(threading.get_ident())
    if loop is None:
        raise RuntimeError("no running event loop")
    return loop


# ═══════════════════════════════════════════════════════════════
#  shared thread pool (default executor of run_in_executor)
# ═══════════════════════════════════════════════════════════════

_default_executor = None
_default_executor_lock = threading.Lock()


def _get_default_executor() -> concurrent.futures.ThreadPoolExecutor:
    global _default_executor
    with _default_executor_lock:
        if _default_executor is None:
            _default_executor = concurrent.futures.ThreadPoolExecutor(
                max_workers=16,
                thread_name_prefix="nasync-io",
            )
        return _default_executor


# ═══════════════════════════════════════════════════════════════
#  subprocess support (self-developed: Popen + reader-pipe threads; kill on cancelled communicate)
# ═══════════════════════════════════════════════════════════════

class _SubprocessConst:
    """Compat namespace of the asyncio.subprocess constants."""
    DEVNULL = _subprocess.DEVNULL
    PIPE = _subprocess.PIPE
    STDOUT = _subprocess.STDOUT


subprocess = _SubprocessConst()


class Process:
    """Self-developed subprocess wrapper.

    Key differences from asyncio.subprocess.Process (simpler, more robust):
      - pipe reads use dedicated daemon threads (read to EOF), not occupying the event loop
      - communicate() is a coroutine: joins the reader threads + waits the process in the executor
      - a cancelled communicate() (wait_for timeout) auto-kills the process; no zombies
    """

    def __init__(self, popen):
        self._popen = popen
        self.returncode = None
        self._stdout_thread = None
        self._stderr_thread = None
        self._stdout_data = None
        self._stderr_data = None
        if popen.stdout is not None:
            self._stdout_thread = self._spawn_reader(
                popen.stdout, "_stdout_data")
        if popen.stderr is not None:
            self._stderr_thread = self._spawn_reader(
                popen.stderr, "_stderr_data")

    def _spawn_reader(self, pipe, attr):
        def _read():
            try:
                data = pipe.read()
            except Exception:
                data = b""
            finally:
                try:
                    pipe.close()
                except Exception:
                    pass
            setattr(self, attr, data)

        t = threading.Thread(
            target=_read, daemon=True,
            name=f"nasync-io-proc-{self._popen.pid}")
        t.start()
        return t

    @property
    def pid(self) -> int:
        return self._popen.pid

    def poll(self):
        rc = self._popen.poll()
        if rc is not None:
            self.returncode = rc
        return rc

    def wait(self, timeout=None) -> int:
        """Wait for the process synchronously (returns returncode)."""
        rc = self._popen.wait(timeout=timeout)
        self.returncode = rc
        return rc

    def terminate(self):
        try:
            self._popen.terminate()
        except (ProcessLookupError, OSError):
            pass

    def kill(self):
        try:
            self._popen.kill()
        except (ProcessLookupError, OSError):
            pass

    def send_signal(self, sig):
        try:
            self._popen.send_signal(sig)
        except (ProcessLookupError, OSError):
            pass

    async def communicate(self, input=None):
        """Wait for the process to finish and collect its output.

        Returns (stdout_bytes, stderr_bytes). When a pipe is None, the
        corresponding value is None.

        Cancellation semantics (wait_for timeout / external cancellation):
          re-raise CancelledError after killing the process, ensuring no zombies.
        """
        loop = get_running_loop()

        if input is not None and self._popen.stdin is not None:
            try:
                self._popen.stdin.write(input)
                self._popen.stdin.close()
            except Exception:
                pass

        def _drain():
            if self._stdout_thread is not None:
                self._stdout_thread.join()
            if self._stderr_thread is not None:
                self._stderr_thread.join()
            rc = self._popen.wait()
            self.returncode = rc
            return (self._stdout_data, self._stderr_data)

        try:
            return await loop.run_in_executor(None, _drain)
        except CancelledError:
            # zombie-process protection: kill on cancellation so reader threads EOF quickly
            self.kill()
            raise

    def __repr__(self):
        return f"<Process pid={self.pid} returncode={self.returncode}>"


def _popen_kwargs(stdin, stdout, stderr, cwd, env, creationflags,
                  start_new_session, extra):
    kwargs = dict(extra)
    kwargs["stdin"] = stdin
    kwargs["stdout"] = stdout
    kwargs["stderr"] = stderr
    if cwd is not None:
        kwargs["cwd"] = cwd
    if env is not None:
        kwargs["env"] = env
    if creationflags:
        kwargs["creationflags"] = creationflags
    if start_new_session is not None:
        # Windows Popen does not support start_new_session; ignore it
        if os.name != "nt":
            kwargs["start_new_session"] = start_new_session
    return kwargs


async def create_subprocess_shell(cmd, stdin=None, stdout=None, stderr=None,
                                  cwd=None, env=None, creationflags=0,
                                  start_new_session=None, **kwargs) -> Process:
    """Launch a child process through the shell (self-developed; parameters aligned with the asyncio version)."""
    popen_kw = _popen_kwargs(stdin, stdout, stderr, cwd, env,
                             creationflags, start_new_session, kwargs)
    popen = _subprocess.Popen(cmd, shell=True, **popen_kw)
    return Process(popen)


async def create_subprocess_exec(program, *args, stdin=None, stdout=None,
                                 stderr=None, cwd=None, env=None,
                                 creationflags=0, start_new_session=None,
                                 **kwargs) -> Process:
    """Launch a child process directly (no shell; prevents command injection)."""
    popen_kw = _popen_kwargs(stdin, stdout, stderr, cwd, env,
                             creationflags, start_new_session, kwargs)
    popen = _subprocess.Popen([program, *args], shell=False, **popen_kw)
    return Process(popen)


# ═══════════════════════════════════════════════════════════════
#  callable core module: makes the "nasyncio packaged into the library" name semantics self-consistent
# ═══════════════════════════════════════════════════════════════

class _CallableCoreModule(type(sys)):
    """Make this core module callable.

    The top-level ``norpagent.nasyncio`` (``np.nasyncio``) binds to this module.
    Calling the module directly is equivalent to calling the architecture function
    ``norpagent.nasyncio()`` (returns the default LoopRuntime implementation), so
    all three usages hold:

        import norpagent.nasyncio as core   # get this module
        core.EventLoop                      # the self-developed event loop class
        core(...)                           # == np.nasyncio(...), returns a LoopRuntime
    """

    def __call__(self, address=None, **config):
        from norpagent.loops import nasyncio as _arch_fn

        return _arch_fn(address, **config)


sys.modules[__name__].__class__ = _CallableCoreModule
