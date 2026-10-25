# E55: P11 catalog-wide undo audit

Date: 2026-10-22; branch `ui-wiring`; tested source parent `7aed5cb`.

This audit closes the software-backed `undo_last` catalog gap identified in
E53. It does not complete P11 or waive physical-device and later-phase gates.

The focused cross-catalog native run covered durable manual undo for files,
window geometry/state, audio, owned application launch and browser actions,
along with guarded conflicts and existing manual-undo cases:

```powershell
output/p11-native-env/Scripts/python.exe -m pytest tests/unit/test_manual_undo.py tests/unit/test_file_move_identity.py tests/unit/test_file_operations_native.py tests/unit/test_window_geometry_native.py tests/unit/test_window_state_native.py tests/unit/test_audio_guards.py tests/unit/test_app_launch_native.py tests/unit/test_browser_native.py -q
```

Result: **161 passed, 1 failed in 114.02s**. The only failure was cleanup of
the private desktop fixture in
`test_native_launch_is_owned_before_resume_and_survives_only_success[success_then_undo]`:
its `finally` could not restore/close the test desktop. The test had completed
its undo assertions. The exact case then passed alone, and a separate run of
`tests/unit/test_app_launch_native.py` passed **16 tests in 5.19s**. The fixture
cleanup failure is recorded as a suite-isolation limitation, not counted as a
passing combined suite or as an undo failure.

The native clipboard suite was run through its existing owned fresh-logon
runner, avoiding the system-named station collision from direct execution:

```powershell
output/p11-native-env/Scripts/python.exe -m tests.fixtures.clipboard_logon clipboard-focused-writefinal
```

Result: **26 passed in 43.66s**. Runner exit was zero; the child used the same
user and integrity at a distinct logon, loaded no profile, left zero owned
processes, and confirmed the interactive clipboard sequence was unchanged.
Coverage includes Unicode copy, clear, actual paste into an owned edit control,
manual/automatic undo, ordered writes and conflict/expiry refusal.

Together with E27-E53 coverage for preferences, folders, recycle-only deletion,
window focus/state, geometry, cross-volume moves, browser selection, and the
legacy-record selector, the supported reversible catalog actions have guarded
inverse/readback evidence. Terminal handoff, app close, power requests and
remote site effects are explicitly non-undoable/irreversible paths and are not
presented as inverses. `CAT-undo_last` is therefore IMPLEMENTED at this bounded
catalog-test scope. The one combined-suite desktop cleanup failure above still
needs isolation before calling that mixed suite clean.

The direct clipboard attempt that encountered `WinError 183` did not mutate the
clipboard; the owned fresh-logon run above resolves the native fixture blocker.
No personal clipboard content was read or written.

P11 remains open for native active-desktop focus evidence, real audio mutation
evidence, physical system-action acceptance, D-10 runtime adapter behavior and
H-05 elevation dispatch/UAC evidence. H-04 native confirmation UI belongs to
P16. The 16 missing perception/input catalog entries remain P12 work and were
not changed.
