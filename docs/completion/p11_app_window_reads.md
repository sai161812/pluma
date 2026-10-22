# E37: native application/window observations

2026-10-22, Asia/Calcutta; source parent `f29c0fc`, branch `ui-wiring`.
P11 remains incomplete; P12 is forbidden. No perception/input work added.

`list_apps`, `app_status` and `list_windows` now require owned isolated workers
and independent native readback. The tasklist subprocess, name-deduplicated
instances, dummy desktop results and no-op READ verifiers are removed. Enumeration
uses native top-level windows on the current desktop; background processes remain
available through list_processes. No launch, focus, close or user-state mutation.

List arguments are strict: visible_only, optional substring filter, max_entries
(1–256 observed window entries; grouped into processes for list_apps), and
max_scan_entries (1–2048). Window filters match captions, app filters match
executable names. Limits are explicit, not total-desktop-count claims. Native
empty observations require successful enumeration; callback/API failure cannot
become a verified empty list. Inaccessible/disappeared windows remain explicit
unavailable entries, with counts in factual history, never dummy applications.

Available windows carry HWND, PID, native creation time, thread/class identity,
bounded caption, visibility/minimized/maximized state and native rectangle.
Per-window DPI context is restored. Independent readback rechecks each exact
observed window/process; it does not claim the desktop cannot change after a
snapshot. Captions are capped at 2048 characters with a truncation flag. A filter
undecidable from a truncated caption refuses rather than silently omitting it.
Caption API errors cannot masquerade as empty titles.

Application grouping preserves distinct PIDs/creation times even when executable
names match, and preserves multiple windows per instance. app_status now requires
exact pid/creation_time from inspection, never a name substring or unbound PID.
Only native absence/replacement evidence reports that identity no longer live.
Unreadable status fails factually; it is not reported as not running. Legacy test
call sites were updated to the exact typed status contract.

## Evidence and bounds

Use `output/p11-native-env/Scripts/python.exe output/p11_app_reads/run_checks.py`
with a suite name. Python 3.12.10, Windows 11 build 26200; isolated APPDATA/
LOCALAPPDATA/TEMP/TMP. Text/JUnit/JSON retain commands, actual exits, source parent/
hashes, environment, wall times and fixture-key cleanup.

| Suite | Actual result | Wall seconds |
|---|---|---|
| app-reads-focused-reviewed | 108 passed in 34.63s | 35.238 |
| app-reads-regression-final | 415 passed / 1 elevation deselected in 79.58s | 80.199 |
| raw-e37 | 15 passed with --runxfail in 0.39s | 1.022 |
| containment-e37 | 3 passed in 2.78s | 3.372 |
| recovery-e37 | 5 passed in 0.43s | 1.047 |

The final regression includes the additional caption-error test/fix after the
focused run. Actual final exits zero, final hashes match, fixture keys zero;
matrix 298 source items / 324 rows PASS, diff check passes. Counts overlap;
elevation exclusion is not a pass. The unsafe historical Notepad launch/raw
PID-taskkill test is not selected; it is not READ acceptance or a passed app
lifecycle gate. No personal window is launched/focused/closed by this validation.

New cases cover real owned hidden windows, multiple same-name process instances,
native text/voice/SQLite pipelines, exact live/gone/reused identity, scoped empty
lists, limits, unreadable status, callback/native failures, invalid/denied calls,
stale/forged observations, 2048-character captions and undecidable filters,
truthy numeric availability rejection, and actual blocked-worker STOP/timeouts.
Initial focused results were 103 passes / two incorrect one-window-per-fixture
assumptions. Windows exposes helper windows too. Corrected tests bind both real
fixture windows and both process identities, and prove all helper-window handles
remain represented in grouping; no ownership or readback assertion was removed.

Catalog: **44 registered / 29 unregistered; 30 IMPLEMENTED / 29 MISSING /
2 DEFECTIVE / 12 UNVERIFIED**. Remaining P11 missing names: open_file, four
system actions, clipboard get/set, open_terminal, five browser tools. Remaining
unverified: open/close/focus app; focus/minimize/maximize/restore window;
cross-volume move; four physical audio mutations. Clipboard clear/full undo and
remaining A/D/H gates stay open. No P12 or release eligibility.

The owner has now resolved native power-request commit behavior in
[scope decisions](p11_scope_decisions.md): initiate after exact confirmation,
without forced app closing; record irreversible/uncertain effects. This does
not authorize disruptive automated validation on the active laptop session.
