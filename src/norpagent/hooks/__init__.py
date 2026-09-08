# Copyright (c) 2026 xingluosama121, MIT Licensed
"""norpagent.hooks — 9-layer 29-hook system (bundled with the standard library, zero dependencies).

Every hook is an independent module-level API; every execution structure can be
intervened by hooks. Quick usage::

    from norpagent.hooks import before_model_call, HookVeto, HookLayer

    # 1. Module-level standalone API: subscribe / trigger / veto
    before_model_call.subscribe(observer, system=registry)

    # 2. Runtime-bound view: agent.hooks.<hook name>.*
    agent.hooks.before_tool_call.intercept(...)

    # 3. Custom hook + custom layer
    layer = HookLayer("L10_network", order=100)
    before_net = layer.hook("before_network_call", mutating=True)
    agent.hooks.install_layer(layer)

    # 4. Veto with one vote
    def veto(event): raise HookVeto("input contains sensitive information")
    before_input.subscribe(veto, system=registry)

Layer overview: L1 runtime lifecycle → L2 task → L3 input → L4 session & history →
L5 message assembly → L6 step → L7 model call → L8 tool call → L9 result finalization.
Full documentation in docs/hooks.md.
"""

from norpagent.hooks.core import (
    BoundHook,
    DYNAMIC_LAYER,
    Hook,
    HookLayer,
    HookSystem,
    HookVeto,
    get_default_system,
)
from norpagent.hooks.standard import (
    ALL_STANDARD_HOOKS,
    MUTATING_HOOK_NAMES,
    STANDARD_LAYERS,
    L1, L2, L3, L4, L5, L6, L7, L8, L9,
    on_agent_init, on_agent_shutdown,
    on_task_start, on_task_done, on_task_error,
    on_task_stopped, on_task_timeout,
    before_input, after_input, on_user_input_required,
    before_session_create, after_session_create,
    before_message_append, after_message_append,
    before_build_messages, after_build_messages,
    before_step, after_step,
    before_model_call, after_model_call,
    on_reasoning, on_content, on_event, on_usage_update,
    before_tool_call, after_tool_call, on_tool_error,
    before_result, after_result,
)

__all__ = [
    "Hook", "BoundHook", "HookLayer", "HookSystem", "HookVeto",
    "DYNAMIC_LAYER", "get_default_system",
    "STANDARD_LAYERS", "ALL_STANDARD_HOOKS", "MUTATING_HOOK_NAMES",
    "L1", "L2", "L3", "L4", "L5", "L6", "L7", "L8", "L9",
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
