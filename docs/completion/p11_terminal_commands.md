# E33: closed diagnostics and confirmed project commands

2026-10-22, Asia/Calcutta. Source parent `0f2fd87`, branch `ui-wiring`.
This closes two bounded catalog entries, not P11. P12 remains forbidden.

## Behavior and boundaries

`run_command` accepts only hostname, identity and network diagnostic IDs.
`run_powershell` accepts only os_version and process_count IDs. Executables are
resolved from the native Windows directory; PowerShell runs without profiles,
interactivity or execution-policy bypass. Raw planner command/script/argv fields
are rejected by strict schemas before policy. Both operations are READ.

The additional typed `run_project_command` accepts only project_id/command_id.
It implements the owner's configured-command choice; it is outside the exact
73-name catalog. The executor selects `%APPDATA%\Pluma\commands.json`, not a
planner path or an untrusted repository file. The catalog must be current-user
owned and writable only by that user, SYSTEM or Administrators. No catalog is
created automatically and no machine-wide ACL or execution policy is changed.

The strict JSON schema is version 1, projects keyed by ID, each with an absolute
local root and commands keyed by ID. Each command has a fixed argv (absolute
`.exe` first), timeout_s (1–15, default 8), inputs (at most eight literal files
inside the root), and encoding (`utf-8` default or `oem`). There is no parameter
substitution. Configuration is trusted owner code, never planner permission.
Secret-bearing definitions/switches, elevation and policy-bypass requests are
refused. Configuration is bounded to 64 KiB and paths reject reparse traversal.

Every configured execution requires HIGH exact material confirmation showing
the executable, arguments and working directory. Protected material arguments
are evaluated by normal policy; LOW overrides cannot downgrade this operation.
The approved definition, catalog, executable, declared inputs and directory
identity are rechecked before dispatch and held against replacement during
execution. Undeclared inputs/external effects of trusted owner code cannot be
predicted or rolled back; the confirmation explicitly states this limitation.

Native CreateProcess starts suspended with no visible window. PID/creation time
and task ownership are registered, and Job containment is established before
resume. Anonymous byte pipes are drained without detached helper threads.
Execution waits for native root exit, both pipe EOFs and zero Job members.
Output is capped at 64 KiB combined; deadlines, nonzero exit, invalid encoding,
output overflow, STOP and failed cleanup cannot return verified success.
Independent verification checks native exit receipt, output digest and exact
process absence. No unrestricted shell or administrator API is exposed.

Raw stdout/stderr is transient and redacted from history/model prompts under
command_output. The durable non-undoable intent contains only IDs and a
definition digest; approved argv/code and command output are not copied into
the undo journal. Unknown interrupted effects remain factual residuals; no
impossible undo is offered. Registry promotion now requires a retained exact
live process handle already inside the original task Job; task-lifetime command
processes need no promotion. The previous raw taskkill-on-adoption-failure path
is removed. This does not certify legacy app lifetime/undo behavior.

## Checks and reproducibility

Declared project-local Windows environment: `output/p11-native-env/Scripts/python.exe`,
Python 3.12.10, Windows 11 build 26200. Runner
`output/p11_commands/run_checks.py` strips PLUMA environment overrides and gives
each suite isolated APPDATA/LOCALAPPDATA/TEMP/TMP. Tests use real native Jobs,
owned command children, SQLite and exact-call confirmation fixtures. No personal
apps, clipboard/audio/power settings or browser profile were changed.

Run with that interpreter and runner, followed by the named argument:

| Argument | Actual pytest result | Wall seconds |
|---|---|---|
| commands-focused-verified | 49 passed in 33.19s | 34.413 |
| commands-regression-verified | 405 passed, 1 elevation deselected in 158.04s | 159.422 |
| raw-final | 15 passed with --runxfail in 0.85s | 1.697 |
| containment-final | 3 passed in 3.18s | 4.123 |
| recovery-final | 5 passed in 0.64s | 1.528 |

Adjacent `.txt`, `.xml` and `.json` record output, actual exit, exact command,
source parent, source hashes, environment and isolated root. Actual exits are
zero; source hashes and zero remaining fixture IPC keys are checked before
commit. Counts overlap and are not a combined unique-test total. The elevation
exclusion is not a pass or an approved waiver. Matrix validation checks source
coverage, not product correctness.

Checks cover native diagnostics, exact approval/denial, missing/private/shared
configuration, configuration/input changes after approval, secret and elevation
refusal, protected roots, schema rejection, nonzero exit, timeout, output bound,
invalid encoding, STOP of an owned descendant, no late effect, private action
and undo-row redaction, forged proof rejection, and exact/foreign/reused-process
adoption refusal. Existing safety and recycle/window regressions remain intact.

Earlier failed runs are retained in output. Initial failures identified native
CreateFile argument handling, missing internal approval binding, dead-process
promotion and delayed Job accounting. A later regression had 384 passes and
two readiness JSON races in the shared process fixture. The fixture now publishes
readiness by atomic same-directory replacement; original ownership/readback
assertions are unchanged. The final affected regression includes geometry tests
because they share that fixture. No failed case was silently deselected.

## Remaining gate

Catalog: 43 registered / 30 unregistered; 25 IMPLEMENTED / 30 MISSING /
2 DEFECTIVE / 16 UNVERIFIED. Sixteen missing P12 names are untouched; fourteen
P11 names remain missing: open_file, set_default_audio_device, four system
actions, clipboard_get/set, open_terminal and five browser operations. Legacy
native/conflict inverses, clipboard_clear, full undo_last and A/D/H acceptance
also remain open. No device, model, UI, performance or release certification is
claimed. Continue P11 only, with its next bounded native tool/undo gap.
