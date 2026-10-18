# Lower popup placement and consistent class sizes

**Latest integration verification (2026-10-19):** the refinement and subsequent
native startup/InfoBar-height corrections pass **658 native popup checks, 195
formatting checks and 35 native control checks** on the hosted Windows runner.
All class renders were exported and inspected. Exact commits, run, commands and
remaining physical Windows 11 acceptance are in
[ui_integration_review.md](ui_integration_review.md). The local signing block
below remains; the older unexecuted status describes the original local attempt.

Date: 2026-10-19. Branch: `ui-polish`.
Placement and class-size source: `f64c008`; dismissal/reflow spacing fix: `8cb49c8`.
This owner-directed refinement supersedes the always-reserved hidden-taskbar
behavior in the earlier [popup stack audit](popup_stack_verification.md).

The owner marked approximate bottom-right regions in screenshots with the
taskbar hidden and shown. The intended behavior is a lower position while
hidden, a smooth rise when the taskbar opens, comfortable edge clearance, and
moderate, identical dimensions for each notification class. The screenshots are
placement references; they are not a request to change the existing dark style.

## Changes

- `PopupDesktopPlacement.cs` now reads the taskbar's actual on-screen extent.
  A hidden activation strip is not treated as a fully visible bar. Reveal is
  detected early and targets its measured full footprint; lowering waits until
  it is fully hidden. Shell hooks remain event driven and stop when empty.
  Unknown bounds/thickness retain a conservative safe reservation.
- `PopupStackLayout.cs` represents taskbar visibility separately from thickness.
  The existing 24-DIP inset, 8-DIP shadow allowance, 12-DIP gaps and common right
  edge remain. A taskbar-only transition can animate; a real display/DPI or
  unrelated work-area change still reflows immediately for safety.
- `PopupStackHost.cs` coordinates the glide from current positions. Cards use
  the same start/frame time and round their translation to pixels to avoid
  gap jitter. If an exit overlaps a taskbar transition, all cards share its
  motion duration. Overflow still stays inside the available monitor area.
  Dismissal during an existing reflow pauses positional movement at the current
  spacing while the departing card fades; survivors reflow after removal.
- `PopupSizing.cs` defines stable class footprints, documented in
  [the placement contract](popup_placement_contract.md). The 460 x 276 voice
  design is retained; notices use 400 x 112, and paired task/tool states share
  their respective sizes. Message length does not change the native card size.
- `PopupCardWindow.cs` stretches short content into its class viewport; long
  content retains bounded native scrolling. Native frame dimensions remain
  separate from client dimensions. No palette, typography, light theme, backend
  protocol or real task execution changes are included.
- `PopupStackAudit.cs` adds native assertions for class client sizes, short/long
  notice equivalence, lower hidden anchor, intermediate upward/downward glide
  positions, size preservation and reveal during dismissal. Its taskbar fixture
  changes only reported geometry, never Windows settings.
  A further frame-sampling case covers dismissal during upward reflow.

## Executed verification

Environment: Windows 11 build 26200, .NET SDK 10.0.401 / .NET 8 target, Debug/x64.

```powershell
dotnet run --project PLUMA.UI/PopupStack.Tests/PopupStack.Tests.csproj --no-restore
# 64537 checks passed across 5000 varied display/queue scenarios.
dotnet run --project PLUMA.UI/SurfaceContracts.Tests/SurfaceContracts.Tests.csproj --no-restore
# 30 checks passed.
dotnet run --project PLUMA.UI/AudioVisualizer.Tests/AudioVisualizer.Tests.csproj --no-restore
# All audio visualizer checks passed. (15 checks)
./PLUMA.UI/check-surface-copy.ps1
# PASS 33 compiled XAML files have no underscores or em dashes in visible strings.
dotnet build PLUMA.UI/PLUMA.UI/PLUMA.UI.csproj -p:Platform=x64 -p:SurfaceGalleryPreview=true -p:OutDir=D:\Workspace\DEVEL\PLUMA\output\ui-stack-preview\ --no-restore -v:minimal
# Build succeeded. 0 warnings, 0 errors.
```

Pure checks exercise all four taskbar edges, the activation strip versus early
reveal, negative monitor origins, 100/125/150/200% scale, both glide directions,
shared class sizes, unrelated geometry changes, thick-taskbar motion paths,
queue ordering/overflow, monitor bounds and pixel-consistent gaps. The expanded
motion checks initially exposed fractional-coordinate gap comparisons; the
implementation now rounds translation consistently on a shared animation clock.

## Original local runtime limitation

Normal launches of the rebuilt preview were rejected by Windows Application
Control. Code Integrity event **3077**, 2026-10-19 at **00:15:54** local time,
identifies `output/ui-stack-preview/PLUMA.UI.exe` as failing enterprise signing
requirements. Subsequent normal launches after the motion and dismissal fixes
were also blocked. The final rebuilt source still has 0 warnings and 0 errors.
No security setting was changed and no alternative host was used to run the
blocked executable.

The new native size/glide checks are **not yet executed**. The older 504 native,
195 formatting and 35 control results apply to the earlier implementation;
they must not be presented as runtime acceptance for this refinement. No owner
approval of this limitation is assumed, and a full UI phase completion or
backend wiring readiness is not claimed.

Next verification: run `./PLUMA.UI/preview-popup-stack.ps1 -Audit` on an approved
runner, inspect the class renders and actual taskbar hover/reveal/hide, then
repeat `./PLUMA.UI/preview-surfaces.ps1 -Export`. Check real DPI configurations
and physical reading/accessibility behavior before wiring. Resolve any native
failure while retaining the owner's dark appearance and class-size rules.
