# NORP Agent Developer Manual

> **Version**: 2.2.1 | **Brand**: FarStars (远星) | **License**: Copyright (c) 2026 xingluosama121, MIT Licensed

---

## Table of Contents

- [Chapter 1 Quick Start](#chapter-1-quick-start)
- [Chapter 2 Overall Architecture: Layers and Data Flow](#chapter-2-overall-architecture-layers-and-data-flow)
- [Chapter 3 Architecture Layer and Address Functions](#chapter-3-architecture-layer-and-address-functions)
- [Chapter 4 Event Loop System: norpagent.nasyncio()](#chapter-4-event-loop-system-norpagentnasyncio)
- [Chapter 5 Frontend Family](#chapter-5-frontend-family)
- [Chapter 6 npa() Startup and Lifecycle](#chapter-6-npa-startup-and-lifecycle)
- [Chapter 7 Models and Tools](#chapter-7-models-and-tools)
- [Chapter 8 Sessions, Sandboxes, Schedulers, Context and Projects](#chapter-8-sessions-sandboxes-schedulers-context-and-projects)
- [Chapter 9 The 9-Layer 29-Hook System](#chapter-9-the-9-layer-29-hook-system)
- [Chapter 10 Security System: norpagent.safe()](#chapter-10-security-system-norpagentsafe)
- [Chapter 11 Plugin System](#chapter-11-plugin-system)
- [Chapter 12 Preset Modes](#chapter-12-preset-modes)
- [Chapter 13 Command-Line Entry](#chapter-13-command-line-entry)
- [Chapter 14 Embedded and Ultra-High-Concurrency Deployment](#chapter-14-embedded-and-ultra-high-concurrency-deployment)
- [Chapter 15 Work Rollback: Snapshots / Undo / Redo / Crash Rescue / Safe Mode](#chapter-15-work-rollback-snapshots--undo--redo--crash-rescue--safe-mode)
- [Chapter 16 Library Integration Examples](#chapter-16-library-integration-examples)
- [Chapter 17 Testing and Debugging](#chapter-17-testing-and-debugging)
- [Chapter 18 Migration Guide](#chapter-18-migration-guide)
- [Chapter 19 FAQ](#chapter-19-faq)
- [Appendix A Architecture Slot Quick Reference](#appendix-a-architecture-slot-quick-reference)
- [Appendix B 9-Layer Hook Quick Reference](#appendix-b-9-layer-hook-quick-reference)
- [Appendix C Public API Index](#appendix-c-public-api-index)
- [Chapter 20 Module Flow Orchestration (FLOW)](#chapter-20-module-flow-orchestration-flow)
- [Chapter 21 Built-in Components in Depth](#chapter-21-built-in-components-in-depth)
- [Chapter 22 Web UI and Frontend Deep Dive](#chapter-22-web-ui-and-frontend-deep-dive)
- [Chapter 23 Performance Design and Benchmarks](#chapter-23-performance-design-and-benchmarks)
- [Chapter 24 Rescue Mode: Low-Level Loop Control and Human Takeover](#chapter-24-rescue-mode-low-level-loop-control-and-human-takeover)
- [Chapter 25 Developer Practice: Modules, Slots, Plugins and Tools](#chapter-25-developer-practice-modules-slots-plugins-and-tools)
- [Chapter 26 Registration Flow in Detail](#chapter-26-registration-flow-in-detail)
- [Chapter 27 Minimal Kernel in Depth: the GeneralEventBus, the Slot Connector, the Registry and the Address Resolver](#chapter-27-minimal-kernel-in-depth-the-generaleventbus-the-slot-connector-the-registry-and-the-address-resolver)
- [Chapter 28 External Python Script Integration: Hot Mounting and Hook Subscription](#chapter-28-external-python-script-integration-hot-mounting-and-hook-subscription)
- [Chapter 29 Multimodal: Vision and Sound](#chapter-29-multimodal-vision-and-sound)
- [Chapter 30 Central Nervous Bus: Multi-Instance and the Neural Tree](#chapter-30-central-nervous-bus-multi-instance-and-the-neural-tree)
- [Chapter 31 Product Distribution: norpagent unbox](#chapter-31-product-distribution-norpagent-unbox)
- [Chapter 32 The Self-Evolution System: Hot Reload, Checkbox Approvals and Evolution Packages](#chapter-32-the-self-evolution-system-hot-reload-checkbox-approvals-and-evolution-packages)
- [Chapter 33 The Complete Plugin Development Guide](#chapter-33-the-complete-plugin-development-guide)
- [Chapter 34 Settings Store, White-box and Evolution Loop (v2.2.0)](#chapter-34-settings-store-white-box-and-evolution-loop-v220)
- [Appendix D Glossary](#appendix-d-glossary)
- [Appendix E 29-Hook Event Payload Quick Reference](#appendix-e-29-hook-event-payload-quick-reference)
- [Appendix F Frontend-Backend Communication Quick Reference](#appendix-f-frontend-backend-communication-quick-reference)
- [Appendix G All Commands Quick Reference](#appendix-g-all-commands-quick-reference)
- [Appendix H All Functions and Structures Quick Reference](#appendix-h-all-functions-and-structures-quick-reference)
- [Appendix I Multimodal Configuration and API Quick Reference](#appendix-i-multimodal-configuration-and-api-quick-reference)
- [Appendix J Central Nervous Bus Quick Reference](#appendix-j-central-nervous-bus-quick-reference)

---

## Chapter 1 Quick Start

### 1.1 Installation

```bash
pip install norpagent
```

The core package has no third-party dependencies and runs in a plain Python environment after installation (with the built-in mock model and tools).
Optional capabilities install on demand:

```bash
pip install norpagent[openai]       # OpenAI-compatible model adapter (DeepSeek/OpenAI/Qwen/vLLM/Ollama)
pip install norpagent[anthropic]    # Anthropic-protocol model adapter
pip install norpagent[web]          # Web search (web_search / web_fetch tools)
pip install norpagent[security]     # Plugin Ed25519 signature verification (cryptography)
pip install norpagent[all]          # everything
```

### 1.2 First Program

```python
import norpagent as npa

npa()                    # start with the default configuration (standard preset + Web frontend)
running = True
while running:
    if npa.stop() == True:   # lifecycle function: exit when the application ends
        running = False
```

Save it as `hello.py` and run; the console prints:

```
[norpagent] frontend web listening on 127.0.0.1:8787
[norpagent] lazy-loaded modules: ...   # lazy-loaded modules actually used this run
```

Open the address in a browser to see the chat UI. See Chapter 6 for the startup flow. Two key points:

1. **`npa()` is a module-level call** — the `norpagent` module itself is callable, equivalent to `norpagent.launch()`;
2. **`npa.stop()` is a lifecycle function** — it returns `True` when the Agent application has ended and the main loop should exit.

### 1.3 Single-Task Mode

```python
import norpagent as npa

npa(prompt="explain briefly what an address function is")
running = True
while running:
    if npa.stop() == True:
        running = False

engine = npa.current()
print(engine.last_result.final_content)
```

With `prompt` given: the Agent executes this single task and stops automatically (`npa.stop()` becomes `True`);
the result is stored in `npa.current().last_result`.

### 1.4 Replacing the Frontend

```python
import norpagent as npa

npa(prompt="hi", frontend="norpagent.frontends.headless:HeadlessFrontend")
while True:
    if npa.stop():
        break
```

HeadlessFrontend reads no keyboard input and renders no UI; it is driven through the programmatic API.
Component replacement is done by filling a new address into a slot, without modifying framework core code.

### 1.5 Chapter Usage Cheat Sheet

| Usage | How |
|---|---|
| Start with the default configuration | `npa()` |
| Check whether the application has ended | `npa.stop()` |
| Single task | `npa(prompt="...")` |
| Specify a preset mode | `npa(preset="standard")` |
| Specify a model | `npa(model="openai_compat")` |
| Specify the event loop | `npa(async_loop="myapp.loop:create")` |
| Specify a frontend | `npa(frontend="myapp.ui:create")` |
| Specify session storage | `npa(session="sqlite")` |
| Specify the security level | `npa(security="high")` |
| Web port / language | `npa(port=9000, language="zh_CN")` |
| Custom main page | `npa(html="/path/to/my.html")` |
| Custom module flow page | `npa(flow_html="/path/to/flow.html")` |
| Frontend mounting an HTML path directly | `npa(frontend="/path/to/my.html")` |
| Instance / value | `npa(async_loop=loop_instance)` — mount an existing object directly |

---

## Chapter 2 Overall Architecture: Layers and Data Flow

### 2.1 Architecture Notes

In NorpAgent, apart from the minimal kernel at the bottom, every component is a
replaceable slot. To replace a component (model, tools, session, sandbox,
scheduler, frontend, event loop, agent loop), fill a new address into its
slot — no framework core code changes are needed.

### 2.2 Layer Diagram

```text
┌─────────────────────────────────────────────────────────────┐
│  Your application                                           │
│  npa() / npa.stop() / npa.nasyncio() / npa.current().submit() │
└───────────────────────────┬─────────────────────────────────┘
                            │ module entry (norpagent/__init__.py, callable)
┌───────────────────────────▼─────────────────────────────────┐
│  Runtime layer  runtime/                                    │
│  launch → ArchLayer.connect → mount.build_registry          │
│  → NorpEngine (lifecycle state machine + background loop    │
│    thread + frontend thread)                                │
└──────┬──────────────────┬───────────────────┬───────────────┘
       │                  │                   │
┌──────▼──────┐   ┌───────▼────────┐  ┌───────▼───────────────┐
│ arch/       │   │ loops/         │  │ frontends/            │
│ slot specs  │   │ LoopRuntime    │  │ Frontend protocol     │
│ address     │   │ protocol +     │  │ console/headless/web  │
│ resolution  │   │ default impl   │  └───────────────────────┘
│ ArchLayer   │   │ = nasyncio()   │
└──────┬──────┘   └───────┬────────┘
       │ mount by slot      │ driven by protocol
┌──────▼────────────────────▼─────────────────────────────────┐
│  Kernel  kernel/                                            │
│  Registry ── EventBus ── AgentRuntime                       │
│  (the agent loop itself is also a replaceable slot:         │
│   agent_runtime)                                            │
└──┬──────────┬──────────┬──────────┬──────────┬──────────────┘
   │          │          │          │          │
┌──▼───┐ ┌────▼────┐ ┌───▼────┐ ┌───▼─────┐ ┌──▼────────────┐
│model │ │tools    │ │session │ │sandbox  │ │scheduler /    │
│      │ │         │ │        │ │         │ │context /      │
│      │ │         │ │        │ │         │ │project /      │
│      │ │         │ │        │ │         │ │security /     │
│      │ │         │ │        │ │         │ │plugins        │
└───────┘ └─────────┘ └─────────┘ └──────────┘ └───────────────┘
   All of the above are resolved by name through the registry —
   all are architecture slots (replaceable)
```

### 2.3 The Minimal Kernel (Four Modules)

The minimal kernel consists of four modules:

| # | Module | Responsibility | Why it is not replaceable |
|---|---|---|---|
| 1 | `norpagent.arch.layer.ArchLayer` | the slot connector | performs the assembly work |
| 2 | `norpagent.arch.address` | the address resolver | provides address semantics |
| 3 | `norpagent.kernel.registry.Registry` | the registry | the name-to-component mapping center |
| 4 | `norpagent.kernel.events.EventBus` | the event bus | the inter-component event channel |

Everything else — event loop, agent loop, models, tools, sessions, sandboxes,
schedulers, context stores, project management, hook extensions, security,
plugins, frontends, renderers, presets, logging, storage, error handling — is a slot.

### 2.4 Data Flow of a Single Task

The user enters one line, "read readme.md and summarize it"; inside an engine
started by `npa()` this happens:

```text
frontend thread input() gets the text
  → engine.submit(text)                  (Chapter 6)
  → loop.submit(fn)                      (Chapter 4: the loop system, replaceable)
  → AgentRuntime.run(text)               (the kernel loop; replaceable via the agent_runtime slot)
      → L3 prepare_input                (before_input / after_input hooks)
      → L4 create_session / append_message
      → L5 build_messages               (system prompt + history merged)
      → L6 before_step
      → L7 call_model                   (model = the provider resolved from the model slot)
      → L8 execute_tool_call            (tools = tools slot, sandbox = sandbox slot)
      →   (multiple rounds until the model gives the final answer)
      → L9 finalize_result
  ← RunResult (final_content / status / usage ...)
the event bus broadcasts all along
  (on_task_start / on_content / after_tool_call ...)
  → ui renderer (UIAdapter) subscribes and renders the stream to the user
```

Every L-numbered stage is a hook layer (Chapter 9); every part is a slot (Chapter 3).

### 2.5 Module Map: What Each File Does

| File | Responsibility |
|---|---|
| `norpagent/__init__.py` | the module is the entry: `npa()` / `npa.stop()` / `npa.nasyncio()` |
| `norpagent/arch/slots.py` | specs for the 18 built-in architecture slots + the hot-pluggable slot-registry (register_slot / unregister_slot / replace=True spec replacement) |
| `norpagent/arch/address.py` | the address-function resolver (string → module/object) |
| `norpagent/arch/layer.py` | ArchLayer: slot connection and factory invocation |
| `norpagent/loops/base.py` | the LoopRuntime protocol (event-loop contract) |
| `norpagent/loops/nasyncio.py` | the default loop implementation: NasyncioLoopRuntime (adapter for the in-house nasyncio core, zero asyncio dependency) |
| `norpagent/loops/std_asyncio.py` | compatibility shim for the old 0.7 module name (re-exports StdLoopRuntime; does not import asyncio) |
| `norpagent/loops/__init__.py` | the `norpagent.nasyncio()` architecture function |
| `norpagent/nasyncio.py` | the in-house async-I/O core (formerly nasync_io, now packaged): event loop / Future / Task / sync primitives / subprocesses, no standard-asyncio dependency |
| `norpagent/frontends/base.py` | the Frontend protocol (frontend contract) |
| `norpagent/frontends/web.py` | the default frontend: Web (HTTP + SSE; page = front.html) |
| `norpagent/frontends/console.py` | console frontend: a command-line REPL (explicitly selected) |
| `norpagent/frontends/headless.py` | headless frontend: pure API, prints output to stdout |
| `norpagent/runtime/mount.py` | slot implementations → registry assembly (default-logic registration) |
| `norpagent/runtime/engine.py` | NorpEngine: lifecycle state machine + thread orchestration |
| `norpagent/runtime/__init__.py` | launch / stop / current / submit / shutdown |
| `norpagent/kernel/agent.py` | AgentRuntime: the agent loop itself (replaceable) |
| `norpagent/kernel/registry.py` | the registry (one of the minimal-kernel modules) |
| `norpagent/kernel/events.py` | the event bus (one of the minimal-kernel modules) |
| `norpagent/kernel/presets.py` | declarative Preset configuration |
| `norpagent/protocols/*` | all component protocols (interface contracts) |
| `norpagent/hooks/*` | the 9-layer, 29-hook system |
| `norpagent/security/*` | the security system (norpagent.safe()) |
| `norpagent/plugins/*` | the plugin system (signature / audit / isolation) |
| `norpagent/builtin/*` | built-in components (also registered in the registry; replaceable like any other) |
| `norpagent/modes/*` | the four preset modes |
| `norpagent/flows/` | the FLOW orchestration kernel (registry snapshots / files-as-modules / topology execution) |
| `norpagent/cli.py` | the `norpagent` command-line entry |

---

### 2.6 Modularity Conventions: Layered Dependencies and Extension Points

#### 2.6.1 Dependency Direction: Unidirectional Downward

Bottom-up dependency relations across all modules (higher layers may import
lower layers; lower layers must never import higher layers):

| Layer | Module | Allowed dependencies |
|---|---|---|
| L0 contracts | `protocols/*` | other protocols only (zero framework dependencies) |
| L0 core | `nasyncio.py` | standard library only (self-contained in-house async core) |
| L0 minimal kernel | `kernel/events.py`, `kernel/registry.py` | stdlib + protocols (registry references the Plugin / Tool protocols) |
| L1 hooks | `hooks/*` | `kernel.events` only (the structured bus view) |
| L1 security | `security/*` | zero framework dependencies (pure decision modules + optional cryptography) |
| L2 plugins | `plugins/*` | `protocols` + `security/*` + `hooks.core` (the pipeline layer) |
| L2 kernel loop | `kernel/agent.py` | `hooks.core` + `kernel/*` + `loops.cancel` + `protocols/*` |
| L2 built-ins | `builtin/*` | `protocols/*` (+ `loops.cancel` for sandboxes) |
| L2 modes | `modes/*` | `kernel.presets` only |
| L3 architecture | `arch/*` | itself only (address / slots / layer) |
| L3 loops | `loops/*` | `arch` + `nasyncio` |
| L3 frontends | `frontends/*` | `frontends.base` only |
| L4 assembly | `runtime/*` | arch + builtin + kernel + modes (the only assembly point that "knows everything") |
| L4 entry | `__init__.py` / `cli.py` / `__main__.py` | everything |

Key rules:

- **The kernel is trimmable**: the `kernel` modules do not import `security` /
  `plugins` / `builtin` at module level — security is injected as
  `registry.security` and the guard module is lazily imported only when
  task-level parameters explicitly ask for scanning; plugins are injected via
  `register_plugin`. The embedded scenario (14.2) relies on exactly this rule
  to keep sqlite3 / http.server and the like out of the kernel;
- **Built-in components are ordinary implementers**: `builtin/*` depends on
  protocols only, is on fully equal footing with third-party components, and
  is resolved by name through the registry;
- **Protocols and implementations are separated**: components talk only
  through the interface contracts in `protocols/*` (model / tool / session /
  sandbox / scheduler / ui / plugin); any implementation that satisfies a
  protocol can join;
- `runtime.mount` is the single default assembly point: presets (modes) and
  built-in components (builtin) are assembled into the registry by the slot
  table (arch/slots);
- `safe.py` sits at the low layer together with `security/*`: the security
  system can be tested and used outside the framework, and the kernel only
  learns about it through injection points (Chapter 10).

#### 2.6.2 Four Kinds of Extension Points

From least to most invasive, **all without modifying framework core code**:

| Extension point | How | Chapter |
|---|---|---|
| Event subscription | `reg.hooks.*.subscribe` / `reg.bus.subscribe` | Chapter 9 |
| Component replacement | slot addresses (model / tools / session / sandbox / frontend / loop ...) | Chapter 3 |
| Generic components | `register_component(kind, name, factory)` + preset components | 2.6.3 |
| Brand-new slots | `register_slot(SlotSpec(...))` | 3.8 |
| External plugins | standalone files / manifest packages, loaded by the security pipeline | Chapter 11 |
| Security policy | `safe()` runtime policy + standalone APIs | Chapter 10 |
| Loops / execution structure | method overrides or the agent_runtime slot | 9.6 |

"Zero framework core modifications" is a design red line: all extensions go
through slots / hooks / the registry — a corollary of the "four minimal-kernel
modules" of 2.3: everything beyond the minimal kernel has an established
replacement channel.

#### 2.6.3 Generic Component Namespace

Besides the six dedicated namespaces (model / tool / session / sandbox /
scheduler / ui), the Registry provides an open generic-component namespace:

```python
reg.register_component("context_store", "my_store", lambda: MyStore())
reg.register_component("my_kind", "my_impl", factory)   # kinds themselves are open

# reference from a preset
Preset(name="mine", ..., components={"context_store": "my_store",
                                     "my_kind": "my_impl"})

reg.build_component("my_kind", "my_impl")               # build (factory call)
reg.build_component("context_store", "my_store",
                    workspace_root=path)                # inject the workspace root by signature
reg.list_components()                                   # list all kinds
```

Context stores / project management / task storage and every other "additional
capability" live here; the framework can gain new component kinds without any
kernel change. When the factory declares a `workspace_root` parameter (or
`**kwargs`), the workspace root is injected automatically.

#### 2.6.4 Standard Flow for Adding a Component Module (Five Steps)

Take "add a session implementation" as the example:

1. **Write the protocol** (if absent): define the interface contract under `protocols/`;
2. **Write the implementation**: create the module, depending on protocols only
   (follow the style of builtin/sessions/);
3. **Register**: `reg.register_session("redis", factory)`, or let runtime.mount
   / your own assembly code register it;
4. **Declare usage**: `session="redis"` in a preset, or at startup
   `npa(session="redis")` / the address string `npa(session="myapp.redis:create")`;
5. **Hook up events** (optional): publish / subscribe events through the
   registry inside the implementation.

The equivalent manual-assembly path: `Registry() + register_* +
AgentRuntime(...)` (section 17.1), fully isomorphic to npa() assembly —
npa() merely automates these five steps.

---

## Chapter 3 Architecture Layer and Address Functions

Replacing any component: fill a new address into the corresponding slot; no
framework core code is modified.

### 3.1 What Is a Slot

Every building block of an agent application is a slot (an assembly point):

```python
from norpagent.arch.slots import SLOT_SPECS, all_slot_names

print(all_slot_names())
# ['async_loop', 'agent_runtime', 'model', 'tools', 'session', 'sandbox',
#  'scheduler', 'context_store', 'project_manager', 'hooks', 'security',
#  'plugins', 'frontend', 'ui', 'preset', 'logger', 'storage', 'error_handler']
```

There are **18 built-in slots** in total (a framework structural contract;
protected — their specs cannot be unregistered / overridden). The slot table
itself is hot-pluggable: third parties can call `register_slot()` at runtime
to register **custom slots** (name / semantics / assembly logic fully
custom); registration joins the complete pipeline — see section 3.8. Every
slot has a spec (SlotSpec): name, responsibility, protocol, default
implementation, string semantics and factory-parameter conventions:

```python
from norpagent.arch.slots import get_slot

print(get_slot("async_loop").format_help())
# [async_loop] Event-loop system: the async scheduling core the agent runs on.
#   (equivalent to the architecture function norpagent.nasyncio())
#   Protocol: the LoopRuntime protocol (norpagent.loops.base.LoopRuntime): ...
#   Default: norpagent.loops.nasyncio:NasyncioLoopRuntime
#   String semantics: address
#   Factory param layer: the owning architecture layer
#   Factory param config: the slot's extra configuration dict
#   Example: npa(async_loop='norpagent.loops.nasyncio:NasyncioLoopRuntime')
```

### 3.2 Address Functions: Default When Empty, Mount When Filled

A slot value comes in four shapes:

| Shape | Form | Semantics |
|---|---|---|
| Not filled (None) | `npa()` | use the library's built-in default logic |
| String address | `npa(async_loop="pkg.mod:attr")` | load the file by address and mount the implementation |
| Callable | `npa(async_loop=MyLoop)` | mount a factory / class directly |
| Instance / value | `npa(async_loop=loop_instance)` | mount an existing object directly |

String-address resolution rules (`norpagent.arch.address.resolve_address`):

1. `"pkg.mod"` — loads that **file (module)**. It prefers the conventional factory
   attributes inside the module: `create` → `build` → `default`; if none exist,
   the **whole module** is mounted as the implementation;
2. `"pkg.mod:attr"` — loads the file and takes the named attribute inside the module;
3. `"pkg.mod:attr;key=value;key=value"` — extra config after the semicolon, injected
   into the factory's `config` parameter (e.g. `"norpagent.frontends.web:WebFrontend;port=9000"`).
   The semicolon clause is stripped before address resolution; the sub-config does
   not interfere with module-path resolution.

An address string points at a module file: the architecture layer loads the file
(or the object inside it) and mounts it into the slot.

Slot mounting parameter example (the `html` clause of the frontend slot):

```python
# Replace the / route's default page with a custom HTML file (without physically overwriting library files)
npa(frontend="norpagent.frontends.web:WebFrontend;html=/path/to/my.html")
```

### 3.3 String Semantics

For some slots the string value is not an address but a "registry component name". Each slot
declares its own string semantics in its SlotSpec:

| Semantics | Meaning | Slots |
|---|---|---|
| `address` | string = module address | async_loop, agent_runtime, frontend, context_store, project_manager |
| `name` | string = registry component name | tools (container semantics, see below) |
| `name_or_address` | try by name first, then by address | model, session, sandbox, scheduler, ui, preset |
| `literal` | string = literal value, address first | security (level), storage (path), hooks, plugins, logger, error_handler |

Here: `"mock"` in `npa(model="mock")` is a model name in the registry;
the string in `npa(model="myapp.model:create")` is an address.
`npa(session="sqlite")` references the built-in SQLite session component;
`npa(session="myapp.sessions:create")` loads a custom session implementation by address.

**v0.9.1: all slots support address loading + values inside dict values support pure-address resolution**

1. `name` / `name_or_address` slots: the string is looked up in the registry first;
   if not found it is loaded as a module address (`pkg.mod[:attr]`) — ui / preset have
   been upgraded from plain `name` to `name_or_address`: `npa(ui="myapp.render:create")`,
   `npa(preset="myapp.presets:build")` mount the implementation by address directly;
2. `literal` slots are "address first": a string **shaped like a pure address**
   (dotted identifier containing `.` or `:`, structurally judged by
   `norpagent.arch.address.is_address_like`) is loaded by address (resolution failure
   raises `AddressError`, no silent fallback); anything else keeps its literal value —
   `npa(security="high")` is still a level, `npa(storage="./data")` is still a path,
   while `npa(security="myapp.sec:build_kit")` /
   `npa(storage="myapp.store:create;root=./x")` load by address;
3. **values inside dict values support pure-address resolution**: any slot's dict-form
   value is processed uniformly (tools mappings / hooks mappings / custom-slot dict
   values, nested dicts recurse): if a value is a pure-address string it is resolved
   to an object by address (resolution failure raises `AddressError`)
   — `tools={"my_tool": "myapp.tools:create"}`,
   `hooks={"before_model_call": "myapp.guard:fn"}`. Resolved callables are called per
   the factory convention (layer / slot / config context injected, `;key=value`
   clauses parsed as factory config); **except the hooks slot** — its values are
   "callbacks themselves", and the callback function pointed to by an address is kept
   as-is, not called;
4. tools slot container: list elements support addresses just like a single string —
   `tools=["myapp.tools:create"]`, `tools="myapp.tools:create;tag=x"`;
   other string elements remain references to registered tool names (e.g. `tools=["echo"]`).

### 3.4 Factory Call Convention: Signature-Based Injection

When address resolution yields a **callable** (class or function), ArchLayer calls it
per `norpagent.arch.layer.call_factory`:

1. inspect the factory signature;
2. inject the context keys **the factory declared** (`layer` / `slot` / `config` /
   plus slot-specific keys, see Appendix A);
3. keys the factory did not declare are **silently ignored** (including factories that
   accept no context at all: called with no arguments);
4. non-callable objects (modules / instances / values) are **used as-is**, never called.

The following three forms are equivalent:

```python
# 1. class: no context declared -> instantiated with no arguments
class MyLoop:
    def __init__(self):
        ...

npa(async_loop=MyLoop)

# 2. factory function: declares config -> injected automatically
def create(config=None, **kw):
    return MyLoop(timeout=float((config or {}).get("timeout", 0)))

npa(async_loop=create)

# 3. string address + extra config clause
npa(async_loop="myapp.loop:create;timeout=5")
```

### 3.5 ArchLayer: Observable Assembly Manifest

Every `npa()` internally builds an ArchLayer and `connect()`s it.
The assembly result is observable:

```python
eng = npa.current()
print(eng.layer.describe())
```

Example output:

```
== NorpAgent architecture-layer assembly manifest ==
  async_loop       <- default logic                         => NasyncioLoopRuntime
  agent_runtime    <- default logic                         => type
  model            <- default logic                         => (not connected)
  ...
  frontend         <- address 'norpagent.frontends.headless:HeadlessFrontend' => HeadlessFrontend
  preset           <- address 'minimal'                 => str
```

`(not connected)` means the slot was not specified and is handled by the preset's
declared default logic.

### 3.6 Example: Replacing Multiple Slots

```python
import norpagent as npa

# model = openai_compat, session = sqlite, sandbox = pooled, frontend = Web (port 9000),
# loop = custom implementation, security level = high. All specified via slot parameters.
npa(
    preset="standard",
    model="openai_compat",              # name reference
    session="sqlite",                   # name reference
    sandbox="pooled",                   # name reference
    frontend="norpagent.frontends.web:WebFrontend;port=9000",
    async_loop="myapp.nasync_loop:create",
    security="high",
)

while True:
    if npa.stop():
        break
```

### 3.7 Runtime Hot Mount: Any Slot Can Be Replaced

After `npa()` starts, **the engine keeps running**; replace any slot implementation at
any time, no restart needed:

```python
import norpagent as npa

npa()                                        # start (default Web frontend)
# ... application running ...

npa.remount(model="openai_compat")           # swap the model: takes effect on the next run
npa.remount(tools=["echo", "get_time"])      # swap the tool set: takes effect on the next run
npa.remount(session="sqlite")                # swap session storage: AgentRuntime hot rebuild
npa.remount(security="high")                 # swap the security level: old guard hooks unsubscribed first
npa.remount(frontend="norpagent.frontends.console:ConsoleFrontend")
npa.remount(async_loop="myapp.loop:create")  # swap the event loop: stop old, start new
npa.remount(model="myapp.model:create")      # replace a module file at runtime (hot reload)
```

Underlying chain: `npa.remount()` → `engine.remount()` → `ArchLayer.remount()`.
Before re-resolving a string address, the **module cache and .pyc bytecode cache are
invalidated**, so "edit the module file → remount" swaps in the changed code at runtime
without restarting the process.

Replacement semantics grouped by slot:

| Group | Slots | How it takes effect |
|---|---|---|
| Component slots | model / tools / hooks / security / plugins | remounted onto the registry and the final preset is rewritten; model / tools take effect on the next run() (the agent loop re-resolves the model and tool schemas on every run); repeatedly mounted architecture-level subscriptions are unsubscribed first then remounted, duplicate firing never stacks |
| Assembly slots | session / sandbox / scheduler / ui / agent_runtime / preset / context_store / project_manager | AgentRuntime hot rebuild: stop the old runtime (release sandboxes / components / unsubscribe the renderer) → build the new runtime per the current assembly → rebind the renderer on the frontend (the HTTP port stays the same) (in-flight task race and drain recommendation: see below) |
| Infrastructure slots | frontend / async_loop | stop the old implementation, start the new one; if the new implementation fails to start, the old one is rolled back automatically. On async_loop replacement, in-flight tasks on the old loop are abandoned — replace when idle |
| Base-service slots | logger / storage / error_handler | engine references updated directly, effective immediately |

**In-flight task race of assembly-slot hot rebuilds (Drain note)**: assembly-slot
remount goes through "stop old → build new → rebind frontend"; **none of these three
steps waits for in-flight `agent.run` tasks in the worker pool**. If the hot rebuild
happens while a task is executing:

1. `old.shutdown()` has closed the old sandbox; the in-flight run's next tool call
   hits a closed sandbox (failure or undefined behavior);
2. there is a window between unsubscribing the old renderer and subscribing the new
   one in which the in-flight run's events are lost; after the rebind the new data
   source receives **leftover events of the old run**, interleaved with the new run's;
3. the in-flight run's result is still returned to its submit caller — a result from
   a "dead runtime";
4. when the session slot is unchanged, old and new runs write the same session store
   (history stays continuous); when sandbox / scheduler / ui slots are swapped, the
   old instances referenced by the in-flight run have already been closed.

**Recommendation (production): two-phase hot mount (drain)** — ① first block new
tasks from entering (the business side maintains its own drain flag, checked before
`submit`); ② `loop.interrupt()` sets the cancel event of every in-flight task and
gives the worker pool a join grace period (e.g. 2s); ③ tasks that fail to exit in
time are covered by the sandbox-close semantics (PTC / pooled sandboxes force-kill
the process tree); ④ only then run the assembly-slot remount. The `interrupt()`
infrastructure already exists (`engine.request_stop` calls it as its first step), so
the implementation cost is low. Management-plane operations (config changes / component
swaps) are best done when tasks are idle; **the current framework version does not
ship built-in drain** — it is the business side's responsibility.

#### 3.7.2 Hot-Mounting Frontend Pages (html / flow_html parameters)

`frontend` is an infrastructure slot whose replacement semantics are "stop old, start
new". Together with WebFrontend's `html` / `flow_html` mounting parameters, the `/`
route page or the `/flow` module-flow page can be swapped at runtime — no process
restart, refresh the browser to see the new page:

```python
import norpagent as npa

npa(html="front.html")                       # start and mount a custom main page
# ... edit front.html or switch to another page file ...
npa.remount(frontend="norpagent.frontends.web:WebFrontend;html=front.html")
# the port stays the same; refreshing the browser (or reopening http://127.0.0.1:8787/) shows the new page

npa.remount(frontend="norpagent.frontends.web:WebFrontend;flow_html=flow.html")
# swap the /flow module-flow orchestration page (the official mounting path for norp-flow.html)
```

Parameter priority: keys **explicitly given** by remount override startup parameters;
keys **not explicitly given** (e.g. port) reuse the startup parameters — so when only
the page changes, the browser URL stays the same. Explicit-key detection: for string
addresses take the keys in the `;key=value` clause; for instances take constructor
parameters whose values differ from defaults (html / flow_html judged by the
`_html` / `_flow_html` attributes). For example:

```python
npa.remount(frontend="norpagent.frontends.web:WebFrontend;port=9000")  # change the port (restart HTTP listening)
npa.remount(frontend="norpagent.frontends.web:WebFrontend;html=")      # reset the main page to the library built-in
npa.remount(frontend="norpagent.frontends.web:WebFrontend;flow_html=") # reset /flow to the library built-in
from norpagent.frontends.web import WebFrontend
npa.remount(frontend=WebFrontend(html="front.html"))                   # instance form
npa.remount(frontend=WebFrontend(flow_html="flow.html"))               # instance form
npa.remount(frontend="front.html")     # HTML-path direct mount: equivalent to WebFrontend;html=front.html
```

**remount page hot-replace keys (v0.9, the simpler page-swap entry)**: `html` /
`flow_html` are not slots themselves but mounting parameters of the frontend slot —
`npa.remount()` accepts these two keys directly and swaps the page immediately via
`mount_page` **without going through "stop old frontend / start new frontend"**
(the HTTP service is not restarted, the port stays the same; refresh the browser to
see the new page):

```python
npa.remount(flow_html="flow-v2.html")       # /flow page swapped immediately (HTTP not restarted)
npa.remount(html="front-v2.html")           # / main page swapped immediately
npa.remount(flow_html="<html>...</html>")   # HTML content passed directly (leading "<" = content)
npa.remount(flow_html=None)                 # unmount, fall back to the library built-in norp-flow.html
npa.remount(flow_html="", html="")          # "" has the same semantics as None (unmount)
npa.remount(flow_html="flow-v2.html",
           frontend="norpagent.frontends.web:WebFrontend")  # composable: set parameters first, then swap the frontend
```

Semantic details:

1. the value is first written into `engine.params` (the same data path as the
   `npa(html=...)` startup passthrough); later frontend hot mounts / attach reuse the new value;
2. when the current frontend is the Web frontend, the page is swapped immediately via
   `mount_page`; for non-Web frontends (console / headless) only the parameter is
   updated, with no side effects;
3. bad paths fail fast with **pre-validation** (`ValueError`), leaving neither the
   slot change nor the page in a half-done state;
4. if the user registered a custom slot of the same name with `register_slot()`, the
   slot table takes priority
4. if the user registered a custom slot of the same name with `register_slot()`, the
   slot table takes priority (handled per the slot's semantics);
5. `remount(port=...)` / `remount(host=...)` and other network parameters are still
   not page keys — they error out and hint at the address-clause form (which restarts
   HTTP listening).

**Two mounting forms of the frontend slot (v0.9, equivalent coexistence)**:

1. Address form: `npa(frontend="norpagent.frontends.web:WebFrontend;html=...")`
   — module address + clause parameters;
2. HTML-path direct mount: `npa(frontend="front.html")` — when the slot value itself
   is a `.html/.htm` file path (with no `;` clause), the architecture layer no longer
   resolves it as a module address; the assembler automatically converts it to
   `WebFrontend(html=<that path>)`. A nonexistent file raises `ValueError` and fails
   fast (no silent fallback to the default frontend).

Note: HTML-path direct mount only affects the `/` main page; to swap the `/flow`
page use the `;flow_html=...` clause or `WebFrontend(flow_html=...)`.

**Swapping pages directly at runtime (HTTP service not restarted, port unchanged)**:

```python
# Way one: remount page hot-replace keys (recommended, v0.9)
npa.remount(flow_html="flow.html")           # /flow swapped immediately
npa.remount(html="front.html")               # / main page swapped immediately
npa.remount(flow_html=None)                  # unmount, fall back to the library built-in

# Way two: frontend instance API
eng.frontend.mount_page("flow", "flow.html")   # /flow swapped immediately
eng.frontend.mount_page("flow", None)          # unmount, fall back to the library built-in
eng.frontend.mount_page("front", "<html>...</html>")  # same, for /
# equivalent entry: WebUI.mount_page(page, html)
```

**Physically replacing library HTML files takes effect automatically**: page byte
caches are validated by the resource file's mtime/size signature — overwrite
`norpagent/builtin/ui/assets/front.html` or `norp-flow.html` directly and refresh
the browser to see the new page (no remount, no restart); on a cache hit only a
single stat check runs, with no open+read disk I/O.

Notes: `npa.remount()` is an **in-process API**; it must be called in the same Python
process that started the engine (it does not work across processes). When running in
cmd, put the remount inside the lifecycle loop or start a thread reading stdin to
implement "type a command to swap the page".

Notes:

1. it may only be called in the engine RUNNING state, otherwise `EngineError` is
   raised; illegal slot names also raise;
2. `remount(slot=None)` clears that slot's configuration (falls back to default logic);
3. preset object identity: after a hot mount, `registry.resolve_preset(name)` and
   `engine.agent.preset` remain the same instance (the frontend's hot rewriting of
   preset.tools relies on this convention);
4. `agent_runtime` is a `defer_factory` slot: the factory call is deferred to the
   engine assembly phase (after the registry / preset context is ready); the address
   clause `;key=value` is injected into the factory's config via `ArchLayer.subconfig()`.

### 3.8 Hot-Pluggable Slot Table: Registering Custom Slots

`npa.remount()` swaps a slot's **implementation**; the slot table itself (`SLOT_SPECS`)
is also hot-pluggable — third-party libraries can register **brand-new custom slots**
at runtime, and registration plugs into the full pipeline (`npa()` parameter validation,
ArchLayer assembly, `npa.remount()` hot replacement, `layer.describe()` listing) with no
framework-source changes and no process restart:

```python
from norpagent.arch import SlotSpec, register_slot, unregister_slot

# custom slot = name + string semantics + application logic (applier)
register_slot(SlotSpec(
    name="audit_tag",                # slot name = npa()'s keyword-argument name
    description="audit tag",
    protocol="literal string",
    string_semantics="literal",      # address / name / name_or_address / literal
    applier=_apply_audit_tag,        # called by the assembler when the slot value is non-empty
))
```

```python
import norpagent as npa

npa(audit_tag="release-1")            # applied at assembly time
npa.remount(audit_tag="release-2")    # hot-replaced at runtime (the applier re-runs)
```

The `applier(reg, layer, value, params, ctx)` contract:

- `value` is the resolved slot value: for `address` semantics it is the instantiated
  implementation (the sub-config `;key=value` is obtained via `layer.subconfig(slot)`);
  for `name` / `name_or_address` / `literal` semantics it is the raw value;
- `ctx` provides four mutable containers: `components` (final-preset component
  declarations {kind: name}), `extras` (engine extra objects, consumed via
  `engine.extras[slot_name]`), `overrides` (preset-field overrides), `meta`
  (registry architecture metadata recording mountable/unsubscribable objects);
- **the same registry may be called repeatedly** (assembly + every `npa.remount`), so
  the applier must be reentrancy-safe: repeated runs must not stack side effects —
  objects subscribed to the event bus are unsubscribed per `ctx["meta"]` records and
  then remounted (see the built-in hooks / security / plugins slots);
- `remount_rebuild_agent=True`: hot-rebuild the AgentRuntime after a hot replacement
  (assembly-type slots whose applier registers generic components into the preset's
  `components` should set True); default False: takes effect on the next run() or
  only updates extras.

Full example — registering a generic-component custom slot (the same assembly channel
as the built-in context_store):

```python
from norpagent.arch import SlotSpec, register_slot


def apply_vector_store(reg, layer, value, params, ctx):
    name = "_arch_vector"
    factory = value if callable(value) else (lambda v=value: v)
    reg.register_component("vector_store", name, factory)
    ctx["components"]["vector_store"] = name   # the preset declares the component
    ctx["extras"]["vector_store"] = value


register_slot(SlotSpec(
    name="vector_store",
    description="vector retrieval component (custom assembly slot)",
    protocol="any implementation (registered as a vector_store generic component)",
    string_semantics="literal",
    applier=apply_vector_store,
    remount_rebuild_agent=True,     # hot rebuild after hot replacement; the component takes effect immediately
))

npa(vector_store=MyVectorStore())    # assembly: engine.agent.components["vector_store"]
npa.remount(vector_store=Other())    # hot replacement: AgentRuntime hot rebuild
```

Protection and validation rules:

| Rule | Note |
|---|---|
| The 18 built-in slots are protected | cannot be registered / spec-overridden / unregistered (framework structural contract: engine, frontend, documentation references). Their **values** can be hot-replaced with `npa.remount` at any time |
| Slot-name legality | a legal Python identifier (`npa()` keyword argument), not a keyword, not `prompt` / `config` (launch special keys) |
| Duplicate names | raise `SlotError`; `register_slot(spec, replace=True)` hot-replaces the spec of a same-named custom slot (default address / semantics / applier / rebuild flag) |
| Illegal specs | a non-callable applier or an illegal `string_semantics` raises `SlotError`; a failed replace does not break the old spec |
| Unregister | `unregister_slot(name)` unregisters a custom slot and returns its spec; afterwards `npa.remount(that_slot)` reports an unknown slot and `npa(that_key=...)` falls back to a task parameter; already-mounted implementations stay as they are |
| Late registration | slots registered after the engine started: `layer.connect()` idempotently fills in (only connects missing slots), or directly `npa.remount(slot=value)` goes through the full pipeline |

Top-level API: `npa.register_slot` / `npa.unregister_slot` /
`npa.SlotSpec` / `npa.SLOT_SPECS` / `npa.is_builtin_slot` /
`npa.snapshot_slots`; slot-table operations are thread-safe (RLock-protected; assembly
and hot mounts iterate over snapshots).

---

### 3.9 Task-Level Slot Injection: submit(slot_overrides=...)

`npa()` startup assembly and `npa.remount()` hot mounts are both **global** dimensions:
one change affects all subsequent tasks. Task-level slot injection is the third
dimension — temporarily overriding any slot implementation for the duration of a
**single task**, without affecting global configuration and without blocking other
in-flight tasks:

```python
import norpagent as npa

engine = npa(preset="standard")

# single task: temporarily swap the model + tools
r = engine.submit(
    "analyze this code",
    slot_overrides={
        "model": "anthropic",
        "tools": ["run_python", "file_read", "echo"],
        "sandbox": "isolated_python",
        "max_steps": 64,          # non-slot key: automatically falls back to a task parameter
    },
)
```

#### 3.9.1 Syntax and the Full Key Set

`engine.submit(text, session_id=None, task_params=None, slot_overrides=None)`
(the top-level `npa.submit(...)` supports the same). The keys of `slot_overrides`
match `npa()`'s slot parameters exactly (14 task-overridable keys):

| Key | Task-level semantics | Takes effect |
|---|---|---|
| `model` | swap this task's model provider (registered name / address / instance) | this run's model calls |
| `tools` | swap this task's tool set (registered-name list / addresses / Tool instances / {name: instance} mapping) | this run's schemas and tool execution |
| `sandbox` | a standalone temporary sandbox (registered name / address / instance), closed when the task ends | this run's tool execution |
| `session` | a standalone temporary session store (registered name / address / instance / `{"name": ..., "persist": True}`), by default does not pollute the global session table | this run's L4 session |
| `scheduler` | a standalone temporary scheduler (registered name / address / instance), closed when the task ends | this run's subtask submission |
| `hooks` | task-period hook subscriptions ({hook name: callback} or callable(registry)), unsubscribed when the task ends | this run's whole lifecycle |
| `security` | task-period security policy (level / dict / SecurityContext / callable), the original policy is restored when the task ends | this run's approvals / guards |
| `agent_runtime` | start a standalone Runtime instance for this task, destroyed after execution (does not affect the engine's default Runtime) | this task |
| `context_store` / `project_manager` | temporary generic components (registered component name / address / instance), closed when the task ends | this run's ctx.components |
| `async_loop` | this task executes on a standalone temporary event loop (no contention with the main loop's worker pool) | this task |
| `logger` / `storage` / `error_handler` | injected into this task's parameter context (params), readable by component factories and hooks (see 3.9.5) | this run |

Value forms match `npa()` slots exactly: registered-name references / module addresses
(`pkg.mod[:attr]`, including `;key=value` clauses) / factories / instances; resolution
failure raises `AddressError`.

**Non-slot keys automatically fall back to task parameters**: when a key in
`slot_overrides` is not among the 14 keys above (e.g. `max_steps` / `task_timeout` /
`mock_script`), it is automatically merged into `task_params` and passed through to
the agent loop — the same data path as `npa()`'s "slot-key split, the rest pass through
as parameters", so `slot_overrides={"max_steps": 64}` works out of the box.

**Keys that cannot be task-level overridden**: `frontend` / `ui` / `plugins` / `preset`
are process-level or engine-level structures (the I/O shell, the renderer, the plugin
loader, the component-composition baseline) and fall outside a single task's override
boundary; passing them falls back to task parameters (no error, but also no slot-override
effect — use `npa.remount` instead).

#### 3.9.2 Priority: Task-Level > remount > Startup Assembly > Preset

| Level | Source | Priority |
|---|---|---|
| 1 | `submit(slot_overrides=...)` | highest |
| 2 | `npa.remount(slot=...)` | second |
| 3 | startup `npa(slot=...)` | third |
| 4 | preset declarations | lowest |

Task-level overrides take a **snapshot at submit() time**; later global `npa.remount`
does not affect in-flight tasks (3.9.3). This complements "Drain + remount": if you
do not want to wait for draining, override; if you do not want to override, drain and
then remount.

#### 3.9.3 Implementation Boundary and Isolation Semantics

Implementation boundary (no kernel-loop changes, only one extra resolution layer):

1. `AgentRuntime.run()` accepts a `slot_overrides` dict at its entry;
2. a slot snapshot layer (`_TaskSlotLayer`) is created for this task and stored in
   `TaskContext` (`ctx.task_slot_layer` / `ctx.slot_overrides`);
3. during the `run()` lifecycle, all component resolution paths (model / tools /
   sandbox / session / scheduler / context_store / project_manager) **check the task
   layer first**, falling back to runtime defaults when not overridden;
4. when the task ends, the task layer is released together with the RunResult
   (`finally` fallback): all temporary sandboxes / sessions / schedulers / components
   are `close()`d, task-period hook subscriptions are unsubscribed, the temporary
   security policy is unloaded and the original `registry.security` is restored — no
   residual state.

**Relation to global remount (isolation semantics)**:

| Scenario | Global slot | Task override | What this task sees | What other tasks see |
|---|---|---|---|---|
| no override | model=A | — | model=A | model=A |
| model overridden | model=A | model=B | model=B | model=A |
| hot rebuild after override | model=A | model=B | model=B (this task still uses its own snapshot) | model=C (new tasks) |
| override cancelled | model=A | task ends | — | model=A |

Key semantics: a task-level override takes a slot snapshot at submit() time; later
global remounts do not affect in-flight tasks.

**agent_runtime override**: a standalone Runtime instance is started for this task
(constructed with the same factory-calling convention as `_build_agent`: registry /
preset / ui / task_params / layer / config injected by signature), destroyed after
execution; the engine's default Runtime is unaffected. Note: the child runtime shares
the same event bus and renderer as the default runtime, so task events may be rendered
once by each of their subscribed renderers (same behavior as `run_task` child agents —
an existing property of the shared bus).

**session override**: this task's dialog history is written to a standalone temporary
session store, not polluting the global session table — unless `persist=True` is
explicitly given:

```python
# temporary session: the session does not appear in the global session table
# temporary session: the session does not appear in the global session table
engine.submit("hi", slot_overrides={"session": "memory"}, session_id="s1")

# persist: write this task's history back into the global session table when the task ends
engine.submit("hi", slot_overrides={
    "session": {"name": "memory", "persist": True},
}, session_id="s2")
```

Note: disk-backed sessions (e.g. `sqlite`) build standalone instances, but if no
standalone database file is specified (address form `...;path=...`), records still
go to the default database file — for full isolation use the address form or an
instance value.

#### 3.9.4 Relation to Multi-Agent Orchestration

If you understand multi-agent as "multiple tasks independently configured with
different roles", task-level slot injection is the cleanest implementation — three
concurrent tasks, each with its own model + tools, without interference:

```python
import threading

futures = []
for key, ov in [
    ("write the plan", {"model": "claude", "tools": ["write"]}),
    ("review the code", {"model": "deepseek", "tools": ["read"]}),
    ("run the deployment", {"model": "mock", "tools": ["exec_cmd"]}),
]:
    t = threading.Thread(
        target=lambda k=k, o=ov: engine.submit(k, slot_overrides=o),
    )
    t.start()
    futures.append(t)
for t in futures:
    t.join()
```

Each task takes its own snapshot independently at submit time: concurrent tasks'
model / tools / session overrides do not affect each other, nor do they affect the
global configuration.

#### 3.9.5 Concurrency and Boundary Notes

- **zero registry pollution**: task-level model / tool instances are held directly by
  the snapshot layer and never `register_*`d into the registry; references are
  released when the task ends. Concurrent tasks' same-named tools each hold their own
  instance, never overwriting each other.
- **hooks / security are task-period temporary state**: subscribed / installed when
  the task starts, unsubscribed / restored when the task ends (including exception
  paths). The callable form of task-level security is managed by the caller itself
  (`registry.security`; the framework cannot track its internals); the string /
  dict / SecurityContext forms are restored automatically.
- **logger / storage / error_handler semantics are parameter injection**: task-level
  overrides of these three keys are injected into `params` (visible to component
  factory ctx and hook payloads), and do **not** replace engine-global references —
  avoiding concurrent tasks trampling engine-level objects.
- **concurrent override safety**: the snapshot layer is a per-task independent
  instance, thread-safe; any number of concurrent tasks on the same runtime each
  carry their own slot snapshot without interference.
- **submission-failure semantics**: resolution of task-level overrides (address
  loading etc.) happens at the `run()` entry (inside the worker thread); resolution
  failure raises `AddressError` / `ComponentError` which bubbles up at the blocking
  `submit()` return (same as ordinary task exceptions).

---

## Chapter 4 Event Loop System: norpagent.nasyncio()

### 4.1 The Loop System Is an Independent Architecture Function

The event loop determines how tasks are scheduled: which thread tasks run on, how
they are interrupted, and how they are woken up. NorpAgent provides the loop system
as an independent architecture function:

```python
import norpagent as npa

loop = npa.nasyncio()                       # default loop (self-developed nasyncio core)
loop = npa.nasyncio("myapp.loop:create")    # custom loop
```

It is equivalent to the slot:

```python
npa(async_loop="myapp.loop:create")   # equivalent to npa.nasyncio("myapp.loop:create")
```

`npa.nasyncio()` returns a **LoopRuntime** (protocol below). The scheduling core run
by the default implementation is the library's built-in **self-developed nasyncio
event loop** (`norpagent.nasyncio`, originally nasync_io, now packaged into the
library) — it **does not depend on or import the standard asyncio** (declaration and
reasons in 4.7). To use another event-loop implementation, implement the LoopRuntime
protocol and fill the `async_loop` slot with an address — no framework core changes.

> The top-level `norpagent.nasyncio` (i.e. `npa.nasyncio`) binds to the self-developed
> core **module** (callable): `npa.nasyncio()` returns the default LoopRuntime
> implementation; `npa.nasyncio.EventLoop` / `Future` / `Task` directly access core
> types; `import norpagent.nasyncio` yields the same core module. The architecture
> function itself lives in `norpagent.loops.nasyncio`.

### 4.2 The LoopRuntime Protocol

```python
class LoopRuntime(Protocol):
    name: str
    def start(self) -> None: ...          # start the loop (usually a dedicated internal thread running run_forever)
    def stop(self) -> None: ...           # request a stop (thread-safe)
    def is_running(self) -> bool: ...     # whether it is still running
    def join(self, timeout=None) -> None: ...   # wait for the loop thread to exit
    def submit(self, fn, *args, **kwargs) -> Any: ...
        # execute the synchronous function fn in the loop context and block returning its result
```

The engine (`norpagent.runtime.engine.NorpEngine`) interacts with the loop only
through this protocol and never imports any concrete loop implementation.

### 4.3 Default Implementation: NasyncioLoopRuntime (Self-Developed nasyncio Core)

The default implementation is based on the library's built-in **self-developed
nasyncio event loop** (no dependency on the standard asyncio): a dedicated thread
runs `norpagent.nasyncio.EventLoop` (run_forever), and `submit()` hands synchronous
functions to the **own daemon worker pool** and waits for the result (why not the
standard thread pool: see 4.6 and 4.7).

Configuration (embedded / high-concurrency tuning; see Chapter 14):

| Config | Note | Default |
|---|---|---|
| `max_workers` | daemon worker-pool thread count | `max(4, cpu_count)` |
| `poll_interval` | submit/run_async completion-poll interval (s) | `0.05` |

Passed via `npa(config={"loop": {"max_workers": 8}})` (or the environment variables
`NORPAGENT_MAX_WORKERS` / `NORPAGENT_SUBMIT_POLL`; equivalent forms
`npa.nasyncio(max_workers=8)` and `npa(async_loop="norpagent.loops.nasyncio:NasyncioLoopRuntime")`
share the same construction source).

```python
loop = npa.nasyncio()
loop.start()
result = loop.submit(lambda: 1 + 1)   # -> 2
loop.stop()
loop.join()
```

The optional `run_async(coro)` capability submits a coroutine to the loop thread via
the self-developed core's `run_coroutine_threadsafe` and blocks returning the result
(the engine defaults to submit(); this is for custom coroutine entry points).

### 4.4 Custom Loop Example

```python
# myapp/simple_loop.py -- loop implementation example (synchronous direct execution; useful for tests or embedded scenarios)
class SimpleLoop:
    name = "simple"

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
        return fn(*args, **kwargs)   # execute synchronously and directly


def create(**kw):                    # module-level factory (the address "myapp.simple_loop" hits it automatically)
    return SimpleLoop(**kw)
```

Mount it:

```python
import norpagent as npa

npa(async_loop="myapp.simple_loop", prompt="hi",
   frontend="norpagent.frontends.headless:HeadlessFrontend")
while True:
    if npa.stop():
        break
```

### 4.5 Cross-Thread Bridging Notes (Fixed in the Self-Developed Core)

**Item one (fixed in the self-developed core)**: the standard asyncio's
`Future.result()` is not a thread-safe blocking wait; cross-thread
`add_done_callback()` goes through `loop.call_soon` when the future is already
finished (only pushes to the `_ready` queue without writing the self-pipe), so a
loop blocked on the selector never gets the wakeup and the waiter hangs. The
library's built-in self-developed core (`norpagent.nasyncio.Future`) fixes both
pitfalls: completion notification from any thread goes through
`call_soon_threadsafe` (writes the self-pipe, waking the loop immediately). The
default runtime's `submit()` still uses the "executor thread writes the result +
threading.Event set" pattern — submit tasks may block for a long time, so running
them in the daemon worker pool, fully decoupled from the loop, is more robust
(unrelated to asyncio).

**Item two (run_async cross-thread waiting)**: `NasyncioLoopRuntime.run_async`
submits the coroutine to the loop thread via the self-developed core's
`run_coroutine_threadsafe` (internally call_soon_threadsafe + self-pipe wakeup, no
wakeup race), and waits with a concurrent.futures.Future done-callback + polling
Event set (concurrent.futures guarantees the callback fires synchronously in the
thread that wrote the result). Note that `run_async` cannot be called inside the
loop thread (a blocking wait would stall the loop) — `await` the coroutine directly,
or use `submit()` instead.

Rule: cross-thread coordination uses "executor thread writes the result +
threading.Event set"; the loop thread is not a necessary link in the wakeup path.

### 4.6 Ctrl+C and Task-Cancellation Semantics

#### 4.6.1 The Problem: the main thread is not inside the event-loop entry, so why might Ctrl+C fail

After `npa()` starts, the main thread only does lifecycle polling (`npa.stop()`); the
real worker threads execute tasks in the background, and the caller (e.g. the console
REPL's main thread) blocks on `loop.submit()`'s wait. Two pitfalls on the signal chain:

1. **On Windows a single `Event.wait()` never sees Ctrl+C**: SIGINT is delivered to
   the main thread as a pending interrupt, checked only at **bytecode boundaries**;
   when the main thread blocks in `Event.wait()` (the underlying
   `WaitForSingleObject` waits forever), it never returns to a bytecode boundary and
   Ctrl+C is as good as dead.
   **Solution**: `NasyncioLoopRuntime.submit()` uses **polling wait** (passing a
   bytecode boundary every ≤`poll_interval` seconds, default 0.05s — tightened from
   0.2s since 0.9 for lower task-completion perception latency; embedded scenarios
   can raise it), so Ctrl+C surfaces immediately as `KeyboardInterrupt`.
2. **Worker threads stuck in blocking I/O cannot be killed; the process freezes**:
   SIGINT reaches only the main thread; a worker thread stuck in a sandbox
   `subprocess` / HTTP request can only wait for its own timeout; worse, the standard
   thread pool (ThreadPoolExecutor, asyncio's default executor) registers its worker
   threads in CPython's `threading._threads_queues`, which are **force-joined** at
   interpreter exit — if a task never ends, the process cannot exit.
   **Solution**: the worker pool uses bare daemon threads (no join at exit);
   meanwhile the "cancel" signal is explicitly handed to the task body (see 4.6.2)
   so it exits by itself as early as possible.

#### 4.6.2 The Cancel Signal: contextvars + cancel event

`NasyncioLoopRuntime.submit()` wraps every task in a contextvars context carrying a
cancel event (`norpagent.loops.cancel`); the body can check it at any time:

```python
from norpagent.loops.cancel import cancel_requested, current_cancel_event

def my_tool(args, ctx):
    for chunk in fetch_stream(...):      # long task / long streaming read
        if cancel_requested():           # Ctrl+C / engine stop -> True
            return ToolResult(output="task cancelled", success=False)
```

Trigger paths (setting the cancel event):

| Trigger | Timing | Behavior |
|---|---|---|
| `KeyboardInterrupt` | the submit waiter receives Ctrl+C | sets this task's cancel event and bubbles the exception |
| `loop.interrupt()` | first step of `engine.request_stop()` | sets the cancel event of every in-flight task |
| `loop.stop()` | stopping the loop | same as above (calls interrupt internally) |

Built-in components' response to cancellation (since 0.7.0):

- **PTC sandbox** (isolated_python): the execution loop checks every ≤0.5s; on
  cancellation it immediately force-kills the child process and returns
  `exit_code=-1` (stderr notes "task cancelled");
- **pooled sandbox**: `run_shell` waits in slices (checks every ≤0.5s); on
  cancellation it kills the process tree and marks the instance damaged;
- **model calls**: `params["_cancel_event"]` is injected even when call_timeout=0
  (previously only the timeout path had it); the openai_compat streaming loop checks
  it on every chunk;
- **the agent main loop**: checks `cancel_requested()` at every step boundary and
  wraps up as `stopped` (on_task_stopped).

A cancel event merely *suggests* the body exit; if a task is stuck in an
uninterruptible system call (e.g. DNS resolution, a D-state process), the final
fallback is still each component's own timeout (SDK connection timeout /
call_timeout / ptc_timeout), and process exit is guaranteed by daemon threads.
**Note: the daemon worker pool itself has no task execution time budget and no
pool-level watchdog** — a stuck task occupies the whole pool; the boundary and
fallback matrix are in 4.6.4.

#### 4.6.3 Thread-Boundary Notes: what goes into the loop and what does not

`norpagent.nasyncio()` is the **architecture function of the async_loop slot**; its
default implementation (NasyncioLoopRuntime) runs the library's built-in
self-developed nasyncio event loop. All task scheduling in the library
(engine.submit → loop.submit) goes through its protocol. The remaining bare threads
are **deliberate blocking-I/O pumps** and should not enter the event loop:

| Thread | Duty | Why not the loop thread |
|---|---|---|
| `norpagent-loop-pool-*` | executes submit's synchronous tasks | the task body may block (sandbox/HTTP); putting it on the loop thread would stall the whole loop |
| `norpagent-nasync-loop` | runs the self-developed nasyncio event loop | the loop itself |
| sandbox pipe readers (PTC/pooled/plugin hosts) | read child-process stdout/stderr | blocking pipe reads, uninterruptible |
| `norpagent-webui` / request threads | HTTP service and requests | socketserver's own thread model |
| `norpagent-model-*` | call_timeout hard-interrupt watchdog | time-limited join; abandoned on timeout |

Rule: **computation and scheduling go into the loop (replaceable); blocking I/O uses
daemon thread pumps (not cancellable, but never block exit)**. Replacing the
`async_loop` slot swaps the whole loop system (protocol in 4.2) without touching any
other part of the framework.

#### 4.6.4 Daemon Worker-Pool Queue Semantics and the Stuck-Task Fallback (honest boundaries)

Semantic boundaries of the `NasyncioLoopRuntime` daemon worker pool (`_DaemonPool`):

- **unbounded queue, no rejection policy**: internally a `queue.Queue()` (no
  maxsize); `submit_nowait` enqueues with `put_nowait` — never blocks, never raises
  `Full`. When the pool is saturated, new tasks **pile up unboundedly** in the queue,
  and the caller's `submit()` waits forever in the `done.wait(poll_interval)` polling
  loop, with unlimited latency (no fast-fail);
- **cancellation is cooperative**: the cancel event only takes effect at boundaries
  the body actively checks (4.6.2); two scenarios cannot be interrupted — ① stuck in
  C-extension pure computation (e.g. `re` regex backtracking): the cancel event is
  visible only at bytecode boundaries; ② custom tools doing raw `Popen + communicate`
  (non-sandbox path) have no slice checks and no process-tree kill: stuck means stuck;
- **one stuck task -> throughput drops to zero**: each worker runs one task at a
  time, with no task execution time budget, no thread abandonment, and no watchdog;
  if a task gets stuck and occupies the whole pool, all subsequent submits pile up
  and business-side throughput approaches 0 — there is no spare thread underneath.
all subsequent submits pile up and business-side throughput approaches 0 — there is
no spare thread underneath.

**Existing fallback precedents (the "time budget + thread abandonment" pattern)**:

| Scenario | Fallback mechanism |
|---|---|
| model calls | `_call_model_with_timeout`: worker thread + `join(timeout)`; on timeout the thread is abandoned as an orphan (daemon, filtered and reclaimed on every run) |
| engine stop | `request_stop`: close task with `t.join(timeout=5.0)`; on timeout `_close()` runs in the current thread as a fallback |
| PTC / pooled sandboxes | the execution loop checks the cancel event in slices every ≤0.5s; on timeout / cancellation the process tree is force-killed |
| worker-pool tasks (bare tools / user tasks) | **none** — no timeout budget; a stuck task occupies the pool |

**Evolution suggestion (roadmap, not implemented)**: introduce a pool-level "task
execution time budget" — a deadline watchdog inside each worker that sets the cancel
event on timeout, marks the task abandoned, and force-kills the associated sandbox
process (reusing the model-call timeout's abandoned-thread pattern); optionally make
the pool a bounded queue or add a submit-timeout fast-fail (rejecting new tasks
instead of piling up unboundedly). For embedded scenarios, prefer splitting tasks
smaller and tightening component-level timeouts (call_timeout / ptc_timeout) rather
than relying on a pool-level fallback.

### 4.7 Explicit Declaration: norpagent Does Not Depend on the Standard asyncio; the Scheduling Core Embraces the Self-Developed nasyncio

**Declaration**: since 0.8 the norpagent library has **zero `import asyncio`**. The
default event-loop core is the self-developed async-IO library `norpagent.nasyncio`
packaged into the library (originally nasync_io, v2.0.0); its underlying dependencies
are only the **non-asyncio** modules of the Python standard library: `threading` /
`queue` / `heapq` / `selectors` / `socket` / `concurrent.futures` / `subprocess` /
`os` / `time`. Verify with `grep -R "import asyncio" norpagent/` — empty.

**Why embrace the self-developed nasyncio and drop the standard asyncio**:

1. **scheduling, cancellation and cross-thread wakeup semantics are fully defined by
   in-library code (control)**. The standard asyncio has well-known semantic
   pitfalls, e.g.:
   - `Task.cancel()` is not thread-safe (directly manipulates the loop thread's
     ready queue);
   - cross-thread `add_done_callback()` on a finished Future goes through
     `call_soon` without writing the self-pipe; a loop blocked on the selector
     never gets the wakeup, and the waiter hangs;
   - there is no external "cancel the main task" entry — an outside thread cannot
     force-interrupt a coroutine being awaited (stop latency depends on the current
     operation and can reach minutes).
   The self-developed core fixes each: `Task.cancel()` is cross-thread safe; Future
   completion notification automatically goes through `call_soon_threadsafe`
   writing the self-pipe; `EventLoop.abort_main()` provides thread-safe immediate
   stopping.
2. **the dependency surface shrinks to an auditable size**. All event-loop behavior
   (trampoline scheduling, the timer heap, socketpair self-pipe wakeup, cancellation
   penetration) is in-library code — the audit surface is one self-developed core
   file; it does not drag in the standard asyncio's internal implementation details
   and version differences (selector behavior differs across Python versions).
3. **exit semantics are controllable**. The standard thread pool is not used for
   submit: ThreadPoolExecutor (including asyncio's default executor) registers its
   worker threads in `threading._threads_queues`, which are force-joined at
   interpreter exit — if a task is stuck in a sandbox subprocess / HTTP call, the
   process freezes. The default runtime uses a bare daemon thread pool + self-pipe
   wakeup, so the process wraps up immediately after Ctrl+C (4.6.1).
4. **API semantics align; migration is zero-cost**. The self-developed core provides
   same-named APIs one-to-one with asyncio usage (`EventLoop` / `Future` / `Task` /
   `Event` / `Lock` / `Condition` / `sleep` / `wait_for` / subprocess wrappers /
   `run_coroutine_threadsafe`); code familiar with asyncio migrates by swapping
   `import asyncio` for `import norpagent.nasyncio`, and `CancelledError` /
   `TimeoutError` semantics stay consistent.
5. **the self-developed core works standalone**. `norpagent.nasyncio` itself is a
   usable miniature async library (originally nasync_io, packaged into the library)
   that can be imported and run independently of the norpagent framework; the
   framework merely plugs it into the `async_loop` slot through the LoopRuntime
   protocol.

**Compatibility**: the old 0.7 address `norpagent.loops.std_asyncio:StdLoopRuntime`
remains as a compatibility shim (re-exports the same implementation, does not import
asyncio); historical code keeps working. New code uses
`norpagent.loops.nasyncio:NasyncioLoopRuntime` (see 4.3).

```python
import norpagent as npa
import norpagent.nasyncio as core  # self-developed core module (callable)

print(core.__version__)          # 2.0.0
loop_rt = npa.nasyncio()          # default LoopRuntime implementation (same as core())
print(loop_rt.name)              # nasyncio
print(core.EventLoop)            # self-developed event-loop class
```

**Coexistence (supplementary declaration, 2026-09-12 feedback round)**: not depending on it does not mean conflicting — the standard `asyncio` (and its ecosystem coroutine clients) and the self-developed `norpagent.nasyncio` **can be used side by side in the same process**: norpagent schedules only through nasyncio on the `async_loop` slot, while your own code may keep using the standard asyncio (including `asyncio.run`) unaffected. The two meet in exactly two places, both with explicit semantics: ① cross-thread collaboration uses thread-safe APIs (nasyncio's `run_coroutine_threadsafe` / `LoopRuntime.submit` / `EventLoop.submit`) instead of reaching into each other's loop internals; ② event-loop replacement is explicit (`async_loop` slot / `npa.nasyncio(...)`), never implicit. In short: **nasyncio is not a takeover replacement for asyncio — coexistence has zero conflict and each loop runs its own tasks**.

---

## Chapter 5 Frontend Family

### 5.1 Two Layers: frontend (Shell) and ui (Renderer)

The frontend family has two layers:

| Layer | Slot | Protocol | Duty |
|---|---|---|---|
| shell | `frontend` | `Frontend` | where input is read from, when to start/stop, handing input to the engine |
| render | `ui` | `UIAdapter` | subscribes to the event bus and renders Agent events into text/UI |

A frontend usually carries a ui renderer; both can be replaced independently.

### 5.2 The Frontend Protocol

```python
class Frontend(Protocol):
    frontend_id: str
    def attach(self, engine) -> None: ...   # bind the engine (engine.submit / engine.request_stop)
    def start(self) -> None: ...            # start (internally spawns background threads; must not block)
    def stop(self) -> None: ...             # stop (thread-safe)
    def is_alive(self) -> bool: ...         # liveness check
```

### 5.3 Built-in Frontends

| Frontend | Address | Notes |
|---|---|---|
| Web (default) | `norpagent.frontends.web:WebFrontend` | HTTP + SSE, no third-party dependencies; page = front.html (multi-tab sessions / streaming render / settings / plugin panels), independent entry `/flow` = norp-flow.html module-flow orchestration; the console prints `listening on http://127.0.0.1:8787/`; configurable via `;port=9000`, `;html=custom main page`, `;flow_html=custom flow page` (slot mounting parameters, see 5.4) or `npa(port=9000, language="zh_CN")`; the frontend slot value can be a `.html` path directly (HTML-path direct mount, v0.9) |
| Console REPL | `norpagent.frontends.console:ConsoleFrontend` | explicit opt-in; `/exit` (or `exit`/`quit`/`exit()`) exits, `/reset` starts a new session; switches to synchronous mode automatically inside the Python interactive interpreter |
| Headless | `norpagent.frontends.headless:HeadlessFrontend` | pure API; default in `prompt` mode; output (body / tools / results) prints to stdout |

### 5.4 Web UI Behavior and Configuration Persistence

Web UI behaviors and configuration:

| Capability | Notes |
|---|---|
| config persistence | after saving in the settings panel, written to `~/.norpagent/webui_config.json` (`NORPAGENT_WEBUI_CONFIG` overrides; `WebUI(config_path=...)` can specify, `None` disables). Disk loading accepts only the `DEFAULT_CONFIG` whitelist keys; unknown keys are dropped. Since 0.9 **disk loading is deferred to `start()`**: constructing WebUI triggers no disk I/O (embedded / read-only-root friendly); the priority explicit constructor params > disk values > defaults is unchanged |
| page anti-caching | page responses carry `Cache-Control: no-store`; the browser fetches the latest front.html on every refresh; the server reads the page bytes into an in-memory cache (0.9: GET / no longer reads disk per request), validated by the resource file's mtime/size signature — **physically replacing library HTML files takes effect automatically on refresh**, with only a single stat check on cache hits |
| page mounting (html / flow_html params) | both the `/` route default page and the `/flow` module-flow page are fully replaceable: `html` / `flow_html` accept **file paths** or **HTML content** (after strip, a leading `<` means content, otherwise a file path); a nonexistent file raises `ValueError` at construction (fast fail, no silent fallback). No need to physically overwrite `norpagent/builtin/ui/assets/front.html` / `norp-flow.html`. At runtime `mount_page(page, html)` swaps the page directly (HTTP service not restarted, port unchanged); `mount_page(page, None)` unmounts and falls back |
| disconnect handling | client disconnects (WinError 10053 / EPIPE etc.) are handled silently, internal errors logged at DEBUG; disconnected SSE connections are reclaimed by non-blocking probing within ≤1s (0.9, prevents thread pileup) |
| SSE backpressure (0.9) | per-connection bounded event buffer + batched frame writes; slow clients degrade automatically; memory stays bounded under ultra-high concurrency — see 14.3 |
| port bump | on bind failure (including Windows 10013 listening-occupied) bumps up to 10 ports backward/forward; the actual port wins |
| request-body guard | negative Content-Length treated as no body; bodies over 1MB rejected |
| shutdown idempotence | `shutdown()` idempotent + same-thread deadlock guard, callable across threads; `block_on_close=False` does not wait for connections to close on stop (0.9) |
| event routing | event sid resolution prefers the original browser-session id registered by `submit()`; the session manager supports creating with a specified id (`create_session(title=..., session_id=...)`); when the kernel resumes a session the id matches the browser tab |

```python
import norpagent as npa
from norpagent.builtin.ui.web import WebUI
from norpagent.frontends.web import WebFrontend

# custom config persistence location (default ~/.norpagent/webui_config.json)
ui = WebUI(port=9000, config_path="./my_app/webui.json")
# config_path=None disables disk reads/writes
ui2 = WebUI(port=9000, config_path=None)
```

**Page mounting (html / flow_html params) — four equivalent forms:**

```python
import norpagent as npa

# 1. slot-address clause (;key=value, recommended)
npa(frontend="norpagent.frontends.web:WebFrontend;html=/path/to/my.html")
npa(frontend="norpagent.frontends.web:WebFrontend;flow_html=/path/to/flow.html")

# 2. constructor params directly (both WebFrontend / WebUI support)
npa(frontend=WebFrontend(html="<html><body>my UI</body></html>"))
npa(frontend=WebFrontend(flow_html="/path/to/flow.html"))

# 3. config dict
npa(config={"web": {"html": "/path/to/my.html", "flow_html": "/path/to/flow.html"}})

# 4. runtime-parameter passthrough
npa(html="/path/to/my.html", flow_html="/path/to/flow.html")

# 5. HTML-path direct mount (v0.9): the frontend slot value itself is a .html path,
#    equivalent to form 1's html= clause
npa(frontend="/path/to/my.html")

# a nonexistent file path errors at construction (fast fail, no silent fallback to the default page)
# ValueError: WebUI html mount parameter is neither HTML content (starts with '<') nor an existing file: ...
```

**Hot-swapping pages at runtime (HTTP service not restarted, port unchanged):**

```python
eng = npa()                                  # or npa.current() to get the running engine

# way one: remount page hot-replace keys (recommended, v0.9)
npa.remount(flow_html="/path/to/flow.html")  # /flow swapped immediately
npa.remount(html="/path/to/front.html")      # / main page swapped immediately
npa.remount(flow_html=None)                  # unmount, fall back to the library built-in

# way two: frontend instance API
eng.frontend.mount_page("flow", "/path/to/flow.html")  # /flow swapped immediately
eng.frontend.mount_page("flow", None)                  # unmount, fall back to the library built-in
eng.frontend.mount_page("front", "<html>...</html>")   # same for the / route
# equivalent lower-level API: WebUI.mount_page(page, html)
```

**The official module-flow frontend norp-flow.html**: the `/flow` standalone entry
(drag modules / beam connections / real backend execution / auto-save), shipped with
the library at `norpagent/builtin/ui/assets/norp-flow.html`; without a mount it is
the official page, and mounting `flow_html` replaces it wholesale. Physically
replacing the file also takes effect automatically (see "page anti-caching" above).

**Repository-root `front.html` (multi-host frontend)**: the pywebview desktop
protocol frontend has been refactored into a multi-host transport bridge — under a
browser host it automatically constructs `window.pywebview.api` (fetch + SSE
implementing all methods, translating library events into the text-event protocol
T:/R:/C:/U:/E:/Q:); the desktop host stays compatible as-is. Mount directly:

```python
npa(html="front.html")   # relative to the working directory; the library reads it as a file path
```

After mounting, chat / sessions / settings / plugin panels / file browsing all go
through the library's REST API (contract in `norpagent/builtin/ui/web.py`'s
do_GET / do_POST); SSH remote and mobile remote control were stripped from the
library version — their UI entries hide automatically and bridge methods degrade as
placeholders.

Input-box selectors (first-intuition design):

- **Mode**: `/api/presets` lists all registry presets (minimal / standard / ptc /
  creative / longrun / embedded); selecting hot-switches via config `preset_name`
  (`engine.remount(preset=...)`, AgentRuntime hot rebuild; disabled while tasks run,
  `*_arch` derived presets are not shown);
- **Model**: pulls the remote model list from `api_base` (`/api/models`); selecting
  saves `model` and takes effect immediately, with "fetch from URL / model settings"
  entries;
- **Reasoning strength**: clicking cycles through off / low / medium / high and saves
  immediately.

The debug panel (Settings → Agent Debug) itemizes version / frontend / preset /
model / tools / plugins / sessions, with the raw JSON folded under the "raw data"
section.

### 5.5 Custom Frontend Example

```python
# myapp/tray_frontend.py -- frontend implementation example
import threading

class TrayFrontend:
    """Tray-style frontend: reads no keyboard; input is submitted via method calls."""

    frontend_id = "tray"

    def __init__(self, **kw):
        self.engine = None
        self.alive = False

    def attach(self, engine):
        self.engine = engine
        self.alive = True

    def start(self):
        self.alive = True

    def stop(self):
        self.alive = False

    def is_alive(self):
        return self.alive

    # frontend custom capability: application code hands user input to the engine from here
    def send(self, text):
        return self.engine.submit(text)
```

Mount and drive it:

```python
import norpagent as npa

npa(frontend="myapp.tray_frontend:TrayFrontend", preset="standard")
fe = npa.current().frontend
result = fe.send("hello")        # the engine executes the Agent in the background loop
print(result.final_content)
npa.shutdown()
```

### 5.6 The UIAdapter Renderer Layer

```python
class UIAdapter(Protocol):
    ui_id: str
    def on_event(self, event) -> None: ...            # render one AgentEvent
    def ask_user(self, question, default="") -> str: ...  # human approval / clarification Q&A
    def notify(self, message, level="info") -> None: ...
```

Swap renderers: `npa(ui=MyRenderer())` or `npa(ui="web")` (reference a registered name).

### 5.7 Module-Flow Canvas (FLOW) and FE Frontend Modules

`/flow` is a standalone frontend category "module flow": it draws the agent assembly
process as a canvas (modules = blocks, ports = registered hooks, beam connections =
execution links); when RUN is pressed the graph is submitted to the backend and
executed topologically with real registry components. The canvas auto-saves to
`~/.norpagent/flow_graph.json` and restores automatically on refresh / restart; when
"apply to agent" in the top bar is on, front chat tasks execute per that flow
(behavior hot-switch). See `docs/flow.md`.

**FE frontend modules (file-as-frontend)**: dragging a `.html / .js / .ts` file onto
the canvas registers it as a frontend module (the "frontend FE" group in the module
dock); the backend hosts it at `/fe/<name>` (the card's "↗" opens a new tab). Each FE
has an **independent config scope** (no interference; defaults come from the global
"connection settings" config), read/written via `GET/POST /api/fe/config?fe_id=...`,
persisted to `~/.norpagent/fe_configs/<fe_id>.json`.

FE nodes have **three forms 1/2/3** (switched with the card-title-bar button):

| Form | Meaning |
|---|---|
| 1 | global-settings node: config written to "connection settings" (scope=global) |
| 2 | FE-as-settings-set: independent config scope (scope=fe, default form) |
| 3 | split into setting-item subcards: one member row per config item (draggable / connectable individually) |

**Input-box family (every place that needs input is an input box)**:

- FE / global-settings node cards render each config item (api_key / api_base /
  model / project_root / plugin_dirs / temperature / max_tokens / max_steps /
  task_timeout / system_prompt / language) as a row of
  "IN port · label · input box · OUT port"; values are written directly on the card
  and auto-save with a 500ms debounce; each member row of form 3 is also an input box;
- model / tool / sandbox / other node cards carry a **value input-box strip** at the
  bottom (context / query / code / value edited directly); the TR card's prompt input
  box,
(context / query / code / value edited directly); the TR card's prompt input box and
the PATH card's path input box stay embedded;
- model fields are always **hand-editable input boxes + datalist hints** (the flow
  connection-settings dialog, the WebUI settings dialog, the model node's instance
  field): if the remote model list fetch fails or the model is not in the list, type
  any model name directly (empty = engine default);
- card input boxes and the right-side node panel sync bidirectionally; when a beam
  connects to a settings port the connection action itself takes effect immediately
  (written to the independent / global config).

**Canvas-management trio (new in 0.6.8, keeps the canvas tidy)**:

- `Alt+left-drag` on empty space = **box select**; modules intersecting the box all
  highlight; `Del` deletes them in bulk;
- `Ctrl+A` = **select all**; `Del` deletes in bulk;
- the top bar's **"Clear canvas"** = one-click deletion of all modules and beams
  (confirmation dialog prevents accidental clicks), auto-save immediately after
  confirmation; after clearing, refreshing stays empty (the backend saves the empty
  graph; loading no longer falls back to the example template);
- **accidental-injection entries removed**: double-clicking empty canvas to inject
  and one-click dock-card quick-inject are gone for good — previously, accidental
  `other` nodes were auto-saved and frozen, causing "a pile of other nodes the moment
  the canvas opens". Now dragging is the only injection path.

**DeepSeek model names**: `deepseek-chat` / `deepseek-reasoner` were officially
retired on 2026-07-24; the current models are `deepseek-v4-flash` / `deepseek-v4-pro`.
The backend `list_models` cache, flow snapshots (`filter_remote_models`), the frontend
hint list and the remote-model dock all filter retired names
(`RETIRED_REMOTE_MODELS` / `RETIRED_MODELS` / `RETIRED_REMOTE`); historical caches
never show old names again.

**Connection-settings dialog** (flow top bar): shows immediately, not blocked by the
remote model fetch; "fetch model list" uses the form's current Key/Base for an
immediate request (no need to save first); clicking outside does not close it
(Esc / × / Cancel close); input boxes auto-save and apply on blur.

**Agent-tool mounting (new in 0.6.10, module tools → front auto-invocation)**:

- **config keys** (`DEFAULT_CONFIG`): `agent_tools` (explicit full tool-set list)
  + `agent_tools_explicit` (bool; True = explicit; False = follow the preset default set);
- **write entries**: ① the `AGENT` badge on tool cards in the `/flow` module dock
  (the frontend calls `POST /api/agent/tools {tools, explicit}`); ② the "🧰 agent
  tools" checkbox list in the WebUI settings dialog (saved into `agent_tools` via
  `save_config`). `GET /api/config` returns `tools_info` (all tools + native/module
  origins) and `agent_effective_tools` / `agent_base_tools`, which the frontend uses
  to render;
- **hot application**: `WebFrontend._apply_agent_tools()` rewrites `preset.tools`
  to the explicit set (unregistered tool names filtered automatically) or a snapshot
  of the preset default set (`WebFrontend._base_tools`, captured at attach); the next
  `run()`'s `registry.tool_schemas(preset.tools)` then includes module tools, and the
  model calls them automatically per the OpenAI function schema;
- **restart restore**: at the end of `WebFrontend.attach()`, the saved config
  re-applies the tool set (without changing existing model-config behavior);
- **fallback semantics**: `set_agent_tools` automatically falls back to non-explicit
  (`agent_tools=[]`) when the explicit set equals the preset default set, so preset
  evolution is followed automatically;
- **snapshot fields**: `/api/flow/snapshot` top level returns `agent_tools` /
  `agent_base_tools`, driving the flow page's badge state.

---

## Chapter 6 npa() Startup and Lifecycle

### 6.1 Reading the Startup Code

```python
import norpagent as npa
npa()                    # ①
running = True
while running:
    if npa.stop() == True:   # ②
        running = False
```

① `npa()` — the `norpagent` module is callable (module-class replacement). It is
equivalent to `norpagent.launch()`, which internally does, in order:

1. **parameter sorting**: keyword arguments whose names match the slot table (the 18
   built-in slots + custom slots registered at runtime via register_slot) → slot
   values; the rest → task parameters (e.g. `max_steps` / `task_timeout` /
   `workspace_root`); special keys `prompt` (single-task text) and `config` (dict-form
   slot assignment);
2. **architecture-layer assembly**: `ArchLayer(config, **slots)` → `mount_defaults()`
   (registers each slot's library built-in default logic) → `layer.connect()`
   (resolves addresses, calls factories, obtains each slot's implementation);
3. **registry assembly**: `build_registry(layer)` installs built-in components and
   presets, then writes the slot overrides into the final preset;
4. **engine start**: `NorpEngine(layer, registry, preset, loop, frontend, ...)`
   → `engine.start()`: assemble the agent runtime → bind the frontend → start the
   loop thread → start the frontend thread → enter RUNNING;
5. **singleton semantics**: when an engine is already running, another `npa()` returns
   the current engine directly.

② `npa.stop()` — the lifecycle function. Returns `True` when the engine has entered
STOPPED (the application has ended; the main loop should exit); also returns `True`
when there is no engine.

### 6.2 Engine Lifecycle State Machine

```
STARTING ──start()──▶ RUNNING ──request_stop()──▶ STOPPING ──▶ STOPPED
```

| State | Meaning | Entry condition |
|---|---|---|
| STARTING | assembling | inside `npa()` |
| RUNNING | accepts input, executes tasks | `engine.start()` finished |
| STOPPING | winding down | `request_stop()` |
| STOPPED | finished | wind-down complete (`npa.stop()` is True) |

Stop-request wind-down order (`NorpEngine.request_stop`):

1. stop the frontend (input loop exits);
2. close the Agent (release sandboxes/components, broadcast `on_agent_shutdown` —
   the L1 lifecycle hook);
3. unsubscribe the renderers additionally subscribed by the engine;
4. stop the loop thread and wait for it to exit;
5. set STOPPED.

### 6.3 Three Run Modes

**Main-loop mode** (default Web frontend):

```python
npa()                            # default frontend = Web (frontend web listening on 127.0.0.1:8787)
while True:
    if npa.stop():
        break
```

Open the printed address in a browser to see the chat UI (front.html). With other
frontends, specify explicitly:
`npa(frontend="norpagent.frontends.console:ConsoleFrontend")`.

**Single-task mode** (when `prompt` is given, the headless frontend is used
automatically and output prints to stdout):

```python
npa(prompt="summarize README", preset="standard")
while True:
    if npa.stop():
        break
print(npa.current().last_result.final_content)
```

**Pure-API mode** (headless + programmatic submit):

```python
npa(preset="minimal", frontend="norpagent.frontends.headless:HeadlessFrontend")
eng = npa.current()
result1 = eng.submit("first question")
result2 = eng.submit("follow-up", session_id=result1.session_id)   # continue the same session
eng.request_stop()
```

> **Note**: `npa()` does not block; the engine runs on background threads. The main
> thread should poll with `npa.stop()` (or call `npa.current().wait()`). If the main
> thread simply ends the process, the daemon engine threads exit with it; the library
> registers an atexit fallback cleanup.
>
> **Special case**: with the **console frontend** explicitly selected, calling `npa()`
> inside the Python interactive interpreter (`>>>` REPL) automatically switches to
> **synchronous mode** — `npa()` blocks until the user exits (`/exit`, `exit()`,
> Ctrl+C or EOF); no polling loop needed during that time. In synchronous mode the
> main thread owns stdin exclusively. The default Web frontend also works in the REPL
> (background service + page interaction, without blocking the interpreter).

### 6.4 The Full npa() Parameter Set

```python
npa(
    # -- architecture slots (18 built-in; empty = default logic; custom slots
    #    registered via register_slot take parameters here too, see 3.8) --
    async_loop=..., agent_runtime=..., model=..., tools=...,
    session=..., sandbox=..., scheduler=..., context_store=...,
    project_manager=..., hooks=..., security=..., plugins=...,
    frontend=..., ui=..., preset=..., logger=..., storage=...,
    error_handler=...,
    # -- special keys --
    prompt="single-task text",      # stops automatically after finishing
    config={"slot": value, ...},    # dict-form slot assignment
    # -- model shortcut parameters (effective when model is a built-in adapter name) --
    model_name="deepseek-v4-flash", # remote model name
    base_url="https://api.deepseek.com/v1",   # remote service address
    api_key="sk-...",               # API key (also read from environment variables)
    # -- Web frontend runtime parameters (passed through to WebFrontend when frontend=web) --
    port=8787,                      # HTTP port (auto-bumps up to 10 when occupied)
    host="127.0.0.1",               # listen address
    open_browser=False,             # whether to open the browser automatically
    language="zh_CN",               # UI language (en / zh_CN)
    html="/path/to/my.html",        # custom main page: file path or HTML content
                                    # (replaces the / route default page, see 5.4)
    sse_queue_size=1024,            # SSE per-connection buffer cap (0=unlimited, 0.9)
    sse_queue_policy="drop_oldest", # drop_oldest / drop_newest / unlimited
    # -- remaining keys = task parameters, passed through to the agent loop --
    max_steps=32, task_timeout=0, call_timeout=0,
    workspace_root=..., system_prompt=...,
)
```

Sub-key conventions of the `config` dict (0.9, embedded / high-concurrency tuning;
see Chapter 14):

```python
npa(config={
    "loop": {"max_workers": 8, "poll_interval": 0.02},   # loop worker pool and polling
    "web": {"port": 9000, "sse_queue_size": 2048,        # Web UI and SSE backpressure
            "sse_queue_policy": "drop_oldest"},
    "preset": "embedded",                                 # slot assignment same as keywords
})
```

> With `preset="embedded"` and no explicit frontend, the default frontend is
> automatically headless (no HTTP service; pure-API mode), see 12.1 and Chapter 14.

### 6.5 Lifecycle ↔ L1 Hook Correspondence

The engine state machine aligns with the L1 layer of the 9-layer hook system:

| Engine event | Hook / event |
|---|---|
| agent runtime constructed | `on_agent_init` (L1) |
| task submitted | `on_task_start` |
| engine stopped | `on_agent_shutdown` (L1) |

Lifecycle subscription: `npa(hooks={"on_agent_init": fn, ...})`
(the hook system is in Chapter 9).

---

## Chapter 7 Models and Tools

### 7.1 The Model Slot

The model slot accepts:

```python
npa(model="mock")                  # registry name (built-in mock / openai_compat / anthropic)
npa(model=MyProvider())            # instance
npa(model="myapp.model:create")    # address (resolved as an address when the string matches no registered name)
```

The ModelProvider protocol (`norpagent.protocols.model`):

```python
class ModelProvider(Protocol):
    def generate(self, messages, tool_schemas, params) -> ModelOutput: ...
    def stream(self, messages, tool_schemas, params): ...   # optional: incremental output
```

When `stream` exists the kernel prefers the streaming path (broadcasting
`on_content` per segment); otherwise it calls `generate` once. `params["_cancel_event"]`
is the cancel event injected by the kernel; adapters should exit as early as possible
accordingly (paired with the hard timeout).

### 7.2 The Tool Slot

Three assignment forms:

```python
npa(tools=["echo", "get_time"])           # name list: registry references
npa(tools={"my_tool": MyTool()})          # mapping: register and enable
npa(tools=[ToolA(), ToolB()])             # instance list: registered by name
```

The Tool protocol (`norpagent.protocols.tool`):

```python
class Tool(Protocol):
    name: str
    def schema(self) -> dict: ...        # OpenAI function schema
    def run(self, args: dict, ctx: RunContext) -> ToolResult: ...
```

Built-in tool list (`install_defaults` registration): `echo`, `get_time`,
`run_python` (PTC sandbox execution), `file_read / file_write / file_list /
file_delete` (path-safe), `exec_cmd` (sandbox protocol), `web_search /
web_fetch / web_extract_links` (SSRF protection), `context_add / search /
list / delete` (FTS5 context store), `project_status`, `task_submit /
list / status / cancel` (long-running task cooperation).

### 7.3 Example: Model Benchmarks

The minimal preset uses a deterministic environment and the smallest tool set,
suitable for comparing different models' outputs on a fixed input set:

```python
import norpagent as npa

for model_name in ("mock", "openai_compat"):
    npa(preset="minimal", model=model_name, prompt="1+1=?",
       frontend="norpagent.frontends.headless:HeadlessFrontend")
    while True:
        if npa.stop():
            break
    r = npa.current().last_result
    print(model_name, r.steps, r.usage.total_tokens, r.final_content[:40])
    npa.shutdown()
```

---

## Chapter 8 Sessions, Sandboxes, Schedulers, Context and Projects

### 8.1 Sessions

```python
npa(session="memory")     # in-process (default)
npa(session="sqlite")     # persisted to ~/.norpagent/sessions.db
npa(session=MySessionManager())          # instance
npa(session="myapp.sessions:create")     # address
```

SessionManager protocol: `create_session / get_session / append_message /
history`. Continue a conversation across sessions via `session_id`:

```python
eng = npa.current()
r1 = eng.submit("remember: my favorite color is blue")
r1 = eng.submit("remember: my favorite color is blue")
r2 = eng.submit("what is my favorite color?", session_id=r1.session_id)
```

### 8.2 Sandboxes

```python
npa(sandbox="subprocess")   # child process (default)
npa(sandbox="pooled")       # pooled reuse + concurrency cap + timeout force-kill of the process tree
npa(sandbox="myapp.docker_sandbox:create")
```

Sandbox protocol: `run / close`. The `exec_cmd` tool executes through the sandbox
protocol; swapping in a container/pooled sandbox implementation requires no tool-code
changes.

### 8.3 Schedulers

```python
npa(scheduler="simple")       # in-memory queue (default)
npa(scheduler="persistent")   # persistent + crash resume() continuation
```

TaskScheduler protocol: `submit / drain / cancel`. The `task_*` tool family lets the
model orchestrate long-running tasks; `agent.run_task()` is the multi-agent
orchestration entry (subtasks can specify a different mode via `preset_name` =
different child agents).

### 8.4 Context Store and Project Management (the generic-component namespace)

```python
npa(context_store="norpagent.builtin.context:FTS5ContextStore")
npa(project_manager=MyProjectManager())
```

These two slots use the **generic-component namespace**
(`registry.register_component`); the component kinds are open — you can register new
kinds and declare them in presets without modifying the kernel.

### 8.5 Base-Service Slots

```python
npa(logger=logging.getLogger("my.app"))       # logging
npa(storage="./my_data")                       # persistence root
npa(error_handler=lambda exc, eng: print(exc))  # last line of defense for errors
```

`error_handler` is called on task-level exception fallback (signature
`(error, engine)`); when omitted, errors are recorded to the logger.

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

## Chapter 14 Embedded and Ultra-High-Concurrency Deployment

Since 0.9 the framework has dedicated optimizations for **embedded (low memory /
low CPU / no disk / edge devices)** and **ultra-high-concurrency servers**. This
chapter covers the optimizations, config entries and usage.

### 14.1 Optimization List

**Embedded scenarios (resource consumption minimized):**

| Optimization | Content |
|---|---|
| `install_core()` minimal assembly | registers only the components needed for the minimal agent loop: mock / openai_compat models, echo / get_time / run_python / file_* tools, memory sessions, subprocess sandbox, simple scheduler, console UI — **zero disk dependencies, no HTTP components, empty component namespace** (no sqlite3 / http.server imports) |
| builtin package lazy imports | `import norpagent.builtin` no longer pulls in sqlite3 / http.server; FTS5 context store / SQLite sessions / persistent scheduler / Web UI all became on-demand imports inside install_defaults + module-level `__getattr__` lazy resolution (`from norpagent.builtin import WebUI` etc. stay compatible) |
| WebUI construction does zero disk I/O | reading of the three disk states (config / FE config / flow graph) is deferred to `start()` (`_ensure_disk_loaded`); constructing without starting reads nothing — safe on read-only root filesystems / environments without HOME |
| page byte cache | `page_bytes()` caches into memory: GET / no longer reads disk per request (previously one open+read per request) |
| `embedded` preset | the built-in sixth mode: pure in-memory components + minimal tool set + headless frontend by default (no listening port); the model falls back to mock without credentials |
| worker-pool tightening | `NORPAGENT_MAX_WORKERS=1` or `config={"loop": {"max_workers": 1}}` squeezes daemon worker threads to the minimum; `NORPAGENT_SUBMIT_POLL=0.5` raises the poll interval to save CPU |

**Ultra-high-concurrency servers (throughput and memory bounds):**

| Optimization | Content |
|---|---|
| EventBus copy-on-write | subscriber tables become immutable snapshots: emit / intercept only take a reference inside the lock and iterate lock-free, **saving one listener-list copy per event** (the biggest win for per-token streaming pushes). subscribe / unsubscribe create a new list and replace the reference; thread-safety semantics unchanged (measured emit throughput >1.5M events/sec) |
| SSE bounded backpressure | each connection gets a `_SSESubscriber` bounded buffer (default 1024): slow clients **drop the oldest event** (`drop_oldest`, default) and degrade automatically; optional `drop_newest` / `unlimited`; memory usage is bounded and decoupled from the client count |
| SSE batched frame writes | write+flush once when 32 frames accumulate or 50ms elapse (`sse_batch` / `sse_batch_interval` configurable): system-call counts drop sharply under high-frequency streaming; single-event-stream latency ≤ batch interval |
| SSE fast disconnect reclamation | after a TCP half-close the first write does not error; discovery via heartbeat alone would take up to 15s — idle connections are probed with a non-blocking select every 1s; after disconnect, threads and buffers are released within ≤1s; heartbeats stay at 15s intervals, adding no network burden |
| HTTP concurrency tuning | listen backlog `request_queue_size=256`; `block_on_close=False` does not wait for connections on stop; `X-Accel-Buffering: no` (nginx reverse proxy does not buffer); responses keep-alive (HTTP/1.1) |
| submit polling tightened | completion-poll interval 0.2s → 0.05s (default): the calling thread's completion-perception latency cap drops from 200ms → 50ms; configurable / env-overridable |
| loop-core micro-tuning | `traceback` promoted to module level (zero import on the callback-exception path); ready-queue snapshot batch execution keeps anti-starvation semantics |

### 14.2 Embedded Deployment

**Way one: `install_core()` with a self-built registry (cleanest dependency
surface):**

```python
from norpagent import Registry, AgentRuntime, install_core
from norpagent.modes import build_embedded_preset

reg = Registry()
install_core(reg)                       # does not import sqlite3 / http.server
reg.register_preset(build_embedded_preset())
agent = AgentRuntime(reg, preset="embedded")
result = agent.run("hello")
print(result.final_content)
```

Note: `install_core`'s registry has no context_store / project_manager / persistent
components — presets declaring them (standard / longrun / creative etc.) are
explicitly refused when assembled on this registry (the error lists the missing
component names).

**Way two: `npa(preset="embedded")` (out of the box):**

```python
import norpagent as npa

npa(preset="embedded")                   # headless by default: no HTTP service
eng = npa.current()
result = eng.submit("hello")            # pure-API submission
eng.request_stop()
```

Behavioral conventions of the embedded preset:

- **the default frontend automatically falls back to headless** (the assembler's
  default factory judges the preset name); for a Web UI specify explicitly
  `npa(preset="embedded", frontend="norpagent.frontends.web:WebFrontend")`;
- the model declares `openai_compat`: with any credential (parameter / environment
  variable) the real model is used, otherwise it falls back to mock (offline
  devices work out of the box);
- all components are pure in-memory (memory / subprocess / simple), no generic
  components declared — FTS5 / SQLite are never built and no files land on disk.

**Way three (resource switches, stackable with ways one/two):**

```python
# squeeze worker threads to 1; relax polling to save CPU
os.environ["NORPAGENT_MAX_WORKERS"] = "1"
os.environ["NORPAGENT_SUBMIT_POLL"] = "0.5"
# or equivalent:
npa(config={"loop": {"max_workers": 1, "poll_interval": 0.5}})
```

### 14.3 Ultra-High-Concurrency Deployment

**SSE backpressure config (startup params → env vars → runtime hot change):**

```python
import norpagent as npa

# pass at startup
npa(config={"web": {"sse_queue_size": 2048, "sse_queue_policy": "drop_oldest"}})
# or runtime params / environment variables
npa(sse_queue_size=2048, sse_queue_policy="drop_oldest")
# NORPAGENT_SSE_QUEUE_SIZE=2048 NORPAGENT_SSE_QUEUE_POLICY=drop_oldest

# hot change while running (no restart; takes effect on existing connections immediately)
from norpagent.builtin.ui.web import WebUI
ui = npa.current().frontend._ui      # or hold the WebUI instance directly
ui.set_sse_queue(sse_queue_size=4096, sse_queue_policy="drop_newest")
print(ui.streams_info())
```

REST operations entries:

| Endpoint | Note |
|---|---|
| `GET /api/streams` | query SSE backpressure config and stats (subscriber count / dropped-event count / per-connection buffer depth) |
| `POST /api/streams` | hot change: `{"sse_queue_size": 2048, "sse_queue_policy": "drop_oldest"}` |
| `GET /api/status` | `sse_queue_size` / `sse_queue_policy` / `sse_dropped_total` fields |

Backpressure-policy semantics:

| Policy | Behavior when the buffer is full | Suitable for |
|---|---|---|
| `drop_oldest` (default) | drop the oldest event; the client degrades automatically but **stays connected** | display-style frontends (chat streams) |
| `drop_newest` | drop the newest event; keep the old state | "state sync" consumers |
| `unlimited` | no limit (the pre-0.8 behavior) | when you know every client consumes everything |

A buffer size of `sse_queue_size=0` means unlimited. `sse_batch` (default 32 frames)
and `sse_batch_interval` (default 0.05s) control the frame batch-write granularity:
the larger, the fewer system calls and the higher single-event latency — balance
against your traffic pattern.

**Reverse-proxy notes**: SSE responses already carry `X-Accel-Buffering: no` (nginx
does not buffer); the proxy timeout (proxy_read_timeout) should be > 15s (the
library heartbeat period).

**Loop tuning**: `config={"loop": {...}}` and `NORPAGENT_MAX_WORKERS` /
`NORPAGENT_SUBMIT_POLL` see 4.3 and 14.1. Task-completion perception latency =
poll_interval (default 50ms); raise it in CPU-sensitive environments, lower it in
latency-sensitive ones (floor 1ms).

**Thread model**: the Web frontend has one HTTP thread per SSE connection (the
standard-library socketserver model); tasks enter the engine serially through
`WebFrontend._gate` and execute on the loop worker pool. The event-publishing path
is O(subscriber count) with O(1) amortized per subscriber (bounded deque + one
empty→non-empty notify), so ten-thousand-scale concurrent pushes do not amplify
lock contention.

**Monitoring metrics** (`GET /api/streams`): `subscribers` (online subscribers),
`dropped_total` (cumulative backpressure drops — sustained growth means clients are
too slow; enlarge the buffer or inspect the consumers), `max_buffered` (peak buffer
depth per connection).

### 14.4 How to Verify

In-library verification scripts (`test/`):

```bash
python test/_verify_embedded_concurrency.py   # 34 items: minimal assembly / lazy imports / e2e / concurrency correctness / throughput
python test/_smoke_webui_09.py                # WebUI: lazy disk I/O / page cache / backpressure hot change / HTTP concurrency / SSE
python test/_smoke_embedded.py                # embedded preset e2e
```

Coverage points: `install_core` component whitelist and blacklist,
`import norpagent.builtin` does not pull sqlite3 / http.server, embedded defaults to
headless + mock fallback, environment variables tighten the worker pool, EventBus
copy-on-write concurrent subscribe/unsubscribe correctness, submit interrupt
wakeup, SSE three policies and hot change, 40 concurrent HTTP, disconnect
reclamation.

---

## Chapter 15 Work Rollback: Snapshots / Undo / Redo / Crash Rescue / Safe Mode

> Core role: Agent work can be rolled back — Web UI / shortcuts / API
> one-click undo and restore (Undo / Redo); browse the full snapshot history and
> roll back to any version in one click (Rollback); when the main program cannot
> start at all, use the standalone CLI crash rescue (which also suggests the last
> known-good snapshot); safe mode loads only the minimal kernel, keeping the core
> rollback capabilities.

### 15.1 Concepts and the Four Layers

| Layer | Capability | Entry |
|---|---|---|
| Undo / Redo | undo / restore the most recent operation, in-process immediate | Web UI buttons / Ctrl+Z / Ctrl+Shift+Z / `npa.undo()` / `npa.redo()` |
| Rollback | browse all historical snapshots, roll back to any version | Web UI "rollback" panel / `npa.rollback(id)` |
| Crash Rescue | roll back snapshots when the main program cannot start; suggest the last known-good snapshot | `norpagent-rescue` (standalone CLI, pure standard library) |
| Safe Mode | load only the minimal kernel (skip all plugins), keep the core rollback capabilities | `npa(safemode="on")` / CLI `--safe-mode` |

Snapshot content (mode A, default): all architecture-layer slot configurations
(mode / model / tools / session / sandbox / frontend / plugin dirs / security
level...) + engine runtime parameters + WebUI settings-file content + custom
provider data. Sensitive keys (api_key / token etc.) are written only after
**redaction**. Non-serializable values (instances / classes / functions) record a
type marker; on replay they are skipped with a hint (honest degradation, never
fabricates state).

Snapshot mode B: `npa(snapshot_sessions="on")` additionally copies session-store
files into the snapshot attachments; rollback restores the whole files (this may
overwrite conversations recorded after the rollback point).

Storage: default `~/.norpagent/snapshots/` (manifest.json timeline + snap/ one
JSON per snapshot + attachments/ session attachments + rollback_target.json the
rescue rollback target). Overridable with the environment variable
`NORPAGENT_SNAPSHOT_DIR` or `npa(snapshot_dir=...)`; while running,
`npa.set_snapshot_dir()` hot-switches the storage directory (explicit programmatic
calls have the highest priority). Auto snapshots are on by default
(`npa(snapshots="off")` disables); auto-prune keeps the most recent 200.

### 15.2 Snapshots and Undo / Redo

Auto-snapshot timing: the startup baseline and after every system-state change
(`npa.remount` / WebUI settings saved / plugin installed / mode switched). Manual
snapshots: the "manual snapshot" button in the Web UI rollback panel or
`npa.snapshot_system("description")`.

```python
import norpagent as npa

npa()                                          # start (baseline snapshot taken automatically)
npa.snapshot_system("before installing plugins")   # manual snapshot
# ...make a few changes (remount / settings saved / install plugins)...
npa.undo()                                     # undo the most recent operation (in-process immediate)
npa.redo()                                     # restore the undo
npa.rollback("20260818T230101_ab12cd")         # roll back to any snapshot
npa.rollback()                                 # roll back to the last known-good snapshot
npa.list_snapshots()                           # timeline (is_current / is_last_good)
npa.mark_good_snapshot("<id>")                 # manually mark "known good"
```

Semantic points:

1. **pointer model**: timeline + current pointer. Undo = apply the previous
   snapshot and move the pointer back; Redo = apply the next snapshot; after an
   undo, a new operation **truncates the redo branch** (standard undo semantics).
2. **in-process immediate**: replay reuses the remount hot-mount pipeline —
   component slots take effect on the next run, assembly slots hot-rebuild the
   AgentRuntime, the HTTP port stays the same; slots whose values equal the
   snapshot are skipped (avoiding needless frontend restarts). Changes during
   replay are **not** auto-snapshotted again (preventing an undo from taking a
   selfie that overwrites the redo branch).
3. **Web UI**: the left "rollback" page + buttons + shortcuts (Ctrl+Z /
   Ctrl+Shift+Z, not intercepted when an input box has focus); backend APIs
   `GET /api/snapshots`, `POST /api/snapshots {action: capture|undo|redo|rollback|mark_good}`.
4. **"known good" auto-marking**: 30 seconds after a successful engine start (or
   the first task completing) auto-marks good; manual marking is also available. ★
   in the rollback panel and the rescue CLI is the last known-good snapshot.

### 15.3 Custom Snapshot Content (hook-style extension)

```python
from norpagent import recovery

# capture hook + restore hook (optional)
recovery.register_snapshot_provider(
    "my_state",
    capture=lambda engine: {"mark": 42},          # any JSON value
    restore=lambda engine, value: apply_mark(value),
)
# registered -> effective: all subsequent snapshots carry a providers.my_state
# section, and restore is called on replay. Duplicate names overwrite;
# unregister_snapshot_provider unregisters.
```

### 15.4 Crash Rescue (standalone CLI, pure standard library)

`norpagent-rescue` deliberately **depends only on the standard library** (reads /
writes snapshot JSON and the WebUI settings file); even if the main program cannot
start at all due to config errors or plugin problems, the rescue tool still works:

```bash
norpagent-rescue list                        # timeline (★ = last known good)
norpagent-rescue show <id>                   # inspect a snapshot (redacted)
norpagent-rescue rollback <id>               # roll back: restore WebUI settings + write the rollback target
norpagent-rescue rollback --last-good        # one-step rollback to the last known-good snapshot
norpagent-rescue mark-good <id>              # manually mark "known good"
norpagent-rescue prune --keep 50             # keep only the most recent N
```

After a rollback, the next `norpagent` / `npa()` startup **automatically consumes**
the rollback target (rollback_target.json, deleted after consumption): file-level
restore (WebUI settings / session files) executes immediately, and the snapshot's
slot config merges into this startup — **parameters explicitly given this time
take priority** (rescue is a fallback; it never overrides the user's conscious
choices). On startup failure both the CLI and npa() print self-rescue guidance
(safe mode + rescue command).

### 15.5 Safe Mode

Entry: `npa(safemode="on")`, CLI `norpagent --safe-mode`. Safe mode is not entered
by default (any value other than on does not trigger it).

Behavior (loads only the minimal kernel):

1. **skip all plugin directories** (plugins are the most likely startup-failure source);
2. **force the minimal preset** (ignores user-given preset / plugins / security
   slot parameters);
3. **does not read the WebUI settings file** (a bad config may be exactly why the
   last run crashed; runs purely in memory, and saving no longer writes to disk);
4. **keeps the core rollback capabilities**: the Web UI rollback panel and
   `/api/snapshots`, `norpagent-rescue` all remain usable — after starting you can
   roll back to any known-good snapshot, then restart normally after repair.

```python
import norpagent as npa
npa(safemode="on")          # minimal kernel + Web rollback panel
```

```bash
norpagent --safe-mode      # CLI equivalent
```

### 15.6 Human Rescue: Manual Tool Takeover API (when the model is dead)

**Scenario**: the model provider is down / the API key is invalid / model output
is corrupted — the model channel is unavailable, but the tool-execution capability still works:
workspace files, sandbox, context store and task queue are all alive. Human
Rescue (v0.9.3; custom-tool support v0.9.7) exposes tools in a human-operable
form: the operator passes arguments by hand (manual input) and reads the raw
execution result (manual output), keeping the work moving until the model
recovers. **All 20 built-in tools are exposed by default; since v0.9.7,
registry-registered custom tools, tools mounted through the tools slot, and
tools provided by external plugins can also be operated manually** (15.6.3).

**Design principles**:

1. **exactly the same execution path as the model** — manual calls and
   model-issued calls share the same `tool.run(args, ctx)` and `RunContext`
   (registry / sandbox / session / scheduler / context_store / project_manager,
   nothing missing) and write to the same state: files land in the same
   workspace, `context_add` writes to the same context store, `task_submit`
   enters the same task queue;
2. **no plugins are loaded by default** (plugins are the most likely failure
   source); when `--plugin-dirs` / `plugin_dirs` is given explicitly, plugins
   load through the same security pipeline as the host application (signature →
   audit → import restriction → register) and their tools are manually callable
   too;
3. **hard timeout + cancel signal**: every call runs in a dedicated worker
   thread; on timeout the call is abandoned (daemon orphan thread, the same
   pattern as the model-call timeout) and the cancel event is set — the sandbox
   force-kills child process trees and streaming loops exit early;
4. **binds 127.0.0.1 by default**, optional bearer token — this endpoint really
   executes commands / writes files and must never be exposed beyond localhost.

Four entry points (`tools / tool-call / manual / serve` all support
`--tools` and `--plugin-dirs`, see 13.5):

```bash
norpagent-rescue tools                              # tool inventory (with origin tags)
norpagent-rescue tool-call echo --args '{"text":"ping"}'
norpagent-rescue tool-call exec_cmd --args '{"command":"git status"}' --timeout 30
norpagent-rescue manual                             # interactive manual console
norpagent-rescue serve --port 8799                  # HTTP API + operator page
norpagent-rescue serve --token my-secret            # with bearer auth

# v0.9.7: manual control of custom tools
norpagent-rescue tools --tools myapp.tools:create   # load a custom tool by module address
norpagent-rescue tools --plugin-dirs ./my_plugins   # load external plugin tools
norpagent-rescue serve --tools t1,t2 --plugin-dirs ./p1,./p2
```

#### 15.6.1 Interactive Manual Console (manual)

```text
rescue> echo {"text": "ping"}                        # <tool name> <JSON args>
rescue> {"tool": "file_list", "args": {}}            # JSON-object form
rescue> /tools                                       # list all tools
rescue> /exit                                        # quit
```

Boundary with the snapshot commands (list / rollback / ...): the `rescue.py`
module top level **still depends only on the standard library**; the
`tools / tool-call / manual / serve` commands lazily import the framework
(`norpagent.rescue_api`) inside the command functions — snapshot rollback keeps
working no matter how broken the main program is; manual takeover requires a
working framework installation but never touches the broken main process.

#### 15.6.2 HTTP API and Operator Page

`norpagent-rescue serve` starts a zero-dependency HTTP service (stdlib
ThreadingHTTPServer); opening the root path in a browser shows the operator
page (inline HTML/JS, no external resources): pick a tool from the dropdown →
the schema and required parameters are shown automatically → fill in JSON args
and a timeout by hand → call → raw result plus a call history.

| Endpoint | Method | Description |
|---|---|---|
| `/` | GET | operator page (inline HTML; the dropdown tags tool origins) |
| `/api/health` | GET | status / tool count / **custom_tools count** / workspace root |
| `/api/tools` | GET | full inventory: `{tools:[{name,description,parameters,required,category,origin}]}` |
| `/api/tools/<name>` | GET | single tool schema |
| `/api/tools/call` | POST | body `{"tool":"echo","args":{...},"timeout":N,"params":{...}}` |
| `/api/tools/<name>/call` | POST | body `{"args":{...},"timeout":N}` |

Every inventory item carries an `origin` field: `builtin` (the 20 framework
built-ins) / `custom` (registered via `--tools` / `extra_tools`) / `plugin`
(loaded from a plugin directory); the operator page tags tools accordingly.

```bash
curl -s http://127.0.0.1:8799/api/tools/call \
  -H "Content-Type: application/json" \
  -d '{"tool":"context_search","args":{"query":"marker"}}'
```

The response is always:

```json
{
  "ok": true, "tool": "echo", "task_id": "1a2b3c4d5e6f",
  "output": "[echo] ping", "error": "", "success": true,
  "timed_out": false, "duration_ms": 0.4
}
```

Semantics: `ok=false` with HTTP 200 = the tool ran and failed (bad args /
business failure); HTTP 404 = tool not registered; 400 = invalid JSON body;
401 = missing or wrong token (only when a token is configured); 413 = body over
1 MB. A hard-timeout abandonment returns `timed_out=true` (HTTP 200; the caller
never waits for the orphan).

#### 15.6.3 Environment Assembly and Defaults

`RescueToolEnvironment` assembles the full built-in stack with
`install_defaults()` (the same source as the standard preset) and shares the
components across calls for the environment's lifetime:

| Component | Default | Notes |
|---|---|---|
| sandbox | subprocess | one child process per command; path-safety constraints still apply |
| session | memory | one fixed rescue session (rescue-manual) |
| scheduler | **persistent** | all task_* tools work; by default shares the main app's queue DB `~/.norpagent/tasks.db` — inspect tasks the agent submitted before the model died |
| context store | fts5 | by default shares `~/.norpagent/context.db`; `--context-db` isolates |
| project management | basic | `project_status` works |
| workspace | current directory | `--workspace` overrides; the file_* path-safety boundary moves with it |

Note: the persistent scheduler means `norpagent-rescue tools` also creates the
task DB on disk (if it does not exist). For a fully diskless environment pass
`--scheduler simple` (the task-query tools then honestly report "the current
scheduler does not support queries").

**Custom tools (v0.9.7)**: `RescueToolEnvironment` constructor parameters
`extra_tools` / `tools` / `plugin_dirs` / `plugin_config` assemble in the
following order (registry name-overwrite semantics; later registrations win):

```python
from norpagent.rescue_api import RescueToolEnvironment

env = RescueToolEnvironment(
    workspace_root=".",
    extra_tools={"my_tool": MyTool()},   # {name: tool} mapping / tool list / name-or-address list
    tools=["my_other_tool", "mypkg.tools:create"],  # registered-name refs + module addresses
    plugin_dirs=["./my_plugins"],        # external plugin directories (security pipeline)
    plugin_config={"plugin_security_audit": "warn"},
)
```

- `extra_tools` registers first, so **name references** in `tools` may point to
  tools registered by `extra_tools` or to built-ins; **module addresses**
  (`pkg.mod:attr`, same semantics as the `npa(tools=[...])` slot) resolve through
  `norpagent.arch.address.resolve_address`, with a clear error on failure;
- `plugin_dirs` load through the same security pipeline as the host application
  (defaults `plugin_security_audit=warn`, `plugin_signature_verify=True`);
  plugin-registered tools are tagged `origin="plugin"`;
- registration order: 20 built-ins → `extra_tools` → `tools` → plugin tools;
- CLI equivalents: `--tools` (comma-separated names or addresses), `--plugin-dirs`
  (comma-separated directories), see 13.5.

#### 15.6.4 Isolation and Safety Boundaries

- **no model, no plugins by default, no hooks**: `before_tool_call` etc. do not
  intervene (the rescue environment subscribes no hooks; the operator is the
  final approver); explicitly loaded plugins (`--plugin-dirs`) go through the
  host security pipeline and never alter the manual-call execution path;
- **path safety still applies**: absolute-path / `..` traversal rejection for
  `file_*`, the `run_python` AST static precheck (no import / no dunder
  attributes) all stay in force;
- **two-layer timeout**: tool-level timeouts (exec_cmd max 300s, run_python's
  `ptc_timeout`) plus environment-level hard timeout (default 300s, tunable via
  the HTTP body or `--timeout`) — a single timed-out call is abandoned (thread
  + cancel event) and never affects later calls;
- **concurrency-safe**: the environment is thread-safe (every component has its
  own lock); multiple HTTP requests can operate in parallel, sharing the same
  context-store / task-queue connections.

#### 15.6.5 Programmatic Embedding

```python
from norpagent.rescue_api import RescueToolEnvironment, RescueToolAPI
from my_tools import MyTool   # your custom tool implementation

env = RescueToolEnvironment(
    workspace_root=".",
    context_db="./rescue.db",
    extra_tools={"my_tool": MyTool()},   # custom tools are manually callable
    tools=["mypkg.tools:create"],        # or load by module address
    plugin_dirs=["./my_plugins"],        # or external plugins
)
print(env.call_tool("echo", {"text": "ping"})["output"])
print(env.call_tool("my_tool", {"arg": 1})["output"])  # custom tools too

api = RescueToolAPI(env, port=0, token="secret")   # port=0 = ephemeral port
port = api.start()                                 # returns the actual port
api.shutdown()
```

An application can also bring up the rescue service automatically after a model
health-check failure (for example mounting a `RescueToolAPI` inside the existing
process) so on-call operators can take over.

#### 15.6.6 Relationship with the Other Rescue Layers

| Layer | Goal | Entry |
|---|---|---|
| snapshot rollback | config / plugins broken — roll back to a good state | `norpagent-rescue rollback --last-good` |
| safe mode | keep rollback ability even when nothing starts | `npa(safemode="on")` / `--safe-mode` |
| **human rescue** | **model dead — a human does the model's work** | `norpagent-rescue tools / tool-call / manual / serve` |

The three complement each other: first roll back (or enter safe mode) to rescue
the configuration, then push the work forward with manual takeover, and when the
model recovers the agent continues from the same state (files / context store /
task queue).

---

## Chapter 16 Library Integration Examples

### 16.1 FastAPI Integration

```python
import norpagent as npa
from fastapi import FastAPI

npa(preset="standard", frontend="norpagent.frontends.headless:HeadlessFrontend")
app = FastAPI()

@app.post("/chat")
def chat(text: str, session_id: str | None = None):
    result = npa.current().submit(text, session_id=session_id)
    return {"content": result.final_content, "session_id": result.session_id,
            "status": result.status}
```

### 16.2 Desktop-App Integration (pywebview style)

```python
import norpagent as npa

npa(frontend="myapp.tray_frontend:TrayFrontend")
fe = npa.current().frontend

# the JS bridge forwards user input to fe.send();
# subscribe to on_content on the event bus to push streaming output back to the frontend.
```

### 16.3 Integration Points

1. **singleton engine**: the running engine is a singleton; `npa()` idempotently
   returns the current engine;
2. **lifecycle**: the main loop polls `npa.stop()`; process exit has an atexit
   fallback cleanup;
3. **assembly observation**: `npa.current().layer.describe()` prints the assembly
   manifest.

---

## Chapter 17 Testing and Debugging

```bash
python tests/test_p1_smoke.py    # kernel/protocol smoke
python tests/test_p2_smoke.py    # adapters/tools/sessions
python tests/test_p3_smoke.py    # context/scheduler/sandbox/security/plugins/Web
python tests/test_p4_smoke.py    # hooks/security/PTC/isolation
python tests/test_p5_arch.py     # architecture layer/address functions/npa()/nasyncio
```

Debugging aids:

```python
eng = npa.current()
print(eng.state)              # engine state
print(eng.layer.describe())   # assembly manifest
print(eng.last_result)        # most recent task result
```

---

## Chapter 18 Migration Guide

### 18.1 Migrating from Old norpagent (≤0.4)

```python
# old style: manual assembly
reg = Registry(); install_defaults(reg); register_all_presets(reg)
agent = AgentRuntime(reg, preset="minimal")
result = agent.run("hello")

# new style: npa() assembly (the manual assembly API stays usable)
import norpagent as npa
npa(preset="minimal", prompt="hello",
   frontend="norpagent.frontends.headless:HeadlessFrontend")
while True:
    if npa.stop():
        break
result = npa.current().last_result
```

The manual assembly API (Registry / AgentRuntime / Preset) **remains usable**;
`npa()` is its declarative wrapper.

### 18.2 Migrating from the Old Desktop Application

Modules in the old application mount into slots per the mapping below:

| Old application module | New slot | How to mount |
|---|---|---|
| `nasync_io` (self-developed event loop) | `async_loop` | **already packaged into the library**: `norpagent.nasyncio` is the default scheduling core (originally nasync_io v2.0.0); no self-hosted file needed; fill an address only when swapping implementations |
| `async_loop.AsyncAgentLoop` | `agent_runtime` | implement run/shutdown -> fill the address |
| FastAPI backend + desktop UI | `frontend` | implement the Frontend protocol -> fill the address |
| `plugin_system` | `plugins` | pass the directory list directly |
| `sandbox_pool` | `sandbox` | `"pooled"` or a custom address |
| `config.json` switches | preset params | task-parameter passthrough |

### 18.3 Version Compatibility

- the protocol modules (protocols) and the kernel (kernel) have been backward
  compatible since 0.1;
- 0.5 added the arch / loops / frontends / runtime packages;
- 0.6 added FLOW flow orchestration / FE frontend modules / the input-box family /
  agent-tool mounting (agent_tools) / the canvas-management trio; DeepSeek's
  `deepseek-chat` / `deepseek-reasoner` were officially retired on 2026-07-24, and
  the adapter defaults to `deepseek-v4-flash`;
- 0.7 added the Web frontend `html` slot mounting parameter (four ways to replace
  the `/` route page: `;key=value` address clause / constructor / config dict /
  runtime params), fixed the `;key=value` address-clause resolution chain, and
  added **runtime hot mount** (`npa.remount()` replacing any slot while running, see 3.7);
- 0.8 migrated the default event loop to the **self-developed nasyncio core**
  (originally nasync_io, packaged into the library as `norpagent.nasyncio`): the
  library has **zero `import asyncio`** and no longer depends on the standard
  asyncio (reasons in 4.7). The default address became
  `norpagent.loops.nasyncio:NasyncioLoopRuntime`; the 0.7 old address
  `norpagent.loops.std_asyncio:StdLoopRuntime` remains as a compatibility shim
  (same implementation, does not import asyncio); historical code keeps working;
- 0.9 embedded and ultra-high-concurrency optimizations (Chapter 14):
  `install_core()` minimal assembly and the builtin package lazy imports
  (`import norpagent.builtin` no longer pulls sqlite3 / http.server), the
  `embedded` preset (sixth mode, headless frontend by default), WebUI
  construction does zero disk I/O with page byte caching, EventBus copy-on-write,
  SSE bounded backpressure (default drop_oldest, hot-changeable) + batched frame
  writes + fast disconnect reclamation, HTTP concurrency tuning, submit polling
  default tightened to 0.05s (configurable). Behavior compatibility: SSE default
  buffer cap 1024 (slow clients drop the oldest; previously unbounded); the
  `unlimited` policy + `sse_queue_size=0` restore the old behavior;
- 0.9 hot-pluggable slot table (3.8): `register_slot()` / `unregister_slot()`
  register / unregister **custom slots** at runtime (`SlotSpec.applier` declares
  assembly logic, `remount_rebuild_agent` declares whether to hot-rebuild the
  AgentRuntime after a hot replacement); registration plugs into the full
  pipeline — `npa()` parameter validation, ArchLayer assembly (connect
  idempotently fills in late-registered slots), `npa.remount()` hot replacement,
  `layer.describe()` listing; `replace=True` spec hot-replacement is supported;
  the 18 built-in slots are protected (their values can still be hot-replaced at
  any time); slot-table operations are thread-safe. Behavior compatibility: the
  assembly / hot-mount semantics of the existing 18 slots are completely unchanged;
- 0.9 work rollback (Chapter 15): snapshot timeline + Undo / Redo / Rollback
  (in-process immediate, reusing the remount hot-mount pipeline) + the standalone
  crash-rescue CLI
(in-process immediate, reusing the remount hot-mount pipeline) + the standalone
crash-rescue CLI `norpagent-rescue` (pure standard library; suggests the last
known-good snapshot for one-step restore; the rollback target is consumed
automatically at the next startup) + safe mode (`npa(safemode="on")` / CLI
`--safe-mode`, loads only the minimal kernel); auto snapshots are on by default
(after remount / settings saved / plugins installed), sensitive keys are redacted
before persisting, custom snapshot providers and snapshot mode B (including session
data files) are supported;
- breaking changes appear only in major versions.

---

## Chapter 19 FAQ

**Q1: does `npa()` block?**
No. The engine runs on background threads and the main thread keeps executing —
this is exactly why the `while running: if npa.stop()` pattern exists.

**Q2: when does `npa.stop()` become True?**
When the engine is STOPPED: the single task finished, the frontend `/exit`, an
explicit `shutdown()`, or any `request_stop()`. Always True with no engine.

**Q3: how do I pass the model API key?**
```python
npa(model="openai_compat", model_name="deepseek-v4-flash",
   base_url="https://api.deepseek.com/v1", api_key="sk-...")
```
`model_name / base_url / api_key` are model shortcut parameters: when the model is
a built-in adapter name the provider is reconstructed automatically (same as the
CLI); or set the environment variable `OPENAI_API_KEY` directly; or pass a
constructed provider instance `npa(model=MyProvider())`.

**Q4: can address strings cause arbitrary code execution?**
Yes. An address string names the module to load; address values are passed by the
library's users in code. External plugin loading goes through signature
verification, AST audit and import restrictions.

**Q5: can I run two different Agents at once?**
The running engine is a singleton. For multiple instances use the manual assembly
API directly: `Registry() + AgentRuntime(...)`, not bound by the singleton
(17.1).

**Q6: do hooks keep working after replacing the loop system?**
Yes. Hooks hang on the event bus (the bottom minimal kernel), independent of the
loop system.

**Q7: what is the difference between `npa(async_loop=...)` and `npa.nasyncio(...)`?**
None — the same path; the former is the slot form, the latter the architecture
function form.

**Q8: what are the `/flow` canvas, FE frontend modules, and the input-box family?**
`/flow` is a standalone frontend category "module flow": the canvas graph
auto-saves and can hot-switch front chat behavior with "apply to agent". FE =
frontend modules registered by dragging in `.html/.js/.ts` files (hosted at
`/fe/<name>`, independent config scope). The input-box family = every place that
needs input is an input box: one input-box row per config item on FE /
global-settings node cards, a value input-box strip at the bottom of
model/tool/sandbox node cards, and every model field is a hand-editable input box
+ datalist hint (type manually even when the fetch fails). See 5.7 and
`docs/flow.md`.

**Q9: how do I bulk-clean the canvas? Can deepseek-chat still be used?**
Canvas: `Alt+drag` box select / `Ctrl+A` select all then `Del` bulk-delete; the
top bar's "clear canvas" wipes everything in one click (auto-saves immediately
after confirmation; refreshing stays blank); double-click-inject and
single-click-dock-card quick-inject were removed (to prevent accidental node
spam). deepseek-chat / deepseek-reasoner were retired by DeepSeek on 2026-07-24;
the current models are deepseek-v4-flash / deepseek-v4-pro; old names are
auto-filtered from the hint list, the remote-model dock and the backend cache
(`RETIRED_REMOTE_MODELS`).

**Q10: the web side has too few native tools — how do I wire third-party custom
tools and let the agent call them automatically?**
"File-as-module" mounting: drag a `.py` file declaring
`__norpagent_type__ = "tool"` onto the `/flow` canvas for real registration
(through the plugin security pipeline); the tool node's ports come automatically
from the OpenAI function schema. To let the agent in front chat call them
automatically (tool calling): ① click the `AGENT` badge on the tool card in the
`/flow` module dock; ② tick the "🧰 agent tools" list in the WebUI settings dialog.
Both go through `POST /api/agent/tools` (config keys `agent_tools` /
`agent_tools_explicit`) and hot-apply `preset.tools`, effective on the next
run(), no restart. See 5.7 "agent-tool mounting" and `docs/flow.md` section 9.

**Q11: can I swap the model / frontend / modules after startup? (runtime hot
mount)**
Yes. `npa.remount(slot=value)` replaces any slot while the engine runs: component
slots (model / tools / hooks / security / plugins) take effect on the next run();
assembly slots (session / sandbox / scheduler / ui / agent_runtime / preset /
context_store / project_manager) trigger an AgentRuntime hot rebuild;
frontend / async_loop stop the old and start the new; logger / storage /
error_handler update immediately. String addresses invalidate the module cache
and .pyc before remounting, so "edit the module file →
npa.remount(model="myapp.model:create")" is hot reload. Repeatedly mounted
architecture-level subscriptions are unsubscribed first then remounted, never
stacking. See 3.7.

**Q12: why did Ctrl+C fail before? How is interruption guaranteed now?**
Two root causes (see 4.6): ① on Windows the main thread blocked in a single
`Event.wait()` (`WaitForSingleObject`) never sees SIGINT — the pending interrupt
is only checked at bytecode boundaries; now `submit()` uses polling wait (a
boundary every ≤poll_interval seconds, default 0.05s, configurable), so Ctrl+C
surfaces immediately as `KeyboardInterrupt`.
② worker threads stuck in sandbox `subprocess` / HTTP cannot be killed, and the
standard thread pool (ThreadPoolExecutor, also asyncio's default executor) is
force-joined at interpreter exit — the process freezes until the task ends; now
the worker pool uses bare daemon threads (no join at exit), and Ctrl+C / engine
stop sets the task's cancel event: the PTC sandbox force-kills the child process
immediately, the pooled sandbox kills the process tree, model streams interrupt,
and the agent wraps up as stopped at turn boundaries. Task bodies can proactively
respond to cancellation with `norpagent.loops.cancel.cancel_requested()`.

**Q13: does norpagent depend on the standard asyncio?**
No. Since 0.8 the library has **zero `import asyncio`**: the default scheduling
core is the self-developed async-IO library `norpagent.nasyncio` packaged into
the library (originally nasync_io), using only non-asyncio standard modules like
threading / selectors / socket. Declaration, reasons and verification in 4.7.

**Q14: how do I deploy on embedded devices / ultra-high-concurrency servers?
(0.9)**
- **embedded**: `install_core()` with a self-built registry (no sqlite3 /
  http.server imports) + `build_embedded_preset()`, or directly
  `npa(preset="embedded")` (headless frontend by default, mock fallback); tighten
  worker threads with `NORPAGENT_MAX_WORKERS=1` (or `config={"loop":
  {"max_workers": 1}}`), relax polling with `NORPAGENT_SUBMIT_POLL`.
- **ultra-high-concurrency**: SSE per-connection bounded buffer default 1024,
  slow clients drop the oldest (`drop_oldest`); configure at startup with
  `npa(config={"web": {"sse_queue_size": 2048}})`, hot-change while running with
  `WebUI.set_sse_queue(...)` / `POST /api/streams`; batched frame writes (default
  32 frames / 50ms) reduce system calls; EventBus copy-on-write eliminates
  per-event list copies. Full details in Chapter 14.

**Q15: what if the framework lacks the slot I need? (hot-pluggable slot table,
0.9)**
Register your own: `register_slot(SlotSpec(name=..., string_semantics=...,
applier=...))`. Registration plugs into the full pipeline — `npa()` parameter
validation, assembly, `npa.remount()` hot replacement, `layer.describe()`
listing; the applier receives the resolved slot value and four mutable containers
(components / extras / overrides / meta) and can register generic components
(`remount_rebuild_agent=True` hot-rebuilds the AgentRuntime after a hot
replacement), mount event subscriptions (recorded in meta for unsubscribe, so
reentrancy is safe), or provide extra objects to the engine. The 18 built-in
slots are protected (cannot be overridden / unregistered); their values can be
hot-replaced with `npa.remount` at any time. Full contract in 3.8.

**Q16: how do I undo a config change / roll back to a previous state? (work
rollback, 0.9)**
Three steps: in-process `npa.undo()` / `npa.redo()` (Web UI Ctrl+Z / Ctrl+Shift+Z
or the "rollback" panel buttons, immediate); roll back to any version with
`npa.rollback("<snapshot id>")` (`npa.list_snapshots()` browses the timeline;
`npa.rollback()` with no args = the last known-good snapshot); when the main
program cannot start use `norpagent-rescue rollback --last-good` (pure
standard-library CLI; applied automatically at the next startup), or
`norpagent --safe-mode` / `npa(safemode="on")` to load only the minimal kernel and
fix the config. Snapshots default to `~/.norpagent/snapshots/`; sensitive keys
are redacted; auto snapshots are on by default (disable with
`npa(snapshots="off")`). Full semantics in Chapter 15.

---

## Appendix A Architecture Slot Quick Reference

| Slot | String semantics | Default | Factory context keys |
|---|---|---|---|
| async_loop | address | NasyncioLoopRuntime (self-developed nasyncio core; config.loop tunes max_workers / poll_interval) | layer, config |
| agent_runtime | address | AgentRuntime | registry, preset, ui, task_params, layer, config |
| model | name_or_address | preset declaration | layer, config |
| tools | name | preset declaration | - |
| session | name_or_address | preset declaration | - |
| sandbox | name_or_address | preset declaration | - |
| scheduler | name_or_address | preset declaration | - |
| context_store | address | preset declaration | layer, config |
| project_manager | address | preset declaration | layer, config |
| hooks | literal | the standard 9 layers | - |
| security | literal | not enabled | - |
| plugins | literal | not loaded | - |
| frontend | address | prompt / embedded→headless, otherwise web | layer, config |
| ui | name | preset declaration | - |
| preset | name | standard | - |
| logger | literal | logging.getLogger("norpagent") | - |
| storage | literal | ~/.norpagent | - |
| error_handler | literal | records to the log | - |

> Runtime hot mount (3.7): every slot can be replaced with `npa.remount(slot=value)`.
> `agent_runtime` is a `defer_factory` slot (the factory call is deferred to the
> engine assembly phase). Hot-pluggable slot table (3.8): `register_slot()` can
> register custom slots into this table.

## Appendix B 9-Layer Hook Quick Reference

| Layer | Hooks | Mutating | Key params |
|---|---|---|---|
| L1 lifecycle | on_agent_init / on_agent_shutdown | - | preset |
| L2 task | on_task_start / on_task_done / on_task_stopped / on_task_error / on_task_timeout | - | task_id, session_id |
| L3 input | before_input / after_input / on_user_input_required | before | user_input, params, question |
| L4 session | before_session_create / after_session_create / before_message_append / after_message_append | before | title, message |
| L5 assembly | before_build_messages / after_build_messages | both | system_prompt, messages |
| L6 step | before_step / after_step | before | step, messages |
| L7 model | before_model_call / after_model_call / on_reasoning / on_content / on_event / on_usage_update | before/after_model_call | messages, output, params |
| L8 tool | before_tool_call / after_tool_call / on_tool_error | both | tool_name, args, result |
| L9 finalize | before_result / after_result | both | result |

> Full payload keys and the complete 29-hook table in 9.1; full return semantics
> of mutating hooks (HookVeto wrap-up / rewrite rules) in 9.3.
> The plugin-loading pipeline has 8 more hooks (PLUGIN_PIPELINE_LAYER), see 11.4.

## Appendix C Public API Index

```python
# module entry
npa()                      # launch()
npa.stop()                 # lifecycle polling
npa.nasyncio(address=...)  # event-loop architecture function (npa.nasyncio binds the self-developed core module, callable)
npa.current() / npa.submit() / npa.shutdown()
npa.remount(model=..., ...)   # runtime hot mount: any slot replaceable

# work rollback (Chapter 15)
from norpagent.recovery import (snapshot_system, undo, redo, rollback,
                                list_snapshots, mark_good, last_good_id,
                                register_snapshot_provider, set_snapshot_dir,
                                prune, RecoveryError)
npa.snapshot_system("description")  # manual snapshot (top-level convenience entry)
npa.undo() / npa.redo()             # undo / restore (in-process immediate)
npa.rollback("<id>")               # roll back to any snapshot (default = last known good)
npa.mark_good_snapshot("<id>")     # mark "known good"
npa(safemode="on")                 # safe mode: loads only the minimal kernel
npa(snapshot_dir=..., snapshots="off", snapshot_sessions="on")  # snapshot config
# crash rescue: norpagent-rescue list|show|rollback|mark-good|prune
# human rescue (15.6): norpagent-rescue tools|tool-call|manual|serve
#   v0.9.7 custom tools: --tools <name|pkg.mod:attr>[, ...]  --plugin-dirs <dir>[, ...]
from norpagent.rescue_api import (RescueToolEnvironment, RescueToolAPI)
env = RescueToolEnvironment(workspace_root=".", context_db="./rescue.db")
env = RescueToolEnvironment(extra_tools={"my_tool": MyTool()},
                            tools=["pkg.mod:create"],
                            plugin_dirs=["./my_plugins"])   # v0.9.7 custom tools
env.call_tool("echo", {"text": "ping"})     # manual args in + raw result out
api = RescueToolAPI(env, port=0, token=...) # HTTP API + operator page
api.start() / api.shutdown()

# architecture layer
from norpagent.arch import ArchLayer, SlotSpec, SLOT_SPECS
from norpagent.arch import resolve_address, call_factory, AddressError
layer.remount(slot, value)  # architecture-layer hot mount (module cache + pyc invalidation)
layer.subconfig(slot)       # slot extra sub-config (";key=value")

# hot-pluggable slot table (3.8)
from norpagent.arch import (register_slot, unregister_slot, SlotError,
                            all_slot_names, snapshot_slots, is_builtin_slot)
register_slot(SlotSpec(name=..., string_semantics=..., applier=...,
                       remount_rebuild_agent=...))   # register a custom slot
register_slot(spec, replace=True)   # hot-replace a custom slot's spec
unregister_slot(name)               # unregister a custom slot

# loop system
from norpagent.loops import (nasyncio, LoopRuntime,
                             NasyncioLoopRuntime, StdLoopRuntime)
from norpagent.loops.cancel import cancel_requested, current_cancel_event
loop.interrupt()   # request cancellation of all in-flight submit tasks (the engine-stop path)

# self-developed async core (packaged into the library, no standard-asyncio dependency)
import norpagent.nasyncio as core
core.EventLoop / core.Future / core.Task        # self-developed types
core.sleep / core.wait_for / core.ensure_future # utility coroutines
core.run_coroutine_threadsafe(coro, loop)       # cross-thread coroutine submission
core.Event / core.Lock / core.Condition         # synchronization primitives

# frontends
from norpagent.frontends import (Frontend, ConsoleFrontend,
                                 HeadlessFrontend, WebFrontend)

# runtime
from norpagent.runtime import (launch, current, stop, submit,
                               shutdown, NorpEngine, EngineState, EngineError)
# task-level slot injection (3.9): submit(text, slot_overrides={...})
#   engine.submit("task", slot_overrides={"model": "anthropic", "tools": [...]})
#   npa.submit("task", slot_overrides={"session": {"name": "memory", "persist": True}})

# kernel (manual assembly, equivalently kept)
from norpagent import (Registry, EventBus, Preset, AgentRuntime,
                       RunResult, install_defaults, install_core,
                       register_all_presets, build_embedded_preset)
# install_core(reg): embedded minimal assembly (no sqlite3 / http.server dependencies)
# build_embedded_preset(): embedded preset (sixth mode)
# general-purpose event bus (27.2; the class stays EventBus):
#   bus.once(fn, type=None)          # one-shot subscription (auto-unsubscribes after firing)
#   bus.wait(type, timeout=None)     # block for an event -> AgentEvent | None
#   bus.emit_all(type, **kw)         # publish and collect all return values -> list
#   bus.subscriber_count(type=None)  # subscriber count
#   bus.has_listeners(type=None)     # are there any subscribers
#   bus.clear(type=None)             # clear subscriptions (returns removed count)

# security / hooks / plugins
from norpagent import safe, SafetyKit, SecurityContext
from norpagent import hooks                      # hook system (HookSystem)
from norpagent.hooks import (Hook, BoundHook, HookLayer, HookSystem,
                             HookVeto, get_default_system,
                             before_input, before_model_call,
                             before_tool_call, after_tool_call, ...)  # 29 standard hooks
from norpagent.plugins import (PluginSystem, PluginLoader, PluginInfo,
                               install_plugin_dirs, PLUGIN_PIPELINE_LAYER,
                               before_plugin_load, after_plugin_register, ...)
from norpagent.plugins.isolation import ProcessIsolationManager, ProcessPluginHost
from norpagent.security import (scan_message, harden_system_prompt,
                                ApprovalPolicy, NetworkPolicy, SourceAuditor,
                                SignatureVerifier, generate_keypair, sign_plugin_file)

# Web UI: page mounting and hot replacement (5.4) + SSE backpressure (ultra-high concurrency, 14.3)
from norpagent.builtin.ui.web import WebUI
ui = WebUI(port=8787, html="/path/to/my.html",
           flow_html="/path/to/flow.html")     # replace the / and /flow pages wholesale
ui = WebUI(port=8787, sse_queue_size=2048,
           sse_queue_policy="drop_oldest")
ui.mount_page("flow", "/path/to/new-flow.html")  # hot page swap while running (no service restart)
ui.mount_page("flow", None)                      # unmount, fall back to the library built-in
ui.page_bytes("flow")                            # current /flow page bytes
ui.set_sse_queue(4096, "drop_newest")   # hot change while running (equivalent to POST /api/streams)
ui.streams_info()                        # subscriber count / dropped-event count / buffer depth
# WebFrontend homogeneous entry: frontend.mount_page(page, html)
# remount page hot-replace keys (v0.9):
#   npa.remount(flow_html="/path/to/new-flow.html")  # /flow page swapped immediately
#   npa.remount(html="/path/to/new-front.html")      # / main page swapped immediately
#   npa.remount(flow_html=None)                      # unmount, fall back to the library built-in
# frontend slot HTML-path direct mount (v0.9):
#   npa(frontend="/path/to/my.html")  ==  npa(frontend="...WebFrontend;html=/path/to/my.html")
```

**Q17: can the standard asyncio and the self-developed nasyncio be used at the same time?**
Yes — they do not conflict and can coexist in one process: norpagent schedules only through
nasyncio on the `async_loop` slot (no import of, and no takeover of, the standard asyncio),
while your own code may keep using the standard asyncio (including `asyncio.run`). Where the
two collaborate, use thread-safe APIs (`run_coroutine_threadsafe` / `LoopRuntime.submit`). See §4.7.

---

## Chapter 20 Module Flow Orchestration (FLOW)

> This chapter corresponds to `norpagent/flows/__init__.py` (1535 lines, one of
> the framework's largest orchestration kernels). 5.7 covered the `/flow` page's
> frontend form; this chapter dives into its **kernel**: registry snapshots,
> file-as-module, topological execution and agent interplay.

### 20.1 Positioning and Overview

"Module flow" (`/flow`) is not an animated demo — it executes the canvas graph
with **real registered components**:

```
build_snapshot(registry, agent)   registry snapshot: model / tools / session / sandbox /
                                 scheduler / plugins / preset / hooks
                                 -> the frontend "core module dock" renders cards per real component
ModuleWorkspace.register(...)    "file-as-module": dragging in a .py goes through the full security
                                 pipeline (signature verification -> AST audit -> import restrictions -> registration)
FlowRunner                       topologically executes per the canvas graph (nodes + beams),
FlowRunner                       topologically executes per the canvas graph (nodes + beams),
                                 progress pushed via flow.* events over SSE
```

Three core classes / functions:

| Name | Duty |
|---|---|
| `build_snapshot(registry, agent)` | serializes the registry's current state into a snapshot dict, driving the frontend module dock |
| `ModuleWorkspace` | the on-disk workspace of flow modules: register / load .py / .json / .yaml modules |
| `FlowRunner` | the canvas-graph executor: node + beam topological execution, zero-interruption, event publishing |

### 20.2 Registry Snapshot: build_snapshot

```python
from norpagent.flows import build_snapshot

snap = build_snapshot(registry, agent)
# includes: models / tools / sessions / sandboxes / schedulers /
#           plugins / presets / hooks (one record per registered component)
```

- the snapshot is **live**: whatever is registered in the registry is what the
  frontend module dock shows;
- each component carries metadata (description / source / port inference) for
  canvas rendering;
- the snapshot drives the whole "module dock → drag onto the canvas → instance
  selection" interaction.

### 20.3 File-as-Module: ModuleWorkspace

```python
ws = ModuleWorkspace(registry, base_dir=default_modules_dir())
info = ws.register("my_node.py")      # goes through the plugin security pipeline
info = ws.register("graph.json")      # pure description module (pass-through node)
info = ws.register("graph.yaml")      # same
```

| File type | Handling |
|---|---|
| `.py` | full security pipeline: signature verification → AST audit → import restrictions → registration into the registry; every hook of a successfully registered plugin becomes a hook node on the canvas |
| `.json` / `.yaml` | registered as pure description modules (pass-through nodes, no execution logic) |
| others | explicit error; the frontend falls back to the official module |

- module directory: overridable with the environment variable
  `NORPAGENT_FLOW_MODULES`, default `~/.norpagent/flow_modules`;
- single-file size cap 200KB (`_MAX_MODULE_SIZE`).

### 20.4 Canvas-Graph Format: normalize_graph

The canvas graph is a "nodes + beams" dict structure; `normalize_graph` normalizes
and validates it:

```python
graph = {
    "nodes": [
        {"id": "n1", "type": "trigger"},
        {"id": "n2", "type": "model", "model": "openai_compat",
         "system_prompt": "...", "tools": ["echo"]},
        {"id": "n3", "type": "tool", "tool": "file_read",
         "inputs": {"path": {"from": "n4", "port": "path"}}},
        {"id": "n4", "type": "path", "value": "./readme.md"},
        {"id": "n5", "type": "output"},
    ],
    "beams": [["n1", "n2"], ["n2", "n3"], ["n3", "n5"], ["n4", "n3"]],
}
```

Node types and execution semantics (type → real action):

| Node | Real action |
|---|---|
| `trigger` | reads the prompt input, produces the start signal |
| `model` | calls the registry's real model; the `tools` port = the container-mounted tool set (schemas auto-resolved and passed to the provider); the `system_prompt` port = the system prompt (priority: beam value > input panel > node config > engine preset params; empty values do not inject a system message) |
| `tool` | calls the registry's real tool: each input port = one schema parameter (no longer a global query/result black box) |
| `toolbox` | tool container: input ports = the union of member-tool parameters (fanned out by port name); output ports = each member's "toolname.portname" qualified names + the tools packed port |
| `sandbox` | executes code in the registry's real sandbox (child-process isolation) |
| `security` | scans payloads for jailbreak / injection (`norpagent.security.guard`) |
| `session` | reads/writes the session manager (the engine's default session store) |
| `plugin` | plugin container (members = tool + hook members, port-union semantics) or standalone plugin-tool execution |
| `hook` | triggers a single hook of a plugin (one hook = one node; mutating hooks go through intercept, the return value becomes the node output) |
| `other` | pass-through (payload forwarded as-is) |
| `output` | aggregates the final result |
| `path` | path module: produces a relative path value validated by common path-safety checks (absolute paths / `..` traversal rejected); empty value = the workspace root `.` |
| `file` | file module: when registered as a plugin, executes as a plugin; otherwise pass-through |

### 20.5 FlowRunner: Topological Execution and Zero-Interruption Semantics

```python
runner = FlowRunner(graph, registry, agent, publish=on_event, workspace=ws)
result = runner.run(prompt="...", session_id="...", params={...})
```

Key designs:

1. **topological execution**: execution order determined by beam dependencies; each
   node has its own `try/except`;
2. **zero-interruption semantics**: a single node failure records `error` but does
   not interrupt the whole chain (other nodes execute normally);
3. **event publishing**: progress is pushed via the `publish` callback as `flow.*`
   events; the Web UI reuses the SSE channel (`/events`) to deliver in real time;
4. **stop support**: `runner.request_stop()` takes effect at node boundaries;
5. **cancellation propagation**: node execution also checks
   `params["_cancel_event"]`; engine stop / Ctrl+C exits as early as possible.

### 20.6 Flow-Agent Interplay (apply to agent)

A canvas graph can be "applied" as the main UI's execution engine:

```python
# Web UI side (the "/flow" page's "apply to agent" button):
ui.flow_save(graph, activate=True)    # save and activate
_active = ui._active_chat_flow()      # the currently active flow (None when not activated)

# once activated, main-UI chat tasks execute per the flow:
ui._run_flow_task(prompt, session_id, task_params)
# the flow execution result is written into the session history (_append_flow_history),
# consistent with ordinary tasks
```

That is: **ordinary chat → canvas orchestration → session history** are fully
connected.

### 20.7 Web UI Integration and APIs

| API | Purpose |
|---|---|
| `flow_snapshot` | registry snapshot, driving the `/flow` page's module dock and instance selection |
| `flow_run` | start one canvas-graph execution (background thread; progress pushed over SSE) |
| `flow_stop` | stop a running flow (effective at node boundaries) |
| `flow_register` | "file-as-module" real registration (.py plugin security pipeline / .json / .yaml descriptions) |
| `flow_save` | save the canvas graph (auto-save entry), optionally activate "apply to agent" |
| `flow_load` | return the last auto-saved canvas graph and activation state (restored after a page refresh) |
| `_load_flow_graph_from_disk` | restore the last saved flow at startup (silently ignored when the file is missing / corrupted) |
| `fe_read_file` / `fe_load_config` / `fe_save_config` | FE frontend-module file reading and independent config (no interference) |

### 20.8 Module Directory and Security Boundaries

- module directory: the `NORPAGENT_FLOW_MODULES` environment variable or
  `default_modules_dir()`;
- `.py` modules share the same security pipeline as external plugins (Chapter 11):
  signature → audit → import restrictions → registration;
- `path` nodes enforce common path-safety validation (absolute paths / `..`
  traversal rejected);
- single-file 200KB cap + output truncated at 4000 chars (`_MAX_OUTPUT_CHARS`) to
  prevent resource blowups.

---

## Chapter 21 Built-in Components in Depth

> This chapter dissects the built-in implementations under `builtin/` one by one:
> internal mechanisms, protocol relations, selection advice. All built-in
> components have equal status with third-party components — they go through the
> registry and can be replaced by anything.

### 21.1 Model Adapters

| Adapter | File | Features |
|---|---|---|
| `mock` | `builtin/models/mock.py` | deterministic output: built-in Q&A pairs + guidance, zero dependencies, for testing / benchmarks / no-network environments |
| `openai_compat` | `builtin/models/openai_compat.py` | OpenAI-compatible protocol (DeepSeek / OpenAI / Qwen / vLLM / Ollama etc.), SDK provided by `norpagent[openai]`; supports reasoning effort (`model_supports_reasoning_effort` / `normalize_effort`), DeepSeek v4 special-casing (`model_is_deepseek_v4`), chain-of-thought extraction (`_extract_reasoning`) |
| `anthropic` | `builtin/models/anthropic.py` | Anthropic-protocol adapter, SDK provided by `norpagent[anthropic]` |

Common points (protocol `ModelProvider`):

- `generate(messages, tool_schemas, params) -> ModelOutput` (including usage);
- optional `stream(...)`: streaming `ModelStreamChunk` output (content deltas /
  chain-of-thought / tool calls);
- cancellation support: adapters read `params["_cancel_event"]` and exit the
  streaming loop as early as possible on engine stop / Ctrl+C;
- credential fallback: when no key is provided at all, the assembly layer falls
  back to `mock` (`runtime/mount.py`'s `_has_model_credentials` checks
  `OPENAI_API_KEY` / `DEEPSEEK_API_KEY` / `ANTHROPIC_API_KEY` /
  `DASHSCOPE_API_KEY` / `NORPAGENT_API_KEY`).

### 21.2 The Tool Set (21 built-in tools)

| Group | Tools | Notes |
|---|---|---|
| P1 basics | `echo` / `get_time` / `run_python` | echo / clock / Python execution (the PTC prototype) |
| P2 engineering | `file_read` / `file_write` / `file_list` / `file_delete` | file operations, **strictly confined to the workspace root** (`pathsafe` validation: absolute paths and `..` traversal rejected; configurable root) |
| P2 commands | `exec_cmd` | command execution through the sandbox protocol (`sandbox.run_shell`), timeout clamped (`_MAX_TIMEOUT`) |
| P2 web | `web_search` / `web_fetch` / `web_extract_links` | web retrieval; **SSRF protection** (`is_private_url` rejects private networks / metadata addresses); uses requests when available, otherwise urllib fallback; bs4 structured extraction when available, otherwise regex fallback — usable with zero dependencies |
| P3 context | `context_add` / `context_search` / `context_list` / `context_delete` | cross-session searchable knowledge base (FTS5, see 21.6) |
| P3 project | `project_status` | project management (git-aware, see 21.7) |
| P3 tasks | `task_submit` / `task_list` / `task_status` / `task_cancel` | long-running task cooperation (persistent scheduler, see 21.5) |

Tool protocol (`protocols/tool.py`): `name` / `schema()` / `run(args, ctx)`,
returning `ToolResult`; `ctx` carries a `RunContext` (component access:
`ctx.component("context_store")` etc.).

### 21.3 Session Stores

| Implementation | Features | Suitable for |
|---|---|---|
| `memory` | pure in-memory dict, lost when the process ends | embedded / tests / single tasks |
| `sqlite` | SQLite persistence: schema + message migration (`_MESSAGE_MIGRATIONS` incremental upgrades), `close` / `clear` lifecycle | default (standard preset); conversations continue across restarts |

Protocol (`protocols/session.py`): `create_session / get_session / append_message /
history / list_sessions / delete_session`.

### 21.4 Sandboxes

| Implementation | Mechanism | Suitable for |
|---|---|---|
| `subprocess` | spawns a child process per call, simple and direct | lightweight / embedded |
| `pooled` | **sandbox pool**: child-process reuse + concurrency cap + timeout force-kill of the process tree (`_kill_process_tree`, `taskkill /T` on Windows); `PooledSandboxProvider` manages the pool lifecycle (create / release / discard / kill_task / close_all / stats) | default (standard preset); balance of performance and isolation |
| `isolated_python` | PTC child-process isolated execution: `check_ptc_source` static validation + wrapper template (`_WRAPPER_TEMPLATE`) + result return (`_CALLER_SRC`) | the isolated execution path of the `run_python` tool |

Protocol (`protocols/sandbox.py`): `Sandbox.run_shell / run_python / close`,
`SandboxProvider.create`.

### 21.5 Schedulers

| Implementation | Mechanism | Suitable for |
|---|---|---|
| `simple` | in-memory queue: submit / pending / drain | embedded / tests |
| `persistent` | **SQLite-persisted scheduling**: tasks on disk (`_SCHEMA`), terminal states (`_TERMINAL_STATUSES`), `resume` after a crash, `counts` / `list_tasks` / `cancel` / `clear` | default (standard preset), long-running task cooperation |

### 21.6 The Context Store (FTS5)

`builtin/context/fts5.py`: a cross-session knowledge base implemented with SQLite
FTS5 full-text indexing.

- **Chinese tokenization**: `_tokenize` has built-in Chinese segmentation
  (bigram + single characters), no jieba dependency — zero third-party dependencies;
- **queries**: `_tokenize_for_query` + `_fts5_phrase` build phrase queries;
- API: `add / update / search / get / list / delete / clear / stats / close`.

### 21.7 Project Management (BasicProjectManager)

`builtin/projects/basic.py`:

- project metadata: `_META_DIR` / `_META_FILE` (meta read/write, `init /
  load_meta / save_meta / touch`);
- directory scanning: `scan` (skips `_SKIP_DIRS`);
- **git-aware**: `git_status` (probes the `git` command; degrades gracefully
  without git);
- API: `status` (used by the `project_status` tool).

---

## Chapter 22 Web UI and Frontend Deep Dive

> Corresponding code: `builtin/ui/web.py` (2596 lines) + `frontends/web.py`
> (407 lines). 5.4 covers usage; this chapter covers **internal mechanisms and
> the complete API set**.

### 22.1 Architecture and Thread Model

```
browser ──HTTP──▶ _RobustHTTPServer (tuned ThreadingHTTPServer)
              ├── /           main chat page (front.html, hot-replaceable)
              ├── /flow       flow-canvas page (norpflow.html, hot-replaceable)
              ├── /api/*      dozens of REST endpoints
              └── /events     SSE long connection (all events pushed in real time)
                └── _SSESubscriber (bounded buffer + condition-variable wakeup, one per connection)

WebUI.start()        background daemon thread serve_forever (non-blocking)
WebUI.submit()       submit a task (background thread execution, does not block HTTP)
WebUI.on_event()     receives AgentEvent -> pushes to all SSE subscribers + records history
```

`_RobustHTTPServer` tuning points: silent disconnect noise (WinError 10053 etc.),
`daemon_threads=True`, `allow_reuse_address=True` (reuse the port immediately on
restart), `request_queue_size=256` (listen backlog), `block_on_close=False` (fast
shutdown).

### 22.2 REST API Reference

| Group | Endpoint (method) | Purpose |
|---|---|---|
| tasks | `submit` / `stop_task` | submit a task / stop a task (effective at step boundaries) |
| sessions | `create_session` / `session_info` / `list_sessions` / `session_messages` / `close_session` / `set_session_title` / `set_session_workspace` | full session lifecycle + message history + workspace |
| config | `get_config` / `save_config` / `reset_config` / `set_api_key` / `validate_api_key` / `first_run` | the config panel (persisted to `~/.norpagent/webui_config.json`, atomic writes) |
| models | `list_models` / `set_agent_tools` / `agent_effective_tools` / `tools_info` | model list (including remote), tool-set management |
| plugins | `get_plugin_dirs` / `list_plugins` / `add_plugin_dir` / `remove_plugin_dir` / `reload_plugins` | plugin directories and hot reload |
| security | `get_security` / `set_security` | security-level read / set |
| monitoring | `health` / `usage` / `debug_info` / `streams_info` | health check / usage / debug / SSE backpressure stats |
| files | `list_fs` / `read_fs_file` / `upload_files` | directory navigation / file reading / dataURL upload (no binaries) |
| flow | `flow_snapshot` / `flow_run` / `flow_stop` / `flow_register` / `flow_save` / `flow_load` | canvas orchestration (Chapter 20) |
| rollback | `recovery_handle` | snapshot / Undo / Redo / Rollback API (`/api/snapshots`) |
| frontend modules | `fe_read_file` / `fe_load_config` / `fe_save_config` | FE module reading and independent config |

### 22.3 The SSE Event Protocol

- channel: the `/events` long connection;
- frame format: `data: {json}\n\n` (`_encode_sse_frame`, module-level reuse to
  avoid building a lambda per frame);
- event content: same-named events as the EventBus (`on_task_start` / `on_content`
  / `on_reasoning` / `after_tool_call` / `flow.*` ...) serialized as JSON frames;
- **backpressure** (`_SSESubscriber`):

| Policy | Semantics | Suitable for |
|---|---|---|
| `drop_oldest` (default) | buffer full drops the oldest; the client degrades without disconnecting | display-style frontends |
| `drop_newest` | buffer full drops the newest; keeps the old state | state-sync consumers |
| `unlimited` | no cap (old behavior) | when you explicitly need everything |

- hot change while running: `ui.set_sse_queue(maxsize, policy)` (effective on
  existing connections immediately);
- wakeup optimization: one wakeup on the empty→non-empty transition; readers drain
  the buffer per wakeup (less locking under high concurrency);
- disconnect reclamation: subscribers are reclaimed within ≤1s after disconnect
  (copy-on-write replacement, never blocks publishing).

### 22.4 Config Panel and Persistence

- config items: model (name / base_url / api_key / sampling params like
  temperature), tool set, plugin directories, security level, port / language etc.;
- persistence: `_save_config_to_disk` atomic writes (failure only logs, never
  drags down saving); startup `_load_config_from_disk` restores (missing /
  corrupted files silently ignored);
- after saving, `set_config_apply` callbacks re-register models / plugins /
  security (`WebFrontend._apply_config`);
- config snapshot: the work-rollback system includes the WebUI settings file in
  snapshots (Chapter 15); `restore_config` restores it on rollback.

### 22.5 Pages and Frontend Modules (FE)

- pages: `/` (front.html) and `/flow` (norpflow.html), both hot-replaceable at
  runtime (`mount_page` / `npa.remount(html=...)` / `npa.remount(flow_html=...)`),
  HTTP not restarted, port unchanged;
- FE frontend modules: `.html` / `.js` / `.ts` files (`fe_read_file` returns by
  mime); after startup `_scan_fe_modules` rescans the module directory to restore
  the list (survives restarts);
- independent config: `fe_save_config` / `fe_load_config` (when no record exists,
  a copy of the global config is returned as the default source — no interference).

### 22.6 Upload and Security Limits

- upload sizes: `_MAX_JSON` / `_MAX_UPLOAD_JSON` / `_MAX_UPLOAD_FILE` multiple limits;
- upload content: text (dataURL-decoded); **since v0.9.9 images return
  `kind="image"` + raw base64** (fed to `/api/vision` for image understanding,
  Chapter 29); other binaries remain unsupported;
- remote-model filtering: `filter_remote_models` (`RETIRED_REMOTE_MODELS` retired
  model list);
- sensitive fields: `json_safe` redacts key-like fields during serialization;
  `tts_service_api_key` / `stt_service_api_key` share the DPAPI-encrypted disk
  path of `api_key` (`_SECRET_KEYS`).

---

## Chapter 23 Performance Design and Benchmarks

> Corresponding code: `kernel/events.py` (EventBus), `builtin/ui/web.py`
> (SSE / HTTP), `nasyncio.py` (the scheduling core), `loops/nasyncio.py`
> (LoopRuntime).

### 23.1 The General-Purpose Event Bus (EventBus): Copy-on-Write + Lock-Free Iteration

```python
# subscribe / unsubscribe: create a new list inside the lock and replace the reference (never mutate in place)
self._all = self._all + [listener]
# emit / intercept: take one reference inside the lock, then iterate directly lock-free
# emit / intercept: take one reference inside the lock, then iterate directly lock-free
listeners = self._snapshot(event_type)   # no copy, only the reference
for fn in listeners: fn(event)
```

- old snapshots held by readers are never modified by concurrent writers — thread
  safety is guaranteed by "immutable + reference replacement";
- high-frequency events (streaming `on_content` pushed per token) skip the
  per-event list-copy overhead;
- measured >1.6M events/sec (**single-machine single-thread publishing scenario**).

**Benchmark baseline (important)**: the 1.6M/sec figure is measured with a
**single publishing thread + a static subscription table (no concurrent subscribe /
remount)**. **Lock-free iteration ≠ lock-free emit** — `emit` still takes one
subscription-table snapshot reference inside the lock (`_snapshot`) each time, then
iterates lock-free. Under single-thread publishing the lock has no contention, hence
the 1.6M measurement; under dynamic hot mounts (high-frequency subscribe / remount),
while a writer holds the lock copying the list, emits are blocked outside the lock
(µs-level — with n<50 subscribers the copy is microsecond-scale, far below ms; it
is only perceptible when hot-mount frequencies reach hundreds/thousands per second).
Streaming `on_content` emits happen inside the worker thread (self-publish,
self-iterate), so they do not constitute multi-thread contention.

**"Briefly seeing the old table" is COW's linearization semantics, not a bug**:
emits that complete before a subscribe use the old table, guaranteeing
"subscribe-then-publish" causal consistency. To eliminate the lock acquisition in
emit entirely, one could make "emit take no lock at all and read the reference
directly" (CPython attribute reads are naturally atomic; writers only replace the
reference inside the lock and never mutate in place; readers seeing the old or new
table are both legal snapshots) — the current implementation conservatively keeps
the read lock; this is an optimizable item (a dynamic hot-mount mixed benchmark
would be added alongside).

### 23.2 SSE Bounded Backpressure

- per-connection independent buffer: bounded deque + condition variable;
- full → drop per policy (default drop the oldest); **slow clients no longer eat
  unbounded memory**;
- batched flush + disconnect reclamation within ≤1s; the `dropped` counter is
  monitorable (`streams_info`).

### 23.3 HTTP Concurrency Tuning

| Parameter | Value | Effect |
|---|---|---|
| `request_queue_size` | 256 | larger listen backlog; high-concurrency connections do not drop SYNs |
| `allow_reuse_address` | True | reuse the port immediately on restart (avoids TIME_WAIT) |
| `daemon_threads` | True | request threads are daemons; process exit does not hang |
| `block_on_close` | False | shutdown does not wait for connections to close; faster stop |

### 23.4 The nasyncio Scheduling Core

- one EventLoop bound to one thread; `run_forever` belongs to whichever thread calls it;
- cross-thread wakeup: thread-safe queue + socketpair self-pipe (no asyncio
  internal mechanisms);
- cancellation semantics: `Task.cancel()` cross-thread safe, done callbacks write
  the self-pipe, `loop.interrupt()` cancels all in-flight tasks;
- the worker pool: `_DaemonPool` (daemon threads, no join at process exit),
  tunable with the `NORPAGENT_MAX_WORKERS` env var (squeeze to 1 for embedded);
- the worker-pool queue is **unbounded**: `put_nowait` never fails; when the pool
  is full tasks pile up indefinitely — no rejection policy, no task time budget
  (boundary and stuck-task fallback matrix in 4.6.4).

### 23.5 How to Verify

The repository ships a full set of specialized verification scripts
(`test/_verify_*.py` / `test/_smoke_*.py`):

| Script | Coverage |
|---|---|
| `_verify_install.py` / `_verify_wheel.py` | installation and packaging |
| `_verify_js*.py` / `_verify_front.py` / `_verify_css_*` | frontend pages and assets |
| `_e2e_webui.py` / `_e2e_shot.py` | WebUI end-to-end and screenshots |
| `_verify_ppt_*.py` / `_pixel_check*.py` | presentations and pixel checks |
| `_final_check.py` / `_verify_coverage.py` | overall regression and coverage audit |

Performance-benchmark methodology suggestion: a fixed input set + a fixed tool set
(the minimal preset), comparing output quality, step count and token consumption
across models / component implementations (7.3 model benchmarks).

---

## Chapter 24 Rescue Mode: Low-Level Loop Control and Human Takeover

> Code: `rescue.py` (pure-stdlib CLI), `rescue_api.py` (human-takeover
> environment), `nasyncio.py` / `loops/nasyncio.py` (loop core and LoopRuntime).
> Section 15.6 covers **usage** (commands, endpoints, parameters); this chapter
> covers **principles** — the relationship between rescue mode and the minimal
> main async loop: how to control the loop directly when the main program is
> unavailable, and how to operate every tool by hand.

### 24.1 A Three-Layer Failure Model: Loop, Engine, Model

Rescue mode picks its entry points by "which layer failed":

| Failed layer | Symptom | Available entry | Dependency |
|---|---|---|---|
| Model down | loop / engine healthy, model calls fail | `norpagent-rescue tools / tool-call / manual / serve` | framework importable (`rescue_api` lazily loaded) |
| Engine down | the loop may still be alive, AgentRuntime cannot start | `norpagent-rescue rollback` / `npa(safemode="on")` | pure stdlib |
| Loop down | scheduling / tasks fully paralyzed | `norpagent-rescue list / show / rollback / mark-good / prune` | pure stdlib |

**Core principle (rescue.py's isolation boundary)**:

1. The snapshot layer (list / show / rollback / mark-good / prune) depends
   **only on the standard library** — it works even when the main program cannot
   be imported at all;
2. The human-takeover layer (tools / tool-call / manual / serve) lazily imports
   the framework (`norpagent.rescue_api`) **inside the command functions** — it is
   meaningful only when the framework can be imported;
3. The `RescueToolEnvironment` assembled by `rescue_api` **does not use the main
   engine's loop** and loads no plugins / hooks / models by default — it is an
   independent minimal tool environment; explicitly loaded plugins
   (`--plugin-dirs`) go through the host security pipeline (24.3.5).

### 24.2 Controlling the Minimal Main Async Loop in Rescue Mode

Controlling the loop in rescue scenarios has three levels: operating the **loop
core** directly (EventLoop), operating through the **LoopRuntime protocol**, and
**bypassing the loop** to drive tools directly.

#### 24.2.1 The Direct Control Surface of the Loop Core (norpagent.nasyncio.EventLoop)

The minimal main async loop is the self-developed `norpagent.nasyncio.EventLoop`
(zero asyncio dependency; thread model: one loop bound to one thread —
`run_forever` owns the loop on whichever thread calls it). In rescue you can
operate it directly from any script:

| API | Calling thread | Purpose |
|---|---|---|
| `run_forever()` | binding thread | start the loop (blocks); repeated calls raise `RuntimeError` |
| `run_until_complete(coro)` | binding thread | run one coroutine then stop; returns its result |
| `stop()` | any | graceful stop: exits after the current round's ready queue drains |
| `abort_main()` | any | **hard stop**: injects `CancelledError` into the main task, interrupting the current await (tool / API stream / user-input wait); the loop exits when the task completes — the stdlib asyncio has no equivalent public entry |
| `call_soon_threadsafe(cb)` | any | cross-thread callback; writes the self-pipe to wake the loop blocked in select |
| `run_coroutine_threadsafe(coro, loop)` | any | submit a coroutine cross-thread; returns a `concurrent.futures.Future` (result / exception / cancellation relayed correctly) |
| `create_task(coro)` / `create_future()` | loop thread | create tasks / result containers |
| `call_later(delay, cb)` | loop thread | timed callback (cancellable); **cross-thread calls are unsafe** (same contract as asyncio) |
| `interrupt()` (LoopRuntime layer) | any | sets the cancel event of every in-flight task (sandbox force-kills child processes / streaming loops exit) |
| `close()` | not running | releases the selector and the self-pipe socketpair |

**Three rescue-critical semantics of the self-developed core**:

1. **Cross-thread cancellation**: `Task.cancel()` auto-detects the calling thread —
   `call_soon` inside the loop thread, `call_soon_threadsafe` + self-pipe wakeup
   outside. Any external thread can cancel any in-flight task directly, no wrapper
   needed;
2. **Self-pipe wakeup**: `call_soon_threadsafe` / cross-thread `set_result` /
   `Event.set` all write the socketpair self-pipe, so a loop blocked in `select()`
   wakes immediately — no "callback queued but the loop is still sleeping" hang;
3. **Select timeout ceiling**: `_run_once` clamps the select wait to 24 hours
   (`_MAX_SELECT_TIMEOUT`, the same value as CPython asyncio). Far-future timers
   (`sleep(1e18)`, distant `call_later`) make `select()` raise `OverflowError` on
   Windows and crash the loop thread — a real defect found by the violent stress
   suite (24.2.6) and fixed: the loop wakes every 24h to re-check the timer heap,
   and `abort_main()` still interrupts at any time.

#### 24.2.2 Protocol-Level Control (NasyncioLoopRuntime)

`loops/nasyncio.py`'s `NasyncioLoopRuntime` is the default `async_loop` slot
implementation; it wraps EventLoop in a thread plus a daemon worker pool. Rescue
scripts can control it through the protocol:

```python
from norpagent.loops.nasyncio import NasyncioLoopRuntime

rt = NasyncioLoopRuntime(config={"max_workers": 2})   # not auto-started
rt.start()                                            # start loop thread + lazy worker pool
rt.submit(lambda: run_a_tool_by_hand(...))            # sync fn -> worker pool, blocks for result
rt.run_async(some_coroutine())                        # coroutine -> loop thread (cross-thread self-pipe wakeup)
rt.interrupt()                                        # cancel all in-flight tasks (Ctrl+C / rescue hard-stop path)
rt.stop()                                             # graceful loop stop
rt.join(timeout)                                      # wait for the loop thread to exit and release resources
```

`submit()`'s cancellation semantics (section 4.6): every task carries its own
cancel event via contextvars; after `interrupt()` sets it, `cancel_requested()`
in the task body returns True — sandboxes force-kill child-process trees, streaming
loops exit early. Calling `run_async` inside the loop thread raises `RuntimeError`
explicitly (a blocking wait would stall the loop; refuse rather than hang).

#### 24.2.3 Scenario A: Model Down, Loop Alive — Drive It Past the Model

When the engine is healthy and only the model is unavailable, rebuild nothing:
submit sync functions or coroutines through the loop held by the engine
(`engine.async_loop`, LoopRuntime protocol), bypassing AgentRuntime's model-call
path:

```python
import norpagent as npa

engine = npa.current()                      # running engine (loop thread + worker pool alive)
loop = engine.async_loop                   # LoopRuntime protocol instance

# way 1: sync function (worker pool; blocks for the result)
out = loop.submit(
    lambda: engine.registry.resolve_tool("file_read")
                .run({"path": "readme.md"}, make_rescue_context(engine))
)

# way 2: coroutine (loop thread; cross-thread wakeup)
out = loop.run_async(read_file_and_log(engine))
```

`submit`'s polling wait (`poll_interval`) keeps the main thread back at a
bytecode boundary every ≤50ms, so Ctrl+C on Windows surfaces immediately as
`KeyboardInterrupt`, and the task's cancel event is set at the same time.

#### 24.2.4 Scenario B: Engine Also Down — Drive a Bare EventLoop by Hand

When the engine / AgentRuntime cannot start at all, bypass the whole assembly
layer and drive a bare loop by hand:

```python
import threading
import norpagent.nasyncio as nio            # self-developed core: zero deps, no plugins, no hooks

loop = nio.EventLoop()
thread = threading.Thread(target=loop.run_forever, daemon=True)
thread.start()

# submit a coroutine cross-thread and wait for the result
cf = nio.run_coroutine_threadsafe(do_manual_work(), loop)
result = cf.result(timeout=30.0)            # exceptions / cancellation relayed as-is

loop.call_soon_threadsafe(loop.stop)        # graceful stop
thread.join(5.0)
loop.close()
```

Combined with `RescueToolEnvironment` (24.3.3) you get "bare-loop scheduling +
manual tool execution": the loop handles orchestration (timers, retries,
concurrency), while tool execution still goes through `call_tool`'s dedicated
threads and cancel events — the two complement each other without blocking.

#### 24.2.5 Scenario C: Loop Stuck — Hard Stop and Rebuild

When the loop thread is stuck in `select()` or a coroutine awaits too long:

1. **Soft first, hard second**: `loop.call_soon_threadsafe(loop.stop)` (graceful)
   → if that fails, `loop.abort_main()` (inject `CancelledError`, interrupt the
   current await);
2. **Task-level cancel**: `rt.interrupt()` sets the cancel events of in-flight
   tasks — sandboxes force-kill child-process trees, streamed reads exit (4.6.2);
3. **Watchdog pattern**: a health-check coroutine periodically does a `loop.time()`
   heartbeat; on heartbeat timeout (loop unresponsive) do `abort_main()` + close +
   rebuild a fresh loop (the bare-loop template in 24.2.4);
4. **Unreclaimable tasks**: tasks stuck in the worker pool (C-extension blocking /
   non-sandboxed subprocess) have no task time budget (4.6.4 states this honestly)
   — the rescue fallback is daemon threads that die with the process, or
   `RescueToolEnvironment.call_tool(timeout=...)`'s hard timeout that abandons the
   worker thread.

#### 24.2.6 Violent Stress Suite for the Loop Core (test/stress_nasyncio_core.py)

A new 35-item violent stress suite covering "testway.txt selections + event-loop
supplements":

| Source | Items |
|---|---|
| testway.txt selections (B/C/D/E mappings) | cold start & readiness (B01), fast start/stop x200 (D10), lifecycle & resource release (B02/B24), 100/500/1000 concurrency (D02), 5000 batch (D08), 200k cross-thread storm (D05), timeout & inner cancel (B17/C02), exception isolation (C04), empty & extreme numeric input (D15/D16), deadlock rejection (C14), 500k-handle resource exhaustion (C17), 2000-deep recursion (D19), duplicate-callback storm (D27), memory baseline (D11), 60s mixed soak (D09), hard-stop latency (B15), watchdog interrupt (E06) |
| supplements (not in the matrix) | 8-thread wakeup race, 1000-timer precision & shuffled registration order, 100k cancel storm, ready queue does not starve timers (fairness), single-thread binding, cross-thread Future completion, cross-thread Event wakeup, Lock/Condition contention, Task.cancel pierce (BaseException), executor result/exception relay, closed-loop rejection, idle loop does not busy-spin (select blocks), 1000 concurrent sleep timers, subprocess-cancel kills child (zombie protection) |

Run: `python test/stress_nasyncio_core.py` (~2 minutes, including the 60s soak).

**Real defect found and fixed by the suite**: `select()` timeout overflow
(Windows `OverflowError: timestamp out of range`) — fixed by the
`_MAX_SELECT_TIMEOUT` clamp (24.2.1 item 3). All other items are confirming
passes of existing behavior (35 items / 110 assertions / 0 failures).

### 24.3 Operating Tools by Hand (Human Takeover)

#### 24.3.1 Four Entry Points and the "Pass In / Pass Out" Semantics

| Entry | Form | Pass in | Pass out |
|---|---|---|---|
| `norpagent-rescue tools` | CLI | — | schemas of all tools (name / description / parameters / required / category / **origin**) |
| `norpagent-rescue tool-call <name> --args '<json>'` | CLI | hand-written JSON args | structured result `{ok, tool, output, error, timed_out, duration_ms}` |
| `norpagent-rescue manual` | interactive | `<tool> <json>` or `{"tool":..., "args":...}` | raw output printed line by line |
| `norpagent-rescue serve` | HTTP API | POST body `{"args":{...},"timeout":N}` | unified JSON response |

**Tool scope**: all 20 built-in tools are exposed by default; since v0.9.7,
custom tools can be added via `--tools` (comma-separated registered names or
module addresses) and external plugin tools via `--plugin-dirs`
(comma-separated directories) — see 24.3.5. A manual call goes through
**exactly the same execution path** as a model-issued call: `tool.run(args, ctx)`
with the same `RunContext` (registry / sandbox / session / scheduler /
context_store / project_manager — all present), writing the same state — files
land in the same workspace, `context_add` writes to the same context store,
`task_submit` enters the same task queue. "Pass in" = a human generates `args`
in place of the model; "pass out" = the result is returned in the model's
structured format, so a recovered model can continue from the same state.

#### 24.3.2 The Loop-Interaction Model of Manual Calls

`RescueToolEnvironment.call_tool()` does **not depend on the main loop** and does
not occupy the loop thread:

```
caller (CLI / HTTP thread / main thread)
  └─ call_tool(name, args, timeout)
       ├─ resolve tool + assemble RunContext (with a per-call cancel-event ContextVar)
       ├─ spawn a dedicated worker thread (contextvars.copy_context isolates the cancel signal)
       ├─ worker: tool.run(args, ctx) -> box the result
       ├─ caller join(timeout): on timeout -> set cancel event + abandon as a daemon orphan
       └─ return the structured result (ok / output / error / timed_out / duration_ms)
```

Key points:

- **Parallel-safe**: every call has its own thread; multiple manual calls can run
  concurrently; components are internally locked;
- **Cancel signal**: `cancel_requested()` is visible in the worker thread —
  sandboxes force-kill child-process trees, streaming loops exit early; after a
  timeout the caller returns immediately without waiting for the task to finish;
- **Relation to 24.2**: if you want manual calls to be orchestrated by a loop
  (timing / concurrency / retry), just put `call_tool` inside `loop.submit(...)`
  (worker pool) or a bare loop's `run_coroutine_threadsafe` — `call_tool` is a
  pure sync function and any loop can schedule it.

#### 24.3.3 Programmatic Embedding: Rescue Environment + Custom Loop Control

```python
from norpagent.rescue_api import RescueToolEnvironment, RescueToolAPI
import norpagent.nasyncio as nio

env = RescueToolEnvironment(workspace_root=".", context_db="./rescue.db")

# 1) direct manual call (sync; dedicated thread + hard timeout)
r = env.call_tool("exec_cmd", {"command": "git status"}, timeout=30)
print(r["output"])

# 2) mount the HTTP takeover service (127.0.0.1, optional Bearer token)
api = RescueToolAPI(env, port=8799, token="my-secret")
api.start()

# 3) orchestrate manual calls with a bare loop (e.g. poll the task queue)
loop = nio.EventLoop()
threading.Thread(target=loop.run_forever, daemon=True).start()
nio.run_coroutine_threadsafe(poll_and_act(env, loop), loop).result(timeout=60)
loop.call_soon_threadsafe(loop.stop)
```

Applications can also auto-start a `RescueToolAPI` after a failed model health
check (mount it inside the existing process); on-call staff take over through
the operator page, and the recovered model continues from the same state.

#### 24.3.4 Timeouts and Safety Boundaries (Quick Reference)

- **Double-layer timeout**: tool's own timeout (exec_cmd max 300s, run_python's
  `ptc_timeout`) + environment-level hard timeout (default 300s; `--timeout` /
  HTTP body adjustable);
- **Abandoned threads**: after a timeout the worker becomes a daemon orphan
  (the same pattern as the model-call timeout); `_orphan_threads` is pruned per
  call;
- **Zero plugins / zero hooks by default**: the rescue environment subscribes to
  no hooks; the operator is the final approver; explicitly loaded plugins
  (`--plugin-dirs`) go through the host security pipeline and never alter the
  manual-call execution path;
- **Path safety still applies**: `file_*` absolute-path / `..` traversal
  rejection and `run_python`'s AST pre-check still apply; HTTP binds 127.0.0.1 by
  default, token optional.

#### 24.3.5 Manual Operation of Custom Tools (v0.9.7)

Three sources, all manually callable through the four entry points:

| Source | How to attach | origin tag | Notes |
|---|---|---|---|
| registry custom tool | `extra_tools={name: tool}` (programmatic) | `custom` | registered directly into the rescue registry |
| tools slot | `tools=["name", "pkg.mod:attr"]` / CLI `--tools` | `custom` | same semantics as the `npa(tools=[...])` slot; address resolution failures raise a clear error |
| external plugin | `plugin_dirs=[dir]` / CLI `--plugin-dirs` | `plugin` | loaded through the security pipeline (signature → audit → import restriction → register) |

```bash
# CLI: load a custom tool by module address and operate it by hand
norpagent-rescue tools --tools myapp.tools:create
norpagent-rescue tool-call my_tool --args '{"x": 1}' --tools myapp.tools:create

# CLI: load external plugin tools
norpagent-rescue serve --plugin-dirs ./my_plugins --port 8799

# programmatic: combine all three sources
env = RescueToolEnvironment(
    extra_tools={"my_tool": MyTool()},
    tools=["builtin_or_extra_name", "pkg.mod:attr"],
    plugin_dirs=["./my_plugins"],
)
```

Every `inventory()` item carries `origin` (builtin / custom / plugin); the CLI
inventory and the operator page tag the source; `/api/health` reports a
`custom_tools` count. The plugin loader is released with `env.close()` (the
isolation host subprocess is shut down too).

### 24.4 Failure Decision Tree

```
Model calls failing?
├─ yes -> engine / loop still alive?
│         ├─ alive -> norpagent-rescue tools / tool-call / manual / serve
│         │           (or programmatically: engine.async_loop.submit(lambda manual tool))
│         └─ dead -> rollback --last-good (pure stdlib)
│                   -> still won't start -> npa(safemode="on") minimal kernel
└─ no  -> but tasks stuck / unresponsive?
          ├─ rt.interrupt() / loop.abort_main() hard stop (24.2.5)
          ├─ loop thread also dead -> rebuild a bare EventLoop + RescueToolEnvironment (24.2.4)
          └─ everything down -> norpagent-rescue list (pure-stdlib last resort)
```

### 24.5 Division of Labor with 15.6

| Chapter | Viewpoint | Content |
|---|---|---|
| 15.6 | user | commands / endpoints / parameters / response format / environment defaults (usage quick reference) |
| 24 | principles & internals | three-layer failure model, direct loop control (EventLoop / LoopRuntime), the loop-interaction model of manual calls, bare-loop rebuild, stress suite and the defect-fix record |

They complement each other: start with 15.6 to get going; come back to 24.2 for
low-level control when the loop itself is in trouble.

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
invalidates the module cache and .pyc files** (3.7), so "edit the implementation
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
three forms are hot-reloadable:

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

Another hot-reload detail: **address hot reload invalidates the module cache
first**. `remount` runs `_invalidate_address_module` on string addresses —
deletes the .pyc corresponding to `__cached__` and pops the `sys.modules`
entry, so the next resolution re-imports from disk (3.7). Therefore "edit
`myapp/weather_tool.py` → `npa.remount(tools={"weather":
"myapp.weather_tool:create"})`" hot-updates the code. Note: **instance /
registered-name forms do no module invalidation** (there is no address to
invalidate); use the address form after editing code.

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

# hot reload: swap model / config / code (the address form invalidates the module cache)
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
.pyc for string addresses, pops `sys.modules`, then re-imports (3.7). Edit
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
`_invalidate_address_module` on string addresses — it deletes the .pyc at
`module.__cached__` and pops the `sys.modules` entry, so the next resolution
re-imports from disk. Hence "edit `myapp/weather_tool.py` →
`npa.remount(tools={"weather": "myapp.weather_tool:create"})`" hot-updates the
code; **instance / registered-name forms have no address to invalidate — use
the address form after editing code**.

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

A string address passed to `remount` first runs two-step cache invalidation
(`_invalidate_address_module`):

1. delete the module's bytecode cache (`module.__cached__`'s .pyc) — otherwise, if a
   same-size file is rewritten within the same second, importlib may judge the "cache
   is still fresh" and re-importing would fetch the old code;
2. pop the `sys.modules` entry — the next resolution re-imports from disk.

Thus the hot-reload closed loop "edit code → remount → new code takes effect" holds.
Custom slots (registered via `register_slot`, 3.8) support remount too, resolving per
the spec at registration time; after `replace=True` hot-replaces a spec, remount
resolves per the new spec.

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
| `wait` never returns | wrong event name / timeout is 0 (means indefinite) | confirm with `subscriber_count` first; give an explicit timeout |
| old logic still active after hot mount | the slot does not rebuild the AgentRuntime (`remount_rebuild_agent=False`) | check the slot spec (Appendix A); assembly-type custom slots must set it True |
| the veto does not take effect | you used `emit` instead of mutating dispatch | mutating semantics require `intercept` (9.3) |

---

## Chapter 29 Multimodal: Vision and Sound

> New in v0.9.9. Code: `builtin/ui/multimodal.py` (stdlib-only backend) +
> `builtin/ui/web.py` (`/api/vision` `/api/tts` `/api/stt` `/api/beep`) +
> `front.html` (image attach / voice input / read-aloud / notification tone).
>
> Multimodal = vision (image understanding) + sound (TTS read-aloud, STT
> speech input, notification tone) + **native multimodal input (image / audio /
> video passthrough, v2.x)**. **Design rule: all capability lives on the
> backend; the browser only captures and plays** — nothing depends on
> browser-native speech APIs (SpeechSynthesis / SpeechRecognition). The
> backend engines work offline (Windows SAPI / macOS say / Linux espeak-ng),
> and OpenAI-compatible cloud services can be configured instead.
>
> **New in v2.x (R-021 / R-022)**: multimodal input supports **native
> passthrough** — each modality (image / audio / video) follows its own route
> (`direct` = passed to the model; `service` = converted to text by an external
> service), **direct by default**; adds the video chain, the vision-service API
> key, and the audio service (not limited to speech). See 29.2.5.

### 29.1 Overview: three channels

| Channel | Direction | Backend | Frontend duty |
|---|---|---|---|
| Vision: image understanding | image → description → conversation | `/api/vision` → external vision service | pick / paste / drag images, preview, merge the description into the message |
| Sound: TTS read-aloud | text → audio | `/api/tts` → OS-native synthesizer / OpenAI-compatible service | play the returned wav (🔊 button / auto-speak) |
| Sound: STT input | recording → text | `/api/stt` → Windows local recognizer / OpenAI-compatible service | MediaRecorder capture → WAV(16k) encode → upload → fill the input box |
| Sound: notification tone | — | `/api/beep` → stdlib-generated short WAV | play (new message / task done) |

Layering:

```
front.html (capture / play / interaction)
   │  HTTP
   ▼
web.py  ui.vision_describe / ui.tts_speak / ui.stt_transcribe / ui.beep_notify
   │
   ▼
multimodal.py (stdlib only)
   ├─ describe_image()   external vision service (JSON protocol, compatible with standalone vision.py)
   ├─ text_to_speech()   service first → OS-native (Windows SAPI / macOS say / Linux espeak-ng)
   ├─ speech_to_text()   service first → Windows SAPI local recognizer
   └─ beep_wav()         stdlib RIFF/WAV sine tone
```

### 29.2 Vision: image understanding

#### 29.2.1 Architecture and flow

A text-only model cannot read images directly. v0.9.9 image understanding
follows a "**describe then talk**" route:

```
user uploads an image ──▶ /api/upload (kind="image", base64 kept)
     │
     ▼
on send: /api/vision  {images:[{name,type,data}], prompt}
     │
     ▼
external vision service (vision_service_url) returns a text description
     │
     ▼
frontend composes: 【用户上传了图片】\n图片1：<description>… \n\n <user text>
     │
     ▼
POST /chat to the model — the model "sees" the image
```

- `/api/upload` returns `kind="image"` + raw base64 for images (mime
  `image/*` or a known image extension); text files behave as before;
- three frontend entries: the 🖼️ button (file picker, multiple), Ctrl+V
  paste, drag & drop; thumbnail preview before sending, removable one by one
  (max 6 images);
- on failure (disabled / not configured / service error) a toast explains the
  reason and **the images are kept** so they can be resent after fixing the
  configuration.

#### 29.2.2 REST endpoint: `POST /api/vision`

Request:

```json
{
  "images": [
    {"name": "shot.png", "type": "image/png", "data": "<base64 without data: prefix>"}
  ],
  "prompt": "请详细描述这张图片的内容，包括画面主体、文字与关键细节。"
}
```

Response:

```json
{
  "ok": true,
  "descriptions": [
    {"name": "shot.png", "description": "画面主体是一台笔记本……"}
  ]
}
```

- `ok=false` carries an `error` reason (disabled / not configured / service error);
- one failed image does not break the batch: it gets an `error` field, the rest return normally;
- prerequisite: enable "Vision API" in settings and fill `vision_service_url`.

#### 29.2.3 External vision service protocol (for self-hosted services)

The backend POSTs `application/json` to `vision_service_url`:

```json
{
  "image_base64": "<base64>",
  "ext": "png",
  "mime": "image/png",
  "prompt": "请详细描述这张图片的内容……"
}
```

Accepted responses (any of the three shapes):

```json
{"description": "……"}
{"ok": true, "description": "……"}
{"text": "……"}
```

> Compatible with the standalone `vision.py` / `vision_adapters.py`
> `describe_with_provider` adapters: wrap one of the built-in providers
> (openai_compatible / anthropic / llama_cpp) behind a thin HTTP service.

#### 29.2.4 Frontend interaction

- paper-clip button: file picker (image / audio / video / text, multiple);
- paste: Ctrl+V of an image adds it to the pending attachment bar;
- drag & drop: dropping files anywhere adds them;
- attachment bar: thumbnail / type icon + file name + remove; cleared after a
  successful send;
- sending: attachments ride the `POST /chat` `attachments` field and are routed
  by the backend (29.2.5); plain-text files are merged into the prompt;
- user bubbles echo image thumbnails (sent here) / type chips (restored history).

#### 29.2.5 Native passthrough and per-modality routing (v2.x, R-021 / R-022)

Attachments are passed **natively** by default — the payload itself becomes a
native content part of the model message (no forced text transcription first);
each modality can be switched to an external service:

| Modality | direct (default) form | service route |
|---|---|---|
| image | `{"type":"image_url","image_url":{"url":"data:image/png;base64,…"}}` | `vision_service_url` (29.2.3 protocol, Bearer key supported) |
| audio | `{"type":"input_audio","input_audio":{"data":"…","format":"wav"}}` | `audio_service_url` (understanding / transcription; **not limited to speech** — music / environment audio accepted) |
| video | `{"type":"video_url","video_url":{"url":"data:video/mp4;base64,…"}}` (compatible extension; actual video support depends on the endpoint) | `video_service_url` |

- Routing switches (Settings → Multimodal, per modality): `mm_image_route` /
  `mm_audio_route` / `mm_video_route`, values `direct` / `service`;
- text-like attachments (txt / md / json / code) are always merged into the
  prompt (routing not involved);
- media service protocol: POST JSON `{"kind": "audio"|"video",
  "data_base64": …, "ext": …, "mime": …, "prompt": …}`; responses accept
  `description` / `text` / `transcript` / `content` / `result`, optional
  `Authorization: Bearer <key>` (`media_describe`, `builtin/ui/multimodal.py`);
- attachments persist with the message (SQLite attachment column; memory stores
  objects directly) and are re-sent with history on replay (standard multimodal
  chat behavior);
- size caps: image 10MB / audio 20MB / video 32MB; service keys are
  DPAPI-encrypted.

### 29.3 Sound: TTS read-aloud

#### 29.3.1 Architecture

```
frontend clicks 🔊 / auto-speak
   │  POST /api/tts  {text, voice, rate}
   ▼
multimodal.text_to_speech()
   ├─ tts_service_url set → OpenAI-compatible /audio/speech (optional Bearer key)
   └─ otherwise OS-native synthesizer (zero config, offline):
        Windows → PowerShell System.Speech (SAPI) → WAV
        macOS   → say --data-format=LEI16@22050 → WAV
        Linux   → espeak-ng / espeak -w → WAV
   ▼
returns {ok, audio_base64, mime:"audio/wav"}
   ▼
frontend plays with new Audio(data:audio/wav;base64,…)
```

- **Windows SAPI**: `Add-Type System.Speech` via PowerShell
  `-EncodedCommand` (UTF-16LE base64, no quoting issues) synthesizes WAV;
  `SelectVoice` selects the voice (e.g. "Microsoft Huihui Desktop" Chinese /
  "Microsoft David Desktop" English), `Rate` (-10..10) maps from 0.5–2.0×;
- **macOS**: `say -v <voice> -r <wpm> -o out.wav --data-format=LEI16@22050`;
- **Linux**: `espeak-ng -w out.wav -s <wpm> -v <voice>` (clear error when not installed);
- **OpenAI-compatible service** (`tts_service_url`): POST JSON
  `{"model":"tts-1","input":text,"voice":voice,"response_format":"wav","speed":rate}`,
  optional `Authorization: Bearer <tts_service_api_key>`.

#### 29.3.2 Endpoint: `POST /api/tts`

```json
request  {"text": "你好", "voice": "", "rate": 1.0}
response {"ok": true, "audio_base64": "<wav base64>", "mime": "audio/wav"}
```

- empty `voice` = system default; `rate` 0.5–2.0 (defaults to config `tts_rate`);
- `tts_enabled=false` or empty text → `{ok:false, error}`.

#### 29.3.3 Frontend

- every assistant reply has a 🔊 read-aloud button (click to speak, click again to stop; becomes ⏸ while playing);
- with "auto-read replies" enabled, the full reply is read aloud when the task finishes;
- a rate slider (0.5–2.0×) and a voice-name text field (e.g. "Microsoft Huihui Desktop").

### 29.4 Sound: STT speech input

#### 29.4.1 Architecture

```
frontend clicks 🎤 → getUserMedia capture → MediaRecorder(webm)
   │
   ▼ frontend decode: AudioContext.decodeAudioData → 16kHz mono PCM → encode WAV
POST /api/stt  {audio:"<wav base64>", mime:"audio/wav"}
   │
   ▼
multimodal.speech_to_text()
   ├─ stt_service_url set → OpenAI-compatible /audio/transcriptions (multipart)
   └─ otherwise Windows local recognizer (SAPI DictationGrammar; en-US built in;
        zh-CN needs the Chinese speech language pack; clear error otherwise)
   ▼
returns {ok, text}
   ▼
frontend fills the recognized text into the input box (editable before sending)
```

- the frontend always converts the recording to **16 kHz mono WAV** — the
  common format accepted by both local engines and cloud services (webm would
  not be decodable by the local engine);
- **Windows local recognition**: PowerShell System.Speech.Recognition +
  `DictationGrammar` + `SetInputToWaveFile`; `stt_language` (default en-US)
  selects the engine language; timeout follows `api_request_timeout`;
- **OpenAI-compatible service** (`stt_service_url`): multipart
  `file=audio.wav` + `model=whisper-1` + `language=<stt_language>`,
  optional Bearer key;
- non-Windows without a configured service →
  `{ok:false, error:"当前平台没有本地语音识别引擎，请在设置中配置 STT 服务地址"}`.

#### 29.4.2 Endpoint: `POST /api/stt`

```json
request  {"audio": "<wav base64>", "mime": "audio/wav"}
response {"ok": true, "text": "recognized text"}
```

- audio limit 10MB; empty recognition → `{ok:false, error:"没有识别到语音内容"}`.

### 29.5 Notification tone: `POST /api/beep`

- the backend synthesizes an 880 Hz sine short tone (RIFF/WAV with fade in/out
  to avoid clicks) using the standard library; the frontend caches it after
  the first fetch;
- trigger: task completion with a reply, when "new-message tone" is enabled;
- returns `{ok, audio_base64, mime:"audio/wav"}`.

### 29.6 Configuration reference

| Key | Default | Description |
|---|---|---|
| `vision_enabled` | false | enable the vision API (image understanding) |
| `vision_service_url` | "" | external vision service URL (protocol in 29.2.3) |
| `vision_service_api_key` | "" | vision service key (DPAPI-encrypted; R-022) |
| `tts_enabled` | true | enable TTS read-aloud |
| `tts_service_url` | "" | optional OpenAI-compatible `/audio/speech` endpoint (empty = OS native) |
| `tts_service_api_key` | "" | TTS service key (DPAPI-encrypted on disk) |
| `tts_voice` | "" | voice name (e.g. "Microsoft Huihui Desktop" / "alloy") |
| `tts_rate` | 1.0 | speech rate multiplier 0.5–2.0 |
| `stt_service_url` | "" | optional OpenAI-compatible `/audio/transcriptions` endpoint (empty = Windows local) |
| `stt_service_api_key` | "" | STT service key (DPAPI-encrypted on disk) |
| `stt_language` | "en-US" | local recognition language (zh-CN needs a Windows Chinese language pack) |
| `sound_notify_enabled` | true | new-message notification tone |
| `auto_speak_enabled` | false | auto-read assistant replies |
| `mm_image_route` | "direct" | image route: `direct` (model) / `service` (external, 29.2.5) |
| `mm_audio_route` | "direct" | audio route (not limited to speech) |
| `mm_video_route` | "direct" | video route |
| `audio_service_url` | "" | audio understanding / transcription service URL (29.2.5 protocol) |
| `audio_service_api_key` | "" | audio service key (DPAPI-encrypted) |
| `video_service_url` | "" | video service URL |
| `video_service_api_key` | "" | video service key (DPAPI-encrypted) |

> Sound preferences (auto-speak / tone / voice / rate) are saved into the
> backend config via the settings panel's "🔊 Sound" section; service URLs and
> keys are stored there too (keys share the DPAPI encryption path of `api_key`,
> see 22.4 and `_SECRET_KEYS`).

### 29.7 Privacy and security

- **images** are sent base64-encoded to the configured vision service; local
  services (e.g. llama.cpp) are fully offline; the page notes that images are
  sent to the vision provider;
- **native passthrough (v2.x)**: under the `direct` route the attachment itself
  is sent to the configured model endpoint (and re-sent with history); under
  `service` it is sent to the configured service. Choose local models / services
  when egress matters, or route that modality more conservatively;
- **recordings** are processed locally by default (Windows SAPI local
  recognition, no data leaves the machine); they are uploaded only when an STT
  service is configured;
- **TTS** native path is fully offline; the cloud path sends only text;
- service keys are DPAPI-encrypted on Windows (0600 file elsewhere);
  `/api/config` masks secret fields;
- multimodal calls reuse `api_request_timeout` as the hard timeout.

### 29.8 Developer access: calling multimodal directly

```python
from norpagent.builtin.ui import multimodal as mm

# vision: image → description (external service)
desc = mm.describe_image(
    image_base64="iVBOR...", ext="png", mime="image/png",
    service_url="http://127.0.0.1:9000/vision", prompt="describe this image",
)

# TTS: text → wav (OS-native synthesizer when no service is configured)
audio, mime = mm.text_to_speech(
    "Hello", voice="Microsoft David Desktop", rate=1.0,
)
assert mime == "audio/wav" and audio[:4] == b"RIFF"

# STT: wav → text (Windows local recognition or the configured service)
text = mm.speech_to_text(audio, "audio/wav", language="en-US")

# notification tone
beep = mm.beep_wav()
```

All errors surface as `MultimodalError` (human-readable messages); handle them
with the `ok=false` semantics.

### 29.9 FAQ

| Symptom | Cause | Fix |
|---|---|---|
| sending an image reports "视觉 API 未启用" | not enabled | Settings → Vision API → enable + fill the service URL |
| image reports "未配置视觉服务地址" | enabled but no URL | fill `vision_service_url` (self-host protocol in 29.2.3) |
| read-aloud fails: Windows TTS error | SAPI unavailable / bad voice name | use an installed voice (PowerShell: `Add-Type -AssemblyName System.Speech; (New-Object System.Speech.Synthesis.SpeechSynthesizer).GetInstalledVoices()`) |
| Linux read-aloud: espeak not found | not installed | `apt install espeak-ng`, or configure a TTS service URL |
| speech input: no speech content | noise / language mismatch | speak closer to the mic; en-US works out of the box, zh-CN needs the Windows Chinese language pack or an STT service |
| speech input: no local engine on this platform | macOS/Linux without a service | Settings → Sound → STT service URL (OpenAI compatible) |
| tone does not play | `sound_notify_enabled=false` | Settings → Sound → new-message tone |

---

## Chapter 30 Central Nervous Bus: Multi-Instance and the Neural Tree

> Module: `src/nervous_bus/` (shipped inside the PyPI package as the top-level package `nervous_bus` since v1.0.2; before 1.0.1 it lived at the repository root as `nervous_bus/`) | Protocol: CNB/1.0 | Standalone design doc: `NERVOUS_BUS.md`
>
> **Core rule**: the cortex (the highest norpagent instance) controls the operation permissions of any atom at any level through the Central Nervous Bus; lower levels may only report upward and can never control upper levels; the neural tree is a tree-shaped topology chain; lower levels obey higher-level commands unconditionally and are forbidden to rewrite higher levels — they may only report back.

### 30.1 Overview and Core Rules

The Central Nervous Bus (CNB) adds **multi-instance** capability to norpagent: any number of norpagent processes form a "neural tree" whose root is the **cortex** (the highest-level instance); every other instance is a **node** (an atomic unit: norpbot / norpilot / norpmemory ... or any custom instance). Each atom can not only start and configure itself independently, but can also join the CNB tree as a node (`node_kind` marks the atom type), centrally scheduled and authorized by the cortex.

```
                    ┌──────────────────────────┐
                    │  Cortex (level 0)           │  highest level, tree root
                    │  最高级 norpagent 实例      │  full topology + control over every level
                    └────────────┬─────────────┘
                                 │  downlink cmd.* (high -> low, unconditional obedience)
                                 │  uplink report.* (low -> high, read-only)
                    ┌────────────┴─────────────┐
                    │   中枢神经总线 CNB          │  protocol + topology + permissions + transport
                    └────────────┬─────────────┘
              ┌──────────────────┼──────────────────┐
       ┌──────┴──────┐    ┌──────┴──────┐    ┌──────┴──────┐
       │ level 3 原子  │    │ level 3 原子  │    │ level 3 原子  │
       │ norpbot-01   │    │ norpmemory-01│    │   ...        │
       └──────┬──────┘    └─────────────┘    └─────────────┘
       ┌──────┴──────┐
       │ level 4 原子  │   ← tree topology chain: every node has exactly one parent
       │ norpilot-01  │
       └─────────────┘
```

Requirements map one-to-one to implementation mechanisms:

| Requirement | Mechanism | Code location |
|---|---|---|
| Tree topology chain | one unique parent per node; cycle check + level check at registration; deep registration forwards level by level up to the cortex | `topology.py` `Topology.register` / `_forward_uplink` |
| Layered instances, layer = level | the smaller the `level` number, the higher the rank; `0` = cortex; children must exceed their parent's level; a registered level can never be altered | `protocol.py` LEVEL_*; `topology.py` anti-rewrite |
| Cortex controls any atom's permissions at any level | `cmd.perm.grant/revoke/set`; targets support exact `node_id` / `node_kind` wildcard / `*` full wildcard | `cortex.py` `perm_grant/perm_revoke/perm_set`; `permissions.py` |
| Lower levels only report, never control upper levels | uplink allows only `report.*`; the transport layer forcibly strips/rejects any control field | `protocol.py` `check_uplink_payload`; `node.py` `_handle_uplink` |
| Lower levels obey higher-level commands unconditionally | downlink `cmd.*` is accepted only from ancestors; legal commands execute unconditionally with an audit record | `node.py` `_handle_downlink` + ancestor-chain check |
| Rewriting higher levels is forbidden | the topology layer forbids level/kind/parent rewrites; uplink has no control channel | `topology.py` anti-rewrite; `protocol.py` control-field blacklist |
| Report back only | heartbeat/event/audit/request all travel through the `report.*` uplink; approval is decided by higher levels | `node.py` `report_*` |

### 30.2 Tree Topology and Layered Levels

A **node** is one atomic unit on the neural tree: at startup each instance declares its `node_id`, `kind` (atom type) and `level`, and points at its single `parent` (the parent node's bus URL). The root is the cortex, with `parent=None`. The whole-tree shape comes from an **explicit definition** (§30.19: no preset shape; every required parameter — per-level LEVEL / count / lower-level parent / port — is validated, and a missing one is reported explicitly).

Level constants (the smaller the number, the higher the rank):

| Constant | Value | Meaning |
|---|---|---|
| `LEVEL_CORTEX` | 0 | the cortex: highest level, tree root |
| `LEVEL_DIRECTOR` | 1 | level 1: directorate / group level |
| `LEVEL_AGENT` | 2 | level 2: agent level |
| `LEVEL_ATOM` | 3 | level 3: atom level (norpbot / norpilot / norpmemory ...) |
| `LEVEL_MAX` | 63 | level ceiling (blocks malicious ultra-deep registration) |

The `Topology` layer provides thread-safe tree management:

| Method | Description |
|---|---|
| `register(node_id, level, kind, parent_id, meta)` | register a node: cycle check (walk up the parent chain) + level check (child level must exceed parent's); a registered node's level/kind/parent are **immutable** (raises `ValueError`) |
| `unregister(node_id)` | deregister a node (**cascades to all descendants**, keeping the tree intact) |
| `is_ancestor(a, n)` / `is_descendant(d, n)` | ancestor/descendant checks (self is never an ancestor: same-level nodes cannot control each other) |
| `ancestor_chain(n)` | ancestor chain (parent -> root, includes parent, excludes self) |
| `subtree(n)` | descendant node-id list (DFS, includes self) |
| `render_ascii()` / `render_tree()` | readable tree rendering (for the cortex console / CLI) |
| `heartbeat(node_id)` / `sweep_dead(timeout=30)` | heartbeat refresh / sweep nodes silent past the timeout (marked dead, not unregistered) |

### 30.3 The CNB/1.0 Message Protocol

Every message uses one envelope (`protocol.make_envelope`):

```json
{
  "proto": "cnb/1.0",
  "kind": "uplink | downlink | ack",
  "msg_id": "uuid",
  "from": {"node_id": "...", "level": 3, "kind": "bot"},
  "to": "parent | cortex | node_id",
  "ts": 1234567890.123,
  "type": "report.heartbeat | cmd.ping | ...",
  "payload": {...}
}
```

**Uplink (low -> high, read-only)**, only `report.*` allowed:

| Type | Description |
|---|---|
| `report.register` | registration request (forwarded level by level to the cortex, with a `via` anti-loop marker) |
| `report.heartbeat` | heartbeat/status report (every 5 s by default; carries the descendant liveness overview) |
| `report.event` | event report (task done/failed/exception/milestone) |
| `report.audit` | audit report (permission denials / command executions) |
| `report.request` | request (lower levels may only ask; approval is decided by higher levels) |
| `report.deregister` | deregistration (node going offline) |

**Downlink (high -> low, control)**, accepted only from ancestor nodes:

| Type | Description |
|---|---|
| `cmd.hello` | registration confirmation (parent approves, carries the ancestor chain) |
| `cmd.ping` | liveness probe (must answer immediately) |
| `cmd.exec` | generic execution command (action + args; the neural permission table is checked first) |
| `cmd.stop` | stop tasks (immediately terminate locally running tasks) |
| `cmd.reload` | reload configuration |
| `cmd.perm.set` | set permissions (overwrite the target's permission set) |
| `cmd.perm.grant` / `cmd.perm.revoke` | grant / revoke a permission |
| `cmd.topology.sync` | topology sync (the cortex broadcasts its topology view) |

**Permission atoms** (aligned with `permission_cascade.Permission` semantics):

`file_read` `file_write` `file_delete` `file_list` `process_exec` `process_shell` `network_out` `network_in` `system_info` `plugin_call`

### 30.4 Module Layout

**v1.0.7 kernel integration**: the neural implementation lives in
`src/norpagent/cnb/` (a norpagent kernel submodule — ready with
`import norpagent`; version merged into norpagent, no separate version); the old
standalone top-level package `src/nervous_bus/` remains as a **compatibility
shim** (re-export + submodule injection + thin cli/demo files) so 1.0.6 and
earlier scripts keep working.

```
src/norpagent/cnb/           # implementation location since v1.0.7
??? __init__.py      # package entry and exports (protocol/topology/permissions/node/cortex/engine)
??? protocol.py      # protocol layer: envelope, directions, levels, permission atoms, uplink control-field blacklist
??? topology.py      # tree topology chain: register/unregister/cascade, ancestor checks, cycle and anti-rewrite validation
??? permissions.py   # neural permission table: node_id/node_kind/* three-level matching, last write wins
??? bus.py           # transport layer: zero-dependency HTTP (one bus endpoint per node) + client
??? node.py          # CNB node: register/heartbeat/event report/command execution/action registry/audit
??? cortex.py        # the cortex: root node + any-level control API + REPL console
??? engine.py        # engine binding (new in v1.0.7): CnbAdapter kernel action surface + env auto-mount
??? cli.py           # command line: cortex/node/topo/ping/exec/stop/reload/perm/reports/audit/sync
??? demo.py          # quick demo (simulates a neural tree in-process)
src/nervous_bus/             # compatibility shim since v1.0.7 (re-exports norpagent.cnb)
??? __init__.py      # symbol re-export + sys.modules submodule injection + version follows norpagent
??? cli.py / demo.py # physical thin files (python -m entries run through the file path)
??? test_cnb.py / test_deep_tree.py / test_e2e.py   # self-tests (ship with the shim; commands unchanged)
```

The transport layer (`bus.py`) is zero-dependency (stdlib only): each node runs a `ThreadingHTTPServer` as its bus access point and the client delivers via `urllib`. Bus endpoints:

| Endpoint | Method | Description |
|---|---|---|
| `/cnb/msg` | POST | deliver a CNB message envelope (JSON) |
| `/cnb/ctrl` | POST | cortex control endpoint (cortex only; CLI / REPL drive the cortex through it) |
| `/cnb/health` | GET | health check (returns node identity and level) |
| `/cnb/reports` | GET | reports received by this node |

### 30.5 Quick Start

**Start the cortex** (GUI-less background process; bypasses the single-instance lock; instances run in parallel). Since v1.0.7 the cortex process **assembles a full norpagent engine by default** (the cortex is the top-level norpagent instance; `--bare` returns to the plain nervous shell):

```bash
# repository source (root main.py)
python main.py --norp-cortex --port 17800 --repl

# all three entries are equivalent; with a PyPI install (v1.0.2+) both
# `python -m` and the `norpagent` subcommand are available.
# v1.0.7 kernel integration: commands run through norpagent.cnb.cli
# (nervous_bus is a compatibility shim; the old path keeps working)
python -m norpagent.cnb.cli cortex --port 17800 --repl
norpagent cortex --port 17800 --repl
```

> Note: `python main.py --norp-cortex ...` is the **repository-source** entry (a PyPI install has no repository main.py — use the `norpagent` / `python -m` forms there). Ordinary GUI / embedded / np() instances join the neural tree without any subcommand — just set the `NORP_CNB_*` env vars and start normally (see 30.8; per-instance **opt-in**: no env vars, no mount).

**Mount nodes** (tree topology chain, level by level; shown with the `norpagent node` subcommand — `python main.py --norp-node ...` is equivalent). Since v1.0.7 node processes also **assemble a full kernel engine by default** — every atom is a real task-capable agent instance (`--bare` returns to the plain probe shell):

```bash
# level-1 atom: cortex -> norpbot-01
norpagent node --id norpbot-01 --kind bot \
    --parent http://127.0.0.1:17800 --port 17801 --level 3
#    (repository-source equivalent: python main.py --norp-node --id norpbot-01 ...)

# level-2 atom: cortex -> norpbot-01 -> norpilot-01 (chained)
norpagent node --id norpilot-01 --kind pilot \
    --parent http://127.0.0.1:17801 --port 17802 --level 4

# another branch: cortex -> norpmemory-01
norpagent node --id norpmemory-01 --kind memory \
    --parent http://127.0.0.1:17800 --port 17803 --level 3
```

**Cortex command-line control** (`--root` points at the cortex bus URL; `norpagent topo ...` is equivalent to `python -m norpagent.cnb.cli topo ...` — shown with `python -m` below):

```bash
# topology
python -m norpagent.cnb.cli topo --root http://127.0.0.1:17800

# commands (any atom at any level)
python -m norpagent.cnb.cli ping   --root ... --node norpilot-01
python -m norpagent.cnb.cli exec   --root ... --node norpbot-01 --action run_task
python -m norpagent.cnb.cli stop   --root ... --node norpbot-01
python -m norpagent.cnb.cli reload --root ... --node norpbot-01

# permission control (node_id / node_kind / * targets)
python -m norpagent.cnb.cli perm --root ... --grant  --target-type node_id   --target norpbot-01 --perm file_write
python -m norpagent.cnb.cli perm --root ... --revoke --target-type node_kind --target bot       --perm process_shell
python -m norpagent.cnb.cli perm --root ... --set    --target-type node_kind --target bot --allows '{"file_delete": false}'

# reports, audit and topology broadcast
python -m norpagent.cnb.cli reports --root ... --n 50
python -m norpagent.cnb.cli audit   --root ... --n 50
python -m norpagent.cnb.cli sync    --root ...          # cortex broadcasts the topology
```

**Cortex REPL console** (type commands after starting with `--repl`):

```
cortex> topo                            # view the topology tree
cortex> ping norpbot-01                 # probe liveness
cortex> exec norpbot-01 run_task        # issue an execution command
cortex> stop norpbot-01                 # stop tasks
cortex> reload norpbot-01               # reload configuration
cortex> grant node_kind bot file_write  # grant a permission
cortex> revoke node_id norpbot-01 process_shell   # revoke a permission
cortex> set node_kind bot '{"process_shell": false}'  # overwrite permissions
cortex> sync                            # broadcast the topology
cortex> reports / audit                 # view reports / audit
```

### 30.6 The Cortex Control API (Cortex)

`Cortex` inherits `NervousNode` and is the neural-tree root (level 0, no parent). Start and control it programmatically:

```python
from norpagent.cnb import Cortex

cortex = Cortex(node_id="cortex", host="127.0.0.1", port=17800)
cortex.start()

# probe / execute / stop / reload (any atom at any level)
print(cortex.ping("norpbot-01"))
print(cortex.exec_cmd("norpbot-01", "run_task", {"n": 3}, perm="process_exec"))
print(cortex.stop_node("norpbot-01"))
print(cortex.reload_node("norpbot-01"))

# permission control: exact node_id / node_kind wildcard / * full
cortex.perm_grant("node_kind", "bot", "file_write")
cortex.perm_revoke("node_id", "norpbot-01", "process_shell")
cortex.perm_set("node_kind", "bot", {"file_delete": False, "network_out": False})

# topology broadcast and view
cortex.sync_topology()
print(cortex.topology_view()["tree"])

# interactive console (blocking)
cortex.repl()
```

Method signatures at a glance:

| Method | Signature | Description |
|---|---|---|
| `ping` | `ping(node_id) -> dict` | liveness probe |
| `exec_cmd` | `exec_cmd(node_id, action, args=None, perm="process_exec", path="") -> dict` | issue an execution command (neural permission table checked first) |
| `stop_node` / `reload_node` | `(node_id) -> dict` | stop tasks / reload configuration |
| `perm_grant` | `perm_grant(target_type, target, perm, scope=None) -> dict` | grant a permission |
| `perm_revoke` | `perm_revoke(target_type, target, perm) -> dict` | revoke a permission |
| `perm_set` | `perm_set(target_type, target, allows) -> dict` | overwrite permissions |
| `sync_topology` | `sync_topology() -> dict` | broadcast the topology to all descendants |
| `topology_view` | `topology_view() -> dict` | topology view (size / tree / nodes) |

The cortex also exposes the HTTP control endpoint `/cnb/ctrl` (for the CLI / external consoles; loopback-only by default):

```python
from norpagent.cnb import BusClient
cli = BusClient(timeout=15.0)
r = cli.post_ctrl("http://127.0.0.1:17800", {"op": "topo"})
r = cli.post_ctrl("http://127.0.0.1:17800", {"op": "ping", "node": "norpbot-01"})
r = cli.post_ctrl("http://127.0.0.1:17800", {"op": "grant", "target_type": "node_kind",
                                             "target": "bot", "perm": "file_write"})
```

Supported `/cnb/ctrl` operations: `topo` `nodeinfo` `ping` `exec` `stop` `reload` `grant` `revoke` `set` `sync` `reports` `audit`.

### 30.7 The Node API (NervousNode)

Every norpagent instance can embed a `NervousNode` and join the neural tree as an atom:

```python
from norpagent.cnb import NervousNode

node = NervousNode(
    node_id="norpbot-01", kind="bot", level=3,
    parent_url="http://127.0.0.1:17800", port=17801,
    meta={"desc": "terminal-operation atom"}, heartbeat_interval=5.0,
)

# register callbacks (where cortex commands land)
node.on("exec", lambda p: {"echo": p.get("action"), "node": node.node_id})
node.on("stop", lambda: {"stopped": True})
node.on("reload", lambda: {"reloaded": True})
node.on("perm_changed", lambda summary: print("permissions changed by cortex:", summary))
node.on("registered", lambda parent_id: print("registration confirmed, parent:", parent_id))

node.start()   # start the bus + register + heartbeat (5 s default)
# ...
node.stop()    # deregister + stop heartbeat + close the bus
```

Callback events:

| `exec` | `(payload: dict) -> dict` | cortex `cmd.exec`; **since v1.0.7 only the fallback when the action registry misses**; the neural permission table is checked first |
|---|---|---|
| `exec` | `(payload: dict) -> dict` | cortex `cmd.exec`; the return value becomes the receipt detail; the neural permission table is checked first |
| `stop` | `() -> dict` | cortex `cmd.stop` (stop local tasks) |
| `reload` | `() -> dict` | cortex `cmd.reload` (reload configuration) |

**Kernel action registry (v1.0.7 kernel integration)**: cortex `cmd.exec` actions
route to registered handlers first; only misses fall back to the `exec` callback;
when neither exists the node rejects the action directly (`ok=False` + top-level
`error`; contract upgrade over 1.0.6 — see 30.16). The engine binding layer
(`norpagent.cnb.engine.CnbAdapter`) registers the NorpEngine public API as a
**14-action kernel surface**; bare nodes may register placeholder actions:

```python
node.register_action("my_action", lambda payload: {"echo": payload.get("args", {})})
node.has_action("my_action")      # True
node.list_actions()               # registered action names (visible to cortex inspect)
node.unregister_action("my_action")
```

**Heartbeat status provider (v1.0.7)**: after registering a `(status, extra_dict)`
provider the heartbeat carries kernel state automatically (the engine binding
injects `engine_state` / `active_tasks` / `version` / `actions` — visible in
cortex `reports`):

```python
node.set_heartbeat_provider(lambda: ("busy", {"task_count": 2, "note": "..."}))
node.set_heartbeat_provider(None)   # back to the basic heartbeat
```
| `perm_changed` | `(summary: dict) -> None` | cortex `cmd.perm.*` changed this node's permission table |
| `registered` | `(parent_id: str) -> None` | registration confirmed by the parent |

Uplink report methods (sent to the parent only, converging level by level at the cortex; a middle layer records locally and then forwards, so deep nodes' heartbeats / events / requests are all visible at the cortex):

```python
node.report_heartbeat()                              # heartbeat and status (running by default)
node.report_heartbeat(status="busy", task_count=3)   # custom status fields (busy/idle/metrics; visible at the cortex)
node.report_event("task_done", {"task": "t1"})
node.report_audit("perm_denied", "process_shell")
node.report_request("network_out", "need access to an external API")   # lower levels may only ask
```

**Deep-tree self-healing**: when a heartbeat is rejected by the parent (typical: the parent restarted under the same id, or the cortex rebuilt its view after rescue/sweep), the node re-registers automatically; parent-chain rescue is driven from above with `cmd.reroot` (see 30.14).

### 30.8 A GUI Instance as a Node (env-var auto-mount, implemented since v1.0.2)

A normally launched GUI / embedded / np() norpagent instance can also join the neural tree as a node: **set the `NORP_CNB_*` env vars and start it normally** (no subcommand, no change to how you start it). Mounting runs on a background thread and never delays startup; any mounting failure **degrades to a plain single instance** (a warning is printed, the main program is untouched); the engine shutdown path unmounts automatically. **2026-09-12 feedback round (final error semantics)**: config errors (missing port / missing node id / a tree definition with missing required parameters) also never block startup — the host starts normally, the error is printed explicitly and **the tree is not loaded**; query it via `engine.cnb_status` (`config-error`) and `engine.cnb_error` (see §30.19.6).

> Contract (prevents double mounting): auto-mount is the kernel's default path; `NORP_CNB_MANAGED=1` makes the **kernel skip mounting** (an upper layer builds its own node in managed mode). The contract reads **environment variables only — config.json is NOT consulted** (the early manual's "same keys in config.json" claim was never implemented and has been removed).

| Env var | Default | Description |
|---|---|---|
| `NORP_CNB_NODE` | (empty = disabled) | node id; **setting it enables auto-mount** |
| `NORP_CNB_KIND` | `agent` | atom type (bot / pilot / memory / ...) |
| `NORP_CNB_LEVEL` | `3` | level (must exceed the parent's; 1–63) |
| `NORP_CNB_PARENT` | `http://127.0.0.1:17800` | parent bus URL |
| `NORP_CNB_PORT` | `17801` | this node's bus port (1–65535) |
| `NORP_CNB_HEARTBEAT` | `5.0` | heartbeat interval in seconds (0.5–3600) |
| `NORP_CNB_DESC` | (empty) | optional node meta description |
| `NORP_CNB_MANAGED` | unset | `1` = kernel mounting skipped (managed mode; the upper layer builds its own node) |
| `NORP_CNB_TREE` | (empty) | neural-tree definition (JSON / PY file path or JSON text); NODE/PORT are then carried by the definition (see §30.19) |

```bash
set NORP_CNB_NODE=norpbot-gui
set NORP_CNB_KIND=bot
set NORP_CNB_LEVEL=3
set NORP_CNB_PARENT=http://127.0.0.1:17800
set NORP_CNB_PORT=17801
python main.py            # repository-source entry; with a PyPI install use norpagent / python -m norpagent
```

**Implementation location**: `NorpEngine.start()` → `runtime/engine.py` `_setup_cnb()` → `runtime/cnb.py` (a forwarding layer since v1.0.7) → **`norpagent.cnb.engine.setup_cnb()`** (the implementation). The mount thread calls `NervousNode.start()` + registration retries (every 5 s, budget ≈ 30 s; an unreachable parent degrades to a plain instance); try-import degradation if CNB is unavailable (since v1.0.7 CNB ships inside norpagent, so this path only triggers in stripped environments). Status: `engine.cnb` (adapter; `status`: `mounting` / `mounted` / `failed` / `stopped`) and `engine.cnb_status` (also `not-mounted` / `managed-skip` / `config-error` — a config error is reported explicitly while the tree is not loaded and the host keeps running); config / mount error details are read via `engine.cnb_error`.

**The cortex downlink surface (kernel action registry since v1.0.7)**:

| Downlink | Landing | Semantics |
|---|---|---|
| `cmd.exec` | **kernel action registry** (14 kernel actions registered by the engine binding — see the action table in 30.16; a miss falls back to the legacy `exec` callback, and with neither the node rejects: `ok=False` + top-level `error`) | task: `run_task` / `status` / `stop_task`; state: `engine_state` / `inspect`; snapshot: `snapshot` / `rollback` / `undo` / `redo` / `list_snapshots` / `mark_good`; ops: `remount` / `reload_plugins` / `stop_engine`. Each action calls the NorpEngine public API directly; the receipt returns up the tree |
| `cmd.stop` | `engine.stop_all_tasks()` | stops all in-flight session tasks of this instance (loop-level interrupt + handle cancellation); **the instance stays RUNNING** |
| `cmd.reload` | re-reads `NORP_CNB_*` + plugin hot reload | hot-updates the hot-swappable runtime knobs (heartbeat / meta description; kind / level / parent / port are fixed after registration — nervous-tree identity protection); with external plugins declared, re-runs `engine.remount(plugins=...)` (module cache invalidated, edited files picked up); otherwise reports honestly |
| `cmd.perm.*` | `perm_changed` callback | the cortex permission command first lands in this node's neural permission table (enforced before every `cmd.exec`), then the callback records the summary and audits it. Syncing cortex permissions into the in-process tool-call chain is left to a future `permission_cascade` integration (see design boundaries in 30.12) |


Every exec / stop / reload / perm event is written to the node-local audit log (`node.get_audit()`); the cortex can query uplink records with the `reports` / `audit` commands.

### 30.9 The Neural Permission Table (NeuralPermissionTable)

Every node holds a local neural permission table: cortex `cmd.perm.*` commands land here as rules, and local actions call `check()` before executing.

```python
from norpagent.cnb import NeuralPermissionTable

tbl = NeuralPermissionTable("norpbot-01", "bot")

# cortex-command landing (normally driven by downlink cmd.perm.*, not called directly)
tbl.apply("node_kind", "bot", "process_shell", allow=False, source="cortex")
tbl.set_all("node_kind", "bot", {"file_delete": False, "network_out": False})

# decision (before a local action)
tbl.check("process_shell")   # False (revoked by the cortex)
tbl.check("file_read")       # True (allowed by default)
```

Decision rules (B4 revision — pure time order):

1. **Pure time order**: among every rule that matches this node and the same permission atom (`node_id` exact / `node_kind` type / `*` full all participate), the **most recently written one wins** (last write wins, **across target granularities too**). The cortex issues commands in time order, and the latest command is the latest management intent: special-case a `node_id` first and then tighten `node_kind` — the tightening applies; tighten first and then special-case — the grant applies. No revoke can be shadowed by an older grant;
2. **Allow by default**: with no rule matched, `check()` returns `True` (the cortex tightens explicitly; `cmd.perm.set` can overwrite a target's whole set for whitelist tightening);
3. **Scope**: a rule may carry `scope={"whitelist": [...], "blacklist": [...]}` matched by path prefix (a whitelist miss or a blacklist hit denies).

### 30.10 Security Model (bus iron rules, enforced in code)

1. **Uplink control-field gate**: `protocol.check_uplink_payload` strips/rejects every control field at the transport layer (prefix blacklist: `cmd.` `perm.` `exec` `config.set` `topology.mutate` `control.`) — even a maliciously crafted lower-level node cannot control upper levels through the uplink.
2. **Downlink ancestor check**: the receiver verifies the sender is in its ancestor chain (told level by level by the parent at registration confirmation + a double check against the local topology parent chain); commands from non-ancestors are rejected and audited.
3. **Topology anti-rewrite**: a registered node's level, kind and parent are immutable (prevents identity forgery, re-parenting and cycles).
4. **Level constraint**: a child level must exceed its parent's; level ceiling 63; registration cycle detection walks the parent chain.
5. **Same level cannot control each other**: ancestor checks exclude self; peer-to-peer commands are rejected.
6. **Loopback by default**: binds `127.0.0.1`; cross-machine deployment needs an explicit host and a trusted network (TLS/signing recommended).
7. **Cortex cannot be controlled from below**: the cortex (level 0) has no parent, so no downlink can pass the ancestor check — lower levels can never rewrite higher levels.

### 30.11 Tests and Verification

| Suite | Coverage | Result |
|---|---|---|
| `test_cnb.py` (60 items) | tree topology chain, level-by-level registration forwarding, layered levels, uplink read-only, downlink obedience, permission control (node_id/node_kind/*), privilege-escalation blocking (low->high / same-level / control fields / level forgery / parent forgery / kind spoofing / non-ancestor reporting), deregistration with **live-child rescue promotion**, topology broadcast, control endpoint | 52/52 pass |
| `test_e2e.py` (13 items) | real multi-process (main.py entry: 1 cortex + 3 nodes), full CLI chain, execution denied after tightening, privilege-escalation blocking, heartbeat convergence | 13/13 pass |
| `test/test_cnb_automount.py` (12 checks, new 2026-09) | ordinary engine `NORP_CNB_*` auto-mount (incl. the `NORP_CNB_MANAGED=1` skip switch); exec action whitelist (run_task/status/stop_task; missing-prompt / unknown-action rejections; task_done uplink); cmd.stop stops tasks and keeps the instance alive; cmd.reload env re-read + plugin hot-reload face; cmd.exec denied after perm tightening and restored after the grant; shutdown unmount; loop.submit_async deep cancellation | 12/12 pass (verified 2026-09-05) |
| `test_deep_tree.py` (36 checks, new 2026-09-05) | 4-level chain (cortex->tech->rnd->dev): deep parent/child relations (B1), de-duplicated ancestor chains (B6), deep heartbeat/event/request convergence (B2), rescue after a middle layer exits normally (B3), rescue after a middle layer crashes (B3 crash / B5), time-ordered permission tightening and grants (B4), custom heartbeat status passthrough (B7), automatic broadcast on register (B8), auto re-registration after a rejected heartbeat (self-healing), dead-node grace-then-drop | 30/30 pass |
| `test/test_cnb_kernel_actions.py` (32 checks, new v1.0.7) | B 11 multi-process + A 21 in-process kernel action surface (see the matrix in 30.16) | 32/32 green |
| `test/test_cnb_tree_suite.py` (56 checks, new 2026-09-12 feedback round) | explicit neural-tree definitions: three sources (dict / JSON / PY), item-by-item required-parameter errors, port-style parents and `level:N` rotation, in-process assembly with diff reshape, file-watch reshape, auto-reconcile, multi-process process tree, np integration and error semantics, CLI | 56/56 green |

```bash
python -m nervous_bus.test_cnb
python -m nervous_bus.test_e2e
python -m nervous_bus.test_deep_tree     # deep-tree regression (4-level chain)
python -m nervous_bus.demo               # in-process neural-tree demo
python test/test_cnb_kernel_actions.py   # kernel action surface (needs PYTHONPATH=src)
python test/test_cnb_tree_suite.py       # explicit neural-tree definition acceptance (needs PYTHONPATH=src)
```

### 30.12 Integration Points with the norpagent Core (actual locations, v1.0.2+)

| File | Change | Description |
|---|---|---|
| `norpagent/cnb/` (kernel-integrated since v1.0.7; the old standalone `nervous_bus` package moved in whole) | `protocol` / `topology` / `permissions` / `bus` / `node` / `cortex` / `cli` / `demo` + a new `engine` binding layer; version merged into norpagent (no separate version) | `import norpagent` makes CNB ready; top-level `norpagent.cnb` exports `NervousNode` / `Cortex` / `CnbAdapter` / `setup_cnb` / `KERNEL_ACTIONS` |
| `nervous_bus/` (compatibility shim) | re-export + sys.modules submodule injection + physical thin `cli.py`/`demo.py` files | `from nervous_bus import ...` / `python -m nervous_bus.cli ...` from 1.0.6 and earlier keep working unchanged |
| `norpagent/cli.py` | CNB subcommand forwarding branch (`_CNB_SUBCOMMANDS`: cortex/node/topo/ping/exec/stop/reload/perm/reports/audit/sync) to **`norpagent.cnb.cli`**; legacy `--norp-cortex` / `--norp-node` forwarded; `--help` shows the branch | PyPI: `norpagent cortex ...` / `python -m norpagent --norp-cortex ...` both work |
| `main.py` (repository-source entry) | src-path bootstrap at the top + CNB branch (same forwarding path as cli.py, to `norpagent.cnb.cli`) | repository source: `python main.py --norp-cortex/--norp-node ...` |
| `norpagent/runtime/engine.py` | `NorpEngine.start()` mounts the auto-mount hook (`_setup_cnb()`); `request_stop()` unmounts (`_teardown_cnb()`); task-level cancellation API (`submit_async` / `cancel_task` / `stop_all_tasks` / `active_tasks` / `forget_task`, see 30.13) | GUI / embedded / np() instances; since v1.0.7 engine.py is untouched (the hook points at the `runtime/cnb.py` forwarding layer) |
| `norpagent/runtime/cnb.py` (forwarding layer) | re-exports `norpagent.cnb.engine` (`CnbAdapter` / `setup_cnb` / `KERNEL_ACTIONS` / legacy `EXEC_ACTIONS`) | `NorpEngine._setup_cnb()` keeps importing `setup_cnb` from this path (zero engine changes) |
| `norpagent/cnb/engine.py` (new since v1.0.7) | `CnbAdapter`: env reading → NervousNode assembly → **14 kernel actions registered** (KERNEL_ACTIONS) → background mount (retries / degrade / unmount); heartbeat provider (engine_state / active_tasks / version / actions) | full implementation of 30.8 / 30.16; includes the `NORP_CNB_MANAGED` skip switch |
| `norpagent/loops/nasyncio.py` | optional extension `submit_async` (`NasyncTaskHandle`, per-task cancellable handle) | the loop-layer foundation for task cancellation (the engine probes it with hasattr; degrades when missing) |
| `nervous_bus/test_e2e.py` | ROOT resolution climbs to the repository root that contains `main.py` | `python -m nervous_bus.test_e2e` works under the v1.0.2+ src layout (since v1.0.7 through the shim onto `norpagent.cnb`) |

Design boundaries (recorded honestly): this release is designed for **same-machine multi-instance** (loopback transport, no encryption); cross-machine deployment needs TLS and node signing. ① The auto-mount contract reads the `NORP_CNB_*` env vars only (config.json is not consulted); ② the `cmd.exec` action surface is a whitelist (`run_task` / `status` / `stop_task`) — unknown actions and missing prompts are rejected and audited; ③ cortex permission commands take effect immediately on the **CNB command surface** (the node permission table is checked before every `cmd.exec`); pushing cortex permissions into the **in-process tool-call chain** is a future `permission_cascade.PermissionCascade` integration (the `perm_changed` callback is already reserved); ④ kind / level / parent / port are immutable after registration (identity anti-forgery); `reload` only hot-updates runtime knobs and external plugins.

### 30.13 Task-Level Cancellation (EngineTaskHandle, v1.0.2+)

`NorpEngine` provides non-blocking, cancellable task APIs (the CNB `exec run_task` / `stop_task` actions are built on them):

```python
import norpagent as np
from norpagent.loops.cancel import cancel_requested

engine = np(mode="minimal", ui="headless")          # engine reaches RUNNING
handle = engine.submit_async("write a short note", session_id="s1")  # returns immediately
print(handle.task_id)                                # task id (32 hex chars)

# inside the task body you can poll the cancel signal at any time:
#   if cancel_requested(): return  # exit ASAP (sandbox force-kills children / streams interrupt)

engine.cancel_task(handle.task_id)   # cancel exactly this task (deep: the body sees the cancel event)
engine.stop_all_tasks()              # cancel every in-flight task (the instance stays RUNNING; cmd.stop landing point)
engine.active_tasks()                # in-flight snapshot [task_id / text / session_id / degraded / cancelled]
result = handle.result()             # wait for completion and fetch the result (timeout/exception semantics match submit())
engine.forget_task(handle.task_id)   # drop a finished task from the registry (bookkeeping)
```

Handle surface (`EngineTaskHandle`): `cancel()` / `cancelled()` / `done()` / `wait(timeout)` / `result(timeout)`; `handle.degraded=True` means the current loop runtime does not implement the `submit_async` extension (or this task carries a task-level `async_loop` override), so cancellation degrades to a request flag (engine-level `stop()` / `stop_all_tasks()` still cancel everything through loop.interrupt).

**Deep semantics**: the default nasyncio loop's `submit_async` gives every task its own cancel event (injected into the task body via contextvars, readable with `cancel_requested()`); cancelling one task does not affect other in-flight tasks; these tasks remain members of the loop's in-flight set, so Ctrl+C / engine-stop `interrupt()` cancels them too. The engine `request_stop()` shutdown path first unmounts the CNB node and cancels the remaining task handles.

### 30.14 Deep-Tree Fix: Shallow-Self-Consistent, Deep-Broken Remediation (2026-09-05)

**Background**: the official suites (test_cnb 51 + test_e2e 13 + automount 12) only covered ≤2-level flat scenarios (atoms mounted straight on the cortex) and never ≥3-level chained forwarding. An audit of a cortex → tech → rnd → dev four-level chain found 9 defects on the registration / uplink / link-loss paths, 3 of them high severity. This section records the fixes one by one (each is covered by the deep-tree regression suite, see 30.11).

#### B1 (high) deep-registration collapse — `via` overwritten at every hop

- Symptom: the cortex view showed `dev.parent = tech` (it should be `rnd`) — while forwarding registrations, each hop ran `fwd["via"] = self.node_id`, replacing the "original direct parent" with the last forwarder, so every deep node was re-parented wrongly.
- Fix (`node.py _forward_uplink`): `fwd.setdefault("via", self.node_id)` — `via` records the forwarder closest to the sender and is then kept untouched; the loop guard (`via == self` means already forwarded) is unaffected.

#### B2 (high) middle layers swallowed uplinks — the cortex went blind to deep nodes

- Symptom: after three heartbeat periods the cortex only saw tech's direct heartbeats; dev's events/heartbeats/requests never reached it (middle layers only called `_record_report`, never forwarded).
- Fix (`node.py _handle_uplink`): the heartbeat / event / audit / request branch now **forwards upward after recording locally** (`_forward_uplink`), so the cortex's reports converge from every depth. Addition: when an upper layer rejects a forwarded uplink (typical: this node was removed from the cortex topology), **the verdict is echoed back to the sender** — the child's heartbeat loop detects `not my descendant` and re-registers automatically (heartbeat self-healing, below).

#### B3 (high) a middle layer exiting cascade-killed a live subtree (rescue)

- Symptom: `tech.stop()` made the cortex cascade-deregister the whole live subtree (rnd/dev became orphans); a restart on the same port never re-attached.
- Fix (`node.py _rescue_children` + `cortex.py` sweep thread):
  1. **Clean-exit path**: on `report.deregister(X)`, rescue first — promote each direct child of X **under this node** (`topology.set_parent`, maintaining children lists on both sides) and send **`cmd.reroot`** (new downlink: carries the new parent id / bus URL / grandparent chain) telling the child to re-parent; the child updates `parent_url` / `parent_node_id` / `_ancestors` and **re-registers immediately** (heartbeats and reports then go straight to the new parent). Only then is X deregistered (its children already moved; only X itself is removed). Every level of the chain runs the same logic, so the cortex converges to the authoritative view.
  2. **Crash path** (no deregister): the cortex gained a **lost-node sweep thread** (`Cortex(sweep_interval / dead_timeout / drop_grace)`, `_sweep_loop` finally calls the previously dead `sweep_dead`): no heartbeat beyond `dead_timeout` → marked dead; dead with children → rescue-promote; an entire branch past `drop_grace` → cascade-deregister; a dead leaf past `drop_grace` → deregister (the grace window protects live leaves whose report path broke because their parent died — once the parent is rescued and forwarding resumes, their heartbeats continue).
  3. **Heartbeat self-healing**: any node whose heartbeat is rejected by its parent (parent restarted / cortex view rebuilt / misjudged by the sweep) re-registers automatically. test_deep_tree D07/D11/D12 verify: a crashed middle layer's live subtree is rescued and keeps reporting, a forgotten node re-attaches, and truly dead nodes are swept away.
- Attached fixes: `topology.set_parent` used to append to the new parent's children **without removing the node from the old parent's children** (the old parent's cascade DFS then wrongly deleted already re-parented children) — it now maintains both sides; `Topology.register` raises an explicit `ValueError` when the parent is missing (previously a KeyError while maintaining children).

#### B4 type-level revoke shadowed — permission decisions now pure time order

- Symptom: after `grant node_id` then `revoke node_kind`, `check()` still returned True — the old "exact-match priority" layering let an old node_id grant shadow a type-level tightening.
- Fix (`permissions.py check`): **pure time order** — among the rules matching this node for the same permission atom, the most recently written one wins (last write wins across node_id / node_kind / * granularities). The cortex's latest command is the latest management intent: special-case first, tighten after → tightened; tighten first, special-case after → granted. Every existing shallow-tree test stays compatible (same-target time-order semantics unchanged).

#### B5 lost-node detection was unwired

- `sweep_dead` / `mark_dead` had no call sites (dead code). They are now wired into the cortex sweep thread (see the B3 crash path); the REPL `sweep` command and the cortex control endpoint `op=sweep` trigger a manual pass.

#### B6 hello ancestor chains duplicated

- Symptom: `dev._ancestors = ['rnd','rnd','tech','tech','cortex','cortex']` — hello carried a chain that already contained the parent itself (`_ancestor_chain()`), and the child prepended its direct parent again.
- Fix (`node.py _accept_register`): hello's `ancestors` now carries only the **grandparent side** (`self._ancestors`, parent excluded); the child prepends its direct parent and gets a single clean chain `[parent, grandparent, ...]`.

#### B7 heartbeat payload was fixed

- Fix (`node.py report_heartbeat`): new `status` parameter (running / busy / idle / degraded ...) and `**extra` custom fields (control-key prefixes are filtered out); the cortex REPL reports show the status. Busy/idle reporting serves the P1D scheduling surface.

#### B8 topology broadcasts were manual only

- Symptom: middle-layer subtree caches could only be refreshed by a manual `sync` after register/deregister.
- Fix (`cortex.py _maybe_auto_sync`): after register / deregister / rescue the cortex **auto-broadcasts debounced** (0.5 s Timer merges bursts), pushing the full topology via `sync_topology()`; on plain nodes the hook is a no-op.

#### B9 duplicate implementation cleanup

- Redundant lines in `NervousNode.__init__` (duplicate `base_url` assignment etc.) removed; `Cortex` reuses the node implementation through inheritance (registration / uplink / rescue / permissions live in the node layer; the cortex adds root semantics only: the control API, the sweep thread, auto-broadcast, REPL).

**New downlink `cmd.reroot`** (registered in protocol.DOWNLINK_TYPES): reserved for parent-chain rescue — sent by an ancestor (typically the cortex) with payload `{parent_id, parent_url, ancestors}`; the receiving node updates its local parent pointer and ancestor chain, then re-registers immediately. It is still subject to the downlink ancestor check (non-ancestors are rejected).

**Test defense**: new `src/nervous_bus/test_deep_tree.py` (30 checks on a 4-level chain): registration + crash + sweep + permission timing + heartbeat status + auto-broadcast are fully covered; test_cnb T48 (formerly "cascade deregistration") now asserts the "live child promoted by rescue" semantics.

### 30.15 Convergence Closure and Permission-Plane Audit (v1.0.6, 2026-09-05)

**Background**: after the B1–B9 remediation, a live multi-level demo tree exposed two closing gaps — receivers did not converge even though the sweep path broadcast (Gap A), and permission-plane audit stayed on the node locally instead of reaching the cortex (Gap B).

#### Gap A: middle-layer cache does not converge after sweep removal — `cmd.topology.sync` becomes an authoritative snapshot mirror

- Evidence (running tree: cortex → tech → rnd → dev + atoms): after probe-x was force-killed, the cortex's `_sweep_once` deregistered it and fired the debounced broadcast (cortex audit: `lost leaf past grace, deregister: probe-x` → `topology broadcast: 11 ok`); still, middle-layer rnd's heartbeat `descendants` kept listing probe-x for 150s+ (observed through tech's report records). The root cause is not the broadcast trigger (the B8 hook already covers the sweep path) but the **receiver semantics**: the `cmd.topology.sync` handler only `register`s snapshot nodes (add-only) — nodes removed from the cortex view never disappear from a middle layer's local topology; parent-pointer mismatches on existing nodes raised `ValueError` and were swallowed, so local views could drift from the cortex for a long time (the same live tree showed rnd listing the four atoms under itself while the cortex view had them under dev).
- Fix (`node.py _exec_downlink`, `cmd.topology.sync` = **authoritative snapshot mirror**):
  1. **Prune**: cascade-deregister every local node absent from the snapshot (self excluded) — the convergence path after cortex sweep / deregistration;
  2. **Parent-pointer convergence**: when a snapshot node exists locally with a different parent, align via `topology.set_parent` to the cortex's authoritative view (level / kind tamper checks are kept as a defensive rejection);
  3. **Self-healing fallback**: transient gaps caused by pruning (in-flight registration uplinks, a slightly stale snapshot) recover through "heartbeat rejected → auto re-register"; live nodes are never lost.
- Regression: `test_deep_tree` gains D13a–f — probe-x hangs directly under middle-layer rnd, is force-killed, the cortex sweep deregisters it, rnd's local topology prunes it, heartbeat `descendants` converge, and rnd's subtree view matches the cortex's (same id set). Suite 30→**36 all green**.

#### Gap B: permission-plane audit uplink (kernel-side, converging on the cortex)

- Evidence: a `cmd.exec` permission denial only wrote a line in the target node's in-memory audit ring; `cmd.perm.grant/revoke/set` effects only fired the local `perm_changed` callback (runtime/cnb.py records it with a local `node.audit`); the cortex kept only its own textual audit of issued permission operations — **there was no permission-plane audit view on the cortex**, so same-permission audit reads saw nothing.
- Fix (three places):
  1. **Node uplinks** (`node.py`): a `cmd.exec` rejected by the permission table uplinks `report.audit(event="perm.denied", detail={action, perm, path})`; a `cmd.perm.*` that takes effect uplinks `report.audit(event="perm.changed", detail={op, target_type, target, perm/allows, source})` (`_perm_uplink_audit`) and also records a local effect-audit line. Both climb hop by hop (middle layers record and forward, per the B2 semantics) and land in the cortex's reports ring.
  2. **Cortex records** (`cortex.py`): `_note_perm_op` writes the cortex's own grant/revoke/set into a structured permission-operation ring (500); `perm_audit(n)` merges cortex operations (`perm.op.*`) with uplinked node events (`perm.denied` / `perm.changed`) in reverse time order.
  3. **Read surface**: cortex REPL gains the `perm_audit [n]` command; the control endpoint gains `op=perm_audit` (`/cnb/ctrl`) — consumed directly by same-permission audit readers.
- Regression: `test_cnb` gains T-A0~T-A6 — revoke + denial + grant sequences verify the cortex sees the uplinked `perm.denied` / `perm.changed`, a **deep node's denial is forwarded through a middle layer to the cortex**, and the `op=perm_audit` view contains both cortex operations and uplinked node events. Suite 52→**60 all green**.

**Version**: norpagent **1.0.6**; the CNB protocol stays CNB/1.0 (semantic additions only: `cmd.topology.sync` snapshot-mirror convergence, and the `report.audit` permission-plane event convention). Full suites re-run: test_cnb 60 + test_deep_tree 36 + test_e2e 13 + automount 12 all green.

### 30.16 CNB Kernel Integration (v1.0.7): Internalized as a Kernel Submodule

**Positioning**: v1.0.7 turns CNB from a standalone package beside norpagent into
a **kernel submodule plus a native engine capability surface** — the cortex can
drive **kernel-level actions** (snapshot / rollback / remount / ops) on any atom
at any level, atom heartbeats carry **deep kernel state**, and every neural atom
started by `norpagent cortex/node` is by default a **full kernel instance**.

#### 30.16.1 Package Layout: `nervous_bus` → `norpagent.cnb`

| Item | 1.0.6 and earlier | v1.0.7 |
|---|---|---|
| Neural implementation | `src/nervous_bus/` (standalone top-level package, own version 1.0.0) | `src/norpagent/cnb/` (kernel submodule; version merged into norpagent) |
| Engine binding | `norpagent/runtime/cnb.py` (external adapter) | `norpagent/cnb/engine.py` (binding layer owned by the CNB module) |
| Import | `from nervous_bus import NervousNode` | `import norpagent` includes CNB; `from norpagent.cnb import NervousNode, Cortex, CnbAdapter, setup_cnb, KERNEL_ACTIONS` |
| CLI | `python -m nervous_bus.cli ...` | `python -m norpagent.cnb.cli ...` (equivalent); `nervous_bus` stays as a shim |

The `nervous_bus/` shim: `__init__.py` re-exports every symbol (version follows
norpagent) + injects submodules into `sys.modules` (`protocol` / `topology` /
`permissions` / `bus` / `node` / `cortex` / `engine`) + physical thin
`cli.py`/`demo.py` files (so `python -m nervous_bus.cli` / `.demo` run through
the file path). **Scripts, commands and tests from 1.0.6 and earlier keep
working unchanged.**

#### 30.16.2 exec Routing Upgrade (Action Registry First)

`NervousNode._exec_downlink` routes cortex `cmd.exec` in three tiers:

1. **kernel action registry** (handlers registered with `register_action`;
   the v1.0.7 main path) → receipt `source="kernel"`;
2. **legacy callback hook** (`on("exec")`; fallback for unregistered actions) → `source="callback"`;
3. neither → the node rejects directly: `ok=False` + top-level
   `error="unknown action: ... (registered: [...])"`.

> **Contract upgrade**: 1.0.6 and earlier returned unknown actions through the
> callback as `ok=True` + `detail.error`; v1.0.7 rejects them node-side with
> `ok=False` (explicit, programmable). Callers relying on the old shape must
> adapt (the automount acceptance test follows the new contract).

API: `register_action(action, handler)` / `unregister_action(action)` /
`has_action(action)` / `list_actions()` / `set_heartbeat_provider(provider)`.

#### 30.16.3 The Kernel Action Surface (KERNEL_ACTIONS, 14 actions → 15 since v2.0.0)

The engine binding (`CnbAdapter.bind_actions`) registers the **NorpEngine public
API** as node actions; the cortex runs
`exec --node X --action <action> --args '<json>'` straight into the target
atom's kernel:

| Surface | Action | args notes | Direct API |
|---|---|---|---|
| Task | `run_task` | `prompt` required; `session_id` / `task_params` | `submit_async` (uplinks `task_started` on accept, `task_done` on finish) |
| Task | `status` | — | mount / engine state / version / permission summary / active tasks |
| Task | `stop_task` | `task_id` | `cancel_task` |
| State | `engine_state` | — | `state` / `is_running` / `should_stop` / task count / version |
| State | `inspect` | — | node identity + `preset` / `preset_model` / slot table / `last_result` / action face |
| Snapshot | `snapshot` | `description` / `tag` (default `cnb`) | `engine.snapshot` (work-rollback / crash-rescue system) |
| Snapshot | `rollback` | `snap_id` (empty = default) | `engine.rollback` |
| Snapshot | `undo` / `redo` | — | `engine.undo` / `engine.redo` |
| Snapshot | `list_snapshots` | — | `engine.list_snapshots` (summarized, first 20) |
| Snapshot | `mark_good` | `snap_id` (empty = default) | `engine.mark_good` |
| Ops | `remount` | args passed as slot values: `{"model": "openai_compat", ...}` | `engine.remount(**slots)` (hot-swap model / tools / plugins) |
| Ops | `reload_plugins` | — | remount the current plugins slot value (module cache invalidated, edits picked up) |
| Ops | `stop_engine` | — | **replies first**, then `engine.request_stop()` after 1 s: stop tasks → deregister node → stop engine; CLI processes exit naturally |

Receipts are JSON-serialization protected (long fields truncated); the neural
permission table is still enforced before every exec (a cortex `perm revoke`
strips the atom of exec capability). `cmd.stop` (stops session tasks, instance
stays RUNNING) and `cmd.reload` (env re-read + plugin hot reload) keep their
semantics and stay on the event callbacks.

#### 30.16.4 CLI Runtime: the Atom Is the Real Instance

`norpagent cortex/node` (and `main.py --norp-cortex/--norp-node`) **assemble a
full kernel engine by default** since v1.0.7:

- assembly: `launch(preset=...)` + headless frontend (output discarded); default
  `minimal` / `mock`, zero third-party deps; `--mode <preset>` / `--model <model>`
  selectable;
- double-mount protection: `NORP_CNB_MANAGED=1` is set before assembly (the
  engine's env auto-mount is skipped; the CLI mounts the node explicitly through
  `CnbAdapter`), and `NORP_CNB_CLI=1` marks the process;
- the cortex = the top-level norpagent instance (engine bound to the Cortex, can
  run tasks locally); a node = a real atom (cortex `run_task` drives a full agent
  kernel);
- `--bare`: back to the 1.0.6 plain nervous shell (probe / placeholder echo, no
  engine);
- shutdown chain: cortex `exec stop_engine` → reply first → engine stops after 1 s
  → node deregisters → the CLI main loop sees `should_stop()` → the process exits
  naturally (the cortex topology converges).

#### 30.16.5 Uplink Fusion: Heartbeats and Events Carry Kernel State

- heartbeat provider: `node.set_heartbeat_provider(...)`; the engine binding
  injects `engine_state` / `active_tasks` / `version` / `mount` / `actions` into
  every heartbeat payload — cortex `reports` (CLI included) show each atom's
  kernel busy/idle and task count;
- task events: `run_task` uplinks `task_started` on accept and `task_done` on
  finish (the cortex sees the whole task lifecycle);
- unknown-action rejections and permission denials (`perm.denied`) keep uplinking
  as audits (Gap-B mechanism unchanged).

#### 30.16.6 Test Matrix (verified 2026-09-05, all green)

| Suite | Count | Notes |
|---|---|---|
| `python -m nervous_bus.test_cnb` | 60/60 | unit/integration (migration regression-free, through the shim) |
| `python -m nervous_bus.test_deep_tree` | 36/36 | 4-level deep-tree regression |
| `python -m nervous_bus.test_e2e` | 13/13 | real multi-process end-to-end (via main.py / norpagent.cnb.cli) |
| `test/test_cnb_automount.py` | 12/12 | env auto-mount acceptance (four downlink surfaces + perm + managed) |
| `test/test_cnb_kernel_actions.py` | A 21 + B 11 = 32/32 | v1.0.7 new: A in-process full action surface (snapshot/rollback/undo/redo/remount/stop_engine/heartbeat kernel state/task_started); B multi-process CLI default engines (engine=on, 15 actions, stop_engine process exit) |
| `test/test_cnb_tree_suite.py` | 56/56 | **2026-09-12 feedback round**: explicit tree definitions (three sources / required-parameter validation / both assembly shapes / reshape / reconcile / np integration / CLI) |
| `python -m nervous_bus.test_cnb_v200` | 44/44 | **v2.0.0 new**: task-molecule channel (mol six elements unchanged / acceptance receipt / mol_id threading), quarantine freeze (new-task rejection / alive forensics / never sweep-dead / recovery), behavior baselines (yellow→black escalation), subpoena evidence (tiers / volumes / isolation frame / read-to-burn / impersonation rejection / issuance audit) |

Run: `PYTHONPATH=src python test/test_cnb_kernel_actions.py A` (or `B`).

---

### 30.17 Kernel Feature Extensions: Task-Molecule Channel / Quarantine Freeze / Behavior Baselines / Subpoena Evidence (v2.0.0 · FarStars 远星)

> This section covers the four feature groups added in v2.0.0: the
> task-molecule (mol) structured dispatch channel with acceptance receipts,
> the node quarantine freeze (freeze/unfreeze), behavior-baseline grading,
> and subpoena evidence (level-0-only highest evidence privilege). Brand:
> the official marketing name is **FarStars (远星)** — the `norpagent` call
> convention and kernel name stay unchanged (`__brand_cn__="远星"` /
> `__brand_en__="FarStars"` / `__display_name__="FarStars（远星）· norpagent"`).

#### 30.17.1 Task-Molecule Channel: structured task_params + task_records acceptance receipts

**Background**: the cortex dispatches work to tree atoms through CNB `exec
run_task`, whose `task_params` previously carried only a flat string
(`mock_script`). When the dispatched payload is structured JSON (a mol with
six elements, including acceptance / depends_on / budget / model_tier), the
channel must carry the structured data in full and support acceptance
receipts traveling back up the tree.

**Implementation (structured extension of the CNB exec channel; no new bus)**:

- `args.task_params` of `run_task` is now a **full carrier for arbitrary
  structured JSON**: the mol six elements (`mol_id` / `objective` /
  `acceptance` / `context_capsule` / `depends_on` / `budget` /
  `model_tier`) reach the absorbing atom (the engine task) unchanged — no
  field loss, no summary degradation;
- new kernel action **`task_records`** (surface 14 → 15): the cortex runs
  `exec task_records` on any atom to read the last 100 accepted task-load
  records — the original `task_params` (the full mol) plus the completion
  receipt (`status` / `error` / `content_len` / `acceptance`); supports
  `args.task_id` / `args.mol_id` / `args.n`;
- **mol_id threads end-to-end**: acceptance audits (node audit with mol_id),
  the `task_started` uplink event and the `task_done` uplink event all carry
  `mol_id`; the `acceptance` spec is echoed back to the cortex verbatim with
  `task_done` (pass/fail judgement stays with the cortex/upper policy —
  the kernel does not adjudicate); the cortex reports ring becomes the full
  mol lifecycle view.

Verified (test matrix §30.11, `test_cnb_v200` S101~S109): the six elements
round-trip deep-equal (no loss); task_done carries mol_id + acceptance; the
audit trail is searchable by mol_id.

#### 30.17.2 Quarantine Freeze (freeze / unfreeze)

**Background**: the disposal matrix "black / suspected malicious" tier
requires quarantine = freeze order intake + preserve evidence + audit — do
not kill, do not let die; the previous per-node commands (launch/stop/
perm.revoke) either revoked intake or stopped the process, both destroying
the forensic scene.

**Implementation (node-level freeze bit + permission-plane integration +
heartbeat marking)**:

- new downlinks **`cmd.freeze`** / **`cmd.unfreeze`** (cortex
  `freeze_node`/`unfreeze_node`; ctrl `op=freeze|unfreeze`; CLI `norpagent
  freeze/unfreeze`; REPL `freeze/unfreeze`):
  - frozen = **new tasks rejected (intake closed)**: exec actions pass only
    the `FROZEN_ALLOWED_ACTIONS` whitelist (read-only evidence face:
    `engine_state` / `status` / `inspect` / `list_snapshots` /
    `task_records`); `run_task` (new orders), `stop_engine` (scene
    preservation), rollback/remount and other mutating actions are rejected
    and audited (`frozen.reject` uplinks to the cortex);
  - **process/heartbeat stay alive (forensics preserved)**: heartbeats keep
    running and carry `status=frozen` + `frozen=true` (the cortex scheduler
    drains the node);
  - **never triggers sweep-dead**: the sweep only judges heartbeat
    freshness; a frozen node's heartbeats keep it alive (verified: still
    alive past `dead_timeout`);
  - **auditable and reversible**: `unfreeze` recovers the node back to the
    tree (intake restored); a review that fails must destroy-and-rebuild
    instead (never reuse a sick node); cortex perm_audit records freeze /
    unfreeze operations;
  - paired with subpoena evidence: freeze first (prevent destruction /
    further contamination), then collect evidence.

#### 30.17.3 Behavior Baselines (kernel-side aggregation, compressed into heartbeats)

**Background**: behavior grading needs mechanical behavior baselines
(heartbeat loss / audit anomaly / task failure rates beyond thresholds →
yellow degraded / black suspected malicious); which side aggregates decides
whether the protocol surface grows.

**Implementation (kernel-side aggregation; raw streams are not uplinked)**:

- nodes accumulate behavior counters locally (`_behavior`: hb_sent/hb_ok/
  hb_fail, audit_total/audit_anomaly, task_total/task_ok/task_fail);
  anomaly classification is automatic (error fields or error/denied/reject/
  failure keywords);
- **heartbeats carry the aggregate** (`behavior`: counts + anomaly_rate /
  task_fail_rate / hb_fail_rate) — compressed uplink (no raw audit stream);
  the engine-binding task watcher calls `note_task_result(ok)` on
  completion;
- **cortex grading view**: `behavior_view()` (ctrl `op=behavior`; CLI
  `norpagent behavior`; REPL `behavior`) grades every node
  **yellow (degraded, human review)** / **black (suspected malicious,
  quarantine)** with evidence; thresholds live in
  `cortex.behavior_thresholds` (cortex-side policy, adjustable);
- accounting aligns with the kernel's raw events (same counters; sampling
  checks show no bias), and the two event kinds (uplink audit stream vs
  heartbeat reports) share the same accounting definitions.

Verified (S301~S303): heartbeat reports carry behavior fields; the
yellow→black escalation fires.

#### 30.17.4 Subpoena Evidence (level-0-only highest evidence privilege)

**Background**: the untrusted-fence forced-summary policy (structured
summaries ≤2KB enter the LLM; raw text is read-to-burn) may deprive
adjudicators of the Raw Context they need — summaries are second-hand, and
a compromised middle layer makes summaries unverifiable; uplink audits were
structured summaries only, and no raw-audit uplink existed.
CONFLICT_UNRESOLVED (insufficient evidence for adjudication) needed a raw
evidence channel.

**Implementation (a new downlink fetch command `cmd.subpoena`)**:

- **Issuance**: `Cortex.subpoena(node, basis, scope, tier_kb, ...)` (ctrl
  `op=subpoena`; CLI `norpagent subpoena`; REPL `subpoena`). Issuer-side
  **five gates**:
  ① **basis prerequisite** — one of the four accepted bases
  (`confidence_low` cortex confidence insufficient / `vote_tie` council tie /
  `evidence_conflict` contradictory evidence / `human_named` a human names
  a target), and `summary_exhausted` must be declared (summary
  adjudication exhausted: 2KB → on-demand fragments → still undecidable);
  ② **isolation frame** — the package is marked `RAW/UNTRUSTED`, held in a
  one-shot isolation box (`_subpoena_box`: read-to-burn / 300s TTL auto
  expiry / purge); adjudication context never enters long-term memory
  (records never land in audit/perm_audit bodies — issuance metadata only);
  ③ **fetch channel** — `cmd.subpoena` downlinks straight to the target
  node, which streams its raw local audit/report records verbatim (not the
  2KB summary); scope = audit/reports/both, time window and event-type
  filters;
  ④ **capacity tiers** — 64/128/256/512KB: ≤128KB level-0 (cortex) decides
  alone; >128KB needs `approved_by_human=True`; 512KB is streamed in
  volumes only (auto-pagination, the cortex fetches all volumes into the
  box); **above 512KB is forced to human adjudication** (the subpoena ends
  at a human);
  ⑤ **issuance leaves a trail** — `subpoena_audit()` (who/when/basis/scope/
  actual bytes), recorded as a **black**-level event;
- **non-delegable**: the node validates the issuer level == 0 (the true
  envelope sender is injected as `_sender_level`, immune to payload
  forgery); lower-level impersonation is rejected and uplink-audited
  (`subpoena.forged`, visible in cortex reports);
- **typical flow**: black node → freeze → subpoena → review →
  recover/rebuild.

Verified (S401~S419): basis/approval/over-limit rejections, isolation-frame
marking, volume pagination, read-to-burn, impersonation rejection and
issuance records all pass.

### 30.18 Universal Slots and the Complete-Instance Module (R-024 / R-025, 2026-09-11)

> 2026-09-11 decree revision: a neural-bus node no longer hard-wires a fixed agent-instance shape; it offers **up to 64 universal slots**. The norpagent complete instance is **not abandoned** — it is wrapped as the standard module `NorpAgentModule`, insertable into any free slot of any node.

#### 30.18.1 Design points and compatibility

| Item | Description |
|---|---|
| Slot surface | Up to **64 universal slots per node** (`MAX_SLOTS=64`); slots run over the nervous bus — models / tools / plugins / custom modules can all be mounted |
| Connector extension | CNB is the multi-instance extension of the "slot connector": one instance connects local parts locally, many instances connect across processes over the neural tree under one slot protocol |
| Complete-instance module | `NorpAgentModule` (kind=`norpagent-instance`): a standard wrapper for a live NorpEngine — pluggable, removable, describable, replaceable; the instance action surface (`KERNEL_ACTIONS`, 15 actions) is reachable through second-level slot routing |
| Auto-mount | `CnbAdapter.bind_actions()` auto-mounts the engine instance into the default slot `norpagent` (shared by CLI neural processes / env auto-mount / `unbox --cnb`) |
| Limit | The 65th slot is rejected (`SlotError`) |

**Compatibility note**: this is a breaking change to the node's internal shape (no more hard-wired instance), but the instance itself is kept — CLI neural processes, env auto-mount and `unbox --cnb` all perform the "instance to standard module" assembly automatically; existing commands and protocol are unchanged.

#### 30.18.2 Module protocol (MountableModule)

| Method | Purpose |
|---|---|
| `describe()` | White-box description (uplinked with slot snapshots) |
| `ok()` | Module health self-report |
| `on_mount(node)` | Mount callback; a raise = mount failure, no commit (transactional, zero state change) |
| `on_unmount(node)` | Unmount callback (best-effort; errors are audited, never block unmount) |
| `actions()` | Exec action table (name -> handler) the module provides |
| `heartbeat()` | Heartbeat contribution (compressed uplink with the node heartbeat) |

Two built-ins:

- `GenericModule(kind, label, payload)` — anything mountable; the payload is self-describing JSON (no preset fields, no semantic trimming; reports what is mounted);
- `NorpAgentModule(engine, adapter=None)` — the complete instance:
  - `actions()`: exports all of `KERNEL_ACTIONS` (task / molecule / state / snapshot / ops — 15 actions);
  - `describe()`: engine_state / active_tasks / preset / version / actions white-box snapshot;
  - `heartbeat()`: instance busy state (engine_state / active_tasks) uplinked.

```python
from norpagent.cnb.slots import NorpAgentModule, GenericModule

node.mount_module("norpagent", NorpAgentModule(engine))     # complete instance
node.mount_module("tools-1", GenericModule(                 # arbitrary payload
    kind="tools", label="custom toolset",
    payload={"entry": "my_tools.py", "count": 3}))
print(node.describe_slots())                                # white-box slot view
```

#### 30.18.3 SlotBay and bus actions

`SlotBay` manages mounts: capacity ≤64, unique `slot_id`, no action-name conflicts with existing slots, transactional (a failed `on_mount` does not commit); every mount / unmount enters the node audit ring. Four node slot actions are reachable over the bus:

| Action | Type | Description |
|---|---|---|
| `slot_list` | read-only | slot count / free / summaries (count / free / max_slots / slots) |
| `slot_describe` | read-only | one slot (`args.slot_id`) or all slots in full |
| `slot_mount` | mutating | mount a self-describing JSON-spec module (model / tools / plugins / custom) |
| `slot_unmount` | mutating | unmount (callback + action-surface withdrawal + audit) |

Two notes:

1. **Frozen whitelist**: a quarantine-frozen node (§30.17.2) allows the read-only evidence surface (`slot_list` / `slot_describe`) and rejects the mutating surface (`slot_mount` / `slot_unmount`);
2. **Complete-instance modules cannot be built from JSON specs**: `slot_mount` needs a live engine object, so `norpagent-instance` modules are refused there — mount `NorpAgentModule` from code instead.

```bash
# Cortex-side bus view of an atom's slots (examples)
norpagent exec --node norpbot-01 --action slot_list --args '{}'
norpagent exec --node norpbot-01 --action slot_describe \
    --args '{"args": {"slot_id": "norpagent"}}'
```

#### 30.18.4 Auto-mount and heartbeat fusion

`CnbAdapter.bind_actions()` does both: direct kernel-action registration (source=kernel) + the complete-instance module mounted into the default slot `norpagent` (source=slot, fallback action surface — even a manual assembly without direct registration keeps the full instance operation surface); the heartbeat carries slot usage (`slots.count` / `slots.free`), so the cortex `reports` view shows each atom's slot usage and free capacity.

#### 30.18.5 Verification

`src/nervous_bus/test_cnb_slots.py` (51 checks), `test/test_cnb_kernel_actions.py` (32 checks) and the M4.5 violent mixed stress domain H (including the slot sub-domain) are all green.

---

### 30.19 Explicit Neural-Tree Definitions: No Preset Shape (2026-09-12 feedback round)

> Core rule: **CNB ships no preset neural-tree shape** — the whole-tree definition must be passed explicitly at startup; per-level `LEVEL`, counts, lower-level parent, ports and other required parameters are validated **one by one, and every missing one is reported explicitly**; on the npa startup path a config error **never blocks the main thread** (explicit error, tree not loaded).

#### 30.19.1 Definition shape (format `farstars-cnb-tree/1`)

```json
{
  "format": "farstars-cnb-tree/1",
  "host": "127.0.0.1",
  "levels": [
    {"level": 0, "count": 1, "kind": "cortex", "node_id": "cortex", "port": 17800},
    {"level": 1, "count": 2, "kind": "agent", "parent": 17800, "base_port": 17810},
    {"level": 2, "count": 4, "kind": "worker", "parent": "level:1",
     "ports": [17820, 17821, 17822, 17823]}
  ]
}
```

Required parameters and semantics (validated item by item; any missing one is an explicit error):

| Field | Required | Meaning |
|---|---|---|
| `levels[].level` | yes | level 0–63; level 0 is the cortex (tree root, `count` must be 1) |
| `levels[].count` | yes | number of nodes on this level (>= 1) |
| `levels[].port` / `ports` / `base_port` | yes (one of three) | ports are explicit, never hard-wired (R-025); `port` requires `count=1`, `ports` has length `count`, `base_port` allocates consecutively |
| `levels[].parent` | required for lower levels | parent in three forms: **parent port number** (int or digit string) / parent node id / `"level:N"` (attach to level N, rotating in definition order) |
| `levels[].kind` | no | atom type; level 0 must be `cortex` |
| `levels[].node_id` | no | node id or template (may contain `{i}`); defaults to `cortex` / `<kind>-<index>` |
| `levels[].engine` | no | `true` = this node carries a full kernel engine (spawn mode only; explicitly rejected in-process) |
| `levels[].heartbeat` / `desc` / `args` | no | heartbeat interval / description / extra spawn-mode args (string list) |
| `auto.watch` / `auto.reconcile` | no | file-watch auto-reshape / auto-reconcile switches and intervals (seconds) |

Unknown fields, duplicate ports, duplicate node ids, unresolvable parent references, a parent level not lower than the child's, or a bad format — all are listed item by item (no silence, no guessing, no default topology).

#### 30.19.2 Three definition sources

| Source | Usage |
|---|---|
| direct parameters (dict) | `np(cnb={"tree": {...}})` / `norpagent tree up --def '{"levels": [...]}'` |
| JSON file | `--def tree.json`, `NORP_CNB_TREE=tree.json`, `np.remount(cnb={"tree": "tree.json"})` |
| PY file | module-level `TREE` / `SPEC` / `tree` / `spec` (possibly callables returning a dict), or `build()` / `build_tree()` — the shape may be generated programmatically |

#### 30.19.3 Two assembly shapes

| Shape | Meaning |
|---|---|
| in-process (inproc, default) | the cortex plus every bare neural node is assembled in one process (each with its own bus port); `np(cnb={"tree": ...})` binds the host engine onto the root node as a module |
| multi-process (spawn) | every node starts via a `norpagent cortex/node` child process; `engine=true` nodes carry a full kernel engine, others run `--bare` |

#### 30.19.4 Runtime reshaping (manual / automatic)

- **manual**: `np.remount(cnb={"tree": <new definition>})` diff-reshapes (unchanged nodes are kept, added/removed/changed nodes are applied; a root change rebuilds the whole tree);
- **file watch (automatic)**: `norpagent tree up --def tree.json --watch` or `auto.watch=true` — a definition-file change triggers an automatic reshape; on error the current shape is kept and the error is explicit;
- **auto-reconcile**: `--reconcile SECONDS` or `auto.reconcile=true` — lost/stopped nodes are restored per the definition automatically.

#### 30.19.5 Entries and commands

```bash
norpagent tree validate --def tree.json      # validate (item-by-item errors; exit 0/2)
norpagent tree show --def tree.json [--json] # show the resolved node table
norpagent tree up --def tree.json --mode inproc|spawn [--watch] [--reconcile 5]
```

```python
import norpagent as np

engine = np(cnb={"tree": "tree.json"})          # explicit definition at startup (in-process tree)
np.remount(cnb={"tree": {"levels": [...]}})     # runtime reshape
np.remount(cnb=False)                           # detach the whole tree
```

The `unbox` product entry supports it too: `norpagent unbox --cnb-tree tree.json` (or the profile key `cnb.tree`); the same source as the `NORP_CNB_TREE` env var.

#### 30.19.6 Error semantics (startup is never blocked)

- `np()` startup path: config errors (missing port / missing node id / a tree definition missing required parameters) **never block the main thread** — the host starts normally, the error is printed explicitly and the tree is not loaded; status `engine.cnb_status == "config-error"`, details in `engine.cnb_error`;
- direct validation surfaces (`validate_cnb_config` / `np.remount`) keep their strict "explicit error" semantics for immediate handling;
- the port rule is unchanged: no hard-wired default port (R-025); silent degradation is forbidden.

#### 30.19.7 Verification

`test/test_cnb_tree_suite.py` (56 checks): three sources, item-by-item required-parameter errors, three parent forms, in-process assembly with diff reshape, file-watch reshape, auto-reconcile, multi-process process trees, np integration and error semantics, CLI — all green; the CNB family and M4.5 re-run green.

## Chapter 31 Product Distribution: norpagent unbox

### 31.1 Purpose

`norpagent unbox` is the **product-distribution entry** (R-006): one command starts the ready-to-use self-evolving user software (architecture book §8.1). Assembly:

| Part | Description |
|---|---|
| Core agent | **A single powerful agent** (R-014: no default atom set); the engine assembles with the profile under the standard preset (full tool surface) |
| Cortex (optional) | CNB level-0 cortex process (with a real engine); not carried by default (R-023), enabled explicitly with `--cnb`; when enabled the port must be configured manually (R-025) |
| Console | Web frontend (chat / settings / rollback / plugins / console page); open the browser and use it |
| Evolver | The self-evolution loop's settings foundation (R-004 / R-005); on by default (major = manual, normal = auto) |
| Profile | `~/.norpagent/unbox.json` — declarative data, readable and editable; changes take effect immediately |

The user's three-nots principle (R-007): no need to read the developer manual, no need to know how to develop, no need to know the runtime process; but the console keeps a permanent "inspect and intervene" channel (white-box, non-intrusive by default).

### 31.2 Quick start

```bash
norpagent unbox                          # open-and-use in the browser (default port 8890)
norpagent unbox --port 8891 --no-browser # custom port / do not open a browser
norpagent unbox --smoke                  # self-check: assemble -> health check -> exit (CI/tests)
norpagent unbox --cnb --cnb-port 17811   # enable CNB explicitly (port required, R-025)
norpagent unbox --cnb-parent http://127.0.0.1:17800 --cnb-port 17811
                                         # join an existing neural tree as a node
```

| Flag | Description |
|---|---|
| `--port N` | Web entry port (default from the profile; 8890 on first run) |
| `--no-browser` | Do not open the browser automatically |
| `--smoke` | Self-check: assemble -> health check -> exit (0 on success / 1 on failure) |
| `--cnb` | Enable CNB explicitly (not carried by default, R-023) |
| `--cnb-node-id ID` | CNB node id (defaults to `unbox-<pid>`) |
| `--cnb-parent URL` | Join an existing neural tree as a node |
| `--cnb-port N` | CNB node port (required when enabled; a missing value is reported explicitly without blocking startup, R-025 / §30.19.6) |
| `--cnb-tree <def>` | explicit neural-tree definition (JSON / PY file path or JSON text); the whole tree assembles from it, ports included; no preset shape (§30.19) |
| `--profile PATH` | Profile path override |

Startup output (console):

```
FarStars unbox software is online
  entry       http://127.0.0.1:8890/
  console     http://127.0.0.1:8890/farstars
  agent       single powerful agent (preset=standard)
  profile     ~/.norpagent/unbox.json
  CNB         not carried (off by default, R-023)
  exit        Ctrl+C (or via the console)
```

### 31.3 Profile (unbox.json)

Created automatically on first run; format `farstars-unbox/1`; a profile that is not a JSON object / cannot be read raises a clear error (no silent degrade). Default fields:

| Field | Default | Description |
|---|---|---|
| `name` | `FarStars Unbox` | profile name |
| `preset` | `standard` | single powerful agent (full tool surface) |
| `model` | `null` | `null` = engine default; a model config may be set |
| `ui` | `web` | frontend shape |
| `port` | `8890` | Web entry port |
| `console` | `true` | star-track console / built-in console page |
| `evolution.enabled` | `true` | self-evolution master switch |
| `evolution.approval` | `major-manual` | default: major manual / normal auto (`all-manual` / `all-auto` also supported) |
| `evolution.idle_policy` | `reduced` | reduce or stop while idle (R-011) |
| `cnb.enabled` | `false` | not carried by default (R-023) |
| `cnb.node_id` / `cnb.parent` / `cnb.port` | `null` | the port is required when enabled (R-025) |
| `cnb.tree` | `null` | explicit neural-tree definition (JSON / PY file path or JSON text; the whole tree assembles from it, ports included) |

### 31.4 Two CNB assembly shapes

| Shape | Trigger | Structure |
|---|---|---|
| Standalone cortex (tree root) | `--cnb --cnb-port N` (no parent) | a level-0 cortex lives in this process; the engine binds via `CnbAdapter` as the cortex engine slot — the complete instance becomes a standard slot module on the cortex node (§30.18) |
| Tree node | `--cnb-parent URL --cnb-port N` | the engine auto-mounts into the existing neural tree as a node (same path as env auto-mount) |
| Neural tree (explicit definition) | `--cnb --cnb-tree <def>` | assembles the whole tree from an explicit definition (no preset shape); the host engine binds as the root-node module; ports come from the definition (§30.19) |

Starting CNB without a port prints a clear error without blocking startup (R-025 revision / 2026-09-12 feedback round: the port is not hard-wired and must be configured manually; on a config error the product keeps running and the tree is not loaded, with the error printed explicitly).

### 31.5 Self-check mode (--smoke)

Flow: assemble -> Web health check (`/api/health`) -> (when CNB is enabled) tree readiness check -> exit.

- Standalone cortex: checks the cortex bus health (`/cnb/health`) and the **complete-instance slot module** on the cortex node (`instance_module_mounted`);
- Tree node: waits for the engine mount status (`cnb_status == "mounted"`);
- Neural tree (explicit definition): waits until `cnb_status` reaches `mounted`; `config-error` follows the "explicit error, never blocking startup" semantics and is reported honestly with the error text.

The last line is `SMOKE OK` (exit 0) or `SMOKE FAILED` (exit 1); CI and tests can assert on it.

### 31.6 Failure handling and rescue hints

| Scenario | Behaviour |
|---|---|
| CNB enabled without a port | explicit error without blocking startup: the product keeps running and the tree is not loaded; states the port is not hard-wired and must be configured manually (R-025 revision / §30.19.6) |
| Corrupt profile | Clear error (no silent degrade) |
| Startup failure | Rescue hints: safe mode (minimal kernel) `norpagent --safe-mode`; crash-rescue rollback `norpagent-rescue rollback --last-good` |
| Evolution foundation failure | Never blocks the product start (best effort; prints `evolution bootstrap skipped`) |

### 31.7 Environment variable

| Variable | Purpose |
|---|---|
| `NORPAGENT_UNBOX_HOME` | Overrides the root directory for the profile / settings DB / evolution log (default `~/.norpagent`; used for test isolation) |

---

## Chapter 32 The Self-Evolution System: Hot Reload, Checkbox Approvals and Evolution Packages

### 32.1 Purpose and overview

The self-evolution subsystem (`norpagent.evolution`) is the shared settings and execution foundation of the four evolution classes (2A memory / 2B skills / 2C configuration / 2D code) (architecture book §7). Five modules:

| Module | Responsibility | Requirements |
|---|---|---|
| `store.py` | settings source of truth (SQLite + JSON import/export) + audit + evolution log | R-017 |
| `points.py` | evolution-point registry + per-item checkbox approval | R-005 |
| `hotswap.py` | code-evolution hot reload (new-file new-logic; the original file's bytes stay untouched) | R-004 |
| `packages.py` | evolution packages `.fspack` + bundles `.zip` | R-010 / R-012 |
| `rhythm.py` | evolution rhythm and direction (idle policy / usage candidates / command channel) | R-011 |

`norpagent unbox` (Chapter 31) calls `bootstrap(profile)` at startup: create the DB + register the schema + write the profile's evolution policy into the settings source of truth; a failure never blocks the kernel.

### 32.2 Settings source of truth (SettingsStore)

- Storage: SQLite (default `~/.norpagent/settings.db`, override with `NORPAGENT_SETTINGS_DB`); three tables: `kv` (values) / `schema` (item metadata) / `audit` (audit ring);
- Every item carries first-class **`evolvable` / `locked`** flags;
- **An evolver writing a locked / non-evolvable item = kernel refusal + audit alarm** (`SettingsLockedError`; actors whose name starts with `evolution` are guarded);
- JSON export / import: `export_json()` / `import_json()` (format `farstars-settings/1`: schema + values + audit tail);
- Audit: `audit_tail(n)` — who changed what, when (including refused writes).

### 32.3 Evolution points and checkbox approval

The kernel inventory has **14 points**: kernel loops and scheduling, agent runtime, context and memory, tool set, model adapters, hooks, nervous bus, snapshots and rollback, security, plugin pipeline, built-in frontend and settings panel, frontend family, preset modes, the evolver itself.

Checkbox semantics (R-005):

| Checkbox | Meaning | Execution |
|---|---|---|
| checked | that item is manually approved | a pending-approval card first; it runs only after a human confirms |
| unchecked | auto-approved | snapshot -> apply -> verify -> auto-rollback on failure |

Defaults: **major items checked (manual), normal items unchecked (auto)**; the major/normal classification itself is a setting, editable per item; the evolver itself (`evolution.self`) is factory-locked (`locked=True`: any evolution write is refused) and security defaults to manual. Checkbox changes are audited.

API: `ApprovalPolicy.decisions()` (panel data source) / `set_manual()` (checkbox) / `set_category()` / `clear_manual()` (back to default) / `can_evolve()` (combined with the master switch).

### 32.4 Code-evolution hot reload (hotswap)

Iron rule (R-004): **never rewrite the original file in place, never delete the original logic** — always "produce a new file -> verify -> hot-swap to the new logic", keeping the original and a one-click rollback.

| Step | API | Description |
|---|---|---|
| Produce | `stage_new_version(target, new_code, tag="")` | the new version file `origstem__evo_<timestamp>[_tag]_<n>.py` is written next to the original; the original stays read-only |
| Activate | `activate(record, validate=..., apply_fn=...)` | load the new file -> validate -> apply; any failure = no activation + status `failed` (auto-rollback semantics, never a partial activation) |
| Roll back | `rollback(record, apply_fn=...)` | drop the new version, return to the original logic (optionally re-apply the original) |
| Evidence | `original_intact(record)` | verifies the original file's sha256 matches the staged-time hash — verifiable proof that the original logic is never deleted |
| List | `list_versions(target)` | lists all historical version files |

State machine: `staged -> active / failed`; after a rollback `rolled_back`. Everything is logged (JSONL).

### 32.5 Evolution packages (.fspack) and bundles (.zip)

**Evolution package** (R-010):

- suffix `.fspack`; **also reads `.json` and `.py`**;
- self-describing payload (format `fspack/1`) + **sha256 verification** + **author attribution**;
- API: `build_fspack / write_fspack / export_fspack / read_fspack / verify_fspack / import_fspack`;
- failed verification / failed apply: **the failed logic is never used**; errors are reported truthfully and logged (`fspack.import.failed`).

**Bundle** (R-012):

- `.zip`, up to **1024** packages per bundle (over-limit = whole refusal: exports are not created, imports are not partial);
- batch import: **one failure never blocks the rest**; a truthful per-entry report `{total, ok, failed, failed_entries, applied}`;
- API: `export_bundle / import_bundle`; log events `fspack.bundle.import.ok` / `fspack.bundle.import.failed`.

One-click export / import in the frontend (settings panel): `/api/evolution/export?kind=fspack&author=...` and `/api/evolution/import`.

### 32.6 Rhythm and direction (rhythm)

| Capability | API / setting key | Description |
|---|---|---|
| Idle policy | `IdlePlanner.policy()` / `evolution.idle_policy` | `reduced` (default: reduce or stop while idle) / `off` (no idle evolution) / `auto` (keep going) |
| Idle threshold | `evolution.idle_min_seconds` | 600 seconds without demand marks idle (default) |
| Usage candidates | `UsageTracker.candidates()` / `evolution.candidate_threshold` | user-frequent features (**>= 3 uses**, adjustable) enter the evolution candidates |
| Command channel | `command_evolution(command)` | the user can order evolution directly (highest priority; execution still goes through hot reload + checkbox approval) |

### 32.7 Interface surface and logs

| Endpoint | Method | Description |
|---|---|---|
| `/api/evolution/points` | GET | current decision view of all evolution points (panel data source) |
| `/api/evolution/points` | POST | change checkbox / category / reset to default (changes are audited) |
| `/api/evolution/log` | GET | evolution log tail (hot-reload / package records) |
| `/api/evolution/export` | GET | export (`kind=fspack` package; settings JSON snapshot by default) |
| `/api/evolution/import` | POST | import `.fspack` / `.json` / `.py` / `.zip` (bundle per-entry semantics) |

Evolution log (JSONL, default `~/.norpagent/evolution_log.jsonl`, override `NORPAGENT_EVOLUTION_LOG`) events: `hotswap.stage` / `hotswap.activate` / `hotswap.failed` / `hotswap.rollback` / `fspack.export` / `fspack.import` / `fspack.import.failed` / `fspack.bundle.export` / `fspack.bundle.import.ok` / `fspack.bundle.import.failed` / `evolution.command` and more.

### 32.8 Verification

- `test/test_evolution_suite.py` (49 checks) all green;
- M4.5 violent mixed stress domain I (self-evolution: approvals / hot reload / packages / rhythm) all green.

### 32.9 Runtime Hardening: Health Checks, Auto-Revert and Sweeps (2026-09-12 feedback round)

> Feedback question: will self-evolution break itself? The answer is not a promise but **layered defenses, each verifiable** (every mechanism below is covered by a suite).

**Defense list (defense in depth)**:

| Layer | Mechanism | Evidence |
|---|---|---|
| 1 original untouched | code evolution never rewrites or deletes the original file — a new version file (`<stem>__evo_<timestamp>.py`) is produced instead; the original bytes stay intact | `hotswap.original_intact()` (sha256 compare) |
| 2 validation on load | activation re-loads the new file (+ optional `validate` callback); syntax / import errors refuse activation outright | `hotswap.activate()` |
| 3 post-activation health check | new `health` callback: immediately after activation (default check = new file exists / loads / original intact); on failure an **automatic revert** re-applies the original logic (or calls a custom `revert_fn`) and records `reverted` | `activate(..., health=..., revert_fn=...)` |
| 4 active-version sweep | `hotswap.verify_active()`: file exists / reloads / original sha256 unchanged; `ProposalBoard.health_sweep()` sweeps every applied code proposal and rolls damaged ones back with a breaker count, notification and log | `verify_active` / `health_sweep` |
| 5 startup sweep | `bootstrap()` (unbox startup) runs one sweep automatically, so a damaged version left over from an earlier session is found and rolled back at startup | `evolution.bootstrap()` |
| 6 breaker and approvals | consecutive failures pause that evolution point automatically; major points default to manual approval (checkbox scheme); locked settings are refused to every evolver | `CircuitBreaker` / `ConfigEvolver.check_target` |
| 7 fallbacks | snapshot timeline / crash-rescue CLI / safe mode stay available at every stage | Chapters 15 / 24 |

```python
from norpagent import evolution as evo

# post-activation health check + auto revert (custom revert first, else re-apply the original via apply_fn)
record = evo.stage_new_version("mod.py", new_code)
evo.activate(record, apply_fn=apply_fn, health=lambda m: smoke(m))
print(evo.verify_active(record))     # {'ok': True, 'checks': {...}}

board = evo.ProposalBoard()
print(board.health_sweep())          # sweep all applied code proposals (also runs once at startup)
```

Verification: `test/test_evo_hardening_suite.py` (19 checks: healthy pass / failure revert / custom revert / explicit failure without revert means / bad code refused / missing-file and tampered-original detection / sweep rollback + breaker / startup sweep / locked key refusal) green; the existing evolution suite (49) re-run green.

## Chapter 33 The Complete Plugin Development Guide

> **Positioning**: plugins are the extension surface closest to the kernel in "shallow development". Without touching kernel source, everything a customer or third party can do is done through plugins: tools, hooks, slots, components, models, services, pages, CLI commands, settings. This chapter is the plugin author's complete reference, covering everything from the first plugin to a signed release. Chapter 11 is the host-side overview, 25.11 the quick-start version, and this chapter the full version.
>
> **Customer visibility**: this chapter, together with 25.11 and Chapter 11, forms the complete plugin documentation delivered to customers. The plugin-guide files in the repository root are internal material; this chapter is authoritative.

### 33.1 Positioning and Overview

#### 33.1.1 What Plugins Can Do

A plugin is distributed as a standalone `.py` file (or a manifest package). On load the host automatically applies the full safety pipeline: signature verification / AST audit / import restrictions / network policy / human approval. Six capability layers are available:

| Layer | Capability | Declaration and entry |
|---|---|---|
| Tools | Register tools with OpenAI function schemas (entering the model's tool table) | `TOOLS` + `execute()`; dynamic: `api.register_tool()` |
| Hooks | Define any of the 29 standard hooks (16 legacy + 13 native) | Module-level functions; custom hooks via `api.define_hook()` |
| Events | Subscribe to / fire any bus event (standard hooks / custom events) | `api.subscribe()` / `api.emit()` |
| Assembly | Register custom architecture slots / generic components / models / sessions / sandboxes / schedulers / UIs | the `api.register_*` surface of `setup(api)` |
| Collaboration | Service registration and discovery (plugin-to-plugin / plugin-to-host), dependency and version declarations | `api.provide()` / `api.get()`; `PLUGIN_REQUIRES` / `PLUGIN_MIN_NORPAGENT` |
| Interface | Mount Web pages (front / flow / farstars), register CLI commands, declare settings | `api.mount_page()` / `api.register_cli_command()` / `api.register_settings()` |

#### 33.1.2 Two Distribution Shapes

| Shape | Structure | Use when |
|---|---|---|
| Single-file plugin | one `.py` file (module constants + functions) | most cases; the Web panel can upload-and-install it directly |
| Manifest package | a directory + `manifest.json` + an entry module (default `plugin.py`) | you need version / permission / isolation / signature metadata, or multi-file organization |

Both shapes expose the same module-level interface; the package shape merely adds a metadata file.

#### 33.1.3 Loading Paths

Plugin directories enter the system through any of the following; all five paths share the same safety pipeline:

```python
# 1. npa() slot (literal semantics, a directory list)
npa(plugins=["./my_plugins"])

# 2. library facade (full lifecycle + status)
from norpagent.plugins import PluginSystem
ps = PluginSystem(reg, ["./my_plugins"], config={...})
ps.load()

# 3. command line
norpagent --mode standard --plugin-dir ./my_plugins

# 4. Web settings panel (directory management + upload install + disable / uninstall / reload)

# 5. single-file programmatic install (the hot-install entry for evolution flows /
#    external orchestrators; loads exactly the given file)
from norpagent.plugins import install_plugin_file
loader, info = install_plugin_file(reg, "./my_plugins/one.py", config={...})
print(info.enabled, info.error or "ok")
```

For a full runtime replacement use `npa.remount(plugins=[...])`: the framework first unloads the old loader completely (hooks unsubscribed / tools removed / on_unload run), then installs the new directories — nothing stacks and nothing leaks.

### 33.2 Quick Start

#### 33.2.1 The Minimal Plugin (One Tool)

```python
# my_plugins/hello_plugin.py
PLUGIN_NAME = "Hello Plugin"
PLUGIN_VERSION = "1.0.0"
PLUGIN_PUBLISHER = "your-name"
PLUGIN_DESCRIPTION = "Demo plugin: a single tool."

TOOLS = [{
    "type": "function",
    "function": {
        "name": "hello",
        "description": "Greet the given name.",
        "parameters": {
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "additionalProperties": False,
        },
    },
}]


def execute(tool_name, args, ctx):
    if tool_name == "hello":
        return f"Hello, {args.get('name') or 'world'}!"
    return None
```

#### 33.2.2 Load and Verify

```python
import norpagent as np

npa = np(preset="minimal", plugins=["./my_plugins"])
# or hot-mount onto a running engine:
np.remount(plugins=["./my_plugins"])
```

Verify from the command line (without starting the full application; prints the plugin table):

```bash
norpagent plugins list --plugin-dir ./my_plugins
```

The output shows per-plugin enabled state, signature status, isolation mode, tool and hook counts, plus load-failure reasons and warnings.

#### 33.2.3 The Debugging Trio

| Tool | Purpose | Example |
|---|---|---|
| `ctx.logger` | per-plugin log (stdout + `~/.norpagent/plugin_logs/<name>.log`) | `ctx.logger.info("...")`; levels `debug / info / warn / error` |
| `ctx.storage` | per-plugin state store (survives across hooks and tools) | `ctx.storage["count"] = ctx.storage.get("count", 0) + 1` |
| diagnostics | hook exceptions are reported automatically (never silent): first error printed + counted + recorded into `PluginInfo.diagnostics` | visible in the Web panel / `plugins list` / `ps.status()` |

During development, relax the audit and run in-process for easy breakpoints:

```python
from norpagent.plugins import PluginSystem
ps = PluginSystem(reg, ["./my_plugins"], config={
    "plugin_security_audit": "warn",
    "plugin_isolation": "inproc",
})
```

Switch back to `auto` before shipping.

### 33.3 Plugin Format and Metadata

#### 33.3.1 Single-File Plugins: Module Constant Reference

| Constant | Type | Required | Meaning |
|---|---|---|---|
| `PLUGIN_NAME` | str | yes | display name (identity for reload and panel display) |
| `PLUGIN_VERSION` | str | no | default `0.0.0` |
| `PLUGIN_PUBLISHER` | str | no | publisher |
| `PLUGIN_DESCRIPTION` | str | no | description |
| `TOOLS` | list | no | OpenAI function schemas |
| `APPROVAL_HINTS` | dict | no | tool -> approval hint (see 33.4.5) |
| `ISOLATION` | str | no | `"process"` = process isolation (read statically via AST, plugin code not executed) |
| `PLUGIN_CAPABILITIES` | list | no | capability surface (see 33.8.1); absent = the base set `tools / hooks / events` |
| `PLUGIN_REQUIRES` | list / dict | no | dependency declarations (see 33.10) |
| `PLUGIN_MIN_NORPAGENT` | str | no | minimum framework version, e.g. `"2.1"` |
| `__norpagent_type__` | str | no | file-as-module type for FLOW (`"tool"` / `"plugin"`) |

Function-level interface: `execute(tool_name, args, ctx)`, any of the 29 hooks, `setup(api)`, `on_load(ctx)`, `on_unload(ctx)`.

#### 33.3.2 Manifest Package Format

```
my_pkg/
├─ manifest.json
├─ plugin.py          # entry (changeable via manifest.entry)
└─ ...                # private modules (importable within the same directory)
```

`manifest.json` field reference:

| Field | Type | Meaning |
|---|---|---|
| `name` | str | plugin name (`PLUGIN_NAME` in the entry module wins) |
| `version` | str | version |
| `publisher` / `author` | str | publisher (`publisher` wins) |
| `description` | str | description |
| `entry` | str | entry file, default `plugin.py` |
| `isolation` | str | `inproc` / `process` |
| `permissions` | list | permission declarations (validated when `require_permissions` is on; `process` / `file_read` / `file_write` ...) |
| `capabilities` | list | capability surface (same as `PLUGIN_CAPABILITIES`) |
| `requires` | list / dict | dependency declarations (same as `PLUGIN_REQUIRES`) |
| `min_norpagent` | str | minimum framework version |
| `signature` | object | signature block (see 33.9.2) |

When both manifest and module constants exist: `PLUGIN_NAME` wins over `manifest.name`; `version / publisher / description` come from the manifest first.

#### 33.3.3 File-as-Module (FLOW Integration)

A plugin file carrying `__norpagent_type__` can be dropped onto the FLOW canvas as a module node; `"tool"` marks a single-tool module and `"plugin"` a full plugin.

### 33.4 Tool Development

#### 33.4.1 Schema Rules

Follow the OpenAI function format (`type` / `function.name` / `function.description` / `function.parameters`); list `required` explicitly and prefer `additionalProperties: False`.

Write descriptions that state when to use the tool, what the parameters mean, and what is returned — the model decides from the description.

#### 33.4.2 The execute() Entry

```python
def execute(tool_name, args, ctx):
    """Unified entry: return str / ToolResult / None; None = not this tool."""
```

- returning `str`: the text is fed back to the model as the tool result;
- returning `ToolResult`: a full result (may set `success=False`);
- raising: the framework captures it into a failed result (the task never breaks);
- `args` is normalized (empty dict when absent).

#### 33.4.3 Dynamic Tools (setup)

Beyond the static `TOOLS`, handlers can be registered inside `setup(api)`:

```python
def setup(api):
    api.register_tool(
        "dyn_echo",
        lambda args: "echo:" + str(args.get("text", "")),
        description="Dynamically registered demo tool",
    )

# two-argument form is detected: handler(args, plugin_ctx)
```

When `schema` is omitted an empty-parameter schema is generated; pass a full schema for real parameters.

#### 33.4.4 Name Conflicts

Tool names are global (a later registration overwrites an earlier one, with a log notice). Prefix names (`myplugin_xxx`) to avoid collisions.

#### 33.4.5 APPROVAL_HINTS

```python
APPROVAL_HINTS = {
    # read-only tool needs no approval; undeclared tools follow the host master switch
    "hello": {"approval": "none", "risk": "L0"},
}
```

`approval: "none"` skips human approval for that tool; undeclared tools follow the host `approval_enabled` policy.

### 33.5 Hook Development (All 29 Hooks)

Hook functions live directly in the plugin module; the name is the hook name and no registration is needed. Signature convention: **business arguments first, `PluginContext` last**.

#### 33.5.1 The 16 Legacy Hooks (aligned with the existing ecosystem)

| Hook | Plugin signature | Return-value semantics |
|---|---|---|
| `on_agent_init` | `(ctx)` | ignored |
| `on_agent_shutdown` | `(ctx)` | ignored |
| `on_task_start` | `(task_text, ctx)` | ignored |
| `on_task_done` | `(summary, final_reply, ctx)` | ignored (both parameters carry the final reply) |
| `on_task_error` | `(error_msg, ctx)` | ignored |
| `on_task_stopped` | `(ctx)` or `(reason, ctx)` | ignored (auto-adapted from the function's positional arity) |
| `on_task_timeout` | `(elapsed, ctx)` | ignored |
| `before_step` | `(step, messages, ctx)` | return a list to replace this round's messages; returning the input unchanged = no rewrite |
| `after_step` | `(step, reasoning, content, tool_calls, ctx)` | ignored (observation; `tool_calls` is the full list) |
| `before_tool_call` | `(tool_name, args, ctx)` | return a dict to replace arguments; returning the input unchanged = no rewrite; return `False` to block the call |
| `after_tool_call` | `(tool_name, args, result, ctx)` | return a str to replace the result text; returning the input unchanged = no rewrite |
| `on_user_input_required` | `(question, ctx)` | ignored |
| `on_reasoning` | `(token, ctx)` | ignored |
| `on_content` | `(token, ctx)` | ignored |
| `on_event` | `(event_type, data, ctx)` | ignored |
| `on_usage_update` | `(usage, ctx)` | ignored (`usage` carries both `input_tokens / output_tokens / tool_call_tokens` and `input / output / total`) |

#### 33.5.2 The 13 Native Hooks (the rest of the 9-layer kernel surface)

| Hook | Plugin signature | Return-value semantics |
|---|---|---|
| `before_input` | `(user_input, session_id, params, ctx)` | return a str to replace the input |
| `after_input` | `(user_input, session_id, ctx)` | ignored |
| `before_session_create` | `(session_id, title, params, ctx)` | return a str or `{"title": str}` to replace the title |
| `after_session_create` | `(session_id, title, ctx)` | ignored |
| `before_message_append` | `(session_id, message, ctx)` | return a ChatMessage to replace; return `False` to drop |
| `after_message_append` | `(session_id, message, ctx)` | ignored |
| `before_build_messages` | `(system_prompt, session_id, step, tool_names, ctx)` | return a str or `{"system_prompt": str}` |
| `after_build_messages` | `(messages, system_prompt, step, ctx)` | return a list to replace the whole set |
| `before_model_call` | `(step, messages, tool_schemas, params, ctx)` | return `{"messages": [...], "params": {...}}` |
| `after_model_call` | `(step, output, ctx)` | return a ModelOutput to replace |
| `on_tool_error` | `(tool_name, error, args, ctx)` | ignored |
| `before_result` | `(result, ctx)` | return a RunResult to replace |
| `after_result` | `(result, ctx)` | return a RunResult to replace (takes effect) |

#### 33.5.3 Mutating-Hook Semantics (Important)

- **Winner rule**: a mutating hook returning a non-None value participates in the rewrite; the bus lets the **first non-None value win** and ignores the rest.
- **Pass-through normalization**: returning the input unchanged (the legacy `return messages` / `return args` / `return result` idiom) is treated as "no rewrite" (equivalent to `None`) and never shadows later plugins' rewrites. Full compatibility with the legacy ecosystem.
- **All side effects run**: for one hook event, **every subscriber is invoked exactly once**; counters, logs and writes of all plugins execute — the old "an earlier non-None return stops later plugins from running" truncation is gone.
- **HookVeto**: raising `HookVeto` in any hook vetoes with one vote according to the execution point's semantics (usually the task ends as `stopped`, or this step/call is skipped); the veto takes effect immediately.
- **Exception isolation**: an uncaught exception in a hook never breaks the main loop: it is reported (first occurrence printed + counted + recorded in `diagnostics`) and the call counts as "no rewrite".

#### 33.5.4 Ordering and Frequency

Typical single-task timeline (per-step loop):

```
on_task_start
  └─ before_step (once per step)
      ├─ before_build_messages / after_build_messages
      ├─ before_model_call → [on_reasoning / on_content / on_event / on_usage_update]
      ├─ after_model_call
      ├─ before_tool_call → tool execution → after_tool_call (once per tool call)
      └─ after_step (rounds with tool calls)
on_task_done / on_task_error / on_task_stopped / on_task_timeout (one of four)
```

Frequency notes: `on_reasoning` / `on_content` are streaming high-frequency hooks (per delta) — keep them light; `on_usage_update` fires per usage update.

#### 33.5.5 Timeouts and Isolation Constraints

Hooks of process-isolated plugins are relayed over RPC with a per-hook limit of 5 seconds (abandoned on timeout; the main loop never stalls). In-process plugins have no such limit, but fast returns are still recommended.

### 33.6 PluginContext Reference

Every hook and `execute()` receives a `PluginContext` as its last parameter:

| Field | Type | Meaning |
|---|---|---|
| `plugin_name` | str | plugin name |
| `project_root` | str | current workspace root (when the task context provides it) |
| `app_dir` | str | application data directory (user home) |
| `config` | dict | read-only snapshot of the host load config |
| `storage` | dict | **per-plugin state store** surviving across hooks, tools and tasks (within one load session) |
| `logger` | PluginLogger | per-plugin log: `debug / info / warn / error` to stdout + log file |
| `current_step` | int | current step (when the kernel provides it) |
| `total_usage` | dict | cumulative token usage (when the kernel provides it) |
| `api` | PluginAPI | registration facade (available during and after `setup`; see 33.8) |

```python
def on_task_start(task_text, context):
    context.logger.info(f"task started: {task_text[:60]}")
    context.storage["started_at"] = __import__("time").time()

def before_tool_call(tool_name, args, context):
    count = context.storage.get("tool_calls", 0) + 1
    context.storage["tool_calls"] = count
    context.logger.debug(f"tool call #{count}: {tool_name}")
```

### 33.7 Lifecycle and Hot Reload

#### 33.7.1 Lifecycle Functions

| Function | Timing | Notes |
|---|---|---|
| `setup(api)` | after the safety pipeline, before registration | register extensions (tools / slots / components / hooks / events / services / pages / CLI / settings); an exception rejects the plugin and **rolls back its registrations** |
| `on_load(ctx)` | after registration | runtime initialization (open resources, warm caches, log); failures do not reject the plugin, they are recorded in diagnostics |
| `on_unload(ctx)` | before unload / reload / shutdown | clean up; hooks are unsubscribed and tools removed only after it completes |

Timeline: `safety pipeline → setup(api) → registration (tools into the table / hooks onto the bus) → on_load(ctx) → [runtime] → on_unload(ctx) → teardown (unsubscribe / remove tools)`.

#### 33.7.2 Hot Reload (Clean)

```python
from norpagent.plugins import PluginSystem
ps = PluginSystem(reg, ["./my_plugins"], config={...})
ps.load()
ps.reload("Hello Plugin")   # full unload (on_unload + unsubscribe + tool removal) -> full pipeline again
ps.unload("Hello Plugin")   # unload a single plugin
```

Full replacement (the recommended production path):

```python
npa.remount(plugins=["./my_plugins_v2"])   # unload the old loader entirely -> install the new directories
```

Unload guarantees: hook subscriptions are really removed (same listener objects), tools are deleted from the table, and setup registrations (subscriptions / slots / services / commands / dynamic tools / components) are reclaimed in order. Model / session / sandbox / scheduler / UI registrations follow name-overwrite semantics and are not deleted (a same-named registration after reload naturally overwrites them).

#### 33.7.3 Disable and Uninstall (host side)

| Action | Semantics | Entry |
|---|---|---|
| Disable | the plugin stays listed but is not loaded (`enabled=False`, reason visible) | Web panel button; config `plugin_disabled: ["name"]` |
| Uninstall | delete the plugin file (or package directory) from disk, then reload | Web panel (with confirmation); the path must live inside a plugin directory |
| Enable | remove from the disabled list and reload | Web panel button |

### 33.8 setup(api): The Registration Facade

`setup(api)` is the only host entry a plugin gets at registration time; `api` is a `PluginAPI` instance. Everything registered through it belongs to the plugin and reclaimable items are torn down on unload.

#### 33.8.1 Capability Declarations (Gates)

```python
PLUGIN_CAPABILITIES = ["tools", "hooks", "events", "slots", "components",
                       "services", "cli", "settings"]
```

- absent = the base set: `tools / hooks / events`;
- `"*"` or `"all"` = everything;
- calling an undeclared capability raises `PluginCapabilityError` (setup then rejects the plugin and records the reason in `error`);
- the host may tighten further via the `plugin_capabilities` config key (`None` = no extra restriction).

All capability names: `tools / hooks / events / slots / components / models / sessions / sandboxes / schedulers / uis / services / pages / cli / settings`.

#### 33.8.2 API Reference

| Method | Capability | Notes |
|---|---|---|
| `register_tool(name, handler, *, schema=None, description="")` | tools | dynamic tool; `handler(args)` or `handler(args, plugin_ctx)` |
| `register_slot(spec)` / `unregister_slot(name)` | slots | custom architecture slot (`SlotSpec` or a field dict; see section 3.8) |
| `register_component(kind, name, factory)` | components | generic component (referenced by presets via `components={kind: name}`) |
| `register_model(name, provider)` | models | register a model adapter |
| `register_session(name, factory)` | sessions | session-store implementation |
| `register_sandbox(name, factory)` | sandboxes | sandbox implementation |
| `register_scheduler(name, factory)` | schedulers | scheduler implementation |
| `register_ui(name, adapter)` | uis | renderer implementation |
| `define_hook(name, *, mutating=False, description="")` | hooks | define a custom hook on the engine hook system |
| `subscribe(event, fn)` | events | subscribe to any bus event (standard hooks / custom hooks / custom events) |
| `emit(event, **payload)` | events | fire a bus event |
| `provide(name, obj)` / `get(name, default=None)` | services | service registration and discovery (plugin-to-plugin / plugin-to-host) |
| `mount_page(page, html)` | pages | mount a Web page (`"front"` / `"flow"` / `"farstars"`; queued when the engine is not ready and consumed at frontend attach) |
| `register_cli_command(name, handler, *, help="")` | cli | register a CLI command (run via `norpagent plugins run <name>`; `handler(argv)` or `handler()`) |
| `register_settings(schema)` | settings | declare a settings schema (shown in the Web panel) |
| `get_setting(key, default=None)` / `set_setting(key, value)` | (with settings) | persisted plugin settings (the host writes `~/.norpagent/plugin_settings/`) |

#### 33.8.3 Combined Example

```python
PLUGIN_CAPABILITIES = ["tools", "hooks", "events", "services", "cli", "settings"]


def setup(api):
    # a service other plugins / the host can use
    api.provide("weather.cache", {})

    # a dynamic tool
    api.register_tool("weather_now", query_weather, description="Live weather")

    # a custom hook + subscription
    api.define_hook("weather_updated", description="weather data updated")
    api.subscribe("weather_updated", lambda e: api.logger.info("weather updated"))

    # a CLI command
    api.register_cli_command(
        "weather-refresh", lambda argv: refresh_all(), help="refresh the weather cache")

    # settings
    api.register_settings({"type": "object",
                           "properties": {"city": {"type": "string"}}})
    api.set_setting("city", "Beijing")
```

```bash
norpagent plugins run weather-refresh --plugin-dir ./my_plugins
```

### 33.9 The Safety System (Author's View)

#### 33.9.1 The Load Pipeline

```
discover → signature verify → AST audit → permission declarations → isolation decision → load under import restrictions → register
```

Each stage is an engine hook (`before/after_plugin_load / audit / register`) the host can subscribe to and veto; what plugin authors need is the four points below.

#### 33.9.2 Signing and Trust

```bash
# generate a key pair (keep the private key secret; never commit it)
norpagent plugin-sign --gen

# sign a plugin entry file (writes a <file>.sig sidecar, or fills manifest.signature)
norpagent plugin-sign my_plugin.py --key <private-key-hex>
```

- Signed object: the **SHA-256 of the entry file bytes**; edit the entry file and you must re-sign;
- Trust model: built-in official public key + user-configured `plugin_trusted_keys`;
- Default policy (R-020): **unsigned plugins get a warning, not a block**; `signature_required` (the high-security tier) demands a trusted signature;
- **An invalid signature (file and signature disagree) rejects the load** — fix it by re-signing, or remove the stale signature block to load as unsigned.

#### 33.9.3 Audit and Import Restrictions

| Config | Values | Effect on authors |
|---|---|---|
| `plugin_security_audit` | `off / warn / block` | `block` rejects dangerous calls (subprocess, privilege escalation, reflection bypass, ...); a trusted signature relaxes it to `warn` |
| `plugin_security_import_restrict` | `off / safe / strict` | `safe` blocks `subprocess / ctypes / socket / pickle` etc.; `strict` allows only a whitelist |
| `plugin_security_require_permissions` | bool | when on, the manifest must declare `permissions` |

Trusted relaxation: the audit level drops to `warn`; import restrictions follow the config (trust does not alter them).

#### 33.9.4 Process Isolation

```python
ISOLATION = "process"    # or manifest: "isolation": "process"
```

- the plugin's code exists only in the host child process (JSON-lines RPC); zero execution risk in the main process; crashes auto-restart and reload;
- hooks are limited to 5 seconds; tool calls relay over RPC;
- when to use: untrusted input, heavy capabilities such as `subprocess`, stability isolation;
- note: under process isolation **`setup(api)` registration is not supported** (plugin code is not in the main process, so the registration surface is unreachable; a warning is recorded at load). The tool and hook surfaces work unchanged.

### 33.10 Dependencies and Versions

```python
PLUGIN_REQUIRES = ["other-plugin"]        # other plugins (checked by name among enabled + loaded)
PLUGIN_MIN_NORPAGENT = "2.1"              # minimum framework version
```

Package form:

```json
{"requires": ["other-plugin"], "min_norpagent": "2.1"}
```

Validation happens before registration; unmet requirements reject the load with the reason recorded (e.g. `requires norpagent >= 99.0 (current: 2.0.1)`).

### 33.11 Complete Tutorial: A Weather Plugin from Zero to Release

#### 33.11.1 Step 1: Tool + Hook + State

```python
# my_plugins/weather_plugin.py
PLUGIN_NAME = "Weather Plugin"
PLUGIN_VERSION = "1.0.0"
PLUGIN_PUBLISHER = "your-name"
PLUGIN_DESCRIPTION = "Query city weather; greet on task start."

TOOLS = [{
    "type": "function",
    "function": {
        "name": "weather",
        "description": "Current weather for the given city.",
        "parameters": {"type": "object",
                       "properties": {"city": {"type": "string"}},
                       "required": ["city"],
                       "additionalProperties": False},
    },
}]

APPROVAL_HINTS = {"weather": {"approval": "none", "risk": "L0"}}


def execute(tool_name, args, ctx):
    if tool_name == "weather":
        ctx.storage["queries"] = ctx.storage.get("queries", 0) + 1
        ctx.logger.info(f"weather query: {args.get('city')}")
        return f"{args.get('city')}: sunny, 25C"       # swap in a real API
    return None


def on_task_start(prompt, ctx):
    ctx.logger.info(f"new task: {prompt[:50]}")


def before_step(step, messages, ctx):
    return None                                     # no rewrite
```

#### 33.11.2 Step 2: Add setup (Service + Command + Settings)

```python
PLUGIN_CAPABILITIES = ["tools", "hooks", "events", "services", "cli", "settings"]


def setup(api):
    api.provide("weather.stats", {"queries": 0})
    api.register_cli_command("weather-stats", lambda argv: "ok",
                             help="weather plugin statistics")


def on_load(ctx):
    ctx.storage.setdefault("queries", 0)


def on_unload(ctx):
    ctx.logger.info(f"unloaded after {ctx.storage.get('queries', 0)} queries")
```

#### 33.11.3 Step 3: Package Shape + Declarations

```
weather_pkg/
├─ manifest.json
├─ plugin.py
└─ api_client.py
```

```json
{
  "name": "weather-pkg",
  "version": "1.0.0",
  "publisher": "your-name",
  "description": "package-shape weather plugin",
  "entry": "plugin.py",
  "isolation": "inproc",
  "capabilities": ["tools", "hooks", "events", "services", "cli", "settings"],
  "requires": [],
  "min_norpagent": "2.1"
}
```

#### 33.11.4 Step 4: Sign

```bash
norpagent plugin-sign my_plugins/weather_plugin.py --key <private-key-hex>
norpagent plugins list --plugin-dir my_plugins      # confirm signature: trusted
```

#### 33.11.5 Step 5: The Test Checklist

- [ ] `norpagent plugins list --plugin-dir ...`: loaded, correct tool/hook counts, no warnings;
- [ ] tool call: the model can call it and the result is as expected;
- [ ] hooks fire: logs / counters / rewrites behave as designed;
- [ ] unload then reload: no duplicate subscriptions, no leftover registrations;
- [ ] engine run: `npa(plugins=[...])` and one full task.

### 33.12 Debugging and Troubleshooting

#### 33.12.1 PluginInfo Field Guide

| Field | Meaning | Troubleshooting note |
|---|---|---|
| `enabled` | loaded or not | when `False`, read the first line of `error` |
| `error` | rejection reason | signature / audit / permissions / setup / dependencies |
| `warnings` | non-blocking warnings | unsigned, setup skipped under process isolation, ... |
| `signature_status` | `trusted / untrusted / unsigned / invalid / unavailable` | `invalid` = file and signature disagree |
| `isolation` | `inproc / process` | mismatch means checking ISOLATION / manifest / host config |
| `audit_issues` | AST findings (with line numbers) | critical findings under `block` reject the load |
| `diagnostics` | runtime error records (hook / error / count / time) | the first place to look for silently failing hooks |
| `counts` | hook / tool call counters | verify "was it called" and "how many times" |

#### 33.12.2 Common Issues

| Symptom | Cause | Fix |
|---|---|---|
| plugin not listed | directory not configured / `__init__.py` is skipped | check the plugin dirs config and the file name |
| `signature verification failed` | signature disagrees with the file | re-sign, or remove the stale block |
| `security audit blocked` | dangerous pattern under `block` | adjust the code, or gain trust via a signature (audit relaxes to warn) |
| `import blocked` | import restrictions (safe / strict) | use safe modules, or have the host adjust the tier |
| `missing permission declarations` | permissions required but absent | add `permissions` to the manifest |
| `setup() failed: PluginCapabilityError` | called an undeclared capability | add it to `PLUGIN_CAPABILITIES` / `capabilities` |
| `requires norpagent >= ...` | framework too old | upgrade, or lower the declaration |
| `missing plugin dependencies` | dependency not loaded | load the dependency first |
| hook seems "never called" | wrong signature arity / (legacy) silent exception | check the 33.5 tables; inspect `diagnostics` (exceptions are always reported now) |
| tool blocked by approval | no `APPROVAL_HINTS` and the host master switch is on | declare `approval: "none"` for read-only tools |
| process-isolated setup does nothing | isolation has no registration surface | switch to `inproc`, or move the logic into tools / hooks |
| Web panel shows "failed" | see the error line | work through the rows above |

#### 33.12.3 CLI and Web Tools

```bash
norpagent plugins list --plugin-dir ./my_plugins     # full table (failures / disabled / warnings visible)
norpagent plugins list --plugin-dir ./my_plugins --plugin-disabled x  # simulate a disable
norpagent plugins run <command> [args...] --plugin-dir ./my_plugins   # run a plugin command
```

Web panel (Settings -> Plugins): full status badges, error / warning lines, enable & disable, uninstall (confirmed), upload-and-install (.py), directory management and reload.

### 33.13 Migration Guide (Existing Plugins -> norpagent)

Existing plugins migrate **with zero changes**: load them as they are.

| Item | Compatibility |
|---|---|
| module constants | `PLUGIN_NAME / VERSION / PUBLISHER / DESCRIPTION` recognized as-is |
| `TOOLS` + `execute(tool_name, args, ctx)` | recognized as-is |
| the 16 hook signatures | parameter-by-parameter alignment (`on_task_stopped` supports both the 1-arg and 2-arg forms) |
| `ctx.logger` / `ctx.storage` | fully provided (the missing-field problem is fixed) |
| `on_usage_update` | both the legacy keys (`input_tokens` etc.) and the kernel keys are provided |
| pass-through idioms (`return messages / args / result`) | normalized to "no rewrite", never shadowing other plugins |
| `APPROVAL_HINTS` | works as-is |
| `ISOLATION = "process"` | works as-is (entry constant read statically via AST) |

After migration, consider adding `PLUGIN_CAPABILITIES` (if the setup surface is used), a signature, and manifest metadata.

### 33.14 Release Checklist

- [ ] the entry file loads standalone (import smoke test, no side effects on import);
- [ ] metadata complete (name / version / publisher / description);
- [ ] `norpagent plugins list` shows no warnings and no errors;
- [ ] tools / hooks / registration surface verified per the 33.11.5 checklist;
- [ ] signed (`.sig` or manifest.signature) with the entry file unchanged afterwards;
- [ ] unload / reload clean (`diagnostics` empty of exceptions);
- [ ] heavy capabilities (e.g. `subprocess`): choose `ISOLATION="process"` or tell users to relax import restrictions;
- [ ] distribution notes list the public key (users add it to `plugin_trusted_keys` for trust).

---

## Chapter 34 Settings Store, White-box and Evolution Loop (v2.2.0)

> Anchor: `#chapter-34-settings-store-white-box-and-evolution-loop-v220`

### 34.1 Scope

This chapter covers the developer-facing surface of the v2.2.0 rollout (2026-09-12, Trinity Architecture Book v1.0): the settings source of truth (full moving-point catalog + four-layer inheritance + three channels), white-box traversal, the deepened evolution loop (proposals / breaker / 2A-2C evolvers), the meta-framework and product-state entries, runtime CNB hot mount, and Frontend V2 with the shared trilingual i18n core.

### 34.2 Settings store (`norpagent.settings`)

- **Full catalog**: eleven domains (model / loop / tools / memory / neural / security / plugins / multimodal / evolution / frontend / runtime); each item carries key, title, category, type, default, description, evolvable/locked flags, danger level, three-view visibility and an optional runtime bridge key (`config_key`).
- **Registration**: `register_kernel_schema()` (idempotent), `ensure_schema()` (kernel + evolution registries in one call; shared by Web / CLI / unbox), `schema_view()` (merged DB rows + extended metadata; the single source for panel rendering, validation and export).
- **Four-layer inheritance**: `global > profile > session/task > temp`; "empty = inherit from the upper layer". API: `set_scoped / get_scoped / delete_scoped / resolve / layers / all_resolved`; every item is queryable in three states (default / inherited-with-source / explicit-with-time-and-actor).
- **Mirror bridge**: `mirror_config_to_store(cfg)` / `apply_store_to_config()` / `config_patch_for_key(key)`; bridging applies to the global layer only; secret items never enter the store (they stay on the existing DPAPI path).
- **Audit & export**: `audit_tail(n)`; `export_json() / import_json()` (schema + values + audit tail).

### 34.3 `norpagent settings` CLI (three channels, one source)

```bash
norpagent settings list --category model
norpagent settings get loop.max_steps
norpagent settings set model.temperature 0.6        # schema-validated; bridged to the runtime config
norpagent settings set ui.theme dark --scope temp   # scoped layers stay inside the store
norpagent settings reset loop.max_steps
norpagent settings export settings.json
norpagent settings import settings.json
norpagent settings audit 50
norpagent settings schema
```

Validation covers enum membership, numeric ranges and booleans (exit code 2 with a clear reason on failure); the Web panel, the REST API and this CLI read and write the same store.

### 34.4 White-box traversal (`norpagent.whitebox`)

`overview(engine)` renders the environment tree (`slots / hooks / cnb / evolution / frontend / recovery`); every environment item exposes the quadruple: visible (`describe`), swappable (`change`), configurable (`settings` keys), traceable (`audit` tails). REST: `GET /api/whitebox/overview`; the console "White-box overview" page renders it.

### 34.5 Evolution loop (`evolution.proposals` / `evolution.engines`)

- **ProposalBoard**: `create -> decide -> execute -> run`; states `proposed / awaiting / approved / rejected / applied / failed / paused`; checkbox scheme decides human vs auto approval; a rollback plan is captured before applying and executed automatically on failure (config old-value restore / code hotswap rollback / memory copy retention / skill registry rollback) with circuit-breaker counting.
- **CircuitBreaker**: `evolution.breaker_threshold` (default 3) and `evolution.breaker_auto_pause` (default on); state persists at `evolution.breaker.<point>.state`; `resume(point)` from the console.
- **Evolvers**: `MemoryEvolver` (dedup + soft delete with restorable copies), `SkillEvolver` (registration + `.fspack` archive under `~/.norpagent/skills/`), `ConfigEvolver` (only items marked `evolvable`; locked items are refused by the kernel and audited), `CodeEvolver` (proposal wrapper over the hotswap pipeline).
- **Runtime hardening (2026-09-12)**: `hotswap.verify_active` / `activate(health=..., revert_fn=...)` (post-activation check + auto revert) / `ProposalBoard.health_sweep()` (active-version sweep, also run once by `bootstrap()`); see §32.9;
- **REST** `/api/evolution/proposals`: GET (proposals + breakers + pending); POST actions `run / decide / execute / breaker_resume / memory_plan / memory_apply / memory_restore / memory_forgotten / skill_candidates / skill_apply / config_tune`.

### 34.6 Meta-framework and product-state entries

- `norpagent.core`: the four constructs (`ArchLayer / Registry / EventBus / resolve_address`) + the registration trio (`register_slot / register_layer / register_hook`) + the bare assembly path (`install_core()` + `build_embedded_preset()`).
- `norpagent.farstars_app`: the product-state entry implementation; `norpagent.unbox` forwards for compatibility; `norpagent unbox` mounts all built-in tools by default (`tools: "all"`).

### 34.7 CNB runtime hot mount

```python
import norpagent as np

np.remount(cnb={"cnb": True, "node_id": "atom-x", "port": 17901,
                "parent": "http://127.0.0.1:17800"})   # mount while running (R-025: the port must be configured)
np.remount(cnb={"tree": "tree.json"})                  # runtime reshape: diff-applies a new explicit definition (§30.19)
np.remount(cnb=False)                                  # detach while running (engine stays up)
```

Replacement semantics shut the old adapter down first; mounting continues on a background thread and never blocks the caller. With the `tree` shape, an already-mounted same-mode tree is diff-reshaped instead (`rebuild=true` forces a full rebuild; see §30.19.4). For scripted receipts use `from norpagent.cnb.engine import remount_cnb` with `wait=<seconds>`.

### 34.8 Frontend V2 and the shared i18n core

- **Settings view**: left tab rail + right pane; three perspectives (product / framework / meta-framework, persisted as `ui.console_view`); per-item hover explanations; source chips and one-click reset; master-switch gating via `enable_when` (memory / safety / plugins / multimodal / CNB; direct multimodal routing greys out service URLs and keys); danger confirmations; JSON advanced mode in the framework/meta views.
- **Console**: "White-box overview" and "Proposal center" tabs (pending cards with approve / reject / execute, breaker resume, memory scan, skill candidates).
- **Shared i18n** (`/assets/i18n.js`): one language set (`zh_CN / zh_TW / en`), one storage key (`np_lang`), API `get() / set(lang) / onChange(fn) / t(key) / register(dicts)`; legacy keys migrate automatically; the main frontend, the orbit console and the FLOW page share the state (including cross-tab storage sync).
- **Chat & composer**: batch-clear / clear-all sessions (`POST /api/sessions/clear`); inline mode / model / workspace controls with a directory picker (`/api/fs/list`).

### 34.9 Acceptance

`test/test_v22_suite.py` (65 checks) green; the M4.5 suite extended (J16-J23 / K11-K14) and green; minimal kernel 147 / evolution 49 / CNB slots 51 / plugins 100 and the headless-browser frontend smoke all green; version numbers unified to 2.2.0.
**2026-09-12 feedback round additions**: `test/test_cnb_tree_suite.py` (56 checks, explicit neural-tree definitions) and `test/test_evo_hardening_suite.py` (19 checks, evolution runtime hardening) all green; M4.5 219 / v2.2 65 / minimal kernel 147 / evolution 49 / CNB family (60 / 44 / 36 / 13 / 57 / 12 / 51 / 32) re-run green.

---

### 34.10 2026-09-12 Feedback-Round Additions (version policy / nasyncio / hardening / tree definitions)

| Item | Location | Note |
|---|---|---|
| version policy | this manual's header + all active documents | active documents use the current release as the code baseline (that chapter was written at **2.2.0**; the present baseline is **2.2.1**); historical revision numbers indicate their own era only; archived documents stay as-is |
| asyncio and nasyncio coexist | §4.7 + Chapter 19 FAQ | the standard `asyncio` and the self-developed `norpagent.nasyncio` do not conflict and can coexist in one process (not depending on it means no takeover) |
| evolution runtime hardening | §32.9; `evolution/hotswap.py` / `evolution/proposals.py` | `verify_active` / `activate(health=...)` auto-revert / `health_sweep` / `bootstrap` startup sweep |
| explicit CNB tree definitions | §30.19; `cnb/tree.py`; `norpagent tree validate|show|up` | no preset shape; three sources; item-by-item required-parameter errors; both assembly shapes; remount reshape / watched reshape / auto-reconcile; npa startup config errors never block startup |

Verification: `test/test_cnb_tree_suite.py` 56 and `test/test_evo_hardening_suite.py` 19 green; M4.5 219 / v2.2 65 / minimal kernel 147 / evolution 49 / CNB family (60 / 44 / 36 / 13 / 57 / 12 / 51 / 32) re-run green.

## Appendix D Glossary



| Term | Definition |
|---|---|
| Address Function | the framework's core abstraction: filling a slot value with an "address" (module path / factory / instance) mounts it; not filling uses the default |
| Slot | a replaceable component position; `npa(...)`'s keyword-argument names are slot names |
| Hot-pluggable slot table | `register_slot()` registers custom slots at runtime; registration plugs into the full assembly / validation / hot-replacement pipeline |
| Minimal kernel | only four things in the whole framework are non-replaceable: ArchLayer, the address resolver, Registry, EventBus |
| String-address semantics | the four string interpretation modes `address` / `name` / `name_or_address` / `literal` |
| Extra config clause | the `;key=value` pairs after an address, injected into the factory's `config` parameter |
| defer_factory | a slot factory deferred to the engine assembly phase (used by agent_runtime) |
| Hot mount (remount) | replacing a slot implementation while running, no process restart |
| nasyncio | the self-developed async-IO core (no standard-asyncio dependency), the default event-loop implementation |
| LoopRuntime | the event-loop system's protocol interface (start / stop / submit / interrupt ...) |
| Hook | a named event of an execution structure; subscribable / rewritable (mutating) / vetoable (HookVeto) |
| HookLayer | hook grouping (9 standard layers + custom layers + the dynamic layer) |
| HookVeto | the one-vote-veto exception thrown by mutating hooks; the runtime wraps up safely per the execution point's semantics |
| Registry | the name → component mapping center; everything is a registered item |
| EventBus | the inter-component event channel; copy-on-write + lock-free iteration |
| Preset | declarative assembly: the default combination of slots when unfilled (six built-in modes) |
| Protocol | a component's interface contract (ModelProvider / Tool / SessionManager / Sandbox ...) |
| Sandbox | the isolation boundary for tool execution (subprocess / pooled / isolated_python) |
| PTC | Programmatic Tool Composition: the model generates Python code composing multi-step tool calls |
| FTS5 | the SQLite full-text index engine, the context store's underlying storage |
| Snapshot | a serialized archive of system state (architecture slots + runtime params + WebUI settings) |
| Last known-good snapshot | the good version auto-marked after a 30-second post-startup health window; the rescue CLI's one-step restore target |
| Crash rescue (Rescue) | `norpagent-rescue`: the pure-standard-library CLI that can roll back snapshots even when the main program cannot start |
| Safe Mode | `npa(safemode="on")`: loads only the minimal kernel, skips all plugins |
| Human Rescue | manual takeover when the model fails: `norpagent-rescue tools / tool-call / manual / serve` pass args by hand to every tool and read raw results |
| SafetyKit | the security-policy suite installed by `norpagent.safe()` (approval / network / plugins / protection APIs) |
| Plugin security pipeline | the full plugin-loading flow: signature → audit → import restrictions → registration |
| FLOW | module-flow orchestration: a visual canvas wired to the real registry (node + beam topological execution) |
| File-as-module | dragging in .py / .json / .yaml registers it as a canvas module (.py goes through the plugin security pipeline) |
| Frontend module (FE) | .html / .js / .ts frontend extensions loadable on the `/flow` page |
| SSE backpressure | per-connection bounded buffer; slow clients drop events, not memory (three hot-changeable policies) |
| Copy-on-write (COW) | immutable subscriber-table snapshots + reference replacement; lock-free emit iteration |

---

## Appendix E 29-Hook Event Payload Quick Reference

> Each hook's `payload_keys` are its event-payload fields; mutating hooks' return
> semantics in 9.3 and `test/docs/hooks.md`.

### L1 Runtime Lifecycle

| Hook | Mutating | payload_keys |
|---|---|---|
| `on_agent_init` | - | `preset` |
| `on_agent_shutdown` | - | `preset` |

### L2 Task Lifecycle

| Hook | Mutating | payload_keys |
|---|---|---|
| `on_task_start` | - | `task_id`, `session_id`, `preset`, `user_input` |
| `on_task_done` | - | `task_id`, `session_id`, `content`, `steps`, `context` |
| `on_task_error` | - | `task_id`, `error` |
| `on_task_stopped` | - | `task_id`, `reason` |
| `on_task_timeout` | - | `task_id`, `timeout`, `kind` |

### L3 Input Pipeline

| Hook | Mutating | payload_keys |
|---|---|---|
| `before_input` | ✅ | `task_id`, `user_input`, `session_id`, `params` |
| `after_input` | - | `task_id`, `user_input`, `session_id` |
| `on_user_input_required` | - | `question`, `default` |

### L4 Session & History

| Hook | Mutating | payload_keys |
|---|---|---|
| `before_session_create` | ✅ | `session_id`, `title`, `params`, `task_id` |
| `after_session_create` | - | `session_id`, `title`, `task_id` |
| `before_message_append` | ✅ | `session_id`, `message`, `task_id` |
| `after_message_append` | - | `session_id`, `message`, `task_id` |

### L5 Message Assembly

| Hook | Mutating | payload_keys |
|---|---|---|
| `before_build_messages` | ✅ | `system_prompt`, `session_id`, `step`, `task_id`, `tool_names` |
| `after_build_messages` | ✅ | `messages`, `system_prompt`, `step`, `task_id` |

### L6 Steps

| Hook | Mutating | payload_keys |
|---|---|---|
| `before_step` | ✅ | `task_id`, `step`, `messages`, `context`, `params` |
| `after_step` | - | `task_id`, `step`, `content`, `tool_calls` |

### L7 Model Calls

| Hook | Mutating | payload_keys |
|---|---|---|
| `before_model_call` | ✅ | `task_id`, `step`, `messages`, `tool_schemas`, `params` |
| `after_model_call` | ✅ | `task_id`, `step`, `output` |
| `on_reasoning` | - | `task_id`, `content`, `stream` |
| `on_content` | - | `task_id`, `content`, `stream`, `final` |
| `on_event` | - | `event_type`, `data`, `task_id` |
| `on_usage_update` | - | `task_id`, `input`, `output`, `total` |

### L8 Tool Calls

| Hook | Mutating | payload_keys |
|---|---|---|
| `before_tool_call` | ✅ | `task_id`, `tool_name`, `args`, `context` |
| `after_tool_call` | ✅ | `task_id`, `tool_name`, `args`, `result`, `success`, `context` |
| `on_tool_error` | - | `task_id`, `tool_name`, `error`, `args` |

### L9 Result Finalization

| Hook | Mutating | payload_keys |
|---|---|---|
| `before_result` | ✅ | `task_id`, `result` |
| `after_result` | ✅ | `task_id`, `result` |

> The plugin-loading pipeline has 8 more hooks (`PLUGIN_PIPELINE_LAYER`:
> `before_plugin_load` / `after_plugin_register` etc.), see 11.4; FLOW
> orchestration additionally has `flow.*` events (20.5).

---

## Appendix F Frontend-Backend Communication Quick Reference

> "Frontend" = the user-interface side (Web UI / console / custom frontends /
> external processes); "backend" = inside the framework process (engine / registry /
> event bus / tools).

### F.1 Communication-Channel Overview

| Channel | Direction | Transport | Purpose | Section |
|---|---|---|---|---|
| HTTP REST | frontend → backend | TCP (default 127.0.0.1:8787) | Web UI: submit tasks / query / config | 22.2 |
| SSE stream | backend → frontend | HTTP long connection | streaming output / live task status | 22.3 |
| event bus (in-process) | any component ↔ any component | process memory (copy-on-write + lock-free iteration) | decoupled communication for hooks / UI / plugins / engine | 9.5 / 27.2 |
| CLI args and stdin/stdout | human ↔ framework | command line | REPL / single task / admin commands | 13 / Appendix G |
| HTTP API (rescue) | operator ↔ rescue environment | TCP (default 127.0.0.1:8799) | manually operate tools when the model is down | 15.6.2 |
| files (snapshots / rollback target) | framework ↔ disk | JSON files | crash rescue / Undo-Redo | 15.2 / 15.4 |
| child-process pipes | framework ↔ sandbox children | stdio | tool-execution isolation (exec_cmd / run_python) | 8.2 / 24.2 |
| self-pipe socketpair | loop thread ↔ external threads | in-process fd | nasyncio cross-thread wakeup | 24.2.1 |
| IPC (vision / plugin isolation) | main process ↔ host child | inter-process (RPC) | plugin process isolation, vision assistant | 11.7 |

### F.2 Web Frontend ↔ Backend (HTTP REST)

Default port 8787 (`--port` / `config={"web":{"port":N}}`). Endpoints:

| Method + path | Description |
|---|---|
| `GET /` | main page (front.html) |
| `GET /flow` | module-flow canvas page |
| `GET /farstars` | FarStars star-track console (norp-farstars.html; aliases `/farstars.html`, `/norp-farstars.html`) |
| `POST /chat` | submit a task: body `{"text": "...", "session_id": "..."}` |
| `GET /api/status` | engine status / preset / tool count |
| `GET /api/tools` | tool schema inventory |
| `GET /api/sessions` | session list |
| `GET /api/history?session_id=...` | session history |
| `GET /api/config` / `POST /api/config` | read / save config |
| `GET /api/models` | available models and credential status |
| `POST /api/model` | switch the model |
| `GET/POST /api/snapshots` | snapshot timeline / manual snapshot |
| `POST /api/undo` / `POST /api/redo` / `POST /api/rollback` | work rollback |
| `POST /api/upload` | file upload (restricted extensions) |
| `POST /api/cancel` | cancel the in-flight task |
| `POST /api/vision` | image understanding (v0.9.9 multimodal, Chapter 29) |
| `POST /api/tts` | text → speech wav (v0.9.9 multimodal) |
| `POST /api/stt` | speech wav → text (v0.9.9 multimodal) |
| `POST /api/beep` | notification tone wav (v0.9.9 multimodal) |
| `GET /api/plugins` | plugin table (full state: failure reasons / disabled / signature / isolation / warnings / diagnostics) |
| `GET/POST/DELETE /api/plugins/dirs` | plugin directory query / add / remove |
| `POST /api/plugins/reload` | reload all plugins |
| `POST /api/plugins/toggle` | enable / disable one plugin (persisted) |
| `POST /api/plugins/remove` | uninstall one plugin (deletes the file; path-restricted) |
| `POST /api/plugins/upload` | upload-and-install a single-file plugin (.py, base64) |

Detailed response formats: 22.2 (REST API summary).

### F.3 SSE Stream (backend → frontend)

`GET /api/events` opens an SSE long connection; event names map one-to-one to the
in-process events:

| SSE event | Trigger | Main fields |
|---|---|---|
| `on_task_start` | task start | task_id, user_input |
| `on_reasoning` | reasoning increments | content |
| `on_content` | body-text increments | content, final |
| `on_tool_call` | tool call | tool_name, args |
| `on_task_done` | task finished | task_id, content, steps |
| `on_task_error` / `on_task_stopped` | abnormal / stopped | task_id, error/reason |
| `on_usage_update` | token usage | input, output, total |

> Implementation notes: bounded SSE queue + batched flush (14.3 / 23.2); the page
> JS lives in `front.html` (5.4 / 22.5).

### F.4 In-Process Event Bus (GeneralEventBus)

All components (engine / UI / plugins / hooks) communicate over the event bus in
**the same process**: `emit` (broadcast) / `intercept` (mutating dispatch + veto) /
`emit_all` (collect return values); subscribe with `subscribe` / `once` / `wait`.
Payload keys of the 29 standard hook events: Appendix E; external-script
integration: Chapter 28.

### F.5 Command Line (human ↔ framework)

| Scenario | Command |
|---|---|
| start the Web UI | `norpagent --mode standard --ui web --port 8787` |
| console REPL | `norpagent --mode standard` (when ui=console) |
| single task | `norpagent --mode ptc --prompt "..."` |
| programming equivalent | `npa()` / `npa.submit(text)` |

See Chapter 13 and Appendix G.

---

## Appendix G All Commands Quick Reference

### G.1 The norpagent Main Command

```bash
norpagent --list-modes                                   # list preset modes
norpagent --mode <name>                                  # interactive REPL (console frontend)
norpagent --mode <name> --prompt "<text>"                # single task
norpagent --mode-file <file.py>                          # custom mode file
norpagent --mode standard --ui web --port 8787           # Web UI
norpagent --model <registered-name>                      # override the model
norpagent --model-name <remote-model> --base-url <endpoint> --api-key <key>
norpagent --session sqlite --call-timeout 120            # session backend / call timeout
norpagent --plugin-dir ./dir [--plugin-isolation auto|inproc|process]
norpagent --safe basic|standard|high [--safe-hooks]      # security policy
norpagent --safe-mode                                    # safe mode (minimal kernel)
norpagent unbox                                          # product-distribution entry: one-command ready-to-use software (Chapter 31)
norpagent unbox --smoke                                  # product self-check (assemble -> health check -> exit)
norpagent unbox --cnb --cnb-port 17811                   # product carrying CNB (port required, R-025)
norpagent plugin-sign --gen                              # generate a signing key pair
norpagent plugin-sign <plugin.py> --key <privkey-hex>    # sign a plugin file
norpagent plugins list --plugin-dir ./dir                # plugin table (failures / disabled / warnings visible)
norpagent plugins run <command> [args...] --plugin-dir ./dir  # run a plugin-contributed CLI command (33.8)
norpagent plugins list --plugin-dir ./dir --plugin-disabled <name>  # simulate the disabled list
```

### G.2 norpagent-rescue Snapshot Commands (pure stdlib)

```bash
norpagent-rescue list                     # timeline (★ = last known-good snapshot)
norpagent-rescue show <id> [--last-good]  # inspect a snapshot (sensitive keys redacted)
norpagent-rescue rollback <id>            # roll back to the given snapshot
norpagent-rescue rollback --last-good     # roll back to the last known-good snapshot
norpagent-rescue mark-good <id>           # mark a snapshot "known good"
norpagent-rescue prune --keep N           # keep only the most recent N snapshots
```

### G.3 norpagent-rescue Human-Takeover Commands (framework must be importable)

```bash
norpagent-rescue tools [--workspace WS] [--tools A,B] [--plugin-dirs D1,D2]
norpagent-rescue tool-call <tool> --args '<json>' [--timeout N] \
    [--workspace WS] [--tools A,B] [--plugin-dirs D1,D2]
norpagent-rescue manual [--workspace WS] [--tools A,B] [--plugin-dirs D1,D2]
norpagent-rescue serve [--port 8799] [--host 127.0.0.1] [--token T] \
    [--workspace WS] [--tools A,B] [--plugin-dirs D1,D2]
```

Shared options: `--workspace` (file-tool root), `--tools` (comma-separated
registered tool names or `pkg.mod:attr` module addresses), `--plugin-dirs`
(comma-separated plugin directories), `--context-db` (context-store path).
Manual console built-ins: `/tools` `/help` `/exit`.

### G.4 Common Combinations

```bash
# model dead: operate the tools by hand
norpagent-rescue tools
norpagent-rescue tool-call echo --args '{"text":"ping"}'
norpagent-rescue serve --port 8799 --token my-secret

# custom tools + plugin tools, all manually operable
norpagent-rescue serve --tools myapp.tools:create --plugin-dirs ./my_plugins

# main program cannot start: roll back to the last known-good snapshot and restart
norpagent-rescue list
norpagent-rescue rollback --last-good
norpagent --safe-mode        # if it still won't start, use safe mode

# startup-failure hints (the CLI prints these automatically)
#   1) norpagent --safe-mode
#   2) norpagent-rescue rollback --last-good
#   3) restart (the rollback target is consumed automatically)
#   4) model dead -> norpagent-rescue tools / manual / serve
```

---

## Appendix H All Functions and Structures Quick Reference

> Grouped by module; "→" denotes the return value. Ellipses mean optional
> parameters; authoritative signatures are `inspect.signature` and the source.
> Quick reference only; see the referenced sections for details.

### H.1 Top Level: `import norpagent as npa`

| Symbol | Signature summary | Description | Section |
|---|---|---|---|
| `npa()` | `launch(**slot-args) → NorpEngine` | start the engine (module-as-entry) | 6 |
| `npa.stop()` | `() → bool` | lifecycle poll: True = should exit | 6 |
| `npa.submit(text, session_id=None)` | `→ RunResult` | submit a task to the current engine | 6 |
| `npa.remount(**slot_values)` | `→ NorpEngine` | hot-mount any slot at runtime | 3.7 |
| `npa.nasyncio(address=None, **config)` | `→ LoopRuntime` | event-loop architecture function | 4 |
| `npa.shutdown()` / `npa.current()` | — | shut the engine down / get the current engine | 6 |
| `npa.undo()` / `npa.redo()` / `npa.rollback(id)` | `→ dict` | work rollback | 15.2 |
| `npa.snapshot_system(**kw)` | `→ dict` | manual snapshot | 15.2 |
| `npa.list_snapshots()` / `npa.mark_good_snapshot(id)` | — | snapshot management | 15.2 |
| `npa.safe(reg, level=..., hooks=..., config=...)` | `→ SafetyKit` | mount the security suite | 10 |
| `npa.Registry()` / `npa.EventBus()` / `npa.Preset(...)` | kernel structures | see H.2 | 27 |
| `npa.install_defaults(reg)` / `npa.install_core(reg)` | — | built-in component assembly | 2.3 |
| `npa.register_slot(spec, replace=False)` / `npa.unregister_slot(name)` | — | slot-table hot plug | 3.8 |
| `npa.snapshot_slots()` / `npa.is_builtin_slot(name)` | — | slot-table queries | 3.8 |

### H.2 Kernel Structures (`norpagent.kernel`)

| Structure | Members / methods | Description |
|---|---|---|
| `Registry` | `register_model/tool/session/sandbox/scheduler/ui/plugin/preset/component`; `resolve_*`; `build_session/sandbox/scheduler/component`; `list_*`; `tool_schemas(names=None)`; `validate_preset(p)`; `.bus`; `.hooks`; `.security` | component registration center (9 namespaces) |
| `EventBus` | `subscribe(fn, type=None)` `once(fn, type=None)` `unsubscribe(fn, type=None)` `emit(type, **kw)` `intercept(type, **kw)` `emit_all(type, **kw) → list` `wait(type, timeout=None) → AgentEvent\|None` `subscriber_count(type=None) → int` `has_listeners(type=None) → bool` `clear(type=None) → int` `set_error_logger(cb)` | the general-purpose event bus (27.2) |
| `EventType` | 16 standard event-name enum | 27.2.5 / Appendix E |
| `AgentEvent` | `.type` `.payload` `.ts` `.get(key, default=None)` | 27.2.1 |
| `HookVeto(reason="...")` | one-vote-veto exception (intercept does not catch it) | 9.3 |
| `Preset(name, model, tools, session, sandbox, scheduler, ui, mode, params, components)` | preset declaration | 12 |
| `RunContext` | `.registry .session_manager .session_id .sandbox .scheduler .ui .params .task_id .preset_name .components`; `component(kind)` `context_store` `project_manager` `task_store` `ask_user(q, default)` | per-task environment handle (Ch. 8 / 25.2.3) |
| `AgentRuntime` | `run(user_input, session_id=None, task_id=None, task_params=None)`; `shutdown()`; `.registry .preset .hooks`; overridable: `prepare_input/create_session/append_message/build_messages/call_model/execute_tool_call/finalize_result` | the agent loop (9.6) |
| `RunResult` | `.ok .status .final_content .session_id .steps .error .tool_calls` | task result |

### H.3 The Hook System (`norpagent.hooks`)

| Symbol | Signature summary | Description |
|---|---|---|
| `Hook` | `subscribe(fn, system=None)` `unsubscribe(fn, system=None)` `emit(system=None, **kw)` `intercept(system=None, **kw)` `bind(bus)`; attrs `.name .layer .order .mutating .payload_keys` | standalone hook API (9.2) |
| `BoundHook` | same four methods (no system); same attrs | runtime hook bound to a bus (9.8) |
| `HookLayer(name, order=0, description="")` | `.hook(name, mutating=False, description="", payload_keys=(), order=0) → Hook` `.names()` | custom layer (9.4) |
| `HookSystem(bus, install_standard=True)` | `install_layer(layer)` `define_hook(...)` `hook(name)` `get(name)` `list_hooks()` `list_hook_names()` `layers()` `layer_of(name)`; attribute access `hooks.<name>` | hook view over a bus (9.4) |
| 29 standard hooks | `from norpagent.hooks import before_model_call, ...` | Appendices B / E / 9.8 |
| `get_default_system()` | `→ HookSystem` | default landing of the module-level API |

### H.4 Architecture Layer (`norpagent.arch`)

| Symbol | Signature summary | Description |
|---|---|---|
| `ArchLayer(slot_specs=None, config=None)` | `connect()` `remount(slot, value)` `describe()` `set_default(slot, factory)` `subconfig(slot)` `__getitem__(slot)` `get(slot, default)`; `.config` `.impls` | the slot connector (27.4) |
| `SlotSpec` | fields: `name description protocol default_address string_semantics factory_kwargs examples defer_factory applier remount_rebuild_agent` | slot spec (3.8 / 25.10.2) |
| `resolve_address(address, *, slot)` | `→ implementation object` | address resolution (3.2 / 27.3) |
| `is_address_like(s)` | `→ bool` | pure structural check (27.3.4) |
| `register_slot(spec, replace=False)` | `→ SlotSpec` | slot-table hot plug (3.8) |
| `snapshot_slots()` / `all_slot_names()` / `is_builtin_slot(name)` / `unregister_slot(name)` | — | slot-table queries and unregister |

### H.5 Runtime (`norpagent.runtime`)

| Symbol | Signature summary | Description |
|---|---|---|
| `NorpEngine` | `.async_loop .registry .preset .state .arch_layer`; `submit(text, session_id=None)` `request_stop()` `wait(timeout)` `join()` `shutdown()` | the engine object (6.2) |
| `launch(**kw) → NorpEngine` | assemble and start | 6.1 |
| `remount(**slot_values) → NorpEngine` | hot mount | 3.7 |
| `submit(text, session_id=None)` / `stop()` / `current()` / `shutdown()` / `is_running()` | — | module-level runtime API |

### H.6 Work Rollback and Rescue

| Symbol | Signature summary | Description |
|---|---|---|
| `snapshot_system(**kw) → dict` / `undo()` / `redo()` / `rollback(id)` | snapshot trio | 15.2 |
| `list_snapshots()` / `mark_good(id)` / `last_good_id()` / `set_snapshot_dir(dir)` / `register_snapshot_provider(fn)` | snapshot management | 15.2 / 15.3 |
| `RescueToolEnvironment(workspace_root=None, sandbox="subprocess", session="memory", scheduler="persistent", scheduler_db=None, context_db=None, with_components=True, params=None, extra_tools=None, tools=None, plugin_dirs=None, plugin_config=None)` | `inventory() → list` `call_tool(name, args, timeout=None, params=None) → dict` `close()` | human-rescue environment (15.6.3) |
| `RescueToolAPI(env=None, port=8799, host="127.0.0.1", token=None)` | `start() → int` `shutdown()` `page_html()` | rescue HTTP API (15.6.2) |

### H.7 Plugins (`norpagent.plugins`)

| Symbol | Signature summary | Description |
|---|---|---|
| `PluginSystem(registry, plugin_dirs=None, config=None)` | `load()` `reload(name)` `unload(name)` `status()` `shutdown()` `configure(cfg)` | plugin facade (11.1) |
| `install_plugin_dirs(reg, dirs, config=None) → PluginLoader` | one-shot loading | 11.1 |
| `PluginAPI` (the `setup(api)` facade) | `register_tool / register_slot / register_component / register_model / register_session / register_sandbox / register_scheduler / register_ui / define_hook / subscribe / emit / provide / get / mount_page / register_cli_command / register_settings / get_setting / set_setting` | 33.8 |
| `PluginInfo` | full field set (`enabled / error / warnings / signature_status / isolation / capabilities / requires / diagnostics / counts` ...) | 33.12.1 |
| `PluginLogger` | `debug / info / warn / error` (stdout + log file) | 33.6 |
| `LEGACY_HOOK_NAMES` / `NATIVE_HOOK_NAMES` | the 16-legacy / 29-native hook name lists | 33.5 |
| `PluginCapabilityError` | capability-gate exception (setup calls beyond the declaration) | 33.8.1 |
| pipeline hooks | `PLUGIN_PIPELINE_LAYER` + 8 `before/after_plugin_*` | 11.4 |

### H.8 Built-in Components (`norpagent.builtin`)

| Category | Registered names | Description |
|---|---|---|
| models | `mock` `openai_compat` `anthropic` | 21.1 |
| tools (20) | `echo get_time run_python file_read file_write file_list file_delete exec_cmd web_search web_fetch web_extract_links context_add context_search context_list context_delete project_status task_submit task_list task_status task_cancel` | 21.2 |
| sessions | `memory` `sqlite` | 21.3 |
| sandboxes | `subprocess` `pooled` | 21.4 |
| schedulers | `simple` `persistent` | 21.5 |
| UI | `console` `web` | 5 / 22 |
| components | `context_store=fts5` `project_manager=basic` | 21.6 / 21.7 |

### H.9 Event Loop (`norpagent.nasyncio` / `norpagent.loops`)

| Symbol | Signature summary | Description |
|---|---|---|
| `nasyncio.EventLoop` | `run_forever()` `run_until_complete(coro)` `stop()` `abort_main()` `call_soon_threadsafe(cb)` `create_task(coro)` `create_future()` `call_later(delay, cb)` `close()` | self-developed loop core (24.2.1) |
| `nasyncio.run_coroutine_threadsafe(coro, loop) → Future` | cross-thread coroutine submission | 24.2.4 |
| `LoopRuntime` protocol | `start()` `stop()` `submit(fn)` `run_async(coro)` `interrupt()` `join(timeout)` `is_running()` | 4.2 |
| `NasyncioLoopRuntime(config=None)` | default async_loop-slot implementation | 4.3 |

---

## Appendix I Multimodal Configuration and API Quick Reference

> v0.9.9. Multimodal = vision (image understanding) + sound (TTS read-aloud /
> STT input / notification tone). Everything is implemented on the backend
> (`builtin/ui/multimodal.py`, stdlib only); the browser only captures and plays.
> Details in Chapter 29.

### I.1 Config keys (Settings → Vision API / Sound)

| Key | Default | Section | Description |
|---|---|---|---|
| `vision_enabled` | false | Vision API | enable image understanding |
| `vision_service_url` | "" | Vision API | external vision service URL (protocol in 29.2.3) |
| `tts_enabled` | true | Sound | enable read-aloud |
| `tts_service_url` | "" | Sound | OpenAI-compatible `/audio/speech` (empty = OS native) |
| `tts_service_api_key` | "" | Sound | TTS key (DPAPI-encrypted) |
| `tts_voice` | "" | Sound | voice name (Windows SAPI / OpenAI voice) |
| `tts_rate` | 1.0 | Sound | rate 0.5–2.0× |
| `stt_service_url` | "" | Sound | OpenAI-compatible `/audio/transcriptions` (empty = Windows local) |
| `stt_service_api_key` | "" | Sound | STT key (DPAPI-encrypted) |
| `stt_language` | "en-US" | Sound | recognition language (zh-CN needs a Windows Chinese pack) |
| `sound_notify_enabled` | true | Sound | new-message tone |
| `auto_speak_enabled` | false | Sound | auto-read assistant replies |

### I.2 Endpoints

| Endpoint | Method | Request | Response |
|---|---|---|---|
| `/api/vision` | POST | `{images:[{name,type,data(base64)}], prompt}` | `{ok, descriptions:[{name,description}]}` |
| `/api/tts` | POST | `{text, voice, rate}` | `{ok, audio_base64, mime:"audio/wav"}` |
| `/api/stt` | POST | `{audio(wav base64), mime}` | `{ok, text}` |
| `/api/beep` | POST | `{}` | `{ok, audio_base64, mime:"audio/wav"}` |
| `/api/upload` | POST | `{files:[{name,type,data}]}` | `{files:[{kind:"image"|"text", …}]}` (v0.9.9 images) |

### I.3 OS-native TTS / STT engines

| Platform | TTS | STT | Notes |
|---|---|---|---|
| Windows | SAPI (System.Speech via PowerShell) | SAPI local recognizer (DictationGrammar) | Chinese TTS built in (e.g. Huihui); Chinese STT needs a language pack |
| macOS | `say` (LEI16@22050 → WAV) | — (configure a service) | — |
| Linux | `espeak-ng` / `espeak` | — (configure a service) | clear error when missing |

### I.4 External service protocol (OpenAI compatible)

```text
TTS: POST {tts_service_url}
     {"model":"tts-1","input":text,"voice":voice,
      "response_format":"wav","speed":rate}
     Authorization: Bearer <tts_service_api_key> (optional)

STT: POST {stt_service_url} (multipart/form-data)
     file=audio.wav (16 kHz mono wav), model=whisper-1, language=<stt_language>
     Authorization: Bearer <stt_service_api_key> (optional)
```

---

## Appendix J Central Nervous Bus Quick Reference

> CNB/1.0 multi-instance neural tree: the cortex controls any atom's operation permissions at any level; lower levels only report upward and never control upper levels. Details in Chapter 30; standalone design doc: `NERVOUS_BUS.md`.

### J.1 Levels and Constants

| Constant | Value | Meaning |
|---|---|---|
| `LEVEL_CORTEX` | 0 | the cortex (root, highest level) |
| `LEVEL_DIRECTOR` | 1 | directorate / group level |
| `LEVEL_AGENT` | 2 | agent level |
| `LEVEL_ATOM` | 3 | atom level (default) |
| `LEVEL_MAX` | 63 | level ceiling |
| `DEFAULT_CORTEX_PORT` | 17800 | cortex default bus port |
| `DEFAULT_HOST` | 127.0.0.1 | loopback only by default |

### J.2 Message Types

| Direction | Types |
|---|---|
| uplink (read-only) | `report.register` `report.heartbeat` `report.event` `report.audit` `report.request` `report.deregister` |
| downlink (control) | `cmd.hello` `cmd.ping` `cmd.exec` `cmd.stop` `cmd.reload` `cmd.perm.set` `cmd.perm.grant` `cmd.perm.revoke` `cmd.topology.sync` `cmd.reroot` (parent-chain rescue re-parenting) |

### J.3 Permission Atoms

`file_read` `file_write` `file_delete` `file_list` `process_exec` `process_shell` `network_out` `network_in` `system_info` `plugin_call`

### J.4 CLI Quick Reference

> Since v1.0.7 CNB is kernel-integrated: the primary path is `python -m norpagent.cnb.cli ...` (equivalent to `norpagent ...`, same arguments); the legacy `python -m nervous_bus.cli ...` still works through the compatibility shim. Since v1.0.7 `cortex`/`node` processes assemble a full kernel engine by default (`--bare` returns to the plain nervous shell; `--mode <preset>` / `--model <model>` selectable).

| Command | Description |
|---|---|
| `norpagent cortex --port 17800 --repl` | start the cortex (equivalent to `python -m norpagent.cnb.cli cortex ...` and `python main.py --norp-cortex --port 17800 --repl`) |
| `norpagent node --id norpbot-01 --kind bot --parent http://127.0.0.1:17800 --port 17801 --level 3` | mount a node (equivalent to `python -m norpagent.cnb.cli node ...` and `python main.py --norp-node ...`) |
| `... topo --root <cortex URL>` | view the topology tree |
| `... tree validate\|show\|up --def <definition>` | explicit neural-tree definition: validate / show / start the whole tree (inproc or spawn; no preset shape; §30.19) |
| `... ping --root ... --node <id>` | probe liveness |
| `... exec --root ... --node <id> --action <action> [--args '{}'] [--perm process_exec]` | issue an execution command (action = kernel surface: run_task/status/stop_task/task_records/engine_state/inspect/snapshot/rollback/undo/redo/list_snapshots/mark_good/remount/reload_plugins/stop_engine, see 30.16.3; plus node slot actions slot_list/slot_describe/slot_mount/slot_unmount, see 30.18) |
| `... stop / reload --root ... --node <id>` | stop / reload |
| `... perm --root ... --grant\|--revoke\|--set --target-type node_id\|node_kind\|* --target <target> --perm <atom> [--scope '{}'] [--allows '{}']` | permission control |
| `... reports / audit --root ... [--n 20]` | view reports / audit (reports show the heartbeat's `engine_state`/`active_tasks`/`version`) |
| `... sync --root ...` | cortex broadcasts the topology |

> Universal slots (R-024 / R-025, §30.18): up to 64 slots per node; `slot_list` / `slot_describe` (read-only), `slot_mount` / `slot_unmount` (mutating; rejected while frozen); the complete-instance module `NorpAgentModule` (kind=`norpagent-instance`) is mounted from code (`node.mount_module`); `CnbAdapter` auto-mounts the default slot `norpagent`, and heartbeats carry `slots.count` / `slots.free`.

### J.5 The Cortex Control Endpoint /cnb/ctrl

`POST {cortex URL}/cnb/ctrl` with body `{"op": ...}`:

| op | Key params | Description |
|---|---|---|
| `topo` | — | topology view |
| `nodeinfo` | `node` | node details |
| `ping` / `stop` / `reload` | `node` | probe / stop / reload |
| `exec` | `node` `action` `args` `perm` `path` | execution command |
| `grant` / `revoke` | `target_type` `target` `perm` `scope` | grant / revoke a permission |
| `set` | `target_type` `target` `allows` | overwrite permissions |
| `sync` | — | topology broadcast |
| `sweep` | — | manually run one lost-node sweep + rescue pass (the cortex REPL also has a `sweep` command) |
| `reports` / `audit` | `n` | report / audit records |

Bus endpoints: `POST /cnb/msg` (message delivery), `GET /cnb/health` (health check), `GET /cnb/reports` (report records).

### J.6 Env Vars (Auto-Mount of Ordinary Instances, v1.0.2+)

> Contract: setting `NORP_CNB_NODE` enables auto-mount; `NORP_CNB_MANAGED=1` skips kernel mounting (the upper layer builds its own node in managed mode — no double mounting). Env vars only; config.json is not consulted. Details: §30.8.

| Env var | Default | Description |
|---|---|---|
| `NORP_CNB_NODE` | empty (setting enables) | node id |
| `NORP_CNB_KIND` | `agent` | atom type |
| `NORP_CNB_LEVEL` | `3` | level (must exceed the parent's) |
| `NORP_CNB_PARENT` | `http://127.0.0.1:17800` | parent bus URL |
| `NORP_CNB_PORT` | `17801` | this node's bus port |
| `NORP_CNB_HEARTBEAT` | `5.0` | heartbeat interval (seconds) |
| `NORP_CNB_DESC` | empty | node meta description |
| `NORP_CNB_MANAGED` | unset | `1` = kernel mounting skipped |
| `NORP_CNB_TREE` | empty | neural-tree definition (JSON / PY path or JSON text); the whole-tree shape is carried by it (§30.19) |

Status: `engine.cnb_status` (`not-mounted` / `managed-skip` / `mounting` / `mounted` / `failed` / `stopped` / `config-error` — a config error is explicit, the tree is not loaded and the host keeps running); config / mount error details via `engine.cnb_error`; `engine.cnb` returns the adapter (`status` / `perm_summary`). Cortex downlink surface: `exec` (action whitelist `run_task` / `status` / `stop_task`), `stop`, `reload`, `perm.*` — landing semantics in the §30.8 callback table.

### J.7 Test Commands

```bash
# verified green on 2026-09-05 (v2.0.0); nervous_bus is the compat shim (test files ship with it; commands unchanged)
python -m nervous_bus.test_cnb        # 60 unit/integration self-tests (incl. permission-plane audit T-A0~T-A6)
python -m nervous_bus.test_e2e        # 13 real multi-process end-to-end tests (ROOT auto-located)
python -m nervous_bus.test_deep_tree  # 36 deep-tree regression checks (4-level chain: collapse / convergence / rescue / sweep / permission time-order / heartbeat self-heal / broadcast / cache convergence)
python -m nervous_bus.test_cnb_v200 # 44 v2.0.0 new-capability acceptance checks (mol channel / quarantine freeze / behavior baselines / subpoena evidence)
python -m nervous_bus.test_cnb_slots  # 51 checks: universal slot system (R-024 / R-025: up-to-64 boundary / action conflicts / transactionality / instance module)
python -m nervous_bus.demo            # in-process neural-tree demo
python test/test_cnb_automount.py     # 12 checks: engine NORP_CNB_* auto-mount acceptance smoke (needs PYTHONPATH=src)
python test/test_cnb_kernel_actions.py  # 32 checks: kernel action surface A 21 + B 11 (v1.0.7 new; needs PYTHONPATH=src)
python test/test_cnb_tree_suite.py     # 56 checks: explicit neural-tree definitions (2026-09-12 feedback round; needs PYTHONPATH=src)
```

### J.8 v2.0.0 New Command Surface and Constants (FarStars 远星)

```bash
# quarantine freeze
norpagent freeze   --root http://127.0.0.1:17800 --node dev --reason "quarantine"
norpagent unfreeze --root http://127.0.0.1:17800 --node dev --reason "review passed"
# behavior grading
norpagent behavior --root http://127.0.0.1:17800          # yellow review / black quarantine
# subpoena (level 0 only; bases: confidence_low / vote_tie /
#   evidence_conflict / human_named; tiers 64/128/256/512KB)
norpagent subpoena --root http://127.0.0.1:17800 --node rnd-01 \
    --basis evidence_conflict --tier-kb 128 --approved-by-human
norpagent subpoena_box   --root ... --subpoena-id <id> --destroy   # read-to-burn
norpagent subpoena_purge --root ... [--subpoena-id <id>]            # destroy after use
norpagent subpoena_audit --root ...                                 # issuance trail
# task-molecule acceptance receipts (surface 15 adds task_records)
norpagent exec --root ... --node dev --action run_task --args '{"prompt": "...", "task_params": {"mol_id": "..."}}'
norpagent exec --root ... --node dev --action task_records --args '{"mol_id": "..."}'
```

New downlinks: `cmd.freeze` / `cmd.unfreeze` / `cmd.subpoena` (CNB/1.0
semantic additions). Freeze whitelist: `FROZEN_ALLOWED_ACTIONS`. Subpoena
constants: `SUBPOENA_BASIS` (four bases) / `SUBPOENA_TIERS_KB`
(64/128/256/512) / `SUBPOENA_MAX_KB` (512; above → forced human
adjudication) / `SUBPOENA_ENVELOPE` (`RAW/UNTRUSTED`). Brand:
`norpagent.__brand_cn__="远星"` / `__brand_en__="FarStars"` /
`__display_name__="FarStars（远星）· norpagent"`.

---

## Revision history

> **Version policy (2026-09-12 feedback round)**: this manual and all active documents use the current release **2.2.1** as the code baseline; version numbers in the historical revision notes below indicate the baseline of their time only, not the present state; archived documents (old manuals, historical update excerpts) stay as-is.
>
> **2026-09-12 v2.2.1 defect closure (R-032 / R-033)**: ① **`ask_user` tool restored (R-033)** — the built-in tool set now exposes `ask_user`, so the model itself can ask the user to clarify a requirement / choose an option / confirm a risky operation (previously this existed only as a UI-adapter and kernel approval-chain mechanism, and the active tool set was missing it); registered in the standard / ptc / longrun presets and in both assembly entries (`install_defaults` / `install_core`); ② **token counting includes raw text (R-032)** — when the endpoint returns no usage, the backend estimates input + output from the **raw text** (raw markdown / LaTeX source plus the prompt); previously only the rendered visible output was counted and input was missing, making the reported total systematically low. Estimated numbers carry an `estimated` flag and the UI marks them with a "≈"; when the endpoint reports usage, the server numbers still win. All active version numbers are unified to **2.2.1**.
>
> **2026-09-12 v2.2.1 feedback-round closure (frontend stats basis / bilingual settings / unified scrolling / instant stop / workspace cleanup)**: within the same 2.2.1 release (no new version number) — ① **frontend stats basis**: the always-zero "0 tok" badge in the top-right corner is removed, and the token / speed estimate now includes reasoning (think) and tool-call arguments (tool, via `toolCallTextOf`, excluding tool return values); ② **bilingual settings**: frontend dictionaries `SET_ZH` / `SET_ZH_POINT` cover all 123 non-evolution settings keys (evolution-point titles are composed at runtime), and `settingRowHtml` renders per language (English falls back to the schema original, Simplified Chinese uses the dictionary, Traditional Chinese falls back to Simplified); ③ **back-to-bottom**: a new `.msgs-wrap` wrapper moves the button out of the scroll container `#msgs` so it stays pinned bottom-right; ④ **slide-to-bottom on open**: `slideToBottom()` animates frame-by-frame with easeOutCubic for ~720ms, triggered only when switching / opening a session; ⑤ **unified scrolling (aligned with `duo2.py`)**: a sticky `_userScrolled` flag (10px tolerance) replaces the distance heuristic, and all auto-scrolling converges on the single entry `scrollBottom(force, animate)`; ⑥ **instant stop**: `web.py::_stop_events` keeps a per-session cancel event (`stop_task()` sets it synchronously), while the kernel streaming loop returns partial content on cancel, finalizes as `stopped`, and persists the partial reply; ⑦ **workspace cleanup**: 622 root-level `_*` artifacts moved into `test/`, and this manual's overly long opening revision block moved to the "Revision history" section at the end. The version number stays **2.2.1**.
>
> **2026-09-12 feedback round (unified versioning / asyncio-nasyncio coexistence / evolution runtime hardening / explicit CNB tree definitions)**: ① **unified versioning** — active documents all use **2.2.0** as the code baseline (see the version policy above; stale claims such as NERVOUS_BUS.md's 2.0.0 are corrected); ② **asyncio and nasyncio coexist** — the standard `asyncio` and the self-developed `norpagent.nasyncio` **do not conflict and can be used side by side in the same process** (not depending on it does not mean taking it over; see §4.7 and the Chapter 19 FAQ); ③ **evolution runtime hardening** — post-activation health check with automatic revert, active-version sweep (`hotswap.verify_active`), startup sweep and damaged-version auto-rollback with circuit breaking (`ProposalBoard.health_sweep`; see §32.9 and §34.10); ④ **explicit CNB neural-tree definitions** — CNB ships **no preset tree shape**: the whole-tree definition is passed explicitly at startup (per-level LEVEL, counts, lower-level parent, ports and other required parameters; a single missing one is reported explicitly, item by item), accepted as direct parameters / JSON files / PY files; both in-process and multi-process assembly are supported; running trees can be reshaped with `np.remount(cnb={"tree": ...})`, file-watched reshape and auto-reconcile; on the npa startup path CNB config errors **never block startup** (explicit error, tree not loaded, `cnb_status=config-error`, `cnb_error` queryable); new `norpagent tree validate|show|up` subcommands (see §30.19).
> **2026-09-12 v2.2.0 Trinity rollout + Frontend V2 (new Chapter 34)**: ① **meta-framework entry** — `norpagent.core` (minimal-kernel four constructs + the `register_slot / register_layer / register_hook` trio + bare assembly path); ② **product-state entry** — `norpagent/farstars_app/` (the unbox implementation moved into its own entry module; `norpagent.unbox` remains a compatibility forwarder; the product state mounts **all built-in tools** by default, `tools: "all"`); ③ **settings source of truth** — the full kernel moving-point catalog (eleven domains) over four-layer inheritance (global > profile > session/task > temp; empty = inherit; default / inherited / explicit are all queryable) + a runtime-config mirror bridge + the `norpagent settings` CLI (Web / CLI / REST share one store and one validation); ④ **white-box traversal** — `norpagent.whitebox` renders the describe / audit_trail / settings triple for every environment, with a console "White-box overview" page; ⑤ **evolution loop completion** — proposal engine (propose -> decide -> execute -> verify -> consolidate) + circuit breaker + 2A memory / 2B skill / 2C config evolvers + a console "Proposal center"; ⑥ **runtime CNB hot mount** — `np.remount(cnb=...)` to mount / replace / detach the neural bus while running; ⑦ **Frontend V2** (warm-sun theme) — left-tab settings layout, three perspectives (product / framework / meta-framework), hover explanations, master-switch gating, JSON advanced mode, a `xhigh` reasoning-effort tier, a workspace directory picker, chat batch-clear / clear-all, inline mode / model / workspace controls in the composer, and a shared trilingual i18n core (`/assets/i18n.js` · `np_lang`) used by the main frontend / orbit console / FLOW page. See Chapter 34. All active version numbers are unified to **2.2.0**.
>
> **2026-09-11 v2.1.0 plugin-system overhaul (kernel dispatch fixes + full plugin capability expansion + new Chapter 33)**: ① **kernel hook-dispatch fixes** — the emit+intercept double dispatch of `before_step / before_tool_call / after_tool_call` collapses into a single call (side effects no longer run twice; the UI no longer double-prints); `EventBus.intercept` now traverses **every** subscriber and lets the first non-None value win (multi-plugin chains no longer truncate each other); ② **bridge compatibility fully repaired** — `PluginContext` gains the missing `logger / storage` (core dependencies of the existing plugin ecosystem); the 16 legacy hook signatures are aligned parameter by parameter (`on_task_stopped` auto-adapts to `(ctx)` or `(reason, ctx)`; `after_step` gains `reasoning` and the full `tool_calls` list; `on_usage_update` carries both key styles); pass-through returns normalize to "no rewrite"; hook exceptions are no longer silent (first error printed + counted + recorded in `diagnostics`); ③ **all 29 hooks open** (16 legacy + 13 native); ④ **the `setup(api)` registration facade** — plugins can register dynamic tools / custom slots / components / models / sessions / sandboxes / schedulers / UIs / custom hooks / event subscriptions / services / Web pages / CLI commands / settings, gated by capability declarations (`PLUGIN_CAPABILITIES`); ⑤ **lifecycle and clean hot reload** — `on_load / on_unload`, real unsubscribe/reclaim on unload, per-plugin `reload`; ⑥ **dependency and version declarations** (`PLUGIN_REQUIRES / PLUGIN_MIN_NORPAGENT`); ⑦ **Web plugin panel upgrade** (full status / failure reasons / signature / isolation / warnings / diagnostics; enable & disable / uninstall / upload-and-install) plus the CLI `norpagent plugins list|run`; ⑧ **new Chapter 33 "The Complete Plugin Development Guide"** (synced in both languages: all 29 hook signatures, the full setup API reference, a complete tutorial, troubleshooting, migration, and a release checklist). All active version numbers are unified to **2.1.0**.
> **2026-09-11 update (CNB universal slots / product entry `norpagent unbox` / self-evolution system)**: ① **CNB universal slots (R-024 / R-025 revision)** — each nervous-bus node offers up to **64 universal slots** over the bus (models / tools / plugins / custom modules); the norpagent complete instance is not abandoned — it is wrapped as the standard pluggable module `NorpAgentModule` (kind=`norpagent-instance`), pluggable / removable / describable / replaceable (see §30.18); ② **product-distribution entry `norpagent unbox` (R-006 / R-014 / R-007)** — one command starts the ready-to-use self-evolving user software: a single powerful agent + Web console + declarative profile; CNB is off by default and needs a manually configured port to enable (see Chapter 31); ③ **self-evolution system (R-004 / R-005 / R-010 ~ R-012 / R-017)** — settings source of truth (SQLite + JSON), per-item checkbox approvals, code hot reload (originals untouched, one-click rollback), .fspack packages / .zip bundles, evolution rhythm and direction (see Chapter 32); ④ version numbers unified to **2.0.1** (`pyproject.toml` / main package / CNB / recovery in sync).
> **2026-09-05 v2.0.0 (FarStars brand naming + kernel feature extensions)**: the official marketing name is **FarStars (远星)** — the `norpagent` call convention and kernel name stay unchanged (import / PyPI package name remain `norpagent`; FarStars is a brand overlay only: `__brand_cn__="远星"` / `__brand_en__="FarStars"` / `__display_name__="FarStars（远星）· norpagent"`). Four new feature groups are added — see the new **§30.17**: ① **task-molecule channel** — `run_task`'s `task_params` is now a full structured-JSON carrier: the mol six elements (mol_id / objective / acceptance / context_capsule / depends_on / budget / model_tier) reach the absorbing atom unchanged (no field loss); new kernel action **`task_records`** (action surface 14 → 15) exposes the acceptance-receipt datapane (original task_params + completion status); mol_id threads through node audits and the `task_started` / `task_done` uplink events with `acceptance` echoed back to the cortex. ② **quarantine freeze** — new downlinks `cmd.freeze` / `cmd.unfreeze`: a frozen node rejects new tasks (order intake closed; only read-only evidence actions pass, `frozen.reject` audits uplink), stays alive for forensics (heartbeats keep running and carry `status=frozen`, so the cortex scheduler drains it), never triggers sweep-dead, is auditable and reversible (unfreeze = recovery back to the tree). ③ **behavior baselines (kernel-side aggregation)** — nodes accumulate heartbeat-loss / audit-anomaly / task-failure counters locally and uplink the aggregate inside every heartbeat (compressed uplink); the cortex `behavior_view` grades each node yellow (degraded, human review) / black (suspected malicious, quarantine) with adjustable thresholds. ④ **subpoena evidence** — level-0-only highest evidence privilege: the new `cmd.subpoena` downlink forces a middle layer to stream its raw local audit (not the 2KB summary) straight to the cortex; five gates (basis prerequisite / quarantine envelope RAW-UNTRUSTED with read-to-burn isolation box / fetch channel / capacity tiers 64-128-256-512KB with human approval above 128KB and forced human adjudication above 512KB / every issuance audited as a black-level event); lower-level impersonation is rejected node-side and audited uplink (`subpoena.forged`). Every active version number is unified to **2.0.0**.
>
> **2026-09-05 v1.0.7 (CNB kernel integration)**: (1) **Structure** — the whole nervous-bus implementation moves into the kernel submodule `norpagent.cnb/` (protocol / topology / permissions / bus / node / cortex / cli / demo + a new `engine` binding layer); the version merges into norpagent (no separate version); `import norpagent` makes CNB ready (top-level `norpagent.cnb` plus `CnbAdapter` / `setup_cnb` / `KERNEL_ACTIONS`). The old standalone package name `nervous_bus` stays as a **compatibility shim** (re-export + sys.modules submodule injection + physical thin cli/demo files) — scripts / commands / tests from 1.0.6 and earlier keep working unchanged. (2) **Capability surface** — `NervousNode` gains an exec **action registry** (`register_action` / `unregister_action` / `list_actions`); cortex `cmd.exec` actions route to registered handlers first, legacy `on("exec")` callbacks fall back, and unknown actions are rejected node-side (`ok=False` + top-level `error`; contract upgrade). The engine binding layer registers the NorpEngine public API as a **14-action kernel surface**: task (`run_task`/`status`/`stop_task`), state (`engine_state`/`inspect`), snapshot (`snapshot`/`rollback`/`undo`/`redo`/`list_snapshots`/`mark_good`), ops (`remount`/`reload_plugins`/`stop_engine`). `cmd.stop` (stops tasks, instance stays running) and `cmd.reload` (env re-read + plugin hot reload) keep their semantics. (3) **Runtime** — `norpagent cortex/node` (and `main.py --norp-cortex/--norp-node`) now **assemble a full kernel engine by default**: every neural atom is a real task-capable norpagent instance (default minimal/mock, zero third-party deps; `--mode`/`--model` selectable; `--bare` returns to the plain nervous shell; the cortex = the top-level norpagent instance). `stop_engine` replies first, then stops the engine gracefully after 1s and deregisters the node; CLI processes exit naturally. (4) **Uplink** — heartbeats carry kernel state (`engine_state`/`active_tasks`/`version`/`actions`, visible in cortex `reports`); `task_started`/`task_done` events go uplink (full task lifecycle visible at the cortex). (5) `runtime/cnb.py` stays as a forwarding layer (engine.py untouched); `norpagent.cli` and `main.py` forward to the new path. (6) Tests: test_cnb 60 + test_deep_tree 36 + test_e2e 13 + automount 12/12 all green (migration regression-free), plus the new kernel-action acceptance `test/test_cnb_kernel_actions.py` (A in-process 21 + B multi-process 11 = 32/32). See §30.16. Every active version number is unified to **1.0.7**.
>
> **1.0.2 revision (CNB ships with the package)**: fixes the PyPI 1.0.1 package missing the Central Nervous Bus (CNB) — `nervous_bus/` moves from the repository root into `src/nervous_bus/` and is shipped with the package (`pip install norpagent==1.0.2` now includes CNB); the `norpagent` command gains the neural-tree subcommands `cortex / node / topo / ping / exec / stop / reload / perm / reports / audit / sync` (equivalent to `python -m nervous_bus.cli ...`; the legacy `--norp-cortex` / `--norp-node` spellings are forwarded automatically); running from the repository source is adapted by a src-path bootstrap at the top of `main.py` / `api.py`; every active version number is unified to 1.0.2 (`pyproject.toml`, `src/norpagent/__init__.py`, the recovery submodule `__version__`, the multimodal UA string, and the version-assertion test are all in sync).
>
> **2026-09-05 deep-tree fix (CNB kernel B1–B9, audit-driven remediation)**: the kernel was "self-consistent on shallow trees, broken on deep trees" — the official suites only covered ≤2-level flat scenarios (atoms mounted straight on the cortex) and never ≥3-level chained forwarding; a five-level tree exposed hard defects on all three main paths (registration / uplink / link-loss): 9 issues, 3 high severity (B1 deep-registration collapse — forwarding overwrote `via` at every hop so the cortex re-parented deep nodes; B2 middle layers recorded heartbeat/events without forwarding, leaving the cortex blind to deep nodes; B3 a middle layer exiting made the cortex cascade-deregister a whole live subtree into orphans). All fixed: `via` now uses `setdefault` so the original direct parent survives the chain; uplinks converge hop by hop and upper-layer rejections are echoed back to drive deep self-healing; new rescue logic `_rescue_children` + the `cmd.reroot` re-parent command keep live subtrees alive; permission decisions are now pure time-order (a type-level revoke is no longer shadowed by an older node_id grant); the cortex's lost-node sweep thread is wired up (`sweep_dead` finally called: dead detection → rescue → grace-then-drop); hello ancestor chains are de-duplicated; heartbeats accept custom status fields; topology broadcasts auto-fire debounced after register/deregister/rescue. A dedicated 4-level deep-tree regression suite `nervous_bus/test_deep_tree.py` (30 checks) was added; all suites verify 52+13+30+12. See §30.14. Every active version number is unified to **1.0.4** (`pyproject.toml`, `src/norpagent/__init__.py`, the recovery submodule `__version__`, the multimodal UA string, and the version-assertion test are all in sync).
> **2026-09-05 v1.0.6 increment (deep-tree convergence closure + permission-plane audit, verified on a running tree)**: ① **Gap A** — after the cortex's sweep had deregistered a lost leaf and auto-broadcast, receivers still did not converge, because `cmd.topology.sync` was add-only: the cortex audit showed `deregister: probe-x` → `topology broadcast: 11 ok`, yet middle-layer rnd's heartbeat `descendants` still listed probe-x for 150s+ (verified live). `cmd.topology.sync` is now an **authoritative snapshot mirror**: prune (cascade-deregister local nodes absent from the snapshot, self excluded) + parent-pointer convergence (align to the cortex view via `set_parent`); transient gaps self-heal through "heartbeat rejected → auto re-register". Deep-tree suite 30→**36** (new D13a–f). ② **Gap B** — exec permission denials and perm changes now uplink `report.audit` (`perm.denied` / `perm.changed`) hop by hop to the cortex; the cortex keeps structured permission-operation records and exposes a merged view `perm_audit(n)` (REPL `perm_audit` + ctrl `op=perm_audit`) for same-permission audit reads. test_cnb 52→**60** (new T-A0~T-A6, incl. a deep node's denial forwarded through a middle layer). See §30.15. Every active version number is unified to **1.0.6**.
> **2026-09 revision (CNB env auto-mount + task-level cancellation + manual alignment)**: ① **P0-1 landed** — ordinary norpagent instances (np()/GUI/embedded) read the `NORP_CNB_*` env vars at assembly time and auto-mount as nervous-tree nodes (new `norpagent/runtime/cnb.py`: CnbAdapter + background mount thread + registration retry + degrade-to-plain-instance on failure; `NORP_CNB_MANAGED=1` skips kernel mounting so an upper layer can build its own node — no double mounting; the shutdown path unmounts); the four cortex downlink callbacks now land on real engine control points: `exec` (action whitelist `run_task` / `status` / `stop_task`; missing-prompt and unknown-action requests are rejected; audit receipts; `report.event` task_done uplinks), `stop` (`stop_all_tasks()` stops every in-flight session task while the instance stays RUNNING), `reload` (re-reads the CNB env config and hot-reloads external plugins through the remount machinery), `perm_changed` (permission summary recorded and audited; the permission table is enforced before every cmd.exec). ② **P2-1 task-level cancellation** — the loop layer gains the optional `submit_async` extension (`NasyncTaskHandle`, deep per-task cancel, still covered by Ctrl+C / engine-stop full cancellation), and the engine gains `submit_async` / `cancel_task` / `stop_all_tasks` / `active_tasks` / `forget_task`. ③ **P1-1/P2-2 alignment** — `--help` now shows the CNB subcommands; §30.8/§30.12/Appendix J are rewritten to the real implementation locations (`runtime/engine.py` + `runtime/cnb.py`; the fictional `api.py AgentAPI._setup_cnb()` and config.json key claims are removed — the contract is env vars only). ④ `nervous_bus.test_e2e` now climbs to the repository root that contains `main.py` (`python -m nervous_bus.test_e2e` works again under the v1.0.2 src/ layout; 13/13). ⑤ new acceptance smoke `test/test_cnb_automount.py` (12 checks, 12/12 verified on 2026-09-05).
>
> **1.0.1 revision (version milestone)**: the 0.9.x line concludes and the project enters the **1.0.x series** — all active version numbers are unified to 1.0.1 (`pyproject.toml`, `src/norpagent/__init__.py`, the recovery submodule `__version__`, the multimodal UA string, and the version-assertion test are all in sync); the 1.0 series carries every capability delivered so far: multimodal (vision + sound), the Central Nervous Bus (CNB) multi-instance neural tree, rescue mode, 29 hooks, and the plugin system.
> **0.9.9 revision (multimodal)**: new **Chapter 29 "Multimodal: Vision and Sound"** and **Appendix I "Multimodal Configuration and API Quick Reference"** — vision: upload / paste / drag images, the backend `/api/vision` endpoint has an external vision service describe them, and the description flows into the conversation; sound: speech output (TTS) and speech input (STT) are **fully implemented on the backend** (Windows SAPI / macOS say / Linux espeak-ng offline, or configurable OpenAI-compatible services), the notification tone is generated by the backend, the browser only captures and plays — nothing depends on browser-native speech APIs; `/api/upload` now supports images; `tts_service_api_key` / `stt_service_api_key` are stored DPAPI-encrypted like `api_key`.
> **2026-08 Central Nervous Bus (CNB) multi-instance upgrade**: new **Chapter 30 "Central Nervous Bus: Multi-Instance and the Neural Tree"** and **Appendix J "Central Nervous Bus Quick Reference"** — the cortex (the highest norpagent instance) controls the operation permissions of any atom at any level through the Central Nervous Bus; lower levels may only report upward through the bus and can never control upper levels; the neural tree is a tree-shaped topology chain; lower levels obey higher-level commands unconditionally and are forbidden to rewrite higher levels — they may only report back. The full `nervous_bus/` module set (protocol layer / tree topology / neural permission table / zero-dependency transport / node / cortex / CLI) passes 51 unit+integration tests and 13 real multi-process end-to-end tests; `main.py` gains the GUI-less `--norp-cortex` / `--norp-node` multi-instance entry (bypassing the single-instance lock), and `api.py` lets a GUI instance join the neural tree as a node.
> 2026-08 revision: Chapter 27 minimal kernel in depth (EventBus / the slot connector ArchLayer / the Registry / the address resolver: data structures, APIs, internals and a startup + hot-mount collaboration walkthrough) | Chapter 26 registration flow in detail (the Registry's 9 namespaces / four value forms and string semantics / the full npa() assembly pipeline / three registration timings and hot reload / slot registration vs component registration / validation and error handling / a checklist) | Chapter 25 developer practice (module / slot / plugin / tool development in depth; slot development contract incl. the hot-reload red line: dict key-value pairs must be valid modules; architecture overview and the minimal main async-loop core) | Chapter 24 rescue mode (low-level loop control + human takeover) | kernel fix: select timeout clamp (found by the stress suite; far timers crashed the loop on Windows) | new 35-item violent stress suite for the minimal async-loop core (test/stress_nasyncio_core.py) | 15.6 human-rescue manual tool takeover API (v0.9.3; operate all tools by hand when the model is down: tools / tool-call / manual / serve) | 3.9 task-level slot injection (submit(slot_overrides=...)) | 3.7 in-flight task races of assembly-slot hot rebuilds and the drain recommendation | 4.6.4 daemon worker-pool queue semantics and the stuck-task fallback matrix | 23.1 EventBus benchmark baseline and lock-contention boundary
> **0.9.7 revision**: human rescue supports manual control of custom tools (`RescueToolEnvironment` gains `extra_tools` / `tools` / `plugin_dirs`; the CLI gains `--tools` / `--plugin-dirs`; the inventory and the operator page tag each tool with builtin / custom / plugin origin) | the general-purpose event bus (GeneralEventBus; the class stays `EventBus`) gains generic capabilities: `once` / `wait` / `emit_all` / `subscriber_count` / `has_listeners` / `clear` | Chapter 9 gains 9.8 "all 29 hooks, one by one (Python code)" | new Chapter 28 "External Python Script Integration: Hot Mounting and Hook Subscription" | new Appendix F (frontend-backend communication quick reference) / Appendix G (all commands quick reference) / Appendix H (all functions and structures quick reference) | Chapter 13 command-line entry expanded (console-frontend entry + rescue-mode commands) | terminology unified (EventBus is called the GeneralEventBus in this manual; code symbols unchanged)

---

*NorpAgent Developer Manual · v2.2.1 · FarStars (远星) · Copyright (c) 2026 xingluosama121, MIT Licensed*
