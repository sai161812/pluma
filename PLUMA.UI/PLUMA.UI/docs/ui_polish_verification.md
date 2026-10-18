# UI polish verification — surfaces 22–26

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

## Remaining acceptance work

This is UI component verification, not completion of Phase 14 or a release
acceptance claim. No backend, IPC, planner, policy, ledger, microphone, capture,
process termination, or installation behavior was added or simulated.

In a separately scoped integration task, a host must connect real redacted core
events on the UI thread, supply measured connection health, perform capability
checks with current-run correlation, handle recovery under core ownership, and
persist verified setup completion before navigating to Dashboard. Recovery
failure should update the error and explicitly re-enable retry when appropriate.

Manual review at 100%, 125%, and 150% DPI, high contrast, keyboard and screen-reader
review, and end-to-end core failure/STOP/recovery acceptance remain outstanding.
The Python regression suite was not run because no Python/backend code changed.
