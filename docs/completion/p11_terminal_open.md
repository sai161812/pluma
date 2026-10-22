# P11 E47: opening PowerShell only

2026-10-22, Windows 11 build 26200, Python 3.12.10, source parent 99255f9.
Owner explicitly requested only opening PowerShell and manual command entry.

open_terminal accepts {} only. Fixed System32 Windows PowerShell starts with
-NoLogo -NoProfile and native CREATE_NEW_CONSOLE. Original PID/creation/image
readback proves the launched process; no console-host/client, input, commands,
working-directory control, elevation or scripting interface is exposed.
The existing parent launcher registers the suspended process and Job before
resume; verified success promotes it to the user, STOP/failure drains ownership.
Native console creation is requested by CreateProcess; the private-desktop
fixture does not claim a physical active-desktop visual inspection.

Minimum launch identity is retained. Undo can verify an already closed original
process; a live console without a safely attributable GUI-close target refuses
inverse. It never force-closes a terminal containing later manual user work.
Full undo_last remains an open gate rather than an invented rollback promise.

Checks, isolated storage, native never-switched private desktop:

- `python output/p11_power_actions/run_checks.py terminal-window-focused-e47-simple`: **7 passed in 2.45s**, exit 0, wall 3.275s. Native process readback, success persistence, STOP drain and five argument rejections before policy.
- `python output/p11_power_actions/run_checks.py terminal-window-regression-e47-final`: **364 passed in 44.60s**, exit 0, wall 45.510s. Covers terminal diagnostics, native app launch, router, tool subsets, shutdown, cleanup, undo, policy and admission. Final runtime source hashes recorded in ignored JSON metadata.
- Earlier regression: 362 passes / 2 obsolete golden-route failures; corrected terminal/PowerShell routing to the new exact open_terminal tool and empty arguments. Earlier abandoned console-client/host probes failed window lookup and are not counted as evidence. Their owned Jobs drained; no pre-existing user processes or console input was touched.

Raw JSON/XML/output remain under ignored output/p11_power_actions.
Catalog: 51 registered/22 unregistered; 40 IMPLEMENTED, 22 MISSING, 1 DEFECTIVE,
10 UNVERIFIED. Six missing P11 names: open_file and browser five. P12's sixteen
names, physical focus/audio/system, complete undo and remaining A/D/H stay open.
P11 is incomplete. P12 must not start. Continue the remaining P11 tools.
