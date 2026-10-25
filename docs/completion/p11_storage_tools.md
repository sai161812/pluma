# P11 E27: Activity, global STOP, preferences, routines and guarded undo

2026-10-21, Asia/Calcutta. Started at pushed ui-wiring `5f1b1d9` with a clean
checkout. Existing P00-P10 bounded gates/E26 evidence checked before editing.
The owner requested remaining P11 implementation and an explanation of scope.
P12 and later milestones remain unauthorized.

## Implemented behavior

- show_activity reads the executor's actual ledger through a required owned
  worker and read-only SQLite URI. No environment/default-path fallback,
  migrations or swallowed read failure. At most 100 records; 4096-character
  command previews explicitly mark truncation. Returned commands are redacted.
- stop_current validates its typed request, then uses the same priority global
  supervisor service as IPC. It latches all active tasks before cleanup and
  does not wait behind policy/model/tool Futures. Pending/residual receipts never
  imply clean STOP. Actual per-task cleanup/history determines verification.
- save_preference/get_preference are typed, bounded, public local memory tools,
  separate from runtime/security configuration. Secret keys/values are refused.
  Writes require exact-call approval, owned pre-state capture, durable journal,
  compare-and-swap, independent SQLite readback and conflict-checked inverse.
- create_routine stores up to eight validated, non-nested backend ToolCalls.
  Unknown tools/arguments, stored screen references and unsupported route tools
  are refused. Edits preserve identity and capture their prior definition.
- run_routine validates the complete stored sequence again before any effect.
  Every child uses the same TaskCapsule, cancellation tree, current policy,
  verifier and ledger. Failure/denial/STOP prevents later children; a failed macro is fatal to outer
  replanning so a completed prefix cannot be replayed. Completion
  requires matching verified child action rows, not just counters. Expanded
  calls share a hard 20-call task budget and distinct action indices. This does
  not claim to repair P13's separate configured planner-limit wiring gap.
- undo_last now uses a required owned worker and durable at-most-once claims.
  Claim precedes inverse; verified inverse/consumption are independently read
  back. Newer edits survive conflict. Unknown/interrupted claims and pre-state
  remain, preventing automatic replay. Automatic rollback respects the same
  claims. Manual supported inverses cover guarded memory and identity-fingerprinted
  file/folder move/rename records; older ungrounded records and other native
  inverses remain a catalog gap and are
  refused rather than guessed. The undo_last matrix row remains DEFECTIVE.
- Validation errors no longer echo argument values. Missing JSON Schema
  validation fails closed. Private verification receipts cross owned workers
  in memory, excluded from ToolResult JSON/repr and stored action output.

File compatibility: a broad run initially found 827 passes / 1 failure / 1
excluded (176.65s), the original usable file-undo gate. Its success assertions
remain unchanged. The fixture now uses an actual ledger and closes its registry
and database. Move/rename now capture native file IDs, content/tree fingerprints
and parent identities; a Windows handle rename refuses overwrite and replaced
objects. Native file/folder round trips, newer-content/identity/source conflicts
and parent replacement are tested. Fingerprints store byte arrays so secret
redaction cannot erase inverse evidence. Supported mode is same-volume without
overwrite; directory snapshots are bounded to 512 entries/depth 32, each file
256 MiB. Cross-volume/overwrite and private path cases remain explicit gaps.
Move/rename rows therefore remain UNVERIFIED for full catalog acceptance.
file_info now explicitly requires its owned worker, including fail-closed
executor/verifier serialization. Native compatibility: 23 passed in 18.23s;
combined final focused batch: **151 passed in 52.88s**, actual exit zero.

Native rename implementation follows [Microsoft FILE_RENAME_INFO](https://learn.microsoft.com/en-us/windows/win32/api/winbase/ns-winbase-file_rename_info)
and [SetFileInformationByHandle](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-setfileinformationbyhandle).

No unrestricted shell/admin API, UI appearance change, P12 implementation,
physical desktop/device mutation, ML activation or dependency change.

## Verification

Ignored native isolated runner: output/p11_storage/run_checks.py, using
output/p11-native-env/Scripts/python.exe. Same isolated storage, owned processes,
20-second per-test and 240-second suite bounds as E26. Actual pytest exit/log,
JUnit, environment, source hashes and fixture-key count are retained.

Focused iterations: Activity 13 passed; Activity/STOP 66; first memory run
95 passed/15 failed (one receipt assertion and legacy partial-builder signature
compatibility); corrected 110 passed. First undo integration 123 passed/2 failed
(pending-journal claim/readback race and a non-serializable verifier fixture).
Corrected 125 passed; then 127; final boundary **129 passed in 39.65s**, actual
exit zero. The fixture verifier now uses its existing module-level contradiction
function; original journal/snapshot safety assertions are retained. The old
file-undo test now proves unsupported ungrounded pre-state is preserved, while
new native tests prove usable guarded undo and concurrent atomic consumption.
No xfail, skip or weakened native safety assertion hides these failures.

```text
output/p11-native-env/Scripts/python.exe output/p11_storage/run_checks.py storage-batch-final
output/p11-native-env/Scripts/python.exe output/p11_storage/run_checks.py focused-final
output/p11-native-env/Scripts/python.exe output/p11_storage/run_checks.py regression-e27-final
output/p11-native-env/Scripts/python.exe output/p11_storage/run_checks.py routine-final
output/p11-native-env/Scripts/python.exe output/p11_storage/run_checks.py raw-e27-reviewed
output/p11-native-env/Scripts/python.exe output/p11_storage/run_checks.py containment-e27-reviewed
output/p11-native-env/Scripts/python.exe output/p11_storage/run_checks.py recovery-e27-reviewed
output/p11-native-env/Scripts/python.exe docs/completion/verify_requirements_matrix.py
```

Final check outputs:

| Check | Actual result | Runner wall |
|---|---|---|
| storage-batch-final | 151 passed, 52.88s | 54.009s |
| Activity/standalone composition compatibility | 21 passed, 3.40s | 4.489s |
| isolated FAST routing + original native descendant case | 113 passed / 3 skipped, 32.24s | 33.186s |
| broad regression-e27-final (before final macro guard) | 1159 passed / 3 skipped / 1 excluded, 219.60s | 220.742s |
| final routine + multi-step + journal regression | 43 passed, 24.30s | 25.389s |
| raw-e27-reviewed (--runxfail) | 15 passed, 0.56s | 1.442s |
| containment-e27-reviewed | 3 passed, 3.36s | 4.301s |
| recovery-e27-reviewed | 5 passed, 0.55s | 1.432s |
| authenticated Python/C# IPC | 39 passed | 7.486s |

Actual final exits zero, final affected-regression/raw/containment/recovery/IPC
source hashes match, fixture keys zero, all 115 FAST cases carry explicit isolation.
The broad 1159-pass run predates one final production change: failed run_routine
is fatal to outer replanning. Its new regression proves a verified prefix runs
once and is rolled back, with zero planner retries. Only multi_step.py and the
new memory test differ from that broad run. The complete affected memory,
multi-step and journal suites then pass 43 on current source. review.json
records those exact differences; no claim that the broad run used later bytes.
Focused 151 preceded the subsequent compatibility/fixture followups; the named
21/113 checks cover those, and the broad plus final affected regressions cover the
implementation with the source distinction above. Matrix 298 source items / 324 traceable rows PASS. Three non-required
corpus skips and system-changing elevation exclusion are not passes or waivers.

Earlier full regression 1156 passed / 3 failed / 3 skipped / 1 excluded (215.39s):
explicit in-memory query compatibility and real-ledger FAST history fixtures were
corrected with their success assertions retained. Original native descendant
cleanup also failed once with retained ownership; instrumented original-case
replay passed in 0.99s, job members 3 to 0 and original process handle signaled
in about 63ms. A later full run had 1158 passes / one FAST mute-emulation failure
(223.07s). FAST routing's test-only audio is now per-case inert memory alongside
its existing clipboard/window isolation; native audio tests remain independent.
No native cleanup deadline, safety assertion or product audio path was relaxed.
The initial native timing cause was not established; preserve its failed report
for stability follow-up rather than claiming it never happened. Final full
regression and containment pass those original cases without instrumentation.

Ignored review.json consolidates final source hashes/exits/keys/isolation and
catalog.json independently confirms 34 registered exact names and row counts.
IPC command: output/p11-native-env/Scripts/python.exe
output/p11_storage/run_ipc_audit.py. No resident/device/tool action was started
by the IPC fixture. Same Windows 11/Python 3.12.10 native environment as E26.

Migration 0003 adds durable undo claims without replacing old tables/data.
Recovery `5f1b1d9` preserves source; do not run pre-claim undo code against a
claim-bearing database, because older code does not enforce those claims.
Production/user storage was not migrated by these isolated checks.

## Remaining P11

This batch closes four missing catalog entries and two defective entries:
15 bounded IMPLEMENTED / 23 non-P12 MISSING / 2 DEFECTIVE / 17 UNVERIFIED.
Sixteen P12 entries remain missing and untouched. Clipboard, controlled terminal,
browser, file/process/power operations, default audio device and window moves/
resizes still need implementation; legacy native mutation identity/inverses,
ownership, broker and other A/D/H gates remain. No acceptance waiver exists.

The owner authorized continued P11 work, so complete separate coherent P11
batches with focused checks and relevant batch regressions. Do not repeatedly
run an overall audit for every small fix. Do not start P12 automatically.
