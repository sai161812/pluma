# P11 folder recycling and interrupted intent recovery (E32)

2026-10-21, Asia/Calcutta. Source parent `f584823` on ui-wiring. P11 only;
P12 and action entry remain untouched. Owner selected Windows Recycle Bin only.

## Changes

- safe_delete supports bounded ordinary folders as well as files on fixed NTFS.
  Snapshot holds inspected tree handles, native IDs and metadata, hashes all
  file streams and relative names in worker memory, and checks directory
  stability. Bounds: 512 entries, depth 32, 256 MiB total file streams.
  Reparse/offline/encrypted/hard-linked files, directory data streams, other
  volumes and Bin targets are refused before dispatch. No permanent deletion.
- Shell updates NTFS change timestamps recursively. Stable content digests
  exclude those timestamps; separate revision digests retain them for exact
  pre-dispatch and current-receipt conflict checks. Native IDs, names, bytes,
  attributes and last-write timestamps remain checked across recycle/restore.
- A pending intent can recover after worker termination without an IPC receipt.
  Original parent identity must match. An unchanged original is a verified
  no-op; occupied/newer original state refuses recovery. Otherwise a bounded
  current-user Bin metadata scan matches the original parent and native
  volume/file ID before reading any candidate content. Exactly one unchanged
  target is required. Missing/changed/ambiguous evidence remains residual.
- Automatic recycle inverses run in a separate bounded capsule-owned worker
  after the original executor drains. Its closed typed inverse phase can
  neither plan nor invoke ordinary tools. Original action admission stays
  latched. Ownership is retained before spawn, Windows Job containment is
  mandatory, timeout drains the owned worker, and failed cleanup retains the
  controller/evidence for retry. No cleanup call kills a personal process.
- Manual pending recovery requires durable terminal and worker/job absence
  evidence for the original task before claiming. It cannot consume intent
  while that executor might still commit. Existing at-most-once claims and
  independent native readback remain required before consumption/success.
- Fixed an observed STOP claim race: action_row_id now enters the initial
  acknowledged journal, rather than first changing undo_json at finalization.
  Claim equality and conflict checks were preserved.

Runtime/tests changed: adapters/recycle_bin.py, tools/files.py,
rollback/{owned,engine,recipes}.py, memory/{activity,undo}.py,
core/task_supervisor.py, app.py, tests/unit/test_recycle_bin_native.py.
No dependency, UI/design, immutable specification or personal-data mutation.

## Checks

```powershell
output/p11-native-env/Scripts/python.exe output/p11_recycle/run_checks.py recycle-focused-recovery-hardened
output/p11-native-env/Scripts/python.exe output/p11_recycle/run_checks.py recycle-regression-recovery-hardened
output/p11-native-env/Scripts/python.exe output/p11_recycle/run_checks.py raw-e32-final
output/p11-native-env/Scripts/python.exe output/p11_recycle/run_checks.py containment-e32-final
output/p11-native-env/Scripts/python.exe output/p11_recycle/run_checks.py recovery-e32-final
output/p11-native-env/Scripts/python.exe docs/completion/verify_requirements_matrix.py
```

- Final focused: **33 passed, 14.32s**, wall 15.336s. Native folder/stream round
  trips, changed child streams, directory-stream/entry bounds, exact pending
  recovery/conflict, owned STOP between recycle and IPC receipt for files and
  folders, inverse timeout, retained failed-cleanup ownership, live-owner manual
  refusal, plus all E31 file/approval/undo/conflict cases.
- Affected regression: **466 passed / 1 elevation deselected, 146.21s**, wall
  147.602s. Actual exit zero; deselection is not a pass or approved exemption.
- Raw backend audit --runxfail: **15 passed, 1.44s**. Native containment:
  **3 passed, 5.64s**. Recovery: **5 passed, 1.41s**. Actual exits zero.
  Matrix: 298 source items / 324 traceable rows, PASS. git diff --check passes.
- Existing 20s per-test and 240s suite limits retained. Windows 11 build 26200,
  Python 3.12.10. Explicit owned temporary fixtures/isolated storage only;
  approval is a callback fixture, not physical confirmation UI certification.
  Exact commands, source/runtime SHA-256s, environment, JUnit and logs are in
  ignored output/p11_recycle. Fixture IPC keys and owned Bin residues are zero.
- Failed initial runs retained: recursive change timestamps contradicted tree
  readback; a test incorrectly treated stop_task's None return as a capsule;
  STOP hit the changing-journal claim race. Corrected native semantics and
  canonical publication; exact STOPPED/recovery assertions were not weakened.
  Two failed folder fixtures were restored by exact owned fixture identity.
  An earlier direct probe restored its own tree but failed its then-overstrict
  timestamp assertion. No user Bin item was restored/deleted or Bin emptied.

Catalog: 41 registered / 32 unregistered; **23 IMPLEMENTED / 32 MISSING /
2 DEFECTIVE / 16 UNVERIFIED**. safe_delete's previously open folder/interrupted
receipt gaps now have native evidence. Sixteen P12 missing names untouched;
16 P11 missing names and remaining inverse/native/A/D/H gates still open.
P11 is incomplete. Continue the remaining P11 tools, never P12 automatically.
