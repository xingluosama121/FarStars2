<!-- Split by part from docs/DEVELOPER_MANUAL.EN.md; body is line-for-line identical -->

> **Developer Manual - Part 5: Flow Orchestration and Deep Dive** | Covers: Chapters 20-24 | [Back to index](../README.md)

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
    Windows and crash the loop thread — a real defect,
    and fixed: the loop wakes every 24h to re-check the timer heap,
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

