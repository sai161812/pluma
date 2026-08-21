# PLUMA

**Fully local, voice-first Windows 11 AI desktop assistant.**

*Smart when active. Featherweight when idle.*

---

## 🎯 Engineering Philosophy

PLUMA is a deterministic Windows control system with a replaceable local reasoning layer, not an unpredictable chatbot. It accepts voice or text commands through a single unified pipeline, executes actions strictly via registered and typed tools, verifies every state change, captures evidence-based undo records, records factual audit history into an Activity Ledger, and unloads heavy runtimes while idle.

---

## 🚀 Core Architecture Principles

1. **Featherweight Resident Process**: Starts without loading LLM, STT, OCR, screen capture loops, or GPU inference.
2. **Unified Voice & Text Pipeline**: Voice is mandatory and shares the identical request, routing, policy, tool, verification, and ledger pipeline as text.
3. **Deterministic Typed Tools as Execution API**: Natural language is never an execution API. Every action is a registered, typed `ToolSpec`.
4. **Hierarchical Automation Priority**: Native/Application APIs $\rightarrow$ Controlled PowerShell/CLI $\rightarrow$ UI Automation (UIA) $\rightarrow$ Stable Keyboard/Input $\rightarrow$ Targeted OCR $\rightarrow$ Raw coordinates (strictly last resort).
5. **Postcondition Verification**: Every state-changing action has an explicit postcondition and must read it back before reporting success.
6. **Reversibility & Undo Evidence**: Safe pre-states are captured prior to action execution.
7. **Task Capsule & Job Object Containment**: Every command is one `TaskCapsule` owned by one `TaskSupervisor`. Subprocess trees are isolated in Windows Job Objects (`JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`).
8. **Global STOP Precedence**: Setting the atomic stop latch immediately terminates execution and prevents new tool steps or branches.
9. **Factual Activity Ledger**: Deterministic, template-generated SQLite history with automatic sensitive data redaction.

---

## 📊 Build & Phase Status

| Phase | Description | Status | Tests |
|---|---|---|---|
| **Phase 0** | Freeze contracts, schemas, SQLite baseline, benchmarks, golden corpus | ✅ Complete | 65 |
| **Phase 1** | Resident Core, Task Capsule, Windows Job Objects, atomic STOP sequence | ✅ Complete | 82 |
| **Phase 2** | Typed tool framework, initial 19 tools, postcondition verifiers, ledger | ✅ Complete | 101 |
| **Phase 3** | Deterministic FAST route, Router, Fast Orchestrator, clipboard & window tools | ✅ Complete | **220** |
| **Phase 4** | Windows Automation Adapters (Win32, PowerShell, UIA, Input, Screen) | ⏳ Next Up | — |
| **Phase 5** | Activity Ledger completion, redaction engine, reverse-order rollback | 📋 Planned | — |
| **Phase 6** | Mandatory voice path (push-to-talk, VAD, whisper.cpp on-demand) | 📋 Planned | — |
| **Phase 7** | UIA perception worker (ScreenElement semantic grounding, snapshot TTL) | 📋 Planned | — |
| **Phase 8** | Targeted OCR fallback (PaddleOCR/ONNX region-only) | 📋 Planned | — |
| **Phase 9** | Replaceable local planner (llama.cpp on-demand manager) | 📋 Planned | — |
| **Phase 10** | Bounded multi-step orchestration (execute-observe-replan loop) | 📋 Planned | — |
| **Phase 11** | Policy engine, risk classifications, elevation broker | 📋 Planned | — |
| **Phase 12** | Latency and quality benchmark tuning, leak testing | 📋 Planned | — |
| **Phase 13** | Packaging, `%LOCALAPPDATA%` isolation, crash recovery | 📋 Planned | — |
| **Phase 14** | Owner-directed UI implementation | 📋 Planned | — |

---

## 🛠️ Implemented Tools (Phase 2 & 3)

- **File Operations**: `list_files`, `find_file`, `move_file`, `rename_file`, `create_folder`
- **Application Lifecycle**: `open_app`, `close_app`, `focus_app`, `list_apps`, `app_status`
- **Window Management**: `list_windows`, `focus_window`, `minimize_window`, `maximize_window`
- **Audio Control**: `set_volume`, `mute`, `unmute`
- **System & Memory**: `get_system_status`, `battery_status`, `stop_current`, `show_activity`, `undo_last`
- **Clipboard Management**: `clear_clipboard`, `clipboard_clear`, `get_clipboard_text`, `set_clipboard_text`

---

## ⚙️ Requirements & Development Setup

- **OS**: Windows 11 (64-bit)
- **Python**: Python 3.12+

```powershell
# Set up virtual environment
python -m venv .venv
.venv\Scripts\Activate.ps1

# Install dependencies
pip install -r requirements-dev.txt
pip install -e .

# Run test suite
python -m pytest tests/unit/ -v
```

---

## 📚 Authoritative Project Documentation

- [`PLUMA_MASTER_SPEC.md`](PLUMA_MASTER_SPEC.md) — Authoritative product and engineering specification
- [`AGENTS.md`](AGENTS.md) — Mandatory safety and architecture contract for coding agents
- [`PLUMA_BUILD_PLAN.md`](PLUMA_BUILD_PLAN.md) — Ordered implementation phases
- [`PLUMA_ACCEPTANCE_TESTS.md`](PLUMA_ACCEPTANCE_TESTS.md) — Objective release gates
- [`PLUMA_TECH_STACK.md`](PLUMA_TECH_STACK.md) — Approved runtime libraries and technology stack
- [`PROJECT_HANDOFF.md`](PROJECT_HANDOFF.md) — Live continuity and save-state record
