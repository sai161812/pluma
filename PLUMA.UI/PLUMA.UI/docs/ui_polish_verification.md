# UI polish verification — surfaces 22–26

Current all-surface formatting status is in [ui_formatting_review.md](ui_formatting_review.md).
It records the latest passing checks and the final native-launch signing block.
The owner has since specified dark-only appearance; current previews and
acceptance checks use Dark only. The counts and light/dark renders below are
historical evidence for their stated versions.

Date: 2026-10-18. Branch: `ui-polish`, tracking `origin/ui-polish`.
Environment: Windows build 26200, .NET SDK 10.0.401, .NET 8 target, Debug/x64.

## Scope

Added `LiveMessageFeed`, `CoreHealthIndicator`, `ToastNotification`,
`CriticalErrorDialog`, and `SetupWizard`, each with its own XAML/code-behind
pair. Supporting state lives in `LiveMessageBuffer.cs` and `SetupChecklist.cs`.
Each XAML file is registered exactly once in `PLUMA.UI.csproj`.

The owner directed surface 24 to follow similar existing notices. It uses an
in-app `InfoBar`, consistent with `PolicyBlockNotice`, rather than a Windows
Notification Center notification. The wizard uses an adapter-neutral OCR check
to respect the immutable master specification.

Approved surfaces 1–15 and 18–21, main navigation, application startup, and the
voice preview were preserved. Surfaces 16–17 remain intentionally skipped.
Generated test `bin`/`obj` directories are ignored; existing tracked application
build artifacts and unrelated workspace files are excluded from this change.

## Commands and results

Restore each test project with `dotnet restore <project>` first. Add
`-p:Platform=x64` for `SurfaceControls.Tests`.

```powershell
dotnet run --project PLUMA.UI/SurfaceContracts.Tests/SurfaceContracts.Tests.csproj --no-restore
# 15 checks passed.

dotnet build PLUMA.UI/SurfaceControls.Tests/SurfaceControls.Tests.csproj -p:Platform=x64 --no-restore -v:minimal
# Build succeeded. 0 Warning(s), 0 Error(s).

& ./PLUMA.UI/SurfaceControls.Tests/bin/x64/Debug/net8.0-windows10.0.19041.0/win-x64/SurfaceControls.Tests.exe
# 24 UI checks passed (written to control-tests.txt beside the test executable).

dotnet run --project PLUMA.UI/AudioVisualizer.Tests/AudioVisualizer.Tests.csproj --no-restore
# All audio visualizer checks passed (15 checks).

dotnet build PLUMA.UI/PLUMA.UI/PLUMA.UI.csproj -p:Platform=x64 --no-restore -v:minimal
# Build succeeded. 0 Warning(s), 0 Error(s).
```

`SurfaceContracts.Tests` links the production state classes. It checks exact
message/timestamp preservation, bounded retention, empty/clear behavior, pending
and failed capability checks, navigation gates, revocation, reset, and invalid
states.

`SurfaceControls.Tests` links the actual production XAML and code-behind into an
isolated WinUI application. It opens only its own temporary test window and
closes it after the checks; it has a 30-second watchdog. UI Automation button
peers exercise real clicks. Coverage includes empty/list transitions,
disconnected defaults, latency invalidation, actual light/dark resource changes,
notice severity, timer replacement, auto-dismiss, manual close and unload,
wizard gating and Continue requests, and recovery requests without false success.
The critical-error dialog remains open while the host verifies recovery.

Initial test-host resource initialization failed when referencing the main
executable project. The final isolated harness links production source directly,
matching the audio harness pattern, and passes. No production startup workaround
was added.

Full local outputs are in `output/ui-polish/{state-checks,control-checks,audio-checks,build}.txt`.

## Visual consistency review

The follow-up review rendered the actual existing and new controls in light and
dark themes at the host's native 125% display scaling. Eight PNGs were inspected:
Dashboard/status comparisons, Settings/setup comparisons, and the approval and
critical-error dialogs. These are test-owned XAML renders, not desktop captures.
Reference components are linked unchanged from production source.

| New surface | Existing visual reference | Result |
|---|---|---|
| Live message feed | Dashboard live messages | Same native subtitle/body/caption styles and list spacing; timestamps remain secondary. The host supplies the surrounding card. |
| Core health | Dashboard status text and approved InfoBadge mapping | Same native text/theme resources; compact dot/latency layout fits the component's ambient status role. |
| Notification | PolicyBlockNotice | Same native InfoBar layout, icon, severity fill, close button, and typography. |
| Critical error | RiskApprovalDialog | Matched its 440-pixel content width and 16-pixel spacing; same native dialog title and button treatment. |
| Setup | SettingsPage | Replaced hand-built checklist cards with the same Community Toolkit SettingsCard; matched 1000-pixel page limit, 32/24/32/32 padding, 24-pixel section spacing, title margin, and secondary description text. |

No changes were needed to the feed, health indicator, or notification styling.
The only product changes in this follow-up are `CriticalErrorDialog.xaml` and
`SetupWizard.xaml`. Existing approved components and runtime behavior are unchanged.
After the layout changes, all 24 UI, 15 state, and 15 audio checks passed again;
both the test host and main UI built with zero warnings/errors.

To reproduce the renders, build the UI harness as above and run:

```powershell
& ./PLUMA.UI/SurfaceControls.Tests/bin/x64/Debug/net8.0-windows10.0.19041.0/win-x64/SurfaceControls.Tests.exe --visual-review
```

PNGs are written under `visual-review` beside the test executable. The reviewed
copies are also available locally under `output/ui-polish/visual-review/`;
the follow-up assertion output is `output/ui-polish/style-review-checks.txt`.
The preview uses a theme page fill; native desktop Mica and compositor effects
remain outside RenderTargetBitmap verification.

## Remaining acceptance work

### Surfaces 16–17 implementation and current verification blocker

The owner authorized implementing the previously skipped perception surfaces.
`OcrMatchIndicator` uses an input-transparent accent outline and an Acrylic
callout matching the approved typography, spacing, and border resources.
`PostClickVerifyIndicator` follows the existing native InfoBar pattern.
The UI harness includes 12 additional runtime checks and light/dark perception
renders. Both the main UI and extended test host compile with zero warnings/errors.

Those new runtime checks have **not passed yet**. Windows Application Control
blocked `SurfaceControls.Tests.exe`; Code Integrity event 3077 reports that it
does not meet the enterprise signing requirements. Running the managed assembly
through the normal .NET host also exited at WinUI startup (0xC000027B), before
the new assertions ran. No security settings were changed. Older 24-check output
does not count as verification of surfaces 16–17. Owner approval of this recorded
limitation is pending; otherwise an approved test runner is required before
calling these surfaces accepted.

The existing backend IPC tests were run with Python 3.12.10:
`python -m pytest tests/unit/test_ipc.py -q --tb=short` → **2 passed in 5.09s**.
Source inspection also confirmed that the untracked capability matrix describes
a protocol that is not implemented: the actual Python Windows pipe uses message
boundaries, HMAC challenge/response, a per-user pipe name, and one request/reply
per connection. There is no current push event stream or JSON-RPC dispatcher.
Wiring must follow the code and add any missing event support explicitly.

### Subsequent owner-facing preview gallery

The owner requested appearance review before placement or wiring. An opt-in
`SurfaceGalleryWindow` now instantiates all 26 actual components using fixture
data. Its preview-only self-contained Windows App SDK build successfully ran
and exported 52 native light/dark renders, including surfaces 16–17. No signing
policy or system runtime registration was changed. See `surface_gallery.md`.

This provides real visual previews despite the earlier standalone test-launcher
block. It confirms construction and rendering; it does not retroactively mark
the 12 pending behavioral assertions as passed. Placement and wiring remain
undecided. The catalogue/state harness passes 17 checks and the existing audio
harness passes 15; the gallery build has zero warnings/errors.

This is UI component verification, not completion of Phase 14 or a release
acceptance claim. No backend, IPC, planner, policy, ledger, microphone, capture,
process termination, or installation behavior was added or simulated.

In a separately scoped integration task, a host must connect real redacted core
events on the UI thread, supply measured connection health, perform capability
checks with current-run correlation, handle recovery under core ownership, and
persist verified setup completion before navigating to Dashboard. Recovery
failure should update the error and explicitly re-enable retry when appropriate.

Manual review at 100% and 150% DPI, high contrast, full-window material behavior,
keyboard and screen-reader review, and end-to-end core failure/STOP/recovery
acceptance remain outstanding.
The Python regression suite was not run because no Python/backend code changed.
