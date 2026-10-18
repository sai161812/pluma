# UI surface gallery

This is an owner-review catalogue of the actual 26 WinUI components, shown
one at a time. The owner has specified a shared bottom-right popup stack in
[popup_placement_contract.md](popup_placement_contract.md). This catalogue
shows individual components. Its **Desktop stack preview** button opens the
shared native host for placement and motion review. All displayed task,
voice, OCR, health, notification, and setup values are preview fixtures.
The owner specified dark-only appearance. The app and all previews default to
Dark; there is no theme selector or light-version review requirement.

## Open the native gallery

From the repository root:

```powershell
./PLUMA.UI/preview-surfaces.ps1
```

The script builds with `SurfaceGalleryPreview=true` into
`output/ui-gallery-preview/` and opens `PLUMA.UI.exe --surface-gallery`.
This preview-only MSBuild property selects unpackaged, self-contained Windows
App SDK deployment, avoiding the missing registered deployment runtime on this
machine. It does not install a runtime, change security settings, or change the
default production build. Restore project dependencies first on a fresh checkout.

The optional Visual Studio **PLUMA.UI (Surface Gallery)** launch profile opens
that same previously built executable. Normal app launch opens MainWindow;
the legacy microphone preview is opt-in with `--voice-preview`.

Use the numbered picker to inspect any surface and the state buttons to
inspect variants, all in Dark. The gallery starts
at surface 16. Its marker intentionally expires after three seconds; use the
replay button to show it again. Surface 17 offers Verified and Unverified states.

Native dialogs 10, 18 and 25 open from preview buttons. Conflict, approval and restart controls
perform no real operation. Setup checks can be set to sample available or failed
values without inspecting the machine or saving preferences. The voice surface
uses the already approved voice host without opening the microphone.

## Export images for review

```powershell
./PLUMA.UI/preview-surfaces.ps1 -Export
```

After rendering completes, open `output/ui-surface-gallery/index.html` to browse
all 26 actual dark-theme WinUI PNGs. Each PNG is a still frame;
use the native gallery for animations, scrolling, and sample state changes.
Surface 15's exported image shows the documented peak of its capture flash.

Only explicit export writes images. The exporter captures its own preview
controls, not the desktop or other windows. Export work is owned by the gallery
window and is cancelled when it closes. The gallery does not connect to IPC,
start the backend, run tools, capture audio, perform OCR, or terminate workers.

## Verification

For the latest all-surface formatting pass, see
[ui_formatting_review.md](ui_formatting_review.md). The component baseline
exported 26 Dark renders with **195 passing formatting checks**. The subsequent
lower-placement/class-size refinement builds, but its fresh executable is again
blocked by Windows Application Control; see
[popup_placement_refinement.md](popup_placement_refinement.md). No security policy
was changed. The export runs `SurfaceGalleryAudit.cs`, writes
`formatting-checks.txt` and long-text `stress-*.png`, and fails on layout/copy
assertions. Its 150% text-size stress does not change OS settings or validate
physical display scaling. Preview actions are disabled while export runs.

- Preview build: zero warnings, zero errors.
- State/catalogue harness: 30 checks passed, including every surface ID 1–26
  exactly once and readable popup-copy formatting.
- Native control runner: **35 UI checks passed**, including surfaces 16/17.
- All-surface current output: `output/surface-gallery-final-audit/`.
- Physical DPI/accessibility and backend acceptance remain separate checks.

## Review the desktop stack

```powershell
./PLUMA.UI/preview-popup-stack.ps1
./PLUMA.UI/preview-popup-stack.ps1 -Audit
```

The first command opens a fixture controller for all 15 participating surface
IDs. Use Burst, Long message, dismissal controls and the local motion checkbox.
Voice 11-14 shares one entry; task/tool updates keep their stable identity.
The audit writes its own timestamped output directory and exercises native
positions, opacity, expiry, overflow and cleanup. Controls are disabled while an
audit is running. All fixture work is owned by the controller and cancelled
when it closes. Normal startup does not create fixture popups.

Current placement checks and remaining native/physical cases are in
[popup_placement_refinement.md](popup_placement_refinement.md). Backend wiring is
still a separate phase.
