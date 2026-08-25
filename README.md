# PLUMA

**Fully local, voice-first Windows 11 AI desktop assistant.**

*Smart when active. Featherweight when idle.*

---

## Engineering Philosophy

PLUMA is a deterministic Windows control system with a replaceable local reasoning layer, not an unpredictable chatbot. It accepts voice or text commands through a single unified pipeline, executes actions strictly via registered and typed tools, verifies every state change, captures evidence-based undo records, records factual audit history into an Activity Ledger, and unloads heavy runtimes while idle.

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

| Phase | Description | Status | Cumulative Tests |
|---|---|---|---|
| **Phase 0** | Freeze contracts, schemas, SQLite baseline, benchmarks, golden corpus | Complete | 65 |
| **Phase 1** | Resident Core, Task Capsule, Windows Job Objects, atomic STOP sequence | Complete | 82 |
| **Phase 2** | Typed tool framework, initial 19 tools, postcondition verifiers, ledger | Complete | 101 |
| **Phase 3** | Deterministic FAST route, Router, Fast Orchestrator, clipboard & window tools | Complete | 220 |
| **Phase 4** | Windows Automation Adapters (Win32, PowerShell, UIA, Input, Screen) | Complete | 246 |
| **Phase 5** | Activity Ledger completion, redaction engine, reverse-order rollback | Complete | 266 |
| **Phase 6** | Mandatory voice path (push-to-talk, VAD, whisper.cpp on-demand) | Complete | 294 |
| **Phase 7** | UIA perception worker (ScreenElement semantic grounding, snapshot TTL) | Complete | 314 |
| **Phase 8** | Targeted OCR fallback (PaddleOCR/ONNX region-only) | Complete | **339** |
| **Phase 9** | Replaceable local planner (llama.cpp on-demand manager) | **Next Up** | — |
| **Phase 10** | Bounded multi-step orchestration (execute-observe-replan loop) | Planned | — |
| **Phase 11** | Policy engine, risk classifications, elevation broker | Planned | — |
| **Phase 12** | Latency and quality benchmark tuning, leak testing | Planned | — |
| **Phase 13** | Packaging, `%LOCALAPPDATA%` isolation, crash recovery | Planned | — |
| **Phase 14** | Creator-directed UI implementation | Planned | — |

---

## Key Subsystems Implemented (Phases 0–8)

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

----

## Implemented Tool Catalog

- **File Operations**: `list_files`, `find_file`, `move_file`, `rename_file`, `create_folder`
- **Application Lifecycle**: `open_app`, `close_app`, `focus_app`, `list_apps`, `app_status`
- **Window Management**: `list_windows`, `focus_window`, `minimize_window`, `maximize_window`
- **Audio Control**: `set_volume`, `mute`, `unmute`
- **System & Activity**: `get_system_status`, `battery_status`, `stop_current`, `show_activity`, `undo_last`
- **Clipboard Management**: `clear_clipboard`, `clipboard_clear`, `get_clipboard_text`, `set_clipboard_text`

----

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

# Run complete test suite (339 unit tests)
python -m pytest tests/unit/ -v
```

---

## Authoritative Project Documentation

- [`PLUMA_MASTER_SPEC.md`](PLUMA_MASTER_SPEC.md) — Authoritative product and engineering specification
- [`AGENTS.md`](AGENTS.md) — Mandatory safety and architecture contract for coding agents
- [`PLUMA_BUILD_PLAN.md`](PLUMA_BUILD_PLAN.md) — Ordered implementation phases
- [`PLUMA_ACCEPTANCE_TESTS.md`](PLUMA_ACCEPTANCE_TESTS.md) — Objective release gates
- [`PLUMA_TECH_STACK.md`](PLUMA_TECH_STACK.md) — Approved runtime libraries and technology stack
- [`PROJECT_HANDOFF.md`](PROJECT_HANDOFF.md) — Live continuity and save-state record
