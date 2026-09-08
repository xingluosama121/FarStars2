# FarStars（远星）· norpagent

A pluggable, brick-style Agent framework — *the module is the entry point*. Build an Agent the way you build with LEGO: swap any part by filling in an "address", with zero changes to the core code — and swap parts while the process is still running (hot mount), with no restart required.

> **Version**: 2.0.1 (2026-09-06) ｜ **Brand**: FarStars（远星）— the official public name since v2.0.0; the package, imports and PyPI name stay `norpagent` ｜ **License**: Copyright (c) 2026 xingluosama121, MIT Licensed
> **Dependencies**: the core package has **zero third-party dependencies** — a plain Python standard library is enough to run it; optional capabilities are installed on demand

---

## Highlights

- **FarStars Orbit Console & Web UI refresh (v2.0.1)** — the built-in Web UI (`front.html`) was re-skinned with a beige `#f6f3ed` theme, white cards, rounded corners and full modal/view/toast animations; a **settings panel** with schema-driven field clamping (live min/max validation), dirty-flag close confirmation and unified risk confirm dialogs; the **FarStars Orbit Console** (`norp-farstars.html`) is served at `/farstars` (three aliases) with `mount_page` and the `farstars_html` remount key for hot page swapping; `/api/cnb/health` and `/api/cnb/ctrl` provide same-origin cortex proxies (loopback targets only, SSRF-guarded). In browser mode a REST compatibility layer + SSE event translation is installed automatically when no native pywebview environment exists — chat/settings/plugins work without an infinite spinner;
- **Central Nervous Bus — CNB, kernel-integrated (v1.0.7 → v2.0.0)** — multi-instance Agent orchestration: any number of `norpagent` processes form a **neural tree** whose root is the **cortex** (highest level, tree root) and whose leaves are **nodes** (atoms: `norpbot`, `norpilot`, `norpmemory`, ... or any custom instance). Cortex ↔ node control flows over an uplink/downlink protocol with layered levels, a neural permission table, heartbeat/sweep lifecycle and an `exec` action registry — since v1.0.7 the cortex can drive **kernel-level actions** (run_task / snapshot / rollback / remount / reload_plugins / stop_engine / ...) on any atom, and every `norpagent cortex/node` process carries a full engine by default (`--bare` for a plain shell). Since v2.0.0: **task molecule (mol)** structured dispatch (`task_params` / `task_records` acceptance receipts), **isolated frozen state** (`freeze`/`unfreeze`: refuses new tasks while keeping heartbeat/alibi alive), **behavior baseline** aggregation (heartbeat compression + graded cortex views) and **subpoena evidence collection** (level-0 exclusive, non-delegable, tiered capacity, isolated RAW/UNTRUSTED frames, fully audited issuance);
- **Multimodal (v0.9.9)** — vision + sound in both directions: upload / paste / drag images and the backend vision service folds them into the conversation (`/api/vision`); **TTS and STT are implemented natively in the backend with zero dependencies** — system engines (Windows SAPI / macOS `say` / Linux `espeak-ng`) work offline, or an OpenAI-compatible service can be configured; notification sounds are generated server-side; the browser only captures and plays audio, no browser speech API required;
- **Architecture layer + address functions** — apart from the minimal bottom kernel (`ArchLayer` / address resolution / registry / event bus), every component is a slot: model, frontend, event loop, session, sandbox... fill in an address and it is replaced;
- **Hot-pluggable slot table (v0.9)** — `register_slot()` / `unregister_slot()` register / unregister custom slots at runtime; registration plugs straight into the whole pipeline of `npa()` argument validation, assembly, `npa.remount()` hot replacement and `layer.describe()` listing (the 18 built-in slots are structural contracts — protected from registration/override/removal, though their *values* can be hot-replaced at any time);
- **Work rollback (v0.9)** — snapshot timeline + Undo / Redo / Rollback (Web UI buttons / Ctrl+Z / API, immediate in-process); the standalone crash-rescue CLI `norpagent-rescue` (pure standard library — works even when the main program cannot start, offering one-key restore to the last known-good snapshot); safe mode `npa(safemode="on")` / `norpagent --safe-mode` (loads only the minimal kernel, skips all plugins);
- **Human rescue (v0.9.3, custom tools v0.9.7)** — when the model fails, a human takes over the tool layer: `norpagent-rescue tools / tool-call / manual / serve` (HTTP API + operator page), passing arguments by hand and reading raw results; the same RunContext path and the same state as the model; besides the built-in tools, **custom and plugin tools** can be operated manually too (`--tools` registry tools / module addresses, `--plugin-dirs` external plugin dirs; the operator page labels builtin / custom / plugin sources); hard timeout + cancel signal, localhost-only by default;
- **Self-developed async scheduling core** — `norpagent.nasyncio` (originally `nasync_io`, packaged into the library) is the default event loop core — it neither depends on nor imports the standard `asyncio`;
- **Security system fully decoupled** — `norpagent.safe()` mounts the whole security suite in one call; hooks are **zero-intervention by default** (no hooks mounted); `hooks=True` / `kit.install_hooks()` enables hook intervention explicitly;
- **9-layer / 29-hook system** — every execution structure is an independent API: subscribable, rewritable, vetoable, with custom hooks and custom layers;
- **Embedded & ultra-high concurrency (v0.9)** — `install_core()` minimal assembly + the `embedded` preset (pure in-memory, headless by default, zero disk dependencies); EventBus copy-on-write, bounded SSE queue + batched flush, HTTP concurrency tuning;
- **External plugins** — a complete security pipeline (signature → audit → import restrictions → registration), process-level isolation and the `PluginSystem` facade;
- **Frontend family** — console / headless / web work out of the box, plus any custom frontend; the Web UI is HTTP + SSE with zero dependencies;
- **Context / project / scheduler / sandbox** — FTS5 context store, `project_status` (git-aware), persistent scheduler, pooled sandboxes and PTC child-process isolation.

---

## Installation

```bash
pip install norpagent
```

The core package has no third-party dependencies; after installation it runs in a plain Python environment (a built-in mock model and tools are included). Optional capabilities install on demand:

```bash
pip install norpagent[openai]       # OpenAI-compatible model adapter (DeepSeek/OpenAI/Qwen/vLLM/Ollama)
pip install norpagent[anthropic]    # Anthropic-protocol model adapter
pip install norpagent[web]          # web access (web_search / web_fetch tools)
pip install norpagent[security]     # plugin Ed25519 verification (cryptography)
pip install norpagent[all]          # everything above
```

---

## Quick Start

### Run it in 5 lines

```python
import norpagent as npa

npa()                        # runs entirely on default logic (standard preset + Web frontend)
running = True
while running:
    if npa.stop() == True:   # lifecycle function: exit when the application ends
        running = False
```

Save as `hello.py` and run it. The console prints `[norpagent] frontend web listening on 127.0.0.1:8787`; open that address in a browser for the chat UI.

Two key points:

1. **`npa()` is a module-level call** — the `norpagent` module itself is callable, equivalent to `norpagent.launch()`;
2. **`npa.stop()` is a lifecycle function** — returns `True` when the Agent application has ended and the main loop should exit.

### One-shot task

```python
import norpagent as npa

npa(prompt="Explain what an address function is in one sentence")
running = True
while running:
    if npa.stop() == True:
        running = False

engine = npa.current()
print(engine.last_result.final_content)
```

When `prompt` is passed, the Agent runs that single task and stops by itself; the result is stored in `npa.current().last_result`.

### Swap parts: fill in an address

```python
npa(preset="standard")                                  # swap the preset mode
npa(model="openai_compat")                              # swap the brain (model)
npa(async_loop="norpagent.loops.nasyncio:NasyncioLoopRuntime")  # swap the event loop system
npa(frontend="norpagent.frontends.console:ConsoleFrontend")     # swap the frontend (web by default)
npa(session="sqlite", sandbox="pooled")                 # swap session and sandbox
```

### Hot mount while running (no restart)

```python
npa.remount(model="openai_compat")                      # swap the model: takes effect on the next run
npa.remount(frontend="norpagent.frontends.console:ConsoleFrontend")
npa.remount(model="myapp.model:create")                 # edit the module file, remount = hot reload
npa.remount(flow_html="H:/path/flow.html")              # swap the /flow page (HTTP not restarted)
npa.remount(html="H:/path/front.html")                  # swap the / main page (HTTP not restarted)
npa.remount(farstars_html="H:/path/farstars.html")      # swap the /farstars orbit console page
npa.remount(flow_html=None)                             # unmount, fall back to the library built-in
```

### Work rollback (Undo / Redo / Rollback / crash rescue)

```python
npa.snapshot_system("before installing the plugin")     # manual snapshot (auto-snapshot on change is on by default)
npa.undo()                                 # undo the latest operation (in-process, immediate)
npa.redo()                                 # redo what was undone
npa.rollback("20260818T230101_ab12cd")     # roll back to any snapshot
npa.rollback()                             # roll back to the last known-good snapshot
npa.list_snapshots()                       # timeline (* = last good)
npa(safemode="on")                         # safe mode: load only the minimal kernel
```

Web UI: the left-side "rollback" page + Ctrl+Z / Ctrl+Shift+Z. When the main program cannot start:

```bash
norpagent-rescue list                     # * = last known-good snapshot
norpagent-rescue rollback --last-good     # one-key rollback (applied automatically on the next start)
norpagent --safe-mode                     # start in safe mode (skips all plugins)
```

### Human rescue (drive tools by hand when the model is down)

The model provider is down but the workspace / sandbox / context store / task queue are still alive? Take over the tool layer directly (pass arguments by hand, read the raw results) — the exact same execution path the model uses:

```bash
norpagent-rescue tools                              # list all tools (custom tools included)
norpagent-rescue tool-call echo --args '{"text": "ping"}'
norpagent-rescue manual                             # interactive manual console
norpagent-rescue serve --port 8799                  # HTTP API + operator page
norpagent-rescue serve --token my-secret            # optional bearer auth

# v0.9.7: manual operation of custom tools
norpagent-rescue tools --plugin-dirs ./my_plugins   # load external plugin tools
norpagent-rescue tool-call my_tool --args '{}' --tools myapp.tools:create
norpagent-rescue serve --tools my_tool1,my_tool2    # append registered tools by name
```

Programmatically: `norpagent.rescue_api` (`RescueToolEnvironment` supports `extra_tools` / `tools` / `plugin_dirs` plus `RescueToolAPI`). See Chapter 24 of the manual.

### Console REPL

When the console frontend is used explicitly, the Python interactive interpreter (REPL) switches to synchronous mode automatically: `npa()` blocks until the user exits (`/exit`, `exit()`, Ctrl+C or EOF) — no polling loop needed:

```python
import norpagent as npa

npa(frontend="norpagent.frontends.console:ConsoleFrontend")
# >>> you: hello
# >>> use /exit to quit
```

---

## Command-Line Entry

```bash
# one-shot task
python -m norpagent --mode standard --prompt "hello"

# interactive REPL
python -m norpagent --mode standard

# list all preset modes (minimal / standard / ptc / creative / longrun / embedded)
python -m norpagent --list-modes

# connect to an OpenAI-compatible service (DeepSeek, etc.)
python -m norpagent --model openai_compat --model-name deepseek-v4-flash \
    --base-url https://api.deepseek.com/v1 --api-key sk-xxxx

# security policy (runtime: approval / audit / signature; hooks zero-intervention by default)
python -m norpagent --safe high
python -m norpagent --safe high --safe-hooks   # explicit hook intervention (jailbreak blocking + prompt hardening)

# Web UI port
python -m norpagent --ui web --port 8787

# external plugins (repeatable; security pipeline: signature -> audit -> import restrictions)
python -m norpagent --plugin-dir ./plugins --plugin-isolation auto

# plugin signing tool (NORP plugin signature protocol v1)
python -m norpagent plugin-sign myplugin.py --gen
python -m norpagent plugin-sign myplugin.py --key <ed25519-hex>
```

### Central Nervous Bus (CNB) subcommands

Kernel-integrated since v1.0.7 (`norpagent.cnb` ships inside the PyPI package; the legacy top-level `nervous_bus` name remains as a compatibility shim):

```bash
# start the cortex — the tree root (level 0); carries a full engine by default
norpagent cortex --port 17800 --repl

# mount a node under the cortex (each node is a real agent instance)
norpagent node --id norpbot-01 --kind bot --parent http://127.0.0.1:17800 --port 17801 --level 3

# cortex control
norpagent topo --root http://127.0.0.1:17800     # show the neural tree
norpagent ping|exec|stop|reload|perm|reports|audit|sync ...

# v2.0.0 (FarStars): quarantine and evidence
norpagent freeze --node <id> | unfreeze --node <id>     # isolated frozen state
norpagent behavior ...                                   # behavior baseline grading
norpagent subpoena ... | subpoena_box ... | subpoena_audit ...   # evidence collection

# kernel-level actions on any atom (cortex -> node):
norpagent exec --node X --action run_task --args '<json>'
norpagent exec --node X --action snapshot --args '{}'
```

Ordinary GUI / embedded / `npa()` instances can join the tree with **no subcommand at all** — set the `NORP_CNB_*` environment variables (node id / kind / level / parent / port / heartbeat) and start normally; mounting happens in a background thread and any failure degrades to a plain single instance. Legacy spellings `norpagent --norp-cortex ...` / `norpagent --norp-node ...` (used by the repository-root `python main.py` entry) are forwarded automatically. See Chapter 30 of the manual.

---

## Core Concepts

### Slots and address functions

Apart from the minimal bottom kernel, every component is a slot; the keyword arguments of `npa(...)` *are* slot names, and a slot value is an "address string" (`package.module:attr` or a registered name) that completes the replacement. Assembly is resolved uniformly by `ArchLayer`.

The slot table itself is hot-pluggable — a third-party library can register brand-new slots at runtime, and the registration plugs into the whole pipeline of `npa()` argument validation, assembly, hot replacement and listing:

```python
from norpagent.arch import SlotSpec, register_slot


def apply_vector_store(reg, layer, value, params, ctx):
    name = "_arch_vector"
    factory = value if callable(value) else (lambda v=value: v)
    reg.register_component("vector_store", name, factory)
    ctx["components"]["vector_store"] = name   # preset-declared component
    ctx["extras"]["vector_store"] = value


register_slot(SlotSpec(
    name="vector_store",
    description="vector search component (custom assembly slot)",
    protocol="any implementation (registered as a generic vector_store component)",
    string_semantics="literal",
    applier=apply_vector_store,
    remount_rebuild_agent=True,     # hot-rebuild AgentRuntime after hot replacement; the component takes effect immediately
))

import norpagent as npa

npa(vector_store=MyVectorStore())    # assembly: engine.agent.components["vector_store"]
npa.remount(vector_store=Other())    # hot replacement: AgentRuntime hot-rebuilt
```

The 18 built-in slots are structural contracts of the framework and cannot be registered / overridden / unregistered (their *values* can still be hot-replaced at any time via `npa.remount`). The full contract and protection rules are in the manual's architecture-chapter.

**v0.9.1: every slot supports address loading.** String values of literal slots (security / storage / hooks / plugins / logger / error_handler) and name slots (ui / preset) also accept addresses — dotted identifiers of the form `pkg.mod[:attr]` are loaded by address, everything else keeps its original semantics (`npa(security="high")` stays a level, `npa(storage="./data")` stays a path, `npa(ui="web")` stays a registered name); the **values of dict entries** in any slot resolve as plain addresses too: `tools={"my_tool": "myapp.tools:create"}`, `hooks={"before_model_call": "myapp.guard:fn"}` — a failed resolution raises `AddressError`.

### Central Nervous Bus: multi-instance and the neural tree

CNB gives `norpagent` **multi-instance** capability: any number of processes form a neural tree. The root is the **cortex** (level 0, the highest-level instance holding the full topology and control over any level); every other instance is a **node** (an atom: `norpbot` / `norpilot` / `norpmemory` / ... or any custom instance). Each atom runs independently with its own configuration and, on top of that, acts as a tree node (`node_kind` states the atom type) dispatched and authorized by the cortex.

```
                    ┌──────────────────────────┐
                    │   Cortex  (level 0)        │  highest level, tree root
                    │   highest norpagent instance │  full topology + control over any level
                    └────────────┬─────────────┘
                                 │  downlink cmd.*  (high -> low, unconditional)
                                 │  uplink report.* (low -> high, read-only)
                    ┌────────────┴─────────────┐
                    │   Central Nervous Bus      │  protocol + topology + permissions + transport
                    └────────────┬─────────────┘
              ┌──────────────────┼──────────────────┐
       ┌──────┴──────┐    ┌──────┴──────┐    ┌──────┴──────┐
       │ level 3 atom │    │ level 3 atom │    │   ...       │
       │ norpbot-01   │    │ norpmemory-01│    └─────────────┘
       └──────┬──────┘    └─────────────┘
       ┌──────┴──────┐
       │ level 4 atom │   <- tree chain: every node has exactly one parent
       │ norpilot-01  │
       └─────────────┘
```

Core mechanics (enforced by code, see Chapter 30 of the manual):

- **Levels**: the smaller the number the higher the rank — `0` = cortex; a child's level must be greater than its parent's; a level cannot be forged after registration (identity anti-tampering);
- **Uplink is read-only**: only `report.*` (register / heartbeat / event / audit / request / deregister) may travel upward; the transport strips or rejects any control field — a low-level node cannot control anything above it even if maliciously crafted;
- **Downlink obeys ancestors**: `cmd.*` (hello / ping / exec / stop / reload / perm.set / perm.grant / perm.revoke / topology.sync) is accepted only from a verified ancestor; legal commands execute unconditionally and are audited;
- **Neural permission table**: each node keeps a local table of `cmd.perm.*` rules over the ten permission atoms (`file_read` `file_write` `file_delete` `file_list` `process_exec` `process_shell` `network_out` `network_in` `system_info` `plugin_call`); targets can be an exact `node_id`, a `node_kind` wildcard, or `*` for all; the cortex grants / revokes / sets rules for any level;
- **Topology**: acyclicity validation, cascaded deregistration of whole subtrees, dead-node sweep by heartbeat timeout (marked dead, not removed), deep registration forwarded hop-by-hop to the cortex;
- **Kernel action surface (v1.0.7)**: `cmd.exec` routes to a registered action registry — the engine binding layer (`norpagent.cnb.engine`, `CnbAdapter`) registers `NorpEngine` public APIs (run_task / status / snapshot / rollback / undo / redo / remount / reload_plugins / stop_engine / task_records / ...) as kernel actions, so the cortex can operate the kernel of any atom at any depth;
- **v2.0.0 extensions**: `cmd.freeze` / `cmd.unfreeze` quarantine a node (the intake closes: only read-only evidence actions pass, `run_task`/`stop_engine` are rejected and audited as `frozen.reject`; heartbeat stays alive with `status=frozen` so the sweep never misjudges it as dead); task molecule (`task_params` structured payloads with `mol_id` threaded through `audit` / `task_started` / `task_done`, and `task_records` acceptance receipts); behavior baselines (heartbeat compression + graded cortex views: yellow = degraded, black = suspected malicious); subpoena evidence collection (level-0 exclusive, non-delegable, five gates, tiered capacity, isolated RAW/UNTRUSTED frames, issuance fully audited).

Programmatic API (available right after `import norpagent`):

```python
import norpagent as npa

npa.cnb.Cortex                        # cortex node: tree root + control API
npa.cnb.NervousNode                   # any node: bus / heartbeat / uplink / downlink + exec action registry
npa.cnb.Topology / NodeInfo           # tree topology
npa.cnb.NeuralPermissionTable / PermRule
npa.cnb.CnbAdapter / setup_cnb / KERNEL_ACTIONS   # engine binding layer
npa.cnb.make_envelope / check_uplink_payload      # CNB/1.0 protocol helpers
```

`npa.cnb.demo` runs a quick same-process demo (one cortex + a three-level tree). Quick start and deep-tree behavior are covered in the manual's Chapter 30 and Appendix J.

### Self-developed async core: norpagent.nasyncio

**Explicit statement: norpagent does not depend on the standard asyncio.** Since 0.8 there is zero `import asyncio` inside the library: the default scheduling core is the self-developed async IO library `norpagent.nasyncio` (originally `nasync_io`, packaged into the library since v2.0.0), which relies only on non-asyncio standard modules (`threading` / `selectors` / `socket` / `heapq`). Why:

1. **Scheduling / cancellation / cross-thread wakeup semantics are fully self-controlled** — the known standard-asyncio pitfalls are fixed: `Task.cancel()` is not thread-safe, done callbacks that do not write the self-pipe leave waiters hanging, and there is no public "cancel the main task" entry;
2. **The dependency surface shrinks to something auditable** — all event-loop behavior is code written inside the library; no internals or version differences of standard asyncio are pulled in;
3. **Exit semantics are controllable** — no `ThreadPoolExecutor` that the interpreter force-joins; the process winds down immediately after Ctrl+C;
4. **API semantics align, migration is zero-cost** — `EventLoop` / `Future` / `Task` / `Lock` / `Condition` / `sleep` / `wait_for` correspond by name to asyncio; replace `import asyncio` with `import norpagent.nasyncio` and port;
5. **The core is independently usable** — `norpagent.nasyncio` is itself a standalone micro async library.

```python
import norpagent as npa
import norpagent.nasyncio as core   # self-developed core module (callable)

core.EventLoop                      # self-developed event loop class
loop_rt = npa.nasyncio()            # default LoopRuntime implementation (same as core())
```

The pre-0.7 address `norpagent.loops.std_asyncio:StdLoopRuntime` remains as a compatibility shim (no asyncio import); legacy code keeps working.

### Security: fully decoupled, zero hook intervention

The security system is decoupled from the hook pipeline: `norpagent.safe()` mounts only runtime policies by default (manual approval / network policy / plugin-loading policy) and **subscribes to no hooks** — the hook pipeline stays pure. The power to intervene in hooks is handed entirely to you:

```python
from norpagent.safe import safe

safe(reg, level="high", hooks=True)     # mount hooks at install time
kit = safe(reg, level="high")           # default: zero intervention
kit.install_hooks(reg)                  # mount manually afterwards
kit.uninstall_hooks(reg)                # unmount (removes only the security kit's own subscribers)
kit.hooks_installed(reg)                # query mount state
```

The guard capabilities stay available as standalone APIs (`kit.scan_input()` / `kit.harden()` and more) that you can call freely from your own hook subscribers or method overrides. See Chapter 10 of the manual.

### The 9-layer / 29-hook system

Every execution structure is an independent API — subscribable, rewritable, vetoable — with custom hooks and custom layers:

- input layer (before_input / input_pipeline, ...) — including veto semantics;
- model, tool, output, session, task, lifecycle, bus layers and more: 9 layers, 29 hooks in total.

The full inventory is in the manual's Chapter 9 and Appendix B / Appendix E.

### Preset modes

| Mode | Description |
|---|---|
| `minimal` | smallest closed loop: mock model + minimal tool set |
| `standard` | standard assembly (default) |
| `ptc` | PTC sandbox execution (`run_python` child-process isolation) |
| `creative` | creative mode: load a custom mode from a .py file |
| `longrun` | long-running task cooperation (persistent scheduler) |
| `embedded` | embedded: pure in-memory components, headless by default, zero disk dependencies |

### Embedded and ultra-high concurrency

**Embedded** (minimal dependency surface):

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

Or simply `npa(preset="embedded")` out of the box (headless by default, no HTTP service started).

**Ultra-high concurrency**: EventBus copy-on-write (one listener-list copy saved per event; measured at >1.6 M events/sec); bounded SSE backpressure (drops the oldest by default — slow clients no longer eat memory unboundedly, and the bound can be changed while running); batched SSE frame flushing + sub-second disconnect reclamation; HTTP concurrency tuning (listen backlog, reverse-proxy buffering disabled). See Chapter 14 of the manual.

### Top-level API quick reference

```python
import norpagent as npa

npa()                          # start the default Agent (= npa.launch())
npa.stop()                     # lifecycle polling: True when the application has ended
npa.current()                  # current engine (NorpEngine)
npa.submit("hello")            # pure API submission
npa.remount(model="...")       # hot-mount a slot
npa.shutdown()                 # shut down
npa.nasyncio()                 # self-developed event loop (LoopRuntime)
npa.safe(...)                  # mount security policies
npa.register_slot(...)         # hot-plug the slot table
npa.unregister_slot(...)
npa.snapshot_slots()
npa.is_builtin_slot("model")
# work rollback
npa.snapshot_system("note")    # manual snapshot
npa.undo() / npa.redo()        # undo / redo
npa.rollback("<snapshot-id>")  # roll back to any version (default = last good)
npa.list_snapshots()           # snapshot timeline
npa.mark_good_snapshot("<id>") # mark a snapshot as "good"
# Central Nervous Bus (v1.0.7+)
npa.cnb                        # CNS kernel submodule: Cortex / NervousNode / Topology / CnbAdapter / ...
```

---

## Project Structure

Source layout (PyPI `src` layout; `norpagent.cnb` is the kernel-integrated CNB since v1.0.7, with the legacy top-level package `nervous_bus` kept as a compatibility shim):

```
src/norpagent/
├── kernel/          # minimal kernel: Registry / EventBus / AgentRuntime / presets
├── arch/            # architecture layer: ArchLayer / SlotSpec / slot-table hot-plug / address resolution
├── runtime/         # npa() startup & lifecycle: launch / stop / remount / NorpEngine
├── loops/           # event-loop architecture functions (nasyncio default + std shim)
├── nasyncio.py      # self-developed async IO core (zero asyncio dependency)
├── recovery/        # work rollback: snapshot store / replay / Undo / Redo / Rollback
├── rescue.py        # crash-rescue CLI (norpagent-rescue, pure standard library)
├── rescue_api.py    # human rescue: manual tool environment + HTTP API + operator page
├── cnb/             # Central Nervous Bus: protocol / topology / permissions / bus / node / cortex / engine / cli / demo
├── hooks/           # the 9-layer 29-hook system
├── security/        # security pipeline (approval / audit / signature) — decoupled, zero hook intervention by default
├── safe.py          # norpagent.safe(): mount the whole security suite in one call
├── plugins/         # plugin system (signature -> audit -> import restrictions -> registration)
├── builtin/         # built-in components: models / tools / sessions / sandboxes / scheduler / context / projects
│   └── ui/          #   Web UI: front.html (chat), norp-farstars.html (orbit console), norp-flow.html (flow page)
├── modes/           # six preset modes
├── frontends/       # frontend shells (console / headless / web)
├── protocols/       # component protocols
├── flows/           # execution flows
├── cli.py           # command-line entry (python -m norpagent; CNB subcommands forwarded to norpagent.cnb.cli)
└── __init__.py      # module as entry: the callable module npa()
```

---

## Documentation and Tests

- **Developer manual (Chinese)**: `docs/DEVELOPER_MANUAL.md` — 30 chapters + 10 appendices (A–J): architecture and data flow, slots & address functions, the nasyncio event loop (including the full "no standard asyncio" statement), the frontend family, hooks (per-hook Python usage), security, plugins, embedded & high-concurrency deployment, work rollback, FLOW orchestration, built-in components in depth, Web UI deep dive, performance design and benchmarks, rescue mode, developer practice, registration flow, minimal kernel internals, external Python-script integration, multimodal (vision & sound), and Chapter 30 on the Central Nervous Bus (multi-instance / neural tree / v2.0.0 extensions in §30.17); a complete **English copy** is available as `docs/DEVELOPER_MANUAL.EN.md`;
- **Technology architecture whitepaper**: `test/ARCHITECTURE_WHITEPAPER.md` — design philosophy, layered architecture, the slot system, the kernel, nasyncio, hooks, security, plugins, reliability, FLOW, measured performance and ADRs; a `.docx` rendering of the same source is next to it;
- **Hook quick reference**: `test/hooks.md`;
- **Regression tests**: `test/_verify_*.py` / `test/_smoke_*.py` cover the nasyncio migration, cancellation semantics, hot-mount loops, slot hot-plug, embedded & concurrency, WebUI smoke tests, front.html migration and the human-rescue manual-tool API; `test/test_minimal_kernel_suite.py` is the 48-item minimal-kernel suite; `test/test_cnb_automount.py` (12 items) and `test/test_cnb_kernel_actions.py` (32 items) cover CNB engine auto-mounting and kernel-level actions.

---

## License

Copyright (c) 2026 xingluosama121, MIT Licensed
