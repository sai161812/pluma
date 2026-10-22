# E35: bounded native file search candidates

2026-10-22, Asia/Calcutta; source parent `b524b04`, branch `ui-wiring`.
P11 remains incomplete and P12 is forbidden.

`find_file` now requires an explicit absolute root and strict typed arguments
before policy. A basename glob is case-insensitive; path/stream patterns and
implicit current-directory searches are refused. Optional file/directory kind
and creation/modification epoch-nanosecond ranges support candidate filtering.
Time ranges use an inclusive lower bound and exclusive upper bound; no relative
date, timezone or natural-language interpretation is hidden inside execution.

Enumeration runs in a required owned process, bounded to requested depth 0–10,
1–200 results and 1–4096 examined entries. Native directory handles bind the
root/ancestors/traversed directories; candidate handles read volume/file ID,
kind, size and modification metadata. Creation/modification timestamps are
read while the candidate is held. No file contents are read. Changed directory
or candidate identity, missing root, access failure and reparse traversal fail
closed, without substituting a successful empty search.

The independent verifier repeats the bounded native inspection and compares
candidate data and captured directory identities. Cancellation is checked
before opening the root, in traversal and in final directory readback; blocked
workers remain STOP/timeout-owned. A limited result explicitly says it stopped
at a limit. `unambiguous` is true only for one candidate after completion within
the requested depth. Duplicate candidates remain distinct; this tool never
selects or opens/moves one automatically. Actual model semantic selection and
the complete master §26.3 multi-tool story remain separate open gates.

## Verification

Use `output/p11-native-env/Scripts/python.exe output/p11_search/run_checks.py`
with the suite name. Declared project-local Python 3.12.10, Windows 11 build
26200; unique isolated APPDATA/LOCALAPPDATA/TEMP/TMP. Adjacent text/JUnit/JSON
record exact commands, actual pytest exit, source parent/hash, environment,
wall time and fixture-key cleanup. No personal files or settings are touched.

- `search-focused-reviewed`: **82 passed in 20.74s**, wall 21.679s.
- `search-regression-final`: **424 passed / 1 elevation deselected in 72.63s**,
  wall 73.304s. The elevation exclusion is not a pass or an approved waiver.
- `raw-e35`: **15 passed with --runxfail in 0.40s**, wall 1.014s.
- `containment-e35`: **3 passed in 2.79s**, wall 3.374s.
- `recovery-e35`: **5 passed in 0.45s**, wall 1.062s.

Actual exits zero, runtime/test hashes match and fixture IPC keys are zero.
Matrix validation passes 298 source items / 324 rows; diff check passes. Counts
overlap, and the matrix checker validates traceability rather than behavior.

Evidence covers text/voice owned native pipelines with real SQLite and distinct
same-name PDF candidates; case/type/time filters; depth/entry/result limits;
no-match state; invalid/denied calls before execution; replaced root/candidate,
new matches and forged proof/data; real owned junction refusal; pre-cancelled
inspection; actual blocked-worker STOP/timeout drain; and schema visibility.
The first focused run had 77 passes and one test API argument error. It is
retained; correcting the command keyword preserved the schema assertion.

Catalog after this bounded READ row: **44 registered / 29 unregistered;
26 IMPLEMENTED / 29 MISSING / 2 DEFECTIVE / 16 UNVERIFIED**. Thirteen missing
P11 names and remaining native/inverse/A/D/H acceptance stay open; sixteen P12
missing names remain untouched. No product, planner, physical or release
certification is inferred from these fixture results.
