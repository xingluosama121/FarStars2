# Copyright (c) 2026 xingluosama121, MIT Licensed
"""Run context: the full environment tools and hooks can access during one task execution.

``RunContext`` is passed to outer components through the ctx parameter of
``tool.run(args, ctx)`` and the ``context`` field in event payloads. It is the
single coupling surface between the agent kernel and outer components: components
depend only on the capabilities the context provides, never on concrete classes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Dict, Optional

if TYPE_CHECKING:  # type-checking-only references, avoiding circular imports
    from norpagent.kernel.registry import Registry
    from norpagent.protocols.sandbox import Sandbox
    from norpagent.protocols.scheduler import TaskScheduler
    from norpagent.protocols.session import SessionManager
    from norpagent.protocols.ui import UIAdapter


@dataclass
class RunContext:
    """Environment handle of one task run.

    Attributes:
        registry: component registry (can resolve other tools / models)
        session_manager / session_id: session read/write
        sandbox: current task sandbox (command execution, code execution)
        scheduler: task scheduler (can submit subtasks; entry point for multi-agent cooperation)
        ui: UI adapter (ask_user for human interaction)
        components: generic component instances declared by the preset ({kind: instance})
        params: merged result of preset params and task-level params
        task_id: task id
    """

    registry: Any = None
    session_manager: Any = None
    session_id: Optional[str] = None
    sandbox: Any = None
    scheduler: Any = None
    ui: Any = None
    params: Dict[str, Any] = field(default_factory=dict)
    task_id: str = ""
    preset_name: str = ""
    components: Dict[str, Any] = field(default_factory=dict)
    # task-level slot injection (3.9): the snapshot layer and raw override dict of
    # submit(slot_overrides=...). Tools and hooks may read this field to know which
    # task-level overrides this task used, but **must not modify** it — the kernel
    # manages the lifecycle of the override layer.
    task_slot_layer: Any = None
    slot_overrides: Dict[str, Any] = field(default_factory=dict)

    def component(self, kind: str, default: Any = None) -> Any:
        """Get a generic component by kind (e.g. "context_store" / "project_manager")."""
        return self.components.get(kind, default)

    @property
    def context_store(self) -> Any:
        """Context store component (used by context_add / context_search tools)."""
        return self.components.get("context_store")

    @property
    def project_manager(self) -> Any:
        """Project management component (used by project_status tool)."""
        return self.components.get("project_manager")

    @property
    def task_store(self) -> Any:
        """Task store component (used by task_* tools; may be None when the persistent scheduler carries its own)."""
        return self.components.get("task_store")

    def ask_user(self, question: str, default: str = "", kind: str = "") -> str:
        """Ask the user a question (returns default when the UI provides no interaction).

        ``kind`` is forwarded to the UI adapter so an approval prompt can render a
        binary approve/reject control while a clarification keeps the text box.
        A third-party adapter that still implements the old two-argument
        ``ask_user`` is called without ``kind`` rather than failing the request
        (which would otherwise be read as a denial).
        """
        if self.ui is not None:
            try:
                return self.ui.ask_user(question, default, kind)
            except TypeError:
                try:
                    return self.ui.ask_user(question, default)
                except Exception:
                    return default
            except Exception:
                return default
        return default


# ══════════════════════════════════════════════════════════
#  Context budget clamp (2026-09-13)
# ══════════════════════════════════════════════════════════
#
# When a conversation grows past the configured token budget, the oldest whole
# turns are dropped before the request is sent. The clamp obeys the four rules
# that keep a request body legal:
#   1. the three-part turn is atomic — reasoning, output and the
#      tool_call request/result pair travel together;
#   2. a turn is either kept in full or dropped in full (never sliced);
#   3. the assistant message that carries ``tool_calls`` and the ``tool``
#      message that carries the matching ``tool_call_id`` are one unit;
#   4. the newest turn is always kept, so the current input is never lost.
# Trimming only touches the request payload — the persisted session is intact.


def _estimate_text_tokens(text: str) -> int:
    if not text:
        return 0
    cjk = 0
    for ch in text:
        o = ord(ch)
        if 0x3040 <= o <= 0x30FF or 0x4E00 <= o <= 0x9FFF or 0xAC00 <= o <= 0xD7A3:
            cjk += 1
    other = len(text) - cjk
    return cjk + (other + 3) // 4


def estimate_text_tokens(text: str) -> int:
    """Rough token estimate of one raw text string (CJK ~1/char, other ~1/4 chars).

    Counts the **raw source text** (markdown / LaTeX delimiters included), not the
    rendered / stripped display text — so a reply's token count does not shrink
    when its markdown or formulas happen to render short.
    """
    return _estimate_text_tokens(text)


def estimate_tokens(messages: "list[Any]") -> int:
    """Rough token estimate of a message list (CJK ~1/char, other ~1/4 chars)."""
    total = 0
    for m in messages:
        total += 8  # per-message overhead
        total += _estimate_text_tokens(str(getattr(m, "content", "") or ""))
        total += _estimate_text_tokens(str(getattr(m, "reasoning", "") or ""))
        for tc in getattr(m, "tool_calls", None) or []:
            total += 8 + _estimate_text_tokens(str(getattr(tc, "name", "") or ""))
            total += _estimate_text_tokens(
                str(getattr(tc, "arguments", "") or ""))
    return total


def repair_tool_pairs(messages: "list[Any]") -> "list[Any]":
    """Make a transcript legal for OpenAI-compatible endpoints (request-only).

    OpenAI / DeepSeek / GLM and other compatible endpoints reject a request with
    HTTP 400 when an ``assistant`` message carrying ``tool_calls`` is not answered
    by one ``tool`` message per ``tool_call_id``:

        An assistant message with 'tool_calls' must be followed by tool messages
        responding to each 'tool_call_id'.

    A persisted transcript can end up in that state even though the kernel writes
    the pair atomically in normal flow — e.g. the process was killed while a tool
    was still executing, a ``before_message_append`` hook dropped the tool result,
    or a hook raised between the assistant append and the tool append. Once such a
    turn is in the history, EVERY later request to that session fails, which is
    what "regenerate" surfaced.

    This repairs the **request payload only** (the store is never touched):

    * every unanswered ``tool_call_id`` gets a synthetic ``tool`` message inserted
      before the next non-tool message (or at the end of the transcript);
    * an orphan ``tool`` message (whose ``tool_call_id`` was never requested) is
      dropped, because endpoints reject those too.

    Returns a new list; the original objects are not mutated.
    """
    from norpagent.protocols.model import ChatMessage

    out: "list[Any]" = []
    pending: "list[tuple[str, str]]" = []  # (tool_call_id, name) awaiting a result

    def flush() -> None:
        for cid, name in pending:
            out.append(ChatMessage(
                role="tool",
                tool_call_id=cid or None,
                name=name or None,
                content=("[tool result unavailable — the previous run was "
                         "interrupted before this tool returned]"),
            ))
        pending.clear()

    for m in messages:
        role = (getattr(m, "role", "") or "")
        if role == "tool":
            cid = str(getattr(m, "tool_call_id", "") or "")
            answered = False
            for i, (pid, _pn) in enumerate(pending):
                if pid and pid == cid:
                    pending.pop(i)
                    answered = True
                    break
            if answered:
                out.append(m)  # a legitimate result
            # else: orphan tool message — dropped (endpoints reject it)
            continue
        calls = getattr(m, "tool_calls", None)
        if role == "assistant" and calls:
            # a previous assistant's unanswered calls cannot sit between this one
            flush()
            out.append(m)
            for tc in calls:
                pending.append((
                    str(getattr(tc, "id", "") or ""),
                    str(getattr(tc, "name", "") or ""),
                ))
            continue
        # user / system / plain assistant: close any dangling pair first
        flush()
        out.append(m)
    flush()
    return out


def clamp_history(messages: "list[Any]", max_tokens: int) -> "list[Any]":
    """Drop the oldest whole turns so the estimate fits ``max_tokens``.

    ``max_tokens <= 0`` disables the clamp (returns a copy unchanged). Leading
    system messages are always kept. The last turn is always kept, even if it
    alone exceeds the budget; older turns are removed newest-first only when the
    whole turn fits (keep-all-or-drop-all). Tool_call / tool_call_id pairs are
    never split because a turn is handled as one unit.
    """
    msgs = list(messages)
    if max_tokens <= 0 or not msgs:
        return msgs
    lead = 0
    while lead < len(msgs) and (getattr(msgs[lead], "role", "") or "") == "system":
        lead += 1
    head = msgs[:lead]
    rest = msgs[lead:]
    units: "list[list[Any]]" = []
    cur: "list[Any]" = []
    for m in rest:
        if (getattr(m, "role", "") or "") == "user" and cur:
            units.append(cur)
            cur = [m]
        else:
            cur.append(m)
    if cur:
        units.append(cur)
    if len(units) <= 1:
        return msgs
    head_tokens = estimate_tokens(head)
    kept: "list[list[Any]]" = [units[-1]]
    kept_tokens = head_tokens + estimate_tokens(units[-1])
    for unit in reversed(units[:-1]):
        unit_tokens = estimate_tokens(unit)
        if kept_tokens + unit_tokens > max_tokens:
            break  # keep-all-or-drop-all: never slice an older turn
        kept.insert(0, unit)
        kept_tokens += unit_tokens
    return head + [m for unit in kept for m in unit]
