# UI surface gallery

This is an owner-review catalogue of the actual 26 WinUI components. It is not
a proposal for where they should appear in the product. All displayed task,
voice, OCR, health, notification, and setup values are preview fixtures.

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
that same previously built executable. The normal app launch path is unchanged.

Use the numbered picker to inspect any surface, the Theme picker to choose
System/Light/Dark, and the state buttons to inspect variants. The gallery starts
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
all 52 actual WinUI PNGs (26 surfaces × light/dark). Each PNG is a still frame;
use the native gallery for animations, scrolling, and sample state changes.
Surface 15's exported image shows the documented peak of its capture flash.

Only explicit export writes images. The exporter captures its own preview
controls, not the desktop or other windows. Export work is owned by the gallery
window and is cancelled when it closes. The gallery does not connect to IPC,
start the backend, run tools, capture audio, perform OCR, or terminate workers.

## Verification

For the latest all-surface formatting pass, see
[ui_formatting_review.md](ui_formatting_review.md). The current development
executable is blocked by Windows Application Control signing requirements;
the earlier render counts below must not be treated as final formatting passes.
On an approved runner, export also runs `SurfaceGalleryAudit.cs`, writes
`formatting-checks.txt` and long-text `stress-*.png`, and fails on layout/copy
assertions. Its 150% text-size stress does not change OS settings or validate
physical display scaling. Preview actions are disabled while export runs.

- Preview build: zero warnings, zero errors.
- State/catalogue harness: 17 checks passed, including every surface ID 1–26
  exactly once.
- Gallery export: 52 component renders completed, recorded in
  `output/ui-surface-gallery/gallery-report.txt`.
- This confirms component construction/rendering for the review catalogue.
  It is not a claim that the previously blocked UI behavior assertions passed,
  nor that placement, DPI/accessibility, or backend acceptance is complete.

The owner should review appearance first. Placement and wiring remain undecided.
