# E45: guarded native window/application focus

2026-10-22, Asia/Calcutta; source parent `ff75cfe`, branch `ui-wiring`.
P11 remains incomplete; P12 is forbidden.

focus_window and focus_app replace legacy title-first targeting, unconditional
restore and non-Windows successes with exact native HWND/PID/creation-time and
placement guards. focus_app also accepts one complete, unique executable-name
resolution. Typed schemas, policy and durable owned journal precede required
bounded workers. Current foreground and both window identities are captured;
minimized targets are restored through the existing placement adapter.

SetForegroundWindow must actually read back the exact foreground identity. No
AttachThreadInput, synthetic Alt/keyboard, privilege change or other foreground
bypass is used. Failure/refusal remains factual. Successful private receipts add
post-state without replacing durable pre-state. Manual/closed owned inverse checks
the current foreground and both placements before restoring the prior placement
and foreground. Newer owner changes are preserved. No title or screenshot payload
is stored in the minimal undo record.

## Evidence and concrete limit

`output/p11-native-env/Scripts/python.exe
output/p11_power_actions/run_checks.py focus-focused-e45`: **15 passed in 1.11s**,
1.918s wall. Final `focus-regression-e45`: **158 passed in 84.70s**, 85.757s wall.
Actual exit/fixture keys zero; reviewed source hashes match. These include schema,
journal, cancellation, exact targeting, forward/readback, Windows refusal and
newer-foreground/placement inverse conflicts, plus existing native placement,
geometry, app-close/reads, policy, admission and undo/rollback regressions.

The focus-transition fixture is explicitly **inert**: it isolates foreground APIs
and is not native foreground acceptance. A separate retained native probe
(`python -m output.p11_power_actions.focus_probe`) attempted SetForegroundWindow
only for an owned window on a never-switched private desktop. Windows refused;
original interactive foreground stayed unchanged and owned cleanup completed.
No personal window was focused, minimized or closed for validation. The probe
confirms a test-environment restriction, not a successful native focus transition.
Do not weaken the production guard or invent a passing physical result.

Catalog counts remain **50 registered / 23 unregistered; 38 IMPLEMENTED /
23 MISSING / 1 DEFECTIVE / 11 UNVERIFIED**. Both focus tools now have guarded
implementations and deterministic inverse/refusal evidence, but remain UNVERIFIED
for permitted native active-desktop transitions. This is a concrete outstanding
acceptance limit, not an owner-approved waiver or P11 completion. Continue the
remaining app-launch/file/terminal/browser implementations; do not start P12.

Native boundary: [SetForegroundWindow restrictions](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-setforegroundwindow).
