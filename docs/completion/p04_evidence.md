# P04: verified cleanup and retained residual ownership

Date: 2026-10-19 (Asia/Calcutta). BA-04's bounded gate passes; P01-P03 remain
green. P05 is the next gate and was not started. Full STOP, backend, device/UI,
installed-artifact and release acceptance remain open.

## Prerequisites and source

Started clean on local/remote `ui-wiring` at
`f6543d1a1df622e8f7d2a64131cd49d32343a298`. Branches, remotes, four worktrees
and both draft/open PRs were checked. The immutable master was already read
completely in P00 and is unchanged; reread STOP/ownership/verification/ledger,
AGENTS, shared contract/P04, handoff, Build Plan Phases 1/2/5, technology
contract and applicable G-01/G-03/G-06/G-07/G-09/G-10/H-08/final acceptance.
Inspected current runtime/tests and UI wiring/placement references. No locked
requirement, native dark UI or disabled action-entry contract was altered.

Before editing, matrix coverage passed (298 source items / 324 rows).
P01-P03 plus their three ordinary audit assertions freshly passed **72 checks
in 12.67s** (exit 0; wall 13.879s). Original BA-04 reproduced with `--runxfail`:
**1 failed in 0.42s**, exit 1, wall 1.038s: `Cleanup failure became STOPPED;
worker reference retained: False`. Original assertion remains unchanged; only
its strict marker is removed. Ignored `output/p04/prerequisite.*` and `before.*`
retain the pre-edit source hashes, exact commands and output.

Final tested source is the P04 commit containing this record, parent `f6543d1`:

| File | Git blob |
|---|---|
| `pluma/core/cleanup.py` | `ece1d0b43bdfe7016c8b470218ec2936b7077c35` |
| `pluma/core/job_object.py` | `2fddf535fcc1c769b26c95b853022bb0f8a17448` |
| `pluma/core/ownership.py` | `0afbce323770d162f50e2a77c84d82e54686fa8b` |
| `pluma/core/task_supervisor.py` | `240d63d36a8d6b1b9455e1c7017e20b95c34157d` |
| `pluma/memory/activity.py` | `795286c52cb3c0e064146fa72bbc9ae8f64e34d9` |
| `pluma/memory/db.py` | `4eb5396190d182c4345028e6b1b6c4b24b81e7c6` |
| `pluma/memory/migrations/0002_cleanup_reports.sql` | `5550d04089c74f2931a1a9df7c8879b11e958dfa` |
| `pluma/rollback/engine.py` | `9c3c481a60c2e9f883c04ed9d4353dfa24c3be84` |
| `pluma/rollback/recipes.py` | `b22ee4460ef67f8c1ba2c5e5ad9967388805985e` |
| `pluma/tools/registry.py` | `c9a4af7e9dfd58d4c8c5cfda98d2e946bf58de77` |
| `tests/unit/test_backend_wiring_audit.py` | `6da27aba6db5cb6a9ad983bd27cc0e20b24dbe33` |
| `tests/unit/test_cleanup_evidence.py` | `eea2b67494cb2cdd708ad465c53f7b1f2c86e9bf` |
| `tests/unit/test_global_stop_ordering.py` | `3db8f39139ae8e2be2f29baa75d638f903fa4f64` |
| `tests/unit/test_worker_cancellation.py` | `c6b5d524aac2b2d3e50597261d81aa72107c47a1` |

P01 cancellation/admission tests, P03 pipe adapter, desktop isolation plugin,
orchestrator, resident and app are unchanged. Final JSON reports record exact
vectors, SHA-256, platform, parent, isolated roots and wall time; Git blobs
normalize checkout line endings. Runtime reports/JUnit remain ignored.

## Cleanup contract

- Structured `CleanupEvidence` records resource ID/type, minimum ownership
  identity, readback code, verified flag and fixed error codes. Raw exception
  bodies, tool arguments and native handles are excluded from these reports.
  Historical failed attempts remain; latest evidence per resource determines
  unresolved cleanup. A successful function/native return is insufficient.
- Native Job Objects now read `ActiveProcesses` through
  `QueryInformationJobObject`. STOP waits for zero before closing the ownership
  handle. Termination/query/close failures retain it. A termination exception
  may resolve only through positive empty-job and closed-handle readback;
  failed attempts stay recorded. Native false termination/close returns raise.
- Worker cleanup retains the P03 process handle, task/PID/creation-time/class
  identity, job and pipe on uncertainty. Controller `verify_cleanup` checks
  startup completion, root exit and released job/pipe. Registry task/idle
  acquisition and close retain failed controllers rather than dropping them.
  Same-task disposal/STOP remains idempotent; no detached branch is created.
- The supervisor combines worker, task/persistent job, snapshot, registered
  resource, rollback, irreversible-effect and persistence evidence. It clears
  references only after readback. Unknown worker absence defers rollback and
  temporary deletion; partial/unverified rollback preserves temporary pre-state.
  Deferred records still persist each resource's minimum identity.
- Clean STOP requires all evidence resolved. Otherwise the core chooses
  `STOPPED_WITH_RESIDUAL`. Ordinary success cleanup failures become `FAILED`;
  they cannot discard the live owner or claim core success. Unresolved terminal
  capsules survive pruning. Failed unpublished preparations are retained
  separately without publishing a cancelled request as new active work.
- Registered temporary files/directories capture file identity; missing,
  changed or reparse-point identity is refused. File changes are preserved.
  Deletion reads absence back, marks release only after verification and retains
  failures. Released ownership never claims a later resource at the same path/PID. Existing task directories cannot be newly claimed; computed,
  unregistered paths and PREEXISTING files/job handles are not deleted/closed.
  Process resources are probed read-only with creation identity. A replacement
  PID is preserved; this adds no name/PID-based force termination fallback.
- Existing file/audio rollback recipes read their postconditions. Database
  rollback consumes only matching successfully restored memory pre-state;
  failed undo queries no longer become empty success. Partial conflicts and
  non-undoable effects remain factual residuals, with pre-state retained.
- Additive migration 0002 journals reports independently of task-history
  insertion. `ActivityLedger.record_cleanup` atomically mirrors into resources
  when the task row exists, redacts and reads the journal back. This covers
  STOP before history insertion without inventing input mode or command text.
  Queue acknowledgement is bounded to two seconds for these writes/terminal
  updates. Storage failure retains evidence and prevents clean core completion;
  an unavailable store cannot prove durable persistence. P05 still owns complete
  returned-result/history reconciliation, including late/failed writes.

Controller startup/join/pipe bounds remain P03's. Job empty-readback waits are
300ms per capsule/persistent job and use the remaining controller budget for
worker jobs. SQLite reads use the existing driver timeout. These are per-call
budgets, not whole-task/hotkey/p95 performance acceptance. No new ML/capture,
UI action, retry queue, recovery action, process killer or background worker
is added. Journal inspection does not authorize automatic recovery/deletion.

## Checks (E09)

Windows 11 build 26200, Python 3.12.10 x64, pytest 8.3.3. Each run uses unique
user-local LOCALAPPDATA/APPDATA/TEMP/TMP directories with inherited PLUMA_*
overrides removed. Existing conftest enables test/audio emulation. Only owned
fixture processes/jobs/pipes/files, SQLite and inert adapters are used. No
production resident, microphone, model, desktop target, elevation operation,
security-policy bypass or raw capture was activated. Fixture keys remaining:
zero. All 115 FAST cases carry the explicit desktop-isolation property.

Common options (each command also has `--junitxml=output/p04/<run>.xml`):

```text
-q -o addopts= -o junit_family=xunit1 --timeout=20 --timeout-method=thread --tb=short -ra -p no:cacheprovider
```

Outer pytest processes have a 180-second bound. Exact vectors/stdout are in
ignored JSON/TXT reports. The selected commands are:

```powershell
python -m pytest tests/unit/test_worker_cancellation.py tests/unit/test_executor_admission.py tests/unit/test_global_stop_ordering.py tests/unit/test_backend_wiring_audit.py::test_worker_stop_interrupts_outstanding_response_wait tests/unit/test_backend_wiring_audit.py::test_stop_during_prestate_prevents_executor_start tests/unit/test_backend_wiring_audit.py::test_global_stop_latches_every_task_before_first_grace <common options>
# Before edits: 72 passed in 12.67s; exit 0; wall 13.879s.
python -m pytest tests/unit/test_backend_wiring_audit.py::test_failed_worker_cleanup_requires_residual_state --runxfail <common options>
# Before edits: 1 failed in 0.42s; exit 1; wall 1.038s.
python -m pytest tests/unit/test_db.py tests/unit/test_cleanup_evidence.py tests/unit/test_rollback_engine.py tests/unit/test_rollback_recipes.py tests/unit/test_worker_cancellation.py tests/unit/test_global_stop_ordering.py tests/unit/test_executor_admission.py tests/unit/test_task_supervisor.py tests/unit/test_tool_runner_ledger.py tests/unit/test_schemas.py tests/unit/test_ownership.py tests/unit/test_job_object.py <common options>
# 183 passed in 20.10s; exit 0; wall 21.149s.
python -m pytest tests/unit/test_backend_wiring_audit.py tests/unit/test_schemas.py tests/unit/test_router.py tests/unit/test_brain_validator.py tests/unit/test_policy_engine.py tests/unit/test_redaction.py tests/unit/test_activity_ledger_lifecycle.py tests/unit/test_rollback_engine.py tests/unit/test_rollback_recipes.py tests/unit/test_tool_runner_ledger.py tests/unit/test_perception_freshness.py tests/unit/test_phase13_7_ui_verification.py tests/unit/test_phase13_7_created_stop.py tests/unit/test_ipc.py tests/unit/test_cleanup_evidence.py tests/unit/test_worker_cancellation.py tests/unit/test_global_stop_ordering.py tests/unit/test_executor_admission.py tests/unit/test_fast_orchestrator.py tests/unit/test_multi_step_orchestrator.py -k "not test_elevation_broker_execution" -p tests.fixtures.desktop_isolation <common options>
# 507 passed, 3 skipped, 1 deselected, 7 xfailed in 36.94s; exit 0; wall 38.087s.
python -m pytest tests/unit/test_phase13_8_final_patch.py::TestTaskOwnedWorkerContainment <common options>
# 3 passed in 3.60s; exit 0; wall 4.691s.
python -m pytest tests/unit/test_backend_wiring_audit.py --runxfail <common options>
# 7 failed, 8 passed in 0.88s; exit 1; wall 1.797s.
python docs/completion/verify_requirements_matrix.py
# PASS: 298 source items, 324 traceable rows.
git diff --check
# Passed.
```

Thirty-eight new cases cover failed/unknown worker exit, successful fallback
readback, failed/live/query/close Job Objects, registry retention, no-op and
failed temporary deletion, changed/missing identity, pre-existing protection,
partial real file rollback with preserved backup, irreversible effects, pruning,
ordinary success cleanup failure, read-only PID mismatch/live-process checks,
repeated STOP, snapshot no-op, unpublished preparation/journal reopen, redaction,
failed persistence/readback, bounded writer acknowledgement, five rollback no-op
postconditions, exact DB/memory consumption, undo-query failure and actual
supervisor/worker/descendant cleanup. The real path verifies root/descendant
exit, unrelated fixture survival, no late marker, cancellation action readback,
empty/closed jobs and complete SQLite report/state. Audio checks are emulation,
not hardware acceptance. Seven existing DB migration/WAL/writer cases also pass.

Test double changes are explicit: P02/P03 jobs/workers now provide independent
readback, and P02's old expected ROLLING_BACK-on-resource-error becomes the
required residual state. Its latch/order/request assertions are unchanged.
BA-08's resource-error setup stopped producing nonterminal state after P04;
its failure injection now occurs after the actual ROLLING_BACK transition.
The original nonterminal guard, IPC assertion and strict marker remain. P08's
defect is still reproduced; none of its assertions was weakened or counted
as repaired. The first new native fixture omitted a required ToolSpec verifier;
that setup error was fixed. Intermediate reports remain ignored, including
`regression-isolated-ba08-setup.*`; final reports use the source above.

The three inherited corpus skips and excluded elevation case are not passes
or approved limitations. Load `-p tests.fixtures.desktop_isolation` for this
bounded FAST suite; retain the [P02 isolation correction](p02_evidence.md).
No complete unit/product/device/install suite, hardware audio, reboot/PID reuse,
adversarial filesystem-race hardening or hotkey/loaded p95 is certified.

## Remaining blockers, next gate and Git

BA-01 through BA-04 pass their bounded gates. Five findings remain, BA-05
through BA-09, represented by seven raw assertion failures: FAST residual/history
truth, runtime drain, two voice cases, two IPC cases and credential privacy.
The live matrix retains broader mandatory tool/model/voice/screen/UI/security
and release gaps. Core cleanup evidence does not repair returned FAST/IPC
truth. No locked capability or acceptance requirement is waived.

Next is **P05 only**: reproduce BA-05, make returned results and history project
the supervisor's actual terminal outcome, preserve residual/rollback details,
and test racing STOP, non-undoable effects and storage failure. Do not advance
automatically or enable actions. P06 must drain retained terminal/preparation
owners and registry failures before storage shutdown. P10 must rerun combined
P01-P09 Windows/failure/rollback/shutdown/voice/ledger paths and repeated handle
lifecycle measurements. P26 owns performance; P27 owns broader recovery/race
hardening. P04 provides inspectable evidence, not a new recovery executor.

P04 is committed/pushed on `ui-wiring`; PR [2](https://github.com/sai161812/pluma/pull/2)
remains draft/open against `ui-polish-integration`, and PR [1](https://github.com/sai161812/pluma/pull/1)
remains draft/open against `main`. Main stays `6dbf589`, integration `9544752`.
Recovery before P04 is `f6543d1a1df622e8f7d2a64131cd49d32343a298`; inspect
using `git worktree add --detach <new-folder> f6543d1a1df622e8f7d2a64131cd49d32343a298`.
Existing worktrees, tags, archive and stash remain per
[workspace recovery](../workspace_cleanup.md). No merge, reset/clean, force
push, worktree switch or security-policy change was performed.

A separate diff review checks exact scope/source preservation, original audit
assertions and remaining markers, P01-P03 invariants, real tested hashes/JUnit,
isolation, native ownership, retention/postconditions, redaction and cleanup
failure paths. Only the ten runtime/migration files, four test files and four
handoff/evidence documents change. Generated output, credentials, captures,
models, user-local state and UI source are excluded from Git.
