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

Only `PLUMA.UI/` and additive `.gitignore` rules differ from main. The Python
backend, its tests, root README, release report, agent contract, immutable master
specification, build plan and acceptance requirements remain identical to main.
No IPC, backend wiring, product styling or execution behavior was changed by
the import. A second documentation commit adds this review record.

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

## Draft status and remaining gate

The integrated executable's normal launch was also blocked by Windows
Application Control. Code Integrity event 3077 at **2026-10-19 00:33:21** local
time identifies `output/ui-integration-preview/PLUMA.UI.exe` as not meeting
enterprise signing requirements. No Windows security configuration was changed.

Current native popup size/glide checks are **not executed**. The earlier native
results in the imported documents remain historical evidence, not acceptance of
the latest refinement. See [popup_placement_refinement.md](popup_placement_refinement.md)
for those changes and [popup_placement_contract.md](popup_placement_contract.md)
for the owner's appearance, dimensions and taskbar behavior requirements.

Keep the integration PR in draft until the native preview/audit runs on a
permitted Windows runner and the real taskbar reveal/hide, class sizes, long
text, monitor/DPI and reading/accessibility checks are reviewed. No owner-approved
limitation, full Phase 14 completion or readiness for backend wiring is assumed.
The integration work does not merge the PR or begin wiring automatically.
