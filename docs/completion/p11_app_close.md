# E44: exact native graceful application close

2026-10-22, Asia/Calcutta; source parent `ccbfd6c`, branch `ui-wiring`.
P11 remains incomplete; P12 is forbidden.

close_app now reuses the verified same-user native process-close adapter instead
of taskkill/name-wide termination and legacy no-op verification. Targets are an
exact PID/creation time or one exact executable basename resolving to a unique
visible application process. Incomplete enumeration, duplicate names, stale identity,
title substrings, force arguments, cross-user/session and critical processes refuse.
Names are re-resolved before dispatch; capture and executor intent must match.

Strict schema validation and deterministic policy precede bounded required owned
execution. A non-undoable durable intent precedes WM_CLOSE. The retained original
handle must signal exit and independent readback must prove absence before success.
Unsaved-data dialogs and refusal remain with the application; timeout never falls
back to force. Irreversible closure is never offered as a reconstructive undo.
The existing graceful_close_process/terminate_process contracts remain intact.

## Evidence

`output/p11-native-env/Scripts/python.exe
output/p11_power_actions/run_checks.py app-close-focused-e44`:
**13 passed in 12.13s**, 13.132s wall.

Final `app-close-regression-e44`: **204 passed in 93.03s**, 94.120s wall.
Includes exact native application closure, graceful refusal, headless timeout,
unrelated-process preservation, denied policy before capture, strict schemas,
unique/ambiguous name resolution, text/voice requests and durable non-undoable
history; existing native process controls/inspection, app reads, policy, journal,
admission, tool subsets and raw backend audit checks. Actual exit zero, fixture
keys zero; reviewed source hashes match. No personal process/window was closed.
Owned fixtures are registered and Job-contained before resume and drained on exit.
No new dependencies, shell fallback, UI design, action wiring or P12 changes.

Catalog **50 registered / 23 unregistered; 38 IMPLEMENTED / 23 MISSING /
1 DEFECTIVE / 11 UNVERIFIED**. Seven P11 names still missing: open_file,
open_terminal and browser five. open_app/focus_app/focus_window, physical audio/
system effects, full undo_last and remaining A/D/H evidence remain open.
Continue remaining P11; no completion or P12 eligibility is inferred.
