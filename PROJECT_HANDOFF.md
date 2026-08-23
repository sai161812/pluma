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
| **Phase 7** | UIA perception worker (ScreenElement semantic grounding, snapshot TTL) | **COMPLETED** | **314 (cumul.)** |
| **Phase 8** | Targeted OCR fallback (PaddleOCR/ONNX region-only) | **NEXT UP** | Pending |
| **Phase 9** | Replaceable local planner (llama.cpp on-demand manager, grammar constraints) | Planned | Pending |
| **Phase 10** | Bounded multi-step orchestration (execute-observe-replan loop, replan limits) | Planned | Pending |
| **Phase 11** | Policy engine, risk classifications, single-operation elevation broker | Planned | Pending |
| **Phase 12** | Latency and quality benchmark tuning, leak testing | Planned | Pending |
| **Phase 13** | Packaging, `%LOCALAPPDATA%` isolation, crash recovery | Planned | Pending |
| **Phase 14** | Owner-directed UI implementation | Blocked on Owner Design | Pending |

---

## 5. Current Verified Implementation Details (Phases 0–7)

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

---

## 6. Test Suite & Verification Baseline

Run the complete test suite with:
```powershell
python -m pytest tests/unit/ -v
```

**Current status: 314 passed, 0 failed, 0 warnings (Execution time ~9.8s)**

### Test Coverage Summary by File
- `tests/unit/test_perception_context.py` (3 tests): Active window context inspection, null foreground handling, process name resolution.
- `tests/unit/test_perception_uia_snapshot.py` (3 tests): Control tree extraction, window-relative bounding boxes, zero module-level pywinauto import.
- `tests/unit/test_perception_freshness.py` (3 tests): Snapshot TTL expiration, window mismatch error, freshness validation.
- `tests/unit/test_tools_ui.py` (5 tests): `inspect_active_window`, `click_element`, `type_into_element` executors and error handling.
- `tests/unit/test_verify_screen.py` (6 tests): Control text match/mismatch, control invocation verification, window active verification.
- All existing tests (294 tests across Phases 0–6) fully passing.

---

## 7. Known Architectural Decisions & Technical Nuances

1. **Window-Relative Bounding Boxes**: All `ScreenElement` coordinates are stored relative to the target window's top-left corner (`(left - win_left, top - win_top)`). Moving a window does not invalidate control geometries as long as the window title/process remains fresh.
2. **Strict Snapshot TTL**: `ScreenSnapshot` enforces a default 3-second TTL (`perception.snapshot_ttl_seconds`). Actions attempted after expiration trigger `StaleSnapshotError` requiring fresh re-capture.
3. **Active Window Focus Guard**: `FreshnessChecker` validates that the foreground window's process and title still match the snapshot before any UI interaction. If the user shifts focus, the action aborts safely with `WindowMismatchError`.
4. **UIA Control Invocation Hierarchy**: Interactive tools prioritize semantic invocation (`invoke` pattern / `click_input`) via `UiaAdapter` before falling back to keyboard or coordinates.

---

## 8. Current Objective & Exact Next Steps

### Next Phase: **Phase 8 — Targeted OCR Fallback**
Reference: `PLUMA_BUILD_PLAN.md` Phase 8 & `PLUMA_MASTER_SPEC.md` §8.

### Objectives for Phase 8:
1. **On-Demand OCR Worker (`pluma/perception/ocr_adapter.py`)**:
   - Lightweight `PaddleOCR` (ONNX Runtime) adapter with on-demand lifecycle.
   - Target-window or cropped-region OCR only — no whole-desktop scans.
   - Automatic idle unloading after `ocr_idle_unload_seconds` (default: 10s).
2. **Ephemeral Screenshot Management (`pluma/perception/capture.py`)**:
   - GDI target-window screen capture returning ephemeral image buffer.
   - Screen images discarded immediately after OCR extraction (zero screenshots persisted in ledger).
3. **OCR ScreenElement Grounding**:
   - Maps detected OCR words/lines to `ScreenElement(source=ElementSource.OCR)` with confidence and bounding boxes.
4. **OCR-Based Verification**:
   - Verifies on-screen text appearance/disappearance post-action.
5. **Write Unit & Integration Tests**:
   - OCR word extraction and confidence thresholding.
   - Ephemeral image deletion and memory leak tests.
   - OCR idle unload timer.

### Exact Instructions for the Next Agent:
1. Review `PLUMA_BUILD_PLAN.md` (Phase 8 section) and `PLUMA_MASTER_SPEC.md` (§8).
2. Prepare and present the Phase 8 Implementation Plan to the user for approval.
3. Upon approval, implement `pluma/perception/ocr_adapter.py`, update `pluma/perception/capture.py`, and create corresponding unit tests.
4. Verify all tests pass (`pytest tests/unit/ -v`).
5. Update `PROJECT_HANDOFF.md` before proceeding to Phase 9.

