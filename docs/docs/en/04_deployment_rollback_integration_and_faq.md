<!-- Split by part from docs/DEVELOPER_MANUAL.EN.md; body is line-for-line identical -->

> **Developer Manual - Part 4: Deployment, Rollback, Integration and FAQ** | Covers: Chapters 14-19 + Appendices A-C | [Back to index](../README.md)

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
and .pyc before remounting (see 25.2.6), so "edit the module file →
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

