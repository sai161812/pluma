# E38: confirmed native system requests and missing-policy refusal

2026-10-22, Asia/Calcutta; source parent `a7e4f7d`, branch `ui-wiring`.
P11 remains incomplete. P12 is forbidden.

The owner selected native sleep/restart/shutdown initiation after exact material
confirmation, without forcing applications closed, with irreversible or uncertain
effects recorded. This resolves commit behavior, not physical acceptance.

Four exact HIGH ToolSpecs (`lock`, `sleep_request`, `restart_request`,
`shutdown_request`) now use strict schemas, material confirmation, bounded owned
workers, durable unavailable undo intents before dispatch, and separate native
readback. Restart/shutdown accept only a 30–300 second delay. No remote-machine,
force-close, arbitrary message, command, elevation or policy-bypass argument.
Risk overrides cannot downgrade HIGH. STOP is rechecked after native preparation
and immediately before initiation. A previously accepted OS effect is never
promised reversed, and no automatic shutdown abort is attempted.

Native APIs load only on demand. Lock readback uses the exact worker session's
WTS lock state. Sleep readback requires increased native last-sleep and matching
wake counters. Restart/shutdown readback requires a new local System/User32 event
1074 containing the exact operation UUID marker, beyond the captured record
baseline. Raw event strings, account names and WTS private fields are discarded.
API return alone cannot establish success. Restart/shutdown history reports
observed initiation, never completed restart/off. Missing readback retains unknown
non-undoable effects. No impossible inverse is offered.

Sleep/restart/shutdown temporarily enable the assigned shutdown privilege on the
owned worker token only and restore/read back its original enabled state before
closing the token. No UAC, administrator request or machine-policy change.
Native sleep uses no hibernation, forced suspend or disabled wake events;
restart/shutdown never force applications closed.

An inert four-case reproduction also exposed a registry policy bypass: HIGH
non-undoable actions could execute when no policy engine was configured. They
now return `POLICY_REQUIRED` before capture or dispatch. The same guard covers
MEDIUM/HIGH/ADMIN/DENY/RESTRICTED and every non-undoable spec. READ/LOW retain
their existing policy-free allowance. No production confirmation is mocked.

## Evidence and limits

Runner: `output/p11-native-env/Scripts/python.exe
output/p11_power_actions/run_checks.py <suite>`. Python 3.12.10, Windows 11
build 26200; isolated APPDATA/LOCALAPPDATA/TEMP/TMP, bounded owned workers,
commands/exits/hashes/JUnit/text/fixture-key cleanup retained in ignored output.

| Suite | Actual result | Wall seconds |
|---|---|---|
| power-focused-final | 154 passed in 47.56s | 48.630 |
| power-regression-final-2 | 477 passed / 1 elevation deselected in 145.68s | 146.653 |
| raw-e38-final | 15 passed with --runxfail in 0.49s | 1.097 |
| containment-e38-final | 3 passed in 3.39s | 4.092 |
| recovery-e38-final | 5 passed in 0.57s | 1.355 |

Final regression includes the corrected fixture approval setup and combined P10
native owned-process/rollback/history/shutdown cases. Actual final exits zero,
source hashes match, fixture keys zero. Focused run precedes those fixture-only
setup edits; final regression covers the final source. Matrix coverage check:
298 source items / 324 rows PASS; diff check PASS. Counts overlap; elevation
exclusion is not a pass, and inert transitions are not physical acceptance.

Text/voice cases use actual registered ToolSpecs, policy confirmations, capsule,
Windows Jobs, reopened SQLite intents and unavailable undo records. Mutation
interfaces are explicitly inert fixtures, labelled as such. Native WTS, sleep
counters and local System event-log probes are read-only. No automated native
lock/sleep/restart/shutdown was performed on the active user session.

Negative cases cover denial before capture, invalid force/remote/delay fields,
missing policy, downgrade refusal, native return without readback, STOP during
privilege preparation, owned blocked-worker interruption/timeouts, and privilege
restoration on success/failure. Native binding tests replace DLL calls and prove
the closed local/no-force flags; they are not physical-operation evidence.

Retained failed runs: initial focused 12 failures / 130 passes exposed a fixture
assuming an unavailable worker database capability. The fixture now receives
its own explicit test database path and still checks persisted intent before
dispatch; production worker capabilities were not broadened. The missing-policy
reproduction failed all four cases before the production guard. Focused second
run had five constructor errors / 146 passes because a generic test ToolSpec
omitted its required verifier; adding the verifier preserves all refusal checks.
The first affected regression was 9 failures / 464 passes / 1 elevation deselected
(139.98s): old HIGH/medium fixtures lacked policy approval. They now use the real
policy engine with confirmation restricted to named owned fixture tools. A second
run was 1 failure / 472 passes / 1 elevation deselected (147.08s): a broad test
fixture policy changed a LOW queue-timeout boundary into a policy-timeout boundary.
Approval setup is now limited to the three HIGH spawn tests, retaining the
original TOOL_TIMEOUT assertion. Initial containment was 2 failures / 1 pass;
its named owned probes now have explicit fixture approval too. No executor,
PID identity, STOP, undo, cleanup or timeout assertion was weakened.

Physical effects remain UNVERIFIED. Sleep's complete capture/execution budget is
300 seconds; a longer suspend or unavailable counters cannot claim verification.
Actual shutdown event timing/marker behavior and app-blocked completion need
controlled physical evidence. A request may remain accepted even if the three
second readback poll fails. No owner-approved acceptance limitation is inferred.

Catalog after registration: **48 registered / 25 unregistered; 30 IMPLEMENTED /
25 MISSING / 2 DEFECTIVE / 16 UNVERIFIED**. Four system rows move from MISSING to
UNVERIFIED, not IMPLEMENTED. Sixteen P12 missing names remain untouched; nine P11
names are missing: open_file, clipboard_get/set, open_terminal and browser five.
App/window mutations, cross-volume move, physical audio/system changes,
clipboard clear/full undo and remaining A/D/H gates remain open.
