# E43: native cross-volume regular-file move and guarded inverse

2026-10-22, Asia/Calcutta; source parent `b90b71b`, branch `ui-wiring`.
P11 remains incomplete; P12 is forbidden.

move_file now detects distinct native volumes during pre-state capture. For a
regular file it composes the existing bounded CopyFileEx and Recycle Bin adapters:
the exact created destination, primary and alternate-stream bytes and unchanged
source are verified before recycling the original. The source is never permanently
deleted. Same-volume regular-file/folder movement retains its existing adapter.
Cross-volume folders and unsupported recycle targets refuse before copying.
Existing file-size, filesystem, identity, reparse, parent and overwrite bounds apply.

The durable pre-state is immutable. Successful copy and recycle receipts are added
under separate fields, then independently read back. Undo preflights both paths,
parents and the exact Bin item before restoring the original and deleting only
the exact unchanged PLUMA-created copy. Newer primary/alternate content or an
occupied original path is preserved. A later inverse race leaves copies and a
factual residual rather than risking source loss. Interrupted effects without a
creation receipt retain uncertain intent; no filename-only deletion is attempted.

Native checks exposed the same secondary-stream sharing defect previously repaired
for moves in E36: copy inverse fingerprinting held DELETE on the primary file while
its alternate-stream reader did not share DELETE. Its secondary reader now uses
the established sharing rule; the primary guard continues to deny outside deletion.
This also repairs existing copy_file undo for files with alternate streams.

## Verification

`output/p11-native-env/Scripts/python.exe
output/p11_power_actions/run_checks.py cross-move-focused-e43-streamfix`:
**8 passed in 11.18s**, 12.011s runner wall.

Final `cross-move-regression-e43`: **151 passed in 92.58s**, 93.466s wall,
including all **10** final cross-volume/stream-guard tests and existing native
same-volume moves, file copy, recycle recovery, manual undo, rollback, journal,
policy and file tool checks. Actual exit zero, fixture keys zero; final reviewed
runtime/test hashes match. Metadata/raw/JUnit are local ignored output artifacts.
Matrix coverage and staged whitespace checks pass before commit.

Positive native evidence uses distinct actual C: and D: volumes, empty/Unicode
files with alternate streams, durable exact receipts, manual undo and actual STOP
owned inverse/cleanup. Conflicts, changed source, occupied destination, cancellation
before copy and the original delete guard have native negative evidence. Test paths
are exact owned temporary files and UUID workspace output directories; no recursive
delete or personal source is used. Every recycled fixture original is restored.

Retained failures: initial four positives correctly failed the registry's immutable
undo-prestate check because nested capture fields were replaced. Receipts now add
fields instead; the guard was preserved. The four exact fixture originals from
that run were recovered using their durable recycle identity/parent proofs, not
Bin-wide undo. Four subsequent inverse failures exposed the alternate-stream
sharing defect described above. Original success, ownership and conflict assertions
remain intact and pass after the repair.

Catalog **50 registered / 23 unregistered; 37 IMPLEMENTED / 23 MISSING /
1 DEFECTIVE / 12 UNVERIFIED**. move_file is implemented within its documented
bounds. Seven P11 names still missing: open_file, open_terminal and browser five.
App lifecycle/focus, physical audio/system effects, full undo_last and remaining
A/D/H gates remain open. Continue remaining P11; no P12 eligibility is claimed.
