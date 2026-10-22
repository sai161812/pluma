# P11 owned verification and interrupted-call checkpoint (E25)

2026-10-20, Asia/Calcutta. Starting pushed ui-wiring `2c5abf5`. Prior source
passed 761 focused / 1079 isolated regressions / 15 raw / 3 containment / 5
recovery checks. P11 is incomplete; P12 is forbidden. This is a bounded safety
repair, not certification of the tool catalog or product.

## Reproductions and review

- Blocked postcondition ran synchronously outside the tool budget. A 200 ms
  fixture did not return within an 800 ms observation window. Its barrier was
  released and drained before asserting: **1 failed in 2.02s**.
- Initial owned-verification boundary: **56 passed in 26.90s**. Expanded run:
  **63 passed / 6 failed in 43.13s**. Those assertions checked an unlatched token
  after terminal worker cleanup, which seals admission. They now observe the
  cause at action completion, before cleanup, and still require no fabricated
  deadline, no replan, retained pending state and verified worker absence.
- A missing observer variable in three protocol fixtures then gave **68 passed /
  3 failed in 45.79s**. Wiring corrected; **71 passed in 39.60s**. No product
  assertion, configured deadline, xfail or exclusion was relaxed to hide failure.
- Legacy executor STOP wait and admission-observation race: **72 passed in
  44.59s**. Four extra cases reproduced unhandled exception text leaking into
  results and an executor-raised TimeoutError being classified as the registry
  deadline: **4 failed in 4.74s**. Repaired set **76 passed in 48.44s**.
- Review added successful future completion racing an expired poll. Final
  boundary: **77 passed in 50.94s**. There are 22 new verification cases.
- Read-only inspection of the owned success fixture's completed SQLite database
  also found **SUCCEEDED / user_stop** without an actual user STOP. Native worker
  disposal cancels the parent token by default. This is a separate, recorded
  P11 factual-history defect; it is not waived or covered by a passing latch
  assertion. The overall audit tracks it explicitly.

## Implemented boundary

Capture, execution and postcondition checking share the declared tool budget;
policy, history acknowledgements and cleanup have separate bounded safety waits.
Required process-isolated tools run their verifier in the same capsule-owned
worker/Windows Jobs. Required executor/verifier serialization fails closed
before mutation dispatch. Legacy verifier Futures are tracked by task and
`verification` class, polled for STOP/deadline, and retained until actual exit.
Storage cannot close while a running owned verifier remains.

Internal verifier responses contain typed proof, not a new planner capability.
Wrong-tool, untyped and coerced proof replies fail without inventing a timeout.
Late proof after STOP cannot upgrade a pending mutation or report success.
Verification failure/timeout retains minimum pre-state and unknown effects;
SMART cannot replan or run another action while a mutation remains uncertain.

Legacy executor waits also poll STOP. A running action may have crossed actual
admission just before the caller observes cancellation and before its started
marker becomes visible. Only proven queue cancellation or completed non-entry
can discard unused undo. The race fixture demonstrates a real owned rename
after caller interruption while pending pre-state and failure history remain.
No Python thread is force-killed or detached.

The P01 admitted-body fixture is strengthened: the caller returns cancellation
while its already-admitted body remains blocked; the body is subsequently
released and explicitly drained; no verifier starts after STOP and no late
verified success is accepted. Original BA-03 assertions are unchanged. Existing
native journal/pre-state fixtures use equivalent module-level proof callables
so required serialization is exercised without changing their assertions.

Final registry history writes use bounded two-second acknowledgements. A later
history failure cannot change an existing TASK_TIMEOUT into a clean user stop;
FAST/SMART use the capsule's first cause. Unhandled executor/worker exceptions
produce fixed errors without private text. A callable's TimeoutError is distinct
from an expired Future wait, including completion racing the poll boundary.

## Checks and limits

Ignored runner: `output/p11_verification/run_checks.py`, native interpreter
`output/p11-native-env/Scripts/python.exe`. Isolated application/temp roots,
actual owned Windows workers/Jobs, original process identities, actual SQLite
and reopened history, JUnit/log/JSON and source hashes. Temporary test execution
request restores in finally; no persistent power/security change. No user
file/app/window/browser/clipboard/audio state is changed. Native rename effects
belong only to temporary fixtures. SQL/protocol/planner/thread barriers are
disclosed injection seams, not native device acceptance.

Final reviewed-source command prefix:
`output/p11-native-env/Scripts/python.exe output/p11_verification/run_checks.py`.

| Run | Actual output | Runner wall |
|---|---|---|
| `focused-audit-final` | 783 passed / 1 excluded, 103.29s | 104.138s |
| `regression-audit-final` | 1101 passed / 3 skipped / 1 excluded, 126.22s | 127.240s |
| `raw-audit-final` (`--runxfail`) | 15 passed, 0.38s | 0.940s |
| `containment-audit-final` | 3 passed, 2.65s | 3.245s |
| `recovery-audit-final` | 5 passed, 0.40s | 0.919s |

`output/p11-native-env/Scripts/python.exe output/p11_verification/run_ipc_audit.py`
also passed **39 Python/C# authenticated native IPC checks in 7.183s**, exit zero,
no production core/device/tool execution and zero remaining fixture keys. All
final runtime/test source hashes match; actual exits zero, fixture keys zero,
115/115 FAST cases isolated. Three corpus skips and elevation exclusion are
separate. Matrix and diff/staged checks pass. See [overall audit](p00_p11_audit.md). Skips/exclusions are
not passes. No hardware latency, soak, full native voice or release claim.

Catalog remains 9 IMPLEMENTED / 43 MISSING / 4 DEFECTIVE / 17 UNVERIFIED across
73 rows; 16 missing perception/input entries belong to P12 and are untouched.
P11 still has 27 missing non-P12 tools, 4 defective catalog tools, 17 unverified
tools, native blocking/rollback/inverse/irreversible/privacy/elevation gaps and
the newly confirmed cleanup-cause defect. No blanket approval or waiver exists.

Recovery before this block: separate detached worktree at `2c5abf5`. Push only
ui-wiring; preserve all other worktrees, main/integration, archives/stash/tags.
