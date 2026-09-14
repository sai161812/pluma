# PLUMA Phase 14 — UI Surfaces Reference

All surfaces wire directly to the resident core via `pluma.core.ipc` (named pipe / JSON-RPC).  
No surface requires polling — all state changes are event-driven from the core.

---

## Full-Screen Surfaces

### 1. Dashboard
**Purpose:** Primary command entry and live task view.  
**Data/Actions:** Text input bar, active task state badge, current route badge (FAST/SMART/DEEP/SCREEN), live message feed, recent ledger entries, core health indicator.  
**Wire:** `IPC → task_state`, `router.route()` result, `ActivityLedger` stream.

### 2. Settings
**Purpose:** Configure LLM paths, hotkeys, audio emulation, tool policy overrides.  
**Data/Actions:** Form fields bound to `config.yaml` and `PreferencesStore`; save action writes back via `SettingsContract`.  
**Wire:** `pluma/ui/settings_contract.py`, `pluma/config/loader.py`, `pluma/memory/preferences.py`.

### 3. History / Activity Ledger
**Purpose:** Browse all completed tasks.  
**Data/Actions:** Searchable list of task records — task ID, prompt, timestamp, final state (SUCCEEDED / FAILED / STOPPED), steps executed, redacted args.  
**Wire:** `pluma/memory/activity.py`, `ActivityViewContract`.

---

## Floating Popup Surfaces

### 4. Task Running Popup
**Purpose:** Compact overlay showing an active task is in progress.  
**Data/Actions:** Task ID, state (RUNNING / STOPPING / ROLLING_BACK), elapsed timer, dismiss on task end.  
**Wire:** `TaskSupervisor` state changes → IPC push.

### 5. Step Progress Popup
**Purpose:** Shows the multi-step planner advancing through tool calls.  
**Data/Actions:** Step N of M, current tool name, purpose string, spinner.  
**Wire:** `MultiStepOrchestrator` step events.

### 6. Route Badge Popup
**Purpose:** Briefly shows which execution route was chosen after a command.  
**Data/Actions:** Route name (FAST / SMART / DEEP / SCREEN), auto-hides after 2s.  
**Wire:** `Router.route()` result via IPC.

### 7. Tool Call Card
**Purpose:** Shows a tool executing in real time.  
**Data/Actions:** Tool name, sanitised arguments, live elapsed timer, risk class badge.  
**Wire:** `ToolRegistry.execute()` start event, `ToolSpec.risk_class`.

### 8. Tool Result Card
**Purpose:** Shows the outcome of a completed tool call.  
**Data/Actions:** Tool name, `ToolResult.factual_message`, verified badge (✓ / ✗), error code if failed.  
**Wire:** `ToolResult` payload from IPC.

### 9. Rollback Popup
**Purpose:** Visible while the system is undoing actions after a failure or STOP.  
**Data/Actions:** "Rolling back…" heading, list of recipes executing (e.g., "Restoring file…"), step-by-step progress.  
**Wire:** `RollbackEngine` recipe events, `TaskState.ROLLING_BACK`.

### 10. Conflict Alert Popup
**Purpose:** Warns user when a rollback cannot proceed automatically.  
**Data/Actions:** "Manual resolution required" message, current path, conflict path, action links.  
**Wire:** `ROLLBACK_CONFLICT` error payload from `RollbackEngine`.

---

## Voice / STT Surfaces

### 11. Voice Listening Animation
**Purpose:** Full-screen or floating animated indicator while the system is listening.  
**Data/Actions:** Microphone icon with animated waveform or pulse; active until VAD detects silence or hotkey released.  
**Wire:** `VoiceActivation` start event, `pluma/voice/activation.py`.

### 12. Live Transcription Overlay
**Purpose:** Shows speech being transcribed in real time.  
**Data/Actions:** Streaming text buffer updating character by character, finalized text highlighted.  
**Wire:** `STTAdapter` partial result stream, `pluma/voice/stt_adapter.py`.

### 13. Voice Committed Banner
**Purpose:** Confirms what the system understood and is now acting on.  
**Data/Actions:** Final transcript string, auto-hides and hands off to Route Badge.  
**Wire:** `VoicePipeline` final transcript → `Router`.

### 14. Voice Silence Timeout Indicator
**Purpose:** Shows that the VAD has detected silence and is about to commit.  
**Data/Actions:** Short progress bar or countdown; auto-commits on expiry.  
**Wire:** `VAD` silence event, `pluma/voice/vad.py`.

---

## OCR / Perception Surfaces

### 15. Screen Capture Flash
**Purpose:** Brief visual confirmation that a screen/window capture occurred.  
**Data/Actions:** Flash frame around target window or full screen, auto-dismisses.  
**Wire:** `WindowCapture.capture_window()` / `capture_region()` event.

### 16. OCR Match Indicator
**Purpose:** Shows which word the OCR engine matched and where it will click.  
**Data/Actions:** Matched word text, confidence score (0–1), desktop coordinates (x, y).  
**Wire:** `OcrResult.find_words()` result before click in `execute_click_ocr_text`.

### 17. Post-Click Verify Indicator
**Purpose:** Shows result of the mandatory post-click visual verification.  
**Data/Actions:** "Verified ✓" or "Unverified ✗", verification method (ocr_rescan), detail string.  
**Wire:** `ToolResult.verify_detail` → `VerifyResult`.

---

## Confirmation / Policy Surfaces

### 18. Risk Approval Dialog
**Purpose:** Blocks execution and requests explicit user approval for HIGH-risk tools.  
**Data/Actions:** Tool name, risk class, sanitised args, "Approve" and "Deny" buttons; denial returns `PERMISSION_DENIED`.  
**Wire:** `ConfirmationContract.request_confirmation()`, `pluma/ui/confirmations.py`.

### 19. Policy Block Notice
**Purpose:** Non-blocking notice when an action is rejected by a policy rule.  
**Data/Actions:** "Action blocked" label, matched rule, tool name.  
**Wire:** `PolicyEngine.evaluate()` → DENIED result.

---

## STOP / Cancellation Surfaces

### 20. Cancellation Animation
**Purpose:** Full visual feedback when STOP is triggered (hotkey or voice "stop").  
**Data/Actions:** Animated "Stopping…" overlay, task ID, elapsed time at cancellation.  
**Wire:** `CancellationToken.cancel()` event, `TaskState.STOPPING`.

### 21. Worker Termination Flash
**Purpose:** Brief confirmation that the isolated tool worker process was killed.  
**Data/Actions:** Worker PID, "Worker terminated" message, auto-hides.  
**Wire:** `TaskWorkerController._terminate_internal()` → Job Object terminate event.

---

## Status / Message Surfaces

### 22. Live Message Feed
**Purpose:** Scrolling real-time log of everything PLUMA says it is doing.  
**Data/Actions:** `ToolResult.factual_message` strings, orchestrator status lines, timestamps.  
**Wire:** All IPC `tool_result` and `status` events.

### 23. Core Health Indicator
**Purpose:** Small ambient indicator showing the resident core is connected.  
**Data/Actions:** Green/red dot, "Connected" / "Disconnected", IPC ping latency.  
**Wire:** `pluma/core/ipc.py` heartbeat.

### 24. Toast Notification
**Purpose:** One-line non-blocking info / warning pop-in.  
**Data/Actions:** Short message, severity level (info / warning / error), auto-dismiss.  
**Wire:** Generic IPC notification event.

### 25. Critical Error Dialog
**Purpose:** Blocking dialog on fatal failures — IPC down, unhandled crash.  
**Data/Actions:** Error message, optional stack trace, "Restart Core" button.  
**Wire:** `CrashRecovery`, IPC connection loss event.

---

## Onboarding Surface

### 26. Setup Wizard
**Purpose:** First-run check ensuring all system dependencies are present.  
**Data/Actions:** Checklist — Tesseract OCR, PyWinAuto / UIA, microphone access, local LLM path, hotkey confirmation. "Continue" unlocks the Dashboard.  
**Wire:** `pluma/config/loader.py` capability checks, `PreferencesStore`.
