# PLUMA

**Fully local, voice-first Windows 11 AI desktop assistant.**

*Smart when active. Featherweight when idle.*

---

## What PLUMA Does

PLUMA is a **local Windows automation assistant** built around deterministic execution rather than free-form agent behavior.

It accepts voice or text requests, routes them through a typed tool system, executes actions through bounded Windows automation adapters, verifies postconditions before reporting success, records an audit trail, and captures undo evidence for reversible actions.

The local reasoning layer is replaceable and loaded only when needed. Core execution remains policy-constrained, observable, and independently verifiable.

### Engineering highlights

- **Fully local execution path** for voice, planning, perception, and desktop control
- **Typed tool contracts** instead of direct natural-language execution
- **Postcondition verification** for state-changing actions
- **Reverse-order rollback** with evidence-backed undo records
- **Windows Job Object containment** for subprocess ownership and STOP behavior
- **UI Automation + targeted OCR fallback** with freshness and focus validation
- **On-demand ML runtimes** so heavy components unload while idle
- **Release hardening evidence** with 716 collected tests and 0 failures in the final release report

> The goal is not to make an assistant that can do anything. It is to make one that can do useful things **predictably, reversibly, and with evidence that the action actually happened**.

---

## Execution Model

```text
Voice / Text Request
        |
        v
   Request Router
   /     |      \
FAST   SMART   SCREEN/DEEP
   \     |      /
        v
 Policy + Tool Subset
        |
        v
 Typed Tool Execution
        |
        v
 Postcondition Verification
        |
        +----> Activity Ledger
        |
        +----> Undo Evidence / Rollback
        |
        v
 Verified Result
```

The reasoning layer can propose a plan, but it never bypasses the registered tool system, route permissions, policy checks, or verification path.

---

## Core Architecture Principles

1. **Featherweight Resident Process**: Starts without loading LLM, STT, OCR, screen capture loops, or GPU inference.
2. **Unified Voice & Text Pipeline**: Voice is mandatory and shares the identical request, routing, policy, tool, verification, and ledger pipeline as text.
3. **Deterministic Typed Tools as Execution API**: Natural language is never an execution API. Every action is a registered, typed `ToolSpec`.
4. **Hierarchical Automation Priority**: Native/Application APIs -> Controlled PowerShell/CLI -> UI Automation (UIA) -> Stable Keyboard/Input -> Targeted OCR -> Raw coordinates (strictly last resort).
5. **Postcondition Verification**: Every state-changing action has an explicit postcondition and must read it back before reporting success.
6. **Reversibility & Undo Evidence**: Safe pre-states are captured prior to action execution.
7. **Task Capsule & Job Object Containment**: Every command is one `TaskCapsule` owned by one `TaskSupervisor`. Subprocess trees are isolated in Windows Job Objects (`JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`).
8. **Global STOP Precedence**: Setting the atomic stop latch immediately terminates execution and triggers safe reverse-order rollback without starting new tool steps.
9. **Factual Activity Ledger & Redaction**: Deterministic, template-generated SQLite audit history with automatic sensitive data and secret redaction.

---

## Build & Phase Status

| Phase | Description | Status |
|---|---|---|
| **Phase 0** | Freeze contracts, schemas, SQLite baseline, benchmarks, golden corpus | Complete |
| **Phase 1** | Resident Core, Task Capsule, Windows Job Objects, atomic STOP sequence | Complete |
| **Phase 2** | Typed tool framework, initial tool catalog, postcondition verifiers, ledger | Complete |
| **Phase 3** | Deterministic FAST route, Router, Fast Orchestrator, clipboard & window tools | Complete |
| **Phase 4** | Windows Automation Adapters (Win32, PowerShell, UIA, Input, Screen) | Complete |
| **Phase 5** | Activity Ledger, redaction engine, reverse-order rollback | Complete |
| **Phase 6** | Mandatory voice path (push-to-talk, VAD, whisper.cpp on-demand) | Complete |
| **Phase 7** | UIA perception worker (semantic grounding, snapshot freshness) | Complete |
| **Phase 8** | Targeted OCR fallback (region-only perception) | Complete |
| **Phase 9** | Replaceable local planner (llama.cpp on-demand manager) | Complete |
| **Phase 10** | Bounded multi-step orchestration (execute-observe-replan loop) | Complete |
| **Phase 11** | Policy engine, risk classifications, elevation broker | Complete |
| **Phase 12** | Latency, quality, leak, and soak verification | Complete |
| **Phase 13** | Packaging, `%LOCALAPPDATA%` isolation, crash recovery, release hardening | Complete |
| **Phase 14** | Creator-directed UI implementation | In progress / separate from hardened core |

Release verification evidence is tracked in [FINAL_RELEASE_REPORT.md](FINAL_RELEASE_REPORT.md). That report records **716 collected tests: 713 passed, 3 environment-specific skips, 0 failures**, plus 9/9 deterministic acceptance gates passed.

---

## Key Subsystems

### Replaceable Local Planner Subsystem (`pluma.brain`)
- **Pluggable Local LLM Adapter**: `LlamaCppAdapter` using `llama.cpp` for local quantized inference with zero module-level imports.
- **On-Demand Warm/Cold Lifecycle**: `LlmLifecycleManager` state machine with automatic 30s idle unloading (`runtime.model_idle_unload_seconds`) enforcing zero ML footprint at idle.
- **Route-Specific Tool Subsets**: `ToolSubsetSelector` delivering only route-permitted tool schemas (`SMART`, `SCREEN`, `DEEP`) to prevent token bloat and eliminate hallucination.
- **Sanitized Prompt Construction**: `PromptBuilder` injecting minimal context and redacting passwords, API keys, and sensitive tokens.
- **Strict Second-Pass Validation**: `PlanValidator` verifying tool existence in `ToolRegistry`, argument Pydantic schemas, and step limits ($N \le 20$).

### Targeted OCR Fallback Subsystem (`pluma.perception`)
- **Ephemeral Screen Capture**: Target-window and region capture returning in-memory raw BMP bytes; zero screenshots written to disk or the Activity Ledger (`WindowCapture`).
- **On-Demand OCR Worker**: Lazy-loaded `PaddleOCR`/ONNX Runtime adapter extracting `OcrWord` items with window-relative bounding boxes and confidence scoring (`OcrAdapter`).
- **Warm/Cold Lifecycle Management**: Automatic model unload after 10 seconds of idle inactivity (`OcrLifecycleManager`).
- **OCR Interaction Tools**: Grounded text clicking with coordinate translation and duplicate label ambiguity rejection (`click_ocr_text`).
- **Postcondition Verification**: On-screen text presence and absence verification (`ScreenVerifier`).

### UIA Perception Subsystem (`pluma.perception`)
- **Active Window Context**: Inspects foreground window identity, PID, process name, window geometry, and DPI scale (`ActiveWindowContext`).
- **UIA Snapshot Worker**: Traverses UI Automation control tree extracting semantic `ScreenElement` instances with window-relative bounding boxes and invocation capabilities (`UiaSnapshotBuilder`).
- **Freshness & Focus Guard**: Enforces snapshot TTL (3s default) and aborts stale or mismatched window interactions (`FreshnessChecker`).
- **UI Interaction Tools**: Typed tools for active window inspection (`inspect_active_window`), element clicking (`click_element`), and text entry (`type_into_element`).
- **Postcondition Verification**: UI control text, accessibility, and window focus verification (`ScreenVerifier`).

### Mandatory Voice Subsystem (`pluma.voice`)
- **Push-to-Talk Activation**: Win32 hotkey listener (`agent.voice_hotkey`, default `ctrl+alt+v`) with press/release triggers.
- **Energy-Based VAD**: Pure Python/numpy RMS energy calculation for 16-bit 16kHz PCM audio and silence trimming.
- **On-Demand STT Lifecycle**: `WhisperSttAdapter` for `whisper.cpp` with warm/cold state machine and configurable idle timeout unload (`runtime.stt_idle_unload_seconds`).
- **Unified Pipeline Parity**: Produces `PlumaRequest(input_mode=VOICE)` flowing through identical router and tool execution paths as typed text.
- **Material Target Safety**: Low-confidence transcripts (< 0.65) for commands with files, numbers, or destructive verbs prompt for clarification.

### Activity Ledger & Persistence (`pluma.memory`)
- **SQLite WAL Baseline**: Crash-safe async queued background writer thread (`DbConnection`).
- **Complete Activity Ledger**: Factual tracking across 5 core tables (`tasks`, `actions`, `undo_records`, `resources`, `screen_events`).
- **Deterministic Redaction Engine**: Automatic masking of passwords, tokens, private clipboard content, and sensitive argument keys.
- **Memory Stores**: SQLite-backed `PreferencesStore`, `AliasStore`, and `RoutineStore`.

### Reverse-Order Rollback Engine (`pluma.rollback`)
- **`RollbackEngine`**: Reverse-order execution of recorded `UndoRecord` items upon task cancellation or rollback request.
- **`RollbackRecipes`**: Tool-specific inverse operations (`move_file` restore, `rename_file` restore, `create_folder` safe non-preexisting empty folder deletion, `set_volume` restore, `mute`/`unmute` restore).
- **Residual Tracking**: Identifies non-undoable actions and updates task state to `STOPPED_WITH_RESIDUAL` when full reversal is impossible.

### Automation Adapters (`pluma.adapters`)
- **Native Win32**: `ctypes` bindings for HWND management, window states, process metrics, and display geometry.
- **PowerShell Adapter**: Bounded PowerShell execution with Job Object containment and timeout aborts.
- **UIA Adapter**: Lazy-loaded `pywinauto` UIA backend for semantic control inspection and invocation.
- **Input Adapter**: `SendInput` ctypes with guaranteed modifier key safe-release in `finally` blocks and coordinate boundary checks.
- **Screen Adapter**: Window and region GDI screen capture with headless buffer fallbacks. Zero persistent screenshots.

---

## Implemented Tool Catalog

- **File Operations**: `list_files`, `find_file`, `move_file`, `rename_file`, `create_folder`
- **Application Lifecycle**: `open_app`, `close_app`, `focus_app`, `list_apps`, `app_status`
- **Window Management**: `list_windows`, `focus_window`, `minimize_window`, `maximize_window`
- **Audio Control**: `set_volume`, `mute`, `unmute`
- **System & Activity**: `get_system_status`, `battery_status`, `stop_current`, `show_activity`, `undo_last`
- **Clipboard Management**: `clear_clipboard`, `clipboard_clear`, `get_clipboard_text`, `set_clipboard_text`

---

## Current State

The hardened backend/core, automation stack, safety model, local reasoning path, packaging, and release verification are implemented. The remaining active work is primarily the creator-directed Windows UI layer and final UI-to-core wiring.

---

## Requirements & Development Setup

- **OS**: Windows 11 (64-bit)
- **Python**: Python 3.12+

```powershell
# Set up virtual environment
python -m venv .venv
.venv\Scripts\Activate.ps1

# Install dependencies
pip install -r requirements-dev.txt
pip install -e .

# Run the unit test suite
python -m pytest tests/unit/ -v
```

---

## Verification & Project Evidence

PLUMA keeps implementation claims tied to explicit project artifacts rather than README-only assertions.

- [`FINAL_RELEASE_REPORT.md`](FINAL_RELEASE_REPORT.md) — final verification matrix, release status, test summary, and packaged artifacts
- [`ACCEPTANCE_TEST_RAW_LOG.txt`](ACCEPTANCE_TEST_RAW_LOG.txt) — raw acceptance-test evidence
- [`PLUMA_ACCEPTANCE_TESTS.md`](PLUMA_ACCEPTANCE_TESTS.md) — release gates and verification criteria
- [`PLUMA_MASTER_SPEC.md`](PLUMA_MASTER_SPEC.md) — authoritative product and engineering specification
- [`PLUMA_BUILD_PLAN.md`](PLUMA_BUILD_PLAN.md) — ordered implementation phases
- [`PLUMA_TECH_STACK.md`](PLUMA_TECH_STACK.md) — approved runtime libraries and technology stack
- [`AGENTS.md`](AGENTS.md) — safety and architecture contract used during implementation
- [`PROJECT_HANDOFF.md`](PROJECT_HANDOFF.md) — project continuity and implementation state
