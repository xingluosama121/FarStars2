<!-- Split by part from docs/DEVELOPER_MANUAL.EN.md; body is line-for-line identical -->

> **Developer Manual - Part 3: Hooks, Security, Plugins and CLI** | Covers: Chapters 9-13 | [Back to index](../README.md)

---

## Chapter 9 The 9-Layer 29-Hook System

> Design principle: **every execution structure must be exposed as an API and be
> intervenable by hooks.** Every hook is an independent module-level API; custom
> hooks and custom layers are supported; zero dependencies, standard library only.
> Read this chapter together with `docs/hooks.md` (the standalone hook-system
> document).

### 9.1 Hook Layers and the Full 29-Hook Table

The agent loop is cut into 9 layers, each exposing hooks:

```
L1 runtime lifecycle ─ L2 task ─ L3 input ─ L4 session & history ─ L5 message assembly
   ─ L6 step ─ L7 model call ─ L8 tool call ─ L9 result finalization
```

All 29 hooks are first-class objects importable under `norpagent.hooks`
(`from norpagent.hooks import before_model_call, ...`); full table:

| Layer | Hook | Mutating | Payload keys |
|---|---|---|---|
| L1 runtime | `on_agent_init` | | preset |
| L1 runtime | `on_agent_shutdown` | | preset |
| L2 task | `on_task_start` | | task_id, session_id, preset, user_input |
| L2 task | `on_task_done` | | task_id, session_id, content, steps, context |
| L2 task | `on_task_error` | | task_id, error |
| L2 task | `on_task_stopped` | | task_id, reason |
| L2 task | `on_task_timeout` | | task_id, timeout, kind |
| L3 input | `before_input` | ✓ | task_id, user_input, session_id, params |
| L3 input | `after_input` | | task_id, user_input, session_id |
| L3 input | `on_user_input_required` | | question, default |
| L4 session | `before_session_create` | ✓ | session_id, title, params, task_id |
| L4 session | `after_session_create` | | session_id, title, task_id |
| L4 session | `before_message_append` | ✓ | session_id, message, task_id |
| L4 session | `after_message_append` | | session_id, message, task_id |
| L5 assembly | `before_build_messages` | ✓ | system_prompt, session_id, step, task_id, tool_names |
| L5 assembly | `after_build_messages` | ✓ | messages, system_prompt, step, task_id |
| L6 step | `before_step` | ✓ | task_id, step, messages, context, params |
| L6 step | `after_step` | | task_id, step, content, tool_calls |
| L7 model | `before_model_call` | ✓ | task_id, step, messages, tool_schemas, params |
| L7 model | `after_model_call` | ✓ | task_id, step, output |
| L7 model | `on_reasoning` | | task_id, content, stream |
| L7 model | `on_content` | | task_id, content, stream, final |
| L7 model | `on_event` | | event_type, data, task_id |
| L7 model | `on_usage_update` | | task_id, input, output, total |
| L8 tool | `before_tool_call` | ✓ | task_id, tool_name, args, context |
| L8 tool | `after_tool_call` | ✓ | task_id, tool_name, args, result, success, context |
| L8 tool | `on_tool_error` | | task_id, tool_name, error, args |
| L9 finalize | `before_result` | ✓ | task_id, result |
| L9 finalize | `after_result` | ✓ | task_id, result |

A ✓ marks a **mutating hook** (mutating=True): subscribers can rewrite the data flow
through return values, or veto with one vote by raising `HookVeto`; the rest are
observation hooks (emit) whose return values are ignored. Each hook's complete
payload keys are governed by `Hook.payload_keys` (consistent with the hook comments
in `norpagent.hooks.standard`).

### 9.2 Three Usage Forms and Subscription-Target Resolution

```python
from norpagent.hooks import before_model_call

# 1. module-level independent API: without system, it lands on the "process default hook system"
before_model_call.subscribe(log_request)                # default system (private bus)
before_model_call.subscribe(log_request, system=reg)    # specify a Registry

# 2. runtime view: same bus as registry.hooks (recommended for multiple instances)
agent.hooks.before_model_call.subscribe(log_request)

# 3. slot bulk subscription: npa(hooks={"before_model_call": my_fn})
```

- The module-level `Hook` object's `subscribe / unsubscribe / emit / intercept`
  all need a `system` to locate the bus; you may pass a `HookSystem / EventBus /
  Registry / AgentRuntime` (unified resolution via `_resolve_bus`);
  **by default it lands on the process-level default system**
  (`hooks.get_default_system()`, with its own private bus) — it is NOT the same bus
  as the `npa()` engine's. When using a standalone Registry, **always pass `system`
  explicitly** (every Registry carries a private bus, guaranteeing multi-instance
  isolation); otherwise the subscription hangs on the default system and never
  receives engine events;
- `agent.hooks.before_model_call` returns a `BoundHook` (bound to that engine's
  bus); its four methods no longer need `system`;
- the `npa(hooks={...})` slot (literal semantics): dict keys are event names, values
  are subscribers, mounted on the engine bus at assembly time; hot-mounting
  `npa.remount(hooks=...)` unsubscribes the previous architecture-level subscriptions
  first and then remounts — **never stacking**. The slot value can also be a
  `callable(reg)` factory: called first, then the returned dict is subscribed.

### 9.3 Mutating-Hook Return Semantics and HookVeto

Mutating hooks dispatch through `EventBus.intercept`: **subscribers are called in
subscription order; the first non-None return value wins; all-None means no
intervention.** Full return-semantics table:

| Hook | Return | Effect |
|---|---|---|
| `before_input` | `str` | replace the user input |
| | `HookVeto(reason)` | the task wraps up as stopped; the reason enters the error info |
| `before_session_create` | `str` / `{"title": str}` | rewrite the session title |
| | `HookVeto` | abandon creation (the task wraps up as stopped) |
| `before_message_append` | `ChatMessage` | replace the message |
| | `False` / `HookVeto` | drop that message (not persisted) |
| `before_build_messages` | `str` / `{"system_prompt": str}` | replace the system prompt |
| `after_build_messages` | `List[ChatMessage]` | replace the whole message set |
| `before_step` | `List[ChatMessage]` | replace this round's messages |
| | `HookVeto` | skip this round's model call (go to the next round) |
| `before_model_call` | `{"messages": [...], "params": {...}}` | replace the request as needed |
| | `HookVeto` | refuse this round's call (the task wraps up as stopped) |
| `after_model_call` | `ModelOutput` | replace this output |
| `before_tool_call` | `dict` | replace the tool arguments |
| | `False` / `HookVeto` | block the call (backfilled with a blocked_by_hook result) |
| `after_tool_call` | `str` / `ToolResult` | replace the tool result |
| `before_result` / `after_result` | `RunResult` | replace the final result |
| both | `HookVeto` | keep the original result (the veto is ignored) |

`HookVeto` behavior details:

- the type is defined in `norpagent.kernel.events` (re-exported via
  `norpagent.hooks`); it subclasses `Exception`; the constructor argument is the
  veto reason;
- `EventBus.intercept` does **not catch** HookVeto — the veto semantics must reach
  the kernel, guaranteeing that a one-vote veto always takes effect; ordinary
  subscriber exceptions are caught and logged (stderr, or a logger specified via
  `bus.set_error_logger()`) and dispatch continues — a single subscriber can never
  drag down the main loop;
- each execution point's veto wrap-up semantics differ (see the table):
  before_input / before_model_call / before_session_create → the task is stopped;
  before_step → skip this round; before_tool_call → backfill blocked_by_hook;
  before_message_append → drop that message; before_result / after_result → the
  veto is ignored and the original result stands;
- subscriber dispatch order: all-event subscribers (`bus.subscribe(fn)` without an
  event name) run before named subscribers; within a group, in subscription order;
  emit calls one by one (exception-isolated), intercept calls one by one until a
  non-None return appears.

### 9.4 Custom Hooks and Custom Layers

Three extension forms, with exactly the same rights as the standard 29 hooks:

```python
from norpagent.hooks import HookLayer

# form one: custom layer + hooks declared inside the layer (the plugin-loading pipeline is the standard-library use case, 11.4)
network_layer = HookLayer("L10_network", order=100, description="network access layer")
before_net = network_layer.hook("before_network_call", mutating=True,
                                description="before a network request goes out (rewrite the URL or veto)")
agent.hooks.install_layer(network_layer)          # usable immediately after installation
agent.hooks.before_network_call.subscribe(monitor)

# form two: define a hook directly on the hook system (no layer; belongs to the dynamic layer)
agent.hooks.define_hook("after_cache_hit", mutating=False,
                        description="cache hit")

# form three: zero-definition trigger — an unregistered named event automatically becomes a dynamic-layer hook
agent.hooks.hook("my_custom_event").emit(data=42)
```

- `HookLayer(name, order, description)` declares a layer; `layer.hook()` returns a
  `Hook` definition (the module-level API), exportable in advance for third parties
  to `subscribe(fn, system=reg)`;
- `install_layer` sorts layers by `order`; **when a same-named hook already exists
  the original definition is kept** (only the layer metadata is recorded); repeated
  installation never overwrites existing subscriptions;
- `HookSystem` query API: `list_hook_names()` / `list_hooks()` / `layers()` /
  `layer_of(name)` / `get(name)`;
- custom hooks support `subscribe / unsubscribe / emit / intercept` as usual.

### 9.5 Relation to the General-Purpose Event Bus (GeneralEventBus / `EventBus`)

The hook system is a **structured view of the general-purpose event bus**
(GeneralEventBus; class `EventBus`, see 27.2), not another mechanism:

- `HookSystem` mounts the 9 standard layers onto an `EventBus` at construction;
  subscriptions and publications ultimately land on `registry.bus`;
- `reg.hooks.before_step.subscribe(fn)` and
  `reg.bus.subscribe(fn, "before_step")` are **exactly equivalent** and can be mixed;
- therefore hooks keep working after replacing the loop system (async_loop slot) —
  hooks hang on the event bus, independent of the loop implementation (FAQ Q6);
- event names align one-to-one with the early plugin_system's 16 compatible hooks
  (another 13 native hooks are open as well — 29 in total, see 33.5); old plugins
  / old code need no changes (Chapter 11's plugin-hook bridge relies on this);
- performance (0.9): EventBus uses copy-on-write — subscribe / unsubscribe replace
  the list inside the lock; emit / intercept take one snapshot reference and iterate
  lock-free; high-frequency streaming events (on_content per token) incur no
  per-event list-copy overhead (14.3 ultra-high concurrency).

### 9.6 Every Execution Structure Is Overridable

Besides hooks, the seven execution structures of `AgentRuntime` are public methods;
subclassing overrides that stage without touching the loop body:

```python
from norpagent import AgentRuntime, ChatMessage

class MyRuntime(AgentRuntime):
    def build_messages(self, system_prompt, session_id, *, step,
                       task_id, tool_names=None):
        messages = super().build_messages(...)     # run the L5 hooks first
        messages.append(ChatMessage(role="system", content="custom injection"))
        return messages

    def call_model(self, provider, history, schemas, params,
                   task_id, result, step):
        ...                                         # take over L7 entirely
```

Method list: `prepare_input` (L3) / `create_session`,
`append_message` (L4) / `build_messages` (L5) / `call_model`
(L7) / `execute_tool_call` (L8) / `finalize_result` (L9).
Override-vs-hook relation: the default implementation **runs hooks first, then the
default logic**; overrides may keep the super() call (hooks keep working) or take
over entirely (skipping hooks); you can also replace the whole loop class via the
`agent_runtime` slot (3.1).

### 9.7 Behavior Details and Best Practices

- blocked / vetoed / approval-denied tool calls uniformly flow through
  `after_tool_call` — an "execution structure" passes the hook regardless of outcome;
- `before_step` vetoing this round → skip the model call and go to the next round;
  `after_step` broadcasts only when there are tool calls (no tool calls: straight to
  the final-reply path);
- hook rewrites act on the **actual data flow** (messages / parameters / results),
  not side-channel notifications; rewritten values continue into the downstream
  pipeline;
- subscribing the same fn repeatedly executes it multiple times: when hot-mounting
  the hooks slot the framework unsubscribes architecture-level subscriptions first
  then remounts (no stacking); for your own subscriptions, pair them with
  unsubscribe (`EventBus.unsubscribe` removes only the first equal element);
- avoid heavy computation and blocking I/O inside high-frequency hooks
  (on_content / on_reasoning streaming per token); subscriber exceptions are
  isolated and logged, but the exception path has overhead;
- observation hooks' (emit) return values are ignored — to intervene in the data
  flow you must use a mutating hook (intercept) or a method override;
- thread safety: HookSystem / EventBus registry operations are locked; subscribing /
  unsubscribing while running is safe (3.7's hot mount relies on this);
- when you need intervention but do not want a global subscription: write the logic
  as a standalone function, gated by explicit task-level params (e.g.
  jailbreak_guard / harden_prompt, see 10.4), or use the `npa(hooks=...)` slot to
  subscribe on a specific engine only.

### 9.8 All 29 Hooks, One by One (Python Code)

This section gives **ready-to-run subscription examples** for every one of the 29
standard hooks. Every example follows the same pattern: the subscriber receives an
`AgentEvent` (`.get(key)` reads a payload key, `e.type` is the event name); mutating
hooks (marked ✓) rewrite the data flow via their return value per the 9.3 table, or
raise `HookVeto` for a one-vote veto. Examples subscribe through
`registry.hooks.<name>.subscribe(fn)` (bound bus, recommended); the module-level
API `norpagent.hooks.<name>.subscribe(fn, system=reg)` is fully equivalent and both
forms can be mixed (9.2).

Common preamble:

```python
import norpagent as npa
from norpagent.kernel.events import HookVeto

engine = npa()                # start the engine (or npa(safemode="on") minimal assembly)
hooks = engine.registry.hooks # hook view bound to the engine bus
```

#### L1 runtime lifecycle (2 hooks)

```python
# on_agent_init: broadcast once after the runtime is assembled (components + UI subscriptions done).
# payload: preset (final preset name)
def on_init(e):
    print(f"[init] preset={e.get('preset')}")

hooks.on_agent_init.subscribe(on_init)

# on_agent_shutdown: broadcast after shutdown (sandbox/component release done).
# payload: preset
def on_shutdown(e):
    print(f"[shutdown] preset={e.get('preset')}")

hooks.on_agent_shutdown.subscribe(on_shutdown)
```

#### L2 task lifecycle (5 hooks)

```python
# on_task_start: task began (input passed L3, session ready).
# payload: task_id, session_id, preset, user_input
def on_start(e):
    print(f"[task-start] {e.get('task_id')} input={e.get('user_input')!r}")

hooks.on_task_start.subscribe(on_start)

# on_task_done: task finished normally (final reply produced).
# payload: task_id, session_id, content, steps, context
def on_done(e):
    print(f"[task-done] {e.get('task_id')} steps={e.get('steps')}")

hooks.on_task_done.subscribe(on_done)

# on_task_error: task terminated abnormally (broadcast after internal error fallback).
# payload: task_id, error
def on_error(e):
    print(f"[task-error] {e.get('task_id')} {e.get('error')}")

hooks.on_task_error.subscribe(on_error)

# on_task_stopped: task stopped (step cap / safety block / hook veto, ...).
# payload: task_id, reason
def on_stopped(e):
    print(f"[task-stopped] {e.get('task_id')} reason={e.get('reason')}")

hooks.on_task_stopped.subscribe(on_stopped)

# on_task_timeout: task timed out.
# payload: task_id, timeout, kind (turn boundary or hard interrupt)
def on_timeout(e):
    print(f"[task-timeout] {e.get('task_id')} {e.get('kind')}")

hooks.on_task_timeout.subscribe(on_timeout)
```

#### L3 input pipeline (3 hooks)

```python
# before_input ✓: before the user input is processed. Return str = replace the
# input; raise HookVeto = the task ends as stopped; return None = no change.
# payload: task_id, user_input, session_id, params
def sanitize(e):
    text = e.get("user_input") or ""
    if "forbidden" in text:
        raise HookVeto("input contains blocked content")
    return text.strip()  # trim whitespace (return None to leave it alone)

hooks.before_input.subscribe(sanitize)

# after_input: input finalized (after rewrites / safety scans). Observation hook.
# payload: task_id, user_input, session_id
def log_input(e):
    print(f"[input] {e.get('user_input')!r}")

hooks.after_input.subscribe(log_input)

# on_user_input_required: extra user input is needed (approval / UI question).
# payload: question, default
def prompt_reminder(e):
    print(f"[ask-user] {e.get('question')} (default={e.get('default')!r})")

hooks.on_user_input_required.subscribe(prompt_reminder)
```

#### L4 session and history (4 hooks)

```python
# before_session_create ✓: before the session is created.
# Return str or {"title": str} = rewrite the session title; HookVeto = abandon.
# payload: session_id, title, params, task_id
def title_policy(e):
    title = e.get("title") or ""
    if "private" in title:
        raise HookVeto("sessions with sensitive titles are forbidden")
    return {"title": f"[{e.get('task_id')[:6]}] {title}"}

hooks.before_session_create.subscribe(title_policy)

# after_session_create: session created. Observation hook.
# payload: session_id, title, task_id
def log_session(e):
    print(f"[session] created {e.get('session_id')} title={e.get('title')!r}")

hooks.after_session_create.subscribe(log_session)

# before_message_append ✓: before a message is persisted.
# Return ChatMessage = replace; return False / raise HookVeto = drop the message;
# None = no change. payload: session_id, message, task_id
def redact(e):
    msg = e.get("message")
    if getattr(msg, "content", "").count("****") > 3:
        return False  # suspicious message, do not persist
    return msg

hooks.before_message_append.subscribe(redact)

# after_message_append: message persisted. Observation hook.
# payload: session_id, message, task_id
def watch_messages(e):
    print(f"[msg] {e.get('message')}")

hooks.after_message_append.subscribe(watch_messages)
```

#### L5 message assembly (2 hooks)

```python
# before_build_messages ✓: before messages are assembled.
# Return str = replace the system prompt; {"system_prompt": str} likewise; None = no change.
# payload: system_prompt, session_id, step, task_id, tool_names
def add_system_rules(e):
    base = e.get("system_prompt") or ""
    if e.get("step") == 1:
        return base + "\n[rule] answers must cite their sources."

hooks.before_build_messages.subscribe(add_system_rules)

# after_build_messages ✓: after assembly. Return List[ChatMessage] = replace the whole list.
# payload: messages, system_prompt, step, task_id
from norpagent import ChatMessage  # noqa: E402

def inject_history(e):
    messages = list(e.get("messages") or [])
    messages.append(ChatMessage(role="system", content="demo mode for this task."))
    return messages  # return None to leave it alone

hooks.after_build_messages.subscribe(inject_history)
```

#### L6 step (2 hooks)

```python
# before_step ✓: each loop iteration begins.
# Return List[ChatMessage] = replace this turn's messages; HookVeto = skip this turn;
# None = no change. payload: task_id, step, messages, context, params
def step_limiter(e):
    if e.get("step", 0) >= 10:
        raise HookVeto("step cap reached; stopping early")
    return None

hooks.before_step.subscribe(step_limiter)

# after_step: this turn's model output handled (tool execution or finish). Observation hook.
# payload: task_id, step, content, tool_calls
def trace_step(e):
    calls = [t.get("name") if isinstance(t, dict) else t
             for t in (e.get("tool_calls") or [])]
    print(f"[step {e.get('step')}] tools={calls}")

hooks.after_step.subscribe(trace_step)
```

#### L7 model call (6 hooks)

```python
# before_model_call ✓: before the model request is sent.
# Return {"messages": [...], "params": {...}} = replace the request as needed;
# HookVeto = refuse this call (task stopped); None = no change.
# payload: task_id, step, messages, tool_schemas, params
def model_guard(e):
    if not e.get("tool_schemas"):
        return {"messages": e.get("messages"),
                "params": {**e.get("params") or {}, "temperature": 0.0}}
    return None

hooks.before_model_call.subscribe(model_guard)

# after_model_call ✓: response received. Return ModelOutput = replace this output.
# payload: task_id, step, output
def cap_output(e):
    out = e.get("output")
    if out is not None and len(getattr(out, "content", "") or "") > 2000:
        out.content = out.content[:2000] + "..."
        return out
    return None

hooks.after_model_call.subscribe(cap_output)

# on_reasoning: reasoning-token increments (streaming reasoning models). Observation hook.
# payload: task_id, content, stream
def show_reasoning(e):
    print(f"[reasoning] {e.get('content')}", end="", flush=True)

hooks.on_reasoning.subscribe(show_reasoning)

# on_content: body-text increments (streaming chunks / full chunks). Observation hook.
# payload: task_id, content, stream, final
def show_content(e):
    print(e.get("content"), end="", flush=True)
    if e.get("final"):
        print()  # newline at stream end

hooks.on_content.subscribe(show_content)

# on_event: any model-side sub-event (passthrough). Observation hook.
# payload: event_type, data, task_id
def log_model_event(e):
    print(f"[model-event] {e.get('event_type')}: {e.get('data')}")

hooks.on_event.subscribe(log_model_event)

# on_usage_update: cumulative token usage. Observation hook.
# payload: task_id, input, output, total
def track_tokens(e):
    print(f"[usage] in={e.get('input')} out={e.get('output')} total={e.get('total')}")

hooks.on_usage_update.subscribe(track_tokens)
```

#### L8 tool call (3 hooks)

```python
# before_tool_call ✓: before a tool executes.
# Return dict = replace args; return False / raise HookVeto = block the call
# (a blocked_by_hook result is filled in); None = no change.
# payload: task_id, tool_name, args, context
def tool_allowlist(e):
    if e.get("tool_name") not in {"echo", "get_time", "file_read"}:
        raise HookVeto(f"tool {e.get('tool_name')} is not on the rescue allowlist")
    return None

hooks.before_tool_call.subscribe(tool_allowlist)

# after_tool_call ✓: after a tool executed.
# Return str = replace the result text; return ToolResult = replace the result;
# None = no change. payload: task_id, tool_name, args, result, success, context
def mask_secrets(e):
    if not e.get("success"):
        return None
    text = str(e.get("result") or "")
    return text.replace("sk-", "sk-***")  # redact secrets in the result

hooks.after_tool_call.subscribe(mask_secrets)

# on_tool_error: a tool raised (framework already converted it to ToolResult). Observation hook.
# payload: task_id, tool_name, error, args
def alert_tool_error(e):
    print(f"[tool-error] {e.get('tool_name')}: {e.get('error')}")

hooks.on_tool_error.subscribe(alert_tool_error)
```

#### L9 result finalization (2 hooks)

```python
# before_result ✓: before the final result is set (on_task_done/error/stopped already broadcast).
# Return RunResult = replace the final result; HookVeto = keep the original.
# payload: task_id, result
def annotate_result(e):
    result = e.get("result")
    if result is not None:
        result.final_content = (result.final_content or "") + "\n[note] appended by a hook"
        return result
    return None

hooks.before_result.subscribe(annotate_result)

# after_result ✓: after finalization. Return RunResult = replace (return value takes
# effect); HookVeto = keep the current result. payload: task_id, result
def last_word(e):
    return e.get("result")  # returning it unchanged = confirm; None also means no change

hooks.after_result.subscribe(last_word)
```

> Subscription lifecycle: subscribers live as long as the engine; clean up with
> `hooks.<name>.unsubscribe(fn)` or `engine.registry.bus.clear()` (all). Avoid
> blocking I/O inside high-frequency hooks (on_content / on_reasoning stream per token).

### 9.9 How External Python Scripts Subscribe and Fire Hooks

External scripts (standalone `.py` files, notebooks, ops tools) can subscribe to
hooks or publish custom events exactly like in-library code, in two ways:

1. **In-process embedding**: start the engine with `npa()` inside the script, then
   `engine.registry.hooks` is the engine's hook view (every 9.8 example works
   verbatim); exit with `npa.stop()` when done;
2. **Standalone process + own registry**: the script creates its own `Registry()`
   and `HookSystem`, subscribes through the module-level hook API without starting
   an engine — ideal for monitors, test stubs and event collectors (full template
   in Chapter 28, 28.2).

Module-level APIs and the bus are the same mechanism (9.5), so in an external
script `from norpagent.hooks import before_tool_call` then
`before_tool_call.subscribe(fn, system=engine.registry)` is exactly equivalent to
`engine.registry.hooks.before_tool_call.subscribe(fn)`.

Publishing custom events to the bus (cross-script / cross-plugin communication):

```python
engine.registry.bus.emit("my_custom_event", data=42)   # undefined events become dynamic hooks
engine.registry.hooks.hook("my_custom_event").emit(data=42)  # equivalent form
```

Waiting for an event (one-shot, the temporary subscription is auto-cleaned on
timeout; see 27.2.7):

```python
ev = engine.registry.bus.wait("on_task_done", timeout=60.0)
if ev is not None:
    print("task done:", ev.get("task_id"))
```

---

## Chapter 10 Security System: norpagent.safe()

> Core role: `safe()` converges the whole security suite (jailbreak
> protection / prompt hardening / human approval / network policy / source audit /
> import restrictions / signature trust / plugin isolation policy) into one
> standalone function. Companion document `docs/security.md`.

### 10.1 How to Enable

```python
import norpagent as npa

# 1. npa() slot form
npa(security="high")                                  # string: runtime policy only, zero hook intervention
npa(security={"level": "high", "hooks": True})        # dict: + explicit hook intervention
npa(security=lambda reg: safe(reg, config={...}))     # callable: fully custom assembly

# 2. safe() direct form
from norpagent import safe
kit = safe(registry, level="standard")               # basic / standard / high
kit = safe(registry, level="standard", hooks=True)

# 3. two-phase: get the kit first, install later
kit = safe(level="high")
kit.install(registry)                                # runtime policy only (no hooks by default)
kit.install(registry)                                # runtime policy only (no hooks by default)
kit.install_hooks(registry)                          # mount hooks manually when intervention is needed
kit.uninstall_hooks(registry)                        # take them down any time; the hook pipeline stays pure
```

Design points — **the security system is stripped out as a whole plug**:

- kernel modules never import any `norpagent.security` module at module level;
  guards / hardening / approval / audit / signatures are injected through
  `registry.security` (the kernel lazily imports guard only when task-level params
  explicitly request it, see 10.4);
- **zero hook intervention (default)**: safe() subscribes to no hooks by default —
  jailbreak protection and prompt hardening are not automatically mounted on the
  bus as hook subscribers; the hook pipeline stays pure; intervention is enabled
  explicitly by the user (hooks=True / kit.install_hooks());
- protection capabilities are always available as **independent APIs**
  (kit.scan_input / kit.harden / ..., 10.5) for use in your own hook subscribers or
  method overrides;
- runtime decisions (human approval / network policy / plugin-loading policy) always
  take effect through `registry.security` (SecurityContext), regardless of whether
  hooks are mounted;
- CLI equivalents: `--safe basic|standard|high` (runtime policy only),
  `--safe-hooks` mounts hooks explicitly.

### 10.2 The Three Levels

| Capability | basic | standard | high |
|---|---|---|---|
| input jailbreak/injection protection (L3 hook, explicit opt-in) | ✓ | ✓ | ✓ |
| system-prompt hardening (L5 hook, explicit opt-in) | ✓ | ✓ | ✓ |
| plugin-source AST audit | warn | warn | **block** |
| plugin import restrictions | off | safe | safe |
| permission declarations (manifest permissions) | | | ✓ |
| plugin network policy | allow_all | deny | deny |
| plugin-tool human approval | | ✓ | ✓ |
| enforced trusted signatures | | | ✓ |

- `basic`: only input protection and prompt hardening (and no hooks by default;
  enabled explicitly as needed); no plugin-side restrictions — for trusted-source
  local plugin development;
- `standard` (default): + plugin import restriction safe, network deny, plugin-tool
  approval; signature verification on but not enforced;
- `high`: + audit block (critical rejects), manifest permission declarations
  required, trusted signatures enforced (unsigned / untrusted are all refused).

### 10.3 SecurityContext: the Single Source of Truth for Runtime Security Policy

`registry.security` is a `SecurityContext` instance: AgentRuntime reads it for tool
approval; the plugin loader reads its `plugin_config()` when config is omitted.
Fields (preset by safe(level=...); override per-item with a config dict; key names
match norpagent.security / plugin-loader config):

| Field | Default (standard) | Note |
|---|---|---|
| `level` | standard | basic / standard / high |
| `guard_enabled` | True | input-protection master switch (hook intervention path) |
| `harden_enabled` | True | prompt-hardening master switch (hook intervention path) |
| `audit_level` | warn | off / warn / block |
| `import_restrict` | safe | off / safe / strict |
| `require_permissions` | False | manifest.permissions enforced |
| `signature_verify` | True | Ed25519 verification (invalid rejects) |
| `signature_required` | False | when True only trusted loads |
| `trusted_keys` | [] | trusted public-key hex list |
| `network_policy` | deny | deny / audited_public / public_only / allow_all |
| `approval_config` | None | approval-policy dict (10.6) |
| `plugin_isolation` | auto | auto / inproc / process |
| `hook_intervention` | False | True = mount protection hooks at install time |
| `extra` | {} | extension fields |

- `plugin_config()` converts this context into plugin-loader config (the fallback
  when config is omitted); `to_dict()` outputs the full posture (consistent with
  `kit.describe()`);
- a `SecurityContext` instance can be used directly as the `npa(security=ctx)` slot value;
- config keys favor the plugin-loader style (plugin_security_audit /
  plugin_network_policy / plugin_trusted_keys etc.), plus plain keys
  guard_enabled / harden_enabled / hook_intervention / approval /
  approval_config; safe()'s `_apply_config` maps them uniformly into
  SecurityContext.

### 10.4 Hook Intervention (explicit opt-in)

`hooks=True` / `kit.install_hooks()` mounts two subscribers:

- **L3 input protection** = a `before_input` subscriber: on jailbreak / injection
  features it raises `HookVeto` (the task wraps up as stopped). The task-level param
  `params["jailbreak_guard"] = False` explicitly disables hook protection for that
  task; `True` (or any truthy value) goes the kernel explicit-scan path — the kernel
  calls scan_message directly, **independent of whether hooks are mounted**;
- **L5 prompt hardening** = a `before_build_messages` mutating subscriber: injects
  the core rules and the tool list into the system prompt. The task-level param
  `params["harden_prompt"] = False` explicitly disables hardening for that task;
  `True` goes the kernel explicit-hardening path.

Mount / unmount semantics:

- `kit.install_hooks(reg)` is idempotent: repeated calls on the same registry never stack;
- `kit.uninstall_hooks(reg)` removes only **this kit's own** subscribers, leaving
  user / plugin subscriptions untouched; the hook pipeline returns to pure;
- `kit.hooks_installed(reg)` queries the current state;
- `kit.uninstall(reg)` unsubscribes hook subscriptions and clears
  `registry.security`. Hot-mounting the security slot at runtime
  (`npa.remount(security=...)`) uninstalls the old kit before installing the new one,
  preventing protection hooks from stacking on the same bus;
- after a hot mount, runtime decisions take effect immediately; hook intervention
  applies to subsequent tasks' before_input / before_build_messages.

### 10.5 Standalone Check APIs (usable without hooks)

SafetyKit proxies the norpagent.security modules; all are directly callable
standalone:

| Method | Capability |
|---|---|
| `kit.scan_input(text)` → (blocked, reason, hits) | jailbreak / injection scan |
| `kit.is_jailbreak_attempt(text)` → bool | scan result as boolean |
| `kit.harden(prompt, tool_names)` → str | prompt hardening |
| `kit.audit_file(path)` / `kit.audit_source(src)` → issues | source AST audit |
| `kit.verify_plugin(path, manifest)` → SignatureResult | plugin signature verification |
| `kit.check_network(url)` → bool | adjudicate per the current network policy (SSRF) |
| `kit.approval_policy(hints)` → ApprovalPolicy | approval-policy instance |
| `kit.network_policy()` → NetworkPolicy | network-policy instance |
| `kit.describe()` → dict | current security posture |

Example of calling the standalone APIs inside your own hook subscriber:

```python
from norpagent.hooks import HookVeto

def my_guard(event):
    blocked, reason, _ = kit.scan_input(event.get("user_input") or "")
    if blocked:
        raise HookVeto(reason or "input blocked by security protection")
reg.hooks.before_input.subscribe(my_guard)
```

The underlying modules (`norpagent.security`, zero framework dependency, importable
standalone): `guard` (scan / harden), `approval` (approval decisions),
`network_policy` (SSRF adjudication), `audit` (AST audit), `signature` (Ed25519,
requires the `norpagent[security]`-provided cryptography).

### 10.6 Runtime Decision Points

**Human approval** (AgentRuntime tool-execution path):

- policy-source priority: `params["approval_policy"]` instance >
  `params["approval_config"]` dict > `registry.security.approval_config`;
- native tools approve per "tool name → level" mapping (file_write /
  file_delete / exec_cmd etc. at WRITE / DELETE / EXEC level, with old tool-name
  compatibility); plugin tools go through the `approval_enabled` master switch plus
  the plugin's `APPROVAL_HINTS` fine control (approval="none" exempts, Chapter 11);
- interaction happens via the UI adapter through `ctx.ask_user` (broadcast with the
  on_user_input_required hook); a user denial cancels the call (approval_denied),
  which still flows through after_tool_call.

**Network policy / SSRF protection** (norpagent.security.network_policy):

- four granularities: `deny` (default) → `audited_public` (must hit the URL /
  domain whitelist) → `public_only` (private networks forbidden) → `allow_all`;
- except allow_all, private / loopback / link-local / reserved ranges / cloud
  metadata addresses (169.254.169.254 etc.) are always refused; text-level judgment
  first, then DNS-resolution re-check (covering the common rebinding path).

**Plugin-loading policy**: when `install_plugin_dirs` is given no explicit config,
it automatically adopts `registry.security.plugin_config()` — with the security
system stripped out, plugin loading inherits the global security posture by default
(11.8).

### 10.7 Security-No-Downgrade Principle and Defense in Depth

- without cryptography installed, signature verification returns "untrusted" and
  does **not** let it through (the security posture never downgrades);
  `norpagent[security]` provides the verification capability;
- plugin-loading order is fixed: signature verification → AST audit → permission
  declarations → import restrictions → registration (failure at any stage rejects;
  no next stage, 11.3);
- import restrictions are double-layered: AST static pre-check (preventing
  already-cached sys.modules modules from bypassing meta_path) + sys.meta_path
  runtime interception;
- process-level isolation (high / custom config) moves untrusted plugins out of the
  main process — even if the audit misses something, a plugin crash never affects
  the host (11.7);
- the kernel-side explicit param switches (jailbreak_guard / harden_prompt) coexist
  with safe()'s hook path: as long as either is on, protection is active
  (independent of whether hooks are mounted).

### 10.8 Typical Combinations

```python
# production default: standard + explicit hook intervention
npa(security={"level": "standard", "hooks": True})

# strict: high + whitelist network + trusted keys
kit = safe(level="high", config={
    "plugin_network_policy": "audited_public",
    "plugin_network_domain_allowlist": ["api.example.com"],
    "plugin_trusted_keys": ["<public key hex>"],
})
npa(security=kit.context)                     # install the SecurityContext directly

# decisions only, zero intervention: use only approval and network policy; wire the guard logic yourself
npa(security={"level": "standard",
             "config": {"guard_enabled": False, "harden_enabled": False}})
```

---

## Chapter 11 Plugin System

> External plugins ship as standalone `.py` files (or manifest packages); the host
> mounts them through the `norpagent.plugins` loader and automatically gains the
> full security suite: signature verification / AST audit / import restrictions /
> network policy / human approval. The plugin format is fully compatible with the
> existing plugin ecosystem; old plugins migrate without code changes.
> **Plugin authors should read Chapter 33 "The Complete Plugin Development Guide"
> directly** (all 29 hook signatures / the setup(api) registration surface / a full
> tutorial / troubleshooting / migration / release checklist); this chapter is the
> host-side overview.

### 11.1 Two APIs and the npa() Slot

```python
# convenient entry: load a directory in one call
from norpagent.plugins import install_plugin_dirs
loader = install_plugin_dirs(reg, ["my_plugins"], config={...})

# library facade: full lifecycle + status + hot reload
from norpagent.plugins import PluginSystem
ps = PluginSystem(reg, ["my_plugins"], config={"plugin_isolation": "auto"})
infos = ps.load()        # discover -> secure load -> register
ps.status()              # plugin list + isolation-host status
ps.reload("my_tool")     # hot-reload a single plugin during development
ps.shutdown()            # release process-isolated host subprocesses

# npa() slot (literal semantics, directory list)
npa(plugins=["./my_plugins"])
# runtime hot replacement: old subscriptions auto-unsubscribed, never stack (3.7)
npa.remount(plugins=["./my_plugins_v2"])
```

The `npa(plugins=[...])` slot assembles with fixed config (audit=warn, verification
on, **does not read** registry.security's overrides); for fine-grained config use
PluginSystem / install_plugin_dirs directly on a Registry (or a callable slot value
like `npa(plugins=lambda reg: ps.load())`).

### 11.2 Plugin Format (compatible with the existing application)

**Module-level interface** (single-file plugin `my_plugin.py`):

| Name | Type | Note |
|---|---|---|
| `PLUGIN_NAME` | str | plugin display name (required) |
| `PLUGIN_VERSION` | str | version, default 0.0.0 |
| `PLUGIN_PUBLISHER` | str | publisher |
| `PLUGIN_DESCRIPTION` | str | description |
| `TOOLS` | list | OpenAI function schema list |
| `execute(tool_name, args, ctx)` | callable | unified tool entry, returns str / None |
| `APPROVAL_HINTS` | dict | tool → approval hint (11.8) |
| `ISOLATION` | str | `"process"` = process-level isolation (read statically via AST; code never executes in the host) |
| `__norpagent_type__` | str | file-as-module type declaration ("tool" / "plugin", for FLOW drag-in) |
| `PLUGIN_CAPABILITIES` | list | capability surface (33.8.1; absent = the base set tools / hooks / events) |
| `PLUGIN_REQUIRES` / `PLUGIN_MIN_NORPAGENT` | list·dict / str | dependency and minimum-version declarations (33.10) |
| `setup(api)` / `on_load(ctx)` / `on_unload(ctx)` | callable | registration facade and lifecycle (33.7 / 33.8) |
| hook functions | callable | 16 compatible hooks aligned parameter by parameter + 13 native hooks = 29 (11.5 / 33.5) |

```python
# my_plugin.py -- minimal plugin
PLUGIN_NAME = "greet_plugin"
TOOLS = [{
    "type": "function",
    "function": {
        "name": "greet",
        "description": "greet the user",
        "parameters": {"type": "object",
                       "properties": {"name": {"type": "string"}},
                       "additionalProperties": False},
    },
}]

def execute(tool_name, args, ctx):
    if tool_name == "greet":
        return f"hello, {args.get('name') or 'world'}!"
    return None
```

**Manifest-package format**: a directory + `manifest.json` (name / version /
publisher / description / entry default plugin.py / permissions / signature /
isolation fields).

### 11.3 The Security Pipeline (the full load flow)

```
discovery (directory scan: *.py single files / manifest packages)
  -> before_plugin_load (HookVeto can refuse, 11.4)
  -> 1. signature verification: invalid rejects directly; signature_required allows only trusted
  -> 2. trust grading: trusted signature -> audit relaxed to warn
  -> 3. AST audit: dangerous calls / dangerous imports / getattr, __dict__ reflection bypass
       detection; at block level, critical findings reject
  -> 4. permission declarations: manifest.permissions validated when require_permissions
  -> 5. isolation decision: process -> the plugin loads only in a host subprocess (11.7)
  -> 6. module loading under import restrictions (static pre-check + meta_path interception, 11.6)
  -> 7. read metadata (PLUGIN_NAME / TOOLS / hooks / APPROVAL_HINTS)
  -> before_plugin_register (HookVeto can refuse)
  -> 8. adapt to the Plugin protocol -> register into the Registry (tools into the table, hooks subscribe the bus)
```

A failure at any stage → `PluginInfo(enabled=False, error=...)` records the reason
and scanning **continues with other plugins**; loading is never interrupted.
`PluginInfo` carries `name / path / version / publisher / description / enabled /
error / tools / hook_names / signature_status / trusted /
approval_hints / audit_issues`; for debugging see `loader.plugins[i].error` and
`audit_issues` (with line numbers).

### 11.4 Pipeline Hooks (the standard-library use case for custom layers)

PluginSystem mounts `PLUGIN_PIPELINE_LAYER` (a custom HookLayer with order=200 — the
official example of the 9.4 capability) onto `registry.hooks` at construction;
(a custom HookLayer with order=200 — the official example of the 9.4 capability) on
`registry.hooks`; 8 pipeline hooks:

`before/after_plugin_discover`, `before/after_plugin_load`,
`before/after_plugin_audit`, `before/after_plugin_register`.

```python
from norpagent.hooks import HookVeto
from norpagent.plugins import before_plugin_load

def block_listed(event):
    if (event.get("name"), event.get("path")) in HOST_BLOCKLIST:
        raise HookVeto("this plugin is rejected by the host policy")
before_plugin_load.subscribe(block_listed, system=reg)
```

- mutating pipeline hooks (before_plugin_load / before_plugin_audit /
  before_plugin_register) raising HookVeto = refusing that plugin's loading /
  registration (enabled=False + error records the reason); after_* are observation
  hooks (after_plugin_audit's payload includes allowed / issues);
- pipeline hooks register dynamically via `registry.hooks.hook(name)` and do not
  conflict with plugin module-level hooks.

### 11.5 Old-Plugin Hook Bridge (16 compatible hooks aligned; all 29 hooks open)

Hook functions defined at plugin module level are wrapped by the loader into
EventBus subscribers; the **16 compatible hooks** align parameter by parameter
with the existing ecosystem, and the **13 native hooks** (before_input /
before_model_call / before_result, ...) can be defined too — a plugin may define
any of the **29 standard hooks** (full table + signatures in 33.5):

- signature convention: **business parameters first, PluginContext last** (ctx
  field reference in 33.6);
- mutating hooks' return values pass through the bus to the kernel (first
  non-None wins); returning the input unchanged (`return messages` / `return args`
  / `return result`) counts as "no rewrite" and never shadows other plugins;
- every subscriber is invoked exactly once and all side effects run (no more
  truncation or double dispatch);
- hook exceptions are no longer silent: the first error is printed, counted and
  recorded into `PluginInfo.diagnostics`;
- process-isolated plugins go through the same bridge: fire_hook RPC forwarding
  (5s time limit; the `on_task_stopped` signature auto-adaptation happens inside
  the child process).

### 11.6 Import Restrictions

- `off`: no restrictions (local debugging; a trusted signature only relaxes the
  audit — import restrictions still follow the config);
- `safe` (standard / high default): blocks dangerous modules (subprocess / ctypes /
  cffi / socket / pickle / marshal / telnetlib / ftplib / smtplib; ctypes / cffi
  blocked unconditionally), **double-layered**: AST static pre-check (preventing
  already-cached sys.modules modules from bypassing meta_path) + loading-time
  sys.meta_path interception (stack-frame probing whether the caller is a plugin
  module);
- `strict`: only the safe-module whitelist is allowed (json / re / datetime / math /
  random / collections / itertools / functools / typing / enum / pathlib / os.path /
  textwrap / string / hashlib / base64 / traceback / logging / warnings / copy /
  uuid / time / norpagent.protocols.tool etc.); anything outside the whitelist
  raises ImportError.

Plugin modules load under the `norpagent_ext_<name>` module name (unified
namespace); the restrictor **only applies to plugin modules**, never to host code.

### 11.7 Process-Level Isolation

`ISOLATION = "process"` (module constant, read statically via AST — **plugin code
never executes in the host**) / the manifest `isolation` field / host config
`plugin_isolation` (auto takes the former two; explicit inproc / process forces).
Isolation semantics:

- the plugin module object exists only in a host subprocess (`python -m
  norpagent.plugins.host`, JSON-lines-protocol RPC);
- tool execution returns via RPC; hooks forward via fire_hook, each hook limited to
  5s (HOOK_TIMEOUT), abandoned on timeout — plugin hooks can never stall the main loop;
- crash self-healing: child-process death → auto restart + reload of all plugins →
  one retry;
- tool errors never bubble: remote exceptions become failed ToolResults;
- import restrictions keep working inside the child process (defense in depth);
- **registration-surface limit**: plugin code of process-isolated plugins does not
  run in the main process, so the `setup(api)` registration surface is not offered
  (a warning is recorded at load); the tool and hook surfaces are unaffected (see
  33.9.4).

### 11.8 Interplay with the Security System

- `install_plugin_dirs(reg, dirs)` **without config** automatically adopts
  `registry.security.plugin_config()` — call `safe(reg, ...)` first, then install
  plugins, and plugin loading inherits the global security posture (note: the
  `npa(plugins=...)` slot path passes fixed config and does not read
  registry.security);
- `safe(level="high")`'s effect on plugins: audit block, permission declarations
  enforced, trusted signatures enforced (unsigned / untrusted rejected);
- trust mechanism: `python -m norpagent plugin-sign --gen` generates a key pair;
  `plugin-sign my_plugin.py --key <private key hex>` generates a signature; after
  adding the public key to `plugin_trusted_keys`, that plugin is trusted → the audit
  relaxes to warn (import restrictions follow the config, unaffected by trust);
- network access is adjudicated by the host's `plugin_network_policy` (default
  deny); plugins cannot bypass it — the policy executes in the host process (10.6);
- approval: plugin tools go through the `approval_enabled` master switch by default;
  `{"approval": "none", "risk": "L0"}` in the plugin's `APPROVAL_HINTS` exempts a
  single tool; undeclared tools follow the master switch (backward compatible).

### 11.9 Config-Key Reference and Lifecycle

```python
config = {
    "plugin_security_audit": "warn",            # off / warn / block
    "plugin_security_import_restrict": "off",   # off / safe / strict
    "plugin_security_require_permissions": False,
    "plugin_signature_verify": True,
    "plugin_signature_required": False,         # True: only trusted loads
    "plugin_trusted_keys": ["<public key hex>"],
    "plugin_network_policy": "deny",            # deny/audited_public/public_only/allow_all
    "plugin_network_url_allowlist": ["https://api.example.com/"],
    "plugin_network_domain_allowlist": ["api.example.com"],
    "approval_enabled": True,                   # plugin-tool approval master switch
    "plugin_isolation": "auto",                 # auto / inproc / process
    "plugin_log_dir": "",                       # plugin log dir ("" = ~/.norpagent/plugin_logs)
    "plugin_disabled": [],                      # disabled plugin names (listed, not loaded)
    "plugin_capabilities": None,                # host-side capability master gate (None = unrestricted)
}
```

Lifecycle notes (clean unload / reload semantics since 2026-09-11):

- `ps.load()` is re-callable (clears the manifest first, then rescans);
  `ps.configure()` updates config and invalidates the loader for a rebuild;
- `ps.unload(name)` / `ps.reload(name)` now **fully reclaim**: `on_unload` runs,
  hook subscriptions are really removed, tools are deleted from the table, and
  setup registrations (subscriptions / slots / services / commands / dynamic
  tools / components) are torn down;
- for a full runtime replacement use `npa.remount(plugins=[...])`: the framework
  fully unloads the old loader first, then installs the new directories (no
  stacking, 3.7);
- `ps.shutdown()` / `loader.shutdown()` runs `on_unload` for every plugin and
  releases the process-isolation host subprocesses.

### 11.10 Plugin Capability Surface (v2.1.0 Extension)

Beyond tools and the 29 hooks, a plugin may register, through `setup(api)`:
dynamic tools / custom slots / components / models / sessions / sandboxes /
schedulers / UIs / custom hooks / event subscriptions / services / Web pages /
CLI commands / settings, declaring its surface via `PLUGIN_CAPABILITIES`
(absent = the base set tools / hooks / events). The complete API reference and
examples are in Chapter 33; the CLI offers `norpagent plugins list|run`.

## Chapter 12 Preset Modes

### 12.1 The Six Built-In Modes

| Mode | Purpose | Component combination |
|---|---|---|
| `minimal` | model benchmarks | mock + echo/get_time + memory |
| `standard` | general coding tasks | sqlite + pooled + persistent + fts5 + all built-in tools |
| `longrun` | long-running complex tasks | same as standard; max_steps=512, no time limit, phased planning prompts |
| `ptc` | code-orchestrated tool calls | run_python (sandbox execution) |
| `creative` | custom-mode debugging | mode-file loading (--mode-file) |
| `embedded` | embedded / edge / low-resource (0.9) | pure in-memory components + minimal tool set, **headless frontend by default**, no disk / no network dependencies; the model falls back to mock without credentials. See 14.2 |

```python
npa(preset="standard")
npa(preset="ptc")
npa(preset="embedded")                     # headless by default, pure-API mode
npa(preset=Preset(name="mine", model="mock", tools=["echo"], ...))
```

### 12.2 Custom Presets

```python
from norpagent import Preset

my = Preset(
    name="mine",
    description="custom mode",
    model="mock",
    tools=["echo", "get_time"],
    session="sqlite",
    sandbox="pooled",
    scheduler="simple",
    ui="console",
    mode="single",
    params={"max_steps": 16},
    components={},
)
npa(preset=my)
```

---

## Chapter 13 Command-Line Entry

> This chapter lists every command-line entry and its usage: the main command
> `norpagent` (module entry `python -m norpagent`), the crash-rescue tool
> `norpagent-rescue` (pure standard library), and the equivalence between each
> command and the `npa()` programming entry. The quick version is Appendix G.

### 13.1 The Two Commands

| Command | Purpose | Dependencies | Entry |
|---|---|---|---|
| `norpagent` | Start the agent (REPL / single task / Web UI), load plugins and security policy | full framework | `python -m norpagent` or console_scripts |
| `norpagent-rescue` | Snapshot rollback + human takeover of tools (manual operation when the model is down) | snapshot subcommands: pure stdlib; takeover subcommands lazily import the framework | `python -m norpagent.rescue` or console_scripts |

### 13.2 norpagent Main-Command Options

```bash
# list all built-in preset modes
norpagent --list-modes

# interactive REPL (console frontend; choose a mode with --mode)
norpagent --mode standard

# single task (--prompt skips the REPL)
norpagent --mode ptc --prompt "summarize this repo"

# custom mode file (module-level PRESET variable)
norpagent --mode-file my_mode.py

# Web UI (HTTP + SSE, default port 8787)
norpagent --mode standard --ui web --port 8787

# model and credentials
norpagent --model openai_compat --model-name deepseek-v4-flash \
          --base-url https://api.deepseek.com/v1 --api-key sk-xxx

# external plugins and security
norpagent --mode standard --plugin-dir ./my_plugins
norpagent --mode standard --plugin-isolation process
norpagent --mode standard --safe high              # runtime security policy (zero hook intervention)
norpagent --mode standard --safe high --safe-hooks # hook intervention on as well
norpagent --safe-mode                              # safe mode: minimal kernel only, skip all plugins

# session storage and timeout
norpagent --mode standard --session sqlite --call-timeout 120

# plugin signing
norpagent plugin-sign --gen                        # generate a signing key pair
norpagent plugin-sign my_plugin.py --key <privkey> # sign a plugin file
```

Option quick reference (same source as `norpagent --help`):

| Option | Description | Equivalent npa() argument |
|---|---|---|
| `--list-modes` | list all preset modes | `list_presets()` |
| `--mode / -m` | preset mode name (minimal/standard/ptc/creative or custom) | `preset=...` |
| `--mode-file / -f` | load a mode file (module-level `PRESET`) | `load_preset_file()` |
| `--prompt / -p` | single-task input (skips the REPL) | `submit(text)` |
| `--model` | override the preset model (must be registered) | `model=...` |
| `--model-name` | remote model name (e.g. deepseek-v4-flash) | via `_apply_model_options` |
| `--base-url` | OpenAI-compatible endpoint | same |
| `--api-key` | API key (defaults to env vars) | same |
| `--session` | session backend (memory/sqlite) | `session=...` |
| `--call-timeout` | hard timeout per model call (seconds) | `task_params={"call_timeout": N}` |
| `--ui` | UI adapter (console/web) | `ui=...` |
| `--port` | Web UI port (default 8787) | `config={"web": {"port": N}}` |
| `--plugin-dir` | external plugin directory (repeatable) | `plugins=[...]` |
| `--plugin-isolation` | plugin isolation auto/inproc/process | plugins-slot config |
| `--safe` | security level basic/standard/high | `security=...` |
| `--safe-hooks` | with `--safe`: enable hook intervention | `security={"hooks": True}` |
| `--safe-mode` | safe mode: minimal kernel, skip plugins | `safemode="on"` |
| `plugin-sign` | subcommand: plugin signing tool | — |

The CLI is equivalent to `npa()`: the CLI's internal flow is
"install default components → register presets → apply security → load plugins →
build the runtime"; `--safe-mode` is equivalent to `npa(safemode="on")`.

### 13.3 Console Frontend (REPL) Entry

The console frontend means the interactive mode with `ui=console` (or
`frontend="norpagent.frontends.console:ConsoleFrontend"`):

```bash
# way 1: enter directly from the CLI (REPL is the default)
norpagent --mode standard

# way 2: explicitly use the console frontend in a Python interpreter
#        (sync mode is switched on automatically)
python - <<'PY'
import norpagent as npa
npa(frontend="norpagent.frontends.console:ConsoleFrontend")
# >>> you: hello
# >>> type /exit to quit
PY
```

REPL built-in commands: `/exit` (or `/quit`, `exit()`, Ctrl+C, EOF) quits;
`/help` shows commands; `/modes` lists preset modes; `/tools` lists available
tools; `/reset` starts a new session.

> Note: with the console frontend, `npa()` blocks until the user exits in an
> interactive interpreter — no `npa.stop()` polling loop is needed; the default
> Web frontend still requires `npa.stop()` lifecycle polling (Chapter 6).

### 13.4 Safe Mode and Self-Rescue Hints

On startup or run failure, the CLI prints self-rescue hints (`_print_rescue_hints`):

1. `norpagent --safe-mode`: safe mode (minimal kernel only, all plugin directories
   skipped, WebUI settings file not read) — equivalent to `npa(safemode="on")`;
2. `norpagent-rescue list` / `norpagent-rescue rollback --last-good`:
   crash rescue (pure stdlib), roll back to the last known-good snapshot;
3. restart after the rollback (the rollback target is consumed automatically);
4. model provider down → take over the tools by hand:
   `norpagent-rescue tools / tool-call / manual / serve`.

### 13.5 norpagent-rescue Subcommands

**Snapshot rollback (pure stdlib; usable even when the main program cannot import)**:

```bash
norpagent-rescue list                     # timeline (★ = last known-good snapshot)
norpagent-rescue show <id>                # inspect a snapshot (sensitive keys redacted)
norpagent-rescue rollback <id>            # roll back: write the rollback target + restore WebUI settings
norpagent-rescue rollback --last-good     # one-step rollback to the last known-good snapshot
norpagent-rescue mark-good <id>           # manually mark "known good"
norpagent-rescue prune --keep 50          # keep only the most recent N snapshots
```

**Human takeover (drive the tools by hand when the model is down; the framework must be importable)**:

```bash
norpagent-rescue tools                              # tool inventory (with origin tags)
norpagent-rescue tools --workspace ./ws             # workspace root for file tools
norpagent-rescue tools --tools myapp.tools:create   # add custom tools (module address)
norpagent-rescue tools --plugin-dirs ./my_plugins   # load external plugin tools
norpagent-rescue tool-call echo --args '{"text":"ping"}'
norpagent-rescue tool-call exec_cmd --args '{"command":"git status"}' --timeout 30
norpagent-rescue manual                             # interactive manual console
norpagent-rescue serve --port 8799                  # HTTP API + operator page (127.0.0.1)
norpagent-rescue serve --token my-secret            # optional bearer auth
norpagent-rescue serve --tools t1,t2 --plugin-dirs ./plug1,./plug2
```

Shared options of the four takeover subcommands (tools / tool-call / manual /
serve): `--workspace` (workspace root for file tools), `--tools`
(comma-separated registered tool names or `pkg.mod:attr` module addresses),
`--plugin-dirs` (comma-separated plugin directories), `--context-db` (context
store path, default shared `~/.norpagent/context.db`); `tools` additionally
supports `--sandbox` / `--session` / `--scheduler` backend selection,
`tool-call` additionally supports `--timeout` (hard timeout seconds, default 300),
`serve` additionally supports `--port` / `--host` / `--token`.

Custom tools in detail: 15.6.3 / 24.3.5.

### 13.6 CLI ↔ npa() Equivalence

| Scenario | CLI | Programming entry |
|---|---|---|
| interactive REPL | `norpagent --mode standard` | `npa()` with the console frontend |
| single task | `norpagent --mode ptc --prompt "..."` | `npa(prompt="...")` or `submit(text)` |
| Web UI | `norpagent --mode standard --ui web --port 8787` | `npa()` (default Web frontend) |
| safe mode | `norpagent --safe-mode` | `npa(safemode="on")` |
| security policy | `norpagent --safe high [--safe-hooks]` | `npa(security="high" or {"hooks": True})` |
| external plugins | `norpagent --plugin-dir ./dir` | `npa(plugins=["./dir"])` |
| custom tools (rescue) | `norpagent-rescue ... --tools ...` | `RescueToolEnvironment(tools=[...])` |
| snapshot rollback | `norpagent-rescue rollback <id>` | `npa.rollback(id)` |
| last known-good | `norpagent-rescue rollback --last-good` | semantically equivalent to `npa.rollback("__last_good__")` |

---

