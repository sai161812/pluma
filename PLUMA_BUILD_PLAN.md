# PLUMA Build Plan

This plan turns the locked specification into an implementation sequence. It
does not reduce the final scope. It controls the order so that safety,
ownership, verification and rollback exist before intelligence is added.

## How to use this plan

- Complete one phase at a time.
- Do not start a later phase until the current phase gate passes.
- Keep the architecture and public contracts stable while implementations are
  replaced behind adapters.
- Commit after every accepted phase.
- A demo milestone is not the same as product completion; the final definition
  of done remains in `PLUMA_ACCEPTANCE_TESTS.md`.

## Repository baseline

```text
pluma/
  app.py
  core/
  voice/
  perception/
  brain/
  tools/
  adapters/
  policy/
  verify/
  rollback/
  memory/
  ui/
  config/
  tests/
  data/
  cache/
  logs/
```

The complete module map is in `PLUMA_MASTER_SPEC.md`. Create the directories
and interfaces early, but do not fill them with speculative features.

## Phase 0 — Freeze contracts and benchmark harness

### Build

- Initialize the repository and Python environment.
- Add configuration loading and structured factual logging.
- Define request, task, tool, plan, result, screen snapshot and ledger schemas.
- Create the SQLite migration/schema baseline.
- Add idle CPU/RAM/GPU/process-count measurement scripts.
- Create a deterministic fixture application/script for tests.
- Define the first golden command corpus and expected routes.

### Gate

- The repository starts without loading any ML model.
- SQLite opens and migrations are repeatable.
- A ten-minute idle baseline can be recorded.
- Schema validation rejects malformed tool calls.

### Do not do yet

- Do not add an LLM, OCR or microphone worker.
- Do not add a visual UI design.

## Phase 1 — Resident core, Task Capsule and STOP

### Build

- Resident process and tray entry contract.
- Global text hotkey and dedicated STOP hotkey.
- Atomic stop latch and cancellation propagation.
- `TaskCapsule`/`TaskSupervisor` state transitions.
- Task-owned temporary directories and resource registry.
- Windows Job Object wrapper for PLUMA-owned subprocess trees.
- Crash-safe ownership metadata.

### Gate

- STOP cancels a dummy long-running task.
- STOP prevents a queued next step from starting.
- A spawned child process is ended through the ownership boundary.
- No owned worker remains after cancellation.

## Phase 2 — Typed tool framework and ledger

### Build

- `ToolSpec`, `ToolResult` and registry.
- Pydantic/jsonschema argument validation.
- Risk classes, hard timeouts and cancellability metadata.
- Executor, verifier and undo-builder hooks.
- Deterministic factual result templates.
- Queued SQLite writer and Activity query interface.

### Initial tools

```text
open_app
close_app
focus_app
list_apps
app_status
list_windows
focus_window
set_volume
mute
unmute
get_system_status
list_files
find_file
move_file
rename_file
create_folder
show_activity
stop_current
undo_last
```

### Gate

- At least ten tools execute through one registry.
- Every state change writes action, verification and risk data.
- Reversible tools produce usable undo records.

## Phase 3 — Deterministic FAST route

### Build

- Route high-confidence commands without a model or screen scan.
- Implement app launch/focus, volume/mute, known folders, clipboard, basic
  windows and system status.
- Keep the route decision explicit: `FAST`, `SCREEN`, `SMART` or `DEEP`.

### Gate

- “Open Notepad”, “Mute”, “Volume 30” and “Show activity” do not start the
  LLM, OCR or screen capture.
- Postconditions are read back and recorded.

## Phase 4 — Windows adapters

### Build

- Native/Win32 adapter.
- Controlled PowerShell adapter.
- UIA/pywinauto adapter.
- Input/SendInput adapter.
- Targeted screen capture adapter.
- Adapter priority, timeout and privilege-aware error mapping.

### Gate

- Adapters can be replaced behind interfaces.
- Access-denied and unavailable-control cases become factual failures.

## Phase 5 — Activity Ledger, redaction and rollback

### Build

- Finish `tasks`, `actions`, `undo_records`, `resources` and `screen_events`.
- Record input mode, route, active window, adapter, timings, policy decision,
  verification and stop/rollback details.
- Add deterministic templates and sensitive-value redaction.
- Implement reverse-order safe rollback.

### Gate

- `show activity/history` is reachable from the tray contract and command path.
- Raw audio, continuous screenshots, secrets and chain-of-thought are not saved
  by default.
- A stopped file move can be safely reversed.

## Phase 6 — Mandatory voice path

### Build

- Push-to-talk activation by default.
- Microphone capture and end-of-utterance/VAD handling.
- On-demand whisper.cpp adapter.
- Transcript confidence/sanity checks.
- Local SAPI response option.
- Shared cancellation token and model lifecycle.

### Gate

- Voice and text create the same request type and use the same router/tools.
- STT can be cancelled by STOP.
- Low-confidence filenames, amounts and destructive targets request
  clarification instead of guessing.
- Raw audio is transient unless explicit debug mode is enabled.

## Phase 7 — UIA perception

### Build

- Active process/window context.
- Target-window UIA snapshot.
- Semantic `ScreenElement` references and invocation capability.
- Snapshot TTL/freshness checks.
- UIA-based verification.

### Gate

- PLUMA can find and invoke a standard semantic control such as Submit.
- Active-window changes invalidate the relevant target reference.
- UIA is used even when OCR could also find the same label.

## Phase 8 — OCR fallback

### Build

- On-demand OCR worker using the selected PaddleOCR/ONNX Runtime adapter.
- Target-window or cropped-region capture only.
- OCR words, confidence and bounding boxes.
- Window-relative action fallback.
- OCR-based postcondition checks.

### Gate

- OCR runs only when UIA is insufficient.
- A fresh OCR target can ground a verified action.
- Stale or ambiguous OCR targets are rejected.
- No persistent screenshot or continuous OCR loop exists.

## Phase 9 — Replaceable local planner

### Build

- `Planner` interface and llama.cpp adapter.
- Runtime manager that starts, stops and unloads the model on demand.
- Route-specific tool-schema selection.
- JSON Schema/grammar-constrained output where supported.
- Strict second-pass validation in PLUMA.
- Model timeout, crash recovery and bounded retry.

### Gate

- The planner cannot invent tools or bypass policy.
- The model never receives the full desktop, full file tree, full ledger or all
  tool schemas by default.
- A complex file command creates a short valid plan.

## Phase 10 — Bounded multi-step orchestration

### Build

- Execute → observe → replan loop.
- Maximum plan-step limit.
- Result references and re-observation.
- Stop-latch check before every step.
- Partial-failure and residual-effect states.
- One cancellation tree for every permitted parallel child.

### Gate

- STOP during planning, OCR, shell execution and UI waiting prevents the next
  step.
- No task branch survives the final task state.

## Phase 11 — Policy and elevation

### Build

- Deterministic risk rules: READ, LOW, MEDIUM, HIGH, ADMIN, DENY.
- Concise material-effect confirmation.
- One-operation elevation broker.
- Secret redaction and denied-operation handling.

### Gate

- High-risk/admin actions cannot run silently.
- PLUMA never remains permanently elevated.
- Unsupported/unsafe operations fail closed.

## Phase 12 — Latency and quality tuning

### Measure

- Ten-minute idle CPU/RAM/GPU/process baseline.
- 100–300 golden commands with expected route/tool/risk.
- Fast-path cold/warm latency.
- STT cold/warm accuracy and latency.
- UIA latency on common apps.
- OCR accuracy/latency at 100%, 125% and 150% scaling.
- Planner accuracy/latency across candidate quantized models.
- Fifty active/idle cycles for leaks.
- STOP acknowledgement and cleanup latency.

### Gate

- Never accept a speed improvement that removes verification, policy or
  cleanup.
- Select the smallest model that passes the fixed quality suite, not the model
  with the lowest raw latency.

## Phase 13 — Packaging and hardening

### Build

- Package the resident core only for startup.
- Keep models outside the executable.
- Use `%LOCALAPPDATA%\PLUMA` for data/models/cache/logs/temp and
  `%APPDATA%\PLUMA` for user settings where appropriate.
- Local-only IPC.
- Clean shutdown and crash recovery.
- Mark stale tasks `ABORTED_BY_CRASH`.
- Clean only verifiably PLUMA-owned resources.
- Configuration migration and installer/uninstaller.

## Phase 14 — Owner-directed UI

### Build only after owner direction

- Voice/text entry.
- Current task state and material confirmations.
- Global STOP access.
- Activity view.
- Settings.
- Clear factual results/errors.

Do not invent colors, typography, cards, gradients, dashboard widgets,
waveforms, fake confidence meters, “thinking” text or an AI-themed visual
style.

## Commit sequence

```text
phase-00-contracts
phase-01-stop-foundation
phase-02-tools-ledger
phase-03-fast-route
phase-04-windows-adapters
phase-05-rollback-memory
phase-06-voice
phase-07-uia
phase-08-ocr
phase-09-planner
phase-10-orchestration
phase-11-policy
phase-12-performance
phase-13-packaging
phase-14-owner-ui
```
