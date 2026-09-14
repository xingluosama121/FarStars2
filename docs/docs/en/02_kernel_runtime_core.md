<!-- Split by part from docs/DEVELOPER_MANUAL.EN.md; body is line-for-line identical -->

> **Developer Manual - Part 2: Kernel Runtime Core** | Covers: Chapters 4-8 | [Back to index](../README.md)

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

