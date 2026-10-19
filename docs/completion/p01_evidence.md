# P01: STOP versus actual executor admission

Date: 2026-10-19 (Asia/Calcutta). Bounded outcome: BA-03 repaired. P02 was not
started. This is not complete STOP, backend, voice, UI or release acceptance.

## Prerequisites and source

- Started from clean `ui-wiring`, local and remote
  `81cd450e8991f549f7605bebfb9231cf1e063452` (completed P00).
- `python docs/completion/verify_requirements_matrix.py` passed before editing:
  298 source items / 324 traceable rows. The master specification, agent
  contract, relevant Build Plan Phase 1/2/10 gates, acceptance F-08/G-02 and
  P01 prompt/current handoff were read. The immutable specification remains
  unchanged from the completely read P00 source.
- Verified remotes/worktrees and current GitHub PR state: PR 1 draft/open from
  `ui-polish-integration` into `main`; PR 2 draft/open from `ui-wiring` into
  `ui-polish-integration`. `main` remains `6dbf589`. No worktree was switched,
  user changes overwritten, PR merged/retargeted or history rewritten.
- Before changes, the raw BA-03 assertion failed: **1 failed in 0.54s**, exit 1,
  `Executor started after the latch was set: [True]`.
  `output/p01/before.txt` and `before.xml` retain the evidence.

The tested source is the P01 commit containing this record, whose parent is
`81cd450`. The final runtime/test Git blob identities are:

| File | Git blob |
|---|---|
| `pluma/core/cancellation.py` | `f8a55d26ed4bfafd6d38d4817a9a8958fdf635c1` |
| `pluma/tools/registry.py` | `b9cb6e8c3e4e232ab384eac096f14be3986e92f7` |
| `tests/unit/test_executor_admission.py` | `7485a112d8d91c3314caa508738541828c4a3710` |
| `tests/unit/test_backend_wiring_audit.py` | `401c4cb317250b082530e0716ed2cfa4a5c86c39` |

Ignored `output/p01/*-verified.json` records working-file SHA-256 hashes, full
command vectors, environment, isolated roots, exit codes and wall durations.
Git blob identities normalize checkout line endings and tie the evidence to
the committed source rather than a claimed function return.

## Admission contract

The admission boundary is the final successful latch read in
`_invoke_executor`, running on the actual execution thread/process after
signature preparation and immediately before calling the registered executor.
Submitting a future, acquiring a controller, serializing a request, spawning
a worker or sending a message does not admit execution. No permission granted
by a submitter is carried through a queue.

Thread entry uses `CancellationToken.admit_executor`, serialized with cancel by
the existing short parent lock. Process entry uses a lazily created, unnamed,
manual-reset Windows event inherited through a duplicated handle during owned
spawn. The worker's zero-time kernel read is ordered against SetEvent; the
event becomes the canonical latch when published, then parent waiters are
woken. Gate creation is serialized with cancellation, including cancellation
before a process gate exists. No child-held lock or tool-response wait is
needed to latch STOP. Native event handles are finalized with their owning
object/process; a readback test verifies parent handle release.

An invocation admitted before the latch is already in flight, even if OS
scheduling subsequently pauses it before its body makes progress. The entry
decision never holds a lock through the body, policy, undo, I/O, verification
or cleanup. Preventing later admission is distinct from cancelling/terminating
already admitted work; BA-02 and the P03/P10 gates still cover the latter.

The registry also rechecks after policy/pre-state waits and the controller
rechecks after its serialization wait. `cancellable=False` cannot exempt a new
invocation from the latch. Worker requests are bound to the controller/task;
reusing a controller with a different task gate restarts its owned worker with
the new identity/gate. A cancelled child entry returns `TASK_CANCELLED`, never
verified success or an undo record for an effect that did not occur.

The BA-03 test retains its original assertion and simply loses its expected
failure marker. Schema-before-policy ordering, pre-state capture, strongest
available verification and ledger/undo finalization remain in the same runner.
Successful fixtures read back their state and SQLite action/undo records;
rejected late entry records unverified cancellation without an undo record.
No UI code, command enablement, catalog capability, planner lifecycle or
cleanup/rollback algorithm is changed.

## Executed checks (E06)

Environment: Windows 11 build 26200, x64 Python 3.12.10, pytest 8.3.3.
Each run used a bounded child process with unique user-local LOCALAPPDATA,
APPDATA, TEMP and TMP directories and inherited `PLUMA_*` overrides removed.
`tests/conftest.py` enables test mode/audio emulation. These are not physical
audio or model tests. Each pytest case had a 20-second thread timeout; each
outer test process had a 180-second limit. Only owned temp files/processes/
Job Objects and fixture pipes/credentials were used. Remaining fixture keys:
zero. No production credential, resident hotkey, microphone, user application,
model, system-changing elevation or security-policy change was used.

The common pytest options below are:

```text
-q -o addopts= --timeout=20 --timeout-method=thread --tb=short -ra -p no:cacheprovider
```

Every command also used `--junitxml=<output/p01/run-name.xml>`.

Focused admission/cancellation/registry/ownership checks:

```powershell
python -m pytest tests/unit/test_executor_admission.py tests/unit/test_tool_runner_ledger.py tests/unit/test_schemas.py tests/unit/test_task_supervisor.py tests/unit/test_ownership.py tests/unit/test_job_object.py <common options>
# 78 passed in 6.90s; exit 0; outer wall 7.739s.
```

The 21 new admission cases cover:

- STOP during blocking policy and pre-state capture; no executor/undo effect.
- Already stopped calls, including tools marked noncancellable.
- A real single-thread queue drained after STOP; no escaped executor start.
- STOP during signature preparation and rejected-entry SQLite failure evidence.
- Queued timeout cancellation without a later delayed effect.
- STOP while an admitted body is blocked; latch does not wait for completion.
- Successful pre-state/executor/verifier order and real SQLite action/undo readback.
- Gate creation after STOP and native handle release after token lifetime.
- Waiting for the controller, cancellation during startup, late receive and
  preparation, and wrong-task request rejection using inert connections.
- Actual spawned worker success and STOP during child preparation, with native
  Job Object assignment and marker readback. A recycled controller restarts
  with the next task's gate; a crashed owned worker does not strand the latch.
  Owned worker exit is read back after fixture cleanup.

Relevant regression suite, after the focused suite:

```powershell
python -m pytest tests/unit/test_backend_wiring_audit.py tests/unit/test_schemas.py tests/unit/test_router.py tests/unit/test_brain_validator.py tests/unit/test_policy_engine.py tests/unit/test_redaction.py tests/unit/test_activity_ledger_lifecycle.py tests/unit/test_rollback_engine.py tests/unit/test_rollback_recipes.py tests/unit/test_tool_runner_ledger.py tests/unit/test_perception_freshness.py tests/unit/test_phase13_7_ui_verification.py tests/unit/test_phase13_7_created_stop.py tests/unit/test_ipc.py tests/unit/test_executor_admission.py tests/unit/test_fast_orchestrator.py tests/unit/test_multi_step_orchestrator.py -k "not test_elevation_broker_execution" <common options>
# 418 passed, 3 skipped, 1 deselected, 10 xfailed in 22.10s; exit 0.
# Outer wall 23.018s.
```

The three existing `test_fast_orchestrator.py` no-ML cases skip because those
corpus entries do not require that guarantee. The elevation operation remains
deliberately unexecuted in this bounded task. Neither skips/deselection nor the
ten remaining expected failures count as acceptance or an owner-approved
limitation. This is the relevant regression suite, not a full unit/product/
physical/install suite. Broader tests that interact with applications, clipboard,
hardware and real inference are not silently certified by these inert runs.

Raw audit, preserving all unmet requirements:

```powershell
python -m pytest tests/unit/test_backend_wiring_audit.py --runxfail <common options>
# 10 failed, 5 passed in 0.79s; exit 1; outer wall 1.438s.
```

BA-03 is the additional ordinary pass. The ten failures remain BA-01, BA-02,
BA-04, BA-05, BA-06, two BA-07 assertions, two BA-08 assertions and BA-09.
The native ACL fixture and real SQLite audit readback retain their original
meaning. No assertion was weakened and no remaining defect marker removed.

Earlier development reports are retained separately: the first focused run
had **2 failed, 71 passed** because a new eager import caused a spawn-time
package cycle. The import moved behind TYPE_CHECKING / execution-time access;
actual spawn tests then passed. Review also replaced an initial process-shared
lock design with the native event to avoid an abandoned-child-lock STOP risk.
The final evidence and hashes above refer only to the tested native-event
implementation, not those earlier attempts. No Windows policy bypass was used.

Coverage verification:

```powershell
python docs/completion/verify_requirements_matrix.py
# PASS: 298 source items, 324 traceable rows.
git diff --check
# Passed.
```

The separate final diff/evidence review (`python output/p01/review_final.py`,
ignored) passed: exactly eight announced files, unchanged locked sources and
later-milestone implementations, tested hashes matching final staged sources,
JUnit counts matching every result above, only BA-03's marker removed, resolved
documentation links, no credential patterns and eight remaining BA defects
explicitly visible. Generated reports, binaries, native handles, screenshots,
audio and runtime credentials are not committed.

## Remaining blockers and next safe milestone

BA-03's bounded P01 gate passes for the covered entry paths. Global STOP still
latches tasks sequentially (BA-01), worker termination still waits behind I/O
(BA-02), cleanup can discard failures (BA-04), residual state can be overwritten
(BA-05), shutdown and voice lifetimes remain incomplete (BA-06/07), STOP IPC
can misreport terminal truth (BA-08), and first-key creation is not safely
atomic/private (BA-09). Keep action entry disabled and both PRs draft.

P10 still requires combined real Windows blocked-worker/descendant tests after
P01-P09, including pre-existing fixture survival, PID/creation ownership,
interruptible termination, global latch acknowledgement measured separately
from cleanup, rollback/residual and ledger/IPC agreement, shutdown drain and
no owned orphans. The spawn tests here demonstrate live gate inheritance and
entry ordering only; they do not close P10, physical voice/model/OCR tests or
the target-laptop STOP p95 budget. Full F-08/G-02 acceptance remains open where
global latch ordering/planner/cleanup and real integration are still required.

**Next eligible task: P02 only, BA-01 latch-all ordering.** Reproduce
`test_global_stop_latches_every_task_before_first_grace` with `--runxfail`, then
latch every affected CREATED/RUNNING capsule before the first grace wait or
cleanup. Cover simultaneous STOP and racing requests, preserve this admission
gate, keep cleanup outside latch-critical locks and keep action entry disabled.
P03 does not become eligible until P02 passes. Do not advance automatically.

## Recovery and GitHub

The pre-P01 recovery point is `81cd450e8991f549f7605bebfb9231cf1e063452`.
Inspect it in a new unused detached worktree without overwriting current work:

```powershell
git -C D:\Workspace\DEVEL\PLUMA worktree add --detach D:\Workspace\DEVEL\PLUMA-before-p01 81cd450e8991f549f7605bebfb9231cf1e063452
git -C D:\Workspace\DEVEL\PLUMA-before-p01 status --short
```

Existing recovery tags, detached audit worktree, local archive and generated-state
stash remain as recorded in [P00 recovery](p00_evidence.md#recovery) and
[workspace cleanup](../workspace_cleanup.md). Revert shared changes through
reviewed commits, never reset/clean/force-push. The P01 change is committed and
pushed on `ui-wiring`, updating [draft PR 2](https://github.com/sai161812/pluma/pull/2).
[PR 1](https://github.com/sai161812/pluma/pull/1) remains draft/unmerged, and
`main` is not changed. No claim is made that a prior hosted UI result tests
this new backend commit.
