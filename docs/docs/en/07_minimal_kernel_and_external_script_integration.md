<!-- Split by part from docs/DEVELOPER_MANUAL.EN.md; body is line-for-line identical -->

> **Developer Manual - Part 7: Minimal Kernel and External Script Integration** | Covers: Chapters 27-28 | [Back to index](../README.md)

---

## Chapter 27 Minimal Kernel in Depth: EventBus, the Slot Connector, the Registry and the Address Resolver

> Prerequisite reading: Chapter 2, 2.3 (the four minimal-kernel modules), Chapter 3
> (architecture layer and address functions), Chapter 9, 9.5 (hooks and the EventBus),
> Chapter 26 (the registration flow).
> This chapter takes the four "irreplaceable" components apart one by one: their data
> structures, APIs, internals, and how the four collaborate in one startup and one hot mount.

### 27.1 Overview: The Four Form the Assembly Closed Loop

Section 2.3 already gave the definition of the minimal kernel — the whole framework
has only four irreplaceable pieces:

| # | Component | Class / module | One-line responsibility |
|---|---|---|---|
| 1 | Slot connector | `norpagent.arch.layer.ArchLayer` | Assembles "slot values" into "implementation objects"; supports hot mount at runtime |
| 2 | Address resolver | `norpagent.arch.address` (`resolve_address`) | Resolves an "address string" into a "usable object" |
| 3 | Registry | `norpagent.kernel.registry.Registry` | The name → component mapping center; everything is a registered item |
| 4 | Event bus | `norpagent.kernel.events.EventBus` | The event-passing channel between components; copy-on-write + lock-free iteration |

Everything else — the event loop, agent loop, models, tools, sessions, sandboxes,
schedulers, context store, project management, hook extensions, security, plugins,
frontends, renderers, presets, logging, storage, error handling — is a slot and can
all be replaced.

The collaboration closed loop of the four (one `npa()` startup):

```
npa(...) slot values
   │
   ▼
┌───────────────────────────────────────────────────────┐
│ ArchLayer (slot connector)                            │
│   1. set_default()    registers each slot's built-in  │
│                       default logic                   │
│   2. connect() assembles slot by slot (_connect_slot):│
│        value=None     → default factory               │
│        value=str      → resolve_address() (address    │
│                         resolver)                     │
│        value=dict     → recursive resolution of       │
│                         key-value addresses           │
│   3. layer[slot] gets the implementation directly;    │
│      describe() prints the assembly manifest          │
└───────────────────────────────────────────────────────┘
   │ assembly result lands in the registry
   ▼
┌───────────────────────────────────────────────────────┐
│ Registry                                               │
│   components registered / resolved by name; bus and    │
│   hooks hang off the registry                          │
│   build_registry() / apply_slot_overrides() fill it    │
└───────────────────────────────────────────────────────┘
   │ at runtime
   ▼
┌───────────────────────────────────────────────────────┐
│ EventBus                                               │
│   AgentRuntime / UI / plugins / hooks all subscribe    │
│   emit() broadcast; intercept() mutating dispatch +    │
│   one-vote veto                                        │
└───────────────────────────────────────────────────────┘
```

One-line responsibility boundaries:

- the address resolver only answers "what object is this address";
- the slot connector only answers "what goes in this slot, how, and can it be swapped";
- the registry only answers "which component does this name map to, and how is it made";
- the event bus only answers "who receives which notification when".

The four are independent of each other and none knows the concrete implementation of
the others (the address resolver knows nothing of the Registry, the EventBus nothing of
ArchLayer); the `runtime.mount` assembler strings them together. The following sections
expand on each one.

### 27.2 The General-Purpose Event Bus (GeneralEventBus; the class stays `EventBus`)

> Terminology: in this manual, "the general-purpose event bus" (General Event Bus,
> **GeneralEventBus** for short) denotes the `norpagent.kernel.events.EventBus`
> class and its instances. Only the documentation terminology is unified; **code
> symbols are unchanged** (class name, function names and import paths stay the same).

#### 27.2.1 Positioning and Design Goals

EventBus is "the only decoupling point between the kernel and all external components
(UI / plugins / hooks)": AgentRuntime does not call UI methods directly; it emits events
to the bus; the UI only subscribes to the bus and never perceives the kernel internals.

Code location: `src/norpagent/kernel/events.py`.

Core types:

- `EventType(str, Enum)`: the 16 standard event names, aligned one-to-one with the old
  plugin system's `HOOK_NAMES` (the old comment claims 15, but with on_usage_update it
  is actually 16); migration maps seamlessly: hook = event subscription (11.5 / Appendix E);
- `AgentEvent`: one event = `type` + `payload`(dict) + `ts`, with `.get()` access;
- `HookVeto`: the one-vote-veto exception (`intercept` does not catch it; it reaches the kernel);
- `EventBus`: the bus itself (thread-safe).

#### 27.2.2 Data Structures and the Thread-Safety Model

```python
self._all: List[Listener]                  # listeners subscribed to all events
self._typed: Dict[str, List[Listener]]     # listeners grouped by event type
self._lock = threading.RLock()             # write lock
self._log_error: Optional[Callable]        # subscriber-exception callback
```

Thread safety uses "copy-on-write + lock-free iteration":

- `subscribe` / `unsubscribe`: build a **new list** inside the lock and replace the
  reference; never mutate in place;
- `emit` / `intercept`: take one reference inside the lock (`_snapshot`), then iterate
  directly **lock-free**;
- an old snapshot held by a reader is never mutated (writers replace with a new list
  object), so concurrency safety is unchanged;
- for high-frequency events (e.g. per-token on_content) this saves copying the listener
  list on every event.

Measured numbers (23.1): static subscription table + single-thread publishing, over
1.6 million events/second.

#### 27.2.3 Subscribe and Unsubscribe

```python
from norpagent.kernel import EventBus

bus = EventBus()

def on_content(e):
    print(e.type, e.get("content"))

bus.subscribe(on_content, "on_content")        # only on_content
bus.subscribe(lambda e: print("all:", e.type)) # None = all events
bus.unsubscribe(on_content, "on_content")      # unsubscribe
```

- `event_type=None` goes into the all list (receives every event);
- a specific type goes into the typed list;
- unsubscribe removes the "first equal element" (`_without_one`); a duplicate
  subscription removes only one.

#### 27.2.4 emit vs intercept: Broadcast vs Mutating Dispatch

| Dimension | `emit(event_type, **payload)` | `intercept(event_type, **payload)` |
|---|---|---|
| Purpose | observe / notify (UI refresh, logging) | rewrite the data flow, one-vote veto |
| Return value | ignored | first non-None return wins; all None = no intervention |
| Subscriber exception | caught and logged, keep going | ordinary exceptions same as left; **HookVeto not caught**, reaches the kernel |
| Call order | all listeners first, then typed listeners | same as left |

`intercept` matches the old plugin system's `_broadcast_mutating` semantics: mutating
hooks such as before_step / before_tool_call / after_tool_call rewrite the data flow
through their return values (None = no intervention).

Subscriber-exception isolation: by default printed to stderr; customize with
`set_error_logger(cb)` — a subscriber must never break the main flow (all ordinary
exceptions caught + `_report_error`). This is the hard design of "bus availability first".

#### 27.2.5 The 16 Standard Events

| Layer | Event | Trigger point |
|---|---|---|
| L1 agent lifecycle | on_agent_init / on_agent_shutdown | engine start / shutdown |
| L2 tasks | on_task_start / on_task_done / on_task_error / on_task_stopped / on_task_timeout | the five task states |
| L3 steps | before_step / after_step / before_tool_call / after_tool_call / on_user_input_required | steps and tool calls |
| L4 streaming | on_reasoning / on_content / on_event / on_usage_update | token-level pushes |

#### 27.2.6 Relationship with HookSystem

`HookSystem(bus)` is the "9-layer 29-hook view" over the same bus:
`registry.hooks.before_model_call.subscribe(fn)` is equivalent to subscribing to the
same-named event on `registry.bus`; an unregistered named event automatically becomes a
dynamic-layer hook when emitted. See Chapter 9, 9.5 and Appendix E.

```python
from norpagent import Registry

reg = Registry()
reg.hooks.before_model_call.subscribe(my_fn)   # hook view (recommended)
reg.bus.subscribe(my_fn, "before_model_call")  # direct bus (equivalent)
```

The kernel side emits the same way (inside `AgentRuntime`):

```python
self.hooks.on_agent_init.emit(preset=self.preset.name)     # broadcast
result = self.hooks.before_tool_call.intercept(...)        # mutating dispatch
```

#### 27.2.7 Generic Capabilities (v0.9.7): once / wait / emit_all / Queries and Clear

Beyond the core quartet (subscribe / unsubscribe / emit / intercept), the
general-purpose event bus offers six capabilities aimed at "programmatic
integration / external scripts / testing", all thread-safe and backward-compatible:

```python
from norpagent.kernel import EventBus

bus = EventBus()

# 1) once: one-shot subscription — auto-unsubscribes after the first trigger, no leak
bus.once(lambda e: print("first only:", e.get("v")), "evt_x")
bus.emit("evt_x", v=1)
bus.emit("evt_x", v=2)          # no longer fired

# 2) wait: block until the event fires; returns the AgentEvent (None on timeout,
#    and the temporary subscription is cleaned up automatically)
ev = bus.wait("on_task_done", timeout=30.0)   # external scripts wait for a task
if ev is not None:
    print("task_id:", ev.get("task_id"))

# 3) emit_all: publish and collect every subscriber's return value (unlike emit,
#    which discards return values, and intercept, which stops at the first non-None —
#    emit_all returns the full ordered result list)
results = bus.emit_all("query_metrics", scope="all")
for r in results:
    if r is not None:
        print("metric:", r)

# 4) subscriber_count / has_listeners: subscription-state queries
bus.subscriber_count("on_content")                        # count for one event type
bus.subscriber_count()                                    # count of all-events listeners
bus.has_listeners("on_content")                           # are there any subscribers

# 5) clear: remove subscribers (tests / hot-reload bus rebuilds); returns the count
removed = bus.clear()            # clear everything
removed = bus.clear("evt_x")     # clear one event type
```

Behavior notes:

- `once` wraps the subscription and unsubscribes on trigger; no subscription is
  left behind on timeout or exception paths;
- `wait` **auto-unsubscribes its temporary capturer on timeout** (including a
  re-check for the "event arrives exactly at the timeout instant" race), so no
  subscription leaks; `timeout<=0` means block indefinitely;
- `emit_all` does not catch `HookVeto` (same as intercept); ordinary subscriber
  exceptions are isolated, logged and processing continues;
- `clear` does not notify removed subscribers and returns the actual count removed.

#### 27.2.8 Collaboration Boundary with the Other Three Kernel Components

See 27.6 (startup / hot-mount walkthrough) and 27.5.5 (how the Registry attaches
to the bus).

### 27.3 The Address Resolver (AddressResolver)

#### 27.3.1 Positioning

Code location: `src/norpagent/arch/address.py`.

The address resolver does exactly one thing: **turns an "address" into an "object"** —
it does not call factories, does no assembly, does not check protocols. Factory-context
injection and calling rules live in `norpagent.arch.layer.call_factory`. The address
function semantics "empty = default, filled = connected" (3.2) are all implemented by it.

#### 27.3.2 The Four Address Forms

| Form | Meaning |
|---|---|
| `None` | use the slot's default implementation (handled by the caller; the resolver returns None as-is) |
| `"pkg.mod"` | import the module; prefer the module's conventional factory attributes `create` / `build` / `default`, otherwise mount the whole module |
| `"pkg.mod:attr"` | import the module and take the named attribute as the implementation |
| callable / other object | return as-is (factory function / class / instance / value) |

```python
from norpagent.arch.address import resolve_address

resolve_address(None, slot="model")                    # -> None
resolve_address("myapp.models:create", slot="model")   # -> module attribute create
resolve_address("myapp.tools", slot="tools")           # -> one of create/build/default, else the whole module
resolve_address(MyTool(), slot="tools")                # -> the object itself (instance pass-through)
```

Resolution details:

- attribute fallback order `_FACTORY_ATTRS = ("create", "build", "default")`;
- whole-module mounting requires the module itself to implement the slot protocol
  (e.g. a complete LoopRuntime module);
- a missing `:attr` attribute raises `AddressError` (never silently falls back).

#### 27.3.3 Stripping the Extra Config Clause

In `"pkg.mod:create;timeout=5"`, the `key=value` after the semicolon is **not part of
the address** — the resolver strips it first, and ArchLayer resolves it into the
factory's `config` injection parameter. A clause never interferes with module-path /
attribute resolution:

```python
npa(model="myapp.models:create;api_key=sk-xxx;base_url=https://...")
# address  = myapp.models:create
# config   = {"api_key": "sk-xxx", "base_url": "https://..."}
```

#### 27.3.4 is_address_like: Pure Structural Detection

`is_address_like(value)` decides whether a string looks like a "pure address"
(`pkg.mod[:attr]`) — a purely structural check: no import, no side effect, no exception:

- after stripping `;key=value`, the whole string is a dotted identifier containing at
  least one `.` or `:`;
- therefore literals, paths and URLs such as `"high"` / `"./data"` / `"my_tool"` /
  `"https://api.example.com"` are never misclassified as addresses;
- `"myapp.security:high"` / `"myapp.tools"` / `"pkg:attr"` are addresses.

Used for the v0.9.1 "address-first" decision: in literal slots and dict key-value pairs,
strings in address form load by address, everything else keeps its original semantics
(3.3 / 26.3).

#### 27.3.5 Error Semantics

```python
class AddressError(ImportError): ...
```

A module import failure, a missing attribute, or an empty address string all raise
`AddressError` uniformly (inherits ImportError, catchable via `except ImportError`);
the message carries the slot name and the full address for easy location. **Red line:
an address-like string that fails to resolve must raise, never silently fall back to a
literal** (25.2.6 / 25.10.5).

#### 27.3.6 Division of Labor between Resolving and Calling

```
resolve_address("myapp.models:create", slot="model")  # resolve: get the factory object
call_factory(create, {"layer": layer, "slot": "model", "config": {...}})  # call
```

- `call_factory` injects keys such as `layer / slot / config` by signature; keys the
  factory does not declare are ignored automatically, so a factory of any style plugs in;
- a fully parameterless factory is called with zero arguments; non-introspectable
  callables (built-ins) are called with zero arguments;
- non-callables (module / instance / value) are returned as-is, not called.

### 27.4 The Slot Connector (ArchLayer)

#### 27.4.1 Positioning

Code location: `src/norpagent/arch/layer.py`. The module docstring's first sentence is
the definition: "Architecture layer (ArchLayer): the slot connector".

ArchLayer is the "building-block tray":

1. receives a set of slot values (keyword arguments / a config dict);
2. a slot left empty → uses the default implementation (library built-in logic,
   registered via `set_default`);
3. a slot filled with an address → calls the address resolver and assembles; after
   assembly `layer[slot]` hands back the implementation object directly, and
   `layer.describe()` prints the complete assembly manifest (observable).

#### 27.4.2 Data Structures

```python
self.config: Dict[str, Any]                # slot values (config dict merged with kwargs; kwargs win)
self._impls: Dict[str, Any]                # assembly result: slot -> implementation object
self._defaults: Dict[str, factory]         # default-implementation factories (ctx -> impl)
self._subconfigs: Dict[str, Dict]          # ;key=value clauses resolved out of addresses
self._connected: bool                      # whether connect() has run
```

#### 27.4.3 Core API

| Method | Effect |
|---|---|
| `set_default(slot, factory)` | registers the slot's default-implementation factory (the `mount_defaults` assembler calls it before connect) |
| `connect()` | assembles all slots; **idempotent** — calling again only mounts newly registered slots |
| `remount(slot, value=_RAISE)` | runtime hot mount: without a value, re-resolve with the current config (invalidating the module cache first); with None, clear the slot config back to default; any other value replaces the config and rebuilds immediately |
| `layer[slot]` / `get(slot, default)` | fetch the assembly result (`__getitem__` raises RuntimeError when not connected) |
| `subconfig(slot)` | fetch the extra config clause resolved out of that slot's address |
| `describe()` | print the assembly manifest: each slot's source (default / address / direct value) and implementation type |
| `is_connected()` | whether assembly has run |

#### 27.4.4 String Dispatch: The Four string_semantics

`_connect_slot` dispatches string values by the slot's `string_semantics`:

| Semantics | String-value handling |
|---|---|
| `address` | resolved as a module address (default semantics) |
| `name` | passed through as a registry component name (registration decided by the assembler) |
| `name_or_address` | component name first, module address second (the assembler decides in the registry context) |
| `literal` | literal value (level / path / log name) |

Since v0.9.1 every slot supports "address-first":

- name / name_or_address slots: the string is looked up in the registry first; if not
  found, it resolves as a module address;
- literal slots: a string in pure-address form (`is_address_like`) → loaded by address,
  otherwise kept as a literal;
- **dict key-value pairs of any slot**: a value that is a pure-address string →
  uniformly resolved by address into an object (`_resolve_dict_values` recurses to any
  depth; list elements are not resolved and keep literal semantics; the hooks slot's
  values are the callbacks themselves, and callbacks pointed at by an address stay
  as-is, not called).

Special case: for the frontend slot, a string value that is a `.html/.htm` file path
skips address resolution and is passed through to the assembler for "HTML-path direct
mount" (equivalent to `WebFrontend(html=...)`, 5.4).

#### 27.4.5 defer_factory: Deferring Instantiation

A slot with `defer_factory=True` (e.g. agent_runtime) **only resolves the address, does
not instantiate** during connect; the factory call is deferred to the engine-assembly
phase (`NorpEngine._build_agent`), when the registry / preset context is ready and the
full context is injected by signature.

#### 27.4.6 Hot Mount and Module-Cache Invalidation

```python
layer.remount("model", "myapp.models:v2")   # swap the implementation
layer.remount("model")                      # re-resolve with the current config (hot-reload edited code)
layer.remount("model", None)                # clear the config, fall back to the default logic
```

`remount` first runs two-step cache invalidation (`_invalidate_address_module`)
**only when the outermost value passed in is a string** (the `if isinstance(value,
str)` check in `layer.py`; it does not recurse into dict / list):

1. delete the module's bytecode cache (`module.__cached__`'s .pyc) — otherwise, if a
   same-size file is rewritten within the same second, importlib may judge the "cache
   is still fresh" and re-importing would fetch the old code;
2. pop the `sys.modules` entry — the next resolution re-imports from disk.

Thus the hot-reload closed loop "edit code → remount (**bare string address**) → new
code takes effect" holds; **dict / list forms whose values are addresses do not
trigger invalidation** and will still hit the old module in `sys.modules` (see
25.2.6). Custom slots (registered via `register_slot`, 3.8) support remount too,
resolving per the spec at registration time; after `replace=True` hot-replaces a spec,
remount resolves per the new spec.

#### 27.4.7 Relationship with the Slot Table

The slot table (`norpagent.arch.slots`, `SLOT_SPECS`) itself is hot-pluggable: after
`register_slot()` registers a custom slot at runtime, connect / remount / describe /
set_default all work against the **live table at call time** — connect idempotently
mounts late-registered slots, and remount applies to new slots as well. SlotSpec fields
(name / protocol / default_address / string_semantics / factory_kwargs / defer_factory /
applier / remount_rebuild_agent) are covered in 25.10.2.

#### 27.4.8 Minimal Usage Example

```python
from norpagent.arch.layer import ArchLayer

layer = ArchLayer(async_loop="myapp.loop:create", preset="standard")
layer.connect()                 # assemble all slots
loop = layer["async_loop"]      # the connected loop system
print(layer.describe())         # assembly manifest (observable)
```

### 27.5 The Registry

#### 27.5.1 Positioning

Code location: `src/norpagent/kernel/registry.py`.

"Everything is a registered item": models / tools / sessions / sandboxes / schedulers /
UIs / plugins / presets / generic components are all registered and resolved by name.
AgentRuntime only interacts with the registry, so replacing any part never requires
kernel-code changes. The registry itself is part of the kernel and knows no concrete
implementation (docstring: "unaware of any concrete implementation").

#### 27.5.2 The 9 Namespaces

| Namespace | Internal dict | Register API | Resolve API |
|---|---|---|---|
| models | `_models` | `register_model(name, provider)` | `resolve_model(name)` (instance) |
| tools | `_tools` | `register_tool(name, tool)` | `resolve_tool(name)` (instance) |
| sessions | `_sessions` | `register_session(name, factory)` | `build_session(name)` (calls factory) |
| sandboxes | `_sandboxes` | `register_sandbox(name, factory)` | `build_sandbox(name)` (calls factory) |
| schedulers | `_schedulers` | `register_scheduler(name, factory)` | `build_scheduler(name)` (calls factory) |
| uis | `_uis` | `register_ui(name, adapter)` | `resolve_ui(name)` (instance) |
| plugins | `_plugins` | `register_plugin(plugin)` | `list_plugins()` (no single-fetch API) |
| presets | `_presets` | `register_preset(preset)` | `resolve_preset(name)` |
| components | `_components[kind]` | `register_component(kind, name, factory)` | `build_component(kind, name, workspace_root=None)` |

Key difference:

- **instances**: models / tools / UIs (resolve and use);
- **factories**: sessions / sandboxes / schedulers / generic components (freshly built on
  every build); `build_component` supports `workspace_root` auto-injection — passed in
  when the factory declares a same-named parameter or `**kwargs` (project management and
  other components locate projects through it).

Side effects of `register_plugin`: tools enter the tool table (same-name overwrite + log
hint); hooks subscribe to the bus (`self.bus.subscribe(fn, hook)`). `unregister_plugin`
does the reverse: unsubscribes hooks and removes the plugin record (tool entries remain —
the name-overwrite semantics mean re-mounting a same-name plugin naturally overwrites;
historical entries are unreachable if not in the preset tool set and do not affect
resolution).

#### 27.5.3 Query and Validation

| Method | Effect |
|---|---|
| `list_models() ... list_uis()` | sorted name lists per namespace |
| `list_components(kind=None)` | component listing: with a kind, the kind's name list; otherwise all groups |
| `tool_schemas(names=None)` | export the tools' OpenAI function schemas (all by default) |
| `validate_preset(preset)` | validate whether the components referenced by a preset are all present, returns `(missing, missing_tools)`; empty lists = usable |

`validate_preset` checks the model / session / sandbox / scheduler / ui / components /
tools branches; missing items are formatted as `"model=openai_compat"`,
`"component=vector_store:pg"`, easy to read and debug; AgentRuntime construction also
runs it first and raises `ComponentError` on any gap (fast fail).

#### 27.5.4 Thread Safety and Error Semantics

- all reads and writes go through `threading.RLock()`; registration and resolution are
  cross-thread safe;
- unregistered / wrong type → `ComponentError` (the message carries the list of
  available names);
- `register_preset` only accepts `Preset` instances, otherwise `ComponentError`.

#### 27.5.5 Relationship with the General-Purpose Event Bus / ArchLayer

```python
reg = Registry()          # creates an EventBus internally
reg.bus                   # the bus itself (shared with AgentRuntime as the same instance)
reg.hooks                 # lazily creates HookSystem(bus): the 9-layer hook view
reg.security              # security context (installed by norpagent.safe(); wholesale pluggable)
```

Assembly side (`runtime.mount`):

- `build_registry(layer)`: creates the registry + installs the built-in defaults
  (install_defaults);
- `apply_slot_overrides(reg, layer, ...)`: lands slot assembly results into the registry
  (preset-field overrides, component registration, custom-slot applier calls), called
  repeatedly on hot mount — **appliers must be re-entrancy safe** (record objects to
  unsubscribe in `ctx["meta"]`; repeated execution must not stack side effects, 25.10.3).

#### 27.5.6 Usage Example

```python
from norpagent import Registry

reg = Registry()
reg.register_tool("clock", ClockTool())
reg.register_session("memory", lambda: MemorySession())
reg.register_component("context_store", "fts5", lambda: Fts5Store())

sess = reg.build_session("memory")       # freshly built every time
tool = reg.resolve_tool("clock")         # instance fetched directly
store = reg.build_component("context_store", "fts5")
missing, missing_tools = reg.validate_preset(preset)
assert missing == [] and missing_tools == []
```

### 27.6 The Four Working Together: A Walkthrough of One Startup and One Hot Mount

#### 27.6.1 Startup Sequence (Inside npa())

```
1. ArchLayer(**slot_values)           the slot connector receives all slot values
                                      (config + kwargs merged)
2. mount_defaults(layer)              set_default registers each slot's built-in
                                      default logic
3. build_registry(layer)              create the Registry; install_defaults installs
                                      built-in components
4. apply_slot_overrides(reg, layer)   by priority task-level > remount > startup
                                      assembly > preset: override fields; component
                                      registration; custom-slot applier runs
5. layer.connect()                    assemble slot by slot:
                                      - value None   → default factory (ctx injected)
                                      - string       → resolve_address + call_factory
                                        (inject layer / slot / config by signature;
                                        config comes from the ;key=value clause)
                                      - dict         → recursive resolution of
                                        key-value addresses
                                      - defer_factory slots resolve but do not
                                        instantiate
6. NorpEngine._build_agent()          engine-assembly phase: defer_factory factories
                                      are called (registry / preset context ready) →
                                      AgentRuntime(reg, bus, ...)
7. AgentRuntime startup               on construction: self.bus = registry.bus;
                                      UI mounts the bus (bus.subscribe(ui.on_event),
                                      unsubscribed on shutdown); emits on_agent_init;
                                      task execution → emit / intercept
```

Key point: **the slot connector is in charge of "fitting", the registry of "recording",
the event bus of "communicating", the address resolver of "recognizing"** — in order,
the address resolver is called first (during assembly), the registry is filled
mid-assembly, and the bus runs throughout.

#### 27.6.2 Hot-Mount Sequence (npa.remount(slot, value))

```
1. remount(slot, value)               the slot connector: a string address first
                                      invalidates the module cache
                                      (delete .pyc + pop sys.modules)
2. _connect_slot(slot)                re-resolve / re-assemble that slot
3. apply_slot_overrides runs again    called repeatedly on the same registry →
                                      appliers re-entrancy safe
                                      (old subscriptions unsubscribed via ctx["meta"],
                                      preventing stacking)
4. plugin-like slots                  unregister_plugin unsubscribes old hooks →
                                      re-register the new plugin
5. when it takes effect               slots with remount_rebuild_agent=True hot-rebuild
                                      the AgentRuntime; other slots take effect on the
                                      next run() or only update extras, no rebuild
```

#### 27.6.3 Boundaries of the Four Exception Types

| Exception | Raised by | Trigger | Handling advice |
|---|---|---|---|
| `AddressError` | address resolver | address import failure / missing attribute / empty address | check the module path and attribute name; an address-like string never silently falls back |
| `ComponentError` | registry | unregistered / wrong type / wrong preset type | use `list_*()` to see available names; check the namespace is the right one |
| `SlotError` | slot table | illegal slot-table operation (register / unregister / illegal spec) | check SlotSpec fields and the reserved names (prompt / config) |
| `RuntimeError` | slot connector | `layer[slot]` before connect() | `layer.connect()` first; or use `layer.get(slot, default)` |

#### 27.6.4 Replacement Principles and a Checklist

Four principles for replacing any component (echoing 26.8):

1. **Change config first**: anything solvable with `npa(slot=...)` or `remount` needs
   no code change;
2. **Registry first**: register new components with `register_*`, then reference them
   in a preset;
3. **Address form first**: `pkg.mod[:attr]` gets factory injection, `;key=value` clauses
   and code hot reload in one shot; it is the recommended form;
4. **Assembly observable**: run `layer.describe()` before delivery to confirm the source
   is right.

Self-check list:

| # | Check item | Involved component |
|---|---|---|
| 1 | `layer.connect()` succeeds and `layer[slot]` is fetchable | slot connector |
| 2 | `layer.describe()` shows the source (default / address / direct value) | slot connector |
| 3 | address form: `import myapp.xxx` succeeds, the attribute exists | address resolver |
| 4 | an address-like string that fails to resolve raises `AddressError` (red line) | address resolver |
| 5 | `reg.list_*()` sees it and `resolve_*` fetches it | registry |
| 6 | `validate_preset` reports no gaps | registry |
| 7 | after subscribing, `emit` is received; a throwing subscriber does not break the main flow | event bus |
| 8 | mutating-hook return values take effect; HookVeto reaches the kernel | event bus |
| 9 | edit code → remount → new code takes effect | slot connector + address resolver |
| 10 | appliers re-entrancy safe (repeated remount does not stack side effects) | slot connector + registry |

---

## Chapter 28 External Python Script Integration: Hot Mounting and Hook Subscription

> This chapter targets external scripts that do **not** modify the framework and
> do **not** write plugins: ops tools, monitoring collectors, test stubs, notebook
> analysis, cross-process bridges. The goal: one `.py` file can start the engine,
> subscribe to hooks, hot-mount components and wait for events, all through public
> APIs.

### 28.1 Use Cases and the Two Integration Modes

| Mode | Process | Typical scenario | Key APIs |
|---|---|---|---|
| A. in-process embedding | same process as the engine | start the engine and inject monitoring / rate limiting / auditing | `npa()`, `engine.registry.hooks`, `npa.remount()` |
| B. side-channel subscription | standalone process | event collection, metric reporting, no engine | `Registry()` + `HookSystem` + module-level hook API |

Mode A hook subscriptions are identical to in-library code (every 9.8 example
works verbatim); mode B uses the **module-level hook API**
(`norpagent.hooks.<name>.subscribe(fn, system=...)`) to attach subscriptions to
your own bus, without depending on any engine instance.

### 28.2 Mode A: Start the Engine + Subscribe to Hooks (same process)

```python
# watch_agent.py -- start the engine and attach monitoring hooks
import norpagent as npa

engine = npa(preset="standard")          # start (default Web frontend, or pick one)
hooks = engine.registry.hooks            # hook view of the engine bus

@hooks.on_task_start.subscribe           # task start
def _start(e):
    print(f"[watch] task {e.get('task_id')} start")

@hooks.before_tool_call.subscribe        # tool-call audit (decorator works on mutating hooks too)
def _audit(e):
    print(f"[watch] tool {e.get('tool_name')} args={e.get('args')}")

@hooks.after_tool_call.subscribe
def _result(e):
    print(f"[watch] -> ok={e.get('success')} {str(e.get('result'))[:80]}")

try:
    while not npa.stop():                # the Web frontend needs lifecycle polling
        pass
finally:
    npa.shutdown()
```

Key points: `@hooks.<name>.subscribe` is equivalent to
`hooks.<name>.subscribe(fn)`; subscribers receive an `AgentEvent` and read values
with `e.get(key)` (payload keys in Appendix E). On exit (Ctrl+C / `npa.stop()`)
subscriptions die with the bus — no manual unsubscribe needed.

### 28.3 Hot Mounting: Replacing Components While Running

A running engine can replace any slot implementation; the next run() picks it up
(3.7):

```python
import norpagent as npa

engine = npa()

# switch the model (edit the module file, then remount to hot-reload)
npa.remount(model="myapp.model:create")

# switch the tool set
npa.remount(tools=["echo", "get_time", "myapp.tools:create"])

# switch the frontend (effective on the next task)
npa.remount(frontend="norpagent.frontends.console:ConsoleFrontend")

# switch the security level
npa.remount(security="high")

# hot-mount hooks (the previous architecture-level subscriptions are unsubscribed
# first, then re-attached — nothing stacks)
def my_guard(event):
    if "danger" in (event.get("user_input") or ""):
        raise __import__("norpagent").kernel.events.HookVeto("vetoed by an external script")
npa.remount(hooks={"before_input": my_guard})

# detach
npa.remount(hooks=None)
```

> Hot-reload red line (3.7 / 25.10.5): slot dict key-value pairs must be **valid
> modules** (a registered name / a resolvable address / a valid instance);
> an address-like string that fails to resolve raises `AddressError`, never a
> silent fallback.

### 28.4 Mode B: Standalone Side-Channel Subscription (no engine)

A monitoring script does not start an engine; it builds its own registry and bus
and subscribes through the module-level hook API:

```python
# probe_events.py -- side-channel event probe (standalone process)
import sys
import norpagent as npa
from norpagent import Registry
from norpagent.hooks import on_task_start, before_tool_call, on_content

reg = Registry()                       # own private bus (no engine started)

def on_start(e):
    print(f"[probe] task start: {e.get('user_input')!r}")

def on_tool(e):
    print(f"[probe] tool={e.get('tool_name')}")

def on_stream(e):
    print(f"[probe] content: {e.get('content')!r}")

# module-level hook API: pass system=reg explicitly (the default system is a
# different private bus and would never receive reg's events)
on_task_start.subscribe(on_start, system=reg)
before_tool_call.subscribe(on_tool, system=reg)
on_content.subscribe(on_stream, system=reg)

# publish test events manually (verify the subscriptions)
reg.bus.emit("on_task_start", user_input="hello", task_id="t1")
reg.bus.emit("before_tool_call", tool_name="echo", args={})
```

The engine side can forward events to the probe process over any channel
(HTTP / files / named pipes), or simply `import probe_events` in the engine
process and point `reg` at the engine registry — `system=engine.registry`
completes the cross-module attachment (9.9).

### 28.5 Waiting for Events and One-Shot Subscriptions

External scripts often need "wait until some event, then continue". The general-
purpose event bus's `wait` / `once` are made for this (27.2.7):

```python
import norpagent as npa
from norpagent.kernel import EventBus

engine = npa(frontend="norpagent.frontends.headless:HeadlessFrontend")
bus = engine.registry.bus

# wait for a task to finish (up to 60 seconds)
ev = bus.wait("on_task_done", timeout=60.0)
if ev is not None:
    print("completed:", ev.get("task_id"), "steps:", ev.get("steps"))
else:
    print("timeout: no task finished within 60s")

# one-shot subscription: respond only to the first on_content
bus.once(lambda e: print("first token arrived"), "on_content")

# a standalone local bus works too (unrelated to any engine)
local_bus = EventBus()
local_bus.once(lambda e: print("pong:", e.get("v")), "ping")
local_bus.emit("ping", v=42)
```

### 28.6 Complete Example: an Ops Script (Monitor + Rate Limit + Hot Switch)

```python
# ops_guard.py -- monitor / rate-limit / hot-switch beside the engine, all public APIs
import time
import norpagent as npa
from norpagent.kernel.events import HookVeto

RATE = {}                       # tool_name -> [timestamps]

engine = npa(preset="standard")
hooks = engine.registry.hooks

@hooks.on_task_start.subscribe
def _log(e):
    print(f"[ops] task {e.get('task_id')} <- {e.get('user_input')!r}")

@hooks.before_tool_call.subscribe
def _rate_limit(e):             # mutating hook: veto over-frequent tools
    now = time.time()
    name = e.get("tool_name")
    RATE.setdefault(name, []).append(now)
    RATE[name] = [t for t in RATE[name] if now - t < 60]
    if len(RATE[name]) > 10:
        raise HookVeto(f"tool {name} called more than 10 times/min (ops rate limit)")
    return None

@hooks.after_tool_call.subscribe
def _audit(e):
    ok = "ok" if e.get("success") else "FAIL"
    print(f"[ops] {e.get('tool_name')} {ok} {e.get('duration_ms')}ms")

def health_check():
    """Hot-mount demo: degrade the model to mock after 30 seconds."""
    time.sleep(30)
    npa.remount(model="mock")
    print("[ops] model degraded to mock (hot-swap via remount)")

import threading
threading.Thread(target=health_check, daemon=True).start()

try:
    while not npa.stop():
        time.sleep(0.5)
finally:
    npa.shutdown()
```

### 28.7 Common Errors and Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| subscribed but never receive events | module-level APIs default to the **process default system**, which is a different bus than the engine's | pass `system=engine.registry` explicitly, or use `engine.registry.hooks` |
| `remount(tools=...)` raises `AddressError` | the value looks like an address but cannot be resolved (red line) | check the module path and attribute; use a registered name or a valid instance |
| old logic still runs after editing code + `remount` | you used a dict / list address value, which does not invalidate the module cache (only an outermost bare string does) | use a bare string address: `npa.remount(tools="myapp.weather_tool:create")` (25.2.6) |
| `wait` never returns | wrong event name / timeout is 0 (means indefinite) | confirm with `subscriber_count` first; give an explicit timeout |
| old logic still active after hot mount | the slot does not rebuild the AgentRuntime (`remount_rebuild_agent=False`) | check the slot spec (Appendix A); assembly-type custom slots must set it True |
| the veto does not take effect | you used `emit` instead of mutating dispatch | mutating semantics require `intercept` (9.3) |

---

