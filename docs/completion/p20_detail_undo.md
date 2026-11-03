# E96: P20 detail, selected undo, conflict and Activity entry acceptance

Date: 2026-11-02. Branch: `p12-preparation`.
Recovery: `124200ab471f09f2a29541903f64426f21772656` (E95).
Implementation commits: `9097bcf`, `a59c0cd`, `9c959d9`, `d223a32`.
Final native tested source: `d223a32674a7d825725f0ec813da31ce328fda62`.

**P20's scoped implementation and acceptance gate is complete.** E95 and E96
together cover all P20 packets. There are no remaining P20 implementation packets.
No P21, merge, branch change, reset or force-push is authorized or performed.

## Scope and prerequisites

The checkout was clean at E95. The unchanged complete master read earlier in
this conversation was reused; blob `01b693dbf898b662aa4cd67736c1a0e8a21cf3e3`
was refreshed. AGENTS, the shared/P20 prompt, current handoff/matrix, master
sections 13-17, build phases 5/14, corresponding acceptance and existing
undo/rollback, IPC, native controls and owner decisions were reviewed.

The pre-edit affected prerequisites passed **120 checks in 20.27 s**:

```powershell
output/p14-native-env/Scripts/python.exe -m pytest -q tests/unit/test_p20_history.py tests/unit/test_manual_undo.py tests/unit/test_rollback_engine.py tests/unit/test_p18_action_details.py tests/unit/test_p15_remaining_contracts.py tests/unit/test_stop_protocol.py -p tests.fixtures.desktop_isolation
```

E95's browsing/search/paging/restart gate is retained and regressed. P00-P19
evidence keeps its recorded boundaries. The owner's P19 C-02 physical timing
retest deferral to P25 remains unchanged; no new microphone/model evidence is
claimed. Broad taskbar/DPI/accessibility, security, performance and release
gates retain their later milestones.

## Implementation

- `history_detail.py`, strict shared selection/IPC models, resident handlers and
  matching C# contracts add scoped ten-action replacement pages. A bounded
  read-only snapshot supplies original input/context where available, sanitized
  arguments, tool/step, adapter, risk/decision, timestamps/duration, executor
  message/error/policy reason, verification method/detail, captured inverse
  reference, claim/rollback state and result code, cleanup and residual codes.
  Existing task rows retain route/input mode/timestamps/state. Missing legacy
  evidence remains unavailable. No current desktop observation fills history.
- The native History page/controller binds those facts and preserves raw DTO
  identities separately from local time and human-readable labels. Pages replace
  prior pages, failed reads clear stale evidence, navigation shares shell-owned
  state, and close cancels/joins readers. No visual palette/type/spacing redesign.
- `undo_submit` admits one exact saved selection through the existing submission
  fence/deduplication, TaskCapsule, orchestrator FAST lifecycle and registered
  `undo_last` ToolSpec. Natural language does not select an inverse. The registry
  validates the schema and saved material before policy; exact confirmation uses
  the captured effect. A changed revision/material/owner, active or unclean
  original task, outstanding claim, unsafe legacy inverse or later available
  action refuses. Selection proceeds newest-first within the selected task.
- The existing inverse captures/identity guards and native postconditions remain.
  A SQLite `BEGIN IMMEDIATE` claim revalidates the selection; only its exact
  operation may finish it. Verified consumption is atomic. Duplicate requests,
  clicks and concurrent workers cannot apply it twice. Unverified/interrupted
  claims retain their original pre-state and never repeat automatically.
- Selected inverses additionally journal their reference before worker entry.
  They have no automatic inverse-of-the-inverse. STOP/timeout after a claim keeps
  an uncertain non-undoable intent and residual state while proving owned worker
  absence. No claim or postcondition is fabricated when the worker is interrupted.
  Automatic rollback still walks its reversible records in reverse order.
- Surface 9 also follows actual selected-undo worker execution/readback phases;
  it remains indeterminate until saved verification. Surface 10 binds recorded
  conflict/uncertainty data, supports viewing retained evidence and opening its
  recorded folder, and offers no overwrite, forced retry or guessed restoration.
- `history_folder_submit` derives a folder from an exact saved file conflict or
  unresolved claim. The registered `open_folder` utility uses a bounded owned
  worker and Windows Shell location/visibility readback. Its durable intent is
  non-undoable because a Shell view may reuse an externally owned service/window;
  STOP never terminates Explorer or promises to close a pre-existing view.
- One shell-owned native tray entry/menu reaches Activity. Verified registered
  `show_activity` events open the same page for text/voice command paths; initial
  historical snapshots do not replay navigation. Entry deduplication is bounded.
  Tray/subclass/menu resources are released by their owning shell.
- Legacy clipboard command values are hidden using actual saved tool identity,
  before search or display. Original private voice input/window context,
  clipboard arguments and verifier/executor bodies are withheld or canonically
  redacted. Raw inverse recipes, private volatile values and worker handles do
  not cross the new UI contract. Oversized/corrupt evidence fails closed.

## Reproduced prerequisite repairs and failed attempts

E95's retained P18 observation was reproduced locally and in Windows run
[41461071869](https://github.com/sai161812/pluma/actions/runs/41461071869).
The stack was waiting for the first executing tool, after Run, rather than
waiting for initial health. Diagnostics showed successful health but a refused
first command/capability probe. Four ordinary observers could exhaust all four
normal client slots. Initial sequencing alone did not fix that capacity race.

The shell now drains initial health first and limits all four background readers
to three ordinary slots, retaining the fourth for foreground work. STOP retains
its separate fifth slot. Mutation decisions use foreground admission. Bounded
Busy-only read retries preserve admitted command observation and approval leases;
only proven unwritten Busy decisions retry. Unknown acknowledgements never
replay. New controlled pressure checks failed before repair and pass afterward.
The unchanged individual native deadlines/assertions remain. A five-cycle native
whole-shell diagnostic passed **110 checks**, including actual owned-process
STOP/absence, rollback, reconnect and shutdown.

History fixture expansion initially shadowed its outer `uuid4`/`TaskRecord`
imports. Run [41467469263](https://github.com/sai161812/pluma/actions/runs/41467469263)
caught that fixture error after the shared shell/voice checks passed. The imports
are corrected. Navigation acceptance now waits for the actual intermediate
dashboard before returning, adding a positive loaded-page check rather than
issuing two transitions without allowing WinUI to load the first page.

Run [41470608572](https://github.com/sai161812/pluma/actions/runs/41470608572)
passed through native history and selected undo/denial/STOP/conflict, then failed
folder setup because the lightweight CI installation lacked `pythoncom`.
The workflow now installs the already-declared `.[windows]` provider extra;
`pyproject.toml` and production dependencies are unchanged. The final run below
executes the real folder checks; this failed setup is not counted as acceptance.

The first new STOP oracle incorrectly treated `completion_verified` as successful
execution. Its existing contract describes terminal finalization; final state,
persistence, action verification, claims and independent file postconditions
establish what occurred. The corrected test requires saved STOP/residual state,
unconsumed evidence and unchanged owned files. No existing product assertion or
native timing tolerance was relaxed.

A standalone policy-first collection reproduced a pre-existing eager package
import cycle. Lazy core exports preserve the same public names and remove the
cycle; the previously failing standalone selection now passes **36 checks**.
No test is deselected or hidden by import ordering. Failed logs are retained.

Local native P20 acceptance passed **24 checks**, including actual confirmation,
owned-file inverse/atomic consumption, denial, STOP, retained conflicts, Activity
entry and joined shutdown. Local personal-desktop folder opening was explicitly
unexecuted and is not counted as native folder acceptance. That separate check
requires the disposable Windows CI host and closes only its newly observed owned
folder window. Tray callback tests establish the functional contract; physical
pointer/taskbar/DPI/accessibility acceptance remains P25.

## Commands, source identity and evidence boundaries

Ignored reports are under the directory named in
`output/p20-completion-current.txt`; APPDATA/LOCALAPPDATA/PLUMA_CONFIG were isolated.
No personal file, clipboard, browser profile, microphone or power state was used.
Native test windows and files are fixture-owned. No Windows security setting was
changed or bypassed. Current normal Debug native launches executed successfully;
an old report from the other build path was detected and excluded.
After a later rebuild, Application Control blocked the new local executable.
Two copies of its unchanged previous report are also excluded. Their launch
logs establish nonexecution; final native acceptance comes from authorized CI.

Final affected Python command:

```powershell
output/p14-native-env/Scripts/python.exe -m pytest -q tests/unit/test_policy_engine.py tests/unit/test_policy_boundary.py tests/unit/test_p20_detail_undo.py tests/unit/test_p20_history.py tests/unit/test_manual_undo.py tests/unit/test_rollback_engine.py tests/unit/test_p18_action_details.py tests/unit/test_p15_remaining_contracts.py tests/unit/test_stop_protocol.py tests/unit/test_router.py tests/unit/test_fast_orchestrator.py tests/unit/test_multi_step_orchestrator.py tests/unit/test_voice_orchestrator_integration.py tests/unit/test_memory_tools.py tests/unit/test_p18_runtime.py tests/unit/test_runtime_shutdown.py tests/unit/test_tools_system.py tests/unit/test_worker_cancellation.py tests/unit/test_worker_disposal_cause.py -p tests.fixtures.desktop_isolation
```

Native commands:

```powershell
dotnet run --project PLUMA.UI/CoreIpc.Tests/CoreIpc.Tests.csproj --verbosity quiet -p:UseSharedCompilation=false
dotnet build PLUMA.UI/SurfaceControls.Tests/SurfaceControls.Tests.csproj --verbosity quiet -p:UseSharedCompilation=false
dotnet run --no-build --project PLUMA.UI/SurfaceControls.Tests/SurfaceControls.Tests.csproj --verbosity quiet -- --p20-undo
dotnet run --no-build --project PLUMA.UI/SurfaceControls.Tests/SurfaceControls.Tests.csproj --verbosity quiet -- --p18-startup
./PLUMA.UI/verify-ui.ps1
```

Fixture policy/query/PCM checks are not native model or device acceptance. The
new inverse acceptance performs actual registered owned-file operations, exact
native material decisions, independent filesystem/SQLite readback and owned
closure. The unresponsive claim fixture tests real claim/intent/STOP/timeout/
worker containment, not a successful filesystem inverse. Skips, xfails, empty
logs and process exits alone are not acceptance passes.

### Final results and identities

- **631 passed in 107.07 s**, no skips/xfails, on `9c959d9` for the final Python
  command above (`final-exact-source.log`). `d223a32` only changes CI provider
  installation; Python source/tests are unchanged. The independent policy-first
  order is used, without bootstrap ordering or exclusions.
- Exact-source [Windows gate 41472068637](https://github.com/sai161812/pluma/actions/runs/41472068637)
  passes **285 IPC / 214 native UI / 663 native popup / 195 formatting** checks,
  **64,537 layout / 30 surface** checks, audio visualization and copy gates.
  Builds have zero warnings/errors. All 214 native checks execute, including
  actual Shell folder visibility, saved verifier readback and closure of only
  the newly observed owned folder window. No unexecuted-folder line appears.
- Artifact `13157125079`, verified ZIP SHA-256:
  `dd46378cf37519ef3e36bcb4be3f5dbbd717271f242c43a758e66123897e7b2c`.
  Reports/renders are in `ci-final/20261102-153106-5248defb` under the ignored
  evidence root. Preview executable SHA-256:
  `37DEFA43AF428C54DB70D4FEC946E473ABA142B87C0EBB3BFB2D6628661159BC`
  (unsigned test preview, not a release artifact).
- The inspected native History gallery render retains the approved dark
  styling and shows no invented saved tasks. An owned-element render is not a
  physical desktop/theme/accessibility acceptance substitute. Filled values,
  exact paths, native buttons and outcomes are asserted against SQLite/files.
- `source-build-hashes.json` records all 39 changed code/test/workflow files,
  final native source, Python source and the unchanged master blob. Diff review
  found no unrelated changes, secret material, detached branch, forced cleanup,
  fabricated success or new visual design. `git diff --check` passes.
- Documentation validation:
  `output/p14-native-env/Scripts/python.exe docs/completion/verify_requirements_matrix.py`
  passes **298 source items / 334 traceable rows**, with unique identities,
  unchanged full requirement text, valid statuses/next prompts and local links.
  The final checkpoint changes documentation only; the tested implementation
  remains exactly `d223a32`, so unrelated acceptance is not repeated.

## Recovery and next gate

Preserve unrelated work/data and use reviewed reverts toward `124200a`. E95's
additive order index may remain after source downgrade. Existing receipts and
uncertain claims must never be deleted/reset to permit another inverse. No new
schema migration or dependency is introduced by E96. A completed inverse is not
automatically redone by recovery.

P21 is not started. Independent Sol review is a separate gate; approval is not
assumed. This packet and full P20 are ready for that review. The next safe
milestone after review/owner instruction is P21. Remaining unverified work is
the existing P25 physical interaction/accessibility/timing scope and later
security/performance/release gates; none is represented as a new P20 pass.
