# PLUMA Phase 14 — UI Surfaces Reference

Owner placement direction (2026-10-18): surfaces 4-9, 11-14, 17, 19-21, and 24
share a bottom-right stack, newest below older entries, with comfortable edge
clearance, smooth reflow/exit, and auto-hide taskbar handling. The full contract
and acceptance cases are in
[popup_placement_contract.md](popup_placement_contract.md). Existing dark styling
is retained. The shared desktop host is implemented; native fixture evidence
and remaining physical/interactive checks are in
[popup_stack_verification.md](popup_stack_verification.md). Surface purposes and
wiring references below remain future integration references.

Owner refinement (2026-10-19): lower the stack while the taskbar is hidden,
glide up/down with reveal/hide, and keep identical sizes within each notification
class. The integration now passes 661 hosted native popup checks, 195 formatting
checks and 35 control checks. Local signing restrictions and remaining physical
Windows 11 acceptance are recorded in
[ui_integration_review.md](ui_integration_review.md). See
[popup_placement_refinement.md](popup_placement_refinement.md) before wiring.

These are intended surface contracts, not a claim that every surface is wired.
The resident uses authenticated per-user Windows message-mode named pipes with
bounded JSON messages, not JSON-RPC. P15 defines the [v1 contract
catalog](../../../docs/completion/p15_protocol_v1.md); P16 binds material approval,
P17 guarded text submission/independent STOP, and P18 E87-E91 factual saved/live
readback, the message panel and shared notification stack. Connection latency
comes from measured readback; there is no push stream or invented capability
health. Voice, history/undo, settings, extended health and perception retain
their later milestone gates. [E91](../../../docs/completion/p18_live_runtime.md)
records exact tested source and native-versus-fixture boundaries.

---

## Full-Screen Surfaces

### 1. Dashboard
**Purpose:** Primary command entry and live task view.  
**Data/Actions:** Text input bar, active task state badge, current route badge (FAST/SMART/DEEP/SCREEN), live message feed, recent ledger entries, core health indicator.  
**Wire:** P17 CommandController owns typed submission/priority STOP and persisted terminal readback; P18 E91 adds actual current activity, bounded saved executor/task messages and measured connection readback. See [command wiring](wiring_command_submission.md) and [event/readback wiring](wiring_event_feed.md).

### 2. Settings
**Purpose:** Read actual local configuration and edit supported settings.  
**Data/Actions:** The P21 bounded page edits `max_plan_steps` through typed settings query/save, exact revision, shared command/STOP ownership and material confirmation. Cancel discards the draft; Reload reads persisted/effective values. Saved changes explicitly require Core restart. Model paths, hotkeys, activation, privacy defaults and policy are read-only until their lifecycle gates pass. No audio-emulation or safety-bypass toggle is exposed.  
**Wire:** Native `MainWindow.NavigateSettings`, `SettingsPage`, `SettingsController`, `CoreSettingsProtocol`; backend `SettingsStore` JSON v1, registered `save_settings` and independent ledger/verifier. `pluma/ui/settings_contract.py` remains an abstract alternate-host boundary, not a second native implementation.

### 3. History / Activity Ledger
**Purpose:** Browse all completed tasks.  
**Data/Actions:** Searchable list of task records — task ID, prompt, timestamp, final state (SUCCEEDED / FAILED / STOPPED), steps executed, redacted args.  
**Wire:** `pluma/memory/activity.py`, `ActivityViewContract`.

---

## Floating Popup Surfaces

### 4. Task Running Popup
**Purpose:** Compact overlay showing an active task is in progress.  
**Data/Actions:** Task ID, state (RUNNING / STOPPING / ROLLING_BACK), elapsed timer, dismiss on task end.  
**Wire (P18 E91):** authenticated `runtime_query` from the task-owned state mirror, observed by the shell-owned RuntimeController; no IPC push.

### 5. Step Progress Popup
**Purpose:** Shows the multi-step planner advancing through tool calls.  
**Data/Actions:** Step N of M, current tool name, purpose string, spinner.  
**Wire (P18 E91):** validated plan revision/selected step from FAST/SMART orchestration through runtime readback. No planner-written purpose enters Activity copy.

### 6. Route Badge Popup
**Purpose:** Briefly shows which execution route was chosen after a command.  
**Data/Actions:** Route name (FAST / SMART / DEEP / SCREEN), auto-hides after 2s.  
**Wire:** `Router.route()` result via IPC.

### 7. Tool Call Card
**Purpose:** Shows a tool executing in real time.  
**Data/Actions:** Tool name, sanitised arguments, live elapsed timer, risk class badge.  
**Wire (P18 E91):** actual registry/owned-worker entry, verification/recording phases, effective risk and redacted bounded arguments via runtime readback. Dispatch alone does not mean executing.

### 8. Tool Result Card
**Purpose:** Shows the outcome of a completed tool call.  
**Data/Actions:** Tool name, `ToolResult.factual_message`, verified badge (✓ / ✗), error code if failed.  
**Wire:** `ToolResult` payload from IPC.

### 9. Rollback Popup
**Purpose:** Visible while the system is undoing actions after a failure or STOP.  
**Data/Actions:** "Rolling back…" heading, list of recipes executing (e.g., "Restoring file…"), step-by-step progress.  
**Wire (P18 E91):** RollbackEngine selected inverse and ROLLING_BACK runtime state. Progress remains indeterminate until saved inverse/cleanup verification establishes its outcome.

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
**Wire (P18 E91):** exact scoped saved `action_verification_query` proof, matched to the saved action flag before atomic publication. Historical absence remains unavailable.

---

## Confirmation / Policy Surfaces

### 18. Risk Approval Dialog
**Purpose:** Blocks execution and requests explicit user approval for HIGH-risk tools.  
**Data/Actions:** Tool name, risk class, sanitised args, "Approve" and "Deny" buttons; denial returns `PERMISSION_DENIED`.  
**Wire:** `ConfirmationController` and `NativeConfirmationPresenter` connect the native dialog to authenticated typed pending/decision/disconnect contracts and the actual policy broker. E85 verifies exact literal material display, Deny default and fail-closed STOP/expiry/close; see [material approval wiring](wiring_material_confirmations.md).

### 19. Policy Block Notice
**Purpose:** Non-blocking notice when an action is rejected by a policy rule.  
**Data/Actions:** "Action blocked" label, matched rule, tool name.  
**Wire:** `PolicyEngine.evaluate()` → DENIED result.

---

## STOP / Cancellation Surfaces

### 20. Cancellation Animation
**Purpose:** Full visual feedback when STOP is triggered (hotkey or voice "stop").  
**Data/Actions:** Animated "Stopping…" overlay, task ID, elapsed time at cancellation.  
**Wire:** P17 MainWindow presents actual command STOP request/acknowledgement facts through the existing shared popup host. Cleanup/terminal evidence stays authoritative; broader hotkey/voice/event projection remains with the later surface wiring milestones.

### 21. Worker Termination Flash
**Purpose:** Brief confirmation that the isolated tool worker process was killed.  
**Data/Actions:** Worker PID, "Worker terminated" message, auto-hides.  
**Wire (P18 E91):** runtime readback of verified PLUMA-owned worker absence, exact task/PID/creation time and exit code. Neither a Job terminate call nor resource release alone is sufficient.

---

## Status / Message Surfaces

### 22. Live Message Feed
**Purpose:** Scrolling real-time log of everything PLUMA says it is doing.  
**Data/Actions:** `ToolResult.factual_message` strings, orchestrator status lines, timestamps.  
**Wire (P18 E91):** bounded factual E87 event/readback entries, incrementally applied to LiveMessageFeed. Unchanged polls do not rebind or force scrolling.

### 23. Core Health Indicator
**Purpose:** Small ambient indicator showing the resident core is connected.  
**Data/Actions:** Green/red dot, "Connected" / "Disconnected", IPC ping latency.  
**Current wire (P18 E91):** status on load/Refresh plus measured shell-owned runtime connection readback. This is connection/latency only; extended worker/model/device/capability health remains P22.

### 24. Toast Notification
**Purpose:** One-line non-blocking info / warning pop-in.  
**Data/Actions:** Short message, severity level (info / warning / error), auto-dismiss.  
**P18 E87–E91:** committed task events trigger independent terminal/history readback and deterministic notices through EventFeedController, EventNoticePresentation and the existing PopupStackHost. Combined shell/backend burst, reconnect, STOP, navigation and shutdown checks are recorded in [E91](../../../docs/completion/p18_live_runtime.md). See [event feed contract](wiring_event_feed.md); P25 physical review remains separate.

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
