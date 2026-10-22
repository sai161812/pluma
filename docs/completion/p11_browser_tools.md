# P11 E48: owned browser tools and file viewing

2026-10-22, Windows 11, Python 3.12.10. Implements the six remaining exact
P11 catalog names: `open_file`, `open_url`, `list_tabs`, `focus_tab`, `close_tab`
and `download_status`. No P12 work is included.

The browser adapter supports fixed installed Edge and Chrome binaries, each in
a separate PLUMA-owned profile. It never attaches to personal profiles or
pre-existing browser windows. Calls use bounded loopback CDP against the exact
launched process; schemas expose only fixed browser operations, literal local
file paths and HTTP(S)/blank URLs. Browser tab IDs and session IDs are scoped to
the owned session. `open_file` supports bounded text, HTML, image and PDF
viewing. Opening a URL can have remote side effects, so closing that tab cannot
undo effects on the remote site. Closing a tab requires exact URL confirmation
and is non-undoable. Focus and newly opened tabs have guarded inverses.

Private native fixtures used real Edge and Chrome binaries, PLUMA-only profiles,
a never-switched private desktop and a loopback-only HTTP server. They checked
native tab listing/selection, confirmation, focus undo, open-tab undo and STOP
cleanup; local text and valid one-page PDF viewing; a real local download and
the browser's flushed completion record; schema-before-policy, denied close,
unknown session and missing journal refusal. Fixture browser processes were
drained; no personal browser profile, existing tab, or public URL was used.

Download status reads the browser's authoritative History database. Chromium
may lock that database while running; in that state the tool reports status as
unavailable and does not infer completion from a file's presence. The native
download fixture closes its own browser gracefully before checking the flushed
record and matching file size. No live-history completion is claimed.

## Verification

- `& output/p11-native-env/Scripts/python.exe output/p11_power_actions/run_checks.py browser-focused-e48-final3`: **12 passed in 18.25s**, exit 0, wall 19.782s. Native Edge/Chrome fixtures and browser schemas/policy/ownership/undo checks; run after the final privacy and download-availability verification changes.
- `& output/p11-native-env/Scripts/python.exe output/p11_power_actions/run_checks.py browser-regression-e48-final`: **204 passed, 1 failed in 69.19s**, exit 1. The one failure was the existing `test_native_launch_is_owned_before_resume_and_survives_only_success[success_then_undo]` private desktop fixture teardown (`SetThreadDesktop` returned WinError 0); browser tests and other regression cases passed.
- `& output/p11-native-env/Scripts/python.exe output/p11_power_actions/run_checks.py browser-launch-flake-focused-e48`: the exact regression failure **1 passed in 2.19s**, exit 0. The same isolated private-desktop teardown has occurred intermittently in prior E47/E48 regression runs; it is recorded, not hidden as a fully green regression.
- `python docs/completion/verify_requirements_matrix.py`: **PASS**, 298 source items / 324 traceable rows, unique IDs and local links.
- `git diff --check`: **PASS** after final code and documentation updates.

## Remaining P11 acceptance gaps

All six missing exact P11 tool names are implemented and registered after E48.
That does not close the P11 acceptance gate. `undo_last` remains DEFECTIVE for
unsupported older/native inverses; the matrix identifies remaining guarded
native inverse work. Ten catalog rows remain UNVERIFIED: physical focus (two),
audio changes (four) and power actions (four). Required A/D/H evidence and
native/admin confirmation integration also remain open. No owner waiver exists.
P11 remains incomplete and P12 must not start.
