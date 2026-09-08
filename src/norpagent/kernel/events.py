# Copyright (c) 2026 xingluosama121, MIT Licensed
"""Event system: the decoupling point between the agent loop and all outer components (UI / plugin hooks).

Event names align one-to-one with the 15 hooks of the existing plugin_system; when
external plugins are migrated in P3 the mapping is seamless: hook = event subscription.

Event flow (one task):
    on_task_start -> [ before_step -> (on_reasoning/on_content) ->
    before_tool_call -> after_tool_call ]* -> after_step -> on_task_done
    on_task_error on exceptions; on_task_stopped / on_task_timeout on step-cap / timeout
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional


class EventType(str, Enum):
    # L1 – Agent lifecycle
    ON_AGENT_INIT = "on_agent_init"
    ON_AGENT_SHUTDOWN = "on_agent_shutdown"
    # L2 – task
    ON_TASK_START = "on_task_start"
    ON_TASK_DONE = "on_task_done"
    ON_TASK_ERROR = "on_task_error"
    ON_TASK_STOPPED = "on_task_stopped"
    ON_TASK_TIMEOUT = "on_task_timeout"
    # L3 – step
    BEFORE_STEP = "before_step"
    AFTER_STEP = "after_step"
    BEFORE_TOOL_CALL = "before_tool_call"
    AFTER_TOOL_CALL = "after_tool_call"
    ON_USER_INPUT_REQUIRED = "on_user_input_required"
    # L4 – streaming events
    ON_REASONING = "on_reasoning"
    ON_CONTENT = "on_content"
    ON_EVENT = "on_event"
    ON_USAGE_UPDATE = "on_usage_update"


class HookVeto(Exception):
    """One-vote veto thrown by mutating hooks (the core semantics of the 9-layer hook system).

    When thrown at an execution point that supports veto semantics, the runtime
    wraps up safely per that point's semantics:
    - before_input: the task ends as stopped; the reason enters the error info;
    - before_tool_call: the tool call is blocked (equivalent to returning False);
    - before_model_call: this model call is refused; the task ends as stopped;
    - before_message_append: the message is not persisted;
    - other mutating points: this rewrite is ignored; the original value stands.

    Note: EventBus.intercept does **not** catch it (unlike ordinary subscriber
    exceptions), guaranteeing the veto semantics always reach the kernel.
    """

    def __init__(self, reason: str = "operation vetoed by a hook"):
        super().__init__(reason)
        self.reason = reason


# full list aligned with the existing plugin_system.HOOK_NAMES (including compat aliases)
ALL_EVENT_NAMES = [e.value for e in EventType]


@dataclass
class AgentEvent:
    """One event. ``payload`` is the event payload dict (per-event fields are documented at the emit site)."""

    type: str
    payload: Dict[str, Any] = field(default_factory=dict)
    ts: float = field(default_factory=time.time)

    def get(self, key: str, default: Any = None) -> Any:
        return self.payload.get(key, default)


Listener = Callable[[AgentEvent], None]


class EventBus:
    """Thread-safe, general-purpose event bus.

    Core API:

    - ``subscribe(listener, event_type=None)``: None subscribes to all events
    - ``once(listener, event_type=None)``: subscribe for a single event
    - ``unsubscribe(listener, event_type=None)``: remove a subscription
    - ``emit(type, **payload)``: publishes an event; subscriber exceptions are
      caught and logged without breaking the main flow
    - ``intercept(type, **payload)``: mutating dispatch, first non-None wins
    - ``emit_all(type, **payload)``: publish and collect all return values
    - ``wait(type, timeout=None)``: block until the event fires, return it
    - ``subscriber_count / has_listeners / clear``: state queries & reset

    High-concurrency optimization (copy-on-write):

    - the subscriber tables are **immutable snapshots**: subscribe / unsubscribe
      build a **new list** inside the lock and replace the reference, never mutating
      in place;
    - emit / intercept take a reference once inside the lock, then iterate
      **lock-free directly** — under high-frequency events (e.g. streaming
      on_content pushed per token) this avoids per-event list-copy overhead;
      concurrent writers replace the new list object, and old snapshots held by
      readers are never modified, so thread safety is unchanged.
    """

    def __init__(self) -> None:
        self._all: List[Listener] = []
        self._typed: Dict[str, List[Listener]] = {}
        self._lock = threading.RLock()
        self._log_error: Optional[Callable[[str], None]] = None

    def set_error_logger(self, logger: Callable[[str], None]) -> None:
        """Set the callback for subscriber exceptions (default prints to stderr)."""
        self._log_error = logger

    @staticmethod
    def _without_one(lst: List[Listener], listener: Listener) -> List[Listener]:
        """Return a new list with the first element equal to listener removed (copy-on-write semantics)."""
        for i, fn in enumerate(lst):
            if fn == listener:
                return lst[:i] + lst[i + 1:]
        return lst

    def subscribe(self, listener: Listener, event_type: Optional[str] = None) -> None:
        with self._lock:
            if event_type is None:
                self._all = self._all + [listener]
            else:
                self._typed[event_type] = self._typed.get(event_type, []) + [listener]

    def once(self, listener: Listener, event_type: Optional[str] = None) -> None:
        """Subscribe for a single event: the listener is auto-unsubscribed after its first invocation.

        Useful for one-shot waits from external scripts / programmatic integration
        without leaking a subscription. The listener receives the same
        :class:`AgentEvent` as a regular subscriber.
        """

        def _wrapped(event: AgentEvent) -> None:
            self.unsubscribe(_wrapped, event_type)
            try:
                listener(event)
            except Exception as exc:  # noqa: BLE001 — subscribers must not break the main loop
                self._report_error(event_type or "*", exc)

        self.subscribe(_wrapped, event_type)

    def unsubscribe(self, listener: Listener, event_type: Optional[str] = None) -> None:
        with self._lock:
            if event_type is None:
                self._all = self._without_one(self._all, listener)
            else:
                lst = self._typed.get(event_type)
                if lst:
                    new = self._without_one(lst, listener)
                    if new:
                        self._typed[event_type] = new
                    else:
                        del self._typed[event_type]

    def wait(self, event_type: str, timeout: Optional[float] = None) -> Optional[AgentEvent]:
        """Block until an event of ``event_type`` is emitted, then return it.

        Returns ``None`` when ``timeout`` seconds elapse first (or immediately
        when ``timeout=0`` and no event is pending). Subscriber exceptions are
        isolated exactly like ``emit``; a ``HookVeto`` raised inside a listener
        is swallowed here (wait is an observation primitive, not an intercept
        point). Safe to call from any thread.
        """
        box: Dict[str, Any] = {}
        done = threading.Event()

        def _capture(event: AgentEvent) -> None:
            box["event"] = event
            done.set()

        self.subscribe(_capture, event_type)
        if timeout is None or timeout <= 0:
            done.wait()  # timeout<=0 means "no timeout" (block indefinitely)
        elif not done.wait(timeout):
            # timeout: re-check once for the event-arrives-just-now race,
            # then drop the temporary subscription so nothing leaks.
            if not done.is_set():
                self.unsubscribe(_capture, event_type)
                return None
        return box.get("event")

    def emit_all(self, event_type: str, **payload: Any) -> List[Any]:
        """Publish an event and collect every subscriber's return value.

        Unlike ``emit`` (which discards return values) and ``intercept`` (which
        stops at the first non-None), ``emit_all`` returns the full ordered list
        of subscriber results — useful for fan-out queries over listeners.
        Subscriber exceptions are isolated and logged; ``HookVeto`` propagates.
        """
        event = AgentEvent(type=event_type, payload=payload)
        all_listeners, typed_listeners = self._snapshot(event_type)
        results: List[Any] = []
        for fn in all_listeners:
            try:
                results.append(fn(event))
            except HookVeto:
                raise
            except Exception as exc:  # noqa: BLE001 — subscribers must not break the main loop
                self._report_error(event_type, exc)
        if typed_listeners:
            for fn in typed_listeners:
                try:
                    results.append(fn(event))
                except HookVeto:
                    raise
                except Exception as exc:  # noqa: BLE001 — subscribers must not break the main loop
                    self._report_error(event_type, exc)
        return results

    def subscriber_count(self, event_type: Optional[str] = None) -> int:
        """Number of subscribers: all-events listeners when ``event_type`` is None,
        otherwise the listeners registered for that specific event type."""
        with self._lock:
            if event_type is None:
                return len(self._all)
            return len(self._typed.get(event_type, []))

    def has_listeners(self, event_type: Optional[str] = None) -> bool:
        """True when at least one subscriber would receive the event."""
        with self._lock:
            if event_type is None:
                return bool(self._all)
            return bool(self._typed.get(event_type))

    def clear(self, event_type: Optional[str] = None) -> int:
        """Remove all subscribers (optionally only those of one event type).

        Returns the number of removed listeners. Useful for tests and for
        hot-reload paths that rebuild a bus. Subscribers removed via ``clear``
        are not notified.
        """
        with self._lock:
            if event_type is None:
                removed = len(self._all) + sum(len(v) for v in self._typed.values())
                self._all = []
                self._typed = {}
                return removed
            lst = self._typed.pop(event_type, [])
            return len(lst)

    def _snapshot(self, event_type: str) -> "tuple[List[Listener], Optional[List[Listener]]]":
        """Take a reference snapshot of subscribers inside the lock (no copy; see the class docstring on copy-on-write)."""
        with self._lock:
            return self._all, self._typed.get(event_type)

    def emit(self, event_type: str, **payload: Any) -> None:
        event = AgentEvent(type=event_type, payload=payload)
        all_listeners, typed_listeners = self._snapshot(event_type)
        for fn in all_listeners:
            try:
                fn(event)
            except Exception as exc:  # noqa: BLE001 — subscribers must not break the main loop
                self._report_error(event_type, exc)
        if typed_listeners:
            for fn in typed_listeners:
                try:
                    fn(event)
                except Exception as exc:  # noqa: BLE001 — subscribers must not break the main loop
                    self._report_error(event_type, exc)

    def intercept(self, event_type: str, **payload: Any) -> Any:
        """Mutating-event dispatch: returns the first non-None subscriber return value.

        Consistent with the existing application's plugin_system
        _broadcast_mutating semantics: before_step / before_tool_call /
        after_tool_call hooks can modify the data flow through return values
        (None = no intervention). Returns None when there are no subscribers or
        all return None.

        ``HookVeto`` is special: **not caught** (the veto semantics must reach the
        kernel); other subscriber exceptions are logged and processing continues
        (subscribers must not break the main loop).
        """
        event = AgentEvent(type=event_type, payload=payload)
        all_listeners, typed_listeners = self._snapshot(event_type)
        for fn in all_listeners:
            try:
                result = fn(event)
                if result is not None:
                    return result
            except HookVeto:
                raise
            except Exception as exc:  # noqa: BLE001 — subscribers must not break the main loop
                self._report_error(event_type, exc)
        if typed_listeners:
            for fn in typed_listeners:
                try:
                    result = fn(event)
                    if result is not None:
                        return result
                except HookVeto:
                    raise
                except Exception as exc:  # noqa: BLE001 — subscribers must not break the main loop
                    self._report_error(event_type, exc)
        return None

    def _report_error(self, event_type: str, exc: Exception) -> None:
        msg = f"[EventBus] subscriber error on event {event_type}: {exc}"
        if self._log_error:
            self._log_error(msg)
        else:
            import sys

            print(msg, file=sys.stderr)
