<!-- Split by part from docs/DEVELOPER_MANUAL.EN.md; body is line-for-line identical -->

> **Developer Manual - Part 6: Developer Practice and Registration Flow** | Covers: Chapters 25-26 | [Back to index](../README.md)

---

## Chapter 25 Developer Practice: Modules, Slots, Plugins and Tools

> The first 24 chapters answer "what the framework can do"; this chapter answers
> "how you develop for it": module-by-module development methods (protocol →
> implementation → registration → integration → hot reload), the complete slot
> development contract (including the hot-reload red line: **the values of dict
> key-value pairs must be valid modules**), complete plugin and tool development
> examples, and finally a section back to the architecture and the minimal main
> async-loop core — understand it, and you understand why every extension point
> exists and why hot reload is safe.

### 25.1 Architecture Overview and the Minimal Main Async-Loop Core

#### 25.1.1 The Architecture in One Picture (Quick Overview)

NorpAgent's architecture summary: **everything except the minimal kernel
is a replaceable slot**.

```
Your app: npa() / npa.stop() / npa.nasyncio() / npa.current().submit()
    │
runtime layer runtime/    lifecycle state machine + thread orchestration (NorpEngine)
    │
arch layer arch/          slot table (SLOT_SPECS) + address resolution (address) + assembly (ArchLayer)
    │
loop system loops/        LoopRuntime protocol + default NasyncioLoopRuntime (self-developed nasyncio core)
    │
kernel kernel/            Registry (registry) + EventBus (event bus) + AgentRuntime (agent loop)
    │
protocol layer protocols/ all interface contracts: model / tool / session / sandbox / scheduler / UI / plugin
    │
implementation builtin/   built-in components (absolutely equal in status to third-party components; registered the same way)
```

- **The minimal kernel is only four things**: `ArchLayer` (slot connector),
  `address` (address resolution), `Registry` (registry), `EventBus` (event bus)
  — everything else is a slot (2.3);
- **Dependencies point strictly downward**: upper layers import lower layers;
  lower layers must never depend on upper layers (2.6.1);
- **Four kinds of extension points**: event subscription (Chapter 9) /
  component replacement (Chapter 3) / generic components (2.6.3) / brand-new
  slots (3.8 and 25.10) / external plugins (Chapter 11 and 25.11);
- **Zero-modification red line**: the framework core is never modified; all
  extension goes through slots / hooks / the registry.

#### 25.1.2 The Minimal Main Async-Loop Core: EventLoop Internals

`norpagent.nasyncio.EventLoop` (self-developed, zero asyncio dependency) is the
core of all scheduling. After one `npa()` startup, the engine's
submit → loop submit → worker pool → result path all revolves around the five
structures below:

| Structure | Role |
|---|---|
| `_ready` (deque) | callbacks waiting to run: `call_soon` / expired timers / Task advancement |
| `_scheduled` (timer heap) | timers: `(when, seq, TimerHandle)`, used by `call_later` / `sleep` |
| `_ts_queue` (thread-safe queue) | cross-thread submissions: `call_soon_threadsafe` |
| self-pipe (socketpair) | wakes the loop thread blocked in `selector.select` from other threads |
| `_selector` | listens only for self-pipe readability |

The flow of each `_run_once()` round (this is also the canonical pattern of a
"minimal main async loop"):

```
1. pop expired timers from the heap -> move them to _ready
2. compute the select wait time (ready non-empty: 0; timers pending: wait until
   the earliest expiry; otherwise: wait forever)
3. drain the thread-safe queue once first (fewer spurious wakeups)
4. selector.select(wait) — wake on self-pipe readability or timer expiry
5. drain the self-pipe + thread-safe queue -> merge everything into _ready
6. run _ready by snapshot length (anti-starvation); a callback exception is
   printed and the loop continues — it never breaks the loop
```

**Future / Task trampoline advancement**: `Task._step()` calls `coro.send(None)`;
when the coroutine `yield`s a Future it suspends and registers
`_on_waiter_done`; when the Future completes, the callback re-queues `_step`
into the ready queue to keep advancing — the loop thread never waits on any
coroutine; it only "runs the queued callbacks one by one".

**Cancel propagation**: `Task.cancel()` automatically detects the calling
thread — from the loop thread it goes through `call_soon`, from any other thread
through `call_soon_threadsafe` (writes the self-pipe to wake up immediately),
so **external threads can cancel any task directly** (standard asyncio's
`Task.cancel()` is not thread-safe; this is a key fix of the self-developed
core, see 4.7); cancellation is injected with `coro.throw(CancelledError)` and
the coroutine decides whether to respond or swallow it.

**Three classic pitfalls that were fixed** (detailed in 4.5):

1. cross-thread `Future.add_done_callback` on an already-completed future must
   go through `call_soon_threadsafe` (write the self-pipe), otherwise the loop
   blocks in the selector without a wakeup and the waiter hangs forever;
2. `Future.result()` is thread-safe (no bare waiting without a wakeup);
3. `EventLoop.abort_main()` provides a thread-safe "immediate stop" — it
   injects `CancelledError` into the main task without waiting for the current
   await to finish naturally (detailed in 24.2).

#### 25.1.3 A Teaching-Grade Minimal Event Loop (~40 Lines)

The best way to understand the core is to write a minimal version yourself.
Below is a runnable "minimal main async loop" (isomorphic to the self-developed
core, for illustration only):

```python
# myapp/mini_loop.py -- teaching-purpose minimal event loop (for illustration;
#                       use the library built-in core in production)
import heapq, socket, selectors, time, threading
from collections import deque


class MiniLoop:
    def __init__(self):
        self._ready = deque()          # callbacks ready to run
        self._timers = []              # timer heap [(when, seq, cb)]
        self._seq = 0
        self._sel = selectors.DefaultSelector()
        self._ssock, self._csock = socket.socketpair()
        self._ssock.setblocking(False)
        self._sel.register(self._ssock, selectors.EVENT_READ)

    def call_soon(self, cb, *args):    # from the loop thread
        self._ready.append((cb, args))
        self._wake()

    def call_later(self, delay, cb, *args):   # timer
        self._seq += 1
        heapq.heappush(self._timers, (time.monotonic() + delay,
                                      self._seq, cb, args))

    def call_soon_threadsafe(self, cb, *args):  # cross-thread: write the self-pipe to wake up
        self._ready.append((cb, args))
        self._wake()

    def _wake(self):                   # wake the loop thread blocked in select
        try:
            self._csock.send(b"\0")
        except OSError:
            pass

    def run_forever(self):
        while True:
            # 1. expired timers -> ready
            now = time.monotonic()
            while self._timers and self._timers[0][0] <= now:
                _, _, cb, args = heapq.heappop(self._timers)
                self._ready.append((cb, args))
                now = time.monotonic()
            # 2. select wait duration
            wait = 0.0 if self._ready else (
                max(0.0, self._timers[0][0] - now) if self._timers else None)
            # 3. block until readable (self-pipe or timer expiry)
            try:
                events = self._sel.select(wait)
            except (InterruptedError, OSError):
                events = []
            for _key, _mask in events:
                self._ssock.recv(4096)          # drain the wake-up bytes
            # 4. run ready callbacks by snapshot (anti-starvation)
            n = len(self._ready)
            for _ in range(n):
                cb, args = self._ready.popleft()
                try:
                    cb(*args)
                except Exception:
                    import traceback
                    traceback.print_exc()       # a failing callback must not break the loop


if __name__ == "__main__":
    loop = MiniLoop()
    threading.Thread(target=loop.run_forever, daemon=True).start()
    loop.call_later(0.5, lambda: print("timer fired"))
    loop.call_soon_threadsafe(lambda: print("hello from main thread"))
    time.sleep(1)
    loop.call_soon(loop._ssock.close)
```

The real core adds on top of this: Future / Task (trampoline), cancel
injection, `run_until_complete` / `abort_main`, subprocess wrapping, and
synchronization primitives (Event / Lock / Condition). Master the 40 lines
above and you master the whole skeleton of the "minimal main async-loop core" —
none of the module development in 25.2 ~ 25.11 will require touching it.

#### 25.1.4 The Universal Five Steps of Module Development

No matter which kind of module you develop (tool / model / session / sandbox /
scheduler / frontend / loop / generic component), the flow is exactly the same
(an expanded version of 2.6.4):

1. **Read the protocol**: the interface contracts under `norpagent/protocols/`
   (model / tool / session / sandbox / scheduler / UI / plugin), and confirm the
   protocol and data classes to implement;
2. **Write the implementation**: create a new module that depends only on
   protocols and the standard library (follow the style under `builtin/`;
   built-in components and third-party components are absolutely equal);
3. **Register**: `reg.register_*(...)` (Registry API table in 25.2.5) or
   `registry.register_component(kind, name, factory)`;
4. **Declare it for use**: declare it in a preset (`session="my_impl"`), or at
   startup `npa(session="my_impl")` / an address string
   `npa(session="myapp.sessions:create")`;
5. **Wire hooks** (optional): publish / subscribe events through the registry
   inside the implementation (Chapter 9).

Hot reload is the natural extension of step 4: `npa.remount(session=
"myapp.sessions:create")` re-resolves the address at runtime and **first
invalidates the module cache and .pyc files** (3.7; see 25.2.6), so "edit the implementation
code → remount" hot-updates it without restarting the process.

---

### 25.2 Tool Development in Detail (Key Section)

Tools are the Agent's "skills": the model decides **whether** to call them, you
decide **how** they execute. Developing tools is the most frequent and most
rewarding way to extend NorpAgent.

#### 25.2.1 Protocol and Data Classes

```python
# norpagent/protocols/tool.py
class Tool(Protocol):
    name: str                                        # unique tool name (what the model calls)
    def schema(self) -> dict: ...                    # OpenAI function schema
    def run(self, args: dict, ctx: RunContext) -> ToolResult: ...

@dataclass
class ToolResult:
    output: str = ""                                 # text fed back to the model
    success: bool = True
    error: str = ""
```

Key points:

- `schema()` returns the OpenAI function format
  (`type/function/name/description/parameters`) — this is the world the model
  sees, so **how well you write the description directly determines whether the
  model calls correctly**;
- `args` of `run()` is the JSON argument generated by the model according to
  the schema (already parsed into a dict);
- return a `ToolResult`: on success fill `output`; on failure set
  `success=False` and fill `error` (the model sees a `[tool execution failed]`
  prefix);
- you may raise an exception — the kernel catches it and converts it into a
  unified failed ToolResult (`tool_error`) — but **explicitly returning a failed
  result is more controllable**.

#### 25.2.2 Complete Example: A "Weather Query" Tool from Scratch

```python
# myapp/weather_tool.py -- your own tool module
from __future__ import annotations

import json
from typing import Any, Dict
from urllib.request import urlopen

from norpagent.protocols.tool import Tool, ToolResult


class WeatherTool:
    name = "weather"

    def __init__(self, api_key: str = "", base_url: str = "https://wttr.in"):
        self._api_key = api_key          # constructor param: injectable via the address clause ;api_key=...
        self._base_url = base_url

    def schema(self) -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": "Query the current weather of a city. The city may be given in Chinese or pinyin.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "city": {"type": "string", "description": "city name, e.g. Beijing / Shanghai"},
                    },
                    "required": ["city"],
                    "additionalProperties": False,
                },
            },
        }

    def run(self, args: Dict[str, Any], ctx: Any) -> ToolResult:
        city = str(args.get("city", "")).strip()
        if not city:
            return ToolResult(output="missing city parameter", success=False, error="city is required")
        try:
            with urlopen(f"{self._base_url}/{city}?format=j1", timeout=10) as resp:
                data = json.load(resp)
            cur = data["current_condition"][0]
            return ToolResult(output=(
                f"{city} now {cur['temp_C']} C, "
                f"feels like {cur['FeelsLikeC']} C, {cur['weatherDesc'][0]['value']}"
            ))
        except Exception as exc:
            return ToolResult(output=f"query failed: {exc}", success=False, error=str(exc))


def create(**kw):                        # module-level factory: address "myapp.weather_tool" auto-resolves to it
    return WeatherTool(**kw)
```

#### 25.2.3 RunContext: What a Tool Can Access

`ctx` of `run(args, ctx)` is a `RunContext` (`norpagent.kernel.context`) — the
entire environment of one task execution:

| Field | Description |
|---|---|
| `ctx.registry` | component registry (resolve other tools / models: `reg.resolve_tool(name)`) |
| `ctx.session_manager` / `ctx.session_id` | session read/write (cross-turn memory) |
| `ctx.sandbox` | the current task's sandbox (`run_shell` / `run_python`, isolated execution) |
| `ctx.scheduler` | task scheduler (submit subtasks; the multi-agent collaboration entry) |
| `ctx.ui` | UI adapter (`ctx.ask_user(...)` human interaction / approval) |
| `ctx.params` | merged result of preset params and task-level params (`max_steps` / `task_timeout` / custom keys) |
| `ctx.components` | generic component instances declared in the preset (`{kind: instance}`) |
| `ctx.component("context_store")` | get a generic component by kind (context store / project manager, etc.) |
| `ctx.task_id` / `ctx.preset_name` | task metadata |

```python
# idiomatic way to use a component inside a tool
store = ctx.component("context_store")     # None if absent; fall back yourself
if store is not None:
    store.add(ctx.session_id, chunk, meta={"tool": self.name})
```

#### 25.2.4 Cancellation Cooperation (Mandatory for Long Tasks)

A task may be cancelled by Ctrl+C / `engine.request_stop()` / timeout. The
built-in cancellation signal is injected through contextvars and can be checked
anywhere inside a tool (4.6.2):

```python
from norpagent.loops.cancel import cancel_requested

def run(self, args, ctx):
    for chunk in self._fetch_stream(args["url"]):
        if cancel_requested():            # engine stopped / cancelled -> True
            return ToolResult(output="task cancelled", success=False)
        self._write(chunk)
    return ToolResult(output="done")
```

A long tool that never checks cancellation will occupy the daemon worker pool
(boundary in 4.6.4) — always check on **streaming / loop / chunked** paths.

#### 25.2.5 The Four Ways to Register and Integrate

| Way | Form | Scenario |
|---|---|---|
| Registry entry | `reg.register_tool("weather", WeatherTool())` | programmatic assembly; other components can reference it by name |
| Instance list | `npa(tools=[WeatherTool(), MyTool()])` | ready at startup |
| Name mapping | `npa(tools={"weather": WeatherTool(api_key="x")})` | ready at startup (key = tool name) |
| Address mapping | `npa(tools={"weather": "myapp.weather_tool:create"})` | ready at startup + hot-reloadable |

`npa(tools=["weather"])` references a **registered name**; the value of an
address mapping `"myapp.weather_tool:create"` is a **module address**, resolved
into a factory at assembly time and called per the factory convention (3.4: the
`;api_key=xxx` clause injects the factory's `config`):

```python
npa(tools={"weather": "myapp.weather_tool:create;api_key=MY_KEY"})
# equivalent to WeatherTool(api_key="MY_KEY")
```

The complete set of Registry registration APIs (`norpagent.kernel.registry`):

| API | Description |
|---|---|
| `register_tool(name, tool)` / `resolve_tool(name)` / `list_tools()` | tools |
| `register_model(name, provider)` / `resolve_model(name)` | models |
| `register_session(name, factory)` / `build_session(name)` | sessions (factory) |
| `register_sandbox(name, factory)` / `build_sandbox(name)` | sandboxes (factory) |
| `register_scheduler(name, factory)` / `build_scheduler(name)` | schedulers (factory) |
| `register_ui(name, adapter)` / `resolve_ui(name)` | UI renderers |
| `register_component(kind, name, factory)` / `build_component(kind, name)` | generic components (any kind) |
| `register_preset(preset)` / `resolve_preset(name)` | presets |

#### 25.2.6 Hot-Reloading Tools: Dict Key-Value Values Must Be Valid Modules (Red Line)

The tool set is a **component slot**; `npa.remount(tools=...)` takes effect at
the next `run()` (the agent loop re-resolves tool schemas on every run). All
three forms can be **hot-mounted (remounted)**; note, however, that
**hot-reloading edited code (picking up the new code on disk) only works with a
bare string address** — see below.

```python
npa.remount(tools=["echo", "weather"])                    # registered-name list
npa.remount(tools={"weather": WeatherTool(api_key="new key")})  # instance mapping
npa.remount(tools={"weather": "myapp.weather_tool:create"})   # address mapping (recommended)
```

**Red line: at hot reload the value of a dict key-value pair must be a valid
module.** For dict-form values of the tools mapping, and of any slot (hooks
mapping, custom-slot dict values, nested dicts recursively), if a string
**looks like a pure address** (dotted identifier containing `.` or `:`,
detected by `norpagent.arch.address.is_address_like`), the assembler resolves
it as an address:

- value = **registered name** (e.g. `"echo"`) → kept verbatim as a name
  reference;
- value = **valid module address** (e.g. `"myapp.weather_tool:create"`) → load
  the module, take the attribute, call it per the factory convention;
- value = **valid instance / factory object** → used as-is;
- value = **address-like but unresolvable** (module missing / attribute missing
  / syntax error) → raises `AddressError` (`AddressError(ImportError)`);
  **the hot reload fails; no silent fallback, no partial effect**.

```python
# wrong: module name misspelled / attribute missing -> AddressError, remount raises
npa.remount(tools={"weather": "myapp.weather_toll:create"})   # typo
npa.remount(tools={"weather": "myapp.weather_tool:WeatherTool"})  # class not instantiated? -> callable is called as a factory (legal)
npa.remount(tools={"weather": "myapp.not_exist:create"})      # module does not exist

# correct: choose one of three
npa.remount(tools={"weather": "myapp.weather_tool:create"})   # address (module importable)
npa.remount(tools={"weather": "weather"})                     # registered name (registered via register_tool)
npa.remount(tools={"weather": WeatherTool()})                 # instance
```

Why "if you wrote an address it should raise": hot reload is an ops action; a
silently falling-back address would quietly leave the old / an empty
implementation running online, which is much harder to debug than an explicit
failure. Therefore the assembler strictly resolves every "address-like string"
(item 3 of 3.3; the original comment in `layer.py` `_resolve_dict_values`:
"if you wrote an address it must raise explicitly, never fall back
silently"). **Strings that are not address-like (e.g. `"high"`, `"./dir"`)
are unaffected and keep their literal semantics**.

Another hot-reload detail (**the easiest trap to fall into**): **only the
"bare string address" form triggers module-cache invalidation**. The check in
`remount` is `if isinstance(value, str): self._invalidate_address_module(value)`
(`layer.py` L243) — it **looks only at whether the outermost value is a
string**; it neither recurses into dict values nor iterates list elements.
Comparison across forms:

| Form passed in | Cache invalidated | Hot reload after editing code |
|---|---|---|
| `tools="myapp.weather_tool:create"` (bare string address) | yes | **yes** |
| `tools={"weather": "myapp.weather_tool:create"}` (dict, value is an address) | no | **no** (hits the old module in `sys.modules`) |
| `tools=["myapp.weather_tool:create"]` (list element is an address) | no | **no** |
| `tools={"weather": WeatherTool()}` (instance) / `tools="weather"` (registered name) | no | no (no address to invalidate) |

So when "editing `myapp/weather_tool.py` → wanting to hot-update the code",
**you must use a bare string address**:

```python
# correct: triggers cache invalidation, picks up the new code on disk
npa.remount(tools="myapp.weather_tool:create")

# counter-example: mounts fine and raises nothing, but hits the old module in
# sys.modules, so the edited code does not take effect
npa.remount(tools={"weather": "myapp.weather_tool:create"})
```

`_invalidate_address_module` does two-step invalidation: deletes the .pyc
corresponding to `__cached__` and pops the `sys.modules` entry, so the next
resolution re-imports from disk (3.7). Note it only handles the module name in
the address (the `;` sub-config and `:attr` are not part of the module path).

**Submodules are not invalidated**: the invalidation step pops only the
**exact module name** in the address (`sys.modules.pop(module_name, None)`,
`layer.py` L288); it does not recurse into submodules. If the address points
to a **package** while the implementation lives in an **already-imported
submodule**, editing the submodule file and remounting will not reload it —
point the address directly at the leaf module (e.g. `pkg.impl:create`, not
`pkg:create`).

Debugging tip: on a failed hot reload check the assembly manifest of
`eng.layer.describe()` (3.5) and `reg.list_tools()` to confirm the name was
really registered.

---

### 25.3 Model Development in Detail

The model is the Agent's reasoning core. Integrating any model (local / cloud /
private protocol) only requires implementing `ModelProvider`
(`norpagent.protocols.model`).

#### 25.3.1 Protocol

```python
class ModelProvider(Protocol):
    model_id: str
    def generate(self, messages, tools, params) -> ModelOutput: ...
    def stream(self, messages, tools, params) -> Iterator[ModelStreamChunk]: ...  # optional
```

- `messages`: `List[ChatMessage]` (role: system / user / assistant / tool;
  tool turns carry `tool_calls` / `tool_call_id`);
- `tools`: a list of OpenAI function schemas (None when no tools);
- `params`: runtime parameter dict (temperature / max_tokens / top_p / custom
  keys), freely usable by the implementation;
- `ModelOutput`: `content` / `reasoning` (chain of thought) / `tool_calls` /
  `usage` (`ModelUsage`) / `finish_reason`;
- `ModelStreamChunk`: streaming deltas `delta_content` / `reasoning` /
  `tool_call_delta` / `usage` / `finish_reason`.

**If `stream` is implemented, the kernel prefers the streaming path** (broadcasting
`on_content` chunk by chunk); otherwise it falls back to one-shot `generate`.
Implementing both is recommended.

#### 25.3.2 Complete Example: An HTTP JSON Model Adapter

```python
# myapp/models/http_json.py -- any HTTP JSON protocol model
from __future__ import annotations

import json
from typing import Any, Dict, Iterator, List, Optional
from urllib.request import Request, urlopen

from norpagent.protocols.model import (
    ChatMessage, ModelOutput, ModelProvider, ModelStreamChunk,
    ModelUsage, ToolCallSpec,
)


class HttpJsonModel:
    model_id = "http-json"

    def __init__(self, endpoint: str, api_key: str = "", **kw):
        self._endpoint = endpoint
        self._api_key = api_key

    def _payload(self, messages, tools, params):
        body = {
            "messages": [m.to_openai() for m in messages],
            "temperature": params.get("temperature", 0.7),
        }
        if tools:
            body["tools"] = tools
        return body

    def _post(self, body, timeout=60.0):
        req = Request(self._endpoint, data=json.dumps(body).encode("utf-8"),
                      headers={"Content-Type": "application/json"})
        if self._api_key:
            req.add_header("Authorization", f"Bearer {self._api_key}")
        with urlopen(req, timeout=timeout) as resp:
            return json.load(resp)

    def generate(self, messages, tools, params) -> ModelOutput:
        data = self._post(self._payload(messages, tools, params))
        msg = data["choices"][0]["message"]
        tool_calls = None
        if msg.get("tool_calls"):
            tool_calls = [
                ToolCallSpec(id=tc["id"], name=tc["function"]["name"],
                             arguments=json.loads(tc["function"]["arguments"] or "{}"))
                for tc in msg["tool_calls"]
            ]
        usage = data.get("usage")
        return ModelOutput(
            content=msg.get("content") or "",
            tool_calls=tool_calls,
            usage=ModelUsage(
                input_tokens=usage.get("prompt_tokens", 0),
                output_tokens=usage.get("completion_tokens", 0),
                total_tokens=usage.get("total_tokens", 0),
            ) if usage else None,
            finish_reason=data["choices"][0].get("finish_reason", "stop"),
        )

    def stream(self, messages, tools, params) -> Iterator[ModelStreamChunk]:
        # optional streaming implementation; check the cancel event per chunk (below)
        from norpagent.loops.cancel import cancel_requested
        body = self._payload(messages, tools, params)
        body["stream"] = True
        with urlopen(Request(self._endpoint,
                             data=json.dumps(body).encode("utf-8"),
                             headers={"Content-Type": "application/json"}),
                     timeout=120.0) as resp:
            for line in resp:
                if cancel_requested():           # engine stop / Ctrl+C: exit as early as possible
                    return
                line = line.decode("utf-8").strip()
                if not line.startswith("data:"):
                    continue
                chunk = json.loads(line[5:])
                delta = chunk["choices"][0].get("delta", {})
                yield ModelStreamChunk(delta_content=delta.get("content") or "")
```

#### 25.3.3 Registration, Credential Fallback and Hot Reload

```python
# programmatic registration
reg.register_model("my_http", HttpJsonModel(endpoint="http://127.0.0.1:8000/v1"))

# npa() integration: name / address / instance, choose one
npa(model="my_http")
npa(model="myapp.models.http_json:create;endpoint=http://127.0.0.1:8000/v1")
npa(model=HttpJsonModel(endpoint="..."))

# hot reload: swap model / config / code (the bare string address form invalidates the module cache)
npa.remount(model="myapp.models.http_json:create;endpoint=http://127.0.0.1:9000/v1")
```

Notes:

- **Credential fallback**: when the assembly layer finds no key at all
  (`OPENAI_API_KEY` / `DEEPSEEK_API_KEY` / `ANTHROPIC_API_KEY` /
  `DASHSCOPE_API_KEY` / `NORPAGENT_API_KEY`) it automatically falls back to
  `mock` (21.1) — custom models should likewise give a readable error instead
  of a bare raise when credentials are missing;
- **Cancellation**: `params["_cancel_event"]` is the cancel event injected by
  the kernel (also injected when `call_timeout=0`); check it per chunk in
  streaming loops (4.6.2);
- **DeepSeek V4 special case**: in tool turns, the assistant message's
  `reasoning_content` must be echoed back verbatim (even an empty string);
  `ChatMessage.to_openai()` already handles it (21.1);
- The model slot is a **component slot** (`name_or_address` semantics); a hot
  reload takes effect at the next run().

---

### 25.4 Session Development in Detail

Sessions are the Agent's "memory": persistence and retrieval of conversation
history. Implementing `SessionManager` (`norpagent.protocols.session`) lets you
plug in any backend (file / database / cloud sync).

#### 25.4.1 Protocol and Complete Example

```python
class SessionManager(Protocol):
    def create_session(self, title: str = "") -> Session: ...
    def get_session(self, session_id: str) -> Optional[Session]: ...
    def append_message(self, session_id: str, message: ChatMessage) -> bool: ...
    def history(self, session_id: str) -> List[ChatMessage]: ...
    def list_sessions(self) -> List[Session]: ...
    def delete_session(self, session_id: str) -> bool: ...
```

```python
# myapp/sessions/jsonfile.py -- JSON file session storage
import json, os, threading, time
from norpagent.protocols.session import Session, SessionManager
from norpagent.protocols.model import ChatMessage


class JsonFileSessions:
    """One .json file per session. All methods are thread-safe (lock-protected)."""

    def __init__(self, root: str = "./sessions", **kw):
        self._root = root
        self._lock = threading.RLock()
        os.makedirs(root, exist_ok=True)

    def _path(self, sid):
        return os.path.join(self._root, f"{sid}.json")

    def create_session(self, title=""):
        s = Session(id=f"s{int(time.time() * 1000)}", title=title,
                    created_at=time.time())
        with self._lock:
            with open(self._path(s.id), "w", encoding="utf-8") as f:
                json.dump({"title": title, "messages": []}, f, ensure_ascii=False)
        return s

    def get_session(self, session_id):
        with self._lock:
            p = self._path(session_id)
            if not os.path.exists(p):
                return None
            data = json.load(open(p, encoding="utf-8"))
            return Session(id=session_id, title=data.get("title", ""),
                           created_at=os.path.getmtime(p),
                           messages=[ChatMessage(**m) for m in data["messages"]])

    def append_message(self, session_id, message):
        with self._lock:
            p = self._path(session_id)
            if not os.path.exists(p):
                return False
            data = json.load(open(p, encoding="utf-8"))
            data["messages"].append({
                "role": message.role, "content": message.content,
                "tool_call_id": message.tool_call_id,
            })
            with open(p, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False)
            return True

    def history(self, session_id):
        s = self.get_session(session_id)
        return list(s.messages) if s else []

    def list_sessions(self):
        with self._lock:
            return [self.get_session(fn[:-5]) for fn in os.listdir(self._root)
                    if fn.endswith(".json")]

    def delete_session(self, session_id):
        with self._lock:
            p = self._path(session_id)
            if os.path.exists(p):
                os.remove(p)
                return True
            return False


def create(config=None, **kw):       # module-level factory
    root = (config or {}).get("root", "./sessions")
    return JsonFileSessions(root=root)
```

#### 25.4.2 Registration and Hot-Reload Semantics

```python
reg.register_session("jsonfile", lambda: JsonFileSessions(root="./sessions"))
npa(session="jsonfile")                                   # name
npa(session="myapp.sessions.jsonfile:create;root=./data")  # address
npa.remount(session="myapp.sessions.jsonfile:create;root=./data")  # hot reload

# continue a conversation across sessions via session_id
r1 = eng.submit("Remember: my favorite color is blue")
r2 = eng.submit("What is my favorite color?", session_id=r1.session_id)
```

**Hot-reload semantics differ from tools**: sessions are **assembly slots**;
`remount` goes through "AgentRuntime hot rebuild" — stop the old runtime →
build a new runtime per the current assembly → rebind the frontend renderer
(grouping table in 3.7). In-flight tasks during the rebuild race with the
rebuild; in production drain first, then swap (the "two-phase hot mount"
recommendation in 3.7). Note: swapping the session implementation does not
auto-migrate history — the old and new implementations each manage their own
storage; continuing across implementations requires migrating the data yourself.

---

### 25.5 Sandbox Development in Detail

A sandbox is the Agent's "isolated execution environment": `exec_cmd` /
`run_python` and other tools execute through the sandbox protocol; swapping the
sandbox implementation (container / remote / VM) **requires no changes to any
tool code**.

#### 25.5.1 Protocol

```python
class Sandbox(Protocol):                       # one created sandbox instance
    def run_shell(self, command, timeout=60.0, cwd=None, env=None) -> SandboxResult: ...
    def close(self) -> None: ...

class PythonSandbox(Protocol):                 # optional capability: isolated Python execution
    def run_python(self, code, tool_dispatch, timeout=60.0) -> SandboxResult: ...

class SandboxProvider(Protocol):               # provider: creates sandbox instances on demand
    kind: str
    def create(self) -> Sandbox: ...

class SandboxResult:                           # execution result
    stdout: str; stderr: str; exit_code: int; timed_out: bool
    # ok = exit_code == 0 and not timed_out
```

#### 25.5.2 Complete Example: A Docker Sandbox

```python
# myapp/sandboxes/docker_sb.py -- Docker container sandbox (illustrative)
import subprocess
from norpagent.protocols.sandbox import Sandbox, SandboxProvider, SandboxResult


class DockerSandbox:
    def __init__(self, image: str = "python:3.11-slim", **kw):
        self._image = image

    def run_shell(self, command, timeout=60.0, cwd=None, env=None):
        try:
            proc = subprocess.run(
                ["docker", "run", "--rm", "-i", self._image, "sh", "-c", command],
                capture_output=True, text=True, timeout=timeout,
            )
            return SandboxResult(stdout=proc.stdout, stderr=proc.stderr,
                                 exit_code=proc.returncode)
        except subprocess.TimeoutExpired:
            return SandboxResult(stderr="timeout", exit_code=-1, timed_out=True)
        except FileNotFoundError:
            return SandboxResult(stderr="docker not found", exit_code=-1)

    def close(self):
        pass                                        # docker run --rm cleans up automatically


class DockerSandboxProvider:
    kind = "docker"

    def __init__(self, image="python:3.11-slim", **kw):
        self._image = image

    def create(self):
        return DockerSandbox(image=self._image)


def create(config=None, **kw):
    return DockerSandboxProvider(image=(config or {}).get("image", "python:3.11-slim"))
```

```python
reg.register_sandbox("docker", lambda: DockerSandboxProvider(image="python:3.11"))
npa(sandbox="docker")
npa(sandbox="myapp.sandboxes.docker_sb:create;image=python:3.12-slim")
npa.remount(sandbox="myapp.sandboxes.docker_sb:create;image=python:3.12-slim")
```

Development key points:

- **Timeout and cancellation**: `run_shell`'s `timeout` must be honored
  (`subprocess.run`'s timeout suffices); when the engine stops, the cancel
  event is set (4.6.2); long tasks should check in slices (the built-in pooled
  sandbox checks every ≤0.5s and force-kills the process tree);
- **Process-tree cleanup**: the child process tree of `sh -c` must be killed
  together on timeout (on Windows use `taskkill /T`, see 21.4);
- **`close` must be idempotent**: a sandbox may be closed from multiple places
  — `shutdown` / hot rebuild / task end.

---

### 25.6 Scheduler Development in Detail

A scheduler is the Agent's "orchestration": task queueing, execution order,
concurrency policy. Tools such as `task_submit` / `task_list` and multi-agent
orchestration are all built on top of it.

#### 25.6.1 Protocol and Complete Example

```python
class TaskScheduler(Protocol):
    def submit(self, task: AgentTask) -> str: ...           # enqueue; returns the task id
    def pending(self) -> int: ...                           # number of pending tasks
    def drain(self, run_task) -> List[TaskResult]: ...      # execute all pending tasks in order
```

```python
# myapp/schedulers/priority.py -- priority scheduler (smaller number runs first)
import heapq
from norpagent.protocols.scheduler import AgentTask, TaskScheduler


class PriorityScheduler:
    def __init__(self, **kw):
        self._heap = []                       # [(priority, seq, task)]

    def submit(self, task):
        priority = int(task.params.get("priority", 0))   # priority comes from the task params
        heapq.heappush(self._heap, (priority, id(task), task))
        return task.id

    def pending(self):
        return len(self._heap)

    def drain(self, run_task):
        results = []
        while self._heap:
            _p, _seq, task = heapq.heappop(self._heap)
            results.append(run_task(task))    # run_task is injected by the runtime
        return results


def create(**kw):
    return PriorityScheduler()
```

```python
reg.register_scheduler("priority", lambda: PriorityScheduler())
npa(scheduler="priority")
npa.remount(scheduler="myapp.schedulers.priority:create")
```

Key point: `drain`'s `run_task` callback is injected by the runtime (decoupling
the agent loop from the scheduler; with multi-agent it can point to a different
agent). The built-in `persistent` implementation (21.5) resumes after a crash
via `resume()`; a custom scheduler can follow it.

---

### 25.7 Frontend and Renderer Development in Detail

The frontend is a two-layer structure (5.1): **frontend** (input/output shell,
Frontend protocol) + **ui** (event renderer, UIAdapter protocol).

#### 25.7.1 Protocol

```python
class Frontend(Protocol):              # user interaction shell
    frontend_id: str
    def attach(self, engine) -> None: ...   # bind the engine: engine.submit / request_stop
    def start(self) -> None: ...            # start (usually spawns a background thread)
    def stop(self) -> None: ...             # stop (thread-safe)
    def is_alive(self) -> bool: ...

class UIAdapter(Protocol):             # event renderer
    ui_id: str
    def on_event(self, event) -> None: ...  # render one AgentEvent
    def ask_user(self, question, default="") -> str: ...
    def notify(self, message, level="info") -> None: ...
```

#### 25.7.2 Complete Example: A Toast-Notification Frontend (Simplified)

```python
# myapp/frontends/toast.py -- no input, notifications only (good for desktop assistants)
import threading
from norpagent.frontends.base import Frontend


class ToastFrontend:
    frontend_id = "toast"

    def __init__(self, **kw):
        self._engine = None
        self._stop = threading.Event()

    def attach(self, engine):
        self._engine = engine
        # subscribe to the event bus: only care about final results
        engine.registry.bus.subscribe("on_task_done", self._on_done)

    def _on_done(self, event):
        result = event.get("result")
        if result is not None:
            print(f"[notice] task done: {result.final_content[:80]}")

    def start(self):
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        while not self._stop.wait(0.2):
            pass

    def stop(self):
        self._stop.set()

    def is_alive(self):
        return not self._stop.is_set()


def create(**kw):
    return ToastFrontend()
```

```python
npa(frontend="myapp.frontends.toast:create")
# or runtime hot replacement (infrastructure slot: stop the old, start the new; on failure roll back to the old)
npa.remount(frontend="myapp.frontends.toast:create")
```

Key point: the frontend **does not render directly** — rendering is the job of
the ui renderer (`npa(ui=...)`); the frontend is responsible for "read input →
submit, receive events → hand them to the renderer". The built-in Web frontend
and WebUI renderer are the reference implementation (Chapter 22).

---

### 25.8 Event-Loop Development in Detail

The event loop decides how tasks are scheduled: thread model, interruption
method, wakeup method. The default `NasyncioLoopRuntime` covers most scenarios;
special scenarios (embedded, tests, custom scheduling) can replace it by
implementing the `LoopRuntime` protocol (4.2).

```python
class LoopRuntime(Protocol):
    name: str
    def start(self) -> None: ...
    def stop(self) -> None: ...
    def is_running(self) -> bool: ...
    def join(self, timeout=None) -> None: ...
    def submit(self, fn, *args, **kwargs) -> Any: ...   # run in the loop context and block for the result
```

```python
# myapp/loops/sync_loop.py -- synchronous direct-run loop (tests / embedded)
class SyncLoop:
    name = "sync"

    def __init__(self, **kw):
        self._running = False

    def start(self):
        self._running = True

    def stop(self):
        self._running = False

    def is_running(self):
        return self._running

    def join(self, timeout=None):
        pass

    def submit(self, fn, *args, **kwargs):
        return fn(*args, **kwargs)          # execute synchronously, directly


def create(**kw):
    return SyncLoop()
```

```python
npa(async_loop="myapp.loops.sync_loop")          # address (auto-resolves the module-level create)
npa(async_loop=SyncLoop())                        # instance
npa.remount(async_loop="myapp.loops.sync_loop")   # hot reload (stop the old, start the new)
```

Development key points (engineering lessons from 4.5 / 4.6):

- `submit` is a **blocking** contract: the engine waits for the result on the
  calling thread; the implementation must honor that;
- long tasks go on the **daemon thread pool**, never the loop thread (a stuck
  loop thread = all scheduling paralyzed);
- implement the cancel signal (checkable via `cancel_requested`) and Ctrl+C
  polling wait (the main thread is not at the loop entry, see 4.6.1);
- when replacing the loop, in-flight tasks are abandoned (grouping table in
  3.7); replace when there are no tasks.

---

### 25.9 Generic Component Development in Detail

"Extra capability" modules (context store, project manager, task storage,
vector store...) do not use dedicated slots; they use the **open component
namespace** (2.6.3): `kind` is the category (arbitrarily extensible), `name`
is the component name, `factory` is the factory.

#### 25.9.1 Registration and Usage

```python
# myapp/components/redis_store.py -- example: Redis context store
class RedisContextStore:
    def __init__(self, host="127.0.0.1", port=6379, **kw):
        self._host, self._port = host, port

    def add(self, session_id, text, meta=None):
        ...                                            # implement add / search / list / delete

    def search(self, query, limit=10):
        ...

    def close(self):
        ...


def create(config=None, **kw):
    return RedisContextStore(host=(config or {}).get("host", "127.0.0.1"))
```

```python
# registration (kind context_store already has the built-in fts5; add a redis implementation)
reg.register_component("context_store", "redis",
                       lambda: RedisContextStore(host="127.0.0.1"))

# npa() integration (context_store slot: address / name_or_address semantics)
npa(context_store="redis")
npa(context_store="myapp.components.redis_store:create;host=10.0.0.5")

# custom new kind: any kind can be registered; declare the reference in a preset
reg.register_component("vector_store", "pg", lambda: PgVectorStore())
Preset(name="mine", components={"context_store": "redis",
                                "vector_store": "pg"})
```

Usage from the tool side:

```python
store = ctx.component("vector_store")          # get by kind; None if absent
```

#### 25.9.2 Hot Reload and Factory Injection

- `context_store` / `project_manager` are **assembly slots**: `remount` hot
  rebuilds the AgentRuntime (grouping table in 3.7);
- a factory declaring a `workspace_root` parameter (or **kwargs) gets the
  workspace root injected automatically (2.6.3);
- custom slots can also register generic components (the `vector_store` slot
  example in 3.8; the full version in 25.10.4).

---

### 25.10 Slot Development in Detail (Key Section)

25.2 ~ 25.9 develop "implementations of slots"; this section develops **the
slot itself** — registering a brand-new slot name that gets the exact same full
pipeline as the 18 built-in slots (`npa()` argument validation, ArchLayer
assembly, `npa.remount()` hot replacement, `layer.describe()` manifest). 3.8
gives the contract overview; this section gives the full development flow.

#### 25.10.1 The Essence of a Slot

A slot = **name + string semantics + application logic (applier)**:

- `name`: the slot name, i.e. the keyword-argument name of `npa()` (must be a
  valid Python identifier);
- `string_semantics`: how string values are interpreted — `address` (module
  address) / `name` (registry component name) / `name_or_address` (name first,
  then address) / `literal` (literal value, address preferred) (3.3);
- `applier(reg, layer, value, params, ctx)`: called by the assembler when the
  slot value is non-empty, to "apply" the value to the system (register a
  component / subscribe hooks / write extras).

#### 25.10.2 All SlotSpec Fields

| Field | Type | Description |
|---|---|---|
| `name` | str | slot name (required) |
| `description` | str | description (visible in the `layer.describe()` manifest) |
| `protocol` | str | protocol description (human-readable) |
| `default_address` | Optional[str] | default implementation address (used when the slot is not filled) |
| `string_semantics` | str | `address` / `name` / `name_or_address` / `literal` |
| `factory_kwargs` | Dict[str, str] | extra factory keys (injected call context) |
| `examples` | List[str] | examples (for docs / hints) |
| `defer_factory` | bool | defer factory creation to the engine assembly phase (used by agent_runtime) |
| `applier` | callable | application logic (called when the slot value is non-empty) |
| `remount_rebuild_agent` | bool | whether to hot-rebuild the AgentRuntime after hot replacement |

#### 25.10.3 The Applier Contract and Reentrancy Safety

`applier` is the "assembly function" of a custom slot — when the slot value is
non-empty, the assembler calls it to apply the value to the system. **Must-read
for beginners**: the applier's job is one sentence — "register the value the
user gave to this slot where the registry / preset / engine can consume it".

```python
def applier(reg, layer, value, params, ctx):
    # reg   : the assembled registry (a Registry instance)
    # layer : the architecture layer (an ArchLayer instance; layer.subconfig(slot)
    #         reads the ";key=value" sub-config)
    # value : the resolved slot value (see the table below)
    # params: engine assembly parameters (the raw launch kwargs)
    # ctx   : four mutable containers (see the table below); the applier writes
    #         its results into them
    ...
```

The shape of `value` is decided by `string_semantics`:

| string_semantics | shape of value | example value |
|---|---|---|
| `address` | an instantiated implementation (`;k=v` sub-clause via `layer.subconfig(slot)`) | `MyStore()` |
| `name` / `name_or_address` | the raw string (a registered component name) | `"fts5"` |
| `literal` | the raw value; address-like strings are already resolved | `"high"` / `MyKit()` |

The four mutable containers of `ctx` (write = take effect):

| Container | Purpose | Consumer |
|---|---|---|
| `ctx["components"]` | register generic components `{kind: name}` (must `reg.register_component` first) | AgentRuntime builds `ctx.components`; tools use `ctx.component(kind)` |
| `ctx["extras"]` | engine extra objects (per slot name) | `engine.extras[slot_name]` |
| `ctx["overrides"]` | preset field overrides (final values of `model` / `tools` etc.) | final preset construction |
| `ctx["meta"]` | registry architecture metadata (records **unsubscribable objects**) | cleanup of old subscriptions at hot reload |

**Reentrancy safety is a hard requirement**: the same registry calls the
applier repeatedly (assembly + every `npa.remount`); repeated execution must
not stack side effects — before re-subscribing to the event bus, unsubscribe
the objects recorded in `ctx["meta"]` (the built-in hooks / security /
plugins slots are the reference implementations);
- `remount_rebuild_agent=True`: assembly-type slots whose applier registers
  generic components into the preset `components` should set True (hot rebuild
  after hot replacement, taking effect immediately).

#### 25.10.4 Complete Example: Developing a "Vector Search" Slot

Goal: add a new `vector_store` slot — pass in any vector-store implementation
(instance / factory / module address), register it as a `vector_store`-kind
generic component, tools access it via `ctx.component("vector_store")`; it
takes effect immediately after hot replacement.

```python
# myapp/slots/vector_store.py
from norpagent.arch import SlotSpec, register_slot


def _apply_vector_store(reg, layer, value, params, ctx):
    # 1. the resolved value is the implementation (instance / factory / module
    #    object) -- the arch layer resolves and instantiates address forms
    #    before calling the applier
    factory = value if callable(value) else (lambda v=value: v)
    # 2. register as a generic component (fixed name; overwrite semantics)
    reg.register_component("vector_store", "_arch_vector", factory)
    # 3. write the preset component declaration -> AgentRuntime builds ctx.components
    ctx["components"]["vector_store"] = "_arch_vector"
    # 4. write extras (engine side can access engine.extras["vector_store"] directly)
    ctx["extras"]["vector_store"] = value


register_slot(SlotSpec(
    name="vector_store",
    description="vector-search component (custom assembly-slot example)",
    protocol="any vector-store implementation (registered as a vector_store generic component)",
    string_semantics="literal",        # the value is passed to the applier as-is (incl. address resolution)
    applier=_apply_vector_store,
    remount_rebuild_agent=True,        # hot rebuild after hot replacement so the component takes effect immediately
))
```

Usage (the experience is identical to the built-in slots):

```python
import norpagent as npa

npa(vector_store=MyVectorStore())                     # instance
npa(vector_store="myapp.vector:create;index=./idx")   # address + clause (literal's address-first semantics)
npa.remount(vector_store=OtherStore())                # hot replacement: AgentRuntime hot rebuild
print(npa.current().engine.extras["vector_store"])    # consume extras
# inside a tool: ctx.component("vector_store")
```

The "address-first" semantics of `string_semantics="literal"` (item 2 of 3.3):
a string **looking like a pure address** (dotted identifier containing `.` /
`:`) is loaded as an address (resolution failure raises `AddressError`);
anything else keeps its literal value — so the `"myapp.vector:create;index=
./idx"` above is resolved, instantiated, and then passed to the applier.

#### 25.10.5 Hot-Reload Red Line: Dict Key-Value Values Must Be Valid Modules (Key Point)

**This is the single most important rule of slot development and hot reload.**
It shares its origin with the tool-mapping red line in 25.2.6, but applies
more broadly:

> For **dict key-value pairs** in any slot value (tools mapping / hooks mapping
> / custom-slot dict values, **nested dicts recursively**), if the value is a
> **pure-address-like string** (`is_address_like`: dotted identifier containing
> `.` or `:`), the assembler resolves it as a **module address** — hot reload
> (`npa.remount`) and startup assembly (`npa()`) are treated identically. **On
> resolution failure it raises `AddressError`; the hot reload fails; there is
> never a silent fallback.**

The value of a key-value pair must be one of the following three "valid
modules":

| Value form | Example | Result |
|---|---|---|
| registered name (name-semantics slot) | `tools={"a": "echo"}` | name reference |
| valid module address (importable + attribute exists) | `tools={"a": "myapp.tools:create"}` | loaded and instantiated (factory convention) |
| valid instance / factory object | `tools={"a": MyTool()}` | used as-is |
| address-like but invalid (typo / module missing / attribute missing) | `tools={"a": "myapp.tolls:create"}` | **AddressError; failure** |

Why it must be strict: hot reload is an online ops action. If an address typo
fell back silently, the old / an empty implementation would quietly stay
online — much harder to debug than an explicit failure. So "if you wrote an
address it must raise explicitly". The implementation lives in
`_resolve_dict_values` in `norpagent/arch/layer.py` (uniform dict-value
handling, nested recursion, raise on resolution failure).

```python
# custom-slot dict values: just as strict at hot reload
npa.remount(vector_store={"embedder": "myapp.embed:create",   # valid address -> resolved
                         "index": "./idx"})                   # not address-like -> literal value
npa.remount(vector_store={"embedder": "myapp.embd:create"})    # typo -> AddressError
```

Exceptions and boundaries:

- **hooks-slot exception**: the hooks mapping's values are "callbacks
  themselves"; an address pointing to a callback function is **kept verbatim,
  not called** (item 3 of 3.3) — but the address must still resolve (module /
  attribute exists), otherwise it raises too;
- **list elements are not resolved**: lists keep literal semantics (e.g. the
  directory path in `plugins=["./dir"]`; tools list elements get the special
  "name or address" treatment by the assembler, see item 4 of 3.3);
- **non-address strings are unaffected**: strings without dotted identifiers
  such as `"high"`, `"./data"`, `"sqlite"` keep literal / name semantics.

**The module cache is invalidated before hot reload**: `remount` deletes the
.pyc for string addresses, pops `sys.modules`, then re-imports (3.7; see 25.2.6). Edit
code → remount and it takes effect; instance forms do no cache invalidation.
To debug a failed hot reload use `layer.describe()` for the assembly manifest
and the `AddressError` traceback to locate the address.

---

### 25.11 Plugin Development in Detail (Quick-Start Version)

A plugin = tools + lifecycle hooks + metadata, distributed as an independent
`.py` file (or a manifest package). When the host loads it, it automatically
gets the full security protection: signature verification / AST audit / import
restrictions / network policy / human approval (Chapter 11). This section is the
quick-start; **the complete reference (all 29 hooks / the setup(api) surface / a
full tutorial / troubleshooting / migration / release checklist) is Chapter 33**.

#### 25.11.1 Complete Single-File Plugin Example

```python
# my_plugins/weather_plugin.py -- complete plugin: tools + hooks + approval hints
PLUGIN_NAME = "Weather Plugin"
PLUGIN_VERSION = "1.0.0"
PLUGIN_PUBLISHER = "xingluosama121"
PLUGIN_DESCRIPTION = "Query city weather; greet at task start."

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "weather",
            "description": "Query the current weather of a city.",
            "parameters": {
                "type": "object",
                "properties": {
                    "city": {"type": "string", "description": "city name"},
                },
                "required": ["city"],
                "additionalProperties": False,
            },
        },
    },
]

# approval hints: weather needs no approval (read-only); undeclared tools follow the host master switch
APPROVAL_HINTS = {
    "weather": {"approval": "none", "risk": "L0"},
}


def execute(tool_name, args, ctx):
    """Unified tool entry: handle and return str / None; unhandled returns None."""
    if tool_name == "weather":
        city = args.get("city") or "Beijing"
        return f"{city}: sunny today, 25 C"   # example implementation; replace with a real API
    return None


# lifecycle hook (one of the 15; names aligned with the legacy app hooks;
# signature: business params first, ctx last)
def on_task_start(prompt, ctx):
    print(f"[plugin] new task: {prompt[:50]}")


def before_tool_call(tool_name, args, ctx):
    """Mutating hook: returning a dict can rewrite the args (11.5)."""
    if tool_name == "weather" and "city" not in args:
        args = dict(args)
        args["city"] = "Beijing"                  # default-city fallback
    return args
```

Loading (host side):

```python
from norpagent.plugins import install_plugin_dirs
loader = install_plugin_dirs(reg, ["./my_plugins"], config={})
for info in loader.plugins:
    print(info.name, info.enabled, info.error or "ok")

# one-shot load via the npa() slot
npa(plugins=["./my_plugins"])
```

#### 25.11.2 Manifest Package Format

Directory distribution: `my_pkg/` contains `manifest.json` + an entry module
(default `plugin.py`):

```json
{
  "name": "my_pkg",
  "version": "1.0.0",
  "publisher": "xingluosama121",
  "description": "package-style plugin",
  "entry": "plugin.py",
  "isolation": "process",
  "permissions": [],
  "signature": ""
}
```

The only difference from a single-file plugin is that the entry module carries
the same module-level interfaces (`PLUGIN_NAME` / `TOOLS` / `execute` / hooks...).

#### 25.11.3 Lifecycle Hooks (29; common signatures excerpted)

A plugin may define the following hook functions at module level (signature
convention: **business params first, PluginContext last**; the full ctx field
reference is in 33.6):

| Hook | Timing | Return value |
|---|---|---|
| `on_task_start(task_text, ctx)` | task starts | ignored |
| `on_task_done(summary, final_reply, ctx)` | task ends | ignored |
| `before_step(step, messages, ctx)` | each step starts | return a list to replace this round's messages |
| `after_step(step, reasoning, content, tool_calls, ctx)` | each step ends | ignored |
| `before_model_call(step, messages, tool_schemas, params, ctx)` | before a model call | return a dict to replace as needed |
| `after_model_call(step, output, ctx)` | after a model call | return a ModelOutput to replace |
| `before_tool_call(tool_name, args, ctx)` | before a tool runs | return a dict to rewrite args / False to block |
| `after_tool_call(tool_name, args, result, ctx)` | after a tool runs | return a str to replace the result |
| `on_content(token, ctx)` | streaming output delta | ignored |
| `on_task_error(error_msg, ctx)` | a task errors | ignored |
| ...... | 16 compatible + 13 native = **29; the full table is 33.5** | |

#### 25.11.4 Isolation, Signing and Publishing

- **Process-level isolation**: declare `ISOLATION = "process"` at the module
  header; the plugin code then only loads and runs in a host child process;
  tools return results via RPC and hooks are forwarded with a time limit
  (11.7) — a crashing plugin never drags down the main process;
- **Signing** (11.8): `python -m norpagent plugin-sign --gen` generates a key
  pair; `plugin-sign my_plugin.py --key <private-key-hex>` produces a signature
  (written into the file header); after the host adds the public key to
  `plugin_trusted_keys`, the plugin is trusted and the audit relaxes to warn;
- **Publishing**: a single-file plugin ships as a `.py`; a package plugin ships
  as a zipped directory.

#### 25.11.5 Debugging and Hot Reload

```python
# development phase: library facade
from norpagent.plugins import PluginSystem
ps = PluginSystem(reg, ["./my_plugins"], config={"plugin_isolation": "inproc"})
infos = ps.load()
ps.status()                 # plugin manifest + isolation-host status
ps.reload("weather_plugin")  # dev-phase hot reload of one plugin
ps.shutdown()               # release the isolation host

# whole-set replacement at runtime (the framework unsubscribes old subscriptions
# before reinstalling, so nothing stacks)
npa.remount(plugins=["./my_plugins_v2"])

# troubleshooting: inspect PluginInfo
for info in ps.loader.plugins:
    if not info.enabled:
        print(info.name, info.error, info.audit_issues)
```

Debugging tips: `plugin_security_audit: "warn"` only warns, never blocks;
`plugin_isolation: "inproc"` runs in-process for easy breakpoint debugging;
switch back to `auto` before going live (AST-reads `ISOLATION` statically; with
process isolation **the plugin code is never executed** by the host).

---

### 25.12 Development Checklist

Self-check every item before delivering a new module (corresponding sections
of this chapter):

| # | Check item | Section |
|---|---|---|
| 1 | implements the full protocol (depends only on protocols, never on concrete implementation classes) | 25.1.4 |
| 2 | the factory supports signature-based injection (`layer` / `slot` / `config` / `workspace_root`) | 3.4 |
| 3 | registered in the Registry (`register_*` or `register_component`); the name does not collide with built-ins | 25.2.5 |
| 4 | at least one integration way verified (name / address / instance); the address form is hot-reloadable | 25.2.5 |
| 5 | **hot-reload verification**: dict key-value values are valid modules (registered name / resolvable address / instance); a misspelled address raises `AddressError` instead of falling back silently | 25.2.6 / 25.10.5 |
| 6 | edit implementation code → remount → new code takes effect (address form invalidates the module cache) | 3.7 |
| 7 | long / streaming paths check the cancel signal (`cancel_requested`) | 25.2.4 |
| 8 | timeouts honored: sandbox `timeout`, model `call_timeout`, network timeouts | 25.5.2 |
| 9 | thread-safe: use locks / immutable data when concurrent tasks share an instance | 25.4.1 |
| 10 | `close()` is idempotent; may be called from shutdown / hot rebuild / task end | 25.5.2 |
| 11 | no exception leaks: tools return `ToolResult(success=False)`, model adapters catch network exceptions | 25.2.1 |
| 12 | the assembly manifest is observable: `layer.describe()` shows your implementation | 3.5 |
| 13 | no upward dependencies (dependency direction points strictly downward) | 2.6.1 |
| 14 | docs and examples (SlotSpec.examples / module docstring) | 25.10.2 |

Completing these 14 items puts your module on exactly the same footing as the
built-in components: assemblable, hot-reloadable, auditable, replaceable.

---

## Chapter 26 Registration Flow in Detail

Chapter 25 explains how to develop modules, slots, plugins and tools. This
chapter explains the act of **registration** itself: how the **Registry**,
the **slot table (SLOT_SPECS)** and the **address resolver** cooperate, which
steps a component goes through from "registered" to "actually used by the
Agent", and the three registration timings, four value forms, validation and
error handling. After reading this chapter you should be able to answer three
questions:

1. Which container does a component register into? (the Registry's 9 namespaces)
2. How does the framework find it after registration? (name / address / instance)
3. What happens between pressing `npa()` and a tool being called? (the assembly pipeline)

### 26.1 The Registration Landscape: Responsibilities of the Three Concepts

Registration is not a single action; it is the cooperation of three existing
mechanisms:

| Mechanism | Module | Responsibility | Typical API |
|---|---|---|---|
| Registry | `norpagent.kernel.registry` | **stores** the "name → implementation" mappings; part of the kernel, unaware of any concrete implementation | `register_*` / `resolve_*` / `build_*` / `list_*` |
| Slot table (SLOT_SPECS) | `norpagent.arch.slots` | **describes** the mount points: 18 built-in slots + runtime hot-pluggable `register_slot` | `get_slot` / `snapshot_slots` / `register_slot` |
| Address resolver | `norpagent.arch.address` | **locates**: turns a string address (`pkg.mod[:attr]`) into an object | `resolve_address` / `is_address_like` |
| Assembler | `norpagent.runtime.mount` | **installs**: translates slot values into registry entries and preset overrides | `build_registry` / `apply_slot_overrides` |

One sentence distinguishes the three: **a slot is a mount point (what to fill),
the Registry is the namespace (what is stored), and an address is a locating
mechanism (how to find it)**. The assembler ties them together.

- A slot value that is a **registered name** (e.g. `"sqlite"`) → the assembler
  looks it up in the Registry and writes the name into the final preset;
- A slot value that is an **address** (e.g. `"myapp.session:create"`) → the
  assembler resolves the address to a factory, registers it under an internal
  name (`_arch_session`) and writes that name into the final preset;
- A slot value that is an **instance / factory** → likewise registered under an
  internal name and referenced.

### 26.2 The Registry: 9 Namespaces

`Registry` (`norpagent.kernel.registry`) holds 9 independent namespaces, each
a "name → implementation" dict:

| Namespace | Register API | Resolve / Build API | Stored content |
|---|---|---|---|
| models | `register_model(name, provider)` | `resolve_model(name)` | model provider instance |
| tools | `register_tool(name, tool)` | `resolve_tool(name)` | Tool instance |
| sessions | `register_session(name, factory)` | `build_session(name)` | factory (new instance each time) |
| sandboxes | `register_sandbox(name, factory)` | `build_sandbox(name)` | factory (new instance each time) |
| schedulers | `register_scheduler(name, factory)` | `build_scheduler(name)` | factory (new instance each time) |
| uis | `register_ui(name, adapter)` | `resolve_ui(name)` | UIAdapter instance |
| plugins | `register_plugin(plugin)` | `unregister_plugin(name)` | Plugin object (tools + hooks) |
| presets | `register_preset(preset)` | `resolve_preset(name)` | Preset instance |
| components | `register_component(kind, name, factory)` | `build_component(kind, name, workspace_root=...)` | any kind: `kind → {name: factory}` |

Key points:

- **`resolve_*` vs `build_*`**: `resolve_*` returns the object as registered;
  `build_*` invokes the factory and **creates a new instance each time** —
  sessions, sandboxes and schedulers are built on demand (each task may get
  its own), while models, tools and UIs are shared (one instance reused
  globally). Therefore you must pass a **factory** (function or class) when
  registering sessions / sandboxes / schedulers, and an **instance** for
  models / tools / UIs.
- **Name-override semantics**: plain dict assignment; a later registration
  silently overrides an earlier one. When a plugin registers a tool whose name
  already exists, it prints `[Registry] tool xxx already exists, overridden by
  plugin xxx` and then overrides.
- **Thread safety**: protected by an internal RLock; any thread may register /
  resolve at any time.
- **Components are an open namespace**: `kind` is not limited to built-ins
  (`context_store` / `project_manager` ...); third parties can register brand
  new kinds (e.g. `vector_store`) without touching the kernel (25.9.1).
- `register_plugin` is a compound registration: plugin tools enter the tool
  table one by one, hooks subscribe to the event bus one by one, and the
  plugin object enters the plugin table; `unregister_plugin` unsubscribes the
  hooks and removes the plugin record (tool entries remain under name-override
  semantics, unreachable when not in the preset's tool set).

### 26.3 The Four Value Forms and String Semantics

A component moves from the developer's code into the Registry in one of four
forms:

| Form | Example | Notes |
|---|---|---|
| Instance | `npa(tools=[MyTool()])` | directly usable; the assembler wraps it in a factory returning the same instance |
| Factory function / class | `npa(model="myapp.model:create")` resolves to a callable | signature-based context injection (`layer` / `slot` / `config` / `workspace_root`, section 3.4) |
| Registered-name reference | `npa(model="openai_compat")` | the string is looked up in the Registry first; found → name reference |
| Address string | `npa(model="myapp.model:create")` | name lookup fails → resolved as an address |

A string entering a slot is interpreted by that slot's **string semantics**
(`SlotSpec.string_semantics`, one of four):

| Semantics | Meaning | Example slots |
|---|---|---|
| `address` | the string is a module address (`pkg.mod[:attr]`), must resolve | `async_loop` / `frontend` / `context_store` / `project_manager` |
| `name` | the string is a registered component name, passed through as-is | `tools` |
| `name_or_address` | look up the Registry name first; if not found, resolve as an address | `model` / `session` / `sandbox` / `scheduler` / `ui` / `preset` |
| `literal` | the string is a literal value (level / path / directory); since v0.9.1, strings shaped like a pure address (dotted identifier containing `.` or `:`) are loaded by address | `hooks` / `security` / `plugins` / `logger` / `storage` / `error_handler` |

Since v0.9.1, **dict key-value pairs** of every slot uniformly support
address resolution (`_resolve_dict_values` in `layer.py`, recursive for
nested dicts):

- a value shaped like a pure address → resolved to an object; a resolution
  failure raises `AddressError` — **no silent fallback** (the red line,
  section 25.2.6);
- a resolved callable → invoked by the factory convention (except the `hooks`
  slot: values are callbacks themselves and are kept as-is, never invoked);
- non-string values pass through unchanged.

Addresses support **extra config clauses**: `"pkg.mod:create;port=9000;theme=dark"`
— the `key=value` pairs after the semicolon are parsed into a dict injected
into the factory's `config` parameter (sections 3.3 / 3.4).

### 26.4 The Full Pipeline from Registration to Assembly (npa() Startup)

Follow the complete chain with `npa(model="myapp.model:create", tools={"weather": "myapp.weather_tool:create"})`:

```
npa(...) startup
│
├─ 1. launch() splits parameters (runtime/__init__.py)
│     by the "live slot-table snapshot":
│     - slot keys (model / tools / ...) → slot_values
│     - other keys (max_steps / workspace_root / ...) → runtime params
│
├─ 2. ArchLayer(config, **slot_values) + mount_defaults(layer)
│     registers the built-in default factories (async_loop / frontend / agent_runtime)
│
├─ 3. layer.connect() (idempotent; resolves slot by slot)
│     - model (name_or_address): the string is left untouched, passed to the
│       assembler for the name-first decision
│     - tools (dict): _resolve_dict_values resolves key-value pairs
│       recursively — the value "myapp.weather_tool:create" is address-like
│       → resolve_address imports myapp.weather_tool → takes the create
│       attribute (callable) → call_factory invokes it by signature
│       → a WeatherTool instance
│
├─ 4. build_registry(layer, params) (runtime/mount.py)
│     a. Registry() creates an empty registry
│     b. install_defaults(reg)    built-in components enter the table
│        (models openai_compat / anthropic / mock; 21 built-in tools;
│         sessions sqlite / memory; sandboxes pooled / subprocess;
│         scheduler persistent; ...)
│     c. register_all_presets(reg)  six built-in presets enter the table
│        (standard etc.)
│     d. apply_slot_overrides(reg, layer, params) assembles in fixed order:
│        ├─ preset slot → baseline preset (default standard)
│        ├─ model: address resolved → register_model("_arch_model", factory)
│        │    → overrides["model"] = "_arch_model"
│        ├─ tools: dict → register_tool("weather", instance) one by one
│        │    → overrides["tools"] = ["weather"] (only yours are enabled)
│        ├─ session / sandbox / scheduler: registered as _arch_xxx or referenced
│        ├─ ui: register_ui("_arch_ui", instance) → extras["ui_adapter"]
│        ├─ context_store / project_manager: register_component(kind,
│        │    "_arch_xxx", factory) → written into the components declaration
│        ├─ hooks: previous architecture-level subscriptions unsubscribed
│        │    first → bus.subscribe re-mounted
│        ├─ security: safe() installs the kit (recorded in meta, unsubscribable)
│        ├─ plugins: install_plugin_dirs runs the full load pipeline
│        ├─ logger / storage / error_handler → extras (consumed by the engine)
│        ├─ custom slots: iterate snapshot_slots(); for each spec with a
│        │    non-None applier, call applier(reg, layer, value, params, ctx)
│        └─ assemble the final Preset(...) (slot overrides + baseline merge)
│           → reg.register_preset(final)
│
├─ 5. NorpEngine(layer, registry, preset, loop, frontend, extras)
│     engine.start() → _build_agent():
│       call_factory(agent_runtime slot implementation, {registry, preset, ui,
│       task_params, layer, config}) → AgentRuntime constructed
│
└─ 6. Consumption (engine.submit(text) → agent.run())
      registry.resolve_model(preset.model)    → the model instance
      registry.tool_schemas(preset.tools)     → the tool schema list
      registry.resolve_tool(name)             → the tool instance (on call)
      registry.build_session(preset.session)  → session instance (on demand)
      registry.build_sandbox(preset.sandbox)  → sandbox instance (on demand)
```

Three key conclusions:

1. **Registration happens in the assembler; consumption happens in the Agent
   runtime** — once your component is in the table, the core code works with
   it with zero changes;
2. **Every slot value ends up as "a registry entry + a preset declaration"**:
   the internal names (`_arch_xxx`) are the assembler's universal device,
   making "your implementation" and "the built-in implementation" consumed
   through exactly the same path;
3. **Order matters**: the preset sets the baseline first, then each slot
   overrides it, and the final preset merges everything — so
   `npa(preset="minimal", model="myapp.model:create")` yields
   minimal baseline + your model override.

### 26.5 Three Registration Timings and Hot Reload

| Timing | Way | Takes effect | Typical scenario |
|---|---|---|---|
| Startup assembly | `npa()` slot params (declarative); or `reg.register_*` before `npa()` (programmatic) | at startup | application assembly, library integration |
| Runtime | `npa.remount(slot=...)`; or direct `reg.register_*` while running | component slots: next run(); assembly slots: AgentRuntime hot rebuild | switching models / tool sets / security levels |
| Code hot reload | edit the module file → `npa.remount(model="myapp.model:create")` | immediately (module cache invalidated) | dev iteration, live bug fixes |

Programmatic registration and the `npa()` ordering convention:

```python
reg = Registry()
reg.register_tool("weather", WeatherTool())   # register first
reg.register_preset(Preset(name="mine", tools=["weather"], ...))
npa(preset="mine")                              # then start, reference by name
```

Note: `npa()` creates its own fresh `Registry()` internally and installs the
built-ins, but it does **not** wipe registrations you made on the same `reg`
before `npa()` — provided you actually use that `reg` (as in the programmatic
assembly above, or by passing `reg` to a custom `agent_runtime` factory).
The simplest approach: use the `reg` produced by `build_registry(layer)` for
programmatic assembly, and `npa()` slot parameters for declarative assembly.

Module-cache invalidation on hot reload (section 3.7): `remount` first runs
`_invalidate_address_module` **only when the outermost value is a bare string
address** — it deletes the .pyc at `module.__cached__` and pops the
`sys.modules` entry, so the next resolution re-imports from disk. So to
hot-update code you must use a bare string address: "edit
`myapp/weather_tool.py` → `npa.remount(tools="myapp.weather_tool:create")`";
**dict / list forms whose values are addresses (e.g. `tools={"weather":
"…:create"}`) do not trigger invalidation and will hit the old module in
`sys.modules`, so the edited code does not take effect**; instance /
registered-name forms have no address to invalidate. See 25.2.6 for details.

Re-entrancy safety: `apply_slot_overrides` may run repeatedly against a
running registry (every `npa.remount` calls it); before re-applying, it
unsubscribes the architecture-level subscriptions it mounted last time (hook
extensions / security kits / plugins), so hot mounts never duplicate
subscriptions — custom-slot appliers must follow the same convention (record
objects to unsubscribe in `ctx["meta"]`, section 25.10.3).

### 26.6 Slot Registration vs Component Registration: Two Kinds of "Register"

The framework has two "register" APIs that are easy to confuse:

| Dimension | `register_slot` (slot-table hot plug) | `register_component` (generic component) |
|---|---|---|
| What is registered | a **mount point**: a new `npa()` keyword (slot name) | an **implementation**: a named implementation under some kind |
| Entry point | `norpagent.arch.slots.register_slot` | `reg.register_component(kind, name, factory)` |
| Scope of effect | the whole pipeline: `npa()` param validation, ArchLayer assembly, `npa.remount` hot replacement, `layer.describe()` manifest | preset `components` declaration + `ctx.component(kind)` lookup |
| Assembly | the `SlotSpec.applier(reg, layer, value, params, ctx)` callback | the framework `build_component`s directly from `preset.components` |
| Protection | the 18 built-in slot names can neither be registered / overridden / unregistered | none (dict-override semantics) |

One sentence: **first a mount point (slot), then an implementation to plug in
(a registry entry)**. In most cases you only need to register implementations
(`register_tool` / `register_component`); you need `register_slot` only when
you want a brand-new `npa()` keyword (full development flow: sections 3.8
and 25.10).

`register_slot` validation rules (violations raise `SlotError`):

- the slot name must be a valid Python identifier (it becomes an `npa()`
  keyword), not a Python keyword, and not `prompt` / `config` (launch special
  keys);
- the 18 built-in slot names are protected (`is_builtin_slot`);
- `string_semantics` must be one of `address` / `name` / `name_or_address` /
  `literal`; `applier` must be callable or None;
- re-registering a name requires `replace=True` (custom slots only, hot-
  replacing the spec; already-assembled implementations keep working until
  the next `remount` re-resolves with the new spec).

`register_slot` takes effect immediately: registering before `npa()` makes the
new slot recognized (launch splits parameters by the live slot table);
registering at runtime works too — a connected ArchLayer fills in late slots
idempotently (`connect`), and `remount` accepts the new slot right away.

### 26.7 Registration Validation and Error Handling

The three exception types of the registration / assembly phase mean different
things:

| Exception | Raised when | What to do |
|---|---|---|
| `ComponentError` | resolving an unregistered name; `register_preset` with a non-Preset; custom-slot applier failure (wrapped) | check whether the name is registered and spelled correctly; cross-check with `reg.list_*()` |
| `SlotError` | illegal slot-table operations: registering a built-in slot name / re-registering without replace / unregistering a missing slot / illegal slot name | fix the spec per the message; change built-in slot values with `npa.remount`, never by editing specs |
| `AddressError` (inherits ImportError) | address resolution failure: module missing / attribute missing / empty address | check the module path and attribute name; import the module yourself to test; **do not silently fall back** (red line, 25.2.6) |

The completeness of a preset's references can be validated in advance:

```python
missing, missing_tools = reg.validate_preset(my_preset)
# the preset is usable only when missing == [] and missing_tools == []
# missing example: ["model=openai_compat", "component=vector_store:pg"]
```

Runtime diagnosis, three moves:

```python
reg.list_tools()                    # what is actually in the table (move 1)
reg.tool_schemas(["weather"])       # is the tool's schema usable (move 2)
eng.layer.describe()                # assembly manifest: where each slot came from (move 3)
```

### 26.8 Registration Best Practices and a Checklist

Best practices:

1. **Naming**: lowercase with underscores; do not collide with built-ins
   (`sqlite` / `pooled` / `persistent` / `openai_compat` ...); prefix plugin
   tools with the plugin name to avoid overrides (`weather_current` beats
   `get_time`).
2. **Factory vs instance**: pass **factories** for sessions / sandboxes /
   schedulers (new instance each time); pass **instances** for models / tools /
   UIs (globally shared). Wrap a tool in a factory only when it carries
   per-run state; otherwise share one instance (mind thread safety).
3. **Timing**: declarative (`npa()` slots) suits application assembly;
   programmatic (`reg.register_*`) suits library integration and dynamic
   conditional assembly; hot reload (`npa.remount`) suits dev iteration and
   live adjustments — all three can be mixed; everything flows into the same
   Registry.
4. **Prefer the address form**: a module address (`pkg.mod[:attr]`) buys you
   factory injection, `;key=value` clauses and code hot reload in one shot.
5. **The hot-reload red line**: dict key-value values must be valid modules —
   a registered name / a resolvable address / an instance; an address-like
   string that fails to resolve raises `AddressError`, never a silent fallback
   (25.2.6 / 25.10.5).
6. **Assembly observability**: before delivery, run `layer.describe()` and
   confirm your implementation appears in the manifest with the right source
   (address / direct value / default logic).

Registration checklist (self-check every item before delivering a new
component):

| # | Check item | Reference |
|---|---|---|
| 1 | the component is registered in the right namespace (tool→tools, session→sessions, component→components) | 26.2 |
| 2 | sessions / sandboxes / schedulers take factories; models / tools / UIs take instances | 26.2 |
| 3 | the name does not collide with built-ins; lowercase with underscores | 26.8 |
| 4 | at least one form verified: `reg.list_*()` shows it; `resolve_*` returns it | 26.7 |
| 5 | the address form is importable: `import myapp.xxx` succeeds, the attribute exists | 26.7 |
| 6 | the address form hot-reloads: edit code → remount → new code takes effect | 26.5 |
| 7 | dict key-value values are valid modules (the red line) | 26.7 / 25.2.6 |
| 8 | preset reference validation passes: `validate_preset` reports no gaps | 26.7 |
| 9 | `layer.describe()` shows the right source | 26.4 / 3.5 |
| 10 | the custom-slot applier is re-entrant (records objects to unsubscribe in `ctx["meta"]`) | 26.5 / 25.10.3 |
| 11 | exception semantics are right: unregistered→`ComponentError`, bad address→`AddressError`, slot table→`SlotError` | 26.7 |
| 12 | an unload path exists: plugins `unregister_plugin`, slots `unregister_slot` | 26.2 / 26.6 |

---

