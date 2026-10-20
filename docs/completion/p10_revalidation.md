# P10 revalidation: owned Windows safety (E16)

Completed 2026-10-20 (Asia/Calcutta) after the owner explicitly instructed
"fix it and proceed to p10". **P10 bounded gate passes; P11 is not started.**
This supersedes the blocked next-step statements, not the original failure
facts in [E15](p10_evidence.md). Action entry and the native dark UI are unchanged.
No blanket device/product/release acceptance or approved limitation is implied.

## Prerequisites, source and change

Started clean on local/remote `ui-wiring` at
`792e13a24cd47c7a7ba677ad48c77d460233e5e9`. Main `6dbf589`, integration `9544752`,
four existing worktrees, origin and draft/open/unmerged PRs 1/2 rechecked.
Shared P10/AGENTS/master/build/acceptance/technology and UI reference contracts
were read previously and pertinent STOP/rollback/verification/failure sections
reread. Inspected the original failed fixture and its real SQLite result,
worker/controller, Jobs/ownership, schemas, orchestrator, STOP and rollback paths.

Before tracked edits: unchanged failing case **1 passed in 1.27s**; full P01-P09
prerequisites **313 passed in 36.16s**; matrix **298 source items / 324 rows**.
No asserted prerequisite was removed or relaxed. This was one diagnostic run
and one full prerequisite check under the owner's renewed instruction, not an
unreported repeat-until-green loop or waiver of the prior failure.

Two test files and four documentation files change. Production Python tree
remains `287d19783e053ea4859097aceb44b5d4e43e3cd0`. Immutable requirements,
production C#/Python/UI, dependencies and action entry are unchanged. Final
source is the commit containing this record, parent `792e13a`:

| Changed test | Git blob |
|---|---|
| `tests/unit/test_worker_cancellation.py` | `974a5b747efd75d9926f28a4abfb905a3c05e094` |
| `tests/unit/test_backend_safety_integration.py` | `48844f53d718f54a5e9b95ed09ca00c3258a9119` |

## P10-01 investigation and bounded fixture fix

Read-only inspection of the original failed fixture's SQLite action found
`TOOL_TIMEOUT` / "Tool execution timed out after 30.000s", recorded unverified.
The original startup marker assertion preceded explicit test cancellation.
The unchanged case now passed in isolation and in the complete prerequisite
set before editing; no deterministic runtime defect was reproduced.

A narrowly filtered read-only Windows System log query (Kernel-Power 506/507,
13:42-13:49 local) records Modern Standby enter **08:12:46.698 UTC** (Idle Timeout)
and exit **08:17:40.700 UTC** (Austerity Battery Drain Budget Exceeded), followed
immediately by standby re-entry. Original suite timestamp is 08:12:50.613 UTC;
cumulative JUnit durations place the failed case approximately 08:13:12.629 to
08:17:39.797 UTC. These events overlap the failed run and its long case, with
wake near completion. **Inference:** host suspension explains the otherwise
unreproduced elapsed-time overrun; these logs do not reconstruct precise worker
admission or prove exactly why its marker was missing. No power, security or
Application Control setting was changed. No suspended run is used as latency
acceptance. The original failure and evidence hashes remain intact.

Inspection did establish a fixture cleanup ordering problem: on a startup
assertion failure, ThreadPoolExecutor.__exit__ joined the executing tool before
the outer finally could cancel/close it. The new owned_registry_execution
context cancels the capsule and terminates/joins its original controller in
its inner finally, **before** pool exit. The original normal-path startup,
cancellation, result, verification, action, undo and absence assertions remain.
A native regression deliberately raises an observation exception after the
worker enters blocked work, verifies prompt original-handle exit/closed pipe/
Job readback, a done execution future, set latch and no late marker. It does
not raise deadlines, ignore startup failures or convert failure to success.

This fixes the independently demonstrated fixture failure-path drain weakness;
it does not claim a production startup repair or universal suspend/resume
safety. Fresh prerequisites and final suites pass without reproducing P10-01.
Target suspend/resume, installed recovery and loaded performance remain later
gates; no requirement is waived to pass P10's bounded fixture gate.

## Combined native evidence

Four actual Windows cases: FAST and SMART, each with safe inverse and conflict.
Each creates a capsule and routes a schema-valid MULTI_STEP plan through typed
registered tools: verified fixture file move with pre-state/ledger undo, blocked
HIGH process-isolated worker spawning a descendant, then a forbidden next step.
SMART uses an inert initial planner with the same token; a separate replan spy
must never run after STOP. Fixture policy is inert and does not certify actual
MEDIUM/HIGH confirmation/elevation or the complete move-file catalog contract.

- Real capsule/controller Jobs, native worker/root and descendant original
  handles, PID/creation/task/class/ownership metadata. The capsule job initially
  reports at least two active processes. Native Jobs/worker pipes are not mocked.
- Separate test-owned process and file created before the capsule, registered
  PREEXISTING. Live identity mismatch is read-only; no PID/name termination.
  Original Popen handle and creation time/file contents survive STOP and runtime
  close. Only the fixture owner disposes its own survivor afterward.
- Real authenticated per-fixture Windows pipe STOP during blocked worker work.
  Cleanup owner is held by an explicit fixture barrier so pending latch receipt
  can be observed independently of terminal cleanup. Actual worker termination,
  Job readback, file inverses and SQLite persistence are not fabricated.
- STOP receipt acknowledges the latch with zero clean stopped count while
  terminal_ready is false. After barrier release, root/descendant handles signal
  exit; task/controller job cleanup verifies and retained owners clear. No next
  action, replan or late marker; no detached stop owner remains after join.
- Real move inverse restores original contents/path, consumes undo and yields
  STOPPED. An intervening fixture source conflict preserves both files and undo,
  records failed inverse/residual and yields STOPPED_WITH_RESIDUAL, never clean
  stopped_count. Existing focused tests separately cover partial and irreversible
  accounting; no actual irreversible external commit is performed here.
- Capsule memory, TaskExecutionResult, persisted task, cleanup journal and
  resource mirror, and typed final IPC receipt match state/completion/persistence/
  rollback/residual/evidence. Actions prove verified move and unverified cancelled
  worker only. Runtime.close requires verified owner/work-gate drain, joined
  shutdown worker and dead DB writer; reopened SQLite retains actual final data.

Final focused-run observations (milliseconds; request initiation to actual
cancel return, full authenticated STOP reply, and subsequent terminal observation):

| Case | Latch | STOP reply | Terminal cleanup observation |
|---|---|---|---|
| restored-FAST | 2.386 | 109.500 | 117.166 |
| restored-SMART | 2.615 | 108.189 | 131.741 |
| conflict-preserved-FAST | 2.077 | 105.531 | 114.651 |
| conflict-preserved-SMART | 1.578 | 110.145 | 151.642 |

These are separate observations with real native work and an injected cleanup
barrier, not a p50/p95 benchmark. STOP waits up to 100ms for cleanup before reply;
transport/authentication/serialization adds time. Reply duration is not latch
duration. No hardware-independent latency promise is inferred. P26 remains.

## Commands, final output and isolation

Windows 11 build 26200 / Python 3.12.10 x64 / pytest 8.3.3. Each ignored runner
invocation uses its own user-local temporary LOCALAPPDATA/APPDATA/TEMP/TMP,
strips inherited PLUMA_* overrides, UTF-8 output, bounded test/external call
budgets, real SQLite and owned pipes/processes only. Keys are removed only as
exact files within their verified isolated root; all final remaining-key counts
are zero. Unhandled thread warnings are errors. No microphone, screen, model,
hotkey or production credential is activated/read/repaired for these tests.

| Check | Actual pytest result | Actual exit |
|---|---|---|
| Pre-edit diagnostic | 1 passed in 1.27s | 0 |
| Pre-edit P01-P09 prerequisites | 313 passed in 36.16s | 0 |
| Four combined native routes | 4 passed in 4.47s | 0 |
| Final focused | 413 passed in 46.34s | 0 |
| Isolated regressions | 739 passed, 3 skipped, 1 deselected in 63.38s | 0 |
| Raw audit, --runxfail | 15 passed in 0.65s | 0 |
| Owned containment | 3 passed in 3.60s | 0 |
| Startup/recovery | 5 passed in 0.71s | 0 |

`python docs/completion/verify_requirements_matrix.py`: 298 source items / 324
traceable rows, before and after edits. `git diff --check`, exact changed paths,
local links, source SHA-256 matches and assertion/ownership/scope review pass.
All 115 FAST JUnit cases carry desktop_isolation from explicit plugin loading;
preserve the historical P02 correction. Three corpus skips do not require a
no-LLM guarantee; the actual elevation execution remains explicitly deselected.
Neither is a pass or an approved limitation. No audit xfail remains.

Runner invocation: `python output/p10_followup/run_checks.py <check-name>`.
Expanded final commands below are retained verbatim in their JSON metadata;
use the isolated environment described above, not production storage:

```text
C:\Users\saipr\AppData\Local\Programs\Python\Python312\python.exe -m pytest tests/unit/test_ipc_credentials.py tests/unit/test_backend_wiring_audit.py::test_first_windows_credential_is_verified_before_return tests/unit/test_stop_protocol.py tests/unit/test_backend_wiring_audit.py::test_ipc_stop_reply_distinguishes_residual_cleanup tests/unit/test_backend_wiring_audit.py::test_ipc_stop_reply_does_not_claim_nonterminal_task_stopped tests/unit/test_voice_session.py tests/unit/test_backend_wiring_audit.py::test_voice_stop_closes_capture_without_key_release tests/unit/test_backend_wiring_audit.py::test_empty_voice_capture_finalizes_its_capsule tests/unit/test_runtime_shutdown.py tests/unit/test_backend_wiring_audit.py::test_runtime_close_drains_active_task_and_registry tests/unit/test_terminal_outcome.py tests/unit/test_backend_wiring_audit.py::test_fast_stop_preserves_supervisor_residual_outcome tests/unit/test_cleanup_evidence.py tests/unit/test_backend_wiring_audit.py::test_failed_worker_cleanup_requires_residual_state tests/unit/test_worker_cancellation.py tests/unit/test_executor_admission.py tests/unit/test_global_stop_ordering.py tests/unit/test_backend_wiring_audit.py::test_worker_stop_interrupts_outstanding_response_wait tests/unit/test_backend_wiring_audit.py::test_stop_during_prestate_prevents_executor_start tests/unit/test_backend_wiring_audit.py::test_global_stop_latches_every_task_before_first_grace -q -o addopts= -o junit_family=xunit1 --timeout=20 --timeout-method=thread --tb=short -ra -W error::pytest.PytestUnhandledThreadExceptionWarning -p no:cacheprovider --junitxml=D:\Workspace\DEVEL\PLUMA\output\p10_followup\prerequisite-before.xml

C:\Users\saipr\AppData\Local\Programs\Python\Python312\python.exe -m pytest tests/unit/test_backend_safety_integration.py tests/unit/test_ipc_credentials.py tests/unit/test_backend_wiring_audit.py::test_first_windows_credential_is_verified_before_return tests/unit/test_backend_wiring_audit.py::test_ipc_stop_reply_distinguishes_residual_cleanup tests/unit/test_backend_wiring_audit.py::test_ipc_stop_reply_does_not_claim_nonterminal_task_stopped tests/unit/test_stop_protocol.py tests/unit/test_ipc.py tests/unit/test_voice_session.py tests/unit/test_voice_pipeline.py tests/unit/test_voice_activation.py tests/unit/test_voice_vad.py tests/unit/test_brain_lifecycle.py tests/unit/test_voice_lifecycle.py tests/unit/test_voice_capture.py tests/unit/test_runtime_shutdown.py tests/unit/test_terminal_outcome.py tests/unit/test_db.py tests/unit/test_cleanup_evidence.py tests/unit/test_rollback_engine.py tests/unit/test_rollback_recipes.py tests/unit/test_worker_cancellation.py tests/unit/test_global_stop_ordering.py tests/unit/test_executor_admission.py tests/unit/test_task_supervisor.py tests/unit/test_tool_runner_ledger.py tests/unit/test_schemas.py tests/unit/test_ownership.py tests/unit/test_job_object.py -q -o addopts= -o junit_family=xunit1 --timeout=20 --timeout-method=thread --tb=short -ra -W error::pytest.PytestUnhandledThreadExceptionWarning -p no:cacheprovider --junitxml=D:\Workspace\DEVEL\PLUMA\output\p10_followup\focused-routes-final.xml

C:\Users\saipr\AppData\Local\Programs\Python\Python312\python.exe -m pytest tests/unit/test_backend_wiring_audit.py tests/unit/test_schemas.py tests/unit/test_router.py tests/unit/test_brain_validator.py tests/unit/test_policy_engine.py tests/unit/test_redaction.py tests/unit/test_activity_ledger_lifecycle.py tests/unit/test_rollback_engine.py tests/unit/test_rollback_recipes.py tests/unit/test_tool_runner_ledger.py tests/unit/test_perception_freshness.py tests/unit/test_phase13_7_ui_verification.py tests/unit/test_phase13_7_created_stop.py tests/unit/test_ipc.py tests/unit/test_backend_safety_integration.py tests/unit/test_ipc_credentials.py tests/unit/test_stop_protocol.py tests/unit/test_voice_session.py tests/unit/test_voice_pipeline.py tests/unit/test_voice_activation.py tests/unit/test_voice_vad.py tests/unit/test_brain_lifecycle.py tests/unit/test_voice_lifecycle.py tests/unit/test_voice_capture.py tests/unit/test_runtime_shutdown.py tests/unit/test_terminal_outcome.py tests/unit/test_cleanup_evidence.py tests/unit/test_worker_cancellation.py tests/unit/test_global_stop_ordering.py tests/unit/test_executor_admission.py tests/unit/test_fast_orchestrator.py tests/unit/test_multi_step_orchestrator.py -q -o addopts= -o junit_family=xunit1 --timeout=20 --timeout-method=thread --tb=short -ra -W error::pytest.PytestUnhandledThreadExceptionWarning -p no:cacheprovider --junitxml=D:\Workspace\DEVEL\PLUMA\output\p10_followup\regression-isolated.xml -k "not test_elevation_broker_execution" -p tests.fixtures.desktop_isolation

C:\Users\saipr\AppData\Local\Programs\Python\Python312\python.exe -m pytest tests/unit/test_backend_wiring_audit.py -q -o addopts= -o junit_family=xunit1 --timeout=20 --timeout-method=thread --tb=short -ra -W error::pytest.PytestUnhandledThreadExceptionWarning -p no:cacheprovider --junitxml=D:\Workspace\DEVEL\PLUMA\output\p10_followup\raw-final.xml --runxfail

C:\Users\saipr\AppData\Local\Programs\Python\Python312\python.exe -m pytest tests/unit/test_phase13_8_final_patch.py::TestTaskOwnedWorkerContainment -q -o addopts= -o junit_family=xunit1 --timeout=20 --timeout-method=thread --tb=short -ra -W error::pytest.PytestUnhandledThreadExceptionWarning -p no:cacheprovider --junitxml=D:\Workspace\DEVEL\PLUMA\output\p10_followup\containment.xml

C:\Users\saipr\AppData\Local\Programs\Python\Python312\python.exe -m pytest tests/unit/test_app_lifecycle.py tests/unit/test_crash_recovery.py -q -o addopts= -o junit_family=xunit1 --timeout=20 --timeout-method=thread --tb=short -ra -W error::pytest.PytestUnhandledThreadExceptionWarning -p no:cacheprovider --junitxml=D:\Workspace\DEVEL\PLUMA\output\p10_followup\recovery.xml

```

Intermediate new-fixture error, retained: first `combined` run had 2 failed /
27 passed / 2 teardown errors in 9.74s. A new three-step Plan omitted explicit
MULTI_STEP mode, so schema validation rejected it before execution; the capsule
had no request row and runtime truthfully refused complete shutdown. Corrected
fixture mode and pre-request history_expected=False (execution sets it True and
inserts the real request). No production fix or assertion weakening. Corrected
two-route-less cases passed 2 in 3.50s; initial focused 411 in 45.61s. Adding
FAST/SMART coverage then produced the final four cases and 413-focused result.
Earlier reports are superseded, not erased or counted as the final source.
No runtime/test source was edited while a test process was in flight.

## Artifacts, remaining gates and recovery

Ignored output/p10_followup retains exact commands/exits, environment, source
parent/SHA-256, roots, key counts, wall timings, JUnit/logs for every named run,
power-observation.json and the adapted runner. No secrets/raw audio/screenshots
or runtime data enter Git. The following hashes identify final local metadata:

| Artifact | SHA-256 |
|---|---|
| `focused-routes-final.json` | `e23b07ebf3f5121b0ecaf9fb45105a63e5facad68a974100dbff5c2466c70859` |
| `regression-isolated.json` | `25799eb40eff3a7ed2f17cbaf9f6787fed435e0781eaf48bb97aabcced11c5d5` |
| `raw-final.json` | `5ad161f6c4e16852cd33ade7ceda1a0fa7ad18eafb52119d40121cdc2d34a435` |
| `containment.json` | `837a44e318c8f3e1571d17e26ec2cc8346a4f27ef04ad0814c2d0271e3c90d04` |
| `recovery.json` | `5816f7fba8086343983757b6c9bdd396a4e22ab5e57e0e2643354f683dbc78ce` |
| `power-observation.json` | `3428775fdc74311de1813501e80c6a800848531706448fd89ae6021a46621729` |
| `run_checks.py` | `4559e77462440d5f0172bc7ada5a7c73ce8a2b9082ec258a90b1635f217ccab6` |

No unresolved original audit expected failure or reproduced safety blocker
remains in the covered paths. This bounded gate supplements prior unit/native
fixtures; it does not certify physical STT/OCR/UI waits/browser tabs, actual
planner interruption, all tool implementations/policies, reboot PID recovery,
loaded latency/soak, security/install/package or release. Those matrix rows and
P11-P33 gates remain mandatory. C# production source is unchanged; P09's 39
interop checks were not rerun here. Real HMAC/native STOP readback passed here.

Next safe milestone is **P11 on a separate instruction**, selecting one required
catalog/policy/verification/undo gap; recorded H-03 explicit MEDIUM intent is a
candidate, not work started. Action entry remains disabled. Commit/push only
ui-wiring; PRs 1/2 stay draft/open/unmerged, main/integration/worktrees/archive/
stash/tags preserved. Recovery: parent `792e13a24cd47c7a7ba677ad48c77d460233e5e9`,
or pre-P10 runtime `b0e486a0ce323da66be630ac55048b756f9f6182`, in a new detached
worktree. No merge or automatic progression.
