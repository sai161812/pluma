# E34: guarded audio mutation and default-device selection

2026-10-22, Asia/Calcutta; source parent `8fc1d02`, branch `ui-wiring`.
P11 remains incomplete; P12 is forbidden. No owner acceptance waiver.

Audio volume/mute/unmute pre-state now captures exact endpoint ID, scalar,
mute state and explicit target before dispatch. The adapter compares captured
state immediately before writing; readback and independent verification require
the same endpoint and coherent requested/unchanged fields. Result receipts
extend the durable intent with actual post-state. Undo requires that exact
post-state still exists; replacement endpoints, changed defaults or newer edits
are refused. The inverse restores the unrounded scalar and reads it back.
Legacy receipts lacking endpoint/before/after evidence are refused before any
setter. Partial effects without a final receipt remain residual, never guessed.

`set_default_audio_device` is a typed MEDIUM ToolSpec requiring exact endpoint_id,
flow (render/capture) and role (console/multimedia/communications). No implicit
all-roles operation or fuzzy name matching. Native Core Audio validates active
endpoint identity/direction, checks captured current default before dispatch,
calls the declared pycaw IPolicyConfig interface and reads the exact default
back. Approval, changed/default target refusal, failed readback and guarded undo
follow the same journal pipeline. Unsupported native interfaces fail closed;
no shell, driver installation or global policy change.

Both automatic audio inverses and recycle inverses run in a closed, bounded,
capsule-owned cleanup worker after executor drain. Manual audio undo uses the
existing isolated undo_last worker and durable at-most-once claim/readback.
Cleanup-worker ownership is retained until native absence is verified.

## Verification and limits

Runner: `output/p11-native-env/Scripts/python.exe output/p11_audio_guards/run_checks.py`
followed by the suite name. Same declared Python 3.12.10 / Windows 11 build
26200 environment; isolated APPDATA/LOCALAPPDATA/TEMP/TMP per invocation.
Adjacent text/JUnit/JSON artifacts record actual exit, command, source parent,
hashes, environment and fixture-key cleanup. Final regression includes the new
guard tests and changed legacy-receipt rejection test in its source hashes.

- `audio-guards-focused-final`: **118 passed in 27.14s**, wall 28.038s.
- `audio-guards-regression-reviewed`: **450 passed / 1 elevation deselected in
  123.39s**, wall 124.313s. Earlier regression before the factual no-op message
  correction: 450 passed / 1 deselected in 126.14s, wall 127.253s.
- `raw-e34`: **15 passed with --runxfail in 0.51s**, wall 1.341s.
- `containment-e34`: **3 passed in 3.26s**, wall 4.174s.
- `recovery-e34`: **5 passed in 0.55s**, wall 1.396s.

Actual pytest exits are zero, final regression/raw/containment/recovery source
hashes match and fixture IPC keys are zero. The focused run preceded only the
factual no-op wording correction. Counts overlap; elevation is not a pass.
Requirements checker: 298 source items / 324 traceable rows PASS; diff check
passes. The matrix checker does not certify runtime behavior.

Tests exercise captured-state changes before mutation, native default direction
and role isolation, missing/inactive/wrong-direction targets, ignored native
setter/readback, denial before capture/execution, schema rejection, newer edit
conflicts, malformed receipts, unrounded-scalar restore, independent verifier
readback, durable manual inverse/consumption and owned automatic inverse drain.

Real Core Audio reads and a current-endpoint selection/undo traverse native
workers, exact approval, SQLite and native default readback. Selecting the
already-current endpoint intentionally does not call SetDefaultEndpoint. Other
default transitions use an isolated in-memory COM-interface fixture; volume
transitions use explicit isolated fixture state. These checks do not establish
a real physical endpoint switch or audible volume/mute change. No physical
audio setting was changed by validation; those four catalog mutation rows stay
UNVERIFIED pending that evidence. Existing READ rows remain implemented.

Catalog after registration: **44 registered / 29 unregistered; 25 IMPLEMENTED /
29 MISSING / 2 DEFECTIVE / 17 UNVERIFIED**. Thirteen missing P11 names remain,
plus native/undo/A/D/H gates; sixteen missing P12 names are untouched. This is
an implementation/guard checkpoint, not a full P11 completion claim.
