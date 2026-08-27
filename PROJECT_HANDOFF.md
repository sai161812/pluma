# PROJECT HANDOFF & TECHNICAL CONTINUITY RECORD

> **CRITICAL PERMANENT DIRECTIVE FOR ALL AGENTS**
>
> `PROJECT_HANDOFF.md` is the **authoritative, permanent live save-state** for PLUMA.
>
> Whenever you finish any phase, before considering that phase complete:
> 1. Verify the work you implemented (run full test suite and phase gate checks).
> 2. Update `PROJECT_HANDOFF.md` to reflect the new verified project state.
> 3. Record the completed phase, new modules, and important changes.
> 4. Record any unresolved issues or known limitations.
> 5. Record any important architectural decisions introduced.
> 6. Record the next phase / current objective.
> 7. Record the **exact next action** another agent should take.
> 8. Remove or correct information that is no longer true.
>
> Assume that at any moment the current model, conversation, session, or account may disappear permanently. A incoming agent must be able to resume development safely using only:
> 1. The existing repository,
> 2. The specification files (`PLUMA_MASTER_SPEC.md`, `AGENTS.md`, `PLUMA_BUILD_PLAN.md`, `PLUMA_ACCEPTANCE_TESTS.md`, `PLUMA_TECH_STACK.md`),
> 3. This `PROJECT_HANDOFF.md` file.

---

## 1. Project Overview & Mission

**PLUMA** is a fully local, voice-first Windows 11 AI desktop assistant engineered with safety, bounded execution, and zero unnecessary runtime overhead at its core.

### Core Immutable Principles
1. **Lightweight Resident Core**: The background process starts and idles without loading LLM, STT, OCR, screen capture loops, or GPU inference.
2. **Unified Voice & Text Pipeline**: Voice is mandatory and enters the identical `PlumaRequest` pipeline, router, policy, tool execution, verification, and ledger path as text (`InputMode` enum only records source).
3. **Deterministic Typed Tools as Execution API**: Natural language is never an execution API. Every action is a registered, typed `ToolSpec`.
4. **Hierarchical Automation Priority**: Native/Application APIs $\rightarrow$ Controlled PowerShell/CLI $\rightarrow$ UI Automation (UIA) $\rightarrow$ Stable Keyboard/Input $\rightarrow$ Targeted OCR $\rightarrow$ Raw coordinates (strictly last resort).
5. **Postcondition Verification**: Every state-changing action has an explicit postcondition and must read it back before reporting success.
6. **Reversibility & Undo Evidence**: Every reversible action captures safe pre-state into an `UndoRecord` before executing.
7. **Task Capsule & Job Object Containment**: Every command is one `TaskCapsule` owned by one `TaskSupervisor`. Spawned subprocesses are assigned to Windows Job Objects (`JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`).
8. **Global STOP Precedence**: Setting the atomic stop latch immediately rejects all new tool steps, replans, or worker starts. Cleanup strictly avoids touching pre-existing user resources.
9. **Factual Activity Ledger**: All audit history in SQLite is deterministic, template-generated factual data, never LLM hallucination.
10. **Zero Invented UI**: UI is functional contract-based until the project owner provides visual styling direction.

---

## 2. Specification & Reference Documents

| Document | Authority & Scope |
|----------|-------------------|
| [`PLUMA_MASTER_SPEC.md`](file:///D:/Workspace/DEVEL/PLUMA/PLUMA_MASTER_SPEC.md) | **Authoritative product and engineering specification.** Read before making architectural changes. |
| [`AGENTS.md`](file:///D:/Workspace/DEVEL/PLUMA/AGENTS.md) | **Mandatory safety and architecture contract** binding all coding agents. |
| [`PLUMA_BUILD_PLAN.md`](file:///D:/Workspace/DEVEL/PLUMA/PLUMA_BUILD_PLAN.md) | Ordered implementation phases (Phase 0 through Phase 14). |
| [`PLUMA_ACCEPTANCE_TESTS.md`](file:///D:/Workspace/DEVEL/PLUMA/PLUMA_ACCEPTANCE_TESTS.md) | Objective release gates and verification criteria. |
| [`PLUMA_TECH_STACK.md`](file:///D:/Workspace/DEVEL/PLUMA/PLUMA_TECH_STACK.md) | Approved runtime libraries, adapters, and technology stack. |

---

## 3. Technology Stack & Constraints

- **Language & Runtime**: Python 3.12+ (64-bit Windows 11).
- **Core Frameworks**: `pydantic` (v2 schemas), `ctypes` (Win32 API integration), `sqlite3` (WAL mode, async worker thread), `multiprocessing.connection` (local IPC named pipes).
- **Automation Adapters**:
  - Native Win32: `ctypes` `user32`/`kernel32`/`gdi32` (window management, process info, display rects).
  - Shell: `subprocess` with Windows Job Objects and bounded timeouts (`PowerShellAdapter`).
  - UIA: `pywinauto` (UIA backend, lazy import inside methods).
  - Input: `SendInput` ctypes with modifier safety & coordinate bounds checking (`InputAdapter`).
  - Screen: targeted window/rect GDI capture with headless fallback (`ScreenAdapter`).
- **Perception & Models** (lazy/on-demand only in later phases):
  - Audio/STT: `whisper.cpp` / `pywhispercpp` (Phase 6).
  - OCR: `PaddleOCR` / ONNX Runtime (Phase 8).
  - Local Planner: `llama.cpp` (Phase 9).
- **Testing**: `pytest`, `pytest-timeout`, `pyyaml`.

---

## 4. Phase Roadmap & Completion Status

| Phase | Description | Status | Test Count |
|---|---|---|---|
| **Phase 0** | Freeze contracts, schemas, SQLite baseline, benchmarks, golden corpus | **COMPLETED** | 65 |
| **Phase 1** | Resident Core, Task Capsule, Windows Job Objects, atomic STOP sequence | **COMPLETED** | 82 (cumul.) |
| **Phase 2** | Typed tool framework, initial 19 tools, postcondition verifiers, ledger integration | **COMPLETED** | 101 (cumul.) |
| **Phase 3** | Deterministic FAST route, Router, Fast Orchestrator, clipboard & window tools | **COMPLETED** | 220 (cumul.) |
| **Phase 4** | Windows Automation Adapters (Native Win32, PowerShell, UIA, Input, Screen capture) | **COMPLETED** | 246 (cumul.) |
| **Phase 5** | Activity Ledger completion, redaction engine, reverse-order rollback | **COMPLETED** | 266 (cumul.) |
| **Phase 6** | Mandatory voice path (push-to-talk, VAD, whisper.cpp on-demand) | **COMPLETED** | 294 (cumul.) |
| **Phase 7** | UIA perception worker (ScreenElement semantic grounding, snapshot TTL) | **COMPLETED** | 314 (cumul.) |
| **Phase 8** | Targeted OCR fallback (PaddleOCR/ONNX region-only) | **COMPLETED** | 339 (cumul.) |
| **Phase 9** | Replaceable local planner (llama.cpp on-demand manager, grammar constraints) | **COMPLETED** | 365 (cumul.) |
| **Phase 10** | Bounded multi-step orchestration (execute-observe-replan loop, replan limits) | **COMPLETED** | 384 (cumul.) |
| **Phase 11** | Policy engine, risk classifications, single-operation elevation broker | **COMPLETED** | 399 (cumul.) |
| **Phase 12** | Latency and quality benchmark tuning, leak testing | **COMPLETED** | **405 (cumul.)** |
| **Phase 13** | Packaging, `%LOCALAPPDATA%` isolation, crash recovery | **NEXT UP** | Pending |
| **Phase 14** | Owner-directed UI implementation | Blocked on Owner Design | Pending |

---

## 5. Current Verified Implementation Details (Phases 0–11)

### Phase 0: Schema Contracts & Storage Foundation
- [`pluma/brain/schemas.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/brain/schemas.py): `RouteMode` (`FAST`, `SCREEN`, `SMART`, `DEEP`), `PlanMode`, `ToolCall`, `Plan` with hard cap step validation ($N \le 20$).
- [`pluma/core/request.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/core/request.py): `PlumaRequest`, `InputMode` (`TEXT`, `VOICE`), `RequestID` validation.
- [`pluma/core/cancellation.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/core/cancellation.py): `CancellationToken`, `StopReason`, `TaskCancelledError`.
- [`pluma/memory/db.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/memory/db.py): SQLite with WAL mode, busy timeout, queued async background writer loop for crash resiliency.

### Phase 1: Resident Core & Process Containment
- [`pluma/core/job_object.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/core/job_object.py): Win32 `CreateJobObjectW`, `SetInformationJobObject` setting `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`, `AssignProcessToJobObject`.
- [`pluma/core/ownership.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/core/ownership.py): `OwnershipRegistry` tracking PID creation timestamps via `GetProcessTimes` to protect against PID reuse.
- [`pluma/core/task_supervisor.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/core/task_supervisor.py): Complete task state machine with reverse rollback and Job Object termination.
- [`pluma/core/ipc.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/core/ipc.py): Local-only Windows named pipe `IpcServer` / `IpcClient`.
- [`pluma/core/resident.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/core/resident.py): Resident daemon with Win32 `RegisterHotKey` loop and push-to-talk integration.

### Phase 2: Typed Tool Framework & Initial Tools
- [`pluma/tools/base.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/tools/base.py): `ToolSpec`, `ToolResult`, `VerifyResult`, `RiskClass`, `AdapterPriority`.
- [`pluma/tools/registry.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/tools/registry.py): `ToolRegistry` with validation, cancellation checks, policy evaluations, pre-state capture, execution, verification, and ledger writes.
- Deterministic Tool Suites: `files.py`, `apps.py`, `windows.py`, `audio.py`, `system.py`, `clipboard.py`.

### Phase 3: Deterministic FAST Route & Orchestration
- [`pluma/core/router.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/core/router.py): Regex/pattern classifier routing all golden FAST commands directly without LLM/OCR.
- [`pluma/core/orchestrator.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/core/orchestrator.py): Command lifecycle coordinator.

### Phase 4: Windows Automation Adapters
- [`pluma/adapters/base.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/adapters/base.py): Common error hierarchy and immutable data models.
- [`pluma/adapters/win32.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/adapters/win32.py): Native Win32 window and process management.
- [`pluma/adapters/powershell.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/adapters/powershell.py): Bounded PowerShell adapter with Job Object containment, timeout limits, and instant cancellation polling loop.
- [`pluma/adapters/uia.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/adapters/uia.py): Lazy-loading UI Automation adapter with HWND pre-validation.
- [`pluma/adapters/input.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/adapters/input.py): `SendInput` ctypes with modifier safe release.
- [`pluma/adapters/screen.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/adapters/screen.py): Targeted window/rect GDI screen capture with headless fallback.

### Phase 5: Activity Ledger, Redaction & Rollback Engine
- [`pluma/memory/activity.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/memory/activity.py): Complete `ActivityLedger` write path and `ActivityQuery` read path.
- [`pluma/memory/redaction.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/memory/redaction.py): Deterministic sensitive-value redaction.
- [`pluma/memory/preferences.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/memory/preferences.py): `PreferencesStore` for user settings.
- [`pluma/memory/aliases.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/memory/aliases.py): `AliasStore` for command aliases.
- [`pluma/memory/routines.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/memory/routines.py): `RoutineStore` for multi-step routines.
- [`pluma/rollback/recipes.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/rollback/recipes.py): `RollbackRecipes` inverse operations.
- [`pluma/rollback/engine.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/rollback/engine.py): `RollbackEngine` reverse-order execution.

### Phase 6: Mandatory Voice Path
- [`pluma/voice/vad.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/voice/vad.py): Lightweight `EnergyVAD` calculation of RMS energy for 16-bit 16kHz PCM audio.
- [`pluma/voice/capture.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/voice/capture.py): `AudioCapture` managing microphone recording with lazy-loaded `sounddevice`.
- [`pluma/voice/stt_adapter.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/voice/stt_adapter.py): `WhisperSttAdapter` for on-demand `whisper.cpp` inference.
- [`pluma/voice/lifecycle.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/voice/lifecycle.py): `VoiceLifecycleManager` managing on-demand loading and idle unload timer.
- [`pluma/voice/pipeline.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/voice/pipeline.py): `VoicePipeline` orchestrating VAD trimming, STT transcription, and material target safety.
- [`pluma/voice/activation.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/voice/activation.py): `VoiceActivation` managing configurable push-to-talk keybindings.

### Phase 7: UIA Perception Worker
- [`pluma/perception/context.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/perception/context.py): `ActiveWindowContext` inspecting active foreground window identity, PID, executable name, geometry, and DPI scale.
- [`pluma/perception/element_refs.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/perception/element_refs.py): `ScreenElement`, `ScreenSnapshot`, `BoundingBox`, and `SnapshotFreshness` models.
- [`pluma/perception/uia_snapshot.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/perception/uia_snapshot.py): `UiaSnapshotBuilder` capturing semantic control trees with window-relative bounding boxes and TTL expiration.
- [`pluma/perception/freshness.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/perception/freshness.py): `FreshnessChecker` asserting TTL expiration and active window focus matching.
- [`pluma/tools/ui.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/tools/ui.py): `inspect_active_window`, `click_element`, and `type_into_element` registered ToolSpecs.
- [`pluma/verify/screen.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/verify/screen.py): `ScreenVerifier` validating control text, invocation accessibility, and window active states.

### Phase 8: Targeted OCR Fallback
- [`pluma/perception/capture.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/perception/capture.py): `WindowCapture` delivering ephemeral in-memory target window and region screen captures.
- [`pluma/perception/ocr_adapter.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/perception/ocr_adapter.py): `OcrAdapter`, `OcrWord`, `OcrResult` with lazy PaddleOCR import, cancellation support, and dependency injection.
- [`pluma/perception/ocr_lifecycle.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/perception/ocr_lifecycle.py): `OcrLifecycleManager` on-demand warm/cold state machine with automatic 10s idle unload timer.
- [`pluma/tools/ui.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/tools/ui.py): `click_ocr_text` tool grounding clicks on visible text, rejecting ambiguous duplicates, and clearing image bytes.
- [`pluma/verify/screen.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/verify/screen.py): `verify_ocr_text_present` and `verify_ocr_text_absent` postcondition verifiers.

### Phase 9: Replaceable Local Planner
- [`pluma/brain/interface.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/brain/interface.py): `PlannerInterface` abstract contract and error hierarchy.
- [`pluma/brain/tool_subset.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/brain/tool_subset.py): `ToolSubsetSelector` selecting route-specific tool schemas (`SMART`, `SCREEN`, `DEEP`) to prevent token bloat and hallucination.
- [`pluma/brain/prompt_builder.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/brain/prompt_builder.py): `PromptBuilder` constructing sanitized prompts with credential redaction.
- [`pluma/brain/validator.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/brain/validator.py): `PlanValidator` strict 2nd-pass validation enforcing tool existence, argument schemas, and hard step limits ($N \le 20$).
- [`pluma/brain/llama_cpp_adapter.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/brain/llama_cpp_adapter.py): `LlamaCppAdapter` pluggable local LLM worker using `llama.cpp` with zero module-level imports.
- [`pluma/brain/lifecycle.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/brain/lifecycle.py): `LlmLifecycleManager` state machine with 30s idle unload timer (`runtime.model_idle_unload_seconds`).

### Phase 10: Bounded Multi-Step Orchestration
- [`pluma/core/multi_step.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/core/multi_step.py): `MultiStepOrchestrator` coordinating the **Execute $\rightarrow$ Observe $\rightarrow$ Replan** loop with per-step stop-latch checks and reverse rollback.
- [`pluma/core/orchestrator.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/core/orchestrator.py): Unified 4-route dispatcher (`FAST`, `SMART`, `SCREEN`, `DEEP`).
- [`pluma/core/router.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/core/router.py): Pattern classifiers for `DEEP` route commands.
- [`pluma/core/task_supervisor.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/core/task_supervisor.py): State machine transitions with rollback failure handling.

### Phase 11: Policy Engine, Risk Classes & Elevation Broker
- [`pluma/policy/rules.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/policy/rules.py): `PolicyRules` risk classifier (`READ`, `LOW`, `HIGH`, `RESTRICTED`) with protected system path and command detection.
- [`pluma/policy/engine.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/policy/engine.py): `PolicyEngine` evaluating tool calls before execution against confirmation boundaries.
- [`pluma/policy/elevation_broker.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/policy/elevation_broker.py): `ElevationBroker` executing single-operation elevated subprocesses without elevating the resident core.
- [`pluma/ui/confirmations.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/ui/confirmations.py): `ConfirmationContract` functional confirmation interfaces.

---

## 6. Test Suite & Verification Baseline

Run the complete test suite with:
```powershell
python -m pytest tests/unit/ -v
```

**Current status: 393 passed, 0 failed, 0 warnings (Execution time ~11.2s)**

### Test Coverage Summary by File
- `tests/unit/test_policy_engine.py` (9 tests): `READ`/`LOW` auto-approval, `HIGH` confirmation, `RESTRICTED` paths, restricted command patterns, approval/denial callbacks, YAML overrides, ElevationBroker, ToolRegistry integration.
- `tests/unit/test_multi_step_orchestrator.py` (7 tests): Sequential execution, stop-latch checks, replan bounds, rollback on abort, SMART/SCREEN/DEEP e2e routes.
- `tests/unit/test_comprehensive_cross_check.py` (7 tests): Cross-subsystem call contracts, message determinism, activity ledger persistence, 4-route orchestration.
- `tests/unit/test_deep_audit_verification.py` (5 tests): End-to-end multi-subsystem integrity, TTL enforcement, OCR ambiguity, VAD safety, string redaction.
- `tests/unit/test_brain_tool_subset.py` (6 tests): Route-specific tool selection, prompt schema formatting.
- `tests/unit/test_brain_prompt_builder.py` (4 tests): System/user prompt formatting, context injection, credential redaction.
- `tests/unit/test_brain_validator.py` (6 tests): Valid plan acceptance, invented tool rejection, schema mismatch rejection, step count cap.
- `tests/unit/test_brain_lifecycle.py` (5 tests): COLD/WARM state transitions, 30s idle unload timer, cancellation, shutdown.
- `tests/unit/test_brain_llama_cpp_adapter.py` (5 tests): Structured plan generation, complex file decomposition, cancellation, zero module-level imports.
- All existing tests (339 tests across Phases 0–8) fully passing.

---

## 7. Known Architectural Decisions & Technical Nuances

1. **Zero ML at Idle (Spec §4)**: `llama_cpp`, `paddleocr`, and `whisper` are never imported at the module level.
2. **Zero Resident Elevation (Spec §15)**: The PLUMA resident core process NEVER runs elevated. Any action requiring elevation is dispatched as an isolated, single-operation out-of-process execution.
3. **Execute-Observe-Replan Loop (Spec §6)**: Step outputs are verified immediately; failures trigger bounded replanning up to `max_replans = 3`.
4. **Stop-Latch Pre-Check (Spec §12)**: Checked before every tool execution and before every replan invocation; halts immediately if cancelled.
5. **Reverse Rollback on Abort (Spec §13)**: Reversible prior actions are rolled back in reverse order via `RollbackEngine`.
6. **Layering Compliance**: Low-level `pluma.core` does not import high-level `pluma.brain` or `pluma.perception` at module level.

---

## 8. Current Objective & Exact Next Steps

### Next Phase: **Phase 13 — Packaging, `%LOCALAPPDATA%` Isolation & Crash Recovery**
Reference: `PLUMA_BUILD_PLAN.md` Phase 13 & `PLUMA_MASTER_SPEC.md` §20, §25.

### Objectives for Phase 13:
1. **Directory Isolation & `%LOCALAPPDATA%` Structure (Spec §20)**:
   - Config directory: `%LOCALAPPDATA%\Pluma\config\`
   - Database directory: `%LOCALAPPDATA%\Pluma\data\pluma.db`
   - Log directory: `%LOCALAPPDATA%\Pluma\logs\`
   - Models directory: `%LOCALAPPDATA%\Pluma\models\`
2. **Crash Recovery & Startup Reconciliation (Spec §20.3)**:
   - Mark incomplete tasks as `ABORTED_BY_CRASH` upon restart.
   - Clean up orphaned temporary directories and IPC handles.
   - Validate SQLite WAL integrity and execute pending migrations.
3. **Application Entry Point & Packaging (`pluma/app.py`)**:
   - Production entry point launching Resident Core with graceful signal handling (`SIGINT`, `SIGTERM`).
   - PyInstaller / Windows packaging script & specification.
4. **Write Unit & Integration Tests**:
   - `tests/unit/test_app_lifecycle.py`
   - `tests/unit/test_crash_recovery.py`

### Exact Instructions for the Next Agent:
1. Review `PLUMA_BUILD_PLAN.md` (Phase 13 section) and `PLUMA_MASTER_SPEC.md` (§20, §25).
2. Prepare and present the Phase 13 Implementation Plan to the user for approval.
3. Upon approval, implement `pluma/app.py`, crash recovery reconciliation, and packaging config.
4. Verify all tests pass (`pytest tests/unit/ tests/benchmarks/ -v`).
5. Update `PROJECT_HANDOFF.md` before proceeding to Phase 14.

### Phase 0: Schema Contracts & Storage Foundation
- [`pluma/brain/schemas.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/brain/schemas.py): `RouteMode` (`FAST`, `SCREEN`, `SMART`, `DEEP`), `PlanMode`, `ToolCall`, `Plan` with hard cap step validation ($N \le 20$).
- [`pluma/core/request.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/core/request.py): `PlumaRequest`, `InputMode` (`TEXT`, `VOICE`), `RequestID` validation.
- [`pluma/core/cancellation.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/core/cancellation.py): `CancellationToken`, `StopReason`, `TaskCancelledError`.
- [`pluma/memory/db.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/memory/db.py): SQLite with WAL mode, busy timeout, queued async background writer loop for crash resiliency.

### Phase 1: Resident Core & Process Containment
- [`pluma/core/job_object.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/core/job_object.py): Win32 `CreateJobObjectW`, `SetInformationJobObject` setting `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`, `AssignProcessToJobObject`.
- [`pluma/core/ownership.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/core/ownership.py): `OwnershipRegistry` tracking PID creation timestamps via `GetProcessTimes` to protect against PID reuse.
- [`pluma/core/task_supervisor.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/core/task_supervisor.py): Complete task state machine with reverse rollback and Job Object termination.
- [`pluma/core/ipc.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/core/ipc.py): Local-only Windows named pipe `IpcServer` / `IpcClient`.
- [`pluma/core/resident.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/core/resident.py): Resident daemon with Win32 `RegisterHotKey` loop and push-to-talk integration.

### Phase 2: Typed Tool Framework & Initial Tools
- [`pluma/tools/base.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/tools/base.py): `ToolSpec`, `ToolResult`, `VerifyResult`, `RiskClass`, `AdapterPriority`.
- [`pluma/tools/registry.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/tools/registry.py): `ToolRegistry` with validation, cancellation checks, pre-state capture, execution, verification, and ledger writes.
- Deterministic Tool Suites: `files.py`, `apps.py`, `windows.py`, `audio.py`, `system.py`, `clipboard.py`.

### Phase 3: Deterministic FAST Route & Orchestration
- [`pluma/core/router.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/core/router.py): Regex/pattern classifier routing all golden FAST commands directly without LLM/OCR.
- [`pluma/core/orchestrator.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/core/orchestrator.py): Command lifecycle coordinator.

### Phase 4: Windows Automation Adapters
- [`pluma/adapters/base.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/adapters/base.py): Common error hierarchy and immutable data models.
- [`pluma/adapters/win32.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/adapters/win32.py): Native Win32 window and process management.
- [`pluma/adapters/powershell.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/adapters/powershell.py): Bounded PowerShell adapter with Job Object containment and timeout limits.
- [`pluma/adapters/uia.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/adapters/uia.py): Lazy-loading UI Automation adapter with HWND pre-validation.
- [`pluma/adapters/input.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/adapters/input.py): `SendInput` ctypes with modifier safe release.
- [`pluma/adapters/screen.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/adapters/screen.py): Targeted window/rect GDI screen capture with headless fallback.

### Phase 5: Activity Ledger, Redaction & Rollback Engine
- [`pluma/memory/activity.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/memory/activity.py): Complete `ActivityLedger` write path and `ActivityQuery` read path.
- [`pluma/memory/redaction.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/memory/redaction.py): Deterministic sensitive-value redaction.
- [`pluma/memory/preferences.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/memory/preferences.py): `PreferencesStore` for user settings.
- [`pluma/memory/aliases.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/memory/aliases.py): `AliasStore` for command aliases.
- [`pluma/memory/routines.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/memory/routines.py): `RoutineStore` for multi-step routines.
- [`pluma/rollback/recipes.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/rollback/recipes.py): `RollbackRecipes` inverse operations.
- [`pluma/rollback/engine.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/rollback/engine.py): `RollbackEngine` reverse-order execution.

### Phase 6: Mandatory Voice Path
- [`pluma/voice/vad.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/voice/vad.py): Lightweight `EnergyVAD` calculation of RMS energy for 16-bit 16kHz PCM audio.
- [`pluma/voice/capture.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/voice/capture.py): `AudioCapture` managing microphone recording with lazy-loaded `sounddevice`.
- [`pluma/voice/stt_adapter.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/voice/stt_adapter.py): `WhisperSttAdapter` for on-demand `whisper.cpp` inference.
- [`pluma/voice/lifecycle.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/voice/lifecycle.py): `VoiceLifecycleManager` managing on-demand loading and idle unload timer.
- [`pluma/voice/pipeline.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/voice/pipeline.py): `VoicePipeline` orchestrating VAD trimming, STT transcription, and material target safety.
- [`pluma/voice/activation.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/voice/activation.py): `VoiceActivation` managing configurable push-to-talk keybindings.

### Phase 7: UIA Perception Worker
- [`pluma/perception/context.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/perception/context.py): `ActiveWindowContext` inspecting active foreground window identity, PID, executable name, geometry, and DPI scale.
- [`pluma/perception/element_refs.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/perception/element_refs.py): `ScreenElement`, `ScreenSnapshot`, `BoundingBox`, and `SnapshotFreshness` models.
- [`pluma/perception/uia_snapshot.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/perception/uia_snapshot.py): `UiaSnapshotBuilder` capturing semantic control trees with window-relative bounding boxes and TTL expiration.
- [`pluma/perception/freshness.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/perception/freshness.py): `FreshnessChecker` asserting TTL expiration and active window focus matching.
- [`pluma/tools/ui.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/tools/ui.py): `inspect_active_window`, `click_element`, and `type_into_element` registered ToolSpecs.
- [`pluma/verify/screen.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/verify/screen.py): `ScreenVerifier` validating control text, invocation accessibility, and window active states.

### Phase 8: Targeted OCR Fallback
- [`pluma/perception/capture.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/perception/capture.py): `WindowCapture` delivering ephemeral in-memory target window and region screen captures.
- [`pluma/perception/ocr_adapter.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/perception/ocr_adapter.py): `OcrAdapter`, `OcrWord`, `OcrResult` with lazy PaddleOCR import, cancellation support, and dependency injection.
- [`pluma/perception/ocr_lifecycle.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/perception/ocr_lifecycle.py): `OcrLifecycleManager` on-demand warm/cold state machine with automatic 10s idle unload timer.
- [`pluma/tools/ui.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/tools/ui.py): `click_ocr_text` tool grounding clicks on visible text, rejecting ambiguous duplicates, and clearing image bytes.
- [`pluma/verify/screen.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/verify/screen.py): `verify_ocr_text_present` and `verify_ocr_text_absent` postcondition verifiers.

### Phase 9: Replaceable Local Planner
- [`pluma/brain/interface.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/brain/interface.py): `PlannerInterface` abstract contract and error hierarchy.
- [`pluma/brain/tool_subset.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/brain/tool_subset.py): `ToolSubsetSelector` selecting route-specific tool schemas (`SMART`, `SCREEN`, `DEEP`) to prevent token bloat and hallucination.
- [`pluma/brain/prompt_builder.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/brain/prompt_builder.py): `PromptBuilder` constructing sanitized prompts with credential redaction.
- [`pluma/brain/validator.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/brain/validator.py): `PlanValidator` strict 2nd-pass validation enforcing tool existence, argument schemas, and hard step limits ($N \le 20$).
- [`pluma/brain/llama_cpp_adapter.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/brain/llama_cpp_adapter.py): `LlamaCppAdapter` pluggable local LLM worker using `llama.cpp` with zero module-level imports.
- [`pluma/brain/lifecycle.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/brain/lifecycle.py): `LlmLifecycleManager` state machine with 30s idle unload timer (`runtime.model_idle_unload_seconds`).

### Phase 10: Bounded Multi-Step Orchestration
- [`pluma/core/multi_step.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/core/multi_step.py): `MultiStepOrchestrator` coordinating the **Execute $\rightarrow$ Observe $\rightarrow$ Replan** loop with per-step stop-latch checks and reverse rollback.
- [`pluma/core/orchestrator.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/core/orchestrator.py): Unified 4-route dispatcher (`FAST`, `SMART`, `SCREEN`, `DEEP`).
- [`pluma/core/router.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/core/router.py): Pattern classifiers for `DEEP` route commands.
- [`pluma/core/task_supervisor.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/core/task_supervisor.py): State machine transitions with rollback failure handling.

---

## 6. Test Suite & Verification Baseline

Run the complete test suite with:
```powershell
python -m pytest tests/unit/ -v
```

**Current status: 377 passed, 0 failed, 0 warnings (Execution time ~11.0s)**

### Test Coverage Summary by File
- `tests/unit/test_multi_step_orchestrator.py` (7 tests): Sequential execution, stop-latch checks, replan bounds, rollback on abort, SMART/SCREEN/DEEP e2e routes.
- `tests/unit/test_deep_audit_verification.py` (5 tests): End-to-end multi-subsystem integrity, TTL enforcement, OCR ambiguity, VAD safety, string redaction.
- `tests/unit/test_brain_tool_subset.py` (6 tests): Route-specific tool selection, prompt schema formatting.
- `tests/unit/test_brain_prompt_builder.py` (4 tests): System/user prompt formatting, context injection, credential redaction.
- `tests/unit/test_brain_validator.py` (6 tests): Valid plan acceptance, invented tool rejection, schema mismatch rejection, step count cap.
- `tests/unit/test_brain_lifecycle.py` (5 tests): COLD/WARM state transitions, 30s idle unload timer, cancellation, shutdown.
- `tests/unit/test_brain_llama_cpp_adapter.py` (5 tests): Structured plan generation, complex file decomposition, cancellation, zero module-level imports.
- All existing tests (339 tests across Phases 0–8) fully passing.

---

## 7. Known Architectural Decisions & Technical Nuances

1. **Zero ML at Idle (Spec §4)**: `llama_cpp`, `paddleocr`, and `whisper` are never imported at the module level.
2. **Execute-Observe-Replan Loop (Spec §6)**: Step outputs are verified immediately; failures trigger bounded replanning up to `max_replans = 3`.
3. **Stop-Latch Pre-Check (Spec §12)**: Checked before every tool execution and before every replan invocation; halts immediately if cancelled.
4. **Reverse Rollback on Abort (Spec §13)**: Reversible prior actions are rolled back in reverse order via `RollbackEngine`.
5. **Layering Compliance**: Low-level `pluma.core` does not import high-level `pluma.brain` or `pluma.perception` at module level.

---

## 8. Current Objective & Exact Next Steps

### Next Phase: **Phase 11 — Policy Engine, Risk Classes & Elevation Broker**
Reference: `PLUMA_BUILD_PLAN.md` Phase 11 & `PLUMA_MASTER_SPEC.md` §14, §15.

### Objectives for Phase 11:
1. **Policy Engine (`pluma/policy/engine.py`, `pluma/policy/rules.py`)**:
   - Evaluates action against policy rules before execution.
   - Risk classifications: `READ`, `LOW`, `HIGH`, `RESTRICTED`.
   - Explicit user confirmations for `HIGH` risk operations (destructive deletes, system modifications).
2. **Single-Operation Elevation Broker (`pluma/policy/elevation_broker.py`)**:
   - Elevated operations run isolated single subprocesses via UAC elevation broker.
   - Resident core NEVER runs elevated; only isolated single tasks.
3. **Confirmation Contract (`pluma/ui/confirmations.py`)**:
   - Functional contract for user confirmation prompts.
4. **Write Unit & Integration Tests**:
   - Policy evaluation for `READ`, `LOW`, `HIGH`, `RESTRICTED` risk classes.
   - Confirmation prompts blocking execution until approved.
   - Elevation broker running single isolated operations.

### Exact Instructions for the Next Agent:
1. Review `PLUMA_BUILD_PLAN.md` (Phase 11 section) and `PLUMA_MASTER_SPEC.md` (§14, §15).
2. Prepare and present the Phase 11 Implementation Plan to the user for approval.
3. Upon approval, implement `pluma/policy/` components and unit tests.
4. Verify all tests pass (`pytest tests/unit/ -v`).
5. Update `PROJECT_HANDOFF.md` before proceeding to Phase 12.

