# P02: latch all affected tasks before cleanup

Date: 2026-10-19 (Asia/Calcutta). Bounded gate: BA-01 repaired; P01 preserved.
P03 was not started. Full STOP, backend and release acceptance remain open.

## Prerequisites and tested source

The checkout was clean on `ui-wiring` at local/remote
`eab9d8d70ce2abbf45e0171501678a3c41736299`. Read the current handoff, shared
contract/P02 prompt, immutable specification (already completely read in P00,
unchanged), sections 12-13, Build Plan Phase 1 and acceptance G-02/F-08.
The requirements checker passed: 298 source items / 324 rows. A fresh P01
prerequisite run passed **22 checks in 2.68s**, before production edits.

The original BA-01 raw reproduction failed before editing: **1 failed in
0.58s**, exit 1, `First cleanup grace observed stop latches
[(True, False), (True, True)]`. Reports are ignored under `output/p02/`.
The final tested source is the P02 commit containing this record, parent
`eab9d8d`; runtime/test identities are:

| File | Git blob |
|---|---|
| `pluma/core/task_supervisor.py` | `2d39642e31c9518e58dac802a756bf9fec538318` |
| `tests/unit/test_backend_wiring_audit.py` | `b7819fdf0bc14cf42d8ed178196236621e761c80` |
| `tests/unit/test_global_stop_ordering.py` | `43213c73245a772ef603aface3d2f36b25e9e776` |
| `tests/fixtures/desktop_isolation.py` | `7eee91c596d69d67d9cf40b74df17dedbffbd370` |

P01's cancellation/registry source and admission tests are unchanged.
`output/p02/focused-final.json`, `raw-final.json` and `regression-isolated.json`
record full command vectors, working-file SHA-256,
environment, isolated roots, exit codes and wall durations. Git blob IDs
normalize checkout line endings. Reports/JUnit are not committed.

## Latch, cleanup and request-race contract

Global STOP serializes publication, snapshot, all token latches and cleanup
claims under a short admission/state lock. Every affected nonterminal capsule
is latched before the first STOPPING claim and before any grace wait, worker
termination, rollback or resource cleanup. Already terminal tasks are excluded
and retain their state, timestamps and cancellation metadata. The same capsule,
token, supervisor and P01 executor admission boundary are retained.

Cleanup ownership is claimed once through STOPPING. Repeated task/global STOP
during STOPPING or ROLLING_BACK does not re-enter cleanup. Single-task STOP
also latches through the short lock, preserving first-cancellation reason.
The existing owned cleanup body runs after that lock is released. Terminal
resource cleanup may still use the older resource/state lock, but cannot hold
the latch boundary hostage. State publication uses the short lock so a racing
start/success transition cannot bypass STOP's claim. Code needing both locks
acquires the old lock first; latch code releases the short lock before cleanup.
No thread, worker, background cleanup branch or separate cancellation tree is
introduced.

Task creation follows an explicit ordering:

- Publication before the snapshot includes the new capsule in STOP.
- Creation while any global STOP invocation is active fails with
  `TaskCancelledError` before allocating a new Job Object.
- Preparation that spans a STOP generation is rejected before publication,
  even if STOP has already returned. The unpublished capsule is latched and
  its prepared Job Object/snapshot resources are closed. It cannot later
  become an executing command.
- A new explicit request after all overlapping global STOP calls return can
  proceed. There is no silent retry of an older rejected request. A task-specific
  cleanup can still be pending after a repeated global call returns; that
  task's latch remains permanently set.

The synchronous global method still returns affected candidate IDs. It does
not provide a new typed acknowledgement or promise verified terminal cleanup.
BA-08's IPC/result defect remains for P08. BA-02's blocked termination and
BA-04's cleanup-failure accounting are also unchanged. Keeping admission closed
while an owning global STOP remains blocked is intentional; P03 must make the
owned wait interruptible rather than reopen admission prematurely.

## Executed checks (E07)

Environment: Windows 11 build 26200, Python 3.12.10 x64, pytest 8.3.3. Each
run used unique user-local LOCALAPPDATA/APPDATA/TEMP/TMP directories with
inherited `PLUMA_*` overrides removed. Tests enable test/audio emulation through
the existing conftest. Each case has a 20-second thread timeout; each outer
process is bounded to 180 seconds. Fixture credentials remaining: zero.
No production resident, hotkey, microphone, model, elevation operation,
security-policy change or raw capture was activated. The final FAST regression
uses explicit inert clipboard/window/app-close adapters as described below.

New P02 cases use inert jobs/workers and controlled joined threads; the native
event case reads actual Windows latch handles. P01's actual spawned-worker/
Job Object cases and existing owned process fixtures also run in the focused
suite. None substitutes for combined P10 or physical hotkey acceptance.

Common options for the final runs:

```text
-q -o addopts= -o junit_family=xunit1 --timeout=20 --timeout-method=thread --tb=short -ra -p no:cacheprovider
```

Every command also receives `--junitxml=<output/p02/run-name.xml>`.

```powershell
python -m pytest tests/unit/test_executor_admission.py tests/unit/test_backend_wiring_audit.py::test_stop_during_prestate_prevents_executor_start <common options>
# Prerequisite, before editing: 22 passed in 2.68s; exit 0; wall 3.408s.

python -m pytest tests/unit/test_backend_wiring_audit.py::test_global_stop_latches_every_task_before_first_grace --runxfail <common options>
# Before editing: 1 failed in 0.58s; exit 1; wall 1.258s.

python -m pytest tests/unit/test_global_stop_ordering.py tests/unit/test_executor_admission.py tests/unit/test_task_supervisor.py tests/unit/test_tool_runner_ledger.py tests/unit/test_schemas.py tests/unit/test_ownership.py tests/unit/test_job_object.py <common options>
# Final: 100 passed in 7.45s; exit 0; wall 8.364s.
```

The prerequisite/before runs preceded the JUnit xunit1 reporting option; their
exact vectors are retained in their JSON. An initial focused run passed 98
checks with four JUnit `record_property` compatibility warnings. Selecting
xunit1 in the ignored runner preserves timing properties without warnings;
two further cases bring the final focused total to 100. Product/test assertions
were not suppressed or weakened.

Twenty-two new ordering cases cover blocked grace, worker, rollback and resource
cleanup; actual registry rejection for a later latched task; native event
readback; all latches before the first state claim; overlapping global/task
STOP; repeated rollback STOP; five terminal states; preparation across a
completed STOP; no allocation during STOP; terminal cleanup holding the old
lock; start/success races; cleanup failure without omitting later tasks; actual
SQLite final-state/reason/timestamp readback; and empty/repeated global STOP.
The original BA-01 assertion is unchanged; only its xfail marker is removed.

```powershell
python -m pytest tests/unit/test_backend_wiring_audit.py tests/unit/test_schemas.py tests/unit/test_router.py tests/unit/test_brain_validator.py tests/unit/test_policy_engine.py tests/unit/test_redaction.py tests/unit/test_activity_ledger_lifecycle.py tests/unit/test_rollback_engine.py tests/unit/test_rollback_recipes.py tests/unit/test_tool_runner_ledger.py tests/unit/test_perception_freshness.py tests/unit/test_phase13_7_ui_verification.py tests/unit/test_phase13_7_created_stop.py tests/unit/test_ipc.py tests/unit/test_global_stop_ordering.py tests/unit/test_executor_admission.py tests/unit/test_fast_orchestrator.py tests/unit/test_multi_step_orchestrator.py -k "not test_elevation_broker_execution" -p tests.fixtures.desktop_isolation <common options>
# 441 passed, 3 skipped, 1 deselected, 9 xfailed in 21.94s; exit 0; wall 22.794s.

python -m pytest tests/unit/test_backend_wiring_audit.py --runxfail <common options>
# 9 failed, 6 passed in 0.84s; exit 1; wall 1.452s.
```

The nine raw failures are BA-02, BA-04/05/06, two BA-07 assertions, two BA-08
assertions and BA-09. BA-01 and BA-03 are ordinary passes. The three existing
no-ML corpus skips and one intentionally unexecuted elevation operation do not
count as acceptance or an approved limitation. This is the relevant regression
suite, not a complete unit/product/device/installed-artifact suite.

### Correction to inherited FAST test isolation

The earlier `regression-final` run (441 passes in 23.41s) used inherited FAST
fixtures that mock process verification but do not fully isolate desktop APIs.
Their clipboard helpers can clear/read the real clipboard; window helpers can
resolve the foreground window; close_app can invoke taskkill by application
name. That run was executed before this was caught. Its logs remain, but its
desktop-isolation claims are withdrawn. Actual prior clipboard/window/app
state was not captured; no no-impact or restoration claim is made. P01 used
the same inherited sub-suite, and its evidence now carries a correction note.

The final run explicitly loads `tests.fixtures.desktop_isolation`. Only the
inherited FAST module receives an in-memory clipboard, a no-target user32
adapter and blocked desktop termination commands. Other owned process/Job
Object/IPC/admission fixtures remain intact. Each FAST case records the fixture
boundary in JUnit properties. This proves route/orchestration behavior against
inert desktop state, not real window/clipboard/app acceptance. Existing
assertions remain unchanged; native desktop verification is still an open
P11/P24/P27 gate. No attempt was made to read or alter desktop state to guess
a restoration. Future bounded runs of this FAST suite must load the plugin.

Controlled fixture timings in focused JUnit, measured from the test's dispatch
start to the first cleanup boundary (after all latches), then through cleanup:

| Blocked fixture phase | Latch acknowledged (ms) | Completed cleanup (ms) |
|---|---:|---:|
| Grace | 2.381 | 3.349 |
| Worker termination | 0.373 | 0.899 |
| Rollback | 0.269 | 0.709 |
| Resource cleanup | 0.196 | 0.572 |

These are individual controlled observations with no hardware hotkey or p95
claim. Cleanup is held by an event until the test confirms all latches and
rejects later execution/requests. The event is then released and all threads
joined. Actual hotkey acknowledgement/latch and bounded real cleanup under
load remain separate P10/P26 measurements.

```powershell
python docs/completion/verify_requirements_matrix.py
# PASS: 298 source items, 324 traceable rows.
git diff --check
# Passed.
```

The separate final review (`python output/p02/review_final.py`, ignored) passed:
nine scoped files, runtime changes limited to the supervisor, unchanged P01/
locked sources, matching final source hashes and JUnit counts, only BA-01's
marker removed, seven remaining defects retained, resolved links and no
credential patterns. All 115 inherited FAST cases in the final report carry
the explicit desktop-isolation property. The earlier insufficiently isolated
run and P01 correction remain visible. No raw reports, models, build output,
credentials, audio or screenshots are staged.

## Remaining blockers and next milestone

Seven findings remain: BA-02 and BA-04 through BA-09. Full F-08/G-02 integration,
owned descendant termination, residual/ledger/IPC agreement, shutdown/voice,
credential creation, physical devices/UI, performance and release gates remain
open. UI action entry stays disabled. Master/build/acceptance definitions, UI
appearance, registered tools and P01 execution code are unchanged.

**Next eligible milestone: P03 only, BA-02 interruptible owned-worker waits.**
Reproduce `test_worker_stop_interrupts_outstanding_response_wait` with
`--runxfail`; separate execution serialization from cancellation/termination
ownership so STOP does not wait behind blocked response I/O. Preserve P01/P02,
bounded cleanup and PID/creation-time/task identity. Convert only BA-02's
reproduction, test startup/response/repeated disposal races and record actual
owned Windows descendant checks for P10. Do not automatically proceed to P03
or enable commands based on these bounded repairs.

## Recovery and GitHub

Pre-P02 recovery point: `eab9d8d70ce2abbf45e0171501678a3c41736299`. To inspect
without overwriting work, choose a new unused destination:

```powershell
git -C D:\Workspace\DEVEL\PLUMA worktree add --detach D:\Workspace\DEVEL\PLUMA-before-p02 eab9d8d70ce2abbf45e0171501678a3c41736299
git -C D:\Workspace\DEVEL\PLUMA-before-p02 status --short
```

Existing [recovery tags/archive/stash](../workspace_cleanup.md) and separate
worktrees are preserved. No reset, clean, deletion, force push, security bypass
or branch switch. The coherent P02 commit is pushed to `ui-wiring`, updating
[draft PR 2](https://github.com/sai161812/pluma/pull/2), still targeting
`ui-polish-integration`. [PR 1](https://github.com/sai161812/pluma/pull/1) stays
draft/unmerged and `main` stays `6dbf589`. No prior UI CI result is represented
as testing this new backend commit.
