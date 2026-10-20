# Backend audit before action wiring

Current status after P07 (2026-10-20): BA-01 through BA-07 pass bounded gates
with ordinary passing audit regressions. Two findings remain, reproduced by
three raw assertion failures. [P07 capture ownership evidence](../../../docs/completion/p07_evidence.md)
and [P06 shutdown evidence](../../../docs/completion/p06_evidence.md), plus
[P05 outcomes](../../../docs/completion/p05_evidence.md),
[P04 cleanup](../../../docs/completion/p04_evidence.md),
[P03 workers](../../../docs/completion/p03_evidence.md),
[P02 latch/isolation](../../../docs/completion/p02_evidence.md) and
[P01 admission](../../../docs/completion/p01_evidence.md) supersede earlier
next-fix/count statements. Capture now closes on task STOP without key release;
empty/failed/denied paths finalize, and pending owners prevent clean shutdown.
Both original BA-07 bodies/setup/assertions are unchanged; only their strict
markers are removed. Device/STT adapters are inert here; P14/P19 physical voice
acceptance remains. Final isolated checks: 656 passed, 3 skipped, 1 deselected,
3 xfailed; raw audit: 3 failed, 12 passed. STOP acknowledgement remains BA-08,
initial credential privacy remains BA-09. Action entry stays disabled;
**P08/BA-08 typed truthful STOP is next** and has not started. Remaining audit
assertions/setup/strict markers are unchanged. The original audit below remains
historical evidence for its named source, not backend/release certification.

Date: 2026-10-19. Requested scope: inspect the backend used by `ui-wiring`,
reproduce suspected defects, preserve existing work/appearance and record the
next safe implementation step. This is an audit report, not production fixes
or acceptance of the backend/release.

## Baseline and decision

- Audited wiring source: `64559bd256b18bc33a04b47076bbc3f89fa4f2eb`.
- Its `pluma/` tree is `b3ae9d24471ee38ebc5e08965d4e128c9ac3a5f0`, identical
  to `main` / GitHub `main` at `6dbf58925352d41a0196dda33044b18282cc6ddf`.
  Findings concern the existing backend, not a backend rewrite during UI polish.
- Read the complete immutable master specification, agent contract, build plan
  and acceptance tests. Current work remains the first bounded Phase 14 wiring
  step; action submission has not been enabled.
- Nine findings were reproduced in eleven assertions. Eight are P1/high,
  requiring correction before action wiring; one is P2/medium with a conditional
  Windows storage-permission trigger. No P0 finding is claimed.
- Keep command entry disabled. The verified read-only status step can remain.
  A passing existing regression suite does not establish the missing guarantees.

Only the audit test file, this report and the handoff were changed. No
production Python, XAML, C#, palette, component geometry, immutable specification
or build/acceptance requirements were changed. No merge was performed.

## Findings by severity

P1 means a safety/lifecycle or factual-result requirement fails in the isolated
scenario and blocks action wiring. P2 means a reproduced conditional security
gap requiring correction before deployment; exposure of this user's actual key
or compromise by another account has not been established.

| Severity | ID | Finding | Source |
|---|---|---|---|
| P1 | BA-03 | Executor can start after STOP during pre-state capture | [registry.py](../../../pluma/tools/registry.py#L473) |
| P1 | BA-01 | Global STOP waits for earlier tasks' cleanup before latching later tasks | [task_supervisor.py](../../../pluma/core/task_supervisor.py#L429) |
| P1 | BA-02 | Worker STOP waits on the lock held by outstanding execution | [registry.py](../../../pluma/tools/registry.py#L204) |
| P1 | BA-04 | Failed worker termination loses ownership reference and can become clean STOPPED | [task_supervisor.py](../../../pluma/core/task_supervisor.py#L337) |
| P1 | BA-05 | FAST result and persisted task state lose STOPPED_WITH_RESIDUAL | [orchestrator.py](../../../pluma/core/orchestrator.py#L263) |
| P1 | BA-06 | Runtime close does not drain active tasks or close the tool registry | [app.py](../../../pluma/app.py#L119) |
| P1 | BA-07 | Voice STOP leaves capture running; empty capture leaves an active capsule | [resident.py](../../../pluma/core/resident.py#L85) |
| P1 | BA-08 | IPC reports stopped tasks despite nonterminal cleanup or residual effects | [resident.py](../../../pluma/core/resident.py#L181) |
| P2 | BA-09 | First Windows IPC key can inherit a broadly readable ACL | [ipc.py](../../../pluma/core/ipc.py#L95) |

### BA-03: executor admission after STOP

Spec sections 3, 6, 12.1 and acceptance G-02/F-08 require no new executor
start after the latch. `ToolRegistry.execute` checks cancellation before
`undo_builder`, then dispatches later without another admission boundary. The
probe cancels the actual capsule token in pre-state capture; an audit-only
executor subsequently records that its entry saw the latch already set:
`Executor started after the latch was set: [True]`.

Recommended fix: make cancellation and executor admission obey one defined
ordering, including queued thread work and process-worker dispatch. Recheck at
the actual execution boundary, not only before potentially blocking pre-state
work. Preserve ownership, policy, verification and undo capture. An additional
early check alone is not proof that queued work cannot start after STOP.

### BA-01: global latch ordering

Spec 12.1/12.2 and G-02 require latching before cleanup. The global method
iterates `stop_task`, each of which performs its grace/termination/rollback
before the next task is considered. A deterministic sleep seam records
`[(True, False), (True, True)]`: the second task is still uncancelled at the
first task's cleanup grace. The configured default grace is 0.5 seconds per
task; this audit does not claim measured physical hotkey p95 latency.

Recommended fix: capture active tasks and latch all their tokens before any
grace wait, rollback or cleanup. Define admission behavior for requests racing
the stop request. Cleanup can then run in owned, bounded work independently of
acknowledging the latch.

### BA-02: termination lock contention

Spec 12.1 and G-01/G-10 require owned unresponsive workers to be interruptible.
`execute_call` holds the controller lock while waiting on its connection;
`terminate_and_join` needs the same lock. With an event-controlled fake
connection, termination cannot complete within 150 ms and completes only after
the test owner releases the outstanding response wait. Both test threads are
joined. No child process was spawned or killed by this reproduction.

Recommended fix: separate execution serialization from cancellation/termination
ownership. Ensure STOP can interrupt response I/O and terminate/read back only
the registered owned worker tree without waiting for the tool's full timeout.
Validate this with a real owned Windows worker/Job Object after the unit fix.

### BA-04: cleanup failure can look clean

Spec 12.2/15 and G-06/G-10 require verified cleanup and residual accounting.
An injected owned controller raises on termination. The supervisor logs the
error, clears its reference in `finally`, then bases residual state on undo
outcomes alone. Observed: `Cleanup failure became STOPPED; worker reference
retained: False`. This proves lost failure/ownership evidence, not that a real
OS process survived a Job Object kill.

Recommended fix: retain cleanup failures and identity until termination or
absence is verified. Combine worker, Job Object and resource-cleanup readback
with rollback outcomes when selecting final state; never infer clean completion
from a swallowed exception or a discarded handle.

### BA-05: residual state overwritten in FAST

Spec 12.2/16 and G-06/G-07 require residual effects in final state and history.
An audit executor sets STOP with a non-undoable marker. The actual supervisor
chooses `STOPPED_WITH_RESIDUAL`, but the FAST route keeps its local `STOPPED`
value, returns it and writes it over the task in a real in-memory SQLite ledger.
Observed: `Supervisor STOPPED_WITH_RESIDUAL; returned STOPPED; ledger STOPPED`.

Recommended fix: wait for/read the supervisor's authoritative terminal outcome
and project that outcome into result, IPC and ledger consistently. Preserve
residual/rollback detail and avoid two competing terminal-state writers.

### BA-06: shutdown omits task/registry drain

Spec 13/25 and G-10 require clean owned shutdown. The actual runtime `close`
method is exercised with its external services replaced by inert fixtures and
an active real capsule. Observed after close: `state=RUNNING; latch=False;
job closed=False; worker drained=False; registry closed=False`. It closes the
resident/model lifecycles/database but never drains the supervisor or calls
`tool_registry.close`.

Recommended fix: stop admission, latch/cancel active work, drain owned handlers,
capture and workers, verify cleanup and persist terminal outcomes before
closing storage. Close registry resources explicitly. This probe does not
establish whether OS process-exit cleanup ultimately kills a real child.

### BA-07: incomplete voice capsule lifecycle

Spec 7/12 and C-07/G-10 require capture to obey the task token. The resident
starts capture without connecting STOP to capture shutdown. The fake capture
remains recording after the real supervisor reaches STOPPED, until key release.
Separately, an empty capture returns before finalizing its capsule and leaves
`CREATED` in `get_active_tasks`. The existing voice STOP test checks after key
release, so it does not cover immediate capture cancellation.

Recommended fix: own capture within its capsule and cancel/close it immediately
on STOP. Finalize every empty, failed and cancelled capture path, preserve the
same capsule into transcription/execution, and serialize press/release/shutdown
races. Real microphone/STT device behavior remains untested here.

### BA-08: IPC STOP is not verified terminal evidence

Spec 5/12/15/16 and G-06/G-10 require factual outcomes. Two probes use the actual
resident handler and supervisor: residual state is omitted from the reply; and
a cleanup exception leaves a capsule in `ROLLING_BACK` while its ID is returned
inside `stopped_tasks` with `status: ok` and `All active tasks stopped.`.
`stop_all_active_tasks` returns its original candidate IDs even after errors.

Recommended fix: distinguish latch acknowledgement from completed cleanup.
Provide typed per-task terminal/pending/residual outcomes backed by supervisor
and ledger readback. The future C# bridge must never turn transport `ok` or the
candidate count into a clean cancellation claim. Do not invent a UI push
protocol without separately defining/testing its contract.

### BA-09: first-key creation bypasses Windows ACL guarantee

Spec 14/25 and IPC's own contract require private per-user authentication
material. A new empty fixture directory is given an inheritable Builtin Users
read ACE, preserving owner control. The production factory returns a new
32-byte key; its own validator then rejects that file's actual inherited ACL.
Existing-file validation runs only on later opens; first creation uses
`os.open(..., 0o600)` and returns without Windows ACL verification.

Recommended fix: create credentials atomically with an explicit safe Windows
owner/DACL, validate the opened file for both new/existing paths, and fail
closed on unsafe permissions or competing creation. Keep the C# reader's
permission checks. The deliberately permissive directory and key were fixture
resources only; the user's actual credential/ACL was not read or changed.

The native fixture uses Windows' documented [OW/BU SID aliases](https://learn.microsoft.com/en-us/windows/win32/secauthz/sid-strings)
and [SetFileSecurityW](https://learn.microsoft.com/en-us/windows/win32/api/securitybaseapi/nf-securitybaseapi-setfilesecurityw).
No second-user impersonation or cross-account pipe attack was attempted.

## Executed evidence and reproducibility

Test source: [test_backend_wiring_audit.py](../../../tests/unit/test_backend_wiring_audit.py).
Its functions map BA IDs in strict `xfail` markers. Eleven assertions cover
nine findings, with four passing controls: unknown tool and invalid arguments
are rejected before policy, failed verification cannot become success, and an
already-cancelled task cannot start its executor.

Environment: Windows 11 build 26200; Python 3.12.10, pytest 8.3.3. Each pytest
run was a bounded child process with isolated LOCALAPPDATA, APPDATA, TEMP and
TMP under a unique user-local Temp root; inherited `PLUMA_*` overrides were
removed. Audio emulation/test mode comes from existing `tests/conftest.py`.
No resident hotkeys, user apps, microphone, models, elevation operation or
production credentials were activated. IPC regressions used unique test pipes.
The native ACL fixture changes only its own newly created empty directory.

Final reports, complete command vectors, source/test hashes and JUnit:
`output/backend-audit/20261019-113604-da2f4a6f/` (ignored local artifacts).
`metadata.json` records test SHA-256
`1d38be44327264756460d76f0e71faa7ea77f1eab9773448bad6e894c295e525`.
Remaining fixture key count after the final run: zero. Earlier diagnostic
runs are retained separately and are not substituted for these final results.

In that isolated child environment, the focused commands were:

```powershell
python -m pytest tests/unit/test_backend_wiring_audit.py -q -o addopts= --timeout=15 --timeout-method=thread --tb=short -ra
# 4 passed, 11 xfailed in 0.97s; exit 0.

python -m pytest tests/unit/test_backend_wiring_audit.py --runxfail -q -o addopts= --timeout=15 --timeout-method=thread --tb=short -ra
# 11 failed, 4 passed in 0.97s; exit 1, expected defect evidence.
```

`xfail(strict=True, raises=AssertionError)` records known defects explicitly;
unexpected setup exceptions still fail. Expected failures are not passing
acceptance checks. Resolving a defect produces XPASS until its marker is removed.
`--runxfail` exposes the actual failures and must be green after remediation.

The subsequent regression command used the same bounds/options plus
`-k "not test_elevation_broker_execution"` and these files under `tests/unit/`:

```text
test_backend_wiring_audit.py
test_schemas.py
test_router.py
test_brain_validator.py
test_policy_engine.py
test_redaction.py
test_activity_ledger_lifecycle.py
test_rollback_engine.py
test_rollback_recipes.py
test_tool_runner_ledger.py
test_perception_freshness.py
test_phase13_7_ui_verification.py
test_phase13_7_created_stop.py
test_ipc.py

277 passed, 1 deselected, 11 xfailed in 9.40s; exit 0.
```

Of those 277 passes, 273 are existing regressions and four are new audit
controls. The elevation operation is intentionally unexecuted, not approved as
an acceptance limitation or counted as passing. No full unit, physical-device,
performance or release suite is claimed.

## Verified scope, remaining uncertainty and next safe step

Verified: the nine described control-flow/permission failures, the four controls,
and the selected regression behaviors. BA-09 uses real Windows ACL inheritance;
BA-05 uses real SQLite readback. The other failure injections use inert adapters,
fake worker connections/controllers and owned joined threads to avoid user effects.

Still unverified: real hotkey p95 under load; actual hung worker/descendant
containment and OS cleanup; real microphone/STT/OCR/planner cancellation; installer
and clean-profile behavior; cross-account authentication; ten-minute idle GPU/CPU
and fifty-cycle lifecycle measurements; full screen freshness/DPI behavior;
all adapters/tools; complete UI/backend end-to-end and release acceptance.
No assumption in this list is promoted to a passed requirement.

Next bounded implementation: repair BA-03's STOP/executor-admission boundary
first, including cancellation during pre-state work and queued worker entry.
Keep command entry disabled and preserve the UI. Convert its reproduction into
an ordinary passing regression, add controlled ordering tests at dispatch, then
run the focused and relevant suites and commit the fix separately.

Then address latch-all ordering and interruptible worker termination (BA-01/02),
cleanup/residual/result truth (BA-04/05/08), shutdown/voice ownership (BA-06/07)
and credential creation (BA-09), each in reviewable commits. Re-run this audit
without xfail handling and the relevant real-owned Windows integration checks
before enabling text submission/STOP wiring. Do not continue automatically into
those fixes as part of this audit.

Recovery stays at [pre-ui-wiring-2026-10-19](wiring_recovery.md); no reset or
history rewrite is required. `main` and the other worktrees remain unchanged.
