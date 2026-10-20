# P11 process inspection checkpoint (E19)

2026-10-20. P11 remains authorized and in progress. P12 is explicitly forbidden.
This block implements three required READ tools, not process control or full P11.
Starting source: `0e64caa03eaf03f74952722a2341566a63a69506` on local/remote
ui-wiring. Main/integration/four worktrees remain preserved. PRs 1/2 were queried
through the GitHub connector: both draft, open and unmerged. The gh executable
is unavailable; it was not used as evidence of PR state.

## Contract and implementation

- `list_processes(max_entries=100)` accepts a strict integer from 1 to 500,
  returns bounded PID/native FILETIME/name observations, enumeration timestamp,
  actual observed PID count and explicit truncation. Per-entry access denial,
  exit/identity change and unavailable reads are facts, with null identity/name;
  they are never invented names or zero usage. Enumeration is an observation,
  not an atomic promise that all processes are still alive after return.
- `process_info(pid, creation_time)` requires both exact positive identifiers;
  returns name/status/parent PID/thread count. `process_usage` requires the same
  identity and samples CPU for 0.05 seconds, returning actual sample duration
  and resident memory bytes. CPU may exceed 100% on multiple logical processors.
  No command lines, environment, executable paths or file contents are collected.
- The native adapter retains the original process handle across PID-based
  psutil queries. Creation time and original-handle liveness are checked before
  and after. An exited original cannot be validated by a replacement PID.
  Every opened native handle closes in finally, including denied/failed reads.
- Registered ToolSpecs are READ, native API only, five-second required owned
  process isolation. Internal `process_isolated` metadata is not a planner
  argument or exported planner field. Serialization failure refuses before
  execution and records executed=false; it cannot silently run in a thread.
  Native/psutil adapter imports occur on demand in the owned worker.
- Strict output models reject incoherent available/unavailable entries,
  duplicate PIDs, false truncation, unknown fields, invalid identity and NaN.
  The verifier requires the native observation proof and valid result schema;
  it performs no unbounded native read on the resident thread.
- Schema precedes policy and worker creation. Calls share the existing capsule,
  cancellation latch, owned worker/Job, verification, factual redacted action
  and shutdown paths. SMART/DEEP expose the tools; FAST has no model schemas
  and SCREEN retains its own subset. No state change, resource promotion or
  undo record is produced by these tools. Process-control tools remain missing.

## Verification

Ignored evidence runner: `output/p11_process/run_checks.py`, adapted from the
prior isolated runner. It strips PLUMA_* overrides, allocates separate local/
roaming/temp roots, uses bounded pytest/subprocess deadlines, saves log/JUnit/
JSON, source hashes and actual pytest exit codes, then removes only fixture key
files within its verified isolated root. Runtime/test source stayed fixed while
pytest was running. Native interpreter: ignored `output/p11-native-env`, with
declared Windows bindings installed only there; no security policy was changed.

Commands use `output/p11-native-env/Scripts/python.exe`:

```text
output/p11_remaining/run_checks.py prerequisite-native-before-inspection
output/p11_process/run_checks.py process-tools-first
output/p11_process/run_checks.py focused-final
output/p11_process/run_checks.py regression-isolated
output/p11_process/run_checks.py raw-final
output/p11_process/run_checks.py containment
output/p11_process/run_checks.py recovery
docs/completion/verify_requirements_matrix.py
git diff --check
```

Before edits, P01-P10/file metadata prerequisites: **368 passed in 49.25s**.
New process checks: **57 passed in 21.06s**. Focused regression: **560 passed,
1 excluded elevation operation in 79.64s**. **878 passed / 3 skipped / 1 excluded in 89.02s** in the isolated regression.
Raw --runxfail audit: **15 passed in 0.43s**; native containment: **3 passed
in 3.24s**; recovery: **5 passed in 0.66s**. An exclusion/skip is not a pass.
All final source hashes match their reports, actual pytest exits are zero and
fixture key counts are zero. All 115 FAST cases retain isolation properties.
Environment: Windows 11 10.0.26200, Python 3.12.10 x64.

Native checks run registered tools through real Windows spawned workers/Jobs
with matching task/PID/creation identity, real SQLite action readback, verified
worker absence, storage-last shutdown and reopened history. Text and voice
requests use the same path; voice capture/STT/planner are inert fixture seams.
The inspected stable process is pytest itself; it remains alive after inspection
and cleanup. Absent PID and mismatched creation-time targets fail without data.

Injected checks cover denied native access, unavailable API, private exception
copy, original-handle exit during observation, partial enumeration, unpicklable
executor refusal and malformed proof/data. They do not certify actual protected
process access denial or force an OS PID reuse. Blocked owned executors use the
same prewarmed worker with unchanged one-second response deadline; STOP/deadline
leaves no late marker, preserves first cancellation cause and persists matching
task/history/cleanup. No user process, audio, browser or clipboard is changed.

## Remaining work and recovery

Only CAT-list_processes, CAT-process_info and CAT-process_usage move from MISSING
to bounded IMPLEMENTED. Catalog totals: 4 IMPLEMENTED, 46 MISSING, 4 DEFECTIVE,
19 UNVERIFIED. All 73 requirements remain present. P11's full A/D/H and catalog
gate remains open. Mutation journaling/partial effects and conflict-safe inverse,
process control, other catalog tools and permitted native/device evidence remain.

The next safe work is another bounded P11 gap under the existing authorization.
Do not start P12, enable action entry, merge or waive requirements. Recovery:
`0e64caa03eaf03f74952722a2341566a63a69506` in a separate detached worktree.
Commit/push only ui-wiring; keep the other worktrees, archive, stash and tags.
