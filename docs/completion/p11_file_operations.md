# P11 native file operations (E28)

2026-10-21, Asia/Calcutta. P11 remains incomplete. P12 is forbidden.
Started from pushed ui-wiring `17d17d2`; no branch switch or unrelated edits.
The owner mentioned PLUMA_COMPLETION_GUIDE.md; that file does not exist in this
checkout. PLUMA_COMPLETION_PROMPTS.md contains the established P11 contract.

## Implemented scope

- Registered exact `list_folder`: explicit absolute literal Windows path,
  strict bounded 1-200 immediate entries, native lstat file IDs (Windows
  DirEntry.stat returns zero identity fields), explicit has_more and independent
  bounded re-enumeration. No content read or reparse-target traversal. Directory
  ancestors/identity are held while observing, and failures never become empty
  success. Required owned worker, policy and factual ledger path.
- Registered exact `copy_file`: one regular file to an exact absent destination,
  no overwrite. MEDIUM exact-call confirmation precedes capture. Native
  CopyFileExW preserves alternate streams/attributes and refuses collisions;
  its callback records the native identity of the created output and cooperates
  with cancellation. Parent bindings, source identity/content, output identity,
  size and all bounded data streams are independently read back. Up to 32
  streams / 256 MiB total; a larger/unsupported observation is refused rather
  than omitting streams. Stream names/content stay out of the undo receipt;
  only the combined digest is stored as bytes, consistent with existing file
  fingerprints and redaction. Native change time/attributes detect later edits.
- Upgraded `create_folder`: strict literal absolute path and bool arguments,
  bounded missing ancestor capture, existing anchor identity, required owned
  worker and independent identity readback. Each new directory is exclusively
  created by NtCreateFile(FILE_CREATE), retaining that very returned handle;
  no mkdir/reopen adoption gap. An existing folder is a verified no-op and is
  never deleted by undo. Up to 32 missing ancestors; reparse ancestors refused.
- Native inverse deletes only the captured output identity/content. It refuses
  edited/replaced files (including alternate-stream edits), changed copy parent,
  replaced directories and nonempty created directories. Native handle deletion
  is nonrecursive. Empty created ancestor directories are undone in reverse.
  Partial/incomplete inverse stays unverified, with its durable claim retained.
- Registry accepts post-mutation creation identities only as an extension of
  captured pre-state; a changed or omitted captured field produces unverified
  history and retains the pending mutation instead of publishing a false undo.
  Both automatic rollback and manual undo support these guarded receipts;
  legacy folder records remain refused by manual undo.
- SMART file selection includes copy_file/list_folder, does not lose file tools
  on the word copy, and keeps memory/routine tools when a routine mentions files.

## Verification

All native mutations use isolated owned temporary files/directories and SQLite.
No personal files, user windows/tabs, clipboard, device/power configuration,
model, microphone or security policy was changed. No new dependencies or UI
changes. The isolated runner strips PLUMA environment variables, isolates app
and temp paths, uses the existing 20-second per-test and 240-second suite bounds,
restores its temporary system-awake request and removes fixture IPC keys.
The runner's shell exit is not pytest's outcome; metadata/JUnit are authoritative.

Commands (repository root, native Windows Python 3.12.10 environment):

```powershell
output/p11-native-env/Scripts/python.exe output/p11_file_ops/run_checks.py file-ops-focused-5
output/p11-native-env/Scripts/python.exe output/p11_file_ops/run_checks.py file-ops-regression-reviewed
output/p11-native-env/Scripts/python.exe docs/completion/verify_requirements_matrix.py
```

Focused before final receipt edge case: **24 passed in 13.76s**, actual pytest exit 0,
wall 14.715s. Durable manual copy/folder undo includes real native worker and
ledger readback, existing folder no-op, empty/Unicode/one-MiB copy, owner edits,
replacement/collision, alternate-stream preservation/edit conflict, bounded
listing/change/truncation readback, invalid schema before policy, cancellation
before effects, routine/file schema selection and forged receipt preservation.

Reviewed affected regression: **186 passed in 71.25s**, actual pytest exit 0,
wall 72.053s. Includes all 25 final native file/receipt cases plus existing
file moves, tools/schema selection, registry/ledger, memory/manual undo,
automatic rollback, mutation journal, admission, owned capture/verification,
policy boundary and backend safety integration. The single selected elevation
case is outside this batch; no actual elevation operation is claimed.
Raw backend audit (`--runxfail`): **15 passed in 0.47s**; native containment:
**3 passed in 3.10s**; recovery/lifecycle: **5 passed in 0.58s**. Actual exits zero,
fixture keys zero and every recorded runtime/test hash matches reviewed source.
Traceability check: **298 source items / 324 rows PASS**. Registry/matrix
reconciliation: **36 exact registered / 37 unregistered**, status totals
**18 IMPLEMENTED / 37 MISSING / 2 DEFECTIVE / 16 UNVERIFIED**; sixteen P12
names untouched. Non-P12 missing count is 21.

Review found a changed-receipt plus backup-field edge case: after refusing the
receipt, the legacy backup augmentation could index None. Guarded that path and
added a fourth forged receipt case, preserving the original pre-state and
unverified ledger assertions. The 186-case run uses those final bytes.
The preceding 185-case run passed in 89.44s before this final review fix.

Prior attempts are retained, not counted as passes:

- Focused 1: 17 passed / 2 failed / 2 errors. Windows DirEntry.stat identities
  were zero and contradicted lstat; changed production enumeration to uncached
  lstat. One-MiB parametrized value exceeded PYTEST_CURRENT_TEST's Windows env
  limit; added short test IDs without reducing payload or assertions.
- Focused 2: 20 passed in 7.26s. First affected regression: 181 passed in 90.20s,
  before later stream/atomic-creation/forged-receipt additions.
- Focused 3: 18 passed / 3 failed. Durable stream digests were redacted as hex
  tokens; stored deterministic digest bytes, retaining every original round-trip
  and exact persisted receipt assertion. Redaction rules were not relaxed.
- Focused 4: 21 passed in 10.93s, before final atomic creation/receipt tests.

Baseline E27 broad regression (1159 passes / 3 skips / 1 exclusion) is historical
baseline evidence, not a run of E28 source. The current affected batch is reported
separately, without adding counts or claiming an unrun whole-project suite.

## Limits and remaining work

Bounded new-file copy only; overwrite and directory-copy are not exposed as
supported modes. Cross-volume/network filesystems, readonly-copy inverse and
physical desktop acceptance are not certified by these owned local fixtures.
Paths whose redaction destroys the inverse are refused before mutation. Native
copy cancellation removes a partial output cooperatively; a forced interruption
or failed final receipt can leave an unknown effect. Such outcomes retain the
pending journal and report residual/unverified state; no guessed cleanup.

Missing P11 tools and the remaining legacy/native inverses remain mandatory.
No blanket acceptance waiver, full P11 completion or eligibility for P12 follows
from this batch. Continue P11 only; do not start P12 without owner instruction.

Native API references reviewed:
[CopyFileExW](https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-copyfileexw),
[FILE_DISPOSITION_INFO](https://learn.microsoft.com/en-us/windows/win32/api/winbase/ns-winbase-file_disposition_info),
[FILE_BASIC_INFO](https://learn.microsoft.com/en-us/windows/win32/api/winbase/ns-winbase-file_basic_info),
[NtCreateFile](https://learn.microsoft.com/en-us/windows/win32/api/winternl/nf-winternl-ntcreatefile).
