# All-surface formatting review

Date: 2026-10-18. Branch: `ui-polish`. Product changes through `c62fd9f`.
Scope: owner-directed appearance and message formatting before placement/wiring.

**Implementation and build checks are complete. Final native visual/layout
acceptance is blocked and has not passed.** Windows Application Control refused
the rebuilt preview executable, including the final launch attempt. Event 3077
reports enterprise signing requirements. No security policy was changed. Under
`AGENTS.md`, this is not a fully accepted UI phase; no owner-approved limitation
is assumed, and wiring has not started.

## Review against the four requirements

| Requirement | Implementation and evidence | Remaining evidence |
|---|---|---|
| Native Windows appearance | Reviewed all 26 surfaces against `PLUMA_WINDOWS_11_UI_STYLE_MAPPING.md` and existing components. Standard WinUI resources, Acrylic floating surfaces, card fills in Dashboard, native conflict dialog, and native committed InfoBar. | Inspect the final build in light/dark themes. Earlier renders are historical references. |
| Long text fits notifications | Shared `PopupMessageText` uses word/character wrapping and bounded native vertical scrolling, without ellipsis or a line-count cutoff. Body text remains readable; captions stay at least 12px. Transcript viewport is 64 DIPs within the existing 460x276 voice overlay. | Run the native long-word, Unicode, scrolling, enlarged-text, and transcript-follow checks. |
| Status elements align with captions | Shared `PopupStatusIndicator` centers dots, checkmarks, spinners, and text in the same grid row. ProgressRing minimum dimensions are explicitly removed so a 14-DIP ring fits. Text line height adapts to its size. | Run the measured center-alignment checks, including enlarged captions. |
| No underscores or em dashes in messages | Static scan passes for all 33 compiled XAML files. Display-only formatting converts tool/state labels and sanitized argument fields; removes both separators; preserves line breaks, file extensions, Unicode, and normal ellipses. Raw transcripts, arguments, event messages, and ledger data are preserved. | Native audit also scans the actual visible TextBlocks. |

## Surface review

| ID | Surface | Native pattern and formatting disposition |
|---|---|---|
| 1 | Dashboard | Native page/list/card composition; standard card fills and readable state labels. |
| 2 | Settings | Existing Community Toolkit SettingsCard/SettingsExpander and native inputs retained. |
| 3 | History | Native searchable ListView; state labels use sentence case and readable detail captions. |
| 4 | Task running | Acrylic flyout treatment, shared status row, bounded message and metadata. |
| 5 | Step progress | Acrylic progress flyout, shared status row, readable action label and bounded purpose. |
| 6 | Route badge | Compact Acrylic surface with existing native typography. |
| 7 | Tool call | Fluent card; readable action and arguments, bounded wrapping, shared status. |
| 8 | Tool result | Fluent card; bounded result/error copy, aligned completion and verification indicators. |
| 9 | Rollback | Acrylic progress surface with native progress controls and bounded message rows. |
| 10 | Conflict | Real ContentDialog with native title/buttons/modal treatment; Close is default. File buttons raise requests only. |
| 11 | Voice listening | Existing owner-approved motion retained; Acrylic host and aligned native status. |
| 12 | Transcription | Full display text in a bounded ScrollViewer; follows new speech while at the end, preserves scroll position while reading earlier words. Only the header is a drag region in the preview window. |
| 13 | Voice committed | Native success InfoBar within the existing voice content area. |
| 14 | Silence timeout | Existing native determinate ProgressBar retained. |
| 15 | Capture flash | Existing brief native XAML opacity animation retained; no message text. |
| 16 | Text match | Existing input-transparent focus outline/Acrylic callout retained; readable match label and bounded text. |
| 17 | Verification | Native Success/Error InfoBar, readable method labels and bounded details; no inferred success. |
| 18 | Approval | Native ContentDialog; readable action/risk/details, bounded fields, Deny remains default. |
| 19 | Policy block | Native Error InfoBar with readable tool/rule text and bounded details. |
| 20 | Cancellation | Acrylic progress surface with shared status and bounded heading/body/metadata. |
| 21 | Worker termination | Acrylic status surface with aligned checkmark/caption and bounded messages. |
| 22 | Message feed | Native ListView scrolling; readable display copy while original event strings remain intact. |
| 23 | Health | Existing native InfoBadge and measured-status text retained. |
| 24 | Notification | Native in-app InfoBar, following the owner's earlier direction; readable bounded copy. Separator-only messages stay hidden. |
| 25 | Critical error | Native ContentDialog/Expander with bounded readable error/details; Close remains default. |
| 26 | Setup | Existing SettingsCard sequential flow; readable check descriptions and original safety gates retained. |

## Files and commands

Shared presentation code: `PopupText.cs`, `PopupMessageText.cs/.xaml`, and
`PopupStatusIndicator.cs/.xaml`. The surface XAML/code-behind files listed above
use these helpers. `VoiceOverlayPreviewWindow.xaml.cs` limits dragging to the
header so the transcript can receive scrolling input. `PLUMA.UI.csproj` registers
the two shared XAML roots exactly once. No backend or pipeline code changed.

Verification changes: `SurfaceContracts.Tests/Program.cs` and project links;
`SurfaceControls.Tests/App.xaml.cs` and project links; `check-surface-copy.ps1`;
`SurfaceGalleryAudit.cs` and the gallery export integration. Test artifact
directories and pre-existing workspace files are excluded from commits.

Executed on Windows build 26200, .NET SDK 10.0.401, .NET 8 target, Debug/x64:

```powershell
./PLUMA.UI/check-surface-copy.ps1
# PASS 33 compiled XAML files have no underscores or em dashes in visible strings.

dotnet run --project PLUMA.UI/SurfaceContracts.Tests/SurfaceContracts.Tests.csproj --no-restore
# 30 checks passed.

dotnet run --project PLUMA.UI/AudioVisualizer.Tests/AudioVisualizer.Tests.csproj --no-restore
# All audio visualizer checks passed. (15 checks)

dotnet build PLUMA.UI/PLUMA.UI/PLUMA.UI.csproj -p:Platform=x64 -p:SurfaceGalleryPreview=true -p:OutDir=D:\Workspace\DEVEL\PLUMA\output\ui-formatting-preview\ --no-restore -v:minimal
# Build succeeded. 0 Warning(s), 0 Error(s).

dotnet build PLUMA.UI/SurfaceControls.Tests/SurfaceControls.Tests.csproj -p:Platform=x64 --no-restore -v:minimal
# Build succeeded. 0 Warning(s), 0 Error(s).
```

The first intermediate build exported 52 native renders into
`output/ui-formatting-first/`. Inspection exposed the light-theme foreground
problem subsequently fixed by themed XAML roots. Those images predate the final
alignment/material/contrast changes and do not prove current acceptance.

The final normal executable launch for `output/ui-formatting-preview/PLUMA.UI.exe`
was refused by Windows Application Control. Consequently, neither final renders
nor a passing `formatting-checks.txt` exist for this version. The separate WinUI
behavior harness also retains its previously recorded execution blocker. Older
test outputs must not be counted as current passes.

The explicit gallery export now includes a fail-fast native audit of every
surface in both themes, long unbroken words/Unicode, 150% message/caption text,
foreground theme, viewport bounds, reachable last lines, glyph/text centers,
transcript follow/read-back behavior, and committed-banner fit. It writes
`formatting-checks.txt` and `stress-*.png`; these checks are **implemented but
unexecuted**, rather than claimed as passing. Enlarged text is not a substitute
for physical DPI, high-contrast, keyboard, or screen-reader acceptance.

Next step: execute `./PLUMA.UI/preview-surfaces.ps1 -Export` and the WinUI behavior
harness in an environment whose signing policy permits the development build,
then inspect the resulting native previews. Resolve any failures before the
separate wiring task or a full Phase 14 completion claim.
