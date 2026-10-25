# P11 pending mutation evidence and history commit checkpoint (E21)

2026-10-20. P11 remains authorized and incomplete; P12 is expressly forbidden.
Starting clean source: `2f5e87c` on local/remote ui-wiring. The preceding block
passed 631 focused / 949 isolated regressions / 15 raw audit / 3 containment /
5 recovery checks before these edits. No UI, immutable requirement, dependency,
other branch/worktree, archive/stash/tag, model or device configuration change.

## Reproduction

A registered typed LOW fixture performs a real rename of an owned temporary
file, signals entry, then blocks in its native Job-owned worker. Before repair,
STOP left the renamed file present, with an empty memory undo stack and **zero
SQLite undo records**, while the persisted task said **STOPPED**. The worker was
drained even though the assertion failed. `journal-before`: **1 failed in 1.76s**.
This demonstrates lost pre-state and a false clean terminal claim, not a mock
success or an inferred problem from source inspection alone.

## Implemented boundary

- After schema/policy/pre-state and serialization checks, the registry publishes
  a `pending_mutation` envelope containing tool, unique operation ID and minimum
  captured pre-state. Publication checks the task latch under the capsule's work
  lock. No native action may begin without its existing actual-entry admission.
- With a ledger, both action and undo writes are acknowledged and the undo row
  is read back before dispatch. Each write has a two-second acknowledgement
  budget. A crash between the two writes cannot have an effect from this call,
  because dispatch follows both. Failed preparation refuses execution. An
  incompletely acknowledged DB journal is conservatively retained, never used
  as an executable inverse. Pre-state redaction occurs before storage.
- Successful verified execution atomically updates the **same** action and its
  inverse in one SQLite transaction, with bounded acknowledgement and readback.
  No duplicate action is inserted for preparation/completion. Original validated
  arguments, policy risk and approval remain associated with the attempt.
- STOP, timeout, partial executor failure and failed verification preserve the
  pending pre-state. A dedicated pending recipe reports MUTATION_OUTCOME_UNKNOWN
  without following the embedded action or touching its paths. The supervisor
  therefore retains residual evidence rather than declaring clean STOP or
  guessing an unsafe inverse. Tool-specific reconciliation remains required.
- A proven non-admission on the thread path consumes the unused undo row and
  removes its memory envelope; existing P01 assertions remain unchanged. Thread
  execution deadlines now latch TASK_TIMEOUT before returning, retaining first
  cause and actual owned Future lifetime. A still-running body stays owned.
- A worker's old undo-stack snapshot cannot overwrite a retained parent journal.
  Additions are merged; removals wait for final ToolSpec verification and history
  commit. Failed worker undo or contradictory final verification cannot discard
  parent pre-state.
- Failed postcondition verification emits POSTCONDITION_FAILED with fixed failure
  copy rather than the executor's success message. Verifier exceptions use fixed
  diagnostics. Ledger-write failure returns LEDGER_WRITE_FAILED with unknown
  effects; it cannot return audited success or log the private exception text.
  SMART ends the same capsule on journal/history failure, without another step
  or replan. FAST already uses its failure owner.
- If a completion acknowledgement is lost after the transaction committed, a
  later verified database inverse and atomic consumption may remove its matching
  pending memory record by exact action-row identity. It cannot discard another
  unrecorded pre-state or a failed/conflicting inverse.

Five runtime files change: registry, activity ledger, rollback recipes/engine and
multi-step fatal-error handling. No schema migration is needed. Existing public
tool arguments, TaskCapsule ownership, native Job containment, STOP priority and
terminal result/ledger projection are retained.

## Verification and observed failures

Ignored runner: `output/p11_journal/run_checks.py`, isolated local/roaming/temp
roots, cleared PLUMA_* overrides, real SQLite, bounded pytest/external calls,
log/JUnit/JSON/source hashes and fixture-key cleanup. It uses the same temporary
test-only execution-state request documented in E20 and restores it in finally;
no persistent power/security policy or resident feature changes. Environment:
Windows 11 10.0.26200, Python 3.12.10 x64 in ignored p11-native-env. Source/test
files never changed while pytest was running.

- Initial two interrupted-effect cases after repair: **2 passed in 3.52s**.
- Expanded new tests: **12 passed / 2 failed in 11.25s**, because two new fixture
  plans used DIRECT with two steps. Corrected to MULTI_STEP; schema/assertions
  were not weakened. Boundary/admission/ledger/rollback set: **74 passed in 16.83s**.
- Initial focused: **644 passed / 1 failed / 1 excluded in 106.91s**. An existing
  native worker/descendant cleanup case (2.817s) did not verify worker exit within
  the existing budget. The persisted task correctly said STOPPED_WITH_RESIDUAL,
  retained WORKER_CLEANUP_UNVERIFIED and deferred inverse/temp cleanup, with empty
  closed Jobs. A later creation-identity check verified original worker absence.
  No matching standby events were found in the queried interval; the exact delay
  is undetermined. This failed run remains evidence, not relabeled as passed.
- Same cleanup case passed unchanged in **1.53s**. Inspection also found that its
  fixture finally skipped later owners if registry.close raised. Nested finally
  now attempts capsule cleanup, native child-handle close and unrelated owned
  helper termination/wait even after an earlier close error. A new injected-close
  check verifies that ordering. All original native assertions/budgets remain.
- Corrected focused set: **646 passed / 1 excluded in 102.79s**. Final review
  strengthened reopened undo-row assertions and added a direct pending-recipe
  refusal check. Before the final ordering review: **647 focused passes / 1
  excluded in 100.10s**; isolated regressions **965 passed / 3 skipped / 1
  excluded in 123.93s**.
  Raw --runxfail audit: **15 passed in 0.51s**; native containment: **3 passed
  in 3.36s**; recovery: **5 passed in 0.55s**. At that stage pytest exits were
  zero, fixture key counts zero and all 115 FAST cases carried
  isolation tags. Exclusion/corpus skips are not acceptance.

Final diff review also moved worker-undo consumption after final verification
and history publication. Its new fixture first correctly hit POLICY_DENIED
because undo_last is MEDIUM; an explicit exact-task host approval fixture was
added, preserving the risk floor. Reviewed boundary: **76 passed in 15.81s**.
Reviewed-source focused: **648 passed / 1 excluded in 131.43s**. Final reviewed
regressions: **966 passed / 3 skipped / 1 excluded in 114.77s**; raw --runxfail
audit: **15 passed in 0.46s**; native containment: **3 passed in 3.17s**; recovery:
**5 passed in 0.63s**. Final reviewed runtime/test source hashes match all five
reports, pytest exits are zero, fixture key counts zero and all 115 FAST cases
are isolated. Skips/exclusion do not count as acceptance.

Commands use `output/p11-native-env/Scripts/python.exe`:

```text
output/p11_journal/run_checks.py journal-before
output/p11_journal/run_checks.py journal-tools-first
output/p11_journal/run_checks.py journal-tools-expanded
output/p11_journal/run_checks.py journal-tools-boundary
output/p11_journal/run_checks.py focused-final
output/p11_journal/run_checks.py cleanup-unchanged-repro
output/p11_journal/run_checks.py focused-rechecked
output/p11_journal/run_checks.py focused-final-source
output/p11_journal/run_checks.py regression-isolated
output/p11_journal/run_checks.py raw-final
output/p11_journal/run_checks.py containment
output/p11_journal/run_checks.py recovery
output/p11_journal/run_checks.py journal-tools-final-boundary
output/p11_journal/run_checks.py focused-reviewed-source
output/p11_journal/run_checks.py regression-reviewed-source
output/p11_journal/run_checks.py raw-reviewed
output/p11_journal/run_checks.py containment-reviewed
output/p11_journal/run_checks.py recovery-reviewed
python docs/completion/verify_requirements_matrix.py
git diff --check
```

The 16 new cases cover real owned file effects before STOP/timeout, explicit
post-effect failure, successful one-row journal upgrade and actual inverse,
preparation action/undo/readback faults, lost completion acknowledgement before/
after commit, atomic transaction failure via an owned SQLite trigger, failed
verifier copy, pre-state redaction, no SMART next step/replan, reopened retained
undo, refusal to blindly execute a pending inverse and rejected final worker-undo
verification. Native workers/Jobs and
SQLite are real; fault/error seams and the typed fixture tool are explicit.
No user files, windows, clipboard, browser, microphone or audio state are changed.

## Remaining work and recovery

This closes the lost-evidence/false-clean gap when a tool has an undo builder.
It does not certify every existing tool's pre-state, metadata/conflict detection,
safe inverse, full-call timeout or irreversible commit handling. Pre-state
builders still run synchronously on the caller; moving blocking capture into
bounded owned execution is the next P11 safety block. A partial effect without
enough identity evidence stays residual; no generic inverse is promised.

Catalog totals stay 6 IMPLEMENTED / 44 MISSING / 4 DEFECTIVE / 19 UNVERIFIED.
All 73 entries and A/D/H requirements remain present. No limitation is waived,
no native timing/performance/soak claim is made and P11 is not complete. Continue
already authorized P11 only; do not start P12, enable action entry or merge.
Recovery before this block: `2f5e87c` in a separate detached worktree. Commit/push
ui-wiring only; preserve other worktrees/archive/stash/tags.
