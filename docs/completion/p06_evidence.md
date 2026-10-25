# P06: bounded shutdown drains owned work before storage

Completed 2026-10-20 (Asia/Calcutta), begun 2026-10-19. BA-06's bounded gate
passes; P01-P05 remain green. P07 is next and was not started. This is not full
STOP, native device/UI, installed-artifact, recovery or release acceptance.

## Prerequisites and source

Started clean on local/remote `ui-wiring` at
`3d56551e12058a1e8ce969d337108529389284ce`. Verified remotes, four worktrees,
unchanged main/integration and both draft/open/unmerged PRs. The immutable
master was read completely in P00 and is unchanged; reread sections 12-16/25,
AGENTS, shared contract/P06, handoff, Build Plan Phases 1/2/5/13, technology
contract, applicable B lifecycle/G-01/G-02/G-06/G-08/G-09/G-10 and final gates.
Inspected runtime, supervisor, routing, registry/futures, model timers,
IPC/capture/listeners, storage and tests, plus UI/placement/wiring references.
Native dark UI and disabled action entry are unchanged.

Before editing, matrix coverage passed **298 source items / 324 rows**.
P01-P05 plus five ordinary audit regressions passed **157 checks in 16.32s**.
BA-06 reproduced with `--runxfail`: **1 failed in 0.52s**, task RUNNING,
latch false, job open, worker undrained, registry unclosed. Original assertion
is unchanged; only its strict marker is removed. Ignored `output/p06/before.*`
and `prerequisite.*` retain the original hashes, exact commands and output.

Final tested source is the P06 commit containing this record, parent `3d56551`:

| File | Git blob |
|---|---|
| `pluma/app.py` | `8c2e5eee14e857fc22a583e4d1512bb35ec393ed` |
| `pluma/core/shutdown.py` | `07034a1e47591e027b48e9e0ebbae3d0d7dbdc18` |
| `pluma/core/task_supervisor.py` | `1f5d332b2e7c1c1afb7a398b4f6b4dfff6050350` |
| `pluma/core/orchestrator.py` | `35317847e3ad3aab90c27f70a0d3599e7ae7152f` |
| `pluma/core/resident.py` | `4eb26aedae94fa1d1b4bb463e2cde2aee1ee5131` |
| `pluma/core/ipc.py` | `aabab2ac92dca9a8f278bb2f44442ffa40c5f3b9` |
| `pluma/tools/registry.py` | `a67a51c0d1fb9ef1e59f1bc61709e33971300b63` |
| `pluma/brain/llama_cpp_adapter.py` | `326ed761badf821d3fa139d28ffeaf4f36e46442` |
| `pluma/brain/lifecycle.py` | `6ae93bd7c24db1026aea38ea927dcec3c8cf7da7` |
| `pluma/voice/lifecycle.py` | `d4bf0aeb6fde8d65e01ee7e2b181098e965a6a16` |
| `pluma/voice/capture.py` | `489f172ed86421cfcc46f068f346dd6f1b56ae2c` |
| `pluma/voice/activation.py` | `07c6c34eeeacaf4fa2a0688451b9491a04fe0b86` |
| `pluma/memory/activity.py` | `7adc38c3556033fb6682f4c6bc0dd10188a33848` |
| `pluma/memory/db.py` | `de33d2965cb8fd6149157b7e08c8e4de8a31e1ca` |
| `tests/unit/test_runtime_shutdown.py` | `885977bb9e473b18904c570760f346a1ee1be309` |
| `tests/unit/test_backend_wiring_audit.py` | `a9cc8586261e833706989ecfd059079bada0104c` |

Fourteen runtime files, two test files and four handoff/evidence documents
change. No inherited P01-P05 assertion or fixture changes. Cancellation,
Windows Job Objects, worker pipe/controller, ownership, rollback engine/recipes,
crash recovery, database migrations, ToolSpecs/policy and native UI are
unchanged. Final JSON records exact SHA-256, parent, environment, isolated
roots, commands, exits and durations. Git blobs normalize checkout line endings.

## Shutdown contract

- `PlumaApplicationRuntime.close(timeout_s=5)` first permanently rejects new
  task/execute/voice/IPC/registry admission and latches all affected capsules,
  including retained preparations. Existing global STOP remains reusable for
  ordinary later commands; runtime shutdown does not reopen admission. Task
  preparation retains its original STOP generation and is counted until
  publication or verified rejection cleanup finishes.
- Close returns a factual `ShutdownResult(complete, stage, code)`. A serialized
  `ShutdownSession` owns at most one non-daemon stage worker. Every close call
  has a bounded wait budget. A slow native driver, rollback, callback or store
  stays owned by the session; a timeout does not kill an arbitrary thread,
  discard it or start the next stage. Repeated close joins the same worker,
  resumes verified stages and retries a failed stage. Concurrent closes share
  the owner. No model/device starts at import or idle.
- Stages cancel/discard capture, stop task-owned work and rollback, drain
  resident/IPC/direct execution handlers, close registry controllers/futures,
  read retained owners and persist outcomes, verify model/timer unload, then
  close storage. The host remains in the shutdown loop while incomplete and
  never logs clean shutdown merely because `close` returned. A permanently
  uncooperative external call therefore keeps the runtime/store owned and
  reports pending/unverified; five seconds is an acknowledgement bound, not a
  promise to force-terminate arbitrary Python/device work.
- Admission/active-call gates track direct orchestrator, resident callbacks and
  registry calls. Registry ownership also tracks executor and planner futures
  that survive their result timeout; queued work is cancelled, running work is
  retained until actual exit. Futures carry task/class/opaque resource identity,
  not arguments or exception bodies. Capsule ownership is registered before
  submission, excludes pruning while work is unresolved, and defers rollback
  or temporary deletion while absence is unknown. The capsule retains the
  Future until supervisor readback. Completion callbacks release gate ownership
  without changing terminal evidence after persistence.
- An unresolved submission/worker/handler/preparation or native job prevents
  verified closure. After callers/registry drain, terminal and unpublished
  owners are revisited, read back and persisted. Previously deferred rollback
  and remaining pre-state are retained as factual residual evidence; shutdown
  does not silently repeat a conflicted inverse or claim reversal. Shared
  executor infrastructure is process-scoped; registry-owned calls/futures must
  all exit before storage closes. This is not a fifty-cycle handle/idle test.
- Windows IPC tracks each client connection and thread. Closing a native
  `multiprocessing.Listener` alone does not interrupt an accept already inside
  ConnectNamedPipe. Shutdown wakes only PLUMA's own named listener, joins it,
  serializes connection closure with handler ownership, interrupts waiting I/O
  and verifies no retained client remains. Busy/unknown closure is incomplete.
  Existing per-user HMAC challenge/native framing, sizes and message bodies are
  preserved. STOP acknowledgement truth remains BA-08/P08; no push API is added.
- Shutdown cancels/discards capture and reads native stream closure back; failed
  closure retains the stream. An already-admitted press may cross the first
  cancellation, so capture is cancelled again after handler drain. Activation
  and hotkey threads retain references until positive exit. Hotkey wake uses
  its Windows native thread ID. No user window/app/settings are modified.
- Voice capture capsules are marked as pre-execution before publication. If no
  executable transcript/request exists, `finalize_pre_execution` stores actual
  terminal/STOP facts in the redacted independent cleanup journal. It does not
  invent command text, input content or a tasks row. Once a real request enters
  execution, normal task history remains mandatory and P05 atomic state/evidence
  readback applies. Ordinary voice STOP/empty-capture bugs are still BA-07.
- Brain/voice lifecycle shutdown cancels and retains timer owners, suppresses
  new idle callbacks and verifies timer exit/model unload after handlers and
  futures drain. Existing model choices/loading/quality contracts are unchanged.
  Running in-process inference is drained, not falsely described as terminated;
  full native planner/STT isolation and device lifecycle remain P13/P14 work.
- SQLite serializes write admission with a single close sentinel, drains and
  joins its writer before closing connections, and refuses new writes behind
  the sentinel. A writer timeout keeps connection ownership/readback available;
  repeated close never queues an extra sentinel. Existing queued writes can
  still commit after an acknowledgement timeout; P05 conservative reconciliation
  remains. Terminal persistence failure prevents the storage stage. Shutdown
  reports/evidence use fixed factual codes; no raw audio/capture/model data,
  exception bodies, credentials or native handles are newly logged.

## Checks (E11)

Windows 11 build 26200, Python 3.12.10 x64, pytest 8.3.3. Unique isolated
LOCALAPPDATA/APPDATA/TEMP/TMP per run; inherited PLUMA_* overrides removed.
Existing conftest enables test/audio emulation. All new tests use owned
processes/files/pipes/SQLite and inert planner/device adapters. No production
resident/hotkey/microphone, user desktop target, model inference, elevation or
Windows setting/security-policy change was activated. All 115 inherited FAST
cases have explicit desktop-isolation properties; retain the P02 correction.
Fixture keys remaining: **zero**. Raw reports stay ignored under output/p06.
Unhandled thread exceptions are errors in final checks.

Exact selected commands/output (outer pytest bound 180 seconds):

```powershell
python -m pytest tests/unit/test_terminal_outcome.py tests/unit/test_backend_wiring_audit.py::test_fast_stop_preserves_supervisor_residual_outcome tests/unit/test_cleanup_evidence.py tests/unit/test_backend_wiring_audit.py::test_failed_worker_cleanup_requires_residual_state tests/unit/test_worker_cancellation.py tests/unit/test_executor_admission.py tests/unit/test_global_stop_ordering.py tests/unit/test_backend_wiring_audit.py::test_worker_stop_interrupts_outstanding_response_wait tests/unit/test_backend_wiring_audit.py::test_stop_during_prestate_prevents_executor_start tests/unit/test_backend_wiring_audit.py::test_global_stop_latches_every_task_before_first_grace -q -o addopts= -o junit_family=xunit1 --timeout=20 --timeout-method=thread --tb=short -ra -p no:cacheprovider --junitxml=output/p06/prerequisite.xml
# 157 passed in 16.32s; pytest exit 0; outer wall 17.268s.
```

```powershell
python -m pytest tests/unit/test_backend_wiring_audit.py::test_runtime_close_drains_active_task_and_registry -q -o addopts= -o junit_family=xunit1 --timeout=20 --timeout-method=thread --tb=short -ra -p no:cacheprovider --junitxml=output/p06/before.xml --runxfail
# 1 failed in 0.52s; pytest exit 1; outer wall 1.187s.
```

```powershell
python -m pytest tests/unit/test_brain_lifecycle.py tests/unit/test_voice_lifecycle.py tests/unit/test_voice_capture.py tests/unit/test_runtime_shutdown.py tests/unit/test_terminal_outcome.py tests/unit/test_db.py tests/unit/test_cleanup_evidence.py tests/unit/test_rollback_engine.py tests/unit/test_rollback_recipes.py tests/unit/test_worker_cancellation.py tests/unit/test_global_stop_ordering.py tests/unit/test_executor_admission.py tests/unit/test_task_supervisor.py tests/unit/test_tool_runner_ledger.py tests/unit/test_schemas.py tests/unit/test_ownership.py tests/unit/test_job_object.py -q -o addopts= -o junit_family=xunit1 --timeout=20 --timeout-method=thread --tb=short -ra -W error::pytest.PytestUnhandledThreadExceptionWarning -p no:cacheprovider --junitxml=output/p06/focused-final.xml
# 286 passed in 21.02s; pytest exit 0; outer wall 21.745s.
```

```powershell
python -m pytest tests/unit/test_backend_wiring_audit.py tests/unit/test_schemas.py tests/unit/test_router.py tests/unit/test_brain_validator.py tests/unit/test_policy_engine.py tests/unit/test_redaction.py tests/unit/test_activity_ledger_lifecycle.py tests/unit/test_rollback_engine.py tests/unit/test_rollback_recipes.py tests/unit/test_tool_runner_ledger.py tests/unit/test_perception_freshness.py tests/unit/test_phase13_7_ui_verification.py tests/unit/test_phase13_7_created_stop.py tests/unit/test_ipc.py tests/unit/test_brain_lifecycle.py tests/unit/test_voice_lifecycle.py tests/unit/test_voice_capture.py tests/unit/test_runtime_shutdown.py tests/unit/test_terminal_outcome.py tests/unit/test_cleanup_evidence.py tests/unit/test_worker_cancellation.py tests/unit/test_global_stop_ordering.py tests/unit/test_executor_admission.py tests/unit/test_fast_orchestrator.py tests/unit/test_multi_step_orchestrator.py -q -o addopts= -o junit_family=xunit1 --timeout=20 --timeout-method=thread --tb=short -ra -W error::pytest.PytestUnhandledThreadExceptionWarning -p no:cacheprovider --junitxml=output/p06/regression-isolated.xml -k "not test_elevation_broker_execution" -p tests.fixtures.desktop_isolation
# 612 passed, 3 skipped, 1 deselected, 5 xfailed in 34.39s; pytest exit 0; outer wall 35.252s.
```

```powershell
python -m pytest tests/unit/test_terminal_outcome.py tests/unit/test_backend_wiring_audit.py::test_fast_stop_preserves_supervisor_residual_outcome tests/unit/test_cleanup_evidence.py tests/unit/test_backend_wiring_audit.py::test_failed_worker_cleanup_requires_residual_state tests/unit/test_worker_cancellation.py tests/unit/test_executor_admission.py tests/unit/test_global_stop_ordering.py tests/unit/test_backend_wiring_audit.py::test_worker_stop_interrupts_outstanding_response_wait tests/unit/test_backend_wiring_audit.py::test_stop_during_prestate_prevents_executor_start tests/unit/test_backend_wiring_audit.py::test_global_stop_latches_every_task_before_first_grace -q -o addopts= -o junit_family=xunit1 --timeout=20 --timeout-method=thread --tb=short -ra -W error::pytest.PytestUnhandledThreadExceptionWarning -p no:cacheprovider --junitxml=output/p06/prerequisite-final.xml
# 157 passed in 12.70s; pytest exit 0; outer wall 13.402s.
```

```powershell
python -m pytest tests/unit/test_phase13_8_final_patch.py::TestTaskOwnedWorkerContainment -q -o addopts= -o junit_family=xunit1 --timeout=20 --timeout-method=thread --tb=short -ra -W error::pytest.PytestUnhandledThreadExceptionWarning -p no:cacheprovider --junitxml=output/p06/containment.xml
# 3 passed in 2.97s; pytest exit 0; outer wall 3.647s.
```

```powershell
python -m pytest tests/unit/test_app_lifecycle.py tests/unit/test_crash_recovery.py -q -o addopts= -o junit_family=xunit1 --timeout=20 --timeout-method=thread --tb=short -ra -W error::pytest.PytestUnhandledThreadExceptionWarning -p no:cacheprovider --junitxml=output/p06/recovery.xml
# 5 passed in 0.46s; pytest exit 0; outer wall 1.043s.
```

```powershell
python -m pytest tests/unit/test_backend_wiring_audit.py -q -o addopts= -o junit_family=xunit1 --timeout=20 --timeout-method=thread --tb=short -ra -W error::pytest.PytestUnhandledThreadExceptionWarning -p no:cacheprovider --junitxml=output/p06/raw-final.xml --runxfail
# 5 failed, 10 passed in 0.57s; pytest exit 1; outer wall 1.212s.
```

```powershell
python docs/completion/verify_requirements_matrix.py
# PASS: 298 source items, 324 traceable rows.
git diff --check
# Passed.
python output/p06/review.py
# Separate scope/source/ownership/ledger/native-framing/assertion/hash review.
```

**46 new shutdown cases** cover intake, latch order, actual direct execution,
late callbacks/capture, native pending execute/auth/accept, capture failure,
rollback, repeated/concurrent close, retained terminal and unpublished owners,
preparation-generation races, registry/tool/planner futures, pruning, model
unload/timers, per-stage failure and actual SQLite close timeouts. Reopened
SQLite verifies terminal fields and cleanup facts, including pre-execution
cancellation with no fabricated history. The real runtime fixture verifies
owned worker/root/descendant exit, empty/released jobs, unrelated fixture
survival and absent late effects. It uses an inert policy owner for a HIGH
fixture ToolSpec, as P03/P04 containment tests do; it is not policy/device or
all-worker acceptance. Five additional fixture checks preserve startup recovery
and logging behavior; recovery source and ownership rules are unchanged.

Intermediate failures are retained, not accepted or silently skipped:
`prerequisite-post` exposed the live native accept; `prerequisite-second` caught
a wrong native CreateFile argument, corrected to the required null integer.
`focused-initial` assumed an auth wait must still be pending after close, while
readback proved prompt exit; it now requires joined owners/closed storage.
`focused-third` exposed concurrent native connection close and missing
pre-execution capture history; both were fixed. `focused-fifth` mistakenly chose
the in-process route for the new process fixture; corrected to HIGH with inert
fixture policy. That failed fixture is not containment evidence. Subsequent read-only checks using its recorded process creation identity verify absence; the initial identity-free probe was unverified, not proof. `focused-sixth`
asserted a terminal value during an explicitly pending close; the corrected
check permits actual pending states, then requires residual state and reopened
history after verified closure. Ownership review additionally retains capsules
through active futures/pruning and keeps asynchronous callbacks out of terminal
persistence. Final reports alone above match the recorded source blobs;
`*-before-owner-review`, `*-before-fixture-review` and `focused-owner-review` remain intermediate artifacts.
Final fixture teardown also requires verified close, idle owned work and closed storage; it never force-closes a store with live work. No inherited audit assertion or remaining marker/setup was changed.

The three inherited corpus skips, one excluded elevation operation and five
strict expected failures are not passes or owner-approved limitations. Raw
failures remain both BA-07, both BA-08 and conditional BA-09. Inert capture/model
fixtures do not prove physical audio/STT/GPU unload. No full unit/product/device/
install, adversarial recovery/filesystem/PID reuse, installed restart, fifty-cycle
soak or hotkey/loaded p95 acceptance is claimed. Storage cannot be closed or
called durably current while drain/persistence is unverified; that failure
response is tested, not an acceptance waiver.

## Remaining blockers, next milestone and Git

**Three findings remain: BA-07 through BA-09**, five raw failures. Ordinary
voice STOP/empty capture, typed truthful STOP acknowledgement and private first
credential creation remain. Mandatory tool/policy/undo, screen/planner/STT,
native device/UI, recovery/security/performance and release gates remain in
the matrix. Action entry stays disabled; native dark UI is unchanged.

**Next safe milestone: P07 only.** Reproduce both original BA-07 assertions,
connect capture to capsule cancellation, finalize empty/denied/failed/cancelled
paths, preserve the capsule into STT/execution and serialize press/release/STOP/
shutdown races. Keep audio transient/models lazy; use inert fixtures here and
record physical device acceptance at P14/P19. P07 was not started. Do not
advance automatically or enable actions. P10 later combines P01-P09 Windows,
worker/failure/voice/ledger paths and repeated handle lifetimes; the one real
P06 shutdown fixture does not replace that combined gate.

Commit/push target is authorized `ui-wiring`, ordinary non-force push. PR
[2](https://github.com/sai161812/pluma/pull/2) remains draft/open/unmerged toward
`ui-polish-integration`; PR [1](https://github.com/sai161812/pluma/pull/1) remains
draft/open/unmerged toward `main`. Main stays `6dbf589`, integration `9544752`.
Pre-P06 recovery: `3d56551e12058a1e8ce969d337108529389284ce`; inspect with
`git worktree add --detach <new-folder> 3d56551e12058a1e8ce969d337108529389284ce`.
Preserve worktrees, tags, stash and archives per
[workspace recovery](../workspace_cleanup.md). No merge, branch/worktree switch,
reset/clean, force push or security bypass was performed.
