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
| **Phase 4** | Windows Automation Adapters (Native Win32, PowerShell, UIA, Input, Screen capture) | **COMPLETED** | **246 (cumul.)** |
| **Phase 5** | Activity Ledger completion, redaction engine, reverse-order rollback | **NEXT UP** | Pending |
| **Phase 6** | Mandatory voice path (push-to-talk, VAD, whisper.cpp on-demand) | Planned | Pending |
| **Phase 7** | UIA perception worker (ScreenElement semantic grounding, snapshot TTL) | Planned | Pending |
| **Phase 8** | Targeted OCR fallback (PaddleOCR/ONNX region-only) | Planned | Pending |
| **Phase 9** | Replaceable local planner (llama.cpp on-demand manager, grammar constraints) | Planned | Pending |
| **Phase 10** | Bounded multi-step orchestration (execute-observe-replan loop, replan limits) | Planned | Pending |
| **Phase 11** | Policy engine, risk classifications, single-operation elevation broker | Planned | Pending |
| **Phase 12** | Latency and quality benchmark tuning, leak testing | Planned | Pending |
| **Phase 13** | Packaging, `%LOCALAPPDATA%` isolation, crash recovery | Planned | Pending |
| **Phase 14** | Owner-directed UI implementation | Blocked on Owner Design | Pending |

---

## 5. Current Verified Implementation Details (Phases 0–4)

### Phase 0: Schema Contracts & Storage Foundation
- [`pluma/brain/schemas.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/brain/schemas.py): `RouteMode` (`FAST`, `SCREEN`, `SMART`, `DEEP`), `PlanMode`, `ToolCall`, `Plan` with hard cap step validation ($N \le 20$).
- [`pluma/core/request.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/core/request.py): `PlumaRequest`, `InputMode` (`TEXT`, `VOICE`), `RequestID` validation.
- [`pluma/core/cancellation.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/core/cancellation.py): `CancellationToken`, `StopReason`, `TaskCancelledError`.
- [`pluma/memory/db.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/memory/db.py): SQLite with WAL mode, busy timeout, queued async background writer loop for crash resiliency.
- [`pluma/config/loader.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/config/loader.py): Structured YAML config loader.
- [`tests/fixtures/golden_commands.yaml`](file:///D:/Workspace/DEVEL/PLUMA/tests/fixtures/golden_commands.yaml): 22 reference golden commands (GC-001 to GC-022) with expected routes, tools, and `no_llm`/`no_ocr` assertions.

### Phase 1: Resident Core & Process Containment
- [`pluma/core/job_object.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/core/job_object.py): Win32 `CreateJobObjectW`, `SetInformationJobObject` setting `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`, `AssignProcessToJobObject`.
- [`pluma/core/ownership.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/core/ownership.py): `OwnershipRegistry` tracking PID creation timestamps via `GetProcessTimes` to protect against PID reuse.
- [`pluma/core/task_supervisor.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/core/task_supervisor.py): `TaskCapsule` and `TaskSupervisor` implementing the deterministic STOP sequence (§12.2): (1) cancel latch, (2) STOPPING transition, (3) Job Object termination, (4) resource cleanup, (5) STOPPED state.
- [`pluma/core/ipc.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/core/ipc.py): Local-only Windows named pipe `IpcServer` / `IpcClient` with blocking accept loop and test isolation.
- [`pluma/core/resident.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/core/resident.py): Resident daemon with Win32 `RegisterHotKey` loop and crash recovery stubs.

### Phase 2: Typed Tool Framework & Initial Tools
- [`pluma/tools/base.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/tools/base.py): `ToolSpec`, `ToolResult`, `VerifyResult`, `RiskClass`, `AdapterPriority`.
- [`pluma/tools/registry.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/tools/registry.py): `ToolRegistry` with full `execute()` lifecycle: argument validation $\rightarrow$ cancellation latch check $\rightarrow$ undo pre-state capture $\rightarrow$ execution with perf timing $\rightarrow$ postcondition verification $\rightarrow$ Activity Ledger recording.
- [`pluma/verify/common.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/verify/common.py): Deterministic postcondition verifiers (`verify_file_exists`, `verify_file_moved`, `verify_file_renamed`, `verify_dir_created`, `verify_process_running`, `verify_process_closed`, `verify_window_focused`, `verify_noop`).
- Built-in Tool Implementations:
  - [`pluma/tools/files.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/tools/files.py): `list_files`, `find_file`, `move_file`, `rename_file`, `create_folder`.
  - [`pluma/tools/apps.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/tools/apps.py): `open_app`, `close_app`, `focus_app`, `list_apps`, `app_status` (assigned to Windows Job Objects).
  - [`pluma/tools/windows.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/tools/windows.py): `list_windows`, `focus_window`.
  - [`pluma/tools/audio.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/tools/audio.py): `set_volume`, `mute`, `unmute` (lazy `pycaw` with mock fallback for headless test environments).
  - [`pluma/tools/system.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/tools/system.py): `get_system_status`, `stop_current`, `show_activity`, `undo_last`.

### Phase 3: Deterministic FAST Route
- [`pluma/core/router.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/core/router.py):
  - Ordered regex intent router.
  - Generates direct `Plan` for all FAST commands without starting an LLM.
  - Spoken number word parser (`_parse_number` handles "twenty", "thirty five", etc. clamped to 0–100).
  - Normalizes app aliases ("calculator" $\rightarrow$ "calc", "paint" $\rightarrow$ "mspaint", "vs code" $\rightarrow$ "code").
  - Detects SCREEN and SMART boundary keywords and assigns proper `RouteMode`.
- [`pluma/core/orchestrator.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/core/orchestrator.py):
  - End-to-end FAST command coordinator: receives `PlumaRequest`, creates `TaskCapsule`, inserts task to ledger, calls router, iterates plan steps with cancellation checks before each step, executes through `ToolRegistry`, records final state and timings.
  - Non-FAST commands return `final_state="DEFERRED"` without touching uninitialized workers.
- Additional Tools Added:
  - [`pluma/tools/clipboard.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/tools/clipboard.py): `clear_clipboard`, `clipboard_clear`, `get_clipboard_text`, `set_clipboard_text` via Win32 API with 64-bit safe `c_size_t` `HGLOBAL` types. Raw text is omitted from logged `data` for privacy.
  - [`pluma/tools/windows.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/tools/windows.py): `minimize_window`, `maximize_window` via Win32 `ShowWindow` (`SW_MINIMIZE=6`, `SW_MAXIMIZE=3`).
  - [`pluma/tools/system.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/tools/system.py): `battery_status` via Win32 `GetSystemPowerStatus`.

### Phase 4: Windows Automation Adapters
- [`pluma/adapters/base.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/adapters/base.py): Base adapter error hierarchy (`AdapterError`, `AccessDeniedError`, `ElementNotFoundError`, `ElementUnavailableError`, `AdapterTimeoutError`, `WindowNotFoundError`, `InputOutOfBoundsError`) and dataclasses (`Rect`, `WindowInfo`, `ControlInfo`, `WindowState`).
- [`pluma/adapters/win32.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/adapters/win32.py): Concrete Win32 adapter via `ctypes` (`find_windows`, `get_foreground_window`, `set_foreground_window`, `get_window_rect`, `get_window_state`, `set_window_state`, `close_window`).
- [`pluma/adapters/powershell.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/adapters/powershell.py): Bounded PowerShell adapter with Job Object containment, hard timeout enforcement, and permission denial mapping to `AccessDeniedError`.
- [`pluma/adapters/uia.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/adapters/uia.py): Lazy-loading UI Automation adapter via `pywinauto` with HWND pre-validation, semantic control lookup (`find_control`), invocation (`invoke_control`), and text modification (`set_control_text`).
- [`pluma/adapters/input.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/adapters/input.py): Low-level Win32 `SendInput` ctypes adapter with guaranteed modifier key release in `finally` blocks, unicode string typing, and coordinate boundary safety (`InputOutOfBoundsError`).
- [`pluma/adapters/screen.py`](file:///D:/Workspace/DEVEL/PLUMA/pluma/adapters/screen.py): Targeted window/rect GDI screen capture adapter with 64-bit handle safety and headless/service fallback buffer creation. Zero persistent screenshots.

---

## 6. Test Suite & Verification Baseline

Run the complete test suite with:
```powershell
python -m pytest tests/unit/ -v
```

**Current status: 246 passed, 0 failed, 0 warnings (Execution time ~8.5s)**

### Test Coverage Summary by File
- `tests/unit/test_adapters_base.py` (4 tests): Adapter error hierarchy, Rect geometry calculation, WindowInfo and ControlInfo dataclass models.
- `tests/unit/test_adapters_win32.py` (4 tests): Win32Adapter instantiation, invalid HWND errors, window enumeration, foreground window query.
- `tests/unit/test_adapters_powershell.py` (5 tests): Script execution, exit code capture, timeout abort, cancellation token abort, access-denied mapping.
- `tests/unit/test_adapters_uia.py` (5 tests): Lazy loading, invalid HWND handling, element lookup, element not found, disabled control error.
- `tests/unit/test_adapters_input.py` (4 tests): Key code resolution, mouse boundary validation, modifier key safe release chord, unicode text typing.
- `tests/unit/test_adapters_screen.py` (4 tests): Invalid dimensions/HWND errors, BMP capture header validation, temporary file capture and cleanup.
- `tests/unit/test_config.py` (4 tests): Configuration loading & defaults.
- `tests/unit/test_db.py` (7 tests): SQLite WAL mode, async writer queue, migrations.
- `tests/unit/test_schemas.py` (39 tests): Pydantic schemas, cancellation token, task state transitions, zero-ML import check.
- `tests/unit/test_job_object.py` (3 tests): Windows Job Object process attachment and kill-on-close.
- `tests/unit/test_ownership.py` (5 tests): PID creation timestamp capture and registry safety.
- `tests/unit/test_task_supervisor.py` (5 tests): STOP sequence, cancellation latency, active task sweep.
- `tests/unit/test_ipc.py` (2 tests): Named pipe message exchange and isolation.
- `tests/unit/test_resident.py` (2 tests): Hotkey registration and loop lifecycle.
- `tests/unit/test_redaction.py` (15 tests): Sensitive argument and secret redaction.
- `tests/unit/test_tools_files.py` (4 tests): File listing, find, move, rename, folder creation, postconditions, undo.
- `tests/unit/test_tools_apps.py` (2 tests): App lifecycle inside Job Objects.
- `tests/unit/test_tools_windows.py` (2 tests): Window listing and focus validation.
- `tests/unit/test_tools_audio.py` (2 tests): Volume, mute/unmute, undo.
- `tests/unit/test_tools_system.py` (4 tests): System status, activity inspection, stop, file undo execution.
- `tests/unit/test_tool_runner_ledger.py` (5 tests): Registry execution runner, pre-state capture, postconditions, ledger writing.
- `tests/unit/test_tools_clipboard.py` (22 tests): Clipboard clear, set, get, 64-bit Win32 handles, round-trip, redaction.
- `tests/unit/test_router.py` (58 tests): Pattern parsing, spoken number words, voice/text parity, all 22 golden commands.
- `tests/unit/test_fast_orchestrator.py` (39 tests): End-to-end FAST execution, cancellation interruption, zero-ML verification on all golden commands.

---

## 7. Known Architectural Decisions & Technical Nuances

1. **Win32 `HGLOBAL` 64-bit Handle Safety**: In `pluma/tools/clipboard.py`, `GlobalAlloc`, `GlobalLock`, and `SetClipboardData` must use `ctypes.c_size_t` for `HGLOBAL` and handle pointer conversions to prevent 64-bit `OverflowError`.
2. **Win32 GDI & Screen Capture Handle Masking**: In `pluma/adapters/screen.py`, GDI handles (HDC, HBITMAP) must be declared with proper restype/argtypes to prevent 32-bit sign extension on 64-bit Windows. Headless/service desktop DC denial (error 5/6) falls back cleanly to generating memory BMP buffers.
3. **IPC Named Pipe Windows Behavior**: `multiprocessing.connection.wait()` does not support `Listener` objects on Windows. `IpcServer` uses a blocking `.accept()` loop in a dedicated thread.
4. **SQLite Thread Affinity**: Background writer connection must be opened inside the writer worker thread. In-memory databases (`:memory:`) share one connection object.
5. **Audio Headless/CI Mock**: `pluma/tools/audio.py` lazily attempts to load `pycaw`, falling back to an in-memory `_MOCK_AUDIO_STATE` dictionary if audio hardware is absent.
6. **PID String vs Int Compatibility**: Verifiers (`pluma/verify/common.py`) coerce numeric string PIDs to integers to prevent type mismatch between tool callers and process checkers.
7. **Task Completion Calls**: On `TaskSupervisor`, use `mark_succeeded(task_id)` and `mark_failed(task_id)` (not `complete_task`). For stops, default reason is `StopReason.USER_STOP`.

---

## 8. Current Objective & Exact Next Steps

### Next Phase: **Phase 5 — Activity Ledger, Redaction and Rollback**
Reference: `PLUMA_BUILD_PLAN.md` Phase 5 & `PLUMA_MASTER_SPEC.md` §16, §20, §21.

### Objectives for Phase 5:
1. **Activity Ledger Schema & Storage Completion (`pluma/memory/`)**:
   - Complete `actions`, `undo_records`, `resources`, and `screen_events` tables.
   - Record input mode, route, active window, adapter, timings, policy decision, verification, and stop/rollback details.
   - Activity query API for retrieving factual timeline and status.
2. **Deterministic Redaction Engine (`pluma/memory/redaction.py` / `pluma/core/redaction.py`)**:
   - Expand sensitive-value and secret redaction across stored arguments, clipboard history, and logs.
3. **Reverse-Order Rollback Engine (`pluma/rollback/engine.py`, `pluma/rollback/recipes.py`)**:
   - Implement reverse-order execution of `UndoRecord` items for a task.
   - Non-undoable action boundary handling (mark committed, refuse false rollback claims).
   - Residual effect tracking (`STOPPED_WITH_RESIDUAL`).
4. **Write Unit & Integration Tests**:
   - `tests/unit/test_rollback_engine.py`
   - `tests/unit/test_ledger_complete.py`
   - `tests/unit/test_activity_query.py`

### Exact Instructions for the Next Agent:
1. Review `PLUMA_BUILD_PLAN.md` (Phase 5 section) and `PLUMA_MASTER_SPEC.md` (§16, §20, §21).
2. Prepare and present the Phase 5 Implementation Plan to the user for approval.
3. Upon approval, implement `pluma/rollback/` and `pluma/memory/` components and their corresponding unit tests.
4. Verify all tests pass (`pytest tests/unit/ -v`).
5. Update `PROJECT_HANDOFF.md` to record Phase 5 completion before proceeding to Phase 6.
