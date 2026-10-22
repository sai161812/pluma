# E36: all-stream move/rename conflicts and owned native inverses

2026-10-22, Asia/Calcutta; source parent `10b39eb`, branch `ui-wiring`.
P11 remains incomplete; P12 forbidden. This is a concrete reproduced repair.

Before editing, four real native cases failed the conflict invariant: move and
rename, each for a regular file or a folder containing a file. Editing an NTFS
alternate stream and restoring the primary file timestamp let the old inverse
move the target back despite the newer content. `moves-before`: **4 failed in
2.24s**, wall 2.800s. The original refusal assertions remain unchanged.

Move/rename snapshots now include bounded all-data-stream digests and file/
directory attributes throughout the tree. Stream names/content are hashed in
worker RAM, not written to the journal. Stream table, size and native revision
are checked during observation. Native rename legitimately updates change time;
stable identity/content is compared across it. Directory data streams are
refused before mutation; reparse/entry/depth/file-size bounds remain enforced.
At most 32 streams and 256 MiB per file, 512 tree entries and depth 32; the owned
tool/capture/verifier deadlines remain binding for total work.

The primary file handle retains its non-shared DELETE guard. A secondary stream
read shares that already-held access so it can inspect the stream; it does not
grant other processes permission to rename/delete the root. Actual native tests
prove that outside rename is still refused. CreateFile errors now preserve the
ctypes cached Windows error rather than misleading WinError 0.

Automatic inverses for guarded move/rename/copy/folder/window-geometry receipts
now join audio/recycle in the closed capsule-owned inverse worker. They are
bounded, registered before spawn and retained until native cleanup readback.
Manual undo remains an isolated worker with durable at-most-once claims. Legacy
receipts without the stronger evidence are preserved and refused, not upgraded
with guessed pre-state. Unknown partial effects still remain factual residuals.

## Evidence

Use `output/p11-native-env/Scripts/python.exe output/p11_move_guards/run_checks.py`
and the suite name. Declared Python 3.12.10, Windows 11 build 26200; isolated
APPDATA/LOCALAPPDATA/TEMP/TMP. Adjacent text/JUnit/JSON preserve exact commands,
actual pytest exits, source parent/hashes, wall times and fixture-key cleanup.

| Suite | Actual result | Wall seconds |
|---|---|---|
| moves-focused-final | 141 passed in 38.92s | 39.496 |
| moves-boundaries | 2 passed in 1.53s | 2.119 |
| moves-regression-final | 463 passed in 92.61s | 93.227 |
| raw-e36 | 15 passed with --runxfail in 0.42s | 1.043 |
| containment-e36 | 3 passed in 2.73s | 3.303 |
| recovery-e36 | 5 passed in 0.43s | 1.038 |

The two boundary tests were added after the 141-test focused run; the final
regression includes them and its hashes match final runtime/test source.
Actual final exits zero; fixture keys zero; matrix 298 source items / 324 rows
PASS; diff check passes. Counts overlap, not a unique combined total. No UAC,
physical audio, model, personal-app or product/release certification is claimed.

The first implementation run retained 139 passes and two refused file-with-
stream moves. An owned native probe identified the secondary sharing failure;
the adapter was fixed rather than weakening the successful-move/conflict
assertions. Native folder/stream, source/parent/identity/collision, stream-size,
directory-stream refusal, inverse ownership/timeout, recycle, window geometry,
audio, command, search, SQLite and executor safety regressions pass.

`rename_file` now has bounded in-place native mutation, independent readback,
usable durable inverse, alternate-stream conflict and owned automatic inverse
evidence. Existing-name conflicts refuse overwrite, as required for safe undo.
`move_file` remains UNVERIFIED for cross-volume transfer semantics; same-volume
guarded evidence is stronger but does not establish cross-volume support.
Catalog: **44 registered / 29 unregistered; 27 IMPLEMENTED / 29 MISSING /
2 DEFECTIVE / 15 UNVERIFIED**. Thirteen missing P11 names and remaining A/D/H,
native/inverse and physical gates remain. The owner power-request semantics
question is pending; no dependent power implementation is invented.
