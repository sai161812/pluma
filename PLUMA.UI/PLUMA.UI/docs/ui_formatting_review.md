# All-surface formatting review

Date: 2026-10-18. Branch: `ui-polish`. Includes the runtime fixes in `0127744`.
Scope: owner-directed appearance and message formatting before placement/wiring.

**Latest placement refinement (2026-10-19):** lower hidden-taskbar positioning,
reveal/hide glide and stable notification-class sizes are implemented and pass
64,537 pure checks and the expanded hosted **661 native popup checks**. The
integration also reran all **195 native formatting checks and 35 control checks**,
and exported all 26 Dark surfaces and 15 floating class renders. Startup layout
and fixed InfoBar background height corrections are included. See
[ui_integration_review.md](ui_integration_review.md) for the tested source and run.
The owner's local signing block remains unchanged; physical Windows 11 taskbar,
DPI and accessibility review remains open. Results below retain their original
component-baseline source and environment.

Owner correction on 2026-10-18: PLUMA is dark-only, matching the owner's Windows
appearance. `App.xaml` explicitly requests Dark. The native gallery, HTML
viewer, exports, formatting audit, and control-preview harness now use Dark
only. Light-theme support and review are outside the requested scope. The
current exporter produces 26 dark component renders, plus stress fixtures.

**Current native formatting audit: 195 checks passed, with all 26 Dark renders.
Native control runner: 35 UI checks passed.** The shared desktop host also has
passing native fixture evidence, documented in
[popup_stack_verification.md](popup_stack_verification.md). Those baseline executables
launched normally without changing security policy; later local builds are
blocked as recorded in the latest integration review. Physical display/taskbar,
accessibility and owner motion review
remain open; Phase 14 and backend wiring are not claimed complete.

## Review against the four requirements

| Requirement | Implementation and evidence | Remaining evidence |
|---|---|---|
| Native Windows appearance | All 26 Dark renders inspected against `PLUMA_WINDOWS_11_UI_STYLE_MAPPING.md` and existing controls. Standard WinUI resources, Acrylic floating surfaces, native conflict dialog and committed InfoBar; no new dark palette. | Physical display/accessibility and owner review remain. |
| Long text fits notifications | Shared `PopupMessageText` wraps and uses bounded native scrolling, readable font sizes, no ellipsis or line-count cutoff. A finite 460-DIP maximum also bounds InfoBar's initially infinite content measure. The transcript stays within its existing 460x276 host. | Native long-word, Unicode, enlarged-text, scrolling and transcript-follow checks pass; other physical DPI remains open. |
| Status elements align with captions | Shared `PopupStatusIndicator` centers glyphs/spinners and text in one grid row; a 14-DIP ProgressRing has no conflicting minimum size. | Native measured centers pass, including enlarged captions. |
| No underscores or em dashes in messages | Display-only normalization preserves raw values and factual data. All 33 compiled XAML files pass the copy scan. | Actual visible TextBlocks pass the native scan. |

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

The earlier `output/ui-formatting-preview/PLUMA.UI.exe` launch was refused by
Windows Application Control. Those old outputs are not current acceptance
evidence. The current normal launch succeeds: all 26 Dark renders and 195
passing formatting checks are in `output/surface-gallery-final-audit/`.
The current control runner also launches and reports 35 passing UI checks in
`SurfaceControls.Tests/bin/x64/Debug/net8.0-windows10.0.19041.0/win-x64/control-tests.txt`.

The explicit gallery export now includes a fail-fast native audit of every
surface in Dark, long unbroken words/Unicode, 150% message/caption text,
foreground theme, viewport bounds, reachable last lines, glyph/text centers,
transcript follow/read-back behavior, and committed-banner fit. It writes
`formatting-checks.txt` and `stress-*.png`; these checks now **pass in Dark**.
Enlarged text is not a substitute
for physical DPI, high-contrast, keyboard, or screen-reader acceptance.

The runtime audit found and fixed an unconstrained InfoBar long-word measure;
the native control runner found and fixed pre-layout OCR bounds validation.
Its Dark health-brush assertion now compares with an actual theme-resource
probe, rather than assuming live dictionary insertion changes the OS theme.
No production health color changed. Next: finish physical/interactive placement
checks in the stack report before separate wiring or a full Phase 14 claim.

## Dark-only correction verification

Changed files: `App.xaml`, `SurfaceGalleryWindow.xaml/.cs`,
`SurfaceGalleryAudit.cs`, `SurfaceControls.Tests/TestApp.xaml`,
`SurfaceControls.Tests/App.xaml.cs`, `SurfaceControls.Tests/VisualReview.cs`,
and these gallery/review documents. Existing light renders remain historical
artifacts; no new light renders are requested or generated.

The copy scan still passes for 33 compiled XAML files, and the contract harness
still reports 30 checks passed. Both the app preview and control harness build
with zero warnings/errors. Subsequent current native execution passes as
recorded above; older blocked runs are retained as historical evidence.
No wiring or backend behavior changed.

## Owner placement direction recorded

On 2026-10-18 the owner chose bottom-right placement for surfaces 4-9, 11-14,
17, 19-21, and 24. New arrivals belong below older visible entries, which slide
up smoothly; entry/exit, edge clearance, spacing, overflow, and auto-hide taskbar
reveal must remain clean. Keep the existing dark appearance. The detailed
implementation contract and P-01 through P-15 acceptance cases are in
[popup_placement_contract.md](popup_placement_contract.md).

The shared desktop host is implemented and its native fixture audit passes.
The isolated catalogue and legacy voice preview remain separate from the host.
See `popup_stack_verification.md` for executed evidence and remaining real
taskbar/DPI/accessibility/owner-motion checks. No backend wiring or palette
redesign is included.
