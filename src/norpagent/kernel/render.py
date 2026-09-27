# Copyright (c) 2026 xingluosama121, MIT Licensed
"""Rendered request assembly: history -> plain text (2026-09-18).

Why this module exists
----------------------
The previous request assembly rewrote history *in place* through a chain of
mechanisms (``fold_history`` -> ``compress_history`` L1-L4 -> ``clamp_history``
-> ``repair_tool_pairs`` -> ``_inject_history_boundary``). Measured on the real
code path that chain had three properties nobody wanted:

1. it leaked its own bookkeeping into the payload (``[tools called: ...]``
   appended to assistant content, ``[compressed: N chars omitted]`` and
   ``[duplicate tool result omitted during compression]`` replacing tool
   results). Those markers were sent to the model, not merely shown in the UI;
2. its turn-granular passes were dead code in the product's main scenario: the
   main loop appends exactly ONE ``user`` message per task, so a 200-step task
   is a single turn and both ``fold_history`` (``len(units) <= keep``) and
   ``clamp_history`` (``len(units) <= 1``) returned the input untouched;
3. it spent attention on tool-call bookkeeping (pair repair, id matching)
   while the actual cost driver -- raw chain-of-thought replay -- was handled
   only as one pass among four.

This module replaces the whole chain with one deterministic render:

    <history>
    [round 1]
    user_content: "..."
    assistant: "..."
    </history>
    <current_content>
    "..."
    </current_content>

and, once the rendered history exceeds the configured budget, a single rolling
model summary:

    <summary>
    ...
    </summary>
    <history>
    [round 1 after summary]
    user_content: "..."
    assistant: "..."
    </history>
    <current_content>
    "..."
    </current_content>

Properties of the rendered form
-------------------------------
* chain-of-thought is never sent (the single largest saving, and the one that
  measured best);
* tool calls and tool results are almost never sent -- the single exception is
  ``ask_user``, kept in full (see "ask_user traffic"); therefore assistant/tool pairing
  cannot be broken and ``repair_tool_pairs`` is no longer needed;
* there is no in-place rewriting, so nothing can leak into the transcript;
* the session store is untouched: the UI and the persisted conversation are
  byte-for-byte what they were. Only the request payload changes.

ask_user traffic
----------------

``ask_user`` is the one tool whose call and result survive rendering. Its call
carries the question and its result carries the user's answer -- a human
decision the rest of the task has to keep obeying. Dropping it (as a plain
"tool traffic is never sent" rule would) hides the very constraint the user
just set, so the model re-asks or quietly ignores an answer it can no longer
see. Question and answer are therefore rendered in the finished history and in
the ``<earlier_steps>`` digest alike; every other tool still contributes
nothing.

Failure policy: rendering never raises. The summary call is best-effort -- on
error or timeout the step proceeds with the un-summarized history instead of
failing the task.
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
import time
from typing import Any, Dict, List, Optional

from norpagent.kernel.context import (
    _copy_message,
    estimate_text_tokens,
    estimate_tokens,
    repair_tool_pairs,
)

# ──────────────────────────────────────────────────────────────
#  Rendering
# ──────────────────────────────────────────────────────────────

_HISTORY_OPEN = "<history>"
_HISTORY_CLOSE = "</history>"
_SUMMARY_OPEN = "<summary>"
_SUMMARY_CLOSE = "</summary>"
_CURRENT_OPEN = "<current_content>"
_CURRENT_CLOSE = "</current_content>"

# The live loop is replayed verbatim, but only its most recent steps. A single
# long task has no finished history to summarize, so without this bound the
# payload would grow with the step count until the endpoint rejects it. Older
# in-flight steps are condensed into an ``<earlier_steps>`` digest that keeps the
# action/result facts the ReAct loop needs, minus the full bodies.
_LIVE_KEEP_STEPS = 6
_LIVE_DIGEST_OPEN = "<earlier_steps>"
_LIVE_DIGEST_CLOSE = "</earlier_steps>"
_LIVE_DIGEST_CAP = 120
_LIVE_DIGEST_MAX = 8000

# A content body that itself contains a closing tag would break the envelope.
# Neutralise the exact tags only: a broad "</" escape would corrupt code that
# legitimately contains closing tags.
_TAG_GUARDS = (
    (_HISTORY_CLOSE, "< /history>"),
    (_SUMMARY_CLOSE, "< /summary>"),
    (_LIVE_DIGEST_CLOSE, "< /earlier_steps>"),
    (_CURRENT_CLOSE, "< /current_content>"),
)

_SYSTEM_ROLE = "system"
_USER_ROLE = "user"
_ASSISTANT_ROLE = "assistant"
_TOOL_ROLE = "tool"

# ``ask_user`` is the one tool whose traffic is conversation rather than
# bookkeeping: its call carries the question and its result carries the user's
# answer. Both are rendered (module docstring, "ask_user traffic") instead of
# being stripped like every other tool call.
_ASK_TOOL = "ask_user"
_ASK_ANSWER_PREFIX = "user answer:"

# Per-message safety cap on one rendered body. Tool results are not rendered at
# all, so this only guards a pathological hand-written paste.
_BODY_CAP = 20000
_ESCAPE_MARK = "\n...[middle of this message omitted]...\n"

# Safety cap on the text handed to the summarizer (head + tail), so a huge
# history cannot turn the summary call into an unbounded request.
_SUMMARY_INPUT_CAP = 80000
_SUMMARY_INPUT_HEAD = 60000
_SUMMARY_INPUT_TAIL = 20000


def _guard_tags(text: str) -> str:
    for bad, good in _TAG_GUARDS:
        if bad in text:
            text = text.replace(bad, good)
    return text


def _quote(text: str) -> str:
    """Render a body as a quoted value.

    Newlines are preserved (they carry meaning inside code and diffs); only
    embedded double quotes are escaped, so the value stays unambiguous.
    """
    body = str(text or "")
    if len(body) > _BODY_CAP:
        half = (_BODY_CAP - len(_ESCAPE_MARK)) // 2
        body = body[:half] + _ESCAPE_MARK + body[-half:]
    body = _guard_tags(body)
    return '"' + body.replace('"', '\\"') + '"'


def _role_of(m: Any) -> str:
    return str(getattr(m, "role", "") or "")


def _body_of(m: Any) -> str:
    body = str(getattr(m, "content", "") or "").strip()
    attachments = getattr(m, "attachments", None)
    if attachments:
        try:
            names = [
                str((a or {}).get("name") or (a or {}).get("kind") or "file")
                for a in attachments if isinstance(a, dict)
            ]
        except Exception:  # noqa: BLE001
            names = []
        marker = "[attachment: %s]" % ", ".join(names or ["1 file"])
        body = (body + " " + marker).strip() if body else marker
    return body


def _ask_question(tc: Any) -> str:
    """The ``question`` argument of one ``ask_user`` call.

    ``arguments`` is a JSON string on the wire but may already be a dict when a
    caller builds the message by hand. Unparsable arguments are kept as raw text:
    a malformed call is still worth showing, while dropping it would hide both
    the question and the fact that it was asked.
    """
    args = getattr(tc, "arguments", "")
    data: Any = args if isinstance(args, dict) else None
    if data is None:
        try:
            data = json.loads(str(args or ""))
        except Exception:  # noqa: BLE001 -- malformed JSON: fall back to the raw text
            data = None
    if isinstance(data, dict) and data.get("question") is not None:
        return str(data.get("question")).strip()
    return str(args or "").strip()


def _ask_answer(text: Any) -> str:
    """The user's answer inside one ``ask_user`` tool result.

    ``AskUserTool`` labels a real answer with ``user answer: ``; the label is
    dropped here because the rendered line already names the speaker. Failure
    outputs (no UI reached / nobody answered) carry no label and are kept
    verbatim: the model has to be able to tell "the user decided X" from
    "nobody answered", and inventing a decision is exactly what is forbidden.
    """
    body = str(text or "").strip()
    if body[:len(_ASK_ANSWER_PREFIX)].lower() == _ASK_ANSWER_PREFIX:
        body = body[len(_ASK_ANSWER_PREFIX):].strip()
    return body


def _ask_lines(m: Any, asked: "set[str]", info: Dict[str, Any]) -> "List[str]":
    """Rendered lines for ``ask_user`` traffic on one row (empty = not such traffic).

    An assistant row contributes one line per ``ask_user`` call and remembers
    each call id; the matching ``tool`` row then contributes the answer. The id
    set belongs to one transcript scan, so a result is only ever claimed by the
    call that actually produced it.
    """
    role = _role_of(m)
    if role == _ASSISTANT_ROLE:
        lines: "List[str]" = []
        for tc in (getattr(m, "tool_calls", None) or []):
            if str(getattr(tc, "name", "") or "") != _ASK_TOOL:
                continue
            call_id = str(getattr(tc, "id", "") or "")
            if call_id:
                asked.add(call_id)
            lines.append("ask_user: " + _quote(_ask_question(tc)))
        if lines:
            info["asks"] = int(info.get("asks") or 0) + len(lines)
        return lines
    if role == _TOOL_ROLE:
        call_id = str(getattr(m, "tool_call_id", "") or "")
        if call_id and call_id in asked:
            asked.discard(call_id)
            info["asks"] = int(info.get("asks") or 0) + 1
            return ["user answer: " + _quote(_ask_answer(getattr(m, "content", "")))]
    return []


def _last_user_index(msgs: "List[Any]") -> int:
    for i in range(len(msgs) - 1, -1, -1):
        if _role_of(msgs[i]) == _USER_ROLE:
            return i
    return -1


def render_conversation(messages: "List[Any]") -> Dict[str, Any]:
    """Render a transcript into ``history_text`` / ``current_text`` + counters.

    Division of labour (this is what makes ``<current_content>`` meaningful):

    * the **last user message** is the current request -> ``current_text``;
    * everything else -- earlier rounds AND the steps already completed inside
      the current round -- is finished work and goes into ``history_text``.

    Assistant messages without content (pure tool-call turns) contribute
    nothing: tool calls are dropped by design, and tool results are dropped with
    them. The single exception is ``ask_user``, whose question and answer are
    rendered in place (``_ask_lines``) because that exchange is a decision the
    rest of the task has to keep obeying, not tool bookkeeping.
    Leading ``system`` messages are dropped here because the caller re-attaches
    the system prompt as its own message.
    """
    info: Dict[str, Any] = {
        "history_text": "", "current_text": "",
        "rounds": 0, "steps": 0, "skipped": 0, "chars": 0, "asks": 0,
    }
    msgs = [m for m in (messages or []) if _role_of(m) != _SYSTEM_ROLE]
    if not msgs:
        return info

    cut = _last_user_index(msgs)
    completed = msgs[:cut] if cut >= 0 else list(msgs)
    current_round = msgs[cut:] if cut >= 0 else []

    # -- completed rounds --------------------------------------------------
    blocks: List[List[str]] = []
    pending: List[str] = []
    round_no = 0
    # ask_user call ids seen so far, so each answer renders next to its question
    asked: "set[str]" = set()
    for m in completed:
        role = _role_of(m)
        if role == _USER_ROLE:
            if pending:
                blocks.append(pending)
                pending = []
            round_no += 1
            pending.append("[round %d]" % round_no)
            pending.append("user_content: " + _quote(_body_of(m)))
        elif role == _ASSISTANT_ROLE:
            body = _body_of(m)
            ask = _ask_lines(m, asked, info)
            if body:
                pending.append("assistant: " + _quote(body))
            elif not ask:
                info["skipped"] += 1
            pending.extend(ask)
        else:
            ask = _ask_lines(m, asked, info)
            if ask:
                pending.extend(ask)
            else:
                info["skipped"] += 1
    if pending:
        blocks.append(pending)

    # -- steps already completed inside the current round -------------------
    step_lines: List[str] = []
    # a fresh id set: this scan is independent of the completed-rounds one
    asked = set()
    for m in current_round[1:]:
        if _role_of(m) == _ASSISTANT_ROLE:
            body = _body_of(m)
            ask = _ask_lines(m, asked, info)
            if body:
                step_lines.append("assistant: " + _quote(body))
            elif not ask:
                info["skipped"] += 1
            step_lines.extend(ask)
        else:
            ask = _ask_lines(m, asked, info)
            if ask:
                step_lines.extend(ask)
            else:
                info["skipped"] += 1

    info["rounds"] = len(blocks)
    info["steps"] = len(step_lines)
    rounded = ["\n".join(b) for b in blocks]
    if step_lines:
        rounded.append("[current turn - completed steps]\n" + "\n".join(step_lines))
    info["history_text"] = "\n\n".join(rounded)
    info["current_text"] = _body_of(msgs[cut]) if cut >= 0 else ""
    info["chars"] = len(info["history_text"])
    return info


def _verbatim_slice(rows: "List[Any]") -> "List[Any]":
    """Copy the live-loop rows and make them legal for the endpoint.

    Two things happen here:

    * the rows are copied, so the payload never shares objects with the session
      store (a later rewrite must not mutate live history through the payload);
    * ``repair_tool_pairs`` guarantees the OpenAI contract -- an assistant row
      announcing ``tool_calls`` is always followed by one ``tool`` row per id,
      and an orphan ``tool`` row is dropped. A transcript can legitimately be
      broken here (the process died mid-tool, a hook dropped the result, a
      checkpoint was recorded inside a pair), and endpoints answer 400 for it.
    """
    try:
        fixed = list(repair_tool_pairs(rows))
    except Exception:  # noqa: BLE001 -- never fail a task over pair repair
        fixed = list(rows)
    return _copy_messages(fixed)


def _copy_messages(rows: "List[Any]") -> "List[Any]":
    """Copy verbatim rows so the payload never shares objects with the store.

    The assembly must not hand the provider the very objects the session keeps:
    a later rewrite (hook, compression, UI merge) would then mutate live
    history through the payload.
    """
    from norpagent.protocols.model import ChatMessage

    out: List[Any] = []
    for m in rows:
        try:
            out.append(_copy_message(m))
        except Exception:  # noqa: BLE001 -- fall back to a fresh clone
            out.append(ChatMessage(
                role=_role_of(m),
                content=str(getattr(m, "content", "") or ""),
                tool_calls=list(getattr(m, "tool_calls", None) or []) or None,
                tool_call_id=getattr(m, "tool_call_id", None),
                name=getattr(m, "name", None),
                reasoning=str(getattr(m, "reasoning", "") or ""),
                has_reasoning=bool(getattr(m, "has_reasoning", False)),
            ))
    return out


def _split_live(rows: "List[Any]", keep_steps: int) -> "tuple[List[Any], List[Any]]":
    """Split live-loop rows into (older, kept) at an assistant-call boundary.

    ``kept`` holds the most recent ``keep_steps`` steps, a step starting at an
    ``assistant`` row that carries ``tool_calls``. Cutting there keeps every kept
    tool result right after the call that produced it, so the verbatim slice
    stays legal for the endpoint (no orphan ``tool`` row at the front).
    """
    if keep_steps <= 0:
        return list(rows), []
    count = 0
    cut = 0
    for i in range(len(rows) - 1, -1, -1):
        if count >= keep_steps:
            cut = i + 1
            break
        if (_role_of(rows[i]) == _ASSISTANT_ROLE
                and getattr(rows[i], "tool_calls", None)):
            count += 1
    return list(rows[:cut]), list(rows[cut:])


def _brief(text: Any, limit: int = _LIVE_DIGEST_CAP) -> str:
    """One trimmed line, with the envelope tags neutralised."""
    body = " ".join(str(text or "").split())
    if len(body) > limit:
        body = body[:limit] + "..."
    return _guard_tags(body)


def _flat(text: Any) -> str:
    """One line with the envelope tags neutralised and nothing truncated.

    Used for ``ask_user`` traffic in the digest: a question or an answer that has
    been cut down to a prefix is no longer a decision, so it keeps its full body
    (newlines still collapse -- the digest is a line list).
    """
    return _guard_tags(" ".join(str(text or "").split()))


def _condense_rows(rows: "List[Any]") -> str:
    """One line per action and per result, for the steps leaving the verbatim set.

    The digest is what stops the fix from re-creating the blind-retry loop: the
    model still learns which tools ran and what they returned, it just loses the
    full bodies of the older steps.

    The one exception is ``ask_user``: that question and its answer are kept
    whole, because a truncated decision is not a decision (see the module
    docstring, "ask_user traffic").
    """
    lines: "List[str]" = []
    asked: "set[str]" = set()
    for m in rows:
        role = _role_of(m)
        if role == _ASSISTANT_ROLE:
            if str(getattr(m, "content", "") or "").strip():
                lines.append("- said: " + _brief(getattr(m, "content", "")))
            for tc in (getattr(m, "tool_calls", None) or []):
                name = str(getattr(tc, "name", "") or "?")
                if name == _ASK_TOOL:
                    # kept whole: a condensed question is useless and a condensed
                    # answer is worse than none (module docstring, "ask_user traffic")
                    call_id = str(getattr(tc, "id", "") or "")
                    if call_id:
                        asked.add(call_id)
                    lines.append("- asked the user: " + _flat(_ask_question(tc)))
                else:
                    lines.append("- called %s(%s)" % (
                        _brief(name, 40),
                        _brief(getattr(tc, "arguments", ""))))
        elif role == _TOOL_ROLE:
            call_id = str(getattr(m, "tool_call_id", "") or "")
            if call_id and call_id in asked:
                asked.discard(call_id)
                lines.append("- user answer: "
                             + _flat(_ask_answer(getattr(m, "content", ""))))
            else:
                lines.append("- result: " + _brief(getattr(m, "content", "")))
    if not lines:
        return ""
    # The digest itself must stay bounded: at 1000 steps the line list alone would
    # put the payload back over the budget it was condensed to protect. Keep the
    # newest lines (recency is what a ReAct loop reads) and count what was cut.
    kept: "List[str]" = []
    size = 0
    for line in reversed(lines):
        if size + len(line) + 1 > _LIVE_DIGEST_MAX and kept:
            break
        kept.append(line)
        size += len(line) + 1
    kept.reverse()
    dropped = len(lines) - len(kept)
    body = "\n".join(kept)
    if dropped:
        body = "[... %d earlier digest lines omitted ...]\n%s" % (dropped, body)
    return body


def compose(history_text: str, current_text: str, summary_text: str = "") -> str:
    """Wrap the rendered pieces in the request envelope."""
    parts: List[str] = []
    if str(summary_text or "").strip():
        parts.append("%s\n%s\n%s" % (_SUMMARY_OPEN, str(summary_text).strip(),
                                     _SUMMARY_CLOSE))
    if str(history_text or "").strip():
        parts.append("%s\n%s\n%s" % (_HISTORY_OPEN, str(history_text).strip(),
                                     _HISTORY_CLOSE))
    if str(current_text or "").strip():
        parts.append("%s\n%s\n%s" % (_CURRENT_OPEN, str(current_text).strip(),
                                     _CURRENT_CLOSE))
    return "\n".join(parts)


# ──────────────────────────────────────────────────────────────
#  Rolling summary
# ──────────────────────────────────────────────────────────────

_SUMMARY_SYSTEM_PROMPT = (
    "You compress the working history of an AI agent into a compact summary "
    "that replaces the original messages.\n"
    "Keep, in this order of priority: the user's goals and constraints; "
    "decisions already made; concrete facts discovered (file paths, names, "
    "numbers, commands that worked); what has been completed; what is still "
    "open or blocked. Drop greetings, restatements, and anything the reader "
    "does not need in order to continue the work.\n"
    "Write plain prose or short bullet lines. Do not add a preamble such as "
    "'Here is the summary'. Output the summary only."
)


def _cap_for_summary(text: str) -> str:
    if len(text) <= _SUMMARY_INPUT_CAP:
        return text
    return (text[:_SUMMARY_INPUT_HEAD]
            + "\n...[middle of the history omitted before summarizing]...\n"
            + text[-_SUMMARY_INPUT_TAIL:])


def summarize_text(provider: Any, text: str, previous: str = "",
                   params: Optional[Dict[str, Any]] = None) -> Optional[str]:
    """One-shot, tool-free summary call. Returns None when unavailable.

    ``previous`` is folded in so the summary rolls forward instead of being
    recomputed from scratch every time it is triggered.
    """
    if provider is None or not str(text or "").strip():
        return None
    from norpagent.protocols.model import ChatMessage

    body = _cap_for_summary(str(text))
    if str(previous or "").strip():
        body = ("Summary so far:\n%s\n\nNew history to merge in:\n%s"
                % (str(previous).strip(), body))
    msgs = [
        ChatMessage(role="system", content=_SUMMARY_SYSTEM_PROMPT),
        ChatMessage(role="user", content=body),
    ]
    call_params: Dict[str, Any] = {"temperature": 0.2}
    try:
        call_params["max_tokens"] = int((params or {}).get("summary_max_tokens") or 1500)
    except (TypeError, ValueError):
        call_params["max_tokens"] = 1500

    text_out = ""
    gen = getattr(provider, "generate", None)
    if callable(gen):
        try:
            out = gen(msgs, None, dict(call_params))
            text_out = str(getattr(out, "content", "") or "")
        except NotImplementedError:
            text_out = ""
        except Exception:  # noqa: BLE001 -- summary is an optimization, never fatal
            text_out = ""
    if not text_out:
        stream = getattr(provider, "stream", None)
        if callable(stream):
            try:
                chunks = []
                for chunk in stream(msgs, None, dict(call_params)):
                    piece = getattr(chunk, "content", "") or ""
                    if piece:
                        chunks.append(str(piece))
                text_out = "".join(chunks)
            except Exception:  # noqa: BLE001
                text_out = ""
    return text_out.strip() or None


# ──────────────────────────────────────────────────────────────
#  Summary store (per session, outside the session database)
# ──────────────────────────────────────────────────────────────

def default_summary_path() -> str:
    env = os.environ.get("NORPAGENT_SUMMARY_DB")
    if env:
        return env
    return os.path.join(os.path.expanduser("~"), ".norpagent",
                        "context_summaries.json")


class SummaryStore:
    """Persists ``{session_id: {"summary", "covered", "updated_at"}}``.

    ``covered`` is a message count, not a timestamp: how many of the session's
    messages (system messages excluded) the summary already stands for.
    Everything after that index is rendered normally.

    Kept in its own file on purpose -- the session database is never rewritten,
    so the UI keeps showing the full conversation.
    """

    def __init__(self, path: Optional[str] = None) -> None:
        self._path = path or default_summary_path()
        self._lock = threading.RLock()
        self._cache: Optional[Dict[str, Any]] = None

    # -- io ---------------------------------------------------------------
    def _load(self) -> Dict[str, Any]:
        if self._cache is not None:
            return self._cache
        data: Dict[str, Any] = {}
        try:
            with open(self._path, "r", encoding="utf-8") as fh:
                raw = json.load(fh)
            if isinstance(raw, dict):
                data = raw
        except Exception:  # noqa: BLE001 -- missing/corrupt file: start empty
            data = {}
        self._cache = data
        return data

    def _flush(self) -> None:
        data = self._cache or {}
        folder = os.path.dirname(self._path) or "."
        try:
            os.makedirs(folder, exist_ok=True)
            fd, tmp = tempfile.mkstemp(dir=folder, suffix=".tmp")
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(data, fh, ensure_ascii=False, indent=1)
            os.replace(tmp, self._path)
        except Exception:  # noqa: BLE001 -- persistence is best-effort
            pass

    # -- api --------------------------------------------------------------
    def get(self, session_id: str) -> Optional[Dict[str, Any]]:
        if not session_id:
            return None
        with self._lock:
            item = self._load().get(session_id)
        return dict(item) if isinstance(item, dict) else None

    def set(self, session_id: str, summary: str, covered: int,
            summary_covered: "Optional[int]" = None) -> None:
        if not session_id or not str(summary or "").strip():
            return
        with self._lock:
            data = self._load()
            data[session_id] = {
                "summary": str(summary).strip(),
                "covered": max(0, int(covered)),
                "summary_covered": max(0, int(
                    summary_covered if summary_covered is not None else covered)),
                "updated_at": time.time(),
            }
            self._flush()

    def set_checkpoint(self, session_id: str, checkpoint: int,
                       summary: str = "") -> None:
        """Record a model-declared history boundary.

        The checkpoint is a message index: everything before it stands for
        compacted work, everything from it onwards is still rendered verbatim.
        It is stored separately from ``covered`` because a summary usually
        stands for a shorter prefix -- letting a checkpoint promote the summary
        would send text that claims to cover history it never saw.

        ``summary`` is normally empty: the checkpoint outcome goes to the
        context store, so it stays recallable without being pinned into every
        request. A non-empty value replaces the pinned summary instead.
        """
        if not session_id:
            return
        with self._lock:
            data = self._load()
            item = dict(data.get(session_id) or {})
            item["checkpoint"] = max(0, int(checkpoint))
            item["checkpoint_at"] = time.time()
            if str(summary or "").strip():
                item["summary"] = str(summary).strip()
            item.setdefault("updated_at", time.time())
            data[session_id] = item
            self._flush()

    def clear(self, session_id: str) -> None:
        if not session_id:
            return
        with self._lock:
            data = self._load()
            if session_id in data:
                data.pop(session_id, None)
                self._flush()


_STORE: Optional[SummaryStore] = None
_STORE_LOCK = threading.Lock()


def shared_store() -> SummaryStore:
    global _STORE
    if _STORE is None:
        with _STORE_LOCK:
            if _STORE is None:
                _STORE = SummaryStore()
    return _STORE


# ──────────────────────────────────────────────────────────────
#  Entry point used by the kernel
# ──────────────────────────────────────────────────────────────

def build_request_messages(
    messages: List[Any],
    system_prompt: str = "",
    *,
    session_id: str = "",
    token_budget: int = 0,
    provider: Any = None,
    params: Optional[Dict[str, Any]] = None,
    store: Optional[SummaryStore] = None,
) -> List[Any]:
    """Assemble the request payload: ``[system?, user]`` plus the live-loop rows.

    Two zones, and the split is the whole point of this module:

    * finished history (everything before the last ``user`` row) is rendered as
      text -- thinking and tool traffic stripped, per R-056;
    * the live loop (the rows after it) is replayed verbatim, as real
      ``assistant`` / ``tool`` messages, so the ReAct loop can read its own
      motion instead of repeating the call it just made.

    ``token_budget <= 0`` disables summarizing: the rendered history is sent as
    it is. When the payload exceeds the budget a rolling summary is produced once
    and reused by later steps, so the model call happens once per crossing rather
    than on every step. A long single task has no finished history to summarize,
    so the oldest in-flight steps are then condensed into an ``<earlier_steps>``
    digest and only the most recent ``_LIVE_KEEP_STEPS`` steps stay verbatim.

    The input list is never modified. The objects handed back never alias the
    caller's messages.
    """
    from norpagent.protocols.model import ChatMessage

    msgs = list(messages or [])
    nsys = [m for m in msgs if _role_of(m) != _SYSTEM_ROLE]
    total = len(nsys)

    # The live request is the last ``user`` row; everything before it is
    # finished history. Rows after it are the live loop and are replayed
    # verbatim -- the ReAct loop reads its own motion to decide the next step.
    cut = _last_user_index(nsys)
    resume_at = cut if cut >= 0 else total
    hist_cut = resume_at

    keep_store = store or shared_store()
    state = keep_store.get(session_id) if session_id else None
    checkpoint = 0
    covered = 0
    summary_text = ""
    if state:
        covered = int(state.get("covered") or 0)
        checkpoint = max(0, int(state.get("checkpoint") or 0))
        if covered > total:
            # History shrank (regenerate / branch switch): the summary no
            # longer describes this transcript, so drop it rather than lie.
            keep_store.clear(session_id)
            covered = 0
            checkpoint = 0
        elif covered > resume_at:
            # The fresh text would be empty; keep the summary out of the way.
            covered = 0
        else:
            summary_text = str(state.get("summary") or "")

    if checkpoint > total:
        # The transcript was branched or truncated after the checkpoint: a
        # watermark past the end stands for a conversation that is gone.
        checkpoint = 0

    # The render floor is the furthest watermark, clamped to the task
    # boundary. The live loop is always replayed verbatim, so no watermark may
    # reach inside it: a checkpoint or summary that stripped in-flight steps is
    # exactly what made the model repeat its own last call until the step cap.
    floor = min(max(covered, checkpoint), hist_cut)

    def _assemble(floor_at: int) -> "tuple[str, str, List[Any]]":
        """Build (history_text, current_text, verbatim rows) for one floor.

        ``floor_at`` only ever cuts finished history. The rows after the live
        request are the loop's own motion and are handed back whole.
        """
        head = nsys[floor_at:hist_cut]
        live_row = [nsys[hist_cut]] if 0 <= hist_cut < total else []
        # ``live_row`` is appended so render_conversation keeps the live
        # request as ``current_text`` and renders everything before it as
        # finished history -- the split the previous design already used.
        piece = render_conversation(head + live_row)
        motion = list(nsys[hist_cut + 1:])
        return piece["history_text"], piece["current_text"], motion

    history_text, current_text, verbatim_rows = _assemble(floor)
    verbatim = _verbatim_slice(verbatim_rows)

    stats: Dict[str, Any] = {
        "rounds": 0,
        "steps": 0,
        "drops": 0,
        "covered": covered,
        "summary_covered": int(state.get("summary_covered") or 0) if state else 0,
        "checkpoint": checkpoint,
        "floor": floor,
        "summarized": False,
        "verbatim": len(verbatim),
        "history_tokens": estimate_text_tokens(history_text),
    }

    budget = 0
    try:
        budget = int(token_budget or 0)
    except (TypeError, ValueError):
        budget = 0
    stats["budget"] = budget

    # What the payload would actually carry: the summary stands for the covered
    # prefix, the rendered history for the finished rounds, and the verbatim
    # slice for the live loop. Measuring the rendered history alone
    # re-summarized on every later step, because the summary itself is never
    # part of ``history_text``.
    stats["summary_tokens"] = estimate_text_tokens(summary_text)
    stats["verbatim_tokens"] = estimate_tokens(verbatim)
    measured = (stats["summary_tokens"] + stats["history_tokens"]
                + stats["verbatim_tokens"])

    if budget > 0 and measured > budget:
        # Finished history first: one rolling summary is the cheapest shrink and
        # is reused by later steps instead of being recomputed.
        if provider is not None:
            new_summary = summarize_text(provider, history_text, summary_text,
                                         params=params)
            if new_summary:
                # The summary always stands for exactly the prefix before the
                # current request, so ``resume_at`` is the new watermark; adding
                # ``covered`` again would count that prefix twice.
                # ``summary_covered`` records where the boundary stood when the
                # summary was produced, so a later checkpoint cannot promote it
                # into covering the whole prefix.
                keep_store.set(session_id, new_summary, resume_at,
                               summary_covered=covered)
                summary_text = new_summary
                covered = resume_at
                # Clamped to the task boundary like the initial floor: a
                # watermark may never reach inside the live loop.
                floor = min(max(covered, checkpoint), hist_cut)
                history_text, current_text, verbatim_rows = _assemble(floor)
                verbatim = _verbatim_slice(verbatim_rows)
                stats["summarized"] = True
                stats["covered"] = covered
                stats["floor"] = floor
                stats["verbatim"] = len(verbatim)
                stats["history_tokens"] = estimate_text_tokens(history_text)
                stats["summary_tokens"] = estimate_text_tokens(summary_text)
                stats["verbatim_tokens"] = estimate_tokens(verbatim)
            else:
                stats["summarize_failed"] = True
            # One payload triggers at most one summary: if the fresh text alone
            # still exceeds the budget (e.g. a single huge completed step),
            # reporting it beats calling the model again inside the same
            # assembly.
            measured = (stats["summary_tokens"] + stats["history_tokens"]
                        + stats["verbatim_tokens"])

        # Still over budget, and a long single task has no finished history to
        # summarize -- the verbatim slice is the only part left that grows. Keep
        # the most recent steps verbatim and condense the older ones into a
        # digest, so the payload is bounded without blinding the loop.
        if measured > budget and len(verbatim_rows) > 2:
            older, kept = _split_live(verbatim_rows, _LIVE_KEEP_STEPS)
            digest = _condense_rows(older) if older else ""
            if digest:
                head = history_text.rstrip()
                history_text = ((head + "\n") if head else "") + "%s\n%s\n%s" % (
                    _LIVE_DIGEST_OPEN, digest, _LIVE_DIGEST_CLOSE)
                verbatim_rows = kept
                verbatim = _verbatim_slice(verbatim_rows)
                stats["live_digest"] = len(older)
                stats["live_kept"] = len(verbatim)
                stats["verbatim"] = len(verbatim)
                stats["history_tokens"] = estimate_text_tokens(history_text)
                stats["verbatim_tokens"] = estimate_tokens(verbatim)
                measured = (stats["summary_tokens"] + stats["history_tokens"]
                            + stats["verbatim_tokens"])

    # Reported whenever the payload still exceeds the budget, whether or not a
    # summary was possible, so the caller can surface it instead of silently
    # sending an oversized request.
    if budget > 0 and measured > budget:
        stats["still_over_budget"] = True

    payload_text = compose(history_text, current_text, summary_text)
    stats["payload_chars"] = len(payload_text)

    out: List[Any] = []
    if str(system_prompt or "").strip():
        out.append(ChatMessage(role=_SYSTEM_ROLE, content=system_prompt))
    out.append(ChatMessage(role=_USER_ROLE, content=payload_text))
    # the live loop, replayed as real messages so the model sees what it did
    out.extend(verbatim)
    try:
        _LAST_STATS.pop()
    except IndexError:
        pass
    _LAST_STATS.append(stats)
    return out


# Diagnostics for the most recent assembly (used by tests and by the UI when it
# wants to explain "why is the request this small"). A list is used so appends
# are atomic and readers never see a half-built dict.
_LAST_STATS: List[Dict[str, Any]] = []


def last_stats() -> Dict[str, Any]:
    """Return the stats of the most recent ``build_request_messages`` call."""
    return dict(_LAST_STATS[-1]) if _LAST_STATS else {}
