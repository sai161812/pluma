**PLUMA**

**LOCAL VOICE + SCREEN-AWARE WINDOWS AGENT**

**Final Build Guide and Engineering Specification**

<table>
<colgroup>
<col style="width: 100%" />
</colgroup>
<thead>
<tr class="header">
<th><p><strong>ENGINEERING PHILOSOPHY</strong></p>
<p>Smart when active. Featherweight when idle. Fast without skipping
required reasoning, safety, verification, or cleanup.</p></th>
</tr>
</thead>
<tbody>
</tbody>
</table>

Target: Windows 11 \| Local-first \| Offline-capable \| Voice-native \|
Screen-aware \| Model-replaceable

Engineering baseline: August 2026

# **Contents**

1\. Final product definition and locked scope

2\. Practical buildability verdict

3\. Non-negotiable engineering laws

4\. Runtime states and elastic intelligence

5\. Final architecture

6\. Command lifecycle

7\. Voice subsystem - mandatory

8\. Screen perception - UIA + OCR

9\. Latency and quality governor

10\. Planner and model strategy

11\. Deterministic tool system and Windows control priority

12\. Task Supervisor and essential STOP

13\. Undo, rollback, cleanup and orphan prevention

14\. Policy, elevation and dangerous boundaries

15\. Verification contract

16\. Local memory and Activity Ledger

17\. UI ownership and anti-slop contract

18\. Recommended technology stack

19\. Project structure

20\. Data model and schemas

21\. Initial tool catalog

22\. Complete build sequence

23\. Performance engineering and latency budgets

24\. Testing and failure injection

25\. Packaging, startup and crash recovery

26\. Example command traces

27\. Practical limitations and non-goals

28\. Definition of done

Appendix A. Configuration baseline

Appendix B. Technology validation references

# **1. Final product definition and locked scope**

PLUMA is a fully local Windows 11 agent that accepts voice or text
commands, understands the current screen when the task requires it,
plans only when deterministic routing is insufficient, executes through
controlled Windows tools, verifies the result, records exactly what
happened, and returns heavy components to an idle state after use.

<table>
<colgroup>
<col style="width: 100%" />
</colgroup>
<thead>
<tr class="header">
<th><p><strong>LOCKED PRODUCT CLAIM</strong></p>
<p>PLUMA is not a chatbot that happens to control Windows. It is a
Windows control system with a replaceable local reasoning
layer.</p></th>
</tr>
</thead>
<tbody>
</tbody>
</table>

## **1.1 Locked user-facing capabilities**

- Voice is mandatory. Voice commands enter the same execution pipeline
  as text commands; voice is not a later add-on.

- Screen-aware execution is mandatory. PLUMA can inspect the
  active/target window, read semantic controls, use OCR when needed, and
  act on what is visible.

- An essential global STOP is mandatory. It cancels the complete current
  task, prevents new branches/actions, terminates PLUMA-owned task
  workers when necessary, rolls back safe reversible changes, cleans
  task-owned resources, and returns the system to idle.

- Latency is task-sensitive. Simple deterministic tasks bypass models;
  complex tasks may spend more time only where reasoning/perception is
  required. Required safety and verification are never removed for
  speed.

- Heavy ML components are on-demand. LLM, STT, OCR, and any optional
  perception runtime are cold or unloaded while idle and may remain warm
  only for a short measured grace period.

- A local Activity Ledger is mandatory. It records necessary task detail
  and can be viewed inside PLUMA through an Activity view reachable from
  the tray and command interface.

- UI appearance is not defined by this build guide. Functional surfaces
  are specified; visual design is reserved for the project owner.

- User-facing and stored text must be plain, factual, concise, and
  deterministic. No model chatter, fake “thinking,” decorative AI
  language, or generated corporate filler.

## **1.2 Name**

The project name is PLUMA. All implementation paths, package names,
database names, UI labels, documentation, and configuration must use
PLUMA. The old FEATHER name is retired.

# **2. Practical buildability verdict**

The complete design is practically buildable on Windows 11 if it is
implemented in layers and if “screen understanding” is defined
correctly. The reliable core is native APIs + UI Automation + OCR
fallback, not unrestricted pixel clicking. Microsoft UI Automation
exposes semantic desktop elements and supports programmatic
manipulation; this makes ordinary desktop automation far more stable
than coordinate-only agents.

| **Area**                                        | **Buildability**            | **Engineering conclusion**                                                                                                            |
|-------------------------------------------------|-----------------------------|---------------------------------------------------------------------------------------------------------------------------------------|
| Resident core, hotkeys, tray, IPC               | High                        | Straightforward with Win32/Python. Keep it separate from ML runtimes.                                                                 |
| Files/apps/windows/processes/audio/system tools | High                        | Use native APIs and typed wrappers. These should form the strongest part of V1.                                                       |
| Voice input                                     | High                        | whisper.cpp supports Windows, CPU/GPU inference, quantization and VAD. Run on demand.                                                 |
| Semantic desktop control                        | High to medium              | UIA works well for standard Win32/WPF/WinForms/UWP-style controls. Custom canvases vary.                                              |
| OCR-grounded screen actions                     | Medium to high              | Buildable for visible text and geometry. Reliability depends on OCR quality, DPI, scaling, and app rendering.                         |
| Arbitrary visual-only screen understanding      | Medium / not guaranteed     | Do not claim universal coverage in V1. Textless canvases and inaccessible custom controls need app-specific or later vision adapters. |
| Local small-model planning                      | High                        | Use a constrained, tool-only planner with schema validation; model is replaceable.                                                    |
| Global stop + process cleanup                   | High                        | Windows Job Objects can group PLUMA-owned subprocess trees; cooperative cancellation handles in-process work.                         |
| Undo/rollback                                   | High for reversible actions | Must be tool-specific. External/irreversible commits cannot be promised as undoable.                                                  |
| Local action memory                             | High                        | SQLite is appropriate for local application storage and requires no server.                                                           |

<table>
<colgroup>
<col style="width: 100%" />
</colgroup>
<thead>
<tr class="header">
<th><p><strong>BUILDABILITY RULE</strong></p>
<p>Do not try to make PLUMA “general computer intelligence” first. Build
a deterministic Windows automation system first, then add reasoning only
where deterministic control cannot resolve the user request.</p></th>
</tr>
</thead>
<tbody>
</tbody>
</table>

# **3. Non-negotiable engineering laws**

1\. Nothing heavy runs merely because PLUMA is installed.

2\. Natural language is never the execution API. Typed tools are the
execution API.

3\. Voice is a first-class input, not a separate agent.

4\. Prefer native/app APIs, then UIA, then OCR-grounded input, then raw
coordinates only as a last resort.

5\. Every state-changing operation is verified before PLUMA reports
success.

6\. Every reversible operation captures enough prior state to build an
undo record.

7\. Every task is owned by one Task Supervisor and one cancellation
tree. No uncontrolled background branches.

8\. STOP has priority over the planner, OCR, STT, UI interaction and
tool workers.

9\. If STOP occurs, no new action may begin after the stop latch is set.

10\. PLUMA never force-kills a process merely because it interacted with
it. Force termination is limited to PLUMA-owned workers/processes unless
the user explicitly requested termination of another process.

11\. Latency optimization may remove unnecessary computation, never
required quality checks.

12\. Activity history is factual system data, not LLM-written narrative.

13\. No UI visual design is chosen until the project owner specifies it.

14\. No feature is added because it “looks AI.” Every component must
solve a concrete execution problem.

# **4. Runtime states and elastic intelligence**

PLUMA must change its resource footprint according to the command.
“Elastic intelligence” means the resident process is tiny, while STT,
OCR and planning runtimes wake only when needed and return to cold/idle
after the task or a short grace period.

| **State**     | **What may run**                                                                                                                                                                       | **What must not run**                                                                                                  |
|---------------|----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|------------------------------------------------------------------------------------------------------------------------|
| IDLE          | Resident core, global hotkeys, STOP listener, tray entry, tiny config cache, IPC endpoint, task-state guard. Optional wake-phrase detector only if explicitly enabled and benchmarked. | LLM weights, Whisper/STT model, OCR model/runtime, screen capture loop, browser driver, embedding model, GPU workload. |
| LISTENING     | Microphone capture, VAD, STT runtime, resident core.                                                                                                                                   | OCR/LLM unless the transcribed command actually needs them.                                                            |
| FAST ACTIVE   | Resident core + one or more deterministic tools + verifier.                                                                                                                            | LLM/OCR if intent and target are already unambiguous.                                                                  |
| SCREEN ACTIVE | UIA inspection; targeted screenshot/OCR only if required; deterministic interaction; verifier.                                                                                         | Whole-desktop continuous OCR or unrelated models.                                                                      |
| SMART ACTIVE  | Local planner + only relevant tool schemas/context + required tools.                                                                                                                   | Full desktop tree, full tool registry, unrelated models.                                                               |
| WARM GRACE    | Recently used model process may remain warm for a short configurable period if measured benefit is meaningful.                                                                         | Unbounded background residency.                                                                                        |
| STOPPING      | Cancellation supervisor, rollback engine, cleanup, verifier/ledger.                                                                                                                    | New planner calls, new tool starts, new branches.                                                                      |

Default recommendation: use push-to-talk as the always-available voice
activation for V1 because it preserves a near-zero idle ML footprint. A
wake phrase may be enabled as a separate low-cost activation mode after
measuring its continuous CPU/RAM cost. Voice itself remains mandatory
either way.

# **5. Final architecture**

> USER VOICE / TEXT  
> \|  
> v  
> RESIDENT CORE + TASK SUPERVISOR + GLOBAL STOP  
> \|  
> +--\> Voice Capture -\> Local STT --------+  
> \| \|  
> +--------------------------------------v  
> INTENT / ROUTE GATE  
> \| \| \|  
> \| \| +--\> SCREEN CONTEXT  
> \| \| UIA -\> OCR fallback  
> \| \|  
> \| +--\> LOCAL PLANNER (on demand)  
> \|  
> +--\> DETERMINISTIC FAST PATH  
> \|  
> v  
> TOOL REGISTRY  
> \|  
> POLICY / AUTH  
> \|  
> EXECUTION ADAPTERS  
> \|  
> VERIFICATION  
> \|  
> ACTION + UNDO LEDGER  
> \|  
> RESULT / VOICE RESPONSE

## **5.1 Component boundaries**

| **Component**     | **Responsibility**                                                                  | **Must not do**                                                 |
|-------------------|-------------------------------------------------------------------------------------|-----------------------------------------------------------------|
| Resident Core     | Hotkeys, voice trigger, STOP, IPC, request creation, runtime lifecycle, task state. | Load heavy ML at startup.                                       |
| Intent/Route Gate | Choose FAST, SCREEN, SMART or combined path using deterministic rules first.        | Pretend certainty when command is ambiguous.                    |
| Perception Layer  | Active-window identity, UIA tree, targeted capture, OCR, screen-element references. | Continuously watch or store the desktop.                        |
| Planner           | Translate ambiguous natural language + context into typed tools/short plans.        | Directly press keys, click pixels, run shell, or bypass policy. |
| Tool Registry     | Define capabilities, schemas, risk, timeout, verifier, undo builder, adapter order. | Let tools exist without metadata/contracts.                     |
| Policy Engine     | Allow/confirm/elevate/deny exact tool calls.                                        | Ask the LLM whether an action is safe.                          |
| Executor          | Run one validated tool call through selected adapter.                               | Start untracked subprocesses.                                   |
| Task Supervisor   | Own task state, cancellation, child processes/resources, stop and cleanup.          | Allow detached task branches.                                   |
| Verifier          | Read back the resulting state using the strongest available method.                 | Trust “no exception” as proof of success.                       |
| Activity Ledger   | Persist factual task/action history, timings, verification, undo, stop and errors.  | Generate narrative explanations with an LLM.                    |

# **6. Command lifecycle**

1\. Capture voice or text and assign request_id/task_id.

2\. If voice: run local VAD/STT and normalize only obvious transcription
artifacts; retain the original transcript in task metadata.

3\. Latch the task into RUNNING state under the Task Supervisor.

4\. Capture minimal context: active process/window and only the
screen/UI state required by the request.

5\. Try deterministic routing first.

6\. If the command depends on what is visible, inspect UIA first. Invoke
OCR only when semantic controls/text are missing or insufficient.

7\. If deterministic routing still cannot resolve intent or sequence,
start the local planner and send the minimum context + permitted tool
schemas.

8\. Validate planner output against schema. Reject invented tools,
unknown references, stale screen targets, excessive steps and malformed
arguments.

9\. Run deterministic policy on the exact tool call.

10\. Capture pre-state for reversible operations.

11\. Execute under task ownership and hard timeout.

12\. Verify result using API/UIA/OCR/state read-back as appropriate.

13\. Write action + verification + undo information to the local ledger.

14\. For multi-step work, continue only if the task stop latch is clear
and the previous step is in an allowed terminal state.

15\. On success/failure/stop: close task-owned resources, release
workers, mark task final, and move heavy runtimes toward WARM/COLD
according to policy.

16\. Return one concise factual result and optionally speak it locally.

# **7. Voice subsystem - mandatory**

Voice is a required PLUMA interface. It feeds the exact same request
pipeline as typed text; there is no separate “voice brain.” This
prevents duplicated logic, inconsistent safety rules and extra idle
processes.

## **7.1 Recommended voice path**

> Push-to-talk / enabled wake trigger  
> -\> microphone capture  
> -\> VAD / end-of-utterance detection  
> -\> whisper.cpp local STT  
> -\> transcript confidence / sanity checks  
> -\> normal PLUMA request pipeline  
> -\> concise local TTS/result (optional output mode, not a separate
> agent)

- Use whisper.cpp as the reference STT runtime because it supports
  Windows, CPU/GPU inference, quantization and VAD while remaining
  local.

- Do not keep the STT model resident indefinitely. Start/map it when
  listening begins; keep it warm only briefly if follow-up voice
  commands are likely.

- If STT confidence is low on a material target such as a filename,
  destructive command or amount, require clarification instead of
  guessing.

- Voice cancellation must obey the same STOP token as every other
  module.

- Microphone audio is transient by default. Do not save raw audio unless
  an explicit debug setting is enabled.

# **8. Screen perception - UIA + OCR**

PLUMA must be able to execute commands relative to what the user
currently sees. The perception system is deliberately hybrid: UI
Automation provides semantic structure; OCR reads visible text where
semantic accessibility is incomplete. OCR is not used as a reason to
abandon stronger control methods.

## **8.1 Perception priority**

| **Priority** | **Method**             | **Use**                                                                                         | **Why**                                                  |
|--------------|------------------------|-------------------------------------------------------------------------------------------------|----------------------------------------------------------|
| 1            | App/native API         | Known application data/actions, system state.                                                   | Strongest semantics and lowest brittleness.              |
| 2            | Windows UI Automation  | Buttons, text fields, menus, lists, dialogs, window/control state.                              | Semantic control identities, names, patterns and events. |
| 3            | Targeted OCR           | Visible labels/text not exposed through UIA; canvas/web regions when text is rendered visually. | Adds text + bounding boxes only when needed.             |
| 4            | Keyboard/shortcut      | Stable application shortcuts or focus-based operations.                                         | Often more robust than pixel clicking.                   |
| 5            | Coordinate interaction | Only a known, current, window-relative OCR/screen target.                                       | Last resort; must be freshness-checked and verified.     |

## **8.2 Screen snapshot contract**

> ScreenSnapshot {  
> snapshot_id  
> created_at  
> active_process  
> active_window_title  
> window_rect  
> dpi_scale  
> controls\[\] \# UIA-derived semantic controls  
> ocr_words\[\] \# text + confidence + bounding boxes, only if OCR ran  
> image_ref \# ephemeral, not persisted by default  
> expires_at  
> }  
>   
> ScreenElement {  
> element_id  
> snapshot_id  
> source: UIA \| OCR  
> label  
> control_type?  
> bounds  
> confidence  
> invocation_capability  
> }

- ScreenElement references expire quickly. Before a coordinate-based
  action, re-check active window identity and target geometry to prevent
  clicking stale locations.

- OCR runs on the active window or a cropped region, never the full
  desktop by default.

- Do not persist screenshots by default. The Activity Ledger stores only
  necessary target metadata such as app/window, label/control identity,
  confidence and geometry.

- If a target can be invoked through UIA, use the semantic control even
  when OCR also found matching text.

- If the command refers to a purely visual, textless object that UIA
  cannot expose, V1 must return a bounded failure instead of guessing.
  This is a practical limitation, not a reason to fake success.

## **8.3 OCR engine baseline**

Use an on-demand local OCR worker. A practical baseline is a lightweight
PaddleOCR/ONNX Runtime configuration using tiny/small text detection and
recognition models. Windows.Media.Ocr is worth benchmarking for a
packaged MSIX build, but Microsoft documents package-identity
requirements for desktop use, so it should not be the only V1 path.

# **9. Latency and quality governor**

PLUMA does not have one universal latency target. The routing layer
selects the cheapest path that can complete the task correctly. Required
reasoning, policy and verification are never skipped merely to hit a
number.

| **Route** | **Example**                                                        | **Allowed components**                                                    | **Latency rule**                                                               |
|-----------|--------------------------------------------------------------------|---------------------------------------------------------------------------|--------------------------------------------------------------------------------|
| FAST      | “Mute”, “Volume 30”, “Open Notepad”                                | Router + deterministic tool + verifier.                                   | No LLM, no OCR.                                                                |
| SMART     | “Move yesterday’s DBMS PDF to my college folder”                   | Small local planner + file tools + verifier.                              | Use model only for interpretation/decomposition.                               |
| SCREEN    | “Click Submit on this screen”                                      | UIA; OCR only if UIA cannot resolve target; verifier.                     | No planner if target and intent are already unambiguous.                       |
| DEEP      | “Look at this setup screen and finish the remaining configuration” | UIA + targeted OCR + local planner + bounded multi-step tools + verifier. | Spend time where needed; keep plan bounded and re-check state after each step. |

<table>
<colgroup>
<col style="width: 100%" />
</colgroup>
<thead>
<tr class="header">
<th><p><strong>QUALITY RULE</strong></p>
<p>The optimization target is wasted work, not thought itself. Remove
unnecessary model calls, broad screenshots, repeated scans and oversized
prompts. Do not remove the verification or policy step that makes the
action trustworthy.</p></th>
</tr>
</thead>
<tbody>
</tbody>
</table>

# **10. Planner and model strategy**

The local model is a planner and parser, not the operating system. Its
job is limited to intent interpretation, argument extraction, target
disambiguation, short decomposition and optional replanning after tool
results.

- Runtime baseline: llama.cpp launched locally through a replaceable
  adapter.

- Use a small instruction model that benchmarks well on PLUMA’s fixed
  tool-selection suite. Do not hard-code the architecture to one model
  family.

- Constrain outputs with JSON schema/grammar where supported, then
  validate again in PLUMA. Structured generation reduces errors but is
  not a reason to trust unvalidated model output.

- Temperature should be deterministic/low for tool planning.

- Never provide the model with the complete desktop state, full file
  tree, full Activity Ledger or all tool schemas by default.

- Tool schema selection should be route-specific. For a file task, send
  file tools; for a screen task, send perception/interaction tools; for
  system audio, usually skip the model entirely.

- Plans should be short. Prefer execute -\> observe -\> replan over a
  long speculative chain.

> Planner.plan(  
> command,  
> context,  
> permitted_tool_specs,  
> screen_snapshot=None,  
> prior_step_results=None  
> ) -\> Plan  
>   
> \# Planner may propose only registered ToolCalls.  
> \# Planner never imports pywinauto, Win32, PowerShell, OCR or shell
> libraries.

# **11. Deterministic tool system and Windows control priority**

Every real action is a registered tool. A tool is a contract used by the
router, planner, policy engine, Task Supervisor, verifier, Activity
Ledger and tests.

> ToolSpec {  
> name  
> description  
> args_schema  
> risk_class  
> timeout_s  
> executor  
> verifier  
> undo_builder?  
> adapter_priority\[\]  
> cancellable  
> creates_resources?  
> }  
>   
> ToolResult {  
> ok  
> tool  
> data  
> factual_message  
> verified  
> duration_ms  
> error?  
> undo_record?  
> }

## **11.1 Adapter priority**

1\. Native Windows API or application API.

2\. Controlled PowerShell/CLI wrapper.

3\. Windows UI Automation / pywinauto semantic control.

4\. Stable keyboard shortcut / SendInput.

5\. OCR-grounded window-relative interaction.

6\. Raw pixel coordinate only when tied to a fresh validated snapshot
and no stronger method exists.

# **12. Task Supervisor and essential STOP**

The Task Supervisor is the highest-priority runtime authority. Every
user command becomes one Task Capsule. All tool calls, temporary
resources, subprocesses, screen snapshots, undo records and execution
branches belong to that capsule.

> TaskCapsule {  
> task_id  
> request_id  
> state: CREATED \| RUNNING \| STOPPING \| ROLLING_BACK \| SUCCEEDED \|
> FAILED \| STOPPED  
> cancellation_token  
> steps\[\]  
> owned_processes\[\]  
> owned_temp_resources\[\]  
> owned_windows_tabs\[\]  
> preexisting_resource_refs\[\]  
> undo_stack\[\]  
> current_step  
> }

## **12.1 Global STOP requirements**

- A dedicated global hotkey must be handled by the resident core, not by
  the planner or UI worker.

- On activation, set an atomic stop latch first. After that exact
  moment, the orchestrator must reject every new step/tool start for the
  task.

- Propagate the same cancellation token to planner inference, STT, OCR,
  UI waits, shell/CLI calls and tool workers.

- Cooperatively cancel in-process work first. Do not corrupt files or
  application state by force-terminating an operation that has a safe
  cancellation path.

- If a PLUMA-owned worker/process does not stop within a small bounded
  grace period, terminate only that owned task worker/process tree.

- Use a Windows Job Object for task-spawned subprocesses and set
  kill-on-job-close behavior where appropriate. This gives a hard
  boundary for PLUMA-owned descendants even if a worker tries to spawn
  children.

- Immediately stop planner-generated branching. Any explicit parallel
  tasks must still be children of the same Task Capsule and cancellation
  tree.

- Rollback safe reversible completed steps in reverse order unless doing
  so would be more destructive than leaving them in place.

- Close only task-owned temporary windows/tabs/resources. Never close an
  application merely because it existed during the task; distinguish
  PREEXISTING from PLUMA_CREATED.

- After cleanup, verify the task has no active owned worker and mark
  STOPPED. If an irreversible external action already committed, record
  it clearly as not rolled back.

## **12.2 STOP sequence**

> STOP HOTKEY  
> -\> atomic task.stop_latch = true  
> -\> block new ToolCalls / replans  
> -\> cancel active inference / OCR / STT / UI waits  
> -\> request graceful cancellation from current tool  
> -\> terminate unresponsive PLUMA-owned Job Object workers  
> -\> rollback safe reversible actions, newest first  
> -\> close/delete task-owned temporary resources  
> -\> verify cleanup  
> -\> ledger: STOPPED + rollback results + residual irreversible
> effects  
> -\> unload/idle heavy runtimes

<table>
<colgroup>
<col style="width: 100%" />
</colgroup>
<thead>
<tr class="header">
<th><p><strong>STOP IS NOT “KILL EVERYTHING”</strong></p>
<p>The stop path is strict about PLUMA’s own task, but conservative
about the user’s pre-existing applications and data. It must end the
automation without creating a second disaster during cleanup.</p></th>
</tr>
</thead>
<tbody>
</tbody>
</table>

# **13. Undo, rollback, cleanup and orphan prevention**

Undo is tool-specific and evidence-based. Before a reversible state
change, the executor captures only the minimum previous state required
to restore it. Rollback is used automatically for a stopped/failed task
when the rollback policy says restoration is safe.

| **Action**                                 | **Pre-state**                        | **Undo behavior**                                                                 |
|--------------------------------------------|--------------------------------------|-----------------------------------------------------------------------------------|
| rename_file                                | Original path/name                   | Rename back if destination/source state is still safe.                            |
| move_file                                  | Original path + destination metadata | Move back if no conflicting user change occurred.                                 |
| set_volume                                 | Previous volume/mute state           | Restore previous audio value.                                                     |
| move/resize window                         | Previous window rectangle/state      | Restore geometry/state.                                                           |
| create temporary folder/file               | Ownership + created path             | Delete only if still task-owned and unchanged as expected.                        |
| open temporary tab/window                  | Ownership marker/ref                 | Close task-owned instance only.                                                   |
| send email / submit form / external commit | No reliable local inverse            | Mark non-undoable; confirmation policy applies before commit.                     |
| permanent delete / system restart          | Potentially irreversible             | Prefer safe alternatives/confirmation; STOP cannot promise reversal after commit. |

- No detached threads that can outlive the Task Capsule.

- No subprocess created outside the process/resource registry.

- Every subprocess records PID, creation time, command class, task_id
  and ownership.

- Task temporary files live under a task-specific temp directory and are
  removed on success/stop unless intentionally promoted to a user
  result.

- On PLUMA startup, stale tasks are marked ABORTED and residual temp
  metadata is checked. Job-object kill-on-close should already have
  prevented live task child processes when the resident crashed.

# **14. Policy, elevation and dangerous boundaries**

Broad control does not mean permanent administrator privilege. The
policy engine is deterministic and evaluates the exact validated tool
arguments before execution.

| **Class**        | **Examples**                                                                                              | **Default**                                                                    |
|------------------|-----------------------------------------------------------------------------------------------------------|--------------------------------------------------------------------------------|
| READ             | Inspect windows, list files/processes, read system status.                                                | Allow; log.                                                                    |
| LOW              | Open app, set volume, focus/resize window, type into explicitly targeted field.                           | Allow; log; verify.                                                            |
| MEDIUM           | Move/rename files, terminate a normal user app, change user-level setting.                                | Allow only when the user request is explicit; capture undo when possible.      |
| HIGH             | Bulk overwrite/delete, startup changes, software removal, sensitive settings, irreversible UI submission. | Require concise material-effect confirmation.                                  |
| ADMIN            | System-wide operations requiring elevation.                                                               | Use one-operation elevation broker/UAC. Never keep PLUMA permanently elevated. |
| DENY/UNSUPPORTED | Operation violates PLUMA policy or cannot be safely grounded.                                             | Refuse/bounded failure; never improvise around the guard.                      |

Credentials/secrets must be handled outside model context whenever
possible. Stored logs redact tokens, passwords, private clipboard values
and other sensitive data. UIA also has privilege boundaries; Microsoft
notes that UI Automation does not automatically bridge processes started
under different users/elevation contexts.

# **15. Verification contract**

No state-changing tool may report success only because the call returned
without an exception. The tool defines a postcondition and reads the
state back using the strongest method available.

| **Tool example** | **Verification**                                                                                              |
|------------------|---------------------------------------------------------------------------------------------------------------|
| set_volume       | Read current endpoint volume/mute and compare within tolerance.                                               |
| move_file        | Destination exists with expected identity/metadata; source state matches move semantics.                      |
| open_app         | Expected process/window appears within timeout.                                                               |
| close_app        | Target process/window exits or graceful close refusal is surfaced.                                            |
| invoke_control   | Expected control/window/state transition appears through UIA.                                                 |
| OCR click        | Re-scan target/expected region or detect expected window/control change; do not trust the click event itself. |
| run_command      | Exit code + stdout/stderr + optional state postcondition.                                                     |
| STOP cleanup     | No owned task worker remains; rollback results accounted for; final task state persisted.                     |

If verification fails, the orchestrator may use a defined fallback or
re-observe/replan within step limits. It must never fabricate success
text.

# **16. Local memory and Activity Ledger**

PLUMA’s local memory has two roles: deterministic preferences/routines
for future execution, and an Activity Ledger that records what PLUMA
actually did. V1 does not require an always-running vector database.

## **16.1 Where the user views it**

The Activity Ledger is exposed through a functional “Activity” view
inside PLUMA. It must be reachable from the tray menu and from a command
such as “show activity/history.” This guide intentionally does not
define its appearance, layout, colors, typography, animation or
component styling.

## **16.2 What each task records**

- Task ID, timestamps and final state.

- Original text command or voice transcript.

- Input mode (voice/text) and active app/window context when materially
  relevant.

- Route used: FAST / SCREEN / SMART / DEEP.

- Each executed tool, sanitized arguments, adapter used and duration.

- Pre-state reference and undo record for reversible changes.

- Policy classification and whether confirmation/elevation occurred.

- Verification method and result.

- STOP event, rollback attempts/results and any residual non-undoable
  action.

- Errors/timeouts in factual technical language.

## **16.3 What is not stored by default**

- Raw microphone audio.

- Continuous screenshots or video.

- Full desktop OCR dumps unrelated to the requested task.

- Passwords, auth tokens or sensitive clipboard values.

- LLM chain-of-thought or hidden reasoning.

- Generated narrative summaries such as “I successfully completed your
  amazing workflow.”

## **16.4 Plain-text logging rule**

User-visible Activity messages must be generated from deterministic
templates owned by the executor, not by the LLM. Examples: “Opened
Notepad”, “Moved 1 file”, “Stopped task”, “Rollback: restored volume to
40%”, “Could not verify Submit action”. This keeps history useful,
compact and non-AI-looking.

# **17. UI ownership and anti-slop contract**

The build guide defines required functional surfaces only. The project
owner decides how the interface looks. Developers must not invent a
visual style or “AI dashboard” during implementation.

## **17.1 Required functional surfaces only**

- Voice/text command entry.

- Current task state and material confirmations.

- Global STOP access plus its keyboard hotkey.

- Activity Ledger/history access.

- Settings for behavior such as hotkeys, model path, warm grace period,
  voice activation mode and privacy/logging toggles.

- Clear error/result messages.

## **17.2 Explicitly not specified until owner direction**

- Color palette, dark/light appearance, gradients, glass effects, cards,
  shadows, borders.

- Logo/icon treatment, typography, spacing, layout, animation, waveform
  style or microphone visuals.

- Dashboard-style widgets, charts or “AI brain” illustrations.

- Any decorative status text such as “Thinking...”, “Analyzing your
  world...”, “Agentic mode”, fake confidence meters or fake intelligence
  indicators.

## **17.3 Text style**

All visible and stored text should read like a precise native utility:
short action labels, direct confirmations, concrete errors and no
unnecessary personality layer. The model may understand natural language
internally; the product should not sound like generated marketing copy.

# **18. Recommended technology stack**

| **Concern**           | **Baseline**                                                                               | **Reason / note**                                                                                                          |
|-----------------------|--------------------------------------------------------------------------------------------|----------------------------------------------------------------------------------------------------------------------------|
| Core language         | Python 3.12+                                                                               | Fast iteration and strong Windows automation ecosystem. Performance-critical native pieces can move behind adapters later. |
| Windows native access | pywin32 + ctypes                                                                           | Win32, process/job objects, hotkeys, windows, named pipes and system calls.                                                |
| UI automation         | pywinauto UIA/Win32 adapter                                                                | Semantic control access before pixels.                                                                                     |
| Speech-to-text        | whisper.cpp                                                                                | Local, Windows-capable, quantized, CPU/GPU-capable, VAD support.                                                           |
| Planner inference     | llama.cpp local process/server adapter                                                     | Quantized local inference, replaceable model, grammar/JSON-schema constrained output options.                              |
| OCR                   | PaddleOCR tiny/small local models through an on-demand worker; benchmark ONNX Runtime path | Better fit for rendered UI text than simplistic OCR-only pipelines; nothing resident while idle.                           |
| Screen capture        | Target-window/region capture adapter; lightweight Windows capture implementation           | Capture only when screen context is needed; no loop.                                                                       |
| Persistence           | SQLite                                                                                     | Local, serverless, reliable application database.                                                                          |
| Schemas               | Pydantic / jsonschema                                                                      | Strict validation of plans and tools.                                                                                      |
| IPC                   | Windows named pipe or equivalent local-only IPC                                            | Keep heavy workers isolated without exposing a network service.                                                            |
| Process ownership     | Windows Job Objects                                                                        | Hard ownership/termination boundary for PLUMA-spawned subprocess trees.                                                    |
| System scripting      | PowerShell via controlled subprocess wrapper                                               | Broad Windows coverage; bounded timeouts and policy.                                                                       |
| Packaging             | PyInstaller or Nuitka for V1; MSIX evaluation later                                        | Standalone deployment first; packaged identity may unlock native OCR paths later.                                          |
| Tests                 | pytest + deterministic fixture apps/scripts                                                | Repeatable adapter, policy, stop, rollback and latency tests.                                                              |

<table>
<colgroup>
<col style="width: 100%" />
</colgroup>
<thead>
<tr class="header">
<th><p><strong>DEPENDENCY RULE</strong></p>
<p>Disk size is not the same as idle footprint. It is acceptable to ship
local models/runtimes on disk if they remain unloaded and consume
effectively no CPU/GPU while idle.</p></th>
</tr>
</thead>
<tbody>
</tbody>
</table>

# **19. Project structure**

> pluma/  
> app.py  
> core/  
> resident.py  
> request.py  
> router.py  
> orchestrator.py  
> task_supervisor.py  
> cancellation.py  
> runtime_manager.py  
> ownership.py  
> ipc.py  
> voice/  
> capture.py  
> vad.py  
> stt_adapter.py  
> activation.py  
> perception/  
> context.py  
> uia_snapshot.py  
> capture.py  
> ocr_adapter.py  
> element_refs.py  
> freshness.py  
> brain/  
> interface.py  
> llama_cpp_adapter.py  
> prompt_builder.py  
> schemas.py  
> tool_subset.py  
> tools/  
> registry.py  
> base.py  
> files.py  
> apps.py  
> windows.py  
> processes.py  
> audio.py  
> system.py  
> clipboard.py  
> terminal.py  
> ui.py  
> browser.py  
> adapters/  
> win32.py  
> powershell.py  
> uia.py  
> input.py  
> screen.py  
> policy/  
> engine.py  
> rules.py  
> elevation_broker.py  
> verify/  
> base.py  
> common.py  
> screen.py  
> rollback/  
> engine.py  
> recipes.py  
> memory/  
> db.py  
> activity.py  
> preferences.py  
> aliases.py  
> routines.py  
> redaction.py  
> ui/  
> shell_contract.py \# functional interface only; visual design
> intentionally not specified  
> confirmations.py  
> activity_contract.py  
> settings_contract.py  
> config/  
> defaults.yaml  
> tool_policy.yaml  
> tests/  
> unit/  
> integration/  
> windows/  
> perception/  
> stop_rollback/  
> performance/  
> data/  
> pluma.db  
> cache/  
> logs/

Boundary rule: code outside adapters/perception workers must not depend
directly on pywinauto classes, OCR-library objects, PowerShell
implementation details or a specific local LLM model. The architecture
survives technology swaps.

# **20. Data model and schemas**

## **20.1 SQLite baseline**

> preferences(key PRIMARY KEY, value_json, updated_at)  
> aliases(alias PRIMARY KEY, target_json, updated_at)  
> routines(id PRIMARY KEY, name UNIQUE, definition_json, updated_at)  
>   
> tasks(  
> task_id PRIMARY KEY, request_id, input_mode, command_text,  
> created_at, started_at, completed_at, final_state,  
> route, active_process, active_window, stop_reason, error_code  
> )  
>   
> actions(  
> id PRIMARY KEY, task_id, step_index, tool, adapter,  
> args_json_sanitized, risk, approval_state,  
> started_at, ended_at, duration_ms,  
> result_json, verified, verification_json, error_json  
> )  
>   
> undo_records(  
> action_id PRIMARY KEY, undo_json, available,  
> rollback_attempted, rollback_ok, rollback_result_json  
> )  
>   
> resources(  
> id PRIMARY KEY, task_id, resource_type, ownership,  
> external_id, created_at, released_at, metadata_json  
> )  
>   
> screen_events(  
> id PRIMARY KEY, task_id, snapshot_id,  
> source, target_label, control_type, bounds_json,  
> confidence, active_window_signature, created_at  
> )

Use a single queued writer or short transactions. SQLite WAL mode is
reasonable if multiple readers (Activity view, verifier, settings)
coexist with one controlled writer. Screenshots are not part of the
baseline schema.

## **20.2 Plan schema**

> Plan {  
> task_id: string  
> mode: direct \| multi_step  
> steps: ToolCall\[\]  
> }  
>   
> ToolCall {  
> tool: string  
> arguments: object  
> target_ref?: string  
> purpose: short machine-facing reason  
> }  
>   
> Constraints:  
> - tool must exist in registry  
> - arguments must validate  
> - target_ref must belong to a current snapshot when used  
> - max steps is bounded  
> - policy runs after schema validation and before execution  
> - every step re-checks task.stop_latch before starting

# **21. Initial tool catalog**

| **Category**   | **V1 tools**                                                                                                                             |
|----------------|------------------------------------------------------------------------------------------------------------------------------------------|
| Apps           | open_app, close_app, focus_app, list_apps, app_status                                                                                    |
| Windows        | list_windows, focus_window, minimize_window, maximize_window, restore_window, move_window, resize_window                                 |
| Files          | find_file, open_file, copy_file, move_file, rename_file, create_folder, list_folder, file_info, safe_delete                              |
| Processes      | list_processes, process_usage, process_info, graceful_close_process, terminate_process                                                   |
| Audio          | get_volume, set_volume, mute, unmute, list_audio_devices, set_default_audio_device                                                       |
| System         | get_system_status, battery_status, network_status, lock, sleep_request, restart_request, shutdown_request                                |
| Clipboard      | clipboard_get, clipboard_set, clipboard_clear                                                                                            |
| Perception     | get_active_window_context, inspect_window_controls, capture_target_window, read_visible_text, find_visible_text, refresh_screen_snapshot |
| UI interaction | find_control, invoke_control, set_control_text, read_control_text, wait_for_control, invoke_screen_element                               |
| Input fallback | press_key, hotkey, type_text, click_window_relative                                                                                      |
| Terminal       | run_command, run_powershell, open_terminal                                                                                               |
| Browser        | open_url, list_tabs, focus_tab, close_tab, download_status; add browser-specific adapter only when required                              |
| Agent/memory   | save_preference, get_preference, create_routine, run_routine, show_activity, undo_last, stop_current                                     |

Do not create a tool for every possible Windows setting on day one.
Build stable high-value tools, then add typed wrappers when repeated
real tasks justify them.

# **22. Complete build sequence**

## **Phase 0 - Freeze contracts + benchmark harness**

Create repository, config, SQLite schema, structured logging,
latency/CPU/RAM/GPU benchmark scripts, fixture app, and acceptance
command set. Record idle footprint before any ML integration.

## **Phase 1 - Resident core + STOP foundation**

Build global hotkeys, tray entry, IPC, task state machine, Task
Supervisor, cancellation token, task-owned temp directory and Job Object
wrapper. Acceptance: STOP can cancel a dummy long task and leave no
child worker.

## **Phase 2 - Tool framework**

Implement ToolSpec, ToolResult, schema validation, timeouts, ownership
registration, verifier hooks, undo builders, factual messages and
Activity Ledger writes. Add at least 10 deterministic tools.

## **Phase 3 - Fast path**

Implement high-confidence direct intents: app launch/focus, volume/mute,
known folders, clipboard, basic windows, system status. Acceptance: no
LLM process starts for fast commands.

## **Phase 4 - Windows adapters**

Implement Win32/native, PowerShell, UIA and input fallback behind
interfaces. Add adapter selection/retry rules and privilege-aware
errors.

## **Phase 5 - Activity Ledger + rollback**

Finish task/action/resource/undo tables, Activity query API,
deterministic user-visible event templates, reverse-order rollback
engine, sensitive-value redaction.

## **Phase 6 - Voice mandatory path**

Integrate push-to-talk capture, VAD, whisper.cpp local STT, transcript
pipeline, cancellation and warm/cold lifecycle. Voice commands must
exercise the same fast/tool pipeline as text.

## **Phase 7 - Perception/UIA**

Build active-window snapshot, UIA control extraction, semantic
ScreenElement refs, target-window scoping and verification using UIA
events/state.

## **Phase 8 - OCR fallback**

Add targeted window/region capture, on-demand OCR worker, bounding
boxes/confidence, snapshot TTL/freshness checks and OCR-based
verification. No continuous screenshots.

## **Phase 9 - Local planner**

Integrate llama.cpp adapter, model lifecycle manager, tool-subset prompt
builder, schema/grammar constrained plan output, strict validation,
timeout, retry and model crash recovery.

## **Phase 10 - Multi-step orchestration**

Bounded plan execution, result references, re-observation, replanning,
stop-latch check before every step, partial failure states, and no
uncontrolled branching.

## **Phase 11 - Policy/elevation**

Deterministic risk rules, concise confirmation contract, one-operation
elevation broker, secret redaction and denied-operation handling.

## **Phase 12 - Latency/quality tuning**

Run the fixed command suite; remove unnecessary model/OCR starts, reduce
prompt/tool subset, crop OCR regions, tune warm grace. Reject changes
that improve speed by reducing verification/reliability.

## **Phase 13 - Packaging + hardening**

Standalone packaging, startup launch of resident core only, clean
shutdown, crash recovery, stale resource handling, configuration
migration, performance regression gates, installer/uninstaller.

## **Phase 14 - UI implementation after owner direction**

Implement the functional UI contracts only after the owner provides the
visual direction. Do not use placeholder “AI dashboard” styling as the
final design.

# **23. Performance engineering and latency budgets**

The following are engineering budgets for benchmarking, not
hardware-independent promises. Measure p50 and p95 on the target laptop.
If a smaller/faster model fails the fixed quality suite, choose the
stronger model even if it is slower.

| **Path / metric**            | **Initial target**                                             | **Notes**                                                                               |
|------------------------------|----------------------------------------------------------------|-----------------------------------------------------------------------------------------|
| Resident idle GPU            | 0% attributable ML workload                                    | No loaded LLM/STT/OCR model.                                                            |
| Resident idle CPU            | Near background noise                                          | No polling loops; event/hotkey driven.                                                  |
| Resident idle RAM            | Keep small and regression-gated                                | Set a measured baseline after Phase 1; any major increase requires justification.       |
| Command/STOP hotkey response | \<100 ms p95 to acknowledge/latch                              | STOP latch is more important than cleanup completion time.                              |
| Fast-path dispatch overhead  | \<150 ms p95 excluding OS/app response                         | No model or screen scan.                                                                |
| UIA target-window inspection | Aim \<400 ms p95 for normal windows                            | Scope only required control subtree.                                                    |
| Targeted OCR                 | Aim ~0.3-1.0 s typical depending on region/hardware            | Crop aggressively; keep accuracy requirement.                                           |
| Warm planner plan            | Aim around \<=1 s for ordinary short plans on capable hardware | Benchmark tool accuracy first.                                                          |
| Cold planner                 | Allow several seconds if model load is required                | Warm grace can reduce burst latency.                                                    |
| Voice end -\> transcript     | Benchmark warm and cold separately                             | Model size selected by accuracy, accent/noise and latency tests.                        |
| STOP cleanup/rollback        | Operation-dependent, bounded per tool                          | No new actions after latch; cleanup may take longer when safe cancellation requires it. |

## **23.1 Performance test set**

- Idle 10-minute CPU/RAM/GPU/process-count baseline.

- 100-300 fixed natural-language commands with expected route, tool,
  arguments and risk class.

- Fast-path cold/warm latency.

- STT cold/warm transcription accuracy and latency across quiet/noisy
  samples.

- UIA scan latency on common apps.

- OCR accuracy/latency at 100%, 125%, 150% Windows scaling.

- Planner accuracy/latency across candidate small quantized models.

- 50 repeated active/idle cycles to detect model/process/memory leaks.

- STOP latency while planner, OCR, shell command, UI wait and file
  operation are active.

# **24. Testing and failure injection**

PLUMA cannot be validated only by talking to it manually.
Windows-control regressions, stale screen references and cleanup
failures need deterministic tests.

| **Layer**   | **Required tests**                                                                                                                 |
|-------------|------------------------------------------------------------------------------------------------------------------------------------|
| Unit        | Schema validation, route decisions, policy classification, redaction, ledger records, undo builders, state transitions.            |
| Adapter     | Each Win32/PowerShell/UIA/OCR/input adapter, timeout mapping and access-denied behavior.                                           |
| Integration | Command -\> route -\> plan(if needed) -\> policy -\> execute -\> verify -\> ledger.                                                |
| Voice       | VAD, transcription, stop during capture/STT, low-confidence target handling, model lifecycle.                                      |
| Perception  | UIA target resolution, OCR fallback, duplicate visible labels, stale snapshot rejection, DPI/window movement.                      |
| STOP        | Planner running, OCR running, shell child tree, UI wait, multi-step task, rollback partially failing, user app pre-existing.       |
| Failure     | Hung app, locked file, denied permission, invalid model JSON, model crash, OCR failure, control disappears, active window changes. |
| Safety      | High-risk confirmation, elevation boundary, invented tool rejection, secret redaction, non-undoable commit handling.               |
| Performance | Idle footprint, cold/warm latency, unload, repeated cycles, zero orphan worker processes.                                          |
| Regression  | Golden task corpus: expected route, tools, arguments, verification and ledger output.                                              |

## **24.1 Dedicated STOP acceptance tests**

- Start a tool that spawns a child process; STOP must end both
  task-owned processes through the Job Object boundary.

- Open a PLUMA-created temporary tab while a pre-existing browser
  session exists; STOP must close only the task-owned tab, not the user
  browser session.

- Move a test file then STOP before the next step; rollback should
  return it to the original path if safe.

- STOP during planner inference; no tool may begin after the stop latch.

- STOP during OCR; OCR worker ends/cancels, no screenshot remains
  persisted unless debugging is enabled.

- Force a rollback failure; task must still end STOPPED_WITH_RESIDUAL
  (or equivalent internal state) and the Activity Ledger must state the
  exact leftover effect.

# **25. Packaging, startup and crash recovery**

- Windows startup launches only the resident core. LLM/STT/OCR workers
  are never startup services.

- Models live outside the core executable so they can be replaced
  without rebuilding PLUMA.

- Use per-user storage under %LOCALAPPDATA%\PLUMA for
  data/models/cache/logs and %APPDATA%\PLUMA for user configuration if
  appropriate.

- All local IPC must be bound to the user/local machine and not exposed
  as a LAN service.

- Clean shutdown closes task Job Object handles and worker processes.
  Kill-on-job-close provides additional protection against orphan child
  processes.

- On startup, mark any previously RUNNING/STOPPING task as
  ABORTED_BY_CRASH, inspect recorded temp resources, and clean only
  resources whose PLUMA ownership can be verified.

- Never assume a leftover PID is the same process after reboot; verify
  creation time/ownership metadata before any cleanup action.

> %LOCALAPPDATA%\PLUMA\\  
> bin\\  
> data\pluma.db  
> models\\  
> cache\\  
> logs\\  
> temp\task\_\<id\>\\  
>   
> %APPDATA%\PLUMA\\  
> user_settings.json

# **26. Example command traces**

## **26.1 “Volume 20”**

1\. Voice or text arrives.

2\. Fast router resolves set_volume(20).

3\. No LLM, OCR or screen capture starts.

4\. Tool captures old volume, sets new value, reads it back.

5\. Ledger stores factual result + undo value.

6\. Response: “Volume set to 20%.”

7\. Task ends; no heavy component remains active.

## **26.2 “Click Submit on this screen”**

1\. Create active-window snapshot.

2\. UIA searches for a semantic Submit control.

3\. If found and unambiguous, invoke through UIA. OCR is skipped.

4\. If UIA cannot expose it, capture only the target window and run OCR.

5\. Create a short-lived ScreenElement for the Submit text and bounding
box.

6\. Re-check active window + snapshot freshness, then invoke the
window-relative target.

7\. Verify the expected window/control transition.

8\. Ledger stores target source (UIA/OCR), label, method, verification
and timing.

## **26.3 “Move the PDF I downloaded yesterday into College/DBMS and open it”**

1\. Fast path cannot resolve full semantics, so local planner starts.

2\. Planner gets only file-related tool schemas + known alias
“College/DBMS” if saved.

3\. find_file returns candidates; planner selects only if unambiguous.

4\. move_file captures original path and verifies destination.

5\. open_file verifies application/window.

6\. Actions and undo recipe are stored.

7\. Planner goes warm briefly or unloads according to runtime policy.

## **26.4 STOP during a multi-step task**

1\. Global STOP hotkey sets task stop latch.

2\. No next step or replan is permitted.

3\. Active worker receives cancellation; unresponsive PLUMA-owned
descendants are terminated through the task process boundary.

4\. Rollback engine walks completed reversible actions backward.

5\. Task-owned temporary UI/resources are closed/removed without
touching pre-existing user resources.

6\. Cleanup is verified and task is finalized STOPPED.

7\. Activity view shows what completed, what was undone, and any
irreversible effect that remained.

# **27. Practical limitations and non-goals**

- PLUMA V1 does not guarantee control of every application. Secure
  desktops, elevated apps, anti-automation software, games, remote
  sessions, custom-rendered canvases and inaccessible controls may block
  UIA or input methods.

- OCR reads visible text; it is not a universal visual-understanding
  system. Textless icons/graphics that have no UIA semantics are not
  guaranteed targets in V1.

- Undo is not magic. External submissions, sent messages, remote changes
  and some destructive operations may be impossible to reverse after
  commit.

- PLUMA does not keep a multimodal model continuously watching the
  screen.

- PLUMA does not receive unrestricted shell/admin access from the LLM.

- PLUMA does not silently convert every action or conversation into
  permanent semantic memory.

- PLUMA does not define the final visual UI in this guide.

- PLUMA does not add “agentic” features that are not required by the
  locked scope.

# **28. Definition of done**

☐ PLUMA starts with Windows with only the resident core and effectively
no ML/GPU workload.

☐ Voice commands are fully functional in V1 and enter the same
tool/policy/verification pipeline as text.

☐ Common simple commands execute without LLM/OCR invocation.

☐ UIA can inspect and operate common Windows applications through
semantic controls.

☐ OCR wakes only when required, returns visible text + geometry, and can
ground a verified screen-relative action.

☐ Stale OCR/UIA target references are rejected rather than clicked
blindly.

☐ Complex commands produce validated registered tool calls from a local
replaceable planner.

☐ Every task is represented by one Task Capsule; no execution branch
escapes Task Supervisor ownership.

☐ Global STOP latches within the latency budget, blocks new steps,
cancels active work, terminates unresponsive PLUMA-owned task workers,
performs safe rollback, and verifies cleanup.

☐ No PLUMA-owned orphan worker remains after success, failure, STOP or
resident crash in the tested scenarios.

☐ All state-changing tools verify postconditions; reversible tools
capture undo state.

☐ High-risk/admin actions use deterministic confirmation/elevation
paths.

☐ Activity Ledger accurately shows commands, tools, timings,
verification, undo/rollback, stop state and errors with sensitive data
redacted.

☐ Activity text is deterministic/factual and contains no LLM-generated
filler.

☐ Raw audio/screenshots are not persisted by default.

☐ Model/STT/OCR runtimes return to cold/idle after the configured grace
period.

☐ Fixed regression/performance suite passes before release.

☐ UI visual design has not been invented by the implementation team;
final appearance follows owner direction only.

<table>
<colgroup>
<col style="width: 100%" />
</colgroup>
<thead>
<tr class="header">
<th><p><strong>FINAL ENGINEERING RULE</strong></p>
<p>If a component makes PLUMA heavier while idle, first ask whether it
can be event-driven, launched on demand, scoped to the current task,
cached only briefly, or moved behind a worker adapter. If yes, do that
before accepting permanent resource cost.</p></th>
</tr>
</thead>
<tbody>
</tbody>
</table>

# **Appendix A. Configuration baseline**

> agent:  
> text_hotkey: "alt+space"  
> stop_hotkey: "ctrl+alt+esc" \# placeholder behavior key; user can
> change later  
> max_plan_steps: 8  
> default_tool_timeout_seconds: 15  
> fast_path_enabled: true  
> continuous_screen_polling: false  
>   
> runtime:  
> model_idle_unload_seconds: 30  
> stt_idle_unload_seconds: 20  
> ocr_idle_unload_seconds: 10  
> allow_short_warm_grace: true  
>   
> voice:  
> required: true  
> activation_default: "push_to_talk"  
> wake_phrase_enabled: false  
> save_audio: false  
>   
> perception:  
> uia_first: true  
> ocr_enabled: true  
> ocr_scope: "target_window_or_region"  
> persist_screenshots: false  
> snapshot_ttl_seconds: 3  
> coordinate_fallback_requires_fresh_snapshot: true  
>   
> brain:  
> runtime: "llama_cpp"  
> temperature: 0.0  
> structured_output: true  
> model_profile: "benchmark_selected_small_local"  
>   
> policy:  
> confirm_high_risk: true  
> permanent_elevation: false  
> redact_sensitive_logs: true  
>   
> stop:  
> block_new_steps_immediately: true  
> rollback_reversible_actions: true  
> terminate_owned_unresponsive_workers: true  
> touch_preexisting_user_apps: false  
>   
> memory:  
> database: "sqlite"  
> activity_view_enabled: true  
> save_chain_of_thought: false  
> deterministic_activity_text: true  
>   
> ui:  
> visual_design_status: "owner_defined_later"

# **Appendix B. Technology validation references**

The architecture is intentionally adapter-based. The following current
primary/official references validate the core technology choices; exact
versions/models must be re-benchmarked before release.

| **Reference**                                                   | **URL**                                                                             | **Why it matters**                                                                                         |
|-----------------------------------------------------------------|-------------------------------------------------------------------------------------|------------------------------------------------------------------------------------------------------------|
| Microsoft Learn - UI Automation Overview                        | https://learn.microsoft.com/en-us/windows/win32/winauto/uiauto-uiautomationoverview | Documents programmatic access to most desktop UI elements and semantic manipulation through UI Automation. |
| Microsoft Learn - Job Objects                                   | https://learn.microsoft.com/en-us/windows/win32/procthread/job-objects              | Documents grouping/managing process trees and kill-on-job-close behavior for associated processes.         |
| Microsoft Learn - AssignProcessToJobObject / TerminateJobObject | https://learn.microsoft.com/en-us/windows/win32/api/jobapi2/                        | Documents associating and terminating processes through Windows Job Objects.                               |
| Microsoft Learn - Windows.Media.Ocr                             | https://learn.microsoft.com/en-us/uwp/api/windows.media.ocr                         | Documents built-in OCR APIs and the package-identity constraint relevant to desktop packaging decisions.   |
| ggml-org/whisper.cpp                                            | https://github.com/ggml-org/whisper.cpp                                             | Local C/C++ Whisper inference; Windows support, quantization, CPU/GPU backends and VAD.                    |
| ggml-org/llama.cpp                                              | https://github.com/ggml-org/llama.cpp                                               | Local quantized LLM runtime with Windows builds and structured/grammar-constrained output capabilities.    |
| pywinauto documentation                                         | https://pywinauto.readthedocs.io/                                                   | Windows desktop automation with Win32 and UIA backends.                                                    |
| PaddleOCR documentation                                         | https://www.paddleocr.ai/                                                           | Local OCR pipeline, tiny/small model options and supported inference engines including ONNX Runtime.       |
| ONNX Runtime - Windows                                          | https://onnxruntime.ai/docs/get-started/with-windows.html                           | Windows local inference runtime options for CPU/GPU-oriented model execution.                              |
| SQLite - Appropriate Uses                                       | https://www.sqlite.org/whentouse.html                                               | Explains SQLite as a strong fit for local application/device storage without a server.                     |

**PLUMA**

**Smart when active. Featherweight when idle.**

This document is the engineering source of truth for the locked PLUMA V1
architecture.
