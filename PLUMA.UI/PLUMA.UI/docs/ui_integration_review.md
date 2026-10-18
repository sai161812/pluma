# Clean UI integration review

Date: 2026-10-19. Integration branch: `ui-polish-integration`.
Base: `main` at `6dbf58925352d41a0196dda33044b18282cc6ddf`.
Source snapshot: `ui-polish` at `9150e81efe539e822b5a257ac2f2a23a24ee965e`.
Import commit: `d15a7c0`.

## Scope and history

The original branches have unrelated roots. This integration starts from the
current main commit and imports the UI subtree as an ordinary descendant,
without combining unrelated histories or replacing either existing branch.
The original `ui-polish` remains available with its complete development history.

The import contains **125 source, project, documentation, test and asset files**,
whose Git blob IDs exactly match the source snapshot. It excludes **676
generated or user-local paths**: 675 `bin`/`obj` build-output paths and one
`.csproj.user` file. The seven small PNG files under `Assets/` are project source
assets, not captured runtime images. The empty obsolete preview XAML files are
retained as part of the original project snapshot; they are not compiled Pages.

Only `PLUMA.UI/`, `.github/workflows/ui-verification.yml` and additive
`.gitignore` rules differ from main. The Python
backend, its tests, root README, release report, agent contract, immutable master
specification, build plan and acceptance requirements remain identical to main.
No IPC, backend wiring, product styling or execution behavior was changed by
the import. Subsequent commits add this review, a bounded native verification
runner and small native layout corrections described below. The 125 matching
blobs establish import provenance; they do not claim that later fixes are
byte-identical to the original snapshot.

New ignore rules cover UI `bin`/`obj`, Visual Studio state, `.csproj.user`, `.suo`
and root `output/` exports. Existing ignore rules are retained. The source tree
and test projects were restored and built in a fresh isolated worktree; no old
generated output was copied over.

## Executed checks

Windows 11 build 26200, .NET SDK 10.0.401 / .NET 8 target, Debug/x64.

| Check | Result |
|---|---|
| Git ancestry | Merge base equals the latest fetched main commit |
| Imported file provenance | All 125 Git blobs match `ui-polish` exactly |
| Scope | Backend, backend tests and root documentation unchanged |
| Artifact exclusion | No tracked `bin`, `obj`, `.vs` or user-local project state |
| Ignore probes | UI build output, IDE state and preview export paths ignored |
| Popup layout model | 64,537 checks pass across 5,000 display/queue scenarios |
| Surface contracts | 30 checks pass |
| Audio visualizer | 15 checks pass |
| Visible-copy scan | 33 compiled XAML files pass |
| Main UI build, fresh restore | 0 warnings, 0 errors |
| Native control-runner build, fresh restore | 0 warnings, 0 errors |

Commands, run from the integration worktree:

```powershell
dotnet run --project PLUMA.UI/PopupStack.Tests/PopupStack.Tests.csproj --verbosity quiet
dotnet run --project PLUMA.UI/SurfaceContracts.Tests/SurfaceContracts.Tests.csproj --verbosity quiet
dotnet run --project PLUMA.UI/AudioVisualizer.Tests/AudioVisualizer.Tests.csproj --verbosity quiet
./PLUMA.UI/check-surface-copy.ps1
dotnet build PLUMA.UI/PLUMA.UI/PLUMA.UI.csproj -p:Platform=x64 -p:SurfaceGalleryPreview=true -p:OutDir=D:\Workspace\DEVEL\PLUMA-ui-integration\output\ui-integration-preview\ -v:minimal
dotnet build PLUMA.UI/SurfaceControls.Tests/SurfaceControls.Tests.csproj -p:Platform=x64 -v:minimal
```

Diff review verified the additive scope and source equality and found no new
credentials. `git diff --check` reports inherited Markdown hard-break spacing
and two pre-existing trailing-space lines in `app.manifest`. These are retained
to keep the imported source byte-identical; they do not affect the builds.
Backend tests were not rerun: their code and all backend files are unchanged.

## Hosted native verification and layout corrections

The first hosted Windows run launched the app but failed its native client-width
assertion. Diagnostic measurements were added without weakening that assertion.
[Run 2](https://github.com/sai161812/pluma/actions/runs/39158178631), head
`186e299`, then passed **518 native popup checks, 195 formatting checks and
35 native control checks**, and exported all 26 Dark gallery surfaces plus all
15 floating class renders. Its first notice measured 400 x 112 client DIPs,
with a separately measured 6 x 6 physical-pixel native frame at 96 DPI.

The earlier failure remains recorded; a later pass alone does not explain it.
Inspection found a startup timing gap: fade completion did not wait for the
first native XAML layout. `6b6e89f` now shows a new card transparently without
activation, waits for Loaded and positive XAML bounds matching the actual client
rectangle, and remeasures after root-size changes. Pending reconciliation counts
as unsettled. Native assertions check readiness before sampled visible frames;
the 50-window lifecycle test also waits for layout with motion disabled.

Render inspection found that the native InfoBar template left an unused strip
under short notices in the fixed 112-DIP viewport. `d312ac6` scopes the existing
`InfoBarMinHeight` resource to that viewport, subtracting the native themed border.
The native template, colors, typography and class dimensions are retained.
The audit checks the actual background height on surfaces 17, 19 and 24.

The corrections passed [run 5](https://github.com/sai161812/pluma/actions/runs/39158908362)
on head `d312ac657106eb0690153f1bb6ffeb8ac38ae4de`, tested as PR merge
`002a9606b1ca1653c67a5dd22bdf4532f262ab06`. Windows Server build 26100,
.NET SDK 10.0.402 / runtime 8.0.32, x64, 96 DPI, interactive session:

| Current check | Result |
|---|---|
| Popup layout model | 64,537 checks pass across 5,000 scenarios |
| Surface contracts / audio visualizer | 30 / 15 checks pass |
| Visible-copy scan | 33 compiled XAML files pass |
| UI / native control builds | Both have 0 warnings, 0 errors |
| Native popup audit | 658 checks pass, including first-layout readiness, class dimensions, InfoBar background height, taskbar-fixture glide and 50 lifecycles |
| Native all-surface formatting | 195 checks pass, including long words, Unicode, enlarged text, caption alignment and transcript scrolling |
| Native control runner | 35 checks pass, exit code 0 |
| Exported fixture renders | All 26 gallery surfaces and 15 floating classes present; 58 PNGs including stress fixtures |

The workflow executed `./PLUMA.UI/verify-ui.ps1`; its individual commands are
recorded in the script and run logs. The completed reports, process metadata and
fixture renders are in the `windows-ui-verification` artifact (seven-day
retention), downloaded locally under `output/ci-artifacts/run-39158908362/`.
All 26 gallery surfaces and 15 class renders were visually inspected, with
the three corrected InfoBar renders inspected again. No desktop was captured.
The executable SHA-256 is
`EBBF365597A0292BEF1BE5B1E62AA189FF1C5B0D672C3D966F7A7562307EEA72`.

## Draft status and remaining gate

The integrated executable's normal launch was also blocked by Windows
Application Control. Code Integrity event 3077 at **2026-10-19 00:33:21** local
time identifies `output/ui-integration-preview/PLUMA.UI.exe` as not meeting
enterprise signing requirements. No Windows security configuration was changed.

Hosted native popup size/glide checks have executed as recorded above; local
Windows 11 execution remains blocked. Earlier results in the imported documents
remain historical evidence for their named source revisions. See
[popup_placement_refinement.md](popup_placement_refinement.md)
for those changes and [popup_placement_contract.md](popup_placement_contract.md)
for the owner's appearance, dimensions and taskbar behavior requirements.

Keep the integration PR in draft until real Windows 11 taskbar reveal/hide,
monitor/DPI, reading/accessibility and owner appearance/motion checks are reviewed.
The hosted taskbar fixture changes reported geometry only; it does not exercise
the owner's physical auto-hide taskbar. No owner-approved
limitation, full Phase 14 completion or readiness for backend wiring is assumed.
The integration work does not merge the PR or begin wiring automatically.
