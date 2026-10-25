# P11 E54: reconcile the terminal policy gate

Date: 2026-10-22

The requirements matrix incorrectly said there were no registered terminal
ToolSpecs. P11 now registers fixed read-only diagnostic IDs, a separate
owner-configured and exact-confirmed project-command tool, and `open_terminal`,
which opens fixed Windows PowerShell for manual command entry only.

The planner cannot supply arbitrary command strings or scripts. Strict tool
schemas reject those before policy. Configured project commands require HIGH
exact-call confirmation. No ADMIN ToolSpec bypasses policy; elevation remains
blocked until the separate H-05 broker integration is implemented and tested.
This closes F-04's no-implicit-shell/admin-bypass condition, not H-05 or the
broader P11 gate.

Focused checks:

```powershell
output/p11-native-env/Scripts/python.exe -m pytest tests/unit/test_terminal_native.py tests/unit/test_terminal_window_native.py -q
output/p11-native-env/Scripts/python.exe docs/completion/verify_requirements_matrix.py
```

Results: **36 passed in 19.81s** (exit 0); **298 source items / 324 traceable
rows** passed (exit 0). No command was entered into the interactive terminal;
diagnostic fixtures use fixed IDs and owned bounded workers.

H-05 elevation dispatch and native UAC evidence, native confirmation UI, D-10
runtime adapter fallback, other `undo_last` inverses, and physical focus/audio
and system-action evidence remain open. P12 remains forbidden.
