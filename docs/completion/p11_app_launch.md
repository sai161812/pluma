# E46: owned native app launch, persistence and guarded undo

2026-10-22, Asia/Calcutta; source parent `b6aea5b`, branch `ui-wiring`.
P11 remains incomplete; P12 is forbidden.

open_app now uses a closed System32 alias schema and a tracked parent-service
executor. No arbitrary executable, arguments, cwd, interpreter, elevation, PATH
resolution or PLUMA_TEST_MODE bypass is exposed. Native image and directory
identity are captured and held across creation. The process starts suspended;
original PID/creation time and its separate Job are registered before resume.
This avoids trying to promote an app out of a transient worker's kill-on-close
Job. A real visible activatable app view and original process/image are read back
independently before success. System tool/no-activate overlays are not app views.

The new Job initially kills on close, preserving crash/STOP containment. Only
verified task success clears that flag with native readback and releases the
intentionally opened app to the user. Task cleanup then preserves it. Failed
promotion retains ownership; shutdown now checks the correct persistent_job key,
drains retained app Jobs and independently waits a bounded .3s on the original
registered process identity. An empty Job alone is not process-exit evidence.
Pre-assignment failure terminates only the original retained creation handle;
failed cleanup retains that handle under its owner for retry, never by raw PID.

Manual undo closes only the matching newly created instance, preserves newer app
views and verifies original process exit. Graceful refusal has no force fallback.
STOP drains the owned tree before the closed inverse. A deliberately held receipt
owner produces a factual residual, retained intent and no late success. Native
launcher exit/broker handoff is not claimed as an owned existing user instance;
unknown external effects remain a recorded residual even if the original exits.
Brokered/multiplexed apps without owned direct-instance proof remain unsupported.

The shared native graceful-close adapter also handles windows disappearing after
an earlier WM_CLOSE: it skips destroyed/replaced views, never redirects a close,
and still requires the original process handle's exit/readback. Policy, ownership
and no-force guarantees are preserved. Unsafe direct Notepad/raw-taskkill legacy
tests are replaced by stronger owned native launch/close/undo checks.

## Verification

Use `output/p11-native-env/Scripts/python.exe
output/p11_power_actions/run_checks.py <label>`; local ignored raw/JUnit/JSON
artifacts retain the following actual results. Source hashes/exits/fixture keys
are checked; counts overlap and are not full product certification.

| Label | Actual result | Runner wall seconds |
|---|---|---|
| launch-regression-e46-exitproof | 261 passed in 101.42s | 102.336 |
| launch-focused-e46-commit | 16 passed in 8.08s | 8.947 |
| raw-e46 (--runxfail) | 15 passed in 0.74s | 1.679 |
| containment-e46 | 3 passed in 3.62s | 4.568 |
| recovery-e46 | 5 passed in 0.79s | 1.954 |

The commit-focused run adds the final early-exit/handoff residual branch and
fixture case after the regression; its metadata matches final source. All other
reviewed runtime hashes match the affected regression. Native fixtures run on
never-switched private desktops with explicit Win32 STARTUPINFO.lpDesktop, Job
assignment before resume, exact owned cleanup and no personal app launch/close.
The closed real System32 charmap binding is read-only tested. Text/voice request,
SQLite intent/receipt, success persistence, STOP, safe manual undo, invalid schema,
missing journal, failed containment and failed promotion are covered. No ML,
global settings, personal browser profile or action UI changes are introduced.

Retained failures: initial fixture enumeration/startup assumptions were corrected
using explicit native startup/desktop support and no-console GUI launch flags.
Windows input indicators appeared after initial app creation; view selection now
uses native tool/no-activate roles rather than changing identity guards. Native
multi-window close exposed the disappearing-view race described above. An initial
clean-STOP assertion while deliberately holding an executor was inconsistent with
the existing P06 contract: the final test holds it through the residual decision
and proves retained ownership, original process absence and no late success.
A 260-pass/1-failure regression reproduced Job-empty-before-process-signal timing;
bounded independent exit proof repairs it. Exact PID/creation-time fixture-only
cleanup drained prior failed-run instances; no pre-existing process was touched.

Catalog **50 registered / 23 unregistered; 39 IMPLEMENTED / 23 MISSING /
1 DEFECTIVE / 10 UNVERIFIED**. Seven P11 names still missing: open_file,
open_terminal and browser five. Physical focus/audio/system and full undo/A/D/H
gates remain open. Continue all remaining P11 tools; no P12 eligibility is claimed.
