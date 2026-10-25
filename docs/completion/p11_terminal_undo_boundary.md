# E51 — P11 interactive PowerShell undo boundary (superseded by E52)

E52 ([PowerShell handoff is not manually undoable](p11_terminal_nonundoable_handoff.md))
supersedes this checkpoint's manual-undo handling. Successful `open_terminal`
is now journaled as a non-undoable commit, so `undo_last` reports
`UNDO_UNAVAILABLE` without claiming or attempting to close the terminal. The
earlier E51 probe remains evidence that the `powershell.exe` PID does not own a
top-level console window on the private desktop.

Date: 2026-10-22

The owner selected an opening-only PowerShell tool and will enter commands
manually. PLUMA must not type commands or close a console that may contain
manual user work.

The native fixture creates PowerShell on a never-visible private desktop. The
process identity is verified, but no top-level window is owned by the
`powershell.exe` PID: Windows hosts the console window in a separate process.
The generic application inverse therefore has no exact GUI close target.
`undo_last` returns `UNDO_UNVERIFIED` and leaves the PowerShell process and its
undo evidence intact. PLUMA does not guess the console-host PID or force-close
the process. The test fixture alone terminates its exact disposable process
after assertions.

Focused command:

```powershell
output/p11-native-env/Scripts/python.exe -m pytest tests/unit/test_terminal_window_native.py::test_real_powershell_open_only -q
```

Result: **3 passed in 2.28s** (exit 0): successful owned launch, STOP cleanup,
and manual-undo refusal on the isolated desktop. No commands were typed and no
personal terminal or process was touched.

This evidence confirms `open_terminal`'s bounded launch behavior and a safe
refusal. It does not close the catalog-wide `undo_last` gate: the interactive
terminal has no proven inverse once user work may exist.
