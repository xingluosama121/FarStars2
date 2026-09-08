# Copyright (c) 2026 xingluosama121, MIT Licensed
"""Self-developed nasyncio loop adapter: the default implementation of the async_loop slot.

A dedicated thread runs a self-developed nasyncio event loop
(norpagent.nasyncio.EventLoop, fully self-developed, zero asyncio dependencies);
submit() hands synchronous functions to the **own daemon worker pool** and blocks
waiting for the result. Fully transparent to the upper layer — to replace it with
any event loop system, just implement the LoopRuntime protocol and fill in the
async_loop slot address.

This module does not import the standard asyncio. The scheduling core (event loop /
Future / Task / coroutine trampoline / self-pipe wakeup) all come from the
library's built-in self-developed ``norpagent.nasyncio`` core (originally
nasync_io, now packaged into the library).

Why the default core replaced the standard asyncio (embracing the self-developed nasyncio):

- **control**: cancellation / stop / cross-thread wakeup semantics are all defined
  by in-library code. The standard asyncio's Task.cancel() is not thread-safe; its
  cross-thread add_done_callback goes through call_soon without writing the
  self-pipe (a loop blocked on the selector never gets the wakeup); the
  self-developed core fixes all of these pitfalls (Task.cancel thread-safe,
  cross-thread Future completion notifications automatically go through the
  self-pipe, abort_main() stops immediately);
- **dependency surface**: the self-developed core only depends on non-asyncio
  standard modules such as threading / selectors / socket / heapq — the full
  audit surface is the library's own code;
- **exit semantics**: does not use asyncio's default ThreadPoolExecutor (its
  worker threads are registered in CPython's threading._threads_queues and force-joined
  at interpreter exit — a stuck task would freeze the process).

Cancellation semantics (the key design for Ctrl+C usability):

- submit() waits by polling a threading.Event (every ≤poll_interval seconds,
  default 0.05s, tunable via config / NORPAGENT_SUBMIT_POLL) to return to a
  bytecode boundary: on Windows the main thread's pending interrupt is only
  checked at bytecode boundaries once WaitForSingleObject swallows it, and a
  single blocking Event.wait() would make Ctrl+C dead — polling wait solves this
  completely; the main thread's Ctrl+C **immediately** surfaces as
  KeyboardInterrupt;
- every task is wrapped in a contextvars context carrying a cancel event
  (norpagent.loops.cancel). On KeyboardInterrupt that cancel event is set:
  sandboxes force-kill child processes immediately, model streaming loops
  interrupt, tools exit early — worker threads no longer wait stupidly for timeouts;
- interrupt() cancels all in-flight tasks (called by engine request_stop);
- worker threads are bare daemon threads + queue (reason in "exit semantics" above).
"""
from __future__ import annotations

import contextvars
import os
import queue
import threading
import time
from typing import Any, Dict, Optional

from norpagent.loops.cancel import _current_cancel
from norpagent.nasyncio import EventLoop, run_coroutine_threadsafe


def _default_workers() -> int:
    try:
        return max(4, os.cpu_count() or 4)
    except Exception:  # noqa: BLE001 — fallback when os.cpu_count is unavailable
        return 4


def _env_int(name: str, floor: int = 1, ceiling: int = 4096) -> Optional[int]:
    """Read an integer environment variable (None on invalid values). Used for resource-tuning switches."""
    raw = os.environ.get(name)
    if raw is None:
        return None
    try:
        return max(floor, min(int(raw), ceiling))
    except (TypeError, ValueError):
        return None


def _resolve_workers(cfg: dict) -> int:
    """Worker-pool thread count resolution: config.max_workers > env var
    NORPAGENT_MAX_WORKERS > default max(4, cpu_count).

    Embedded scenarios: NORPAGENT_MAX_WORKERS=1 (or an explicit config 1) squeezes
    worker threads to the minimum; high-concurrency servers can increase explicitly
    (default cap 4096).
    """
    return int(
        cfg.get("max_workers")
        or _env_int("NORPAGENT_MAX_WORKERS")
        or _default_workers()
    )


def _resolve_poll(cfg: dict) -> float:
    """submit/run_async completion-poll interval resolution: config.poll_interval >
    env var NORPAGENT_SUBMIT_POLL > default 0.05s.

    This interval only affects the perceived completion latency of the calling
    thread blocking on the task; it adds no event-loop overhead. Default 0.05s:
    under high concurrency, task-completion perception latency caps at 50ms; in
    CPU-sensitive embedded scenarios it can be raised to 0.5s to save power.
    """
    raw = cfg.get("poll_interval")
    if raw is None:
        raw = os.environ.get("NORPAGENT_SUBMIT_POLL")
    if raw is None:
        return 0.05
    try:
        return max(0.001, min(float(raw), 5.0))
    except (TypeError, ValueError):
        return 0.05


class _DaemonPool:
    """Daemon worker pool: executor of submitted tasks (bare threads + queue, zero exit burden).

    - worker threads are bare threading.Thread(daemon=True), not registered in any
      "must join at interpreter exit" registry — the process can exit immediately
      even when a task is stuck in blocking I/O (ThreadPoolExecutor cannot; see the
      module docstring);
    - lazy start: workers are created on demand; after stop, start again to reuse;
    - shutdown(): posts sentinels letting workers exit naturally; does not wait for
      stuck tasks (daemon threads die with the process; no reaping needed).
    """

    def __init__(self, max_workers: int) -> None:
        self._max_workers = max(1, int(max_workers))
        # the queue is reused for the whole lifetime (never replaced): replacing it
        # would leave old workers stuck on the old queue
        self._queue: "queue.Queue[Any]" = queue.Queue()
        self._threads: list = []
        self._spawn_lock = threading.Lock()
        self._stopped = False

    def submit_nowait(self, fn: Any) -> None:
        """Post a task (non-blocking)."""
        self._ensure_workers()
        self._queue.put_nowait(fn)

    def _ensure_workers(self) -> None:
        with self._spawn_lock:
            self._threads = [t for t in self._threads if t.is_alive()]
            self._stopped = False
            missing = self._max_workers - len(self._threads)
            for i in range(missing):
                t = threading.Thread(
                    target=self._worker,
                    name=f"norpagent-loop-pool-{len(self._threads) + i}",
                    daemon=True,
                )
                self._threads.append(t)
                t.start()

    def _worker(self) -> None:
        while True:
            fn = self._queue.get()
            if fn is _SENTINEL:
                return
            try:
                fn()
            except BaseException:  # noqa: BLE001 — fallback: should not happen (the submit wrapper already catches)
                pass

    def shutdown(self) -> None:
        """Notify workers to exit (does not wait for stuck tasks)."""
        with self._spawn_lock:
            if self._stopped:
                return
            self._stopped = True
            # one sentinel per alive worker (extra sentinels are consumed at the
            # next reuse with no side effects: a worker exits on receipt, and the
            # next start tops up the thread count)
            for _ in self._threads:
                try:
                    self._queue.put_nowait(_SENTINEL)
                except Exception:  # noqa: BLE001
                    pass
            for t in self._threads:
                if t.is_alive():
                    t.join(0.2)
            # dead-thread references are filtered by _ensure_workers; clearing here reclaims references
            self._threads = [t for t in self._threads if t.is_alive()]


class _Sentinel:
    pass


_SENTINEL = _Sentinel()


class NasyncTaskHandle:
    """Cancellable handle returned by NasyncioLoopRuntime.submit_async.

    Surface: cancel() / cancelled() / done() / wait(timeout) / result(timeout).

    - cancel() sets this task's cancel event (idempotent; returns False once the
      task has finished). Task bodies read ``norpagent.loops.cancel.cancel_requested()``
      and exit as soon as possible (sandbox force-kill of child processes / model
      stream interrupt) instead of waiting for timeouts;
    - the same cancel event is a member of the loop's in-flight set, so
      ``interrupt()`` (Ctrl+C / engine request_stop) also cancels tasks submitted
      through submit_async;
    - result(timeout) blocks with Ctrl+C-safe polling (same rationale as submit)
      and re-raises the task's exception when it failed.
    """

    __slots__ = ("_box", "_done", "_cancel", "_poll")

    def __init__(self, box: Dict[str, Any], done: "threading.Event",
                 cancel: "threading.Event", poll: float) -> None:
        self._box = box
        self._done = done
        self._cancel = cancel
        self._poll = poll

    def cancel(self) -> bool:
        """Request cancellation of exactly this task; False when it already finished."""
        if self._done.is_set():
            return False
        self._cancel.set()
        return True

    def cancelled(self) -> bool:
        return self._cancel.is_set()

    def done(self) -> bool:
        return self._done.is_set()

    def wait(self, timeout: Optional[float] = None) -> bool:
        """Block until done (True) or the timeout elapses (False); Ctrl+C-safe polling."""
        deadline = None if timeout is None else time.monotonic() + timeout
        while not self._done.is_set():
            if deadline is not None and time.monotonic() >= deadline:
                return False
            self._done.wait(self._poll)
        return True

    def result(self, timeout: Optional[float] = None) -> Any:
        """Wait for completion (Ctrl+C-safe) and return the task's value; re-raises its exception."""
        if not self.wait(timeout):
            raise TimeoutError("task not finished within the timeout")
        if "exc" in self._box:
            raise self._box["exc"]
        return self._box.get("ok")


class NasyncioLoopRuntime:
    """LoopRuntime implementation based on the library's built-in self-developed nasyncio core (default loop).

    Thread model:
      - ``norpagent-nasync-loop``: runs the self-developed EventLoop (run_forever),
        hosting coroutines submitted via run_async;
      - ``norpagent-loop-pool-*``: daemon worker pool executing synchronous submit
        tasks (task bodies may block on sandbox/HTTP I/O; they never enter the loop thread).
    """

    name = "nasyncio"

    def __init__(self, **kwargs: Any) -> None:
        # config may carry loop-specific settings (injected by the architecture
        # layer factory); supported:
        #   max_workers  worker-pool thread count (default max(4, cpu_count);
        #                overridable via the NORPAGENT_MAX_WORKERS env var)
        #   poll_interval submit completion-poll interval in seconds (default 0.05;
        #                overridable via the NORPAGENT_SUBMIT_POLL env var)
        cfg = kwargs.get("config") or {}
        self.max_workers = _resolve_workers(cfg)
        self._poll = _resolve_poll(cfg)
        self._loop: Optional[EventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self._closed = threading.Event()
        self._pool = _DaemonPool(self.max_workers)
        self._active_cancels: set = set()  # cancel-event set of in-flight tasks

    # ── LoopRuntime protocol ──────────────────────────────

    def start(self) -> None:
        with self._lock:
            if self._thread is not None:
                return  # already started
            self._loop = EventLoop()
            self._closed.clear()
            self._thread = threading.Thread(
                target=self._loop.run_forever,
                name="norpagent-nasync-loop",
                daemon=True,
            )
            self._thread.start()

    def stop(self) -> None:
        loop = self._loop
        if loop is not None and loop.is_running():
            loop.call_soon_threadsafe(loop.stop)
        self.interrupt()
        self._closed.set()

    def interrupt(self) -> None:
        """Request cancellation of all in-flight submit tasks (Ctrl+C / engine-stop path).

        Sets the cancel event of every in-flight task: sandboxes force-kill child
        processes, model streaming loops interrupt, task bodies exit early; this
        method does not wait for tasks to actually finish.
        """
        with self._lock:
            cancels = list(self._active_cancels)
        for event in cancels:
            try:
                event.set()
            except Exception:  # noqa: BLE001
                pass

    def is_running(self) -> bool:
        loop = self._loop
        return bool(
            loop is not None
            and loop.is_running()
            and self._thread is not None
            and self._thread.is_alive()
            and not self._closed.is_set()
        )

    def join(self, timeout: Optional[float] = None) -> None:
        thread = self._thread
        if thread is not None:
            thread.join(timeout)
            if not thread.is_alive():
                # after the loop thread exits, close loop resources
                loop = self._loop
                if loop is not None and not loop.is_closed():
                    loop.close()
                self._pool.shutdown()
                with self._lock:
                    self._thread = None
                    self._loop = None

    def submit(self, fn: Any, *args: Any, **kwargs: Any) -> Any:
        loop = self._loop
        if loop is None:
            raise RuntimeError("loop has not been start()ed")
        # already inside the loop thread: execute synchronously (avoid deadlock waiting)
        if threading.current_thread() is self._thread:
            return fn(*args, **kwargs)
        if not self.is_running():
            raise RuntimeError("loop has stopped")
        # task bodies get their own cancel event via contextvars (see the module
        # docstring); results are written by the worker thread directly into a local
        # box which sets an event — not depending on the event loop Future's
        # done-callback scheduling order (although the self-developed core already
        # fixes cross-thread completion notification via the self-pipe, submit tasks
        # may block for a long time; running them in the daemon worker pool fully
        # decouples them from the loop).
        box: dict = {}
        done = threading.Event()
        job_cancel = threading.Event()
        ctx = contextvars.copy_context()

        def _bind_cancel() -> None:
            _current_cancel.set(job_cancel)

        ctx.run(_bind_cancel)
        with self._lock:
            self._active_cancels.add(job_cancel)

        def _runner() -> None:
            try:
                box["ok"] = ctx.run(fn, *args, **kwargs)
            except BaseException as exc:  # noqa: BLE001 — exceptions relay back to the caller
                box["exc"] = exc
            finally:
                done.set()
                with self._lock:
                    self._active_cancels.discard(job_cancel)

        self._pool.submit_nowait(_runner)
        try:
            # polling wait instead of a single blocking wait: on Windows, once
            # WaitForSingleObject swallows the main thread's SIGINT, the pending
            # interrupt is only checked at bytecode boundaries, and an unbounded
            # Event.wait() never returns to a bytecode boundary (Ctrl+C dead).
            # Polling makes the main thread pass a bytecode boundary every
            # ≤poll_interval seconds, so a console Ctrl+C surfaces immediately as
            # KeyboardInterrupt. The interval defaults to 0.05s
            # (config.poll_interval / NORPAGENT_SUBMIT_POLL tunable): small
            # task-completion perception latency under high concurrency;
            # CPU-sensitive embedded scenarios can raise it.
            while not done.is_set():
                done.wait(self._poll)
        except KeyboardInterrupt:
            # Ctrl+C: the caller is interrupted immediately; set the cancel event
            # so the task body exits as soon as possible (sandbox force-kill of
            # child processes / model stream interrupt), not waiting for timeouts.
            job_cancel.set()
            raise
        if "exc" in box:
            raise box["exc"]
        return box["ok"]

    def submit_async(self, fn: Any, *args: Any, **kwargs: Any) -> NasyncTaskHandle:
        """Submit fn in the loop context and return immediately with a cancellable handle.

        Optional LoopRuntime extension (the engine probes with hasattr): the
        engine-level NorpEngine.submit_async builds on it for task-level
        cancellation. The task body sees the same per-task cancel event
        (norpagent.loops.cancel.cancel_requested); handle.cancel() cancels exactly
        this task. Tasks submitted this way are members of the in-flight set, so
        interrupt() (Ctrl+C / engine stop) still cancels them.
        """
        loop = self._loop
        if loop is None:
            raise RuntimeError("loop has not been start()ed")
        if threading.current_thread() is self._thread:
            # blocking inside the loop thread would stall the loop; the loop
            # thread itself must use submit() (or await directly)
            raise RuntimeError(
                "submit_async cannot be called inside the loop thread; use submit() instead"
            )
        if not self.is_running():
            raise RuntimeError("loop has stopped")
        box: dict = {}
        done = threading.Event()
        job_cancel = threading.Event()
        ctx = contextvars.copy_context()

        def _bind_cancel() -> None:
            _current_cancel.set(job_cancel)

        ctx.run(_bind_cancel)
        with self._lock:
            self._active_cancels.add(job_cancel)

        def _runner() -> None:
            try:
                box["ok"] = ctx.run(fn, *args, **kwargs)
            except BaseException as exc:  # noqa: BLE001 — relayed to handle.result()
                box["exc"] = exc
            finally:
                done.set()
                with self._lock:
                    self._active_cancels.discard(job_cancel)

        self._pool.submit_nowait(_runner)
        return NasyncTaskHandle(box, done, job_cancel, self._poll)

    # ── extra capabilities ───────────────────────────────

    def run_async(self, coro: Any) -> Any:
        """Run a coroutine inside the loop and block returning its result (optional capability).

        For custom entry points written as coroutines; the engine defaults to
        submit(). Cross-thread submission goes through the self-developed core's
        run_coroutine_threadsafe (internally call_soon_threadsafe + self-pipe
        wakeup; a loop blocked in select still starts advancing the coroutine
        immediately); completion notifications ride on a concurrent.futures.Future,
        and Event.wait() can be interrupted by Ctrl+C (polling wait).
        """
        loop = self._loop
        if loop is None:
            raise RuntimeError("loop has not been start()ed")
        if threading.current_thread() is self._thread:
            # already inside the loop thread: a blocking wait would prevent the
            # loop from advancing tasks — guaranteed deadlock. Refuse explicitly
            # rather than hang.
            raise RuntimeError(
                "run_async cannot be called inside the loop thread (a blocking wait would stall the loop). "
                "Await directly inside the coroutine, or use submit()."
            )
        fut = run_coroutine_threadsafe(coro, loop)
        done = threading.Event()

        def _on_fut_done(_: Any) -> None:
            done.set()

        # when the concurrent.futures.Future is already finished,
        # add_done_callback fires synchronously in the calling thread (no race);
        # when unfinished, the callback fires in the thread that wrote the result
        # (the loop thread) and the Event is set immediately. The polling wait
        # keeps Ctrl+C usable on Windows (same rationale as submit).
        fut.add_done_callback(_on_fut_done)
        while not done.is_set():
            done.wait(self._poll)
        exc = fut.exception()
        if exc is not None:
            raise exc
        return fut.result()


# legacy name compat: the default class name before 0.8 was StdLoopRuntime (from
# the loops/std_asyncio.py era). The implementation has fully moved to the
# self-developed nasyncio core; this alias keeps old address strings / old imports working.
StdLoopRuntime = NasyncioLoopRuntime


__all__ = ["NasyncioLoopRuntime", "NasyncTaskHandle", "StdLoopRuntime"]
