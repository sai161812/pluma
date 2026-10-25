# P11 bounded owned pre-state checkpoint (E22)

2026-10-20. Starting clean/pushed ui-wiring: `f4eea7b`. P11 remains
authorized and incomplete. P12 is forbidden; no action entry or merge enabled.
Master, AGENTS, shared/P11 prompt, build-plan Phase 11 and acceptance A/D/G/H
were checked before edits. Other worktrees, recovery archives/stash/tags and
native dark UI are preserved.

## Reproduction and prerequisites

Source inspection found `undo_builder` called synchronously before the tool
timer, outside the capsule's tracked futures. An inert blocked capture with a
150 ms tool budget did not return within an 800 ms observation window. The
fixture releases and drains the capture before asserting, so failed evidence
does not abandon work. `prestate-before-valid-result`: **1 failed in 1.71s**.

The first fixture executor accidentally returned None and failed with a result
attribute error instead. That setup was corrected to return a valid ToolResult;
the corrected reproduction above demonstrates the actual deadline defect.
The first corrected runner name selected its existing regression default rather
than the targeted case: **822 passed / 3 skipped / 1 excluded in 75.70s** on
unchanged runtime, before repair. Both artifacts are retained and distinguished.

## Implemented boundary

- Internal capture is part of the registered ToolSpec, after schema/policy and
  actual-entry cancellation admission. It is not a new planner API.
- Required process-isolated ToolSpecs capture inside the same capsule-owned
  killable worker/controller and Windows Jobs used for execution. The builder
  must serialize; refusal never falls back to an in-process call. Attach the
  controller before dispatch so STOP can reach it. Successful capture and
  execution reuse the same observed PID and original creation identity.
- Other captures use a tracked `prestate` Future with task ID and capsule
  ownership. STOP is polled while waiting; queued work is cancelled. A running
  Python thread cannot be killed safely and remains owned until actual exit.
  Shutdown refuses to close SQLite while that capture remains active. Late
  capture results cannot dispatch mutation or publish an undo journal.
- Capture and execution share the declared tool timeout. Worker startup is
  included in capture time. Policy and journal acknowledgement/cleanup safety
  waits retain their separately bounded budgets. Parent-side verifier waits
  and complete whole-call/catalog bounds remain open, so D-09 is not closed.
- Missing/invalid pre-state or capture exceptions refuse execution. Fixed
  diagnostics do not expose injected private exception values. Timeout latches
  TASK_TIMEOUT; explicit STOP preserves its first cause. Failed pre-state creates
  no usable inverse. Known no-execution history uses a two-second acknowledgement;
  failed acknowledgement reports LEDGER_WRITE_FAILED and cannot execute/replan.
- The prior redaction fixture's local capture closure was moved to an equivalent
  module-level partial so required isolation can serialize it. All existing
  private-value, persisted-redaction and retained-memory assertions remain.

## Verification

Ignored runner: `output/p11_prestate/run_checks.py`, native interpreter
`output/p11-native-env/Scripts/python.exe`. It uses isolated application/temp
storage, original Windows Jobs/process creation identities, bounded commands,
JUnit/log/JSON, source SHA-256 and actual pytest exits. Temporary test-only
system execution request restores in finally; no persistent power/security
policy change or idle feature. FAST regressions require desktop isolation.

Initial boundary: **90 passed / 1 failed in 26.73s**, because the old privacy
fixture's local closure correctly failed required serialization before reaching
its redaction assertions. Equivalent serializable fixture correction and new
ownership/budget cases: **100 passed in 28.71s**. Review added bounded failure
history acknowledgement: **101 passed in 26.26s**. Failures are preserved.

Final reviewed-source commands, each prefixed with the native interpreter and
`output/p11_prestate/run_checks.py`:

| Run argument | Actual pytest output | Runner wall |
|---|---|---|
| `focused-final` | 661 passed / 1 excluded, 97.83s | 98.860s |
| `regression-final` | 979 passed / 3 skipped / 1 excluded, 125.54s | 126.812s |
| `raw-final` (`--runxfail`) | 15 passed, 0.55s | 1.169s |
| `containment-final` | 3 passed, 3.10s | 3.849s |
| `recovery-final` | 5 passed, 0.56s | 1.241s |

All actual pytest exits are zero, final recorded source hashes match, fixture
credential-file counts are zero and all 115 FAST cases carry desktop isolation.
There are 13 new pre-state cases. The three skips belong to existing corpus
entries without a no-LLM assertion; the excluded elevation case would change
system state. These are not passes. No latency/soak/hardware claim. Skips, exclusions and injected adapters are not native device
acceptance. Native pre-state fixtures touch only owned temporary markers; no
user app/file/browser/clipboard/audio setting is changed.

## Remaining P11

No catalog row is newly complete: 6 IMPLEMENTED / 44 MISSING / 4 DEFECTIVE /
19 UNVERIFIED. Tool-specific identities and conflict-safe inverse, pending-effect
reconciliation, irreversible evidence, verifier ownership/bounds and remaining
typed catalog/A/D/H gates remain required. Native audio writes, clipboard,
browser sessions, actual elevation and other device scenarios are not certified.

The owner resolved terminal scope during this block: fixed read-only Windows
diagnostics plus explicitly configured, confirmed project commands. See
[scope decisions](p11_scope_decisions.md); it is no longer a pending question.

Next safe work remains P11, beginning with owned bounded verification and
tool-specific safe inverse/catalog gaps. P12 is not eligible or authorized.
Recovery before this block: create a separate detached worktree at `f4eea7b`;
never reset this checkout or overwrite other worktrees. PRs 1/2 were rechecked
draft/open/unmerged. Commit and push only ui-wiring.
