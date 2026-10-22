# P07: own the push-to-talk capture lifetime

Completed 2026-10-20 (Asia/Calcutta). BA-07 passes its bounded gate. P01-P06
remain green. P08 is next and was not started. Native dark UI and disabled
action entry remain unchanged. This is not physical voice or product acceptance.

## Prerequisites and scope

Started clean on local/remote `ui-wiring` at
`e5643210d2795ac9d542021ef7adf06df736bef4` (P06). Rechecked four worktrees,
origin, main `6dbf589`, integration `9544752`, and draft/open/unmerged PRs 1/2.
Read the shared contract/P07, current handoff and AGENTS; reread master voice,
lifecycle, STOP, cleanup, verification, memory, failure and recovery contracts,
Build Plan Phase 6, technology contract, acceptance C-01/C-06/C-07/C-08/C-09,
B lifecycle, G-02/G-06/G-10 and J, plus native wiring/placement references.
The immutable master was read completely in P00; no locked source is changed.

Before editing: matrix **298 source items / 324 rows**; P01-P06 prerequisites
**204 passed in 22.30s**. Both original BA-07 assertions reproduced:
**2 failed in 0.57s**: STOP reached a terminal state while capture recorded;
empty release left CREATED active. Their bodies/setup/assertions are unchanged;
only those two strict expected-failure markers are removed.

Four runtime files, three test files and four evidence/handoff files change.
Exact files/checks were stated before production edits. No P08 protocol,
credential/security-policy, ToolSpec, native UI, model choice, rollback recipe,
worker admission/controller, native containment, immutable specification,
build-plan or acceptance requirement changes.

Final tested source is the commit containing this record, parent `e564321`.
Git blobs identify exactly the tested files without a circular commit hash:

| File | Git blob |
|---|---|
| `pluma/core/resident.py` | `e2f2745cc42e67deabb28856b62bf65d43c68403` |
| `pluma/core/task_supervisor.py` | `2de7425b414bf0bb146bf67637f55ce2f1790004` |
| `pluma/voice/capture.py` | `9d1861aef2a4381c81b981971a5977a8451879cb` |
| `pluma/voice/session.py` | `1d830458a96f9d4a9c01bc4d6ce360d001685e32` |
| `tests/unit/test_backend_wiring_audit.py` | `32bb10206f27e705e7c866d0afb2e77388984814` |
| `tests/unit/test_voice_capture.py` | `f93885f9b889371404df82b287f45997a80538f6` |
| `tests/unit/test_voice_session.py` | `71090d398d8e2f443ebe32e3156ecc94339f3eed` |

## Capture and cancellation contract

- A press creates one pre-execution capsule and attaches its VoiceSession
  under the supervisor admission boundary before microphone admission. STOP
  winning publication/attachment prevents startup. Repeated press cannot replace
  an unreleased/processing/failed owner. Duplicate and orphan releases are inert.
- The same capsule/token owns capture, STT and the ordinary Orchestrator.
  A real transcript updates the capsule request ID and enters the registered
  route/policy/executor/verification/ledger path. A callback that cannot preserve
  capsule ownership is no longer an alternate voice execution path: missing
  orchestration fails closed. Text dispatch is unchanged.
- STOP still latches first (and global STOP latches all first). Capsule cleanup
  invokes the session independently of key release. Native capture operations
  serialize separately from the latch and short resident state lock. A session
  uses one retained ShutdownSession cleanup worker; the 100 ms cleanup wait
  bounds the caller, without pretending an unresponsive Python/device driver
  was killed. Pending startup, release or STT retains the owner, records
  VOICE_OWNER_PENDING, defers unsafe rollback, and prevents complete shutdown or
  capsule pruning while ownership is unresolved. P06 entry gates and storage-last
  shutdown remain the outer lifetime. No detached cancellation listener runs.
- Capture discards its buffer on cancellation and every failed release. Normal
  release requires native `closed is True` before returning PCM. Failed abort,
  close or readback retains the stream for explicit retry. A stale native
  callback is generation-checked so it cannot populate another utterance.
  Missing sounddevice now fails closed rather than pretending recording exists;
  tests inject an explicit inert device. Idle imports still load no device/model.
- Empty, missing capture/pipeline, silence, denied/low-confidence, pipeline error,
  missing executor and cancellation paths all finalize. No transcript means
  actual pre-execution terminal facts in the independent cleanup journal, with
  no fabricated command/task row. Real execution uses the existing atomic
  history readback. Audio is transient; no new audio/screenshot storage or raw
  driver exception logging is added. Original transcript metadata completeness
  and real-device parity remain P14, not claimed here.
- Supervisor refresh reads retained voice closure after handlers finish and
  persists it. An earlier residual result stays residual; readback never rewrites
  it into a former local success/clean STOP or repeats deferred rollback.
  A failed close blocks the next capture until a verified retry. Shutdown also
  checks voice owners even when ordinary jobs/controllers are already closed.
- Production capture exposes `capture_closed` (no stream, recording or bytes).
  Legacy inert audit adapters may expose explicit `recording is False` instead;
  an unknown adapter state cannot prove clean closure. The original empty BA-07
  fixture lacks closure readback, so its capsule ends conservatively failed with
  retained evidence, rather than leaking CREATED. New explicit-device fixtures
  prove clean empty completion, repetition and storage readback separately.

## Checks (E12)

Windows 11 build 26200 / Python 3.12.10 x64 / pytest 8.3.3. Each invocation uses
unique LOCALAPPDATA/APPDATA/TEMP/TMP, removes inherited PLUMA_* overrides, and
retains exact source SHA-256/environment/command/exit/JUnit under ignored
`output/p07`. Existing test/audio emulation remains explicit. All device/STT
fixtures are inert; native process/pipe/SQLite checks remain real and test-owned.
No production microphone, hotkey listener, desktop app, model, settings,
elevation or security-policy changes were activated. All 115 inherited FAST
cases carry desktop-isolation properties via the explicitly loaded plugin.
Retain the P02 desktop-isolation correction; no historical exposure is erased.
Fixture keys remaining: zero. Unhandled thread exceptions fail the checks.

The isolated runner bounds each pytest invocation to 180 seconds and each test
uses a 20-second thread timeout. The runner itself returns zero after recording
pytest failure; **the actual pytest exit is reported below**, not inferred from
that wrapper. Commands below normalize only the Python executable and repository
report path; metadata retains their exact absolute values.

```powershell
python -m pytest tests/unit/test_runtime_shutdown.py tests/unit/test_backend_wiring_audit.py::test_runtime_close_drains_active_task_and_registry tests/unit/test_terminal_outcome.py tests/unit/test_backend_wiring_audit.py::test_fast_stop_preserves_supervisor_residual_outcome tests/unit/test_cleanup_evidence.py tests/unit/test_backend_wiring_audit.py::test_failed_worker_cleanup_requires_residual_state tests/unit/test_worker_cancellation.py tests/unit/test_executor_admission.py tests/unit/test_global_stop_ordering.py tests/unit/test_backend_wiring_audit.py::test_worker_stop_interrupts_outstanding_response_wait tests/unit/test_backend_wiring_audit.py::test_stop_during_prestate_prevents_executor_start tests/unit/test_backend_wiring_audit.py::test_global_stop_latches_every_task_before_first_grace -q -o addopts= -o junit_family=xunit1 --timeout=20 --timeout-method=thread --tb=short -ra -W error::pytest.PytestUnhandledThreadExceptionWarning -p no:cacheprovider --junitxml=output/p07/prerequisite-before.xml
# 204 passed in 22.30s; pytest exit 0; outer wall 23.376s.
```

```powershell
python -m pytest tests/unit/test_backend_wiring_audit.py::test_voice_stop_closes_capture_without_key_release tests/unit/test_backend_wiring_audit.py::test_empty_voice_capture_finalizes_its_capsule -q -o addopts= -o junit_family=xunit1 --timeout=20 --timeout-method=thread --tb=short -ra -W error::pytest.PytestUnhandledThreadExceptionWarning -p no:cacheprovider --junitxml=output/p07/before.xml --runxfail
# 2 failed in 0.57s; pytest exit 1; outer wall 1.224s.
```

```powershell
python -m pytest tests/unit/test_voice_session.py tests/unit/test_voice_pipeline.py tests/unit/test_voice_activation.py tests/unit/test_voice_vad.py tests/unit/test_brain_lifecycle.py tests/unit/test_voice_lifecycle.py tests/unit/test_voice_capture.py tests/unit/test_runtime_shutdown.py tests/unit/test_terminal_outcome.py tests/unit/test_db.py tests/unit/test_cleanup_evidence.py tests/unit/test_rollback_engine.py tests/unit/test_rollback_recipes.py tests/unit/test_worker_cancellation.py tests/unit/test_global_stop_ordering.py tests/unit/test_executor_admission.py tests/unit/test_task_supervisor.py tests/unit/test_tool_runner_ledger.py tests/unit/test_schemas.py tests/unit/test_ownership.py tests/unit/test_job_object.py -q -o addopts= -o junit_family=xunit1 --timeout=20 --timeout-method=thread --tb=short -ra -W error::pytest.PytestUnhandledThreadExceptionWarning -p no:cacheprovider --junitxml=output/p07/focused-final.xml
# 328 passed in 32.44s; pytest exit 0; outer wall 33.332s.
```

```powershell
python -m pytest tests/unit/test_backend_wiring_audit.py tests/unit/test_schemas.py tests/unit/test_router.py tests/unit/test_brain_validator.py tests/unit/test_policy_engine.py tests/unit/test_redaction.py tests/unit/test_activity_ledger_lifecycle.py tests/unit/test_rollback_engine.py tests/unit/test_rollback_recipes.py tests/unit/test_tool_runner_ledger.py tests/unit/test_perception_freshness.py tests/unit/test_phase13_7_ui_verification.py tests/unit/test_phase13_7_created_stop.py tests/unit/test_ipc.py tests/unit/test_voice_session.py tests/unit/test_voice_pipeline.py tests/unit/test_voice_activation.py tests/unit/test_voice_vad.py tests/unit/test_brain_lifecycle.py tests/unit/test_voice_lifecycle.py tests/unit/test_voice_capture.py tests/unit/test_runtime_shutdown.py tests/unit/test_terminal_outcome.py tests/unit/test_cleanup_evidence.py tests/unit/test_worker_cancellation.py tests/unit/test_global_stop_ordering.py tests/unit/test_executor_admission.py tests/unit/test_fast_orchestrator.py tests/unit/test_multi_step_orchestrator.py -q -o addopts= -o junit_family=xunit1 --timeout=20 --timeout-method=thread --tb=short -ra -W error::pytest.PytestUnhandledThreadExceptionWarning -p no:cacheprovider --junitxml=output/p07/regression-isolated.xml -k "not test_elevation_broker_execution" -p tests.fixtures.desktop_isolation
# 656 passed, 3 skipped, 1 deselected, 3 xfailed in 47.91s; pytest exit 0; outer wall 48.829s.
```

```powershell
python -m pytest tests/unit/test_runtime_shutdown.py tests/unit/test_backend_wiring_audit.py::test_runtime_close_drains_active_task_and_registry tests/unit/test_terminal_outcome.py tests/unit/test_backend_wiring_audit.py::test_fast_stop_preserves_supervisor_residual_outcome tests/unit/test_cleanup_evidence.py tests/unit/test_backend_wiring_audit.py::test_failed_worker_cleanup_requires_residual_state tests/unit/test_worker_cancellation.py tests/unit/test_executor_admission.py tests/unit/test_global_stop_ordering.py tests/unit/test_backend_wiring_audit.py::test_worker_stop_interrupts_outstanding_response_wait tests/unit/test_backend_wiring_audit.py::test_stop_during_prestate_prevents_executor_start tests/unit/test_backend_wiring_audit.py::test_global_stop_latches_every_task_before_first_grace -q -o addopts= -o junit_family=xunit1 --timeout=20 --timeout-method=thread --tb=short -ra -W error::pytest.PytestUnhandledThreadExceptionWarning -p no:cacheprovider --junitxml=output/p07/prerequisite-final.xml
# 204 passed in 19.25s; pytest exit 0; outer wall 20.015s.
```

```powershell
python -m pytest tests/unit/test_phase13_8_final_patch.py::TestTaskOwnedWorkerContainment -q -o addopts= -o junit_family=xunit1 --timeout=20 --timeout-method=thread --tb=short -ra -W error::pytest.PytestUnhandledThreadExceptionWarning -p no:cacheprovider --junitxml=output/p07/containment.xml
# 3 passed in 2.86s; pytest exit 0; outer wall 3.549s.
```

```powershell
python -m pytest tests/unit/test_app_lifecycle.py tests/unit/test_crash_recovery.py -q -o addopts= -o junit_family=xunit1 --timeout=20 --timeout-method=thread --tb=short -ra -W error::pytest.PytestUnhandledThreadExceptionWarning -p no:cacheprovider --junitxml=output/p07/recovery.xml
# 5 passed in 0.50s; pytest exit 0; outer wall 1.116s.
```

```powershell
python -m pytest tests/unit/test_backend_wiring_audit.py -q -o addopts= -o junit_family=xunit1 --timeout=20 --timeout-method=thread --tb=short -ra -W error::pytest.PytestUnhandledThreadExceptionWarning -p no:cacheprovider --junitxml=output/p07/raw-final.xml --runxfail
# 3 failed, 12 passed in 0.56s; pytest exit 1; outer wall 1.226s.
```

```powershell
python docs/completion/verify_requirements_matrix.py
# PASS: 298 source items, 324 traceable rows.
git diff --check
python output/p07/review.py
# Separate scope, original assertions, ownership, tested hashes/JUnit and privacy review.
```

**29 new session cases** exercise STOP without release, all pre-execution paths,
55 empty cycles/pruning, duplicate press/release, denied startup, native stop/
abort/close/readback failure, blocked startup/close, release crossing startup,
STOP during STT, actual registered voice/text execution and SQLite parity,
STOP before actual admission, stale callbacks, missing device library,
publication/attachment ordering, orphan release, failed-close retry, unknown
readback, global latch-all, and real pipeline low-confidence target rejection
with inert transcription. The inherited 46 shutdown cases are unchanged and
continue to verify native owned descendants/pipes, retained owner/store drain,
SQLite outcomes and unrelated fixture survival. Three further owned containment
and five recovery checks pass. No acceptance assertion is weakened.

The first implementation check was **322 passed in 32.74s** (`focused-first`),
then review added conservative normal-release/readback handling and six further
failure/race cases. No failed implementation check was hidden or deselected. The separate review
corrected an initial new-case count from 30 to the actual 29 JUnit cases.
Only final reports above match final tested blobs. The three inherited skips
(corpus entries without a no-LLM guarantee), one excluded elevation operation,
and three strict BA-08/09 xfails are not passes or approved limitations.
Raw `--runxfail` now has **3 failed, 12 passed**: both BA-08 STOP reply assertions
and BA-09 first credential ACL assertion. Both BA-07 assertions pass ordinarily.

## Remaining gates, Git and recovery

Two original findings remain: **BA-08** truthful typed STOP acknowledgement and
**BA-09** private atomic credential creation. P10 combined real Windows safety,
P13 native inference lifetime, P14 physical microphone/whisper.cpp cancellation,
accuracy/noise/latency/parity and P19 voice overlay/events remain open. This
emulation does not count as physical C-01/C-07/C-08/B-04 acceptance. No loaded
STOP p95, fifty full active/idle cycles, GPU, full unit/product/install, physical
hotkey/UI, adversarial recovery or release acceptance is claimed. A hung native
driver stays owned with pending/residual evidence and an open store until it
exits; bounded acknowledgement is not termination proof. No limitation is waived.

Commit/push is confined to `ui-wiring`; PR 2 targets `ui-polish-integration`,
PR 1 targets main, both draft/open/unmerged. Main/integration remain unchanged.
The pre-P07 recovery point is `e5643210d2795ac9d542021ef7adf06df736bef4`:
inspect using a **new** detached worktree without resetting any current checkout.
Existing worktrees, archive, tags and stash remain intact. Raw reports, keys,
model data, audio and caches are excluded from Git.

The exact next safe milestone is **P08 only**, after reading its contract and
rechecking P01-P07 prerequisites and fresh Git/PR state. Keep action entry
disabled. Do not start P08, merge or advance automatically.
