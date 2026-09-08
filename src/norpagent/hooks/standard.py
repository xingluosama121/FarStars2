# Copyright (c) 2026 xingluosama121, MIT Licensed
"""9 standard hook layers: the complete exposed surface of every execution structure in the agent lifecycle.

        L1  runtime lifecycle     on_agent_init / on_agent_shutdown
        L2  task lifecycle        on_task_start / done / error / stopped / timeout
        L3  input pipeline        before_input / after_input / on_user_input_required
        L4  session & history     before/after_session_create、before/after_message_append
        L5  message assembly      before/after_build_messages
        L6  step                  before_step / after_step
        L7  model call            before/after_model_call + 4 streaming events
        L8  tool call             before/after_tool_call + on_tool_error
        L9  result finalization   before_result / after_result

29 hooks in total; every one is an independent module-level API:

    from norpagent.hooks import before_model_call, after_tool_call
    before_model_call.subscribe(fn, system=registry)
    agent.hooks.before_model_call.subscribe(fn)      # equivalent to the line above

Mutating hooks (mutating=True) can rewrite the data flow through return values;
semantics are documented in each hook's comment; any mutating hook may raise
``HookVeto`` for a one-vote veto (the runtime wraps up per the execution point's semantics).
"""

from __future__ import annotations

from typing import List

from norpagent.hooks.core import Hook, HookLayer

# ═══════════════════════════════════════════════════════════════════
#  L1 – runtime lifecycle (order 10)
# ═══════════════════════════════════════════════════════════════════

L1 = HookLayer(
    "L1_runtime", order=10,
    description="Runtime lifecycle: creation and destruction of the Agent instance",
)

on_agent_init = L1.hook(
    "on_agent_init",
    description="Runtime initialization finished (after component assembly and UI subscription)",
    payload_keys=("preset",),
)
on_agent_shutdown = L1.hook(
    "on_agent_shutdown",
    description="Runtime shutting down (broadcast after sandbox/component release)",
    payload_keys=("preset",),
)

# ═══════════════════════════════════════════════════════════════════
#  L2 – task lifecycle (order 20)
# ═══════════════════════════════════════════════════════════════════

L2 = HookLayer(
    "L2_task", order=20,
    description="Task lifecycle: start, completion and the various terminations of one run()",
)

on_task_start = L2.hook(
    "on_task_start",
    description="Task started (input passed L3; session ready)",
    payload_keys=("task_id", "session_id", "preset", "user_input"),
)
on_task_done = L2.hook(
    "on_task_done",
    description="Task finished normally (final reply produced)",
    payload_keys=("task_id", "session_id", "content", "steps", "context"),
)
on_task_error = L2.hook(
    "on_task_error",
    description="Task terminated abnormally (broadcast after internal exception fallback)",
    payload_keys=("task_id", "error"),
)
on_task_stopped = L2.hook(
    "on_task_stopped",
    description="Task stopped (step cap / security block / hook veto, etc.)",
    payload_keys=("task_id", "reason"),
)
on_task_timeout = L2.hook(
    "on_task_timeout",
    description="Task timed out (task_timeout turn boundary or call_timeout hard interrupt)",
    payload_keys=("task_id", "timeout", "kind"),
)

# ═══════════════════════════════════════════════════════════════════
#  L3 – input pipeline (order 30)
# ═══════════════════════════════════════════════════════════════════

L3 = HookLayer(
    "L3_input", order=30,
    description="Input pipeline: user input can be rewritten, vetoed and observed before entering the system",
)

before_input = L3.hook(
    "before_input", mutating=True,
    description=(
        "Before processing user input. Return str = replace the input; raise HookVeto = "
        "the task ends as stopped (reason enters the error info); return None = no rewrite"
    ),
    payload_keys=("task_id", "user_input", "session_id", "params"),
)
after_input = L3.hook(
    "after_input",
    description="After the input is determined (rewrites / security scans finished)",
    payload_keys=("task_id", "user_input", "session_id"),
)
on_user_input_required = L3.hook(
    "on_user_input_required",
    description="Additional user input is required (human approval / UI questions)",
    payload_keys=("question", "default"),
)

# ═══════════════════════════════════════════════════════════════════
#  L4 – session & history (order 40)
# ═══════════════════════════════════════════════════════════════════

L4 = HookLayer(
    "L4_session", order=40,
    description="Session & history: complete hooks around session creation and every message persistence",
)

before_session_create = L4.hook(
    "before_session_create", mutating=True,
    description=(
        "Before session creation. Return str or {'title': str} = rewrite the session title; "
        "raise HookVeto = abandon creation (task ends as stopped)"
    ),
    payload_keys=("session_id", "title", "params", "task_id"),
)
after_session_create = L4.hook(
    "after_session_create",
    description="After session creation",
    payload_keys=("session_id", "title", "task_id"),
)
before_message_append = L4.hook(
    "before_message_append", mutating=True,
    description=(
        "Before a message is persisted. Return ChatMessage = replace; return False = drop this one; "
        "raise HookVeto = drop this one; None = no rewrite"
    ),
    payload_keys=("session_id", "message", "task_id"),
)
after_message_append = L4.hook(
    "after_message_append",
    description="After a message is persisted",
    payload_keys=("session_id", "message", "task_id"),
)

# ═══════════════════════════════════════════════════════════════════
#  L5 – message assembly (order 50)
# ═══════════════════════════════════════════════════════════════════

L5 = HookLayer(
    "L5_assembly", order=50,
    description="Message assembly: the process of merging the system prompt and history into model input",
)

before_build_messages = L5.hook(
    "before_build_messages", mutating=True,
    description=(
        "Before assembling messages. Return str = replace the system prompt; "
        "return {'system_prompt': str} = same as left; None = no rewrite"
    ),
    payload_keys=("system_prompt", "session_id", "step", "task_id", "tool_names"),
)
after_build_messages = L5.hook(
    "after_build_messages", mutating=True,
    description="After assembling messages. Return List[ChatMessage] = replace the whole message set",
    payload_keys=("messages", "system_prompt", "step", "task_id"),
)

# ═══════════════════════════════════════════════════════════════════
#  L6 – step (order 60)
# ═══════════════════════════════════════════════════════════════════

L6 = HookLayer(
    "L6_step", order=60,
    description="Step: the boundary of every iteration of the main loop",
)

before_step = L6.hook(
    "before_step", mutating=True,
    description=(
        "Start of every iteration. Return List[ChatMessage] = replace this round's messages; "
        "raise HookVeto = skip this round; None = no rewrite"
    ),
    payload_keys=("task_id", "step", "messages", "context", "params"),
)
after_step = L6.hook(
    "after_step",
    description="This round's model output processed (entering tool execution or finishing)",
    payload_keys=("task_id", "step", "content", "tool_calls"),
)

# ═══════════════════════════════════════════════════════════════════
#  L7 – model call (order 70)
# ═══════════════════════════════════════════════════════════════════

L7 = HookLayer(
    "L7_model", order=70,
    description="Model call: before the request, after the response, and throughout streaming deltas",
)

before_model_call = L7.hook(
    "before_model_call", mutating=True,
    description=(
        "Before the model request. Return {'messages': [...], 'params': {...}} = "
        "replace as needed; raise HookVeto = refuse this call (task stopped); None = no rewrite"
    ),
    payload_keys=("task_id", "step", "messages", "tool_schemas", "params"),
)
after_model_call = L7.hook(
    "after_model_call", mutating=True,
    description="After the model response. Return ModelOutput = replace this output",
    payload_keys=("task_id", "step", "output"),
)
on_reasoning = L7.hook(
    "on_reasoning",
    description="Model chain-of-thought delta (streamed by reasoning models)",
    payload_keys=("task_id", "content", "stream"),
)
on_content = L7.hook(
    "on_content",
    description="Model body delta (streamed per segment / whole)",
    payload_keys=("task_id", "content", "stream", "final"),
)
on_event = L7.hook(
    "on_event",
    description="Any model-side sub-event (compatible event passthrough)",
    payload_keys=("event_type", "data", "task_id"),
)
on_usage_update = L7.hook(
    "on_usage_update",
    description="Cumulative token usage update",
    payload_keys=("task_id", "input", "output", "total"),
)

# ═══════════════════════════════════════════════════════════════════
#  L8 – tool call (order 80)
# ═══════════════════════════════════════════════════════════════════

L8 = HookLayer(
    "L8_tool", order=80,
    description="Tool call: argument rewriting, one-vote veto, result rewriting, exception observation",
)

before_tool_call = L8.hook(
    "before_tool_call", mutating=True,
    description=(
        "Before tool execution. Return dict = replace arguments; return False / raise HookVeto = "
        "block the call (fill in a blocked_by_hook result); None = no rewrite"
    ),
    payload_keys=("task_id", "tool_name", "args", "context"),
)
after_tool_call = L8.hook(
    "after_tool_call", mutating=True,
    description=(
        "After tool execution. Return str = replace the result text; return ToolResult = replace the result; "
        "None = no rewrite"
    ),
    payload_keys=("task_id", "tool_name", "args", "result", "success", "context"),
)
on_tool_error = L8.hook(
    "on_tool_error",
    description="Tool execution raised an exception (broadcast after the framework caught it into a ToolResult)",
    payload_keys=("task_id", "tool_name", "error", "args"),
)

# ═══════════════════════════════════════════════════════════════════
#  L9 – result finalization (order 90)
# ═══════════════════════════════════════════════════════════════════

L9 = HookLayer(
    "L9_result", order=90,
    description="Result finalization: the last rewrite window before RunResult is returned to the caller",
)

before_result = L9.hook(
    "before_result", mutating=True,
    description=(
        "Before result finalization (on_task_done/error/stopped already broadcast). "
        "Return RunResult = replace the final result; raise HookVeto = keep the original result"
    ),
    payload_keys=("task_id", "result"),
)
after_result = L9.hook(
    "after_result", mutating=True,
    description=(
        "After result finalization. Return RunResult = replace the final result (the return value takes effect); "
        "raise HookVeto = keep the current result"
    ),
    payload_keys=("task_id", "result"),
)

# ── standard layer collection ─────────────────────────────

STANDARD_LAYERS: List[HookLayer] = [
    L1, L2, L3, L4, L5, L6, L7, L8, L9,
]

# all standard hooks (collection of module-level standalone APIs, for docs and traversal)
ALL_STANDARD_HOOKS: List[Hook] = [
    h for layer in STANDARD_LAYERS for h in layer.hooks.values()
]

MUTATING_HOOK_NAMES = [h.name for h in ALL_STANDARD_HOOKS if h.mutating]

__all__ = [
    "L1", "L2", "L3", "L4", "L5", "L6", "L7", "L8", "L9",
    "STANDARD_LAYERS",
    "ALL_STANDARD_HOOKS",
    "MUTATING_HOOK_NAMES",
    "on_agent_init", "on_agent_shutdown",
    "on_task_start", "on_task_done", "on_task_error",
    "on_task_stopped", "on_task_timeout",
    "before_input", "after_input", "on_user_input_required",
    "before_session_create", "after_session_create",
    "before_message_append", "after_message_append",
    "before_build_messages", "after_build_messages",
    "before_step", "after_step",
    "before_model_call", "after_model_call",
    "on_reasoning", "on_content", "on_event", "on_usage_update",
    "before_tool_call", "after_tool_call", "on_tool_error",
    "before_result", "after_result",
]
