# E95: P20 saved-task history browsing packet

Date: 2026-11-02. Branch: `p12-preparation`.
Production implementation: `523ae61541af01e2bae9ac55750278123afa27a7`.
Final verification source: `f393b087ebd2414b03e88994998cead774528542`.
Independent field-readback checks: `f348d1070b95a8d755b89b87d16bcdb8b8ccd3f7`.
Recovery: `8d5548e1eac0113c94f791e522bcc3e1df1aae1c` (E94).

This packet implements redacted saved-task browsing, literal search and bounded
paging in the existing History page. **It is a bounded P20 packet; full P20
remains in progress.** Action details, selected undo, conflict handling and the
remaining Activity entry wiring are not implemented by this packet.

## Prerequisites and scope

The checkout was clean at E94. Branch, remotes/worktrees and current source were
inspected; no merge, branch switch or reset was performed. The complete unchanged
master was reused and its blob refreshed:
`01b693dbf898b662aa4cd67736c1a0e8a21cf3e3`. AGENTS, shared/P20 prompts,
latest handoff, matrix, applicable Phase 5/14, ledger/privacy and acceptance
requirements were reviewed. Existing P00-P19 evidence retains its stated scope.
The E94 owner-approved physical C-02 timing retest remains P25; no device/model
acceptance was repeated or inferred here.

Before editing, **145 prerequisite checks passed in 21.87 s**, including durable
undo/rollback, existing history/activity contracts, voice lifecycle and STOP.
The actual History page contained four fixed sample records. The existing recent
history query had a result cap and no full-search/keyset browsing contract.

## Implemented contract

- New authenticated v1 `history_page_query` / `history_page` leaves the old
  history wire unchanged. Request fields are canonical query `request_id`,
  literal `search` (at most 256 Unicode characters), nullable canonical
  `before_task_id` and `limit` (1-20). Extra/invalid fields are rejected before
  storage. This is a read API, never command or undo admission.
- One independent read-only SQLite transaction anchors the cursor and page.
  Stored `created_at`/`task_id` descending order is stable, including ties.
  One extra matching row proves continuation; no total count or end is invented.
  Missing cursors require refresh. Newer insertions do not repeat old rows while
  paging; refresh returns to the newest records.
- Literal case-insensitive Unicode substring search covers redacted command,
  task identity, saved state, route and input mode. SQL parameters are not SQL
  syntax. Searching a private legacy clipboard value cannot reveal its presence.
  Commands are redacted completely before matching or display. Oversized input
  is withheld in full before Python receives it, with no exposed prefix.
- At most 20 rows and 8192 UTF-8 command bytes per row are returned. Malformed or
  private-shaped codes are withheld, unknown historical flags are unavailable,
  and malformed timestamps fail closed. No original transcript, app/window body,
  action arguments/results, screen data or undo recipe is fetched.
- The file-only snapshot has a 250 ms SQLite progress budget and 50 ms lock wait;
  work exceeding it returns unavailable, never false empty results. It does not
  alter a shared connection's functions, transaction or progress handler.
  Anonymous in-memory storage has no independent durable snapshot and is refused;
  existing in-memory legacy APIs remain unchanged.
- Migration `0007_history_order.sql` adds only the stable order index. Existing
  task/action/undo rows are unchanged, and migration/reopen checks pass.
- The shell owns one history controller/read, a three-second cancellation budget
  and at most two read-only retries for temporary Busy. Navigation shares its
  state; close cancels and joins it. A validated older page replaces its predecessor,
  so memory stays bounded. Read failures clear stale rows and differ from empty
  or unmatched storage. Browsing does not create tasks or invoke tools.
- Production samples are removed. The existing dark styles, width, padding,
  typography and row separators remain. Native search/refresh/older controls use
  typed readback. Literal filenames and original DTO identities remain intact;
  presentation labels and local timestamp formatting do not modify stored values.
  The UI explicitly labels saved state rather than inventing verification.

Files: `pluma/memory/{db,history}.py`, migration 0007, IPC contracts/resident;
native `CoreHistoryProtocol.cs`, `HistoryController.cs`, History page and main
window wiring, plus the reproduced shared `PopupMessageText.cs` reader race.
Tests/host links and owned render export are updated. No undo
implementation, policy, ToolSpec, planner or visual palette was changed.

## Verification

Logs are under the ignored directory named in `output/p20-history-current.txt`.
APPDATA, LOCALAPPDATA and PLUMA_CONFIG were isolated. Tests use owned SQLite,
credentials/pipes, files and native windows. No personal clipboard, browser,
power state, microphone, files or pre-existing processes were used.

Final affected Python command:

```powershell
output/p14-native-env/Scripts/python.exe -m pytest -q tests/unit/test_p20_history.py tests/unit/test_db.py tests/unit/test_activity_ledger_lifecycle.py tests/unit/test_p15_remaining_contracts.py tests/unit/test_p18_activity_query.py tests/unit/test_p18_action_details.py tests/unit/test_manual_undo.py tests/unit/test_rollback_engine.py tests/unit/test_p19_voice_bridge.py tests/unit/test_stop_protocol.py tests/unit/test_p18_runtime.py tests/unit/test_runtime_shutdown.py -p tests.fixtures.desktop_isolation
```

Pre-edit prerequisite command (`baseline.log`):

```powershell
output/p14-native-env/Scripts/python.exe -m pytest -q tests/unit/test_p15_remaining_contracts.py tests/unit/test_p18_activity_query.py tests/unit/test_p18_action_details.py tests/unit/test_manual_undo.py tests/unit/test_rollback_engine.py tests/unit/test_p19_voice_bridge.py tests/unit/test_stop_protocol.py -p tests.fixtures.desktop_isolation
```

The selection covers migration, stopped/residual saved facts, independent SQLite
field agreement, stable paging beyond the old cap, insertion/restart, Unicode
and SQL metacharacters, legacy clipboard privacy, oversized data, malformed
requests/cursors, unavailable storage, read-only enforcement and interrupted
SQL work. Existing atomic undo, rollback, ownership, STOP and shutdown remain
regressions; no skip/xfail is an acceptance pass.

Result: **248 passed in 46.26 s**, no skips/xfails, on `f348d10`. The subsequent
`f393b08` changes only the C# reader and its native regression; Python source
and this selection are unchanged. Pre-edit prerequisites were 145 passes.

Native commands:

```powershell
dotnet build PLUMA.UI/CoreIpc.Tests/CoreIpc.Tests.csproj --verbosity quiet -p:UseSharedCompilation=false
dotnet build PLUMA.UI/SurfaceControls.Tests/SurfaceControls.Tests.csproj --verbosity quiet -p:UseSharedCompilation=false
dotnet run --no-build --project PLUMA.UI/CoreIpc.Tests/CoreIpc.Tests.csproj --verbosity quiet
dotnet run --no-build --project PLUMA.UI/SurfaceControls.Tests/SurfaceControls.Tests.csproj --verbosity quiet
```

`PLUMA_TEST_PYTHON` selected the absolute path of the isolated p14-native-env
Python. Native history acceptance uses the actual MainWindow, buttons, template,
authenticated client and production query. A separate SQLite connection/Python
projection checks **every returned field**, including state/route/mode, all
timestamps, STOP reason and error code. It exercises 75 owned saved records,
empty/private/Unicode search, paging, navigation, closed/reopened storage and
joined shutdown. Fixture rows establish display/readback validity, not new tool
execution or real personal-history acceptance.

The full Windows workflow also runs existing popup, gallery, formatting,
layout/surface, audio, copy, P18 whole-shell and P19 voice checks. Native runners
write explicit reports; an empty console or exit alone is not a pass. The saved
history render is an owned-element render, not a personal-desktop capture.

Final exact-source [Windows gate 41414630764](https://github.com/sai161812/pluma/actions/runs/41414630764)
passed on `f393b087ebd2414b03e88994998cead774528542`:
**265 IPC / 187 native UI / 663 native popup / 195 formatting** checks,
**64,537 layout / 30 surface** checks, audio visualization and copy gates.
The UI total includes ten P20 history checks and the added queued-follow
regression; earlier reading remains before=0/after=0 in the same reader.
Both production UI and native host builds have zero warnings/errors.
No skip/xfail, fixture transcript or visual impression is counted as device/model
acceptance. The workflow command is `./PLUMA.UI/verify-ui.ps1` on `windows-2025`.

Artifact ID `13127014111`, SHA-256:
`6dcb0404ef6a305162778d392f43182c3c19e9c9acd9235cd26204b583aaff74`.
The downloaded ZIP digest was checked before extraction. Final reports/renders
are under `ci-final/20261102-084055-2caf3433` within the ignored log directory.
Preview executable SHA-256:
`EC7B9B57AB8CFA05D4A8728D4F6AFC6A0AB354D9481D38FA774C0C2B3E711FE0`
(unsigned test preview, not a release artifact).
`source-build-hashes.json` records all 24 changed code/test files and the
unchanged master identity. The inspected gallery History render preserves the
native dark page and empty state; the filled owned-element render verifies
readable literal rows but has transparent/background and composition limitations,
so it is not a physical-desktop theme/accessibility acceptance claim.

`verify_requirements_matrix.py` passes: **298 source items / 333 traceable rows**;
locked requirement texts are unchanged. `git diff --check` passes.

## Failed attempts and corrections

- Early local full runs failed the existing P19 earlier-reading assertion.
  Observing the actual top position replaced an assumed fixed-delay setup, but
  [run 41412103460](https://github.com/sai161812/pluma/actions/runs/41412103460)
  still reproduced a real queued-follow race: before=0, after=1492, extent=1492,
  in the same reader. The shared reader now cancels queued following when its
  viewport moves away from the tail or native scrolling input arrives. A new
  native regression moves to earlier text between a transcript update and queued
  layout. Existing one-pixel preservation and actual tail-follow assertions remain.
  No timeout or assertion was relaxed and no styling changed.
- One local full attempt timed out in unchanged P18 startup. It was retained as
  a failure; later full acceptance passed. No timeout or assertion was relaxed.
- The new independent fixture reader initially used SQLite's transaction context
  without closing its connection. Windows correctly refused fixture-file cleanup.
  It now closes explicitly; the final full run verifies cleanup. Production
  snapshots already closed in `finally`.
- Initial independent checks covered identities/commands. Final review extended
  both Python and native checks to all displayed fields, then repeated the gate
  on the final test revision. Earlier passes do not stand in for that revision.
- The reader fix built locally without warnings/errors, but Application Control
  blocked the new native executable. That attempt did not execute acceptance.
  An old copied report is explicitly excluded; the authorized Windows CI host
  supplies final native evidence. No execution policy was bypassed.

Focused native flags are available for diagnosis; normal CI uses neither and
runs the complete suite. Failed attempts are retained and never counted as passes.
No Windows security policy was changed or bypassed.

The first exact `f393b08` Windows attempt, [41413894036](https://github.com/sai161812/pluma/actions/runs/41413894036),
passed 265 IPC checks and both builds (zero warnings/errors), then failed the
existing P18 shell startup admission wait before reaching P19/P20. Its report
and artifact are retained as a failure, not a P20 pass. The same unmodified full
workflow was retried to check the intermittent startup behavior.
The retry passed without changing source, timeouts or assertions. The startup
timeout's root cause is **not established or claimed fixed**; retain it as a
diagnostic follow-up before building further command/undo admission behavior.

## Remaining P20 and recovery

1. Bind task/action detail, context/appropriate original input, policy,
   verification, cleanup, rollback and residual readback to safe scoped contracts.
2. Define/verify selected undo admission through typed registered execution,
   material confirmation, ownership and STOP. Preserve reverse ordering,
   atomic consumption, stale/conflict refusal and factual outcomes; no duplicate
   click may repeat an inverse or promise reversal of an irreversible commit.
3. Bind actual conflict data/actions to surface 10, complete Activity tray/command
   entry integration and run the remaining owned-file undo/conflict acceptance.

The next safe packet is P20 task/action detail, then scoped undo admission after
checking the retained intermittent startup/admission observation. P21 is not
eligible and has not started. This bounded packet is ready for independent Sol
review with that observation visible; approval is not assumed.
Recovery is a reviewed revert toward `8d5548e`, preserving unrelated work and
the database. The additive index may harmlessly remain on source downgrade;
do not reset/clean/force-push or delete user data to recover.
