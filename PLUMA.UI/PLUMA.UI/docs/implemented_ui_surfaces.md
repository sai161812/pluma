# PLUMA UI Surface Inventory

This document records the UI work currently present in the C# WinUI 3 project.

## Summary

- Total planned surfaces: **26**
- Implemented UI surface components: **26** (backend integration is separate; surfaces 16–17 have runtime verification pending)
- Intentionally skipped: **0** — the owner authorized surfaces 16 and 17
- Not started: **0** within the approved UI component scope
- Production namespace: `PLUMA.UI`
- Project: `PLUMA.UI/PLUMA.UI.csproj`
- Target framework: `.NET 8` / WinUI 3

Temporary preview windows are not production surfaces and are not included in the completed count.

## Implemented UI components

| Surface | UI surface | XAML | Code-behind | Notes |
|---:|---|---|---|---|
| 1 | Dashboard | `DashboardPage.xaml` | `DashboardPage.xaml.cs` | Main dashboard page. |
| 2 | Settings | `SettingsPage.xaml` | `SettingsPage.xaml.cs` | Settings page. |
| 3 | History / Activity Ledger | `HistoryPage.xaml` | `HistoryPage.xaml.cs` | History page. |
| 4 | Task Running Popup | `TaskRunningPopup.xaml` | `TaskRunningPopup.xaml.cs` | Compact task-running popup. |
| 5 | Step Progress Popup | `StepProgressPopup.xaml` | `StepProgressPopup.xaml.cs` | Step progress surface. |
| 6 | Route Badge Popup | `RouteBadgePopup.xaml` | `RouteBadgePopup.xaml.cs` | Route/status badge. |
| 7 | Tool Call Card | `ToolCallCard.xaml` | `ToolCallCard.xaml.cs` | Tool execution card. |
| 8 | Tool Result Card | `ToolResultCard.xaml` | `ToolResultCard.xaml.cs` | Tool result card. |
| 9 | Rollback Popup | `RollbackPopup.xaml` | `RollbackPopup.xaml.cs` | Rollback progress surface. |
| 10 | Conflict Alert Popup | `ConflictAlertPopup.xaml` | `ConflictAlertPopup.xaml.cs` | Rollback conflict alert. |
| 11 | Voice Listening Animation | `VoiceListeningRing.xaml` | `VoiceListeningRing.xaml.cs` | Animated voice ring. |
| 12 | Live Transcription Overlay | `LiveTranscriptionOverlay.xaml` | `LiveTranscriptionOverlay.xaml.cs` | Transcript visual component. |
| 13 | Voice Committed Banner | `VoiceCommittedBanner.xaml` | `VoiceCommittedBanner.xaml.cs` | Committed-state visual component. |
| 14 | Voice Silence Timeout Indicator | `VoiceSilenceTimeoutIndicator.xaml` | `VoiceSilenceTimeoutIndicator.xaml.cs` | Silence progress indicator. |
| 15 | Screen Capture Flash | `ScreenCaptureFlash.xaml` | `ScreenCaptureFlash.xaml.cs` | Dormant capture acknowledgement control. |
| 16 | OCR Match Indicator | `OcrMatchIndicator.xaml` | `OcrMatchIndicator.xaml.cs` | Input-transparent target outline and Acrylic callout; expires with supplied snapshot, at most three seconds. Runtime checks pending Application Control approval. |
| 17 | Post-Click Verify Indicator | `PostClickVerifyIndicator.xaml` | `PostClickVerifyIndicator.xaml.cs` | Native success/error InfoBar displaying supplied verifier evidence. Runtime checks pending Application Control approval. |
| 18 | Risk Approval Dialog | `RiskApprovalDialog.xaml` | `RiskApprovalDialog.xaml.cs` | Native WinUI `ContentDialog`. |
| 19 | Policy Block Notice | `PolicyBlockNotice.xaml` | `PolicyBlockNotice.xaml.cs` | Native WinUI `InfoBar`. |
| 20 | Cancellation Animation | `CancellationAnimation.xaml` | `CancellationAnimation.xaml.cs` | Cancellation feedback popup. |
| 21 | Worker Termination Flash | `WorkerTerminationFlash.xaml` | `WorkerTerminationFlash.xaml.cs` | Worker termination feedback popup. |
| 22 | Live Message Feed | `LiveMessageFeed.xaml` | `LiveMessageFeed.xaml.cs` | Empty by default; timestamped, bounded display of supplied factual messages. |
| 23 | Core Health Indicator | `CoreHealthIndicator.xaml` | `CoreHealthIndicator.xaml.cs` | Disconnected by default; theme status dot and supplied ping latency. |
| 24 | Toast Notification | `ToastNotification.xaml` | `ToastNotification.xaml.cs` | In-app native `InfoBar`, following the existing policy notice convention. |
| 25 | Critical Error Dialog | `CriticalErrorDialog.xaml` | `CriticalErrorDialog.xaml.cs` | Native `ContentDialog`; explicit host recovery request, optional sanitized details. |
| 26 | Setup Wizard | `SetupWizard.xaml` | `SetupWizard.xaml.cs` | Dependency, input, and review steps; Continue requires all five host-verified checks. |

Every completed production surface has a separate XAML file and code-behind file in the main `PLUMA.UI` project folder. The project uses explicit XAML `Page` entries with implicit Page items disabled so each active XAML file is registered once.

## Voice infrastructure

Surfaces 11–14 are composed inside one reusable host:

- `VoiceOverlay.xaml`
- `VoiceOverlay.xaml.cs`

`VoiceOverlay` remains the unified state coordinator and exposes the shared wiring properties:

- `VoiceState`
- `IsListening`
- `Amplitude`
- `IsAnimating`
- `FinalTranscript`
- `PartialTranscript`
- `SilenceProgress`

The approved voice states remain:

- `Hidden`
- `ListeningSilence`
- `ListeningSpeech`
- `SilenceTimeout`
- `Committed`

Supporting voice files:

- `VoiceOverlayState.cs` — approved state enum.
- `VoiceOverlayPreviewGenerator.cs` — mock preview state-cycle generator.
- `VoiceOverlayPreviewWindow.xaml` — preview window XAML.
- `VoiceOverlayPreviewWindow.xaml.cs` — preview window host and generator wiring.

Only one `VoiceOverlayPreviewWindow` is launched by `App.xaml.cs`.

## Future-wiring APIs

### Surface 11 — Voice Listening Animation

`VoiceListeningRing.xaml.cs` exposes:

- `Amplitude`
- `IsAnimating`

### Surface 12 — Live Transcription Overlay

`LiveTranscriptionOverlay.xaml.cs` exposes:

- `FinalTranscript`
- `PartialTranscript`

### Surface 14 — Voice Silence Timeout Indicator

`VoiceSilenceTimeoutIndicator.xaml.cs` exposes:

- `Progress`

`VoiceOverlay` forwards the unified `SilenceProgress` value to this component.

### Surface 15 — Screen Capture Flash

`ScreenCaptureFlash.xaml.cs` exposes:

- `Play()`

It performs visual feedback only and contains no capture integration.

### Surface 18 — Risk Approval Dialog

`RiskApprovalDialog.xaml.cs` exposes:

- `ToolName`
- `RiskClass`
- `SanitizedArguments`
- `ApprovalRequested` event
- `DenialRequested` event

It is a native `ContentDialog`. Deny is the safe default, and cancellation/close raises the denial event.

### Surface 19 — Policy Block Notice

`PolicyBlockNotice.xaml.cs` exposes:

- `ToolName`
- `MatchedRule`
- `IsNoticeOpen`
- `ShowNotice()`
- `HideNotice()`

It is a non-blocking native `InfoBar` with error severity.

### Surface 20 — Cancellation Animation

`CancellationAnimation.xaml.cs` exposes:

- `Heading`
- `Message`
- `TaskId`
- `ElapsedTime`
- `IsActive`
- `Show()`
- `Hide()`

### Surface 21 — Worker Termination Flash

`WorkerTerminationFlash.xaml.cs` exposes:

- `Heading`
- `Message`
- `WorkerPid`
- `ElapsedTime`
- `IsOpen`
- `Show()`
- `Hide()`

Auto-dismiss timing belongs to a preview or future host, not the production control.

## Perception surface contracts

### Surface 16 — OCR Match Indicator

- `ShowMatch(sanitizedText, confidence, hostBounds, desktopPosition, snapshotExpiresAt)` and `HideMatch()`; read-only `IsMatchVisible`.
- `hostBounds` are host-local logical pixels (DIPs), supplied after the host verifies the snapshot/window identity and current DPI/geometry. Desktop coordinates are display metadata only and may be negative on multiple monitors.
- Rejects blank text, invalid confidence/geometry, expired snapshots, and targets outside the host. Automatically clears on expiry or unload. Display lifetime never exceeds three seconds or the supplied expiry.
- The target outline and callout never intercept input and never click anything. The host must also hide the marker whenever the target window or snapshot changes. Actual OCR targeting and action verification remain exclusively in the existing backend pipeline.

### Surface 17 — Post-Click Verify Indicator

- `ShowResult(verified, verificationMethod, sanitizedDetail)` and `HideResult()`.
- Defaults closed. Displays supplied verification evidence with native Success/Verified or Error/Unverified severity; missing method cannot display success.
- A click event itself never counts as verification. The future host must supply the backend verifier's actual result and already-redacted detail.
- Both new controls compile. Their newly added runtime assertions and visual renders are currently blocked by the machine's Application Control policy; see the verification notes.

## Surfaces 22–26 — wiring contracts

### Surface 22 — Live Message Feed

- `AppendMessage(sanitizedMessage, timestamp)` and `ClearMessages()`, on the UI thread.
- Messages are supplied by deterministic executor/status events, with no rewriting.
- `LiveMessageBuffer` retains the latest 200 rows in memory; it does not replace or write the Activity Ledger.
- Native `ListView` handles scrolling; new events do not force the user away from earlier rows.

### Surface 23 — Core Health Indicator

- `IsConnected` and `PingLatencyMs` dependency properties.
- Starts disconnected, with no latency measurement; disconnect invalidates old latency.
- No heartbeat loop or IPC client. The host must supply connection changes and fresh measurements.

### Surface 24 — Toast Notification

- `Show(sanitizedMessage, severity, duration)` and `Hide()`; read-only `IsOpen`.
- Native in-app `InfoBar`, matching existing similar notices as directed by the owner.
- This resolves the older shell-notification recommendation in the style mapping for this surface; no Windows Notification Center integration is added.
- Defaults to four seconds; replacement resets the timer. Closing, hiding, or unloading stops the timer.
- Blank content stays hidden. No startup or idle timer.

### Surface 25 — Critical Error Dialog

- `ErrorMessage`, `SanitizedDetails`, `CanRestart`, and `RestartRequested`.
- Close is the safe default. Restart is disabled until the host enables it.
- Restart raises one request and disables repeat clicks. The dialog stays visible until the host verifies recovery and hides it, or the user closes it.
- The host supplies `XamlRoot` before `ShowAsync()` and only already-redacted technical details.

### Surface 26 — Setup Wizard

- `SetCheckResult(id, state, sanitizedDetail)`, `RecheckRequested`, and `ContinueRequested`.
- Checks: OCR runtime, UI Automation, local model path, microphone access, and command/STOP hotkeys.
- Uses the same Community Toolkit `SettingsCard` and page spacing as the approved Settings page.
- The OCR label is adapter-neutral, following the master specification rather than requiring Tesseract.
- All checks start pending. Failed or pending checks block progress; later failures revoke Continue.
- Check again invalidates previous results. The host must correlate check results with the current check run.
- The host owns real capability checks, preference persistence, and Dashboard navigation after verification. No installation, microphone activation, shell calls, model loading, or hotkey registration occurs in the wizard.

## Verification scope

The new components have dedicated state and WinUI control harnesses under `../SurfaceContracts.Tests` and `../SurfaceControls.Tests`. See `ui_polish_verification.md` for commands, results, and remaining integration checks.

This inventory records UI component implementation. It does not assert that Phase 14 or the release gates in `PLUMA_ACCEPTANCE_TESTS.md` are complete. IPC integration and end-to-end acceptance remain separate work.

## Preview and launch notes

The following are preview-only or obsolete and are not production surfaces:

- `VoiceOverlayPreviewWindow` — retained and approved for the voice preview.
- Stop Surfaces preview host — removed after preview validation.
- Safety Surfaces preview host — removed after preview validation.
- Screen Capture Flash preview host — not implemented or launched.

Current application launch should retain the main `MainWindow` and the approved `VoiceOverlayPreviewWindow` only.

No Python, IPC, backend, OCR, capture, process termination, or mock service integration was added to the UI surface controls.

## Continuation checklist

For the next workspace:

1. Preserve all completed surface files listed above.
2. Do not modify approved Surfaces 1–15 or 18–21 while beginning new work.
3. Run and visually inspect the new surfaces 16–17 in an approved WinUI test environment; their runtime gate is currently pending, not passed.
4. Wire Surfaces 22–26 to real core events in a separately scoped integration task; retain their disconnected, pending, or hidden defaults until evidence is supplied.
5. Update `PLUMA.UI.csproj` with exactly one XAML registration per new production XAML file.
