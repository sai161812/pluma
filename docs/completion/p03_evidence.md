# P03: interruptible owned-worker I/O and lifetime

Date: 2026-10-19 (Asia/Calcutta). BA-02's bounded gate passes; P01/P02 remain
green. P04 is the next milestone and was not started. Full STOP, backend,
native UI, hardware latency and release acceptance remain open.

## Prerequisites and tested source

Started clean on local/remote `ui-wiring` at
`f303f231b825cad151fcf0846b3966e6ccc4a2a2`. Rechecked branches, remotes,
worktrees and both draft/open PRs. The immutable master specification was
already read completely in P00 and is unchanged; reread its STOP, ownership
and verification contracts, AGENTS, shared execution contract/P03, current
handoff, Build Plan Phase 1, applicable F-08/G-01/G-02/G-09/G-10 and technology
contract. Inspected implementation, tests and current UI wiring/placement
references. No source requirement, UI design or action-entry gate was changed.

Before editing, coverage passed (298 source items / 324 rows), and P01/P02 plus
their two ordinary audit assertions freshly passed **45 checks in 3.21s**
(exit 0; wall 3.896s). BA-02 then reproduced with `--runxfail`: **1 failed in
0.50s**, exit 1, wall 1.126s, `STOP could not acquire the controller until the
outstanding response wait ended`. The pre-edit reproduction and source hashes
remain in ignored `output/p03/before.*`. A later prerequisite rerun is stored
separately as `prerequisite-post.*` (45 passed in 3.11s).

Final tested source is the P03 commit containing this record, parent `f303f23`:

| File | Git blob |
|---|---|
| `pluma/core/job_object.py` | `7df2b721284c8ad756ff06cb7af2209803e22513` |
| `pluma/tools/registry.py` | `832a2353030688f4cf48450878a2f62053bd1b6d` |
| `pluma/adapters/worker_pipe.py` | `aaab1f8c621a5869f4253a4c4f50c8c7d9700e08` |
| `tests/unit/test_backend_wiring_audit.py` | `5875cb864fa2c1489b1392d3b3417d587fd18d3a` |
| `tests/unit/test_worker_cancellation.py` | `b3338e43a89651f88a965b06611a789d0fb1ce46` |

P01 cancellation/admission tests, P02 supervisor/ordering tests and the desktop
isolation plugin are unchanged. Final JSON reports record full command vectors,
source SHA-256, parent hash, isolated roots, platform, exit and wall durations.
Git blob IDs normalize checkout line endings. Reports/JUnit stay ignored.

## Controller contract and limits

- `_lock` serializes requests only. Separate short state and bounded cleanup
  locks govern lifetime. STOP sets the controller stop event and inherited
  admission latch before waiting for startup, grace, cleanup or joining.
  Explicit disposal also signals the original parent token/waiters. Transport
  failure cleanup does not consume the parent's first explicit cancellation.
- Parent request writes and response reads use native Windows overlapped
  message-pipe I/O behind `WorkerPipe`. The standard multiprocessing wire format
  is unchanged. Pending operations check cancellation/deadline at most every
  20ms; cancellation drain and close each have a 200ms bound. Failed drain
  retains the OVERLAPPED and connection for explicit retry. No I/O helper or
  cleanup thread is launched; STOP never sends into a potentially full pipe.
- The request deadline includes serialization-lock waiting, startup elapsed
  time and I/O. The native synchronous process launch itself cannot be forcibly
  interrupted before a handle exists. STOP waits at most the cleanup budget
  for its owner to finish startup, then raises a concrete pending-startup
  failure while retaining ownership. The original execution caller checks the
  latch when launch returns and performs cleanup without admitting a ToolCall.
  This is a tested failure path, not a clean-stop acknowledgement or a waiver.
- Spawned workers retain task ID, PID, native creation timestamp, command class
  and PLUMA_CREATED ownership. Before any request is sent, the worker is
  assigned to a private kill-on-close Job Object and the supplied capsule Job
  Object. Creation-time readback and assignment use the original Windows
  process handle; neither reopens the worker's numeric PID. Containment/identity failures fail closed. The controller never
  closes the capsule's shared job. Force termination uses the owned job and
  original multiprocessing process handle, never a process-name/PID kill.
- Workers receive a cooperative view of the same inherited latch. A completed
  cancelled invocation exits the worker loop. Default controller grace is 50ms;
  forced termination/join uses the remaining one-second cleanup budget. Pipe
  close has its separate 200ms bound. Unverified root exit, active pipe I/O,
  startup or cleanup exceptions propagate with retained references for retry.
  The exited Process/identity is retained for readback; multiprocessing's
  finalizer owns its native handles through object lifetime.
- Repeated/concurrent disposal is serialized independently of request I/O.
  Same-task restart after disposal is rejected. Idle pool acquisition disposes
  the old task controller and creates a new one, so a delayed old reference
  cannot terminate a newly assigned task. The P01 explicit rebinding seam still
  proves that changing task/gate cannot reuse the old worker.

These are controller guarantees. Supervisor/registry failure retention and
aggregate Job Object/resource/rollback readback still have BA-04/BA-06 defects.
Their exception swallowing/reference loss is unchanged for P04/P06. A native
job termination return or controller result alone does not certify all task
descendants absent, terminal persistence or truthful IPC acknowledgement.

## Executed checks (E08)

Windows 11 build 26200, Python 3.12.10 x64, pytest 8.3.3. Every run uses unique
user-local LOCALAPPDATA/APPDATA/TEMP/TMP directories, with inherited PLUMA_*
overrides removed. Existing conftest enables test/audio emulation. No resident,
hotkey, microphone, ML/OCR, elevation operation, real desktop interaction,
security-policy change or raw capture was activated. Owned fixture files,
processes, native events/pipes/jobs and SQLite are used; retained fixture keys
after each run: **zero**.

Common options below (each also has `--junitxml=output/p03/<run>.xml`):

```text
-q -o addopts= -o junit_family=xunit1 --timeout=20 --timeout-method=thread --tb=short -ra -p no:cacheprovider
```

Each outer pytest process has a 180-second bound. Exact vectors and stdout
are in ignored JSON/TXT reports. Commands/results:

```powershell
python -m pytest tests/unit/test_executor_admission.py tests/unit/test_global_stop_ordering.py tests/unit/test_backend_wiring_audit.py::test_stop_during_prestate_prevents_executor_start tests/unit/test_backend_wiring_audit.py::test_global_stop_latches_every_task_before_first_grace <common options>
# Before edits: 45 passed in 3.21s; exit 0; wall 3.896s.

python -m pytest tests/unit/test_backend_wiring_audit.py::test_worker_stop_interrupts_outstanding_response_wait --runxfail <common options>
# Before edits: 1 failed in 0.50s; exit 1; wall 1.126s.

python -m pytest tests/unit/test_worker_cancellation.py tests/unit/test_global_stop_ordering.py tests/unit/test_executor_admission.py tests/unit/test_task_supervisor.py tests/unit/test_tool_runner_ledger.py tests/unit/test_schemas.py tests/unit/test_ownership.py tests/unit/test_job_object.py <common options>
# Final: 126 passed in 14.48s; exit 0; wall 15.629s.

python -m pytest tests/unit/test_backend_wiring_audit.py tests/unit/test_schemas.py tests/unit/test_router.py tests/unit/test_brain_validator.py tests/unit/test_policy_engine.py tests/unit/test_redaction.py tests/unit/test_activity_ledger_lifecycle.py tests/unit/test_rollback_engine.py tests/unit/test_rollback_recipes.py tests/unit/test_tool_runner_ledger.py tests/unit/test_perception_freshness.py tests/unit/test_phase13_7_ui_verification.py tests/unit/test_phase13_7_created_stop.py tests/unit/test_ipc.py tests/unit/test_worker_cancellation.py tests/unit/test_global_stop_ordering.py tests/unit/test_executor_admission.py tests/unit/test_fast_orchestrator.py tests/unit/test_multi_step_orchestrator.py -k "not test_elevation_broker_execution" -p tests.fixtures.desktop_isolation <common options>
# Final: 468 passed, 3 skipped, 1 deselected, 8 xfailed in 28.50s;
# exit 0; wall 29.289s.

python -m pytest tests/unit/test_backend_wiring_audit.py --runxfail <common options>
# Final: 8 failed, 7 passed in 0.67s; exit 1; wall 1.314s.

python -m pytest tests/unit/test_phase13_8_final_patch.py::TestTaskOwnedWorkerContainment <common options>
# 3 passed in 2.89s; exit 0; wall 3.554s.

python docs/completion/verify_requirements_matrix.py
# PASS: 298 source items, 324 traceable rows.
git diff --check
# Passed.
```

Twenty-six new cases cover real hung/cooperative worker response waits,
owned descendant exit with a separate unrelated fixture surviving, real full
request-pipe cancellation/timeout, response deadline, native pending send/read
cancellation/timeout, wire interoperability through empty/small/1MiB payloads,
failed native I/O drain/retry, STOP before launch/during stalled OS startup,
queued request deadline, kill/exit/pipe/job failures with retry, containment
refusal before executor entry, concurrent repeated disposal, old-controller
pool isolation, handle-based identity/assignment despite a substituted PID,
parent cancellation waiter signalling and SQLite cancellation readback with no fabricated verification
or undo. BA-02's 150ms assertion is unchanged. Its process double now records
exit when killed (with PID/exit-code fields), replacing an always-alive no-op
kill double so cleanup readback is meaningful; only BA-02's marker is removed.

Review caught an intermediate P01 crash-cancellation regression while adding
parent-waiter signalling (one failing case in focused/regression runs). Logs
remain under `*-parent-signal-review.*`. Separating transport failure cleanup
from explicit parent cancellation restores the unchanged assertion; all final
checks above use the corrected source.

Real hung/cooperative worker observations from final focused JUnit were
**63ms / 78ms** from cancellation dispatch through controller disposal, versus
30-second tool deadlines. Root process exit, cooperative marker/exit code,
descendant handle signalling, unrelated fixture liveness and absent late-effect
markers are read back. These individual fixture timings are not hotkey,
target-device, loaded p95 or whole-supervisor measurements.

All 115 FAST cases in final JUnit carry `desktop_isolation`: the explicit
plugin uses in-memory clipboard, no target window and blocked desktop process
termination. This is orchestration evidence, not native desktop acceptance.
Retain the [P02 isolation correction](p02_evidence.md); do not rerun this
bounded FAST suite without the plugin. The three inherited corpus skips and
excluded elevation operation are not passes or approved limitations. The
additional persistent-app containment case uses an owned empty job, not a real
desktop application. No full unit/product/device/install suite is claimed.

## Remaining blockers, P10 record and next gate

BA-01/02/03 now pass their bounded gates. **Six findings remain**, BA-04 through
BA-09, represented by eight raw failures: failed cleanup retention, FAST
residual truth, runtime drain, two voice cases, two IPC truth cases and initial
credential privacy. Their strict markers/assertions remain. Action entry is
disabled. Required capabilities and physical/device/UI acceptance stay open.

P10 must rerun the actual worker/full-pipe/descendant/unrelated-survivor checks
above against the combined P01-P09 source and exercise the complete supervisor,
rollback/resource verification, final SQLite/IPC outcome, shutdown/voice and
repeated lifecycle path. Include pending startup/native I/O failure retention
and process/handle counts; do not substitute this controller subset for that
gate. P26 separately measures hotkey acknowledgement and cleanup under load.

Next safe task is **P04 only**: reproduce BA-04 with `--runxfail`, preserve
cleanup failure/ownership until verified absence, combine worker/job/resource/
rollback evidence and persist factual residual state. Use P03's retained
controller identity and pending-cleanup failures. Do not enable actions or
advance automatically.

## GitHub, review and recovery

P03 changes are committed/pushed on `ui-wiring`. PR [2](https://github.com/sai161812/pluma/pull/2)
remains draft/open against `ui-polish-integration`; PR [1](https://github.com/sai161812/pluma/pull/1)
remains draft/open against `main`. Main stays
`6dbf58925352d41a0196dda33044b18282cc6ddf`, integration stays `9544752`.
No merge, force push, destructive cleanup or worktree switch was performed.
Recovery before P03 is `f303f231b825cad151fcf0846b3966e6ccc4a2a2`; inspect with
`git worktree add --detach <new-folder> f303f231b825cad151fcf0846b3966e6ccc4a2a2`.
Existing tags, worktrees, archive and stash remain per
[workspace recovery](../workspace_cleanup.md).

A separate review checks scope, locked-source preservation, original audit
assertions/remaining markers, P01/P02 preservation, actual tested hashes and
JUnit counts/isolation, ownership/readback, secrets, cleanup failure paths and
generated copy. The diff contains only the three worker runtime files, two test
files, this evidence, matrix, audit status and handoff. No runtime data/model,
credentials, captures, UI source or generated build output is committed.
