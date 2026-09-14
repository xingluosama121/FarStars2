<!-- Split by part from docs/DEVELOPER_MANUAL.EN.md; body is line-for-line identical -->

> **Developer Manual - Part 1: Quick Start and Architecture** | Covers: Chapters 1-3 | [Back to index](../README.md)

---

# NORP Agent Developer Manual

> **Version**: 2.2.2 | **Brand**: FarStars (远星) | **License**: Copyright (c) 2026 xingluosama121, MIT Licensed
>
> **Repository**: https://github.com/xingluosama121/farstars2 | **PyPI**: https://pypi.org/project/norpagent/

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
**Only when the outermost value passed in is itself a string** are the **module cache
and .pyc bytecode cache invalidated** before re-resolution; dict / list forms (even
when their values are address strings) do not trigger invalidation (only the outermost
`isinstance(value, str)` check invalidates the cache; it does not recurse into dict /
list) — see 25.2.6. So "edit the module file → remount (**bare string address**)"
swaps in the changed code at runtime without restarting the process.

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

