# P11 E52: PowerShell handoff is not manually undoable

Date: 2026-10-22

The owner's scope is to open Windows PowerShell so the user can type commands.
After a verified launch, those commands and any resulting state belong to the
user. PLUMA therefore journals the successful launch as a committed,
non-undoable effect. `undo_last` does not attempt to close the interactive
terminal or leave a permanently claimed `app_launch` inverse behind.

The launch still captures and journals exact pre-state before dispatch. If
launch fails or is stopped before verified completion, the existing owned
cleanup path applies. STOP after a committed terminal launch terminates only
the exact PLUMA-created PowerShell process; the task reports
`STOPPED_WITH_RESIDUAL` because the terminal was a non-undoable effect.

The native fixture uses a never-visible private desktop. It verifies the
PowerShell executable, `-NoLogo -NoProfile` arguments, process identity,
committed non-undoable ledger state, no available undo record, STOP cleanup,
and refusal by `undo_last` without a claim or process close. The fixture alone
terminates its exact disposable process after assertions.

Focused checks:

```powershell
output/p11-native-env/Scripts/python.exe -m pytest tests/unit/test_terminal_window_native.py::test_real_powershell_open_only -q
output/p11-native-env/Scripts/python.exe -m pytest tests/unit/test_terminal_window_native.py tests/unit/test_manual_undo.py -q
```

Results: **3 passed in 1.95s** and **11 passed in 6.98s**, respectively (exit 0).
No command was entered and no personal terminal or process was touched.

This resolves the terminal-specific inverse mismatch. It does not close the
catalog-wide `undo_last` gate: unsupported legacy records and other remaining
catalog/A/D/H gaps remain open. P11 is incomplete; P12 remains forbidden.
