# P05: authoritative terminal results and history

Date: 2026-10-19 (Asia/Calcutta). BA-05's bounded gate passes; P01-P04 remain
green. P06 is next and was not started. Full STOP, backend, device/UI,
installed-artifact and release acceptance remain open.

## Prerequisites and source

Started clean on local/remote `ui-wiring` at
`8956cb7ec669df89b79e98c411e4c90f63016be0`. Verified remotes, four worktrees,
unchanged main/integration and both draft/open/unmerged PRs. The immutable
master was read completely in P00 and is unchanged; reread relevant sections
12-16, AGENTS, the shared contract/P05, handoff, Build Plan Phases 1/2/3/5/10,
technology contract, F-05/F-07/F-08/G-02/G-03/G-06/G-07/G-10 and final gates.
Inspected current routes, supervisor, storage, IPC, tests and UI references.
The native dark UI and disabled action entry remain unchanged.

Before editing, matrix coverage passed **298 source items / 324 rows**.
P01-P04 plus four ordinary audit regressions freshly passed **111 checks in
13.72s**. BA-05 reproduced with `--runxfail`: **1 failed in 0.63s**:
`Supervisor STOPPED_WITH_RESIDUAL; returned STOPPED; ledger STOPPED`.
The original assertion is unchanged; only its strict marker is removed.
`output/p05/prerequisite.*` and `before.*` retain original source hashes/output.

Final tested source is the P05 commit containing this record, parent `8956cb7`:

| File | Git blob |
|---|---|
| `pluma/core/task_supervisor.py` | `44817a62014daddca4dc9684ec94962d3900eaa4` |
| `pluma/core/orchestrator.py` | `732f04c4dfac23c3726edf3451e1c46442c36cfe` |
| `pluma/core/multi_step.py` | `72693a9776ee4a287ba2045842b8cd18de5af420` |
| `pluma/core/resident.py` | `3146d153374f323962b49a9a84d8624eb72bb435` |
| `pluma/memory/activity.py` | `36727dc344ac186d2b1603256642aa849e7b6163` |
| `tests/unit/test_terminal_outcome.py` | `2863b244d15044d5bce5a8c0b2f33cfc6b390d7f` |
| `tests/unit/test_backend_wiring_audit.py` | `6114aec2362d044100334c82a1b578a341b45fba` |
| `tests/unit/test_fast_orchestrator.py` | `b224474eadc452ca9adce4989fafced4b4b6cf1c` |

Only these five runtime files, three test files and four handoff/evidence
files change. Cancellation, registry, worker pipe, native ownership/jobs,
rollback engine/recipes, database writer/migrations, P01-P04 tests and desktop
isolation are unchanged. JSON reports include their hashes as applicable.
Git blobs normalize checkout line endings; reports record exact SHA-256,
parent, platform, isolated roots, commands, exit codes and wall duration.

## Terminal outcome contract

- Routes propose an outcome; `TaskSupervisor.finalize_task` returns its actual
  capsule state. Existing terminal outcomes are not overwritten by another
  route-local SUCCEEDED/FAILED/STOPPED value. STOP claim and terminal commitment
  share the short admission boundary. A latch that wins before commitment
  takes the STOP path; a task already committed before a later STOP retains its
  outcome. No cleanup, SQLite I/O or wait is added under that short lock.
- Multi-step STOP/failure and FAST failure use the supervisor's existing owned
  cleanup/rollback owner. They do not independently roll back or decide clean
  STOP. Cancellation at registry admission and planning failure after STOP
  project that same state. Partial undo, non-undoable markers, deferred work and
  cleanup errors retain P04 evidence and remaining pre-state.
- Explicit low-level `transition` still rejects illegal transitions. The
  idempotent route completion API preserves terminal state/timestamp/evidence.
  Overlapping STOP cleanup is awaited outside the state/resource lock, with a
  five-second event-wait bound. If not ready, projections expose the actual
  STOPPING/ROLLING_BACK state with `completion_verified=false` and pending copy.
  That is not a stopped/successful result. The bound is per wait, not a
  whole-request/hotkey/p95 performance claim.
- `completion_verified` identifies finished terminal finalization, not success
  of every effect. `terminal_persisted` is true only after terminal readback,
  false when unverified, and null when no ledger is configured (inert legacy
  fixtures only; application runtime supplies the ledger). `has_residual`,
  rollback attempt/verification and redacted typed cleanup evidence are
  projected into task results, direct multi-step results and execute IPC.
  Deferred rollback does not claim rollback performed. Success additionally
  requires a SUCCEEDED state and finished terminal finalization.
- Existing deterministic tool messages and redaction remain. Terminal
  reconciliation uses fixed factual templates for STOP, pending cleanup and
  conservative failure. It never reports a stale successful step summary as
  successful task completion after cleanup/storage failure. No model narrative,
  raw exception, tool argument or private native handle is added to evidence.
- `ActivityLedger.finalize_task` atomically writes terminal fields, the cleanup
  journal and existing task's resource mirror, then reads them back. The real
  request is inserted before starting/routing so early cancellation has factual
  history. Missing history is an error; no fabricated request/input is inserted
  during reconciliation. Ledger-owner mismatch is rejected. Route code no
  longer writes its local terminal value independently.
- A failed terminal write/readback makes clean STOP residual or success FAILED,
  retains a fixed persistence marker, and queues one conservative retry after
  the first queued transaction. SQLite acknowledgement timeouts do not cancel
  writes. FIFO retry ordering prevents a late original SUCCEEDED/STOPPED write
  from being the last durable value. Unavailable storage exposes
  `terminal_persisted=false`; the prior/missing history is not claimed current.
  An explicit later finalization retries the same conservative state without
  repeating cleanup, rollback, changing timestamp or growing duplicate failure
  evidence. There is no new background retry/recovery executor.
- Terminal owners are not pruned before finalization completes. Unresolved
  evidence/ownership remains retained under P04. Existing normal terminal
  cleanup and actual worker/job containment remain active.

Execute IPC adds outcome fields to the existing authenticated response. Its
`status=ok` means the request was handled; `success`, actual `final_state`,
completion, persistence and residual fields describe the task. The existing
STOP acknowledgement payload is **still defective BA-08**, reserved for P08.
No protocol/event/UI wiring, runtime shutdown or voice lifecycle work is claimed.

## Checks (E10)

Windows 11 build 26200, Python 3.12.10 x64, pytest 8.3.3. Unique isolated
LOCALAPPDATA/APPDATA/TEMP/TMP per run; inherited PLUMA_* overrides removed.
Existing conftest enables test/audio emulation. Fixtures use owned
processes/jobs/files/pipes, real SQLite and inert planner/perception/device
adapters. The P05 transport case uses an owned authenticated native Windows
pipe and checks execute/recent-history responses. No microphone, model,
physical desktop action, elevation or security-policy bypass was activated.
All 115 inherited FAST cases have desktop-isolation properties; load the
explicit plugin below and preserve the P02 isolation correction. Fixture keys
remaining: **zero**. No raw captures/model/runtime output is committed.

Exact selected commands/output (outer subprocess bound 180s):

```powershell
python -m pytest tests/unit/test_cleanup_evidence.py tests/unit/test_backend_wiring_audit.py::test_failed_worker_cleanup_requires_residual_state tests/unit/test_worker_cancellation.py tests/unit/test_executor_admission.py tests/unit/test_global_stop_ordering.py tests/unit/test_backend_wiring_audit.py::test_worker_stop_interrupts_outstanding_response_wait tests/unit/test_backend_wiring_audit.py::test_stop_during_prestate_prevents_executor_start tests/unit/test_backend_wiring_audit.py::test_global_stop_latches_every_task_before_first_grace -q -o addopts= -o junit_family=xunit1 --timeout=20 --timeout-method=thread --tb=short -ra -p no:cacheprovider --junitxml=output/p05/prerequisite.xml
# 111 passed in 13.72s; pytest exit 0; outer wall 14.569s.
```

```powershell
python -m pytest tests/unit/test_backend_wiring_audit.py::test_fast_stop_preserves_supervisor_residual_outcome -q -o addopts= -o junit_family=xunit1 --timeout=20 --timeout-method=thread --tb=short -ra -p no:cacheprovider --junitxml=output/p05/before.xml --runxfail
# 1 failed in 0.63s; pytest exit 1; outer wall 1.513s.
```

```powershell
python -m pytest tests/unit/test_terminal_outcome.py tests/unit/test_db.py tests/unit/test_cleanup_evidence.py tests/unit/test_rollback_engine.py tests/unit/test_rollback_recipes.py tests/unit/test_worker_cancellation.py tests/unit/test_global_stop_ordering.py tests/unit/test_executor_admission.py tests/unit/test_task_supervisor.py tests/unit/test_tool_runner_ledger.py tests/unit/test_schemas.py tests/unit/test_ownership.py tests/unit/test_job_object.py -q -o addopts= -o junit_family=xunit1 --timeout=20 --timeout-method=thread --tb=short -ra -p no:cacheprovider --junitxml=output/p05/focused-final.xml
# 228 passed in 22.34s; pytest exit 0; outer wall 23.35s.
```

```powershell
python -m pytest tests/unit/test_backend_wiring_audit.py tests/unit/test_schemas.py tests/unit/test_router.py tests/unit/test_brain_validator.py tests/unit/test_policy_engine.py tests/unit/test_redaction.py tests/unit/test_activity_ledger_lifecycle.py tests/unit/test_rollback_engine.py tests/unit/test_rollback_recipes.py tests/unit/test_tool_runner_ledger.py tests/unit/test_perception_freshness.py tests/unit/test_phase13_7_ui_verification.py tests/unit/test_phase13_7_created_stop.py tests/unit/test_ipc.py tests/unit/test_terminal_outcome.py tests/unit/test_cleanup_evidence.py tests/unit/test_worker_cancellation.py tests/unit/test_global_stop_ordering.py tests/unit/test_executor_admission.py tests/unit/test_fast_orchestrator.py tests/unit/test_multi_step_orchestrator.py -q -o addopts= -o junit_family=xunit1 --timeout=20 --timeout-method=thread --tb=short -ra -p no:cacheprovider --junitxml=output/p05/regression-isolated.xml -k "not test_elevation_broker_execution" -p tests.fixtures.desktop_isolation
# 553 passed, 3 skipped, 1 deselected, 6 xfailed in 36.87s; pytest exit 0; outer wall 38.06s.
```

```powershell
python -m pytest tests/unit/test_cleanup_evidence.py tests/unit/test_backend_wiring_audit.py::test_failed_worker_cleanup_requires_residual_state tests/unit/test_worker_cancellation.py tests/unit/test_executor_admission.py tests/unit/test_global_stop_ordering.py tests/unit/test_backend_wiring_audit.py::test_worker_stop_interrupts_outstanding_response_wait tests/unit/test_backend_wiring_audit.py::test_stop_during_prestate_prevents_executor_start tests/unit/test_backend_wiring_audit.py::test_global_stop_latches_every_task_before_first_grace -q -o addopts= -o junit_family=xunit1 --timeout=20 --timeout-method=thread --tb=short -ra -p no:cacheprovider --junitxml=output/p05/prerequisite-final.xml
# 111 passed in 10.89s; pytest exit 0; outer wall 11.698s.
```

```powershell
python -m pytest tests/unit/test_phase13_8_final_patch.py::TestTaskOwnedWorkerContainment -q -o addopts= -o junit_family=xunit1 --timeout=20 --timeout-method=thread --tb=short -ra -p no:cacheprovider --junitxml=output/p05/containment.xml
# 3 passed in 2.95s; pytest exit 0; outer wall 3.749s.
```

```powershell
python -m pytest tests/unit/test_backend_wiring_audit.py -q -o addopts= -o junit_family=xunit1 --timeout=20 --timeout-method=thread --tb=short -ra -p no:cacheprovider --junitxml=output/p05/raw-final.xml --runxfail
# 6 failed, 9 passed in 0.64s; pytest exit 1; outer wall 1.309s.
```

```powershell
python docs/completion/verify_requirements_matrix.py
# PASS: 298 source items, 324 traceable rows.
git diff --check
# Passed.
python output/p05/review.py
# Separate review: scope, immutable source, audit assertions/markers, P01-P04
# ownership/latch invariants, hashes, JUnit/isolation, blobs, links and secrets.
```

The **45 new cases** cover STOP on all four routes, normal completion/cleanup
failure, real partial move rollback with conflicts and remaining undo pre-state,
non-undoable markers, empty FAST plan, planning errors after STOP, pre-routing
cancellation, last-step SUCCEEDED/FAILED races, failure recovery, direct
multi-step projection, persistence/readback failure, missing rows, repeated
finalization and a still-pending result. Real SQLite tests reopen history,
compare journal/resource mirror, reject an aborted transaction atomically and
block the actual queued writer to prove late-commit ordering. Outage injection
explicitly verifies missing/unverified history then reconciles on recovery.
Owned worker/root/descendant survival/exit checks from P03/P04 pass unchanged.

Initial iterations are retained, not acceptance: `prerequisite-post` had two
low-level transition regressions, corrected without changing the P02 assertions.
`focused-initial` had eleven failures from fixture schema/undo keys and the
FAILED-vs-STOP race; `focused-second` had seven, corrected schema and transition
ordering. Subsequent focused runs passed. The first regression run had one
obsolete mock call-count assertion; `test_fast_orchestrator` now asserts the
route write and authoritative atomic terminal state/evidence payload. Real
SQLite assertions are independently covered. Review additionally added pending
multi-step and insert-to-start STOP cases. Intermediate names include
`*-review-before` and `focused-final-before-stop-storage`; final artifacts are
`focused-final`, `regression-isolated`, `prerequisite-final`, `containment` and
`raw-final`. No remaining audit assertion/setup was changed.

Three inherited corpus skips, one excluded elevation operation and six strict
expected failures are not passes or owner-approved limitations. The six raw
failures remain BA-06, both BA-07, both BA-08 and conditional BA-09. This gate
is not full unit/product/device/install, actual irreversible external commit,
physical hotkey/microphone/planner/OCR, filesystem adversary or performance
acceptance. A simulated store outage cannot prove durable history while the
store is unavailable; the returned flag states that fact and no success is
claimed. No locked requirement is waived.

## Remaining blockers, next milestone and Git

**Four findings remain: BA-06 through BA-09**, six raw failures. Runtime drain,
voice capture/empty capsule, truthful typed STOP acknowledgements and private
first credential creation remain. Full mandatory tool/policy/undo, screen,
planner/STT/native device, UI, recovery, measurements and release gates remain
in the matrix. Action entry stays disabled; native dark UI is unchanged.

**Next safe milestone: P06 only.** Reproduce BA-06, reject new work during
shutdown, latch/cancel/drain handlers and owned work, include retained terminal
and unpublished-preparation owners, verify cleanup, persist outcomes, close
registry before storage, and prove bounded/idempotent shutdown with real owned
descendants at P10. P05 does not start P06, P07, P08, P09 or enable actions.
P10 later combines P01-P09 paths; P26 owns performance and P27 recovery/races.

Commit/push target is authorized `ui-wiring`, ordinary non-force push. PR
[2](https://github.com/sai161812/pluma/pull/2) remains draft/open/unmerged toward
`ui-polish-integration`; PR [1](https://github.com/sai161812/pluma/pull/1) remains
draft/open/unmerged toward `main`. Main stays `6dbf589`, integration `9544752`.
Pre-P05 recovery: `8956cb7ec669df89b79e98c411e4c90f63016be0`; inspect with
`git worktree add --detach <new-folder> 8956cb7ec669df89b79e98c411e4c90f63016be0`.
Preserve existing worktrees, tags, stash and archives per
[workspace recovery](../workspace_cleanup.md). No merge, branch/worktree switch,
reset/clean, force push or security-policy change was performed.
