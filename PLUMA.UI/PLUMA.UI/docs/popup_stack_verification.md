# Popup stack implementation and audit

**Historical baseline:** the owner refined placement and class sizes on
2026-10-19. The latest hosted integration passes **658 native popup checks,
195 formatting checks and 35 control checks**; exact source/run evidence and the
remaining physical Windows 11 checks are in
[ui_integration_review.md](ui_integration_review.md). Source changes and the
original local native-launch block are in
[popup_placement_refinement.md](popup_placement_refinement.md).
The 504 native checks below predate that refinement and do not accept its new
size or taskbar-glide behavior.

Date: 2026-10-19. Branch: `ui-polish`. Owner appearance and placement contract:
[popup_placement_contract.md](popup_placement_contract.md).

Source revisions: layout/model `2fd81af`, native formatting/OCR fixes `0127744`,
shared host and native audit `3b692ad`. The final runs used that committed source;
generated binaries/renders are local verification artifacts.

The shared stack is implemented. Automated native, layout, component and copy
checks pass. Physical taskbar hover, other real monitor/DPI configurations,
assistive input, and owner motion review remain open. This is not a claim that
Phase 14 or the backend/end-to-end acceptance gates are complete.

## Implementation

- `PopupStackHost.cs`: one UI-thread coordinator, stable identity updates,
  bounded queue, newest below older entries, STOP presentation priority,
  expiry/reading hold, coordinated dismissal and deterministic disposal.
- `PopupCardWindow.cs`: card-sized PLUMA-owned windows, common right edge,
  measured native client/frame bounds, existing Dark theme background and
  controls, no activation on routine display. No invisible desktop-sized input
  surface. Text remains wrapped/scrollable when the usable height is small.
- `PopupDesktopPlacement.cs`: isolated read-only monitor/DPI/appbar adapter;
  taskbar and display events, conservative auto-hide reservation, no cursor
  polling or changes to Windows settings. Hooks run only while entries exist.
- `PopupStackState.cs` / `PopupStackLayout.cs`: pure ordering, admission,
  lifetime and physical-pixel geometry. At most 48 identities; false admission
  must be handled by the future event adapter. No ledger or backend is added.
- `IHostedPopup.cs` and existing Toast/Voice/Cancellation/Termination controls:
  preserve visible content until the host finishes its exit; child timers and
  fades cannot prematurely collapse hosted content.
- `MainWindow.xaml.cs` / `App.xaml.cs`: lazy host; explicit fixture launch
  flags. Normal app launch no longer opens the legacy microphone preview.
  That diagnostic remains available explicitly with `--voice-preview`.
- `PopupStackPreviewWindow.cs` / `PopupStackAudit.cs`, gallery button and
  `../../preview-popup-stack.ps1`: opt-in owned fixtures; no IPC, real tool calls,
  microphone, worker termination or inferred task success.

Existing dark component resources, typography and layouts remain the visual
source. The audit additionally fixed two real defects: an unconstrained InfoBar
could measure long text thousands of pixels wide, and a collapsed OCR marker
could accept out-of-bounds geometry before its first arrange. The shared text
first measure is now bounded; OCR validates explicit host constraints first.
The test runner now compares the health brush with a native Dark theme-resource
probe rather than assuming dictionary insertion at runtime is a theme switch.
No production health palette changed.

## Executed evidence

Windows 11 build 26200, .NET SDK 10.0.401 / runtime 8.0.31, Debug/x64. Native
display: monitor/work area `(0,0,1920,1200)`, scale `1.25`, bottom auto-hide
taskbar found, geometry verified, reservation 80 physical pixels. Insets are
24 DIPs plus 8 DIPs shadow reserve; gaps are 12 DIPs. Native outer frames are
measured separately from the component's usable width.

| Check | Result / retained local output |
|---|---|
| Pure popup tests, 5,000 varied queues/displays | **63,689 checks passed** |
| Native popup host audit | **504 checks passed**, `output/popup-stack-verified/popup-stack-audit.txt` |
| All 26 Dark component renders and formatting stress | **195 checks passed**, `output/surface-gallery-final-audit/formatting-checks.txt` |
| Native control behavior runner | **35 UI checks passed**, `SurfaceControls.Tests/bin/x64/Debug/net8.0-windows10.0.19041.0/win-x64/control-tests.txt` |
| Surface contracts | **30 checks passed** |
| Audio visualizer regression | **15 checks passed** |
| Compiled XAML visible-copy scan | **33 files passed** |
| App preview and native control runner builds | **0 warnings, 0 errors** |

Native assertions read back actual HWND rectangles and layered opacity, check
client-area content fit and intermediate motion frames, verify ordering and
stable HWND reuse, coordinate native InfoBar closing, exercise all 15 selected
surface IDs, long words, readable copy, reading hold, expiry, burst/STOP display,
50 create/dismiss cycles, geometry failure cleanup, and disposal during motion.
Captures assert an opaque
dark base; visual inspection exposed and corrected a transparent InfoBar base
and a native-frame inset before the final pass.

The work-area fixture contracts the reported usable area inside the real
monitor, including during an exit and immediately before another arrival. It
also queues protected entries when the area is too small, then restores them.
It never changes OS settings or pretends to exercise physical DPI changes.

All 26 Dark component renders were visually reviewed, including the transcript
and verification long-text stress captures. Native gallery stress covers every
surface's visible copy, 150% message/caption
text where present, long unbroken words/Unicode, reachable scroll extents,
theme foregrounds, status-glyph centers, transcript tail-follow versus reading
earlier words, and the committed banner. This is text-size stress, not a real
150% display-DPI test. Explicit renders capture only fixture controls.

Earlier signing-policy failures remain historical. These current executables
launched normally; no policy was disabled, signature bypass used or unrelated
process stopped. Failed intermediate audits were fixed and rerun. The native
control runner's exit code and its `control-tests.txt` must both be checked.

## Reproduce

```powershell
dotnet run --project PLUMA.UI/PopupStack.Tests/PopupStack.Tests.csproj --no-restore
dotnet run --project PLUMA.UI/SurfaceContracts.Tests/SurfaceContracts.Tests.csproj --no-restore
dotnet run --project PLUMA.UI/AudioVisualizer.Tests/AudioVisualizer.Tests.csproj --no-restore
./PLUMA.UI/check-surface-copy.ps1
./PLUMA.UI/preview-popup-stack.ps1 -Audit
./PLUMA.UI/preview-surfaces.ps1 -Export
dotnet build PLUMA.UI/SurfaceControls.Tests/SurfaceControls.Tests.csproj -p:Platform=x64 --no-restore -v:minimal
& ./PLUMA.UI/SurfaceControls.Tests/bin/x64/Debug/net8.0-windows10.0.19041.0/win-x64/SurfaceControls.Tests.exe
# Check $LASTEXITCODE and control-tests.txt beside that executable.
```

Restore dependencies first on a fresh checkout. Preview builds use the existing
unpackaged/self-contained gallery property; default deployment is unchanged.
Audit outputs are explicit local artifacts and are excluded from commits.

## Remaining acceptance evidence before wiring

P-01/P-02/P-04/P-05/P-10/P-14/P-15 have native fixture and pure-test evidence.
P-03 has coordinated exit/reflow evidence, but the full interactive middle,
oldest, newest dismissal sequence still merits review. The following are not
claimed as passed:

- P-06/P-07: physically reveal the auto-hide taskbar, toggle its configuration
  or restart Explorer, and confirm the edge remains usable. Current native
  read-back verifies the shell geometry and reservations, not a pointer hover.
- P-08/P-09: real other-DPI/negative-origin monitors, resolution changes and
  disconnection. Pure simulations and native bounded work-area changes pass.
- P-11: actual backend STOP/cancellation timing. The audit verifies priority
  feedback only; cancellation must occur independently before UI presentation.
- P-12: physical pointer/keyboard reading, scrolling and accessibility review.
  The host lifetime hold/release logic and transcript scrolling pass fixtures.
- P-13: changing the Windows animations setting. The host reads UISettings;
  the audit exercises the equivalent local motion-suppression path.

Keep the owner-approved dark style and placement fixed during these checks.
Resolve any failure before the separately scoped backend wiring phase.
