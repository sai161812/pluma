# E42: guarded native minimize, maximize and restore

2026-10-22, Asia/Calcutta; source parent `b92a438`, branch `ui-wiring`.
P11 remains incomplete. P12 is forbidden.

The three existing window-state tools now replace legacy no-op verifiers and
non-Windows success stubs with strict exact HWND/PID/creation-time targets, or
an explicitly requested active-window snapshot. Partial identity and title-only
targets refuse. Active identity is checked again before dispatch. A durable owned
task journal is required; missing journal refuses before capture.

The on-demand native adapter captures window thread/class/DPI identity and
GetWindowPlacement state, invokes SetWindowPlacement asynchronously, waits for
bounded stable readback and independently verifies it. Hidden/unsupported windows,
stale identity, changed placement and uncertain effects are refused factually.
Successful receipts carry minimum placement state, not titles or screenshot data.
The existing manual and closed owned STOP inverse paths restore only unchanged
matching receipts, verify the native result and consume the durable undo record.

No new dependencies, foreground bypass, raw input, UIA/OCR, design or P12 work.
Native fixture windows live on a separate never-switched desktop; every test
process is registered and Job-contained before resume and verified absent on exit.
The fixture's default hidden-window behavior is preserved for previous tests.

## Verification

Use `output/p11-native-env/Scripts/python.exe
output/p11_power_actions/run_checks.py <label>`. Local ignored raw/JUnit/JSON
evidence is under output/p11_power_actions.

- Focused window-state-focused-e42-final: **15 passed in 16.67s** (17.540s wall),
  before adding four affected pipeline/journal/active-change cases.
- Final window-state-regression-e42-final: **171 passed in 100.79s** (101.512s
  wall), including all **19** final state tests, existing native geometry and
  app/window reads, policy, executor admission/cancellation, journal and undo.
- Commit-focused window-state-focused-e42-commit: **19 passed in 29.29s**
  (30.419s wall), after the additional immediate active-window recheck at the
  native commit boundary. Only this affected adapter changed after regression.
- raw-e42: **15 passed** with --runxfail. Actual exits and fixture-key counts zero.
  Reviewed source hashes match final regression except that documented final adapter
  change; the final 19-case metadata matches it.

Evidence covers all three real transitions, native manual undo and actual priority
STOP cleanup/inverse, newer-placement conflicts, invalid/ambiguous schemas, stale
PID creation time, cancellation before mutation, active-window change, no journal,
and shared text/voice capsule/SQLite paths. No pre-existing user window is changed.
Positive assertions were preserved through repairs; no fake native acceptance.

Retained failures: six initial tests exposed redaction of the hexadecimal class
hash in durable undo. It now uses the existing geometry adapter's byte-list
representation. Three follow-up assertions read STOP's bounded pending response as
terminal; tests now wait for the actual terminal latch. A first 169-pass/2-failure
regression caught transient asynchronous placement before final independent
readback and a native sharing race reading the fixture ready marker. Stable
placement readback and bounded marker-open retry repair these without weakening
postconditions, identity checks, timeouts or assertions. OS automatic inactive
minimized-position bookkeeping is normalized; relevant native placement remains
in the guard. Native semantics follow [WINDOWPLACEMENT](https://learn.microsoft.com/en-us/windows/win32/api/winuser/ns-winuser-windowplacement).

Catalog now **50 registered / 23 unregistered; 36 IMPLEMENTED / 23 MISSING /
1 DEFECTIVE / 13 UNVERIFIED**. Seven P11 names are still missing: open_file,
open_terminal and browser five. Focus/app lifecycle, cross-volume moves, physical
audio/system effects, full undo_last and remaining A/D/H gates stay open. Continue
remaining P11; no P12 eligibility or overall completion claim.
