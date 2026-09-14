# NORP Agent Test Suites

> This document gathers **all test-suite material** from the NORP Agent Developer Manual: the former Chapter 17 "Testing and Debugging", the per-chapter "How to Verify / Verification / Test Matrix" subsections, and the test-command quick reference.
>
> The developer manual no longer contains any test-suite chapter — the sections below were removed from the manual and moved here: 14.4 How to Verify, Chapter 17 Testing and Debugging, 23.5 How to Verify, 24.2.6 Violent Stress Suite, 30.11 Tests and Verification, 30.16.6 Test Matrix, 30.18.5 Verification, 30.19.7 Verification, 32.8 Verification, 34.9 Acceptance, Appendix J.7 Test Commands.
>
> Baseline: **2.2.2** | Language: English (Chinese version: [`测试套件.md`](测试套件.md)) | [Back to index](README.md)

---

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

**Test defense**: new `src/nervous_bus/test_deep_tree.py` (30 checks on a 4-level chain): registration + crash + sweep + permission timing + heartbeat status + auto-broadcast are fully covered; test_cnb T48 (formerly "cascade deregistration") now asserts the "live child promoted by rescue" semantics.
- Regression: `test_deep_tree` gains D13a–f — probe-x hangs directly under middle-layer rnd, is force-killed, the cortex sweep deregisters it, rnd's local topology prunes it, heartbeat `descendants` converge, and rnd's subtree view matches the cortex's (same id set). Suite 30→**36 all green**.
- Regression: `test_cnb` gains T-A0~T-A6 — revoke + denial + grant sequences verify the cortex sees the uplinked `perm.denied` / `perm.changed`, a **deep node's denial is forwarded through a middle layer to the cortex**, and the `op=perm_audit` view contains both cortex operations and uplinked node events. Suite 52→**60 all green**.
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

Verified (test matrix §30.11, `test_cnb_v200` S101~S109): the six elements
round-trip deep-equal (no loss); task_done carries mol_id + acceptance; the
audit trail is searchable by mol_id.
#### 30.18.5 Verification

`src/nervous_bus/test_cnb_slots.py` (51 checks), `test/test_cnb_kernel_actions.py` (32 checks) and the M4.5 violent mixed stress domain H (including the slot sub-domain) are all green.

#### 30.19.7 Verification

`test/test_cnb_tree_suite.py` (56 checks): three sources, item-by-item required-parameter errors, three parent forms, in-process assembly with diff reshape, file-watch reshape, auto-reconcile, multi-process process trees, np integration and error semantics, CLI — all green; the CNB family and M4.5 re-run green.

### 32.8 Verification

- `test/test_evolution_suite.py` (49 checks) all green;
- M4.5 violent mixed stress domain I (self-evolution: approvals / hot reload / packages / rhythm) all green.

Verification: `test/test_evo_hardening_suite.py` (19 checks: healthy pass / failure revert / custom revert / explicit failure without revert means / bad code refused / missing-file and tampered-original detection / sweep rollback + breaker / startup sweep / locked key refusal) green; the existing evolution suite (49) re-run green.
### 34.9 Acceptance

`test/test_v22_suite.py` (65 checks) green; the M4.5 suite extended (J16-J23 / K11-K14) and green; minimal kernel 147 / evolution 49 / CNB slots 51 / plugins 100 and the headless-browser frontend smoke all green; version numbers unified to 2.2.0.
**2026-09-12 feedback round additions**: `test/test_cnb_tree_suite.py` (56 checks, explicit neural-tree definitions) and `test/test_evo_hardening_suite.py` (19 checks, evolution runtime hardening) all green; M4.5 219 / v2.2 65 / minimal kernel 147 / evolution 49 / CNB family (60 / 44 / 36 / 13 / 57 / 12 / 51 / 32) re-run green.

Verification: `test/test_cnb_tree_suite.py` 56 and `test/test_evo_hardening_suite.py` 19 green; M4.5 219 / v2.2 65 / minimal kernel 147 / evolution 49 / CNB family (60 / 44 / 36 / 13 / 57 / 12 / 51 / 32) re-run green.
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

---

*NorpAgent Test Suites · v2.2.2 · FarStars (远星) · Copyright (c) 2026 xingluosama121, MIT Licensed*
