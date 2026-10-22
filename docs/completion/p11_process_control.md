# P11 exact process control and irreversible intent (E29)

2026-10-21, Asia/Calcutta. Started from pushed `f7a6833` on ui-wiring.
P11 remains incomplete; P12 remains forbidden. No UI, dependencies, immutable
specification or personal apps/windows/device/clipboard/power settings changed.

## Behavior and safety

- Exact registered graceful_close_process / terminate_process require positive
  PID and native creation FILETIME. Force additionally requires the literal
  allow_unsaved_data_loss=true. Strict validation precedes policy. MEDIUM exact
  approval explains data loss/non-undoability; no free process name or shell.
- Required owned worker checks original native process handle, creation time,
  liveness, critical status, same user/session and rejects system/session-zero,
  worker/parent/resident-supervisor targets. Supervisor PID is an internal worker
  capability, never an accepted planner argument. No elevation or privilege grant.
- Graceful close enumerates bounded native top-level windows of that process,
  rechecks identities before WM_CLOSE and waits for original handle exit. Refusal,
  save prompt, absent supported windows, UIPI/access denial or timeout fail closed;
  no force fallback and no interaction with save dialogs. Force uses the original
  handle, not a PID/name-based shell kill. Only the requested process is targeted;
  this is not implicit process-tree termination or application-name resolution.
- Success requires original handle signaled, actual exit code and independent
  native process-absence/creation-identity check. Callback/API return alone is
  insufficient. Private native proof is excluded from JSON/history/user output.
- ToolSpec.non_undoable opts into durable intent before dispatch using the existing
  action/intent storage. Its row is unavailable as undo from the first write.
  No available inverse or final undo_record is published. The supervisor retains
  a non-undoable marker: interrupted/unverified outcomes stay unknown/residual,
  completed effects are recorded committed, and clean STOP never promises reversal.
  Missing ledger/intent builder, failed capture or failed journal prevents dispatch.
  Existing reversible mutation records retain their original behavior. No migration.

Scope: pluma/adapters/process_control.py, tools/processes.py, tools/base.py,
tools/registry.py, memory/activity.py, policy/engine.py, brain/tool_subset.py;
tests/fixtures/process_control_target.py and tests/unit/test_process_control_native.py;
current handoff, matrix/audit checkpoints and this evidence. Owned target fixtures
are registered and assigned to native kill-on-close Jobs while suspended before
resume. Hidden native fixture windows never show or take foreground focus.

## Verification

```powershell
output/p11-native-env/Scripts/python.exe output/p11_process_control/run_checks.py process-control-focused-3
output/p11-native-env/Scripts/python.exe output/p11_process_control/run_checks.py process-control-regression-reviewed
output/p11-native-env/Scripts/python.exe output/p11_process_control/run_checks.py raw-e29-final
output/p11-native-env/Scripts/python.exe output/p11_process_control/run_checks.py containment-e29-final
output/p11-native-env/Scripts/python.exe output/p11_process_control/run_checks.py recovery-e29-final
output/p11-native-env/Scripts/python.exe docs/completion/verify_requirements_matrix.py
```

- Focused before final boolean validation review: **20 passed in 15.99s**. The
  final regression includes all 21 final native process cases. Real graceful/forced exit, unrelated fixture
  survives, exact confirmation, original handle readback, durable unavailable
  journal, no undo promise, denied/stale/resident/supervisor/invalid targets,
  journal/missing-ledger refusal, graceful refusal with no force, durable intent
  before STOP, retained residual and false-proof rejection.
- Affected regression **427 passed / 1 deselected in 130.92s**, wall 131.968s.
  Existing inspection, new file/native undo, memory/routines, multi-step, outcomes,
  policy/intent/schema, journal, owned capture/verification, shutdown/cleanup,
  STOP and schema-selection suites. Deselected actual elevation operation is not
  a pass or waiver. Native Windows 11, Python 3.12.10; same isolated runner bounds.
- Raw backend --runxfail **15 passed (0.48s)**; native containment **3 (3.12s)**;
  recovery **5 (0.52s)**. Actual pytest exits zero, fixture keys zero, every
  recorded runtime/test source hash matches reviewed source.
- Final review reproduced Pydantic accepting integer 1/0 for Literal true/false.
  Force acknowledgement and the earlier copy overwrite flag now explicitly
  require boolean values, with new before-policy refusals. The first affected
  run passed 425 / 1 deselected in 133.87s before this correction; the reviewed
  427-case run includes both final new schema cases. Redaction/policy were not
  weakened. Scope also includes the bounded E28 files.py/schema-test correction.
- First focused run: 15 passed / one graceful success failed. Direct diagnostic
  exposed fixture PID/window mismatch: Windows venv python.exe redirected to a
  child. Changed only fixture launch to base Python and added ready PID/window
  ownership assertions; retained all original success/exit assertions. Next
  focused run 17 passed (15.52s); final focused adds journal/supervisor checks.
  Diagnostic failures remain recorded; no production success assertion relaxed.
- E28/E27 historical broad numbers are not reruns of this source. Current checks
  above are reported separately, without adding counts or claiming full product,
  physical UI/elevation/model/device/performance/release certification.

## Remaining gate

Catalog totals: 38 exact registered / 35 unregistered; 20 IMPLEMENTED /
35 MISSING / 2 DEFECTIVE / 16 UNVERIFIED. Sixteen P12 names untouched; 19 missing
P11 names remain mandatory. Native window/app/audio/clipboard inverses, remaining
catalog and A/D/H portions remain open. This closes bounded same-user process
control and its commit intent path; it does not authorize P12 or waive any gate.

[TerminateProcess](https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-terminateprocess),
[IsProcessCritical](https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-isprocesscritical),
[PostMessageW](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-postmessagew)
were checked against official native API documentation.
