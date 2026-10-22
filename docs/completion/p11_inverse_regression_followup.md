# E56: clean P11 cross-catalog inverse regression

Date: 2026-10-22; branch `ui-wiring`; source parent `f791834` plus the
`tests/unit/test_app_launch_native.py` change recorded with this evidence.

E56 resolves the one fixture-teardown failure disclosed in E55. The native
app-launch test had repeated an exact process/window verification on pytest's
COM-used main thread after task finalization. The registered verifier had
already read back the launched image and window before finalization; the
subsequent `undo_last` path independently guards and reads back the receipt on
its owned desktop-bound worker. The redundant main-thread desktop rebinding was
removed. Success, ownership, undo, process-absence and durable-ledger
assertions remain.

Focused reproduction:

```powershell
output/p11-native-env/Scripts/python.exe -m pytest tests/unit/test_window_state_native.py tests/unit/test_audio_guards.py tests/unit/test_app_launch_native.py -q
```

Result: **76 passed in 26.01s**.

Full cross-catalog inverse regression:

```powershell
output/p11-native-env/Scripts/python.exe -m pytest tests/unit/test_manual_undo.py tests/unit/test_file_move_identity.py tests/unit/test_file_operations_native.py tests/unit/test_window_geometry_native.py tests/unit/test_window_state_native.py tests/unit/test_audio_guards.py tests/unit/test_app_launch_native.py tests/unit/test_browser_native.py -q
```

Result: **162 passed in 73.26s**, exit 0. The tested app-launch test file SHA-256
was `6250D3B021DEFC43FF5A22FAC95920518F9DA3C80C43D6C12637522AB030296D`.
Together with E55's **26 passed** owned fresh-logon clipboard run and prior
catalog evidence, this resolves the software-backed cross-catalog inverse
regression. It does not certify focus/audio hardware changes or physical power
effects and does not close D-10 or H-05. P12 remains untouched.
