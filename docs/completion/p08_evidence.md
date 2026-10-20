# P08: truthful typed STOP receipts

Completed 2026-10-20 (Asia/Calcutta). Both BA-08 assertions pass ordinarily;
P01-P07 remain green. P09 is next and was not started. This is a bounded
backend protocol gate, not complete STOP/device/UI/product/release acceptance.
Native dark UI and disabled action entry remain unchanged.

## Prerequisites and tested source

Started clean on local/remote `ui-wiring` at
`7cee32faa2e1bc1b363ecb2dfedf46bf5ec116d6` (P07). Rechecked origin, four
worktrees, main `6dbf589`, integration `9544752`, and draft/open/unmerged PRs 1/2.
Read shared contract/P08, current handoff and AGENTS; reread master STOP,
ownership, verification, rollback, ledger, failure/recovery and final gates,
Build Plan Phases 1/5, technology contract, acceptance A-07/G-02/G-06/G-07/G-10,
H-07/H-08 and I/J, and the native wiring/placement references. The immutable
master was read completely in P00; no locked source is changed.

Before production edits: matrix **298 source items / 324 rows**; P01-P07
prerequisites **235 passed in 29.85s**. Both BA-08 raw assertions reproduced:
**2 failed in 0.54s**, residual omitted and ROLLING_BACK reported in stopped_tasks.
Their original setup/bodies/assertions remain identical; only those two strict
markers are removed. BA-09's fixture/marker/assertion is unchanged.

Three runtime files, two test files and five evidence/handoff documents change.
Exact files and acceptance checks were stated before production edits. No
ToolSpec, model/device, native transport/authentication/credential, Windows
security policy, native UI, immutable spec/build-plan/acceptance, worker
admission/controller, rollback recipe or synchronous internal STOP body changes.

Final source is the commit containing this record, parent `7cee32f`. Git blobs
identify the exact tested source without a circular commit hash:

| File | Git blob |
|---|---|
| `pluma/core/resident.py` | `a363bd36524808f07d3b6c84de0ac05f8a7ea053` |
| `pluma/core/task_supervisor.py` | `9606109783f6ae29204359cc35a6d5f4ad6033fd` |
| `pluma/core/stop_protocol.py` | `5b2d632f19a16fec37393627c5db87725c26401c` |
| `tests/unit/test_backend_wiring_audit.py` | `def742d83d9cc7a4077dd9f4dbc3341f7b20681b` |
| `tests/unit/test_stop_protocol.py` | `73135725578212c02d1d0452b0b031f4b6394de8` |

## Bounded protocol and ownership change

The [STOP receipt contract](p08_stop_protocol.md) defines `pluma.stop.v1`,
strict request/error/outcome fields, compatibility counts, unknown/terminal
semantics, ownership, bounds and the absence of a push API. P15 still defines
full events/reconnect/version negotiation; P17 still owns UI STOP wiring.

- STOP aliases produce typed per-task `pending`, `stopped`, `residual`, `error`
  or earlier `terminal` observations. Transport `ok` is receipt processing only.
  Latch acknowledgement, terminal readiness, persisted history, cleanup/retained
  owners, rollback and residual evidence are distinct. `stopped_tasks` and
  `stopped_count` contain only verified clean cancellations, never candidate IDs.
  Strict booleans/outcomes/states and aggregate/proof validation reject fake
  clean STOP values. Errors/copy are fixed; driver exceptions are not reflected.
- The supervisor latches/claims synchronously, latching all global candidates
  before cleanup, retaining the existing global generation/admission boundary.
  It publishes one non-daemon StopOperation with capsule references before
  starting its cleanup thread. The same existing cleanup implementation runs;
  the IPC handler waits at most 100 ms for that owner and returns actual pending
  facts. It never abandons cleanup when a client returns/disconnects/times out.
  This wait budget is not measured hardware p95 or proof of driver termination.
- Repeated/concurrent/reentrant STOP shares the claim; it cannot duplicate
  rollback or join its own thread. Targeted terminal observations do not set a
  fresh latch or rewrite completed success/failure history. Invalid input cannot
  fall through to global STOP. Unknown/evicted runtime IDs are typed errors,
  not an invented historical query or clean stop. Empty global selection is
  explicit and makes no claim about earlier terminal/residual tasks.
- Snapshot projection does not wait for the resource/state lock. If an owner
  holds it, pending/EVIDENCE_BUSY conveys unavailable proof. Otherwise the
  supervisor's terminal-ready event, atomic history-readback flag, typed
  redacted evidence and retained resources determine the result. No terminal
  state is fabricated for failed/incomplete cleanup. A residual/failed rollback,
  irreversible commit or missing persistence cannot enter stopped_tasks.
- Completed cleanup workers are joined before disposal; publication/start races
  keep ownership. Capsules cannot be pruned while an operation retains them.
  P06 task/outcome shutdown stages join the owners before storage closure;
  a blocked/unverified stage keeps its owner/store. Unexpected cleanup failure
  records a fixed code in the independent cleanup journal and preserves actual
  nonterminal state. There is no silent retry of partially completed rollback.
  Original P01-P07 admission, latch, owned process/handle, capture, rollback and
  authoritative result logic remains.

## Checks (E13)

Windows 11 build 26200 / Python 3.12.10 x64 / pytest 8.3.3. Unique isolated
LOCALAPPDATA/APPDATA/TEMP/TMP per run; inherited PLUMA_* overrides removed.
Exact commands, source SHA-256, environment, actual pytest exits and JUnit stay
under ignored `output/p08`. All 115 inherited FAST cases have explicit
desktop-isolation properties from the loaded plugin; preserve the P02 isolation
correction. All fixture keys remaining: zero. Unhandled thread exceptions fail
checks. No production microphone, model, hotkeys, user desktop app/settings,
elevation, credential repair or security-policy bypass was activated.

The new native test uses a test-owned HMAC-authenticated Windows message-mode
pipe and real runtime/SQLite with an inert registered READ executor. A second
authenticated client receives STOP while the execute response is blocked; the
latch/outcome is inspected separately from the eventual execution result.
Failure/rollback seams are explicitly injected, not physical inverse/policy
acceptance. Inherited Windows process/root/descendant and unrelated-fixture
survival checks remain real and pass. No fake device is counted as physical.

Each pytest invocation is externally bounded to 180 seconds; individual tests
use 20-second thread timeouts. The ignored runner returns zero after recording
pytest failure: **actual pytest exits below** are authoritative. Commands
normalize only Python executable/report root; JSON retains their exact paths.

```powershell
python -m pytest tests/unit/test_voice_session.py tests/unit/test_backend_wiring_audit.py::test_voice_stop_closes_capture_without_key_release tests/unit/test_backend_wiring_audit.py::test_empty_voice_capture_finalizes_its_capsule tests/unit/test_runtime_shutdown.py tests/unit/test_backend_wiring_audit.py::test_runtime_close_drains_active_task_and_registry tests/unit/test_terminal_outcome.py tests/unit/test_backend_wiring_audit.py::test_fast_stop_preserves_supervisor_residual_outcome tests/unit/test_cleanup_evidence.py tests/unit/test_backend_wiring_audit.py::test_failed_worker_cleanup_requires_residual_state tests/unit/test_worker_cancellation.py tests/unit/test_executor_admission.py tests/unit/test_global_stop_ordering.py tests/unit/test_backend_wiring_audit.py::test_worker_stop_interrupts_outstanding_response_wait tests/unit/test_backend_wiring_audit.py::test_stop_during_prestate_prevents_executor_start tests/unit/test_backend_wiring_audit.py::test_global_stop_latches_every_task_before_first_grace -q -o addopts= -o junit_family=xunit1 --timeout=20 --timeout-method=thread --tb=short -ra -W error::pytest.PytestUnhandledThreadExceptionWarning -p no:cacheprovider --junitxml=output/p08/prerequisite-before.xml
# 235 passed in 29.85s; pytest exit 0; outer wall 30.821s.
```

```powershell
python -m pytest tests/unit/test_backend_wiring_audit.py::test_ipc_stop_reply_distinguishes_residual_cleanup tests/unit/test_backend_wiring_audit.py::test_ipc_stop_reply_does_not_claim_nonterminal_task_stopped -q -o addopts= -o junit_family=xunit1 --timeout=20 --timeout-method=thread --tb=short -ra -W error::pytest.PytestUnhandledThreadExceptionWarning -p no:cacheprovider --junitxml=output/p08/before.xml --runxfail
# 2 failed in 0.54s; pytest exit 1; outer wall 1.147s.
```

```powershell
python -m pytest tests/unit/test_backend_wiring_audit.py::test_ipc_stop_reply_distinguishes_residual_cleanup tests/unit/test_backend_wiring_audit.py::test_ipc_stop_reply_does_not_claim_nonterminal_task_stopped tests/unit/test_stop_protocol.py tests/unit/test_ipc.py tests/unit/test_voice_session.py tests/unit/test_voice_pipeline.py tests/unit/test_voice_activation.py tests/unit/test_voice_vad.py tests/unit/test_brain_lifecycle.py tests/unit/test_voice_lifecycle.py tests/unit/test_voice_capture.py tests/unit/test_runtime_shutdown.py tests/unit/test_terminal_outcome.py tests/unit/test_db.py tests/unit/test_cleanup_evidence.py tests/unit/test_rollback_engine.py tests/unit/test_rollback_recipes.py tests/unit/test_worker_cancellation.py tests/unit/test_global_stop_ordering.py tests/unit/test_executor_admission.py tests/unit/test_task_supervisor.py tests/unit/test_tool_runner_ledger.py tests/unit/test_schemas.py tests/unit/test_ownership.py tests/unit/test_job_object.py -q -o addopts= -o junit_family=xunit1 --timeout=20 --timeout-method=thread --tb=short -ra -W error::pytest.PytestUnhandledThreadExceptionWarning -p no:cacheprovider --junitxml=output/p08/focused-final.xml
# 380 passed in 34.51s; pytest exit 0; outer wall 35.465s.
```

```powershell
python -m pytest tests/unit/test_backend_wiring_audit.py tests/unit/test_schemas.py tests/unit/test_router.py tests/unit/test_brain_validator.py tests/unit/test_policy_engine.py tests/unit/test_redaction.py tests/unit/test_activity_ledger_lifecycle.py tests/unit/test_rollback_engine.py tests/unit/test_rollback_recipes.py tests/unit/test_tool_runner_ledger.py tests/unit/test_perception_freshness.py tests/unit/test_phase13_7_ui_verification.py tests/unit/test_phase13_7_created_stop.py tests/unit/test_ipc.py tests/unit/test_stop_protocol.py tests/unit/test_voice_session.py tests/unit/test_voice_pipeline.py tests/unit/test_voice_activation.py tests/unit/test_voice_vad.py tests/unit/test_brain_lifecycle.py tests/unit/test_voice_lifecycle.py tests/unit/test_voice_capture.py tests/unit/test_runtime_shutdown.py tests/unit/test_terminal_outcome.py tests/unit/test_cleanup_evidence.py tests/unit/test_worker_cancellation.py tests/unit/test_global_stop_ordering.py tests/unit/test_executor_admission.py tests/unit/test_fast_orchestrator.py tests/unit/test_multi_step_orchestrator.py -q -o addopts= -o junit_family=xunit1 --timeout=20 --timeout-method=thread --tb=short -ra -W error::pytest.PytestUnhandledThreadExceptionWarning -p no:cacheprovider --junitxml=output/p08/regression-isolated.xml -k "not test_elevation_broker_execution" -p tests.fixtures.desktop_isolation
# 706 passed, 3 skipped, 1 deselected, 1 xfailed in 54.44s; pytest exit 0; outer wall 55.541s.
```

```powershell
python -m pytest tests/unit/test_voice_session.py tests/unit/test_backend_wiring_audit.py::test_voice_stop_closes_capture_without_key_release tests/unit/test_backend_wiring_audit.py::test_empty_voice_capture_finalizes_its_capsule tests/unit/test_runtime_shutdown.py tests/unit/test_backend_wiring_audit.py::test_runtime_close_drains_active_task_and_registry tests/unit/test_terminal_outcome.py tests/unit/test_backend_wiring_audit.py::test_fast_stop_preserves_supervisor_residual_outcome tests/unit/test_cleanup_evidence.py tests/unit/test_backend_wiring_audit.py::test_failed_worker_cleanup_requires_residual_state tests/unit/test_worker_cancellation.py tests/unit/test_executor_admission.py tests/unit/test_global_stop_ordering.py tests/unit/test_backend_wiring_audit.py::test_worker_stop_interrupts_outstanding_response_wait tests/unit/test_backend_wiring_audit.py::test_stop_during_prestate_prevents_executor_start tests/unit/test_backend_wiring_audit.py::test_global_stop_latches_every_task_before_first_grace -q -o addopts= -o junit_family=xunit1 --timeout=20 --timeout-method=thread --tb=short -ra -W error::pytest.PytestUnhandledThreadExceptionWarning -p no:cacheprovider --junitxml=output/p08/prerequisite-final.xml
# 235 passed in 21.29s; pytest exit 0; outer wall 22.102s.
```

```powershell
python -m pytest tests/unit/test_phase13_8_final_patch.py::TestTaskOwnedWorkerContainment -q -o addopts= -o junit_family=xunit1 --timeout=20 --timeout-method=thread --tb=short -ra -W error::pytest.PytestUnhandledThreadExceptionWarning -p no:cacheprovider --junitxml=output/p08/containment.xml
# 3 passed in 2.97s; pytest exit 0; outer wall 3.783s.
```

```powershell
python -m pytest tests/unit/test_app_lifecycle.py tests/unit/test_crash_recovery.py -q -o addopts= -o junit_family=xunit1 --timeout=20 --timeout-method=thread --tb=short -ra -W error::pytest.PytestUnhandledThreadExceptionWarning -p no:cacheprovider --junitxml=output/p08/recovery.xml
# 5 passed in 0.46s; pytest exit 0; outer wall 1.1s.
```

```powershell
python -m pytest tests/unit/test_backend_wiring_audit.py -q -o addopts= -o junit_family=xunit1 --timeout=20 --timeout-method=thread --tb=short -ra -W error::pytest.PytestUnhandledThreadExceptionWarning -p no:cacheprovider --junitxml=output/p08/raw-final.xml --runxfail
# 1 failed, 14 passed in 0.75s; pytest exit 1; outer wall 1.7s.
```

```powershell
python docs/completion/verify_requirements_matrix.py
# PASS: 298 source items, 324 traceable rows.
git diff --check
python output/p08/review.py
# Separate scope, original assertions, retained ownership, final hashes/JUnit/privacy review.
```

**48 new STOP cases** cover all aliases, malformed/unknown/evicted IDs,
empty global selection, already succeeded/failed/crash-terminal tasks, real
SQLite fields/journal parity, injected partial rollback/irreversible effects,
blocked cleanup and latch-all ordering, repeated/concurrent/reentrant requests,
cleanup exceptions, absent/failed persistence, resource lock contention,
publication/start failure/races, pruning, uncommitted terminal readiness,
strict proof/count/boolean schemas, one failed task alongside a clean task,
and authenticated native STOP independent of a pending execute response.
The inherited 46 shutdown and 29 voice cases are unchanged. The original two
BA-08 assertions are also included explicitly in the final focused set.

Intermediate failures/reviews are retained and are not passes:

- `focused-first`: **369 passed, 1 failed, 1 teardown error in 40.10s**. The
  injected nonterminal exception fixture incorrectly retried ROLLING_BACK to
  itself; normal transition correctly rejected it. The fixture now restores its
  injected boundary and publishes actual residual state through the public
  supervisor transition/real ledger, with no fake clean success or forced store
  close. The partial-rollback fixture was also corrected to construct a complete
  RollbackResult; final assertions inspect actual failed-count/code readback.
- `focused-second`: **374 passed in 41.27s**, an intermediate source/check set.
- `*-before-clock-review`: focused **377 passed**, but regressions had **2 failed,
  703 passed** and raw **3 failed, 12 passed**. Both original BA-08 setups replace
  the supervisor sleep-clock object, exposing an AttributeError in new monotonic
  deadline code before their assertions. An independent monotonic deadline now
  preserves their exact setup/assertions. Both audit cases were added to focused
  checks; no fixture or assertion was weakened to make them pass.
- `*-before-reentrant-review`: focused **379 passed**, regression **705 passed**,
  raw **1 failed, 14 passed**. Separate review added the self-join guard and an
  explicit reentrant request test. Final reports alone match all tested blobs.

Final regression **706 passed, 3 skipped, 1 deselected, 1 xfailed**; raw audit
**1 failed, 14 passed**. Only BA-09 remains failing. The three corpus skips
(entries without the no-LLM guarantee), excluded elevation operation and BA-09
strict expected failure are not passes or owner-approved limitations.

## Remaining gates, Git and recovery

**BA-09** first credential owner/DACL/atomicity remains, for P09. Combined real
Windows safety/ownership P10, native inference P13/P14, physical voice and UI
P14/P19/P25, complete tool/perception/ledger/UI contracts, performance/security,
installed artifact, recovery and final release gates remain. No full unit,
loaded STOP p95, physical-device/hotkey, fifty full active/idle cycles, GPU,
installer or final product acceptance is claimed. Unexpected cleanup failure
can leave an actual nonterminal task and open store; P08 reports that error
and retains evidence, not automatic recovery or clean completion. No requirement
or limitation is waived. Action entry stays disabled; no event API is invented.

Commit/push is confined to `ui-wiring`. PR 2 targets `ui-polish-integration`,
PR 1 targets main; both remain draft/open/unmerged. Main/integration unchanged.
Pre-P08 recovery is `7cee32faa2e1bc1b363ecb2dfedf46bf5ec116d6`: inspect using a
new detached worktree without resetting this checkout. Existing worktrees,
archive, stash and tags remain. Raw reports, fixture keys, audio/models and
caches are excluded from Git.

Next safe milestone: **P09 only**, after reading its shared contract and
rechecking P01-P08 prerequisites and fresh Git/PR state. P09 has not started.
No merge or automatic progression is authorized.
