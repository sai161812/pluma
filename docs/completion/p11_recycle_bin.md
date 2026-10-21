# P11 native recycle-only files (E31)

2026-10-21, Asia/Calcutta. Source parent: pushed ui-wiring `a654ebd`.
The owner resolved recovery as Windows Recycle Bin only, refusing unrecyclable
targets without a permanent-delete fallback. No P12 authorization or changes.

## Bounded implementation

- Registered `safe_delete` takes one strict literal absolute Windows path.
  Unknown/permanent/bulk arguments, traversal and globs fail before policy.
  HIGH exact-call confirmation precedes owned capture/execution; no shell/admin.
- On-demand native `ITransferSource.RecycleItem`, with a failure/cancellation
  advise sink, returns the exact Bin item. No RemoveItem, global Explorer undo,
  permanent-delete fallback, elevation, overwrite, rename or copy/delete retry.
- Native parent identity and regular-file pre-state are durable before dispatch.
  Shell-bound source is rechecked immediately before dispatch. Independent
  readback requires original path absence, exact current-user same-volume Bin
  receipt, stable native file ID, metadata and every bounded data-stream digest.
  NTFS change time is recorded but necessarily changes across recycle/restore.
  Stream names/content stay outside the journal; result copy is deterministic.
- Receipt additions cannot replace captured pre-state. Guarded manual/automatic
  undo restores only that exact item to the original path and captured parent.
  It refuses newer data/streams, changed parent, occupied destination or missing
  receipt. Native TSF_FAIL_EXIST and refusing overwrite callback also protect a
  destination created after the precheck. Actual readback precedes undo success
  and durable journal consumption. Windows owns Bin retention; recovery is not
  promised once an external actor empties/removes the item.
- Supported now: single-link regular files on ordinary fixed NTFS volumes,
  at most 256 MiB across bounded streams. Reparse/offline/encrypted files,
  existing Bin targets, directories, network/removable/other filesystems and
  mounted-volume aliases are refused. No quarantine or staging path changes
  Windows' original recovery destination.
- Cancellation is checked before binding, native dispatch and in callbacks;
  the 15-second tool budget and existing task-owned Job/worker cover blocked
  native calls. If interrupted after Shell commit but before receipt finalizes,
  the durable pending intent remains uncertain. It does not guess a Bin item,
  offer an unsupported inverse or claim clean STOP. This pending-recovery gap
  and broader target coverage remain open; no crash-window/atomic namespace
  exclusion certification or full A/D/H acceptance is inferred.

Changed runtime/tests: adapters/recycle_bin.py, tools/files.py,
brain/tool_subset.py, memory/undo.py, rollback/recipes.py,
tests/unit/test_recycle_bin_native.py. Handoff, decision, matrix and current
audit checkpoints also updated. Immutable master, UI/action entry, dependencies,
personal files, clipboard, devices, power and P12 remain untouched.

## Verification and provenance

```powershell
output/p11-native-env/Scripts/python.exe output/p11_recycle/run_checks.py recycle-focused-final
output/p11-native-env/Scripts/python.exe output/p11_recycle/run_checks.py recycle-regression-final
output/p11-native-env/Scripts/python.exe output/p11_recycle/run_checks.py raw-e31-final
output/p11-native-env/Scripts/python.exe output/p11_recycle/run_checks.py containment-e31-final
output/p11-native-env/Scripts/python.exe output/p11_recycle/run_checks.py recovery-e31-final
output/p11-native-env/Scripts/python.exe docs/completion/verify_requirements_matrix.py
```

- Final focused: **22 passed in 7.43s**, wall 8.478s. Native empty/text/Unicode
  and alternate-stream round trips, real owned worker and SQLite manual undo,
  policy denial, strict schema, source replacement/edit, locked source,
  cancellation, unsupported volume/targets, changed Bin item/parent, destination
  conflicts including after precheck, forged success, failed independent proof
  retaining pending intent, automatic inverse and file-subset selection.
- Affected regression: **343 passed / 1 deselected in 118.25s**, wall 119.322s,
  including all 22 final recycle cases and affected native files/undo, journal,
  policy/admission, owned pre-state/verification, shutdown, outcomes and cleanup.
  The excluded elevation test is not a pass or waiver.
- Raw backend audit `--runxfail`: **15 passed (0.53s)**; native containment:
  **3 passed (3.67s)**; recovery: **5 passed (0.56s)**. Actual pytest exits zero,
  isolated fixture IPC keys zero, recorded runtime/test hashes match final code.
  Matrix check: **298 source items / 324 traceable rows, PASS**. git diff --check
  passes. Counts overlap; do not sum them or apply earlier evidence to new code.
  Exact commands/environment/isolated roots/JUnit/logs and runtime/test SHA-256s
  are under ignored output/p11_recycle. No owned fixture Bin residues remain.
- Windows 11 build 26200, Python 3.12.10; existing declared pywin32/comtypes.
  Owned temporary filesystem fixtures only. Approval is an exact callback
  fixture, not physical UI certification. Per-test 20s / suite 240s unchanged.
- Initial focused: 10 passed / 8 failed. A PyHANDLE context-manager error after
  native recycle and incorrect test selector were fixed, without weakening
  success/undo assertions. Eight precisely identified owned Bin residues
  (including the earlier probe) were restored with native readback. Subsequent
  focused runs passed; failed logs are retained. Never empty the user's Bin.

Catalog: **41 registered / 32 unregistered; 22 IMPLEMENTED / 32 MISSING /
2 DEFECTIVE / 17 UNVERIFIED**. safe_delete moves MISSING to UNVERIFIED because
only the bounded regular-file path is proven; limitations are not waived.
Sixteen untouched P12 missing names; **16 P11 names remain missing**, plus
partial safe_delete, legacy inverse/native and A/D/H gates. P11 is incomplete.
Next safe work is P11 safe_delete target/partial-outcome recovery coverage;
do not start P12 or enable action entry.

Primary native contracts reviewed:
[RecycleItem](https://learn.microsoft.com/en-us/windows/win32/api/shobjidl_core/nf-shobjidl_core-itransfersource-recycleitem),
[MoveItem](https://learn.microsoft.com/en-us/windows/win32/api/shobjidl_core/nf-shobjidl_core-itransfersource-moveitem),
[Advise](https://learn.microsoft.com/en-us/windows/win32/api/shobjidl_core/nf-shobjidl_core-itransfersource-advise),
[transfer flags](https://learn.microsoft.com/en-us/windows/win32/api/shobjidl_core/ne-shobjidl_core-_transfer_source_flags).
