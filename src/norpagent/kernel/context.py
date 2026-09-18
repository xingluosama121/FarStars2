# Copyright (c) 2026 xingluosama121, MIT Licensed
"""Run context: the full environment tools and hooks can access during one task execution.

``RunContext`` is passed to outer components through the ctx parameter of
``tool.run(args, ctx)`` and the ``context`` field in event payloads. It is the
single coupling surface between the agent kernel and outer components: components
depend only on the capabilities the context provides, never on concrete classes.
"""

from __future__ import annotations

import copy
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

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


# ══════════════════════════════════════════════════════════
#  History compression (2026-09-15)
# ══════════════════════════════════════════════════════════
#
# 截断是最后退路，不是第一步。任何轮次被丢弃之前，先做**压缩**。
# 设计约束（都来自"不能把好事办成坏事"）：
#   1. 纯本地、确定性、**不调用模型**——压缩不允许花钱、失败或阻塞消息装配；
#   2. **不增删、不重排消息**，只改写消息的载荷字段——因此
#      assistant(tool_calls) 与 tool(result) 的配对天然保持合法；
#   3. 末尾若干条消息与开头 system 消息**永不改动**（当前输入不变形）；
#   4. 原始记录不动：本函数返回新列表，原对象不被修改。
#
# 分级（逐级加大力度，每级后重新估算，够了就停）：
#   L1 去思维链 + 去内联 base64 + 连续重复工具结果折叠
#   L2 超长工具结果 / 超长助手正文 → 头 + 尾 + 省略标记
#   L3 早前轮次降级为"卡片"（只留工具名与首段结论）
#   L4 当前任务内较早步骤一并降级为最小卡片
# 压缩后仍超预算，才由调用方走 clamp_history 截断。

_DATA_URL_RE = re.compile(
    r"data:[A-Za-z0-9.+-]+/[A-Za-z0-9.+-]+;base64,[A-Za-z0-9+/=\r\n]{64,}")

_TOOL_RESULT_DEGRADE_OVER = 1200   # 超过该字符数的工具结果才降级
_TOOL_RESULT_HEAD = 600
_TOOL_RESULT_TAIL = 300
_TOOL_RESULT_CARD_HEAD = 200
_ASSISTANT_DEGRADE_OVER = 900
_ASSISTANT_HEAD = 400
_ASSISTANT_TAIL = 150
_ASSISTANT_CARD_HEAD = 300
_ASSISTANT_CARD_TAIL = 120
_USER_CLIP_HEAD = 1500             # 超长用户输入（整段粘贴）才裁剪
_USER_CLIP_TAIL = 400
_DUP_MARK = "[duplicate tool result omitted during compression]"


def _clip_text(text: str, head: int, tail: int) -> str:
    """保留头尾、中间以标记替代（标记里写明省略了多少字符，便于人工核查）。"""
    s = str(text or "")
    keep = max(0, int(head)) + max(0, int(tail))
    if len(s) <= keep:
        return s
    omitted = len(s) - keep
    tail_part = s[-int(tail):] if tail and int(tail) > 0 else ""
    return "%s\n…[compressed: %d chars omitted]…\n%s" % (s[:int(head)], omitted, tail_part)


def _split_turns(messages: "list[Any]") -> "tuple[list[Any], list[list[Any]]]":
    """按 user 消息把历史切成 (前导 system, 轮次列表)。

    与 clamp_history 的切分口径完全一致：以 user 消息为新轮起点，前导 system
    独立返回。注意：一次长任务的中间步骤（assistant/tool 往返）属于**同一轮**，
    因此"保留最后一轮"并不等于"当前任务不受约束"——这正是压缩必须存在的理由。
    """
    msgs = list(messages)
    lead = 0
    while lead < len(msgs) and (getattr(msgs[lead], "role", "") or "") == "system":
        lead += 1
    head = msgs[:lead]
    units: "list[list[Any]]" = []
    cur: "list[Any]" = []
    for m in msgs[lead:]:
        if (getattr(m, "role", "") or "") == "user" and cur:
            units.append(cur)
            cur = [m]
        else:
            cur.append(m)
    if cur:
        units.append(cur)
    return head, units


class MessageCopyError(RuntimeError):
    """消息无法复制；本轮压缩必须放弃，绝不允许改写原对象。"""


def _isolate_mutables(c: Any) -> None:
    """把 ``c`` 上的可变容器换成与原对象不共享的副本。

    压缩只改写字段，但字段若与原对象共享 ``list`` / ``dict`` / ``ToolCallSpec``，
    改写就会回流到会话对象，进而写进 sessions.db 并泄漏到前端与下一轮请求
    （2026-09-15、2026-09-17 两次污染事故的共同根因）。
    """
    try:
        items = list(vars(c).items())
    except Exception:  # noqa: BLE001 — __slots__ 或不可内省对象
        return
    for attr, v in items:
        if not isinstance(v, (list, tuple, dict, set)):
            continue
        try:
            setattr(c, attr, copy.deepcopy(v))
            continue
        except Exception:  # noqa: BLE001
            pass
        try:
            if isinstance(v, list):
                setattr(c, attr, [copy.copy(x) for x in v])
            elif isinstance(v, dict):
                setattr(c, attr, dict(v))
            elif isinstance(v, set):
                setattr(c, attr, set(v))
            else:
                setattr(c, attr, tuple(v))
        except Exception:  # noqa: BLE001
            pass


def _copy_message(m: Any) -> Any:
    """复制一条消息：压缩只改写副本，绝不改动原对象（会话存储仍是全量原文）。

    降级顺序，**任何一级都不返回原对象**——返回原对象会让压缩改写回流到会话，
    这正是 2026-09-15 那批「压缩卡片被写进 sessions.db」事故的机制。
      1. ``copy.deepcopy``：常规路径，整图隔离；
      2. ``copy.copy``：保持类型（``to_openai`` 等方法继续可用），随后由
         :func:`_isolate_mutables` 隔离全部可变容器；
      3. ``object.__new__`` + ``__dict__`` 复制：同类型兜底。

    三级都失败时抛 :class:`MessageCopyError`，由调用方放弃本轮压缩：宁可多花
    token，也不能把关卡写进会话原文。
    """
    try:
        return copy.deepcopy(m)
    except Exception:  # noqa: BLE001
        pass

    c: Any = None
    try:
        c = copy.copy(m)
    except Exception:  # noqa: BLE001
        try:
            c = object.__new__(type(m))
            c.__dict__.update(vars(m))
        except Exception:  # noqa: BLE001
            c = None
    if c is None:
        raise MessageCopyError(
            "无法复制消息 %s：已放弃压缩以保护会话原文" % type(m).__name__
        )
    _isolate_mutables(c)
    return c


def _pass_drop_reasoning(msgs: "list[Any]", protected: set) -> int:
    """L1：丢弃思维链、剥离内联 base64、折叠连续重复的工具结果。"""
    changed = 0
    prev_tool_payload = None
    for i, m in enumerate(msgs):
        if i in protected:
            continue
        role = (getattr(m, "role", "") or "")
        # 连续重复的工具结果：保留消息本身（配对合法性），只替换载荷
        if role == "tool":
            body = str(getattr(m, "content", "") or "")
            if prev_tool_payload is not None and body and body == prev_tool_payload:
                m.content = _DUP_MARK
                changed += 1
            else:
                prev_tool_payload = body
        if getattr(m, "reasoning", ""):
            m.reasoning = ""
            try:
                # 回传三要素契约（2026-09-15）：发生过工具调用的助手消息，
                # reasoning_content 字段必须保留（可为空串），否则下一次请求
                # 返回 400；无工具调用的消息该字段本就不回传，置 False 让
                # to_openai() 直接省略。这样「历史只带空思维链、上一轮带全量」
                # 既省 token 又不破坏端点契约。
                m.has_reasoning = bool(getattr(m, "tool_calls", None))
            except Exception:  # noqa: BLE001
                pass
            changed += 1
        body = str(getattr(m, "content", "") or "")
        if "base64," in body:
            stripped = _DATA_URL_RE.sub("<inline-data removed>", body)
            if stripped != body:
                m.content = stripped
                changed += 1
    return changed


def _pass_clip_long(msgs: "list[Any]", protected: set) -> int:
    """L2：超长工具结果 / 超长助手正文 → 头 + 尾 + 省略标记。"""
    changed = 0
    for i, m in enumerate(msgs):
        if i in protected:
            continue
        role = (getattr(m, "role", "") or "")
        body = str(getattr(m, "content", "") or "")
        if role == "tool" and len(body) > _TOOL_RESULT_DEGRADE_OVER:
            m.content = _clip_text(body, _TOOL_RESULT_HEAD, _TOOL_RESULT_TAIL)
            changed += 1
        elif role == "assistant" and len(body) > _ASSISTANT_DEGRADE_OVER:
            m.content = _clip_text(body, _ASSISTANT_HEAD, _ASSISTANT_TAIL)
            changed += 1
    return changed


def _degrade_unit(unit: "list[Any]", aggressive: bool) -> int:
    """把一整轮降级为卡片：助手只留结论 + 工具名，工具结果只留首段。"""
    changed = 0
    for m in unit:
        role = (getattr(m, "role", "") or "")
        if role == "assistant":
            names = [str(getattr(tc, "name", "") or "")
                     for tc in (getattr(m, "tool_calls", None) or [])]
            body = str(getattr(m, "content", "") or "")
            keep_head = 120 if aggressive else _ASSISTANT_CARD_HEAD
            keep_tail = 0 if aggressive else _ASSISTANT_CARD_TAIL
            card = _clip_text(body, keep_head, keep_tail) if body else ""
            if names:
                card = ("%s\n[tools called: %s]" % (card, ", ".join(names))).strip()
            if card != body:
                m.content = card
                changed += 1
            for tc in (getattr(m, "tool_calls", None) or []):
                args = str(getattr(tc, "arguments", "") or "")
                if args and len(args) > 120:
                    try:
                        tc.arguments = "[arguments omitted during compression]"
                        changed += 1
                    except Exception:  # noqa: BLE001
                        pass
        elif role == "tool":
            body = str(getattr(m, "content", "") or "")
            head = 80 if aggressive else _TOOL_RESULT_CARD_HEAD
            card = _clip_text(body, head, 0)
            if card != body:
                m.content = card
                changed += 1
        elif role == "user":
            body = str(getattr(m, "content", "") or "")
            if len(body) > _USER_CLIP_HEAD + _USER_CLIP_TAIL:
                m.content = _clip_text(body, _USER_CLIP_HEAD, _USER_CLIP_TAIL)
                changed += 1
    return changed


def _pass_old_turns(msgs: "list[Any]", protected: set,
                    head: "list[Any]", units: "list[list[Any]]") -> int:
    """L3：早前轮次（非最后一轮）整体降级为卡片。"""
    if len(units) <= 1:
        return 0
    changed = 0
    for unit in units[:-1]:
        changed += _degrade_unit(unit, aggressive=False)
    return changed


def _pass_current_turn(msgs: "list[Any]", protected: set,
                       head: "list[Any]", units: "list[list[Any]]") -> int:
    """L4：当前任务内较早步骤也降级（长任务的增长恰恰都在这一轮里）。"""
    if not units:
        return 0
    last = units[-1][:-max(1, 2)] if len(units[-1]) > 2 else []
    return _degrade_unit(last, aggressive=True) if last else 0


def _fold_one_line(text: str, limit: int = 600) -> str:
    """把一段多行文本压成一行并截断（折叠历史用）。"""
    t = " ".join((text or "").split())
    if len(t) > limit:
        t = t[:limit].rstrip() + "\u2026"
    return t


def fold_history(messages: "list[Any]", keep_recent_turns: int = 3,
                 max_chars: int = 12000) -> "list[Any]":
    """把「最近 keep_recent_turns 轮」之外的历史折叠成 <history> 文本块。

    动机：每一步都全量重放历史（含思维链与完整工具载荷）会把账单推到百万级。
    折叠后旧轮次只留「用户说了什么 / 助手结论 / 调用了哪些工具」，工具结果正文
    整体丢弃；折叠块并入**当前用户消息**的前缀，因此消息数不随历史增长。

    约束：
      1. 最近 keep_recent_turns 轮**原样保留**（当前任务不受影响）；
      2. 无 system 头或轮数不足时不动作；失败静默（返回原列表）；
      3. ``keep_recent_turns <= 0`` 关闭折叠。
    """
    msgs = [_copy_message(m) for m in (messages or [])]
    if keep_recent_turns <= 0 or not msgs:
        return msgs
    try:
        head, units = _split_turns(msgs)
    except Exception:  # noqa: BLE001
        return msgs
    if len(units) <= keep_recent_turns:
        return msgs
    old_units = units[:-keep_recent_turns]
    recent_units = units[-keep_recent_turns:]

    lines: "list[str]" = []
    for unit in old_units:
        for m in unit:
            role = (getattr(m, "role", "") or "")
            text = (getattr(m, "content", "") or "").strip()
            if role == "user" and text:
                lines.append("用户：" + _fold_one_line(text))
            elif role == "assistant":
                calls = getattr(m, "tool_calls", None) or []
                names = [getattr(tc, "name", "") for tc in calls]
                names = [n for n in names if n]
                if text:
                    lines.append("助手：" + _fold_one_line(text))
                if names:
                    lines.append("（调用工具："
                                 + ", ".join(names) + "）")
    if not lines:
        return msgs
    body = "\n".join(lines)
    if len(body) > max_chars:
        body = body[:max_chars].rstrip() + "\u2026"
    block = "<history>\n" + body + "\n</history>\n\n"

    flat = [m for unit in recent_units for m in unit]
    target = None
    for i in range(len(flat) - 1, -1, -1):
        if (getattr(flat[i], "role", "") or "") == "user":
            target = i
            break
    if target is None:
        return msgs
    out = [_copy_message(m) for m in flat]
    out[target].content = block + (getattr(out[target], "content", "") or "")
    return list(head) + out


def compress_history(messages: "list[Any]", target_tokens: int,
                     protect_tail: int = 2,
                     max_level: int = 4) -> "tuple[list[Any], dict]":
    """压缩历史以贴合 ``target_tokens``；不够时由调用方再截断。

    返回 ``(new_messages, stats)``。``target_tokens <= 0`` 或本来就够→原样返回。
    ``protect_tail`` 为末尾不被改动的消息条数（当前输入不变形）。
    """
    msgs = [_copy_message(m) for m in (messages or [])]
    stats: Dict[str, Any] = {"target": int(target_tokens), "levels_run": [],
                             "changed": 0, "before_tokens": 0, "after_tokens": 0}
    if not msgs:
        return msgs, stats
    # 2026-09-15：压缩改为**无条件**。预算 <= 0（默认不设上限）时不再直接放行，
    # 而是至少执行 L1 安全级压缩：丢历史思维链 / 剥离内联 base64 / 折叠连续重复
    # 工具结果。这些改写不增删消息、不破坏 tool_call 配对，属纯收益，因此
    # 「历史思维链无上限回传」这一主要浪费在默认配置下即被消除。
    # 预算 > 0 时按原分级流程 L1→L4，仍不够再由调用方截断（截断是最后退路）。
    if target_tokens <= 0:
        protected0 = set(range(max(0, len(msgs) - max(0, int(protect_tail))), len(msgs)))
        before0 = estimate_tokens(msgs)
        changed0 = _pass_drop_reasoning(msgs, protected0) if max_level >= 1 else 0
        if changed0:
            stats["levels_run"].append("L1")
            stats["changed"] = changed0
        stats["before_tokens"] = before0
        stats["after_tokens"] = estimate_tokens(msgs)
        return msgs, stats
    before = estimate_tokens(msgs)
    stats["before_tokens"] = before
    if before <= target_tokens:
        stats["after_tokens"] = before
        return msgs, stats
    protect_n = max(0, int(protect_tail))
    protected = set(range(max(0, len(msgs) - protect_n), len(msgs)))
    head, units = _split_turns(msgs)
    for i in range(len(head)):          # 前导 system 永不改动
        protected.add(i)

    passes = [
        ("L1-drop-reasoning", lambda: _pass_drop_reasoning(msgs, protected)),
        ("L2-clip-long", lambda: _pass_clip_long(msgs, protected)),
        ("L3-old-turns", lambda: _pass_old_turns(msgs, protected, head, units)),
        ("L4-current-turn", lambda: _pass_current_turn(msgs, protected, head, units)),
    ]
    for idx, (name, fn) in enumerate(passes):
        if idx >= max(1, int(max_level)):
            break
        if estimate_tokens(msgs) <= target_tokens:
            break
        n = fn()
        stats["levels_run"].append(name)
        stats["changed"] += int(n or 0)
        if not n:
            continue
    stats["after_tokens"] = estimate_tokens(msgs)
    return msgs, stats

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
    head, units = _split_turns(msgs)
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


# ──────────────────────────────────────────────────────────────
# 上下文库回读（2026-09-15）
# ──────────────────────────────────────────────────────────────
# 缺陷：上下文库（context store）此前**只写不读**——写入靠 context_add 工具，
# 读取只有模型自发调用 context_search，且系统提示词只教写、不教读，装配请求时
# 也从不回读。结果是"跨会话知识库"对实际运行没有任何影响。
#
# 本函数把它接回主链路：任务开始时按用户输入检索一次，把命中的结论渲染成
# 一段有界的"长期记忆"块注入系统提示词。约束：
#   1. 只读、失败静默（回读不允许拖垮或阻断任务）；
#   2. 有界（条数 + 字符数双上限），默认最多 3 条 / 1200 字符；
#   3. 每次任务只查一次（注入系统提示词），不随步数重复膨胀。

_RECALL_TOP_K = 3
_RECALL_MAX_CHARS = 1200


def recall_context(store: Any, query: str, *, top_k: int = _RECALL_TOP_K,
                   max_chars: int = _RECALL_MAX_CHARS,
                   min_score: float = 0.0) -> str:
    """从上下文库回读与 ``query`` 相关的条目，渲染为有界的记忆块。

    无 store / 无 query / 无命中 / 任何异常 → 返回空字符串（调用方直接忽略）。
    """
    q = str(query or "").strip()
    if store is None or not q:
        return ""
    try:
        rows = store.search(q, top_k=max(1, int(top_k)), min_score=min_score) or []
    except Exception:  # noqa: BLE001 — 回读失败不得影响任务
        return ""
    if not rows:
        return ""

    lines: List[str] = []
    used = 0
    for row in rows:
        try:
            text = str(row.get("text", "") or "").strip()
            title = str(row.get("title", "") or "").strip()
            src = str(row.get("source", "") or "").strip()
        except AttributeError:
            continue
        if not text:
            continue
        head = "[" + (title or "未命名") + (" · " + src if src else "") + "] "
        piece = head + text
        room = max_chars - used
        if room <= 0:
            break
        if len(piece) > room:
            piece = piece[:max(0, room - 1)].rstrip() + "…"
        lines.append("- " + piece)
        used += len(piece)
        if used >= max_chars:
            break

    if not lines:
        return ""
    return (
        "## 长期记忆（来自上下文库，自动回读）\n"
        "以下条目是此前会话/任务沉淀的结论，可能与你当前任务相关；"
        "如与当前代码或现场冲突，以现场为准：\n" + "\n".join(lines)
    )
