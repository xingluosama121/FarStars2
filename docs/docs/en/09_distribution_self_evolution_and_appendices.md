<!-- Split by part from docs/DEVELOPER_MANUAL.EN.md; body is line-for-line identical -->

> **Developer Manual - Part 9: Distribution, Self-Evolution and Appendices** | Covers: Chapters 31-34 + Appendices D-J + Revision History | [Back to index](../README.md)

---

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
norpagent unbox --smoke                  # self-check: assemble -> health check -> exit (CI)
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

The last line is `SMOKE OK` (exit 0) or `SMOKE FAILED` (exit 1); CI pipelines can assert on it.

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

### 32.9 Runtime Hardening: Health Checks, Auto-Revert and Sweeps (2026-09-12 feedback round)

> Feedback question: will self-evolution break itself? The answer is not a promise but **layered defenses, each verifiable** (every mechanism below is verifiable).

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

---

### 34.10 2026-09-12 Feedback-Round Additions (version policy / nasyncio / hardening / tree definitions)

| Item | Location | Note |
|---|---|---|
| version policy | this manual's header + all active documents | active documents use the current release as the code baseline (that chapter was written at **2.2.0**; the present baseline is **2.2.2**); historical revision numbers indicate their own era only; archived documents stay as-is |
| asyncio and nasyncio coexist | §4.7 + Chapter 19 FAQ | the standard `asyncio` and the self-developed `norpagent.nasyncio` do not conflict and can coexist in one process (not depending on it means no takeover) |
| evolution runtime hardening | §32.9; `evolution/hotswap.py` / `evolution/proposals.py` | `verify_active` / `activate(health=...)` auto-revert / `health_sweep` / `bootstrap` startup sweep |
| explicit CNB tree definitions | §30.19; `cnb/tree.py`; `norpagent tree validate|show|up` | no preset shape; three sources; item-by-item required-parameter errors; both assembly shapes; remount reshape / watched reshape / auto-reconcile; npa startup config errors never block startup |


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

> **Version policy (2026-09-12 feedback round)**: this manual and all active documents use the current release **2.2.2** as the code baseline; version numbers in the historical revision notes below indicate the baseline of their time only, not the present state; archived documents (old manuals, historical update excerpts) stay as-is.
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
> **2026-09-05 v1.0.7 (CNB kernel integration)**: (1) **Structure** — the whole nervous-bus implementation moves into the kernel submodule `norpagent.cnb/` (protocol / topology / permissions / bus / node / cortex / cli / demo + a new `engine` binding layer); the version merges into norpagent (no separate version); `import norpagent` makes CNB ready (top-level `norpagent.cnb` plus `CnbAdapter` / `setup_cnb` / `KERNEL_ACTIONS`). The old standalone package name `nervous_bus` stays as a **compatibility shim** (re-export + sys.modules submodule injection + physical thin cli/demo files) — scripts / commands / tests from 1.0.6 and earlier keep working unchanged. (2) **Capability surface** — `NervousNode` gains an exec **action registry** (`register_action` / `unregister_action` / `list_actions`); cortex `cmd.exec` actions route to registered handlers first, legacy `on("exec")` callbacks fall back, and unknown actions are rejected node-side (`ok=False` + top-level `error`; contract upgrade). The engine binding layer registers the NorpEngine public API as a **14-action kernel surface**: task (`run_task`/`status`/`stop_task`), state (`engine_state`/`inspect`), snapshot (`snapshot`/`rollback`/`undo`/`redo`/`list_snapshots`/`mark_good`), ops (`remount`/`reload_plugins`/`stop_engine`). `cmd.stop` (stops tasks, instance stays running) and `cmd.reload` (env re-read + plugin hot reload) keep their semantics. (3) **Runtime** — `norpagent cortex/node` (and `main.py --norp-cortex/--norp-node`) now **assemble a full kernel engine by default**: every neural atom is a real task-capable norpagent instance (default minimal/mock, zero third-party deps; `--mode`/`--model` selectable; `--bare` returns to the plain nervous shell; the cortex = the top-level norpagent instance). `stop_engine` replies first, then stops the engine gracefully after 1s and deregisters the node; CLI processes exit naturally. (4) **Uplink** — heartbeats carry kernel state (`engine_state`/`active_tasks`/`version`/`actions`, visible in cortex `reports`); `task_started`/`task_done` events go uplink (full task lifecycle visible at the cortex). (5) `runtime/cnb.py` stays as a forwarding layer (engine.py untouched); `norpagent.cli` and `main.py` forward to the new path. See §30.16. Every active version number is unified to **1.0.7**.
>
> **1.0.2 revision (CNB ships with the package)**: fixes the PyPI 1.0.1 package missing the Central Nervous Bus (CNB) — `nervous_bus/` moves from the repository root into `src/nervous_bus/` and is shipped with the package (`pip install norpagent==1.0.2` now includes CNB); the `norpagent` command gains the neural-tree subcommands `cortex / node / topo / ping / exec / stop / reload / perm / reports / audit / sync` (equivalent to `python -m nervous_bus.cli ...`; the legacy `--norp-cortex` / `--norp-node` spellings are forwarded automatically); running from the repository source is adapted by a src-path bootstrap at the top of `main.py` / `api.py`; every active version number is unified to 1.0.2 (`pyproject.toml`, `src/norpagent/__init__.py`, the recovery submodule `__version__`, the multimodal UA string are all in sync).
>
> **2026-09-05 deep-tree fix (CNB kernel B1–B9, audit-driven remediation)**: the kernel was "self-consistent on shallow trees, broken on deep trees" — the official suites only covered ≤2-level flat scenarios (atoms mounted straight on the cortex) and never ≥3-level chained forwarding; a five-level tree exposed hard defects on all three main paths (registration / uplink / link-loss): 9 issues, 3 high severity (B1 deep-registration collapse — forwarding overwrote `via` at every hop so the cortex re-parented deep nodes; B2 middle layers recorded heartbeat/events without forwarding, leaving the cortex blind to deep nodes; B3 a middle layer exiting made the cortex cascade-deregister a whole live subtree into orphans). All fixed: `via` now uses `setdefault` so the original direct parent survives the chain; uplinks converge hop by hop and upper-layer rejections are echoed back to drive deep self-healing; new rescue logic `_rescue_children` + the `cmd.reroot` re-parent command keep live subtrees alive; permission decisions are now pure time-order (a type-level revoke is no longer shadowed by an older node_id grant); the cortex's lost-node sweep thread is wired up (`sweep_dead` finally called: dead detection → rescue → grace-then-drop); hello ancestor chains are de-duplicated; heartbeats accept custom status fields; topology broadcasts auto-fire debounced after register/deregister/rescue. See §30.14. Every active version number is unified to **1.0.4** (`pyproject.toml`, `src/norpagent/__init__.py`, the recovery submodule `__version__`, the multimodal UA string are all in sync).
> **2026-09-05 v1.0.6 increment (deep-tree convergence closure + permission-plane audit, verified on a running tree)**: ① **Gap A** — after the cortex's sweep had deregistered a lost leaf and auto-broadcast, receivers still did not converge, because `cmd.topology.sync` was add-only: the cortex audit showed `deregister: probe-x` → `topology broadcast: 11 ok`, yet middle-layer rnd's heartbeat `descendants` still listed probe-x for 150s+ (verified live). `cmd.topology.sync` is now an **authoritative snapshot mirror**: prune (cascade-deregister local nodes absent from the snapshot, self excluded) + parent-pointer convergence (align to the cortex view via `set_parent`); transient gaps self-heal through "heartbeat rejected → auto re-register". ② **Gap B** — exec permission denials and perm changes now uplink `report.audit` (`perm.denied` / `perm.changed`) hop by hop to the cortex; the cortex keeps structured permission-operation records and exposes a merged view `perm_audit(n)` (REPL `perm_audit` + ctrl `op=perm_audit`) for same-permission audit reads. See §30.15. Every active version number is unified to **1.0.6**.
> **2026-09 revision (CNB env auto-mount + task-level cancellation + manual alignment)**: ① **P0-1 landed** — ordinary norpagent instances (np()/GUI/embedded) read the `NORP_CNB_*` env vars at assembly time and auto-mount as nervous-tree nodes (new `norpagent/runtime/cnb.py`: CnbAdapter + background mount thread + registration retry + degrade-to-plain-instance on failure; `NORP_CNB_MANAGED=1` skips kernel mounting so an upper layer can build its own node — no double mounting; the shutdown path unmounts); the four cortex downlink callbacks now land on real engine control points: `exec` (action whitelist `run_task` / `status` / `stop_task`; missing-prompt and unknown-action requests are rejected; audit receipts; `report.event` task_done uplinks), `stop` (`stop_all_tasks()` stops every in-flight session task while the instance stays RUNNING), `reload` (re-reads the CNB env config and hot-reloads external plugins through the remount machinery), `perm_changed` (permission summary recorded and audited; the permission table is enforced before every cmd.exec). ② **P2-1 task-level cancellation** — the loop layer gains the optional `submit_async` extension (`NasyncTaskHandle`, deep per-task cancel, still covered by Ctrl+C / engine-stop full cancellation), and the engine gains `submit_async` / `cancel_task` / `stop_all_tasks` / `active_tasks` / `forget_task`. ③ **P1-1/P2-2 alignment** — `--help` now shows the CNB subcommands; §30.8/§30.12/Appendix J are rewritten to the real implementation locations (`runtime/engine.py` + `runtime/cnb.py`; the fictional `api.py AgentAPI._setup_cnb()` and config.json key claims are removed — the contract is env vars only).
>
> **1.0.1 revision (version milestone)**: the 0.9.x line concludes and the project enters the **1.0.x series** — all active version numbers are unified to 1.0.1 (`pyproject.toml`, `src/norpagent/__init__.py`, the recovery submodule `__version__`, the multimodal UA string are all in sync); the 1.0 series carries every capability delivered so far: multimodal (vision + sound), the Central Nervous Bus (CNB) multi-instance neural tree, rescue mode, 29 hooks, and the plugin system.
> **0.9.9 revision (multimodal)**: new **Chapter 29 "Multimodal: Vision and Sound"** and **Appendix I "Multimodal Configuration and API Quick Reference"** — vision: upload / paste / drag images, the backend `/api/vision` endpoint has an external vision service describe them, and the description flows into the conversation; sound: speech output (TTS) and speech input (STT) are **fully implemented on the backend** (Windows SAPI / macOS say / Linux espeak-ng offline, or configurable OpenAI-compatible services), the notification tone is generated by the backend, the browser only captures and plays — nothing depends on browser-native speech APIs; `/api/upload` now supports images; `tts_service_api_key` / `stt_service_api_key` are stored DPAPI-encrypted like `api_key`.
> **2026-08 Central Nervous Bus (CNB) multi-instance upgrade**: new **Chapter 30 "Central Nervous Bus: Multi-Instance and the Neural Tree"** and **Appendix J "Central Nervous Bus Quick Reference"** — the cortex (the highest norpagent instance) controls the operation permissions of any atom at any level through the Central Nervous Bus; lower levels may only report upward through the bus and can never control upper levels; the neural tree is a tree-shaped topology chain; lower levels obey higher-level commands unconditionally and are forbidden to rewrite higher levels — they may only report back. The full `nervous_bus/` module set (protocol layer / tree topology / neural permission table / zero-dependency transport / node / cortex / CLI) `main.py` gains the GUI-less `--norp-cortex` / `--norp-node` multi-instance entry (bypassing the single-instance lock), and `api.py` lets a GUI instance join the neural tree as a node.
> 2026-08 revision: Chapter 27 minimal kernel in depth (EventBus / the slot connector ArchLayer / the Registry / the address resolver: data structures, APIs, internals and a startup + hot-mount collaboration walkthrough) | Chapter 26 registration flow in detail (the Registry's 9 namespaces / four value forms and string semantics / the full npa() assembly pipeline / three registration timings and hot reload / slot registration vs component registration / validation and error handling / a checklist) | Chapter 25 developer practice (module / slot / plugin / tool development in depth; slot development contract incl. the hot-reload red line: dict key-value pairs must be valid modules; architecture overview and the minimal main async-loop core) | Chapter 24 rescue mode (low-level loop control + human takeover) | kernel fix: select timeout clamp (far timers crashed the loop on Windows) | 15.6 human-rescue manual tool takeover API (v0.9.3; operate all tools by hand when the model is down: tools / tool-call / manual / serve) | 3.9 task-level slot injection (submit(slot_overrides=...)) | 3.7 in-flight task races of assembly-slot hot rebuilds and the drain recommendation | 4.6.4 daemon worker-pool queue semantics and the stuck-task fallback matrix | 23.1 EventBus benchmark baseline and lock-contention boundary
> **0.9.7 revision**: human rescue supports manual control of custom tools (`RescueToolEnvironment` gains `extra_tools` / `tools` / `plugin_dirs`; the CLI gains `--tools` / `--plugin-dirs`; the inventory and the operator page tag each tool with builtin / custom / plugin origin) | the general-purpose event bus (GeneralEventBus; the class stays `EventBus`) gains generic capabilities: `once` / `wait` / `emit_all` / `subscriber_count` / `has_listeners` / `clear` | Chapter 9 gains 9.8 "all 29 hooks, one by one (Python code)" | new Chapter 28 "External Python Script Integration: Hot Mounting and Hook Subscription" | new Appendix F (frontend-backend communication quick reference) / Appendix G (all commands quick reference) / Appendix H (all functions and structures quick reference) | Chapter 13 command-line entry expanded (console-frontend entry + rescue-mode commands) | terminology unified (EventBus is called the GeneralEventBus in this manual; code symbols unchanged)

---

*NorpAgent Developer Manual · v2.2.2 · FarStars (远星) · Copyright (c) 2026 xingluosama121, MIT Licensed*

