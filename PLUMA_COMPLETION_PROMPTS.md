# PLUMA: prompts from the current checkpoint to a maintainable release

Prepared 2026-10-19 for the project owner. This is an execution guide derived
from the existing requirements, not a replacement specification or a declaration
that the project is complete. Its milestone numbers are work packets, not new
build-plan phases. Already-working code stays in place.

## Start here

Open `D:\Workspace\DEVEL\PLUMA`. The active branch is `ui-wiring`. Send:

```text
Read PLUMA_COMPLETION_PROMPTS.md and PROJECT_HANDOFF.md. Apply the shared
execution contract and execute P00 only. Complete its bounded work, verify it,
commit meaningful changes, push the relevant branch and report the next gate.
```

For the next task, replace `P00` with the next eligible ID. Each prompt below
contains the actual task. Use a fresh conversation for each coherent milestone;
the repository handoff carries progress. You do not need to supervise each edit.
Do not paste every prompt at once or authorize automatic progression through
the whole file. P11-P15 may require multiple bounded tasks as their gap lists
are closed. Finish the named gate before advancing.

Your role: describe expected behavior, report what happens on your computer,
and make genuine product/appearance decisions when the documents cannot answer.
The coding agent owns inspection, implementation, safe fixtures, tests, review,
documentation, commits and evidence. For a bug, provide the command, expected
result, actual result and approximate time; include an error or screenshot when
useful, with sensitive information removed.

One scoped outcome, durable repository guidance, explicit completion evidence
and a separate review pass follow [official OpenAI best practices](https://learn.chatgpt.com/guides/best-practices).
The project-specific requirements below come from PLUMA's own documents.

## Authority and the starting state

Read these in order and inspect the actual implementation before changing code:

1. [PLUMA_MASTER_SPEC.md](PLUMA_MASTER_SPEC.md), completely; immutable product
   and engineering requirements, especially sections 1, 3-16, 21 and 23-28.
2. [AGENTS.md](AGENTS.md), the mandatory execution/safety contract.
3. [PLUMA_BUILD_PLAN.md](PLUMA_BUILD_PLAN.md), the relevant phase and gates.
4. [PLUMA_ACCEPTANCE_TESTS.md](PLUMA_ACCEPTANCE_TESTS.md), every applicable ID
   and the final definition of done; [technology contract](PLUMA_TECH_STACK.md).
5. [PROJECT_HANDOFF.md](PROJECT_HANDOFF.md), its current dated checkpoint first.
6. [Backend audit](PLUMA.UI/PLUMA.UI/docs/backend_wiring_audit.md),
   [wiring handoff](PLUMA.UI/PLUMA.UI/docs/wiring_handoff.md),
   [status connection](PLUMA.UI/PLUMA.UI/docs/wiring_status_connection.md),
   [surface inventory](PLUMA.UI/PLUMA.UI/docs/phase14_ui_surfaces.md),
   [placement contract](PLUMA.UI/PLUMA.UI/docs/popup_placement_contract.md) and
   [UI integration evidence](PLUMA.UI/PLUMA.UI/docs/ui_integration_review.md).

The current facts, to recheck when starting:

- Read-only dashboard status is wired. Text action entry is disabled.
- Nine backend findings remain open: BA-01 through BA-09. The audit has eleven
  failing required-behavior assertions, not eleven passing acceptance checks.
- Selected backend evidence is 277 passes, eleven strict expected failures and
  one excluded elevation operation. Raw `--runxfail` gives eleven failures and
  four passes. These are a bounded audit, not full backend certification.
- Native UI baseline at `64559bd` passed 37 IPC, 663 popup, 195 formatting and
  42 control checks, with 58 render exports. Physical Windows acceptance remains.
- `main` is `6dbf589` at preparation time; the wiring branch contains the native
  UI plus the audit. PR 1 and PR 2 are draft/unmerged. Query current Git state;
  never assume these SHAs or PR states stay current.
- [Cleanup/recovery](docs/workspace_cleanup.md) preserves old local generated
  state, historical reports and archives. Keep its recovery points available.

Historical reports under `docs/history` do not override newer failures. The
owner's optional local capability note contains protocol/event assertions that
must be checked against source. The actual current Windows IPC is per-user
native message-mode framing with HMAC authentication; newline JSON-RPC and a
live event subscription are not established by a surface-reference paragraph.
P15 must define and test missing contracts explicitly. Setup checks must follow
the locked PaddleOCR/ONNX and whisper.cpp contracts, not stale Tesseract or
model-filename examples. Preserve requirements; surface/reference inaccuracies
are not permission to reduce scope or fabricate implemented features.

## Shared execution contract for every prompt

```text
Work on PLUMA in the current authorized development checkout. Read the named
prompt, the current handoff, the immutable master specification, AGENTS.md,
relevant build-plan phase and applicable acceptance IDs. Inspect source and
tests before editing. Verify branch/remotes/worktrees and preserve existing
user work. Do not switch dirty worktrees or overwrite unrelated files.

State exact files and meaningful acceptance checks before editing. Implement
only this bounded milestone or its next explicitly identified gap. Complete
authorized routine work without repeated permission questions. Ask only for
genuinely missing owner decisions or explicit actions requiring approval;
explain the exact requirement or blocker. Never guess a locked requirement.

Retain the existing native Windows dark design. There is no light version.
Preserve approved classes, sizes, typography and spacing; do not reinvent dark
styling. Floating surfaces use the shared bottom-right stack, newest below
older cards, consistent clearance, smooth entry/reflow/exit and taskbar
reveal/hide glide. Use the existing placement contract. Long text, Unicode and
unbroken words must fit through bounded wrapping/scrolling at readable sizes;
indicators align with text. Popup copy is human-readable and contains no
underscores or em dashes. Apply display formatting without corrupting raw tool
identities, paths, evidence, redaction or undo data.

Keep ML/STT/OCR/capture cold at idle. Voice and text share the same request,
router, policy, ToolSpec, TaskSupervisor, verification and ledger path. All
state changes require typed registered execution, safe pre-state where
reversible and verified readback. STOP latches before cleanup and blocks new
work. Own and bound every worker, subprocess, timeout, subscription and task.
Never terminate pre-existing user resources merely because PLUMA used them.

Use isolated storage, owned fixture apps/processes/pipes and inert adapters
where appropriate. Tests must demonstrate real invariants and failure paths;
do not weaken assertions, add fake-success fallbacks, silently deselect failing
requirements or count xfail/skip/emulation as physical acceptance. Real-device
and permitted integration evidence is still required at the relevant gate.
Do not bypass Windows Application Control or change security policy for tests.

Run focused checks, then the relevant regressions. Inspect the diff for scope,
secrets, fabricated success, missing cleanup and user-copy regressions. Record
commands, actual output, tested commit/build hash, environment, durations,
verification and ledger evidence. Distinguish verified facts, failure-injected
fixtures, unexecuted checks and assumptions. A function return is not proof.

Commit every meaningful coherent change and push the authorized branch. Keep
runtime data, model files, raw audio/screenshots, secrets, bin/obj, caches and
release bundles out of Git. Store fresh reports under ignored output; retain
durable redacted summaries in the handoff/evidence map. Do not merge or start
the next milestone unless that prompt explicitly authorizes it.

Update PROJECT_HANDOFF.md, the requirements/evidence map and relevant contracts
before claiming completion. Report changed files, test commands/results,
remaining issues, GitHub state, recovery point and the exact next safe step.
The applicable gate must pass or have a concrete owner-approved recorded
limitation under AGENTS.md. Never assume approval, blanket-waive a locked
capability or call the full product done while final requirements remain open.
```

## Milestone map

Every row is PLANNED at preparation time; this file does not mark them passed.
P00 creates the live requirements/evidence map. Later results belong there and
in the dated handoff, with source/build-specific evidence.

| Prompt | Bounded outcome |
|---|---|
| P00 | Fresh requirements, capability, defect and evidence map |
| P01 | BA-03: STOP versus actual executor admission |
| P02 | BA-01: latch all affected tasks before cleanup |
| P03 | BA-02: interruptible owned-worker termination |
| P04 | BA-04: verified cleanup and retained failures |
| P05 | BA-05: authoritative residual result and ledger state |
| P06 | BA-06: orderly shutdown and worker drain |
| P07 | BA-07: voice capture/capsule cancellation lifecycle |
| P08 | BA-08: truthful typed STOP acknowledgement/outcomes |
| P09 | BA-09: private atomic Windows IPC credential creation |
| P10 | Revalidate repaired safety boundaries with real owned Windows fixtures |
| P11 | Close remaining typed-tool, policy, verification and undo gaps |
| P12 | Close remaining UIA/OCR grounding and screen-safety gaps |
| P13 | Close local planner/runtime lifecycle and constrained-plan gaps |
| P14 | Close mandatory backend voice/text parity and device gaps |
| P15 | Versioned UI/core request, event and reconnect contracts |
| P16 | Material confirmations and bounded elevation decisions |
| P17 | Text submission and independent priority STOP |
| P18 | Factual live task/tool/result/rollback/notification projections |
| P19 | Unified voice overlay and real transcription events |
| P20 | History, details, undo and conflict resolution |
| P21 | Settings persistence, validation and application |
| P22 | Truthful health, setup and controlled recovery |
| P23 | Real target-window capture and OCR match feedback |
| P24 | Complete end-to-end acceptance scenarios and fixed corpus |
| P25 | Physical Windows UI, taskbar, DPI and accessibility acceptance |
| P26 | Idle/resource/latency/quality/soak measurements |
| P27 | Adversarial security, privacy, failure and crash review |
| P28 | Reproducible backend plus WinUI package and signing |
| P29 | Clean install, startup, upgrade, recovery and uninstall |
| P30 | Fresh review against the full specification |
| P31 | Exact-build final acceptance and release evidence |
| P32 | Verified GitHub merge, local branch reconciliation and release tag |
| P33 | User/developer handover and long-term recovery instructions |

### P00 — Establish the current truth

```text
Execute P00 using the shared contract. Do not start a product feature or restart
Phase 0. Reconcile the actual branch/source/tests with the master specification,
build plan, acceptance A-J, all section-28 checkboxes, every section-21 catalog
entry and the 26 UI surfaces. Create docs/completion/requirements_matrix.md with
requirement ID/source, implementation, tests/evidence, actual status, owner of
the next prompt, gaps and unresolved decisions. Include all BA findings and
distinguish implemented, unwired, unverified, defective and genuinely optional
items. Challenge historical pass/completion claims and test validity; never
invent tools/events or silently drop a catalog requirement. Record explicit
dependencies, current PR/branch state and recovery instructions. No production
execution changes. Finish with the prioritized bounded P01 work packet.
```

Gate: every locked capability and acceptance item has a traceable row and an
honest status; omissions and ambiguities are visible, not interpreted away.

### P01 — BA-03: STOP blocks actual executor admission

```text
Execute P01. Reproduce BA-03 before editing. Repair the STOP/admission ordering
so no executor begins after cancellation during pre-state capture or while work
is queued. Inspect both thread and process entry, policy/undo waits and task
ownership. Define the admission boundary precisely; a check far before dispatch
is insufficient. Preserve verification and safe undo capture. Use controlled
ordering/failure tests, convert the BA-03 reproduction into an ordinary passing
regression and inspect for escaped queued work. Keep UI action entry disabled.
Verify focused cancellation/registry checks and relevant regressions; document
remaining real-worker checks for P10. Commit this fix separately.
```

Gate: BA-03 is resolved with admission evidence; no weakened assertion or
post-latch fixture executor start remains in the covered entry paths.

### P02 — BA-01: latch first across affected tasks

```text
Execute P02 after P01 passes. Repair global STOP so all affected tasks are
latched before any grace wait, termination, rollback or cleanup begins. Cover
CREATED/RUNNING tasks, simultaneous STOP requests, terminal tasks and requests
racing the stop operation. Preserve one supervisor/cancellation tree and keep
cleanup outside locks needed for prompt acknowledgement. Convert BA-01 to a
passing regression. Prove a blocked first cleanup cannot leave another affected
task admitting work. Measure acknowledgement separately from cleanup; do not
claim hardware p95 from an injected sleep. Keep action entry disabled.
```

Gate: latch-all ordering is deterministic and P01 remains green.

### P03 — BA-02: STOP interrupts owned worker waits

```text
Execute P03 after P02 passes. Repair controller lock/I/O ownership so STOP can
interrupt a blocked execution response without waiting for the tool's timeout.
Keep calls serialized where required but make cancellation/owned termination
independent. Bound I/O, graceful cancellation, forced owned-tree termination,
joining and cleanup. Retain PID/creation-time/task identity and Job Object
containment; never kill an unrelated process. Cover cancellation before start,
during startup, during response wait and repeated disposal. Convert BA-02 to a
passing regression and preserve P01/P02. Record the real Windows checks for P10.
```

Gate: the blocked-connection fixture is interruptible; ownership and timeouts
remain enforced, with no detached cleanup branch.

### P04 — BA-04: cleanup readback determines final state

```text
Execute P04. Preserve termination/resource-cleanup failures and ownership
identity until absence or cleanup is verified. Combine worker, Job Object,
temporary resource and rollback evidence when choosing terminal state. A logged
exception, discarded reference or successful native call return is not proof
that no owned worker remains. Cover failed termination, failed cleanup,
successful fallback readback and partial rollback. Convert BA-04 to a passing
regression, retaining factual residual details and safe boundaries around
pre-existing resources. Keep UI action entry disabled.
```

Gate: clean completion requires positive cleanup evidence; unresolved cleanup
is represented factually and persists for later inspection/recovery.

### P05 — BA-05: one authoritative terminal result

```text
Execute P05. Make FAST execution, other routes, task results, ledger and IPC
project the supervisor's authoritative terminal outcome consistently. Preserve
STOPPED_WITH_RESIDUAL and rollback details instead of overwriting them with a
local STOPPED/SUCCEEDED value. Cover STOP racing the last step, partial rollback,
non-undoable commits, ledger failure and repeated finalization. Verify real
SQLite readback as well as returned results. Convert BA-05 to a passing
regression. Fix only this bounded state/result consistency issue and preserve
existing factual templates and redaction.
```

Gate: memory, returned result and persisted history agree on tested outcomes.

### P06 — BA-06: close drains owned work before storage

```text
Execute P06. Make runtime shutdown reject new work, latch active tasks, cancel
capture/owned work, drain handlers and worker controllers, verify cleanup,
persist outcomes, close registry resources and finally close storage. Keep
every stage bounded and idempotent. Cover shutdown during execution, pending
IPC, capture, rollback and repeated close, without changing user apps or Windows
settings. Convert BA-06 to a passing regression. Do not rely on interpreter or
OS process exit as the only evidence. Preserve crash-recovery ownership rules.
```

Gate: tested shutdown has no active owned work using closed storage or lost
terminal evidence; real descendant verification is included in P10.

### P07 — BA-07: own every voice capture path

```text
Execute P07. Connect push-to-talk capture to its capsule cancellation lifetime
so STOP closes/discards recording without waiting for key release. Finalize
empty, denied, failed and cancelled capture paths. Preserve the same capsule
into STT and execution; serialize press/release/STOP/shutdown races. Keep raw
audio transient and models lazy. Convert both BA-07 reproductions to ordinary
passing tests. Verify no executor starts after voice STOP and no empty CREATED
capsule accumulates. Use inert device fixtures here and record real-device
acceptance separately for P14/P19; do not count emulation as physical voice.
```

Gate: both lifecycle failures are resolved and text/voice still share ownership.

### P08 — BA-08: truthful STOP protocol outcomes

```text
Execute P08. Distinguish STOP latch acknowledgement, cleanup in progress and
verified terminal outcome. Return typed per-task pending/stopped/residual/error
information using actual supervisor/ledger evidence. A candidate task ID or
transport status ok must not mean clean cancellation. Cover missing/terminal
tasks, cleanup exceptions, partial rollback, repeated STOP and concurrent
execution. Convert both BA-08 reproductions to passing regressions. Keep the
current authenticated native framing and bounded requests. Update the protocol
contract without inventing an already-existing push API; P15 defines live events.
```

Gate: unfinished and residual tasks are never reported as cleanly stopped.

### P09 — BA-09: secure credential creation and reuse

```text
Execute P09. Create Windows IPC credentials atomically with an explicit safe
owner/DACL and validate the opened file on new and existing paths. Fail closed
for broad permissions, invalid owner, corrupt size, access denial and competing
creation. Match the C# reader's security contract without weakening it. Never
log secrets, alter a production key merely for testing, or enable authentication
bypasses. Convert the actual inherited-ACL reproduction BA-09 to a passing
regression; add relevant creation/reuse/race checks using test-owned locations.
Prove Python/C# authenticated compatibility remains intact.
```

Gate: fresh credentials are private or refused; existing security checks and
read-only UI interoperability remain green.

### P10 — Revalidate the repaired backend safety boundary

```text
Execute P10 only after P01-P09 pass. Run the audit without xfail handling and
relevant regressions in isolated user-local storage. Use real owned Windows
fixture processes/Job Objects to verify STOP during blocked work, no next step,
descendant exit, PID identity, rollback/residual accounting and clean shutdown.
Keep a separate pre-existing fixture resource and prove it survives cleanup.
Measure latch acknowledgement independently of terminal cleanup. Reconcile
memory, result, ledger and IPC readback. Do not touch real user applications or
perform system-changing elevation operations. Record failures as blockers and
stop; do not enable command entry or proceed into wiring automatically.
```

Gate: no unresolved audit expected failures or safety blockers in covered paths;
real-owned integration evidence supplements the unit fixtures.

### P11 — Finish required tools, policy, verification and undo

```text
Execute P11 using the P00 matrix. Inspect all section-21 catalog entries and
required functional operations: files, apps, windows, processes, audio, system,
clipboard, browser, controlled terminal, memory/routines and agent controls.
Select the next single bounded required gap; implement it through registered
typed tools/adapters with schema validation before deterministic policy, bounded
owned execution, readback verification, minimal safe pre-state and factual
redacted ledger results. No unrestricted planner shell/admin access. Test
denied/ambiguous targets, failures and safe inverse/conflict behavior. Do not
weaken tests or infer support from a tool name. Repeat P11 in separate tasks
until its required matrix rows and A/D/H gates are satisfied or an actual
requirement ambiguity is resolved by the owner. Then record eligibility for P12.
```

Gate: required capabilities have usable implementations and evidence; missing
catalog entries are not silently reclassified as optional.

### P12 — Finish semantic screen control and OCR fallback

```text
Execute P12 for the next bounded gap in acceptance E-01 through E-10. Verify
native/application APIs and semantic UIA precede fallback; OCR captures only a
needed target window/region on demand. Enforce snapshot TTL, window/process
identity, creation time, geometry and DPI before grounded input. Refuse duplicate
labels, stale references, inaccessible/textless targets and privilege denial
factually. Read back the expected transition after interaction. Preserve capture
privacy and STOP ownership. Use deterministic fixture windows, then permitted
real Windows checks. Repeat bounded fixes until all E rows have evidence;
do not invent broad desktop watching or guess raw coordinates.
```

Gate: supported UIA/OCR actions are grounded and verified; stale/unsupported
targets fail safely and no routine screenshot persists.

### P13 — Finish constrained local planning and runtime lifecycle

```text
Execute P13 for the next bounded planner/lifecycle gap. Verify FAST skips models
and screen capture, route-specific contexts/tool subsets, validated registered
plans, bounded steps/replans, observation before continuation and STOP during
inference. Exercise real local llama.cpp integration where required; mocked
plans do not prove the model adapter. Cover malformed JSON, invented tools,
forbidden arguments, timeout/crash, secret context and cold/warm/unload behavior.
Keep model/runtime replaceable and offline; select quality on the fixed corpus
before optimizing speed. Repeat bounded fixes until applicable B/F rows are
covered. Preserve the configured master-spec limits and record physical budgets
for P26 instead of inventing hardware-independent performance claims.
```

Gate: real constrained planning and on-demand lifecycle have evidence; no
planner output becomes a direct OS action or unvalidated fallback success.

### P14 — Finish the mandatory backend voice path

```text
Execute P14 for the next bounded C-01 through C-10 gap. Verify user-activated
microphone capture, VAD/end boundary, real local whisper.cpp transcription,
confidence/target clarification, capture/STT STOP, transient raw audio and
bounded cold/warm/unload behavior. Voice and typed equivalents must enter the
same request/router/policy/tool/verification/ledger pipeline and task ownership.
Exercise fixture audio plus actual permitted microphone/STT checks; distinguish
device evidence, recorded test samples and emulation. Optional local spoken
results remain factual. Implement no separate voice executor. Repeat bounded
fixes until required C rows have evidence; keep normal startup microphone/model
activation lazy and preserve the approved UI for later P19 connection.
```

Gate: voice is functional backend behavior, not merely an overlay or mock.

### P15 — Define and implement missing UI/core contracts

```text
Execute P15 after the backend gates. Inspect existing IPC and real executor
events before extending it. Define/version typed requests, correlation/task
IDs, submission acknowledgement and terminal readback, priority STOP,
confirmations, settings/history queries and factual event projections. Specify
event ordering, bounded buffering, duplicate handling, disconnect/reconnect,
malformed/oversized messages, authentication/ACLs, ownership and disposal.
STOP must remain responsive under saturation or a long execution response.
Never auto-retry a side effect after an uncertain response. Preserve native
Windows message framing and prove Python/C# compatibility. Implement the next
bounded contract slice and its integration tests; repeat until the required
contracts exist. Update surface references that incorrectly imply JSON-RPC,
heartbeats or push streams already exist. No fabricated UI event data.
```

Gate: required messages are actual tested contracts, not guessed event names.

### P16 — Wire material confirmations safely

```text
Execute P16. Connect the existing risk approval dialog (18) and policy decisions
through the tested contract. Show the exact material operation with readable
redacted arguments; bind decisions to the requesting task/call and validated
arguments. Cover denial, timeout, STOP, stale/mismatched decisions, duplicates
and disconnected UI. High-risk work must fail closed without approval. Prove
one-operation elevation and no permanently elevated resident using safe inert
operations first; record permitted native UAC evidence separately. Do not
execute a destructive/power operation merely to demonstrate its dialog. Keep
native styling, factual messages, bounded waits and cancellation responsive.
```

Gate: actual policy waits receive only valid decisions and cannot outlive STOP.

### P17 — Wire text submission and independent STOP

```text
Execute P17 only after safety/protocol/confirmation gates pass. Connect existing
dashboard text entry to the shared request/TaskSupervisor pipeline. Keep WinUI
responsive; provide correlation/task identity and separate priority STOP from
the in-flight execute response. Prove actual registered safe fixture actions,
postcondition/ledger readback, denied/failed results and terminal residual
outcomes. Cover double submission, STOP during execution/planning, disconnect
after admission, uncertain timeout, reconnect and window close. Do not retry
side effects silently. Enable action entry only when its real guarded path is
ready. Preserve the dark UI and use existing cancellation feedback (20).
```

Gate: one user submission owns one task; STOP works during active work and UI
results reflect verified backend outcomes rather than transport acknowledgement.

### P18 — Wire live state and the shared notification stack

```text
Execute P18. Project tested factual task, step, route, tool, verification,
rollback, policy, termination and notice events into surfaces 4-9, 17, 19-24
and dashboard/live feed. Retain stable task/event identities, ordering,
bounded buffers, redaction and truthful pending/failed/residual states. Reconnect
must not duplicate old notifications or fabricate success. Worker-terminated
feedback requires verified owned termination. Preserve class sizes, newest-below
ordering, lower hidden-taskbar anchor, reveal/hide glide, native layout readiness,
reading holds and smooth dismissal. Long text and status indicators retain the
formatting contract. Test event bursts, replacements, navigation and shutdown;
all production sample events must be removed from these wired paths.
```

Gate: notifications correspond to real backend evidence and remain clean under
bursts, failure, reconnect and replacement; UI dismissal never cancels implicitly.

### P19 — Wire the unified voice/transcription overlay

```text
Execute P19. Connect voice surfaces 11-14 as states of the existing single
VoiceOverlay, through the same capsule and real capture/STT events validated in
P14/P15. Partial and final transcript text must originate from actual recognition;
do not simulate streaming by animating a completed transcript. Implement a missing
required partial-result contract as a separate bounded slice if necessary.
Show committed/timeout states truthfully, preserve low-confidence clarification,
STOP during capture/STT, device-denial and reconnect/shutdown behavior. Keep
transcripts readable within the fixed viewport, follow new speech only when
the user is at the tail, and preserve reading earlier text. Verify real device
and local runtime behavior separately from fixtures, without raw audio storage.
```

Gate: text and voice give equivalent guarded execution; one overlay, no stale
transcript, fabricated commitment or microphone/model work at idle.

### P20 — Wire history, details, undo and conflicts

```text
Execute P20. Connect History/Activity surface 3, task/action details, undo,
rollback surface 9 and conflict dialog 10 to actual redacted ledger/query and
rollback contracts. Include route, input mode, timestamps, verification,
policy, cleanup and residual effects. Undo uses captured evidence, conflict
checks, reverse ordering and atomic consumption; duplicate clicks cannot apply
it twice. Never promise reversal of irreversible commits. Cover search/paging,
empty history, restart, unavailable storage, denied/conflicting undo and stopped
tasks. Remove production history fixtures. Preserve current native controls,
format readable fields and keep original identities/undo values intact.
```

Gate: displayed history agrees with SQLite and undo outcomes are verified.

### P21 — Wire settings and persistent behavior

```text
Execute P21. Complete the existing SettingsContract and surface 2 for the
behavior defined by the specification: hotkeys, local model/runtime paths,
voice activation, measured warm grace, privacy/logging and allowed policy
settings. Validate inputs, write atomically, read back and apply changes with
owned lifecycle handling; document settings needing restart. Preserve defaults,
schema migration and safe recovery from corrupt/denied writes. No hidden
network service, always-on microphone, blanket admin privilege or policy bypass
may be enabled by a UI toggle. Test cancel/save/reload/restart, invalid paths,
hotkey conflict, failure and rollback to previous valid settings. Retain dark
styling and use real persisted data instead of preview selections.
```

Gate: settings survive restart and effective runtime behavior matches readback.

### P22 — Wire health, setup and controlled recovery

```text
Execute P22. Connect health surface 23 and dashboard status, critical error
dialog 25 and setup wizard 26 to real capability/status/recovery contracts.
Keep disconnected/unverified states honest; never enable Continue from fixture
capability checks. Verify required local OCR/UIA/STT/model files, microphone
permissions and hotkey availability using bounded user-initiated checks. Do not
load all ML workers just because the shell starts. Restart Core must target
only the verified owned core and wait for authenticated health readback before
reporting recovery. Cover crash/stale tasks, denied permissions, unavailable
models, repeated restart and configuration failure. Use factual redacted errors
and define any health update mechanism explicitly without unbounded polling.
```

Gate: setup/recovery reflects actual evidence and cannot create duplicate cores
or silently claim unsupported capabilities are ready.

### P23 — Wire target-window perception feedback

```text
Execute P23. Connect capture flash 15 and OCR match indicator 16 to actual
target-window/region capture and validated match evidence. Preserve the existing
geometry/style and target-window coordinate contract; do not put these into
the desktop notification lane or flash the entire desktop by default. Expire
or clear feedback on window identity, geometry/DPI, TTL, task cancellation or
missing/ambiguous target. Confidence and bounds must come from perception,
not an invented visual guess. Show verification 17 only after actual readback.
Test moved/closed windows, monitor/DPI changes, stale matches and STOP with
owned fixture windows. Keep image bytes transient by default.
```

Gate: visual feedback identifies the correct fresh target and proves no action
or success by itself; no unrelated window is marked or captured.

### P24 — Exercise complete user flows and the fixed corpus

```text
Execute P24 after all required backend and surface matrix rows are wired.
Build/run the specification's fixed 100-300 command corpus with expected routes,
tools, arguments and risk. Include text/voice parity, FAST without ML/OCR,
semantic and OCR actions, bounded planning/replanning, material confirmations,
verified mutation, undo/conflict, STOP under load and factual ledger/UI outcomes.
Use owned fixtures and explicit safe targets. Include unavailable core/model,
denied permissions, malformed results, lost connection and partial failure.
Record actual commands, commit, environment, verification, ledger evidence and
timings in the acceptance format. For a failure, reproduce and fix one bounded
issue per task before repeating affected checks; do not replace tests with a
manual chat demonstration or weaker expectations.
```

Gate: every required end-to-end row has actual evidence and no production UI
path still depends on fabricated fixtures or unsupported protocol assumptions.

### P25 — Verify the real Windows experience

```text
Execute P25 on the permitted Windows 11 environment. Verify all 26 surfaces,
real auto-hide taskbar reveal/hide, mixed notification stacks, bottom/right
clearance, fixed class sizes, interrupted motion, no overlap/clipping, long
Unicode/unbroken text, transcript reading, indicator alignment and human copy.
Test actual monitor/DPI combinations from the placement contract, negative
origins, monitor removal, keyboard focus, reading/accessibility and reduced
animation settings. Preserve the approved dark design. If Application Control
blocks the app, use the authorized signing/package route; do not bypass policy
or assume limitation approval. Record physical observations and owner appearance
feedback separately from hosted renders and simulated geometry checks.
```

Gate: physical cases are passed or explicitly unresolved; automated PNGs alone
do not close this milestone or approve appearance/motion for the owner.

### P26 — Measure resource footprint, quality and longevity

```text
Execute P26 using spec section 23 and acceptance I. Record the ten-minute idle
CPU/RAM/GPU/process baseline, FAST p50/p95 dispatch, UIA latency, OCR accuracy
and latency at 100/125/150 percent scaling, cold/warm planner and STT behavior,
quiet/noisy voice accuracy and benchmark-selected model quality. Run fifty
active/idle cycles with worker, handle, memory and model-unload readback.
Measure STOP latch/acknowledgement separately from cleanup during planning,
OCR/STT, shell/UI waits and safe file operations. Compare to source budgets on
this actual laptop; do not invent universal timings. Optimize only demonstrated
waste while keeping policy, verification, cancellation and cleanup. Fix bounded
regressions separately and rerun the affected measurements.
```

Gate: measured idle/heavy-worker behavior and quality meet the documented gates;
faster but less reliable execution is rejected.

### P27 — Adversarial privacy, security and crash review

```text
Execute P27 as a bounded failure-injection/security review. Check local-only
IPC, current-user credential and pipe permissions, auth/size/timeout/concurrency
bounds, corrupt/malicious messages, stale request decisions, secret/clipboard
redaction, no persisted raw audio/screenshots/reasoning and no unrestricted
planner shell/elevation. Inject model/worker/core crashes, locked/conflicting
files, storage failure and recycled PID metadata. Verify ABORTED_BY_CRASH,
ownership-preserving recovery, residual reporting and no active owned orphan
in tested cases. Use only owned fixtures and isolated storage. Report findings
with severity, source and reproduction; repair one bounded issue at a time
and repeat relevant checks. Do not certify cross-account or device behavior
that was not actually exercised.
```

Gate: no open blocking security/cleanup defects; the evidence map states the
tested threat/failure boundaries and remaining limitations precisely.

### P28 — Produce a reproducible signed distributable

```text
Execute P28 after functional gates. Inspect existing packaging before changing
it. Package the actual Python core plus the native WinUI shell and required
runtime/native assets, with model files outside executables and lazy worker
loading. Record exact tested dependency/runtime/model versions, hashes, build
commands, configuration and hardware profile so the build can be reproduced
offline from retained inputs. Validate resources and startup/launch behavior;
startup runs the lightweight resident only. Use the authorized Windows signing
route and verify signatures/launch under the applicable policy, without policy
bypass. Exclude caches, source-control metadata, debug secrets, raw captures and
unrelated local documents. Keep bundles ignored; store release hashes/evidence
as deliberate artifacts. An old backend-only ZIP is not the finished product.
```

Gate: the packaged bits match the tested source/build manifest and launch through
the intended supported path; source-only test success is insufficient.

### P29 — Validate installation, updates and recovery

```text
Execute P29 against the exact P28 artifact using clean controlled Windows/user
profiles first. Verify install/uninstall paths, resident-only startup, explicit
UI launch, models/config/data outside executables, hotkeys, microphone access,
authenticated IPC, clean-profile first key, crash restart and task ownership.
Test upgrade/migration with a preserved local database/config backup, recovery
from interrupted update and readable compatibility failures. Uninstall must
handle user data according to documented intent and never remove unrelated
files/processes. Verify resolved deletion paths before any cleanup. Keep actual
production laptop installation separate until the artifact and recovery route
are reviewable and authorized. Record exact installation and readback evidence.
```

Gate: the installed product, upgrade and uninstall behave correctly; recovery
steps were exercised, not merely written down.

### P30 — Fresh review of the resulting implementation

```text
Execute P30 in a fresh conversation as a read-only review first. Read the
master specification, requirements/evidence map, current source and exact-build
reports. Audit correctness, STOP ordering, ownership, verification/undo,
privacy, protocol races, shutdown/crash behavior, installation, resource
lifetimes and remaining UI fixtures. Reproduce suspected defects safely and
report severity, file/line, failing scenario and recommended fix. Challenge
test validity, skips/xfails, synthetic results and old completion claims.
Do not rewrite working code or start another phase during this review.
Record the smallest next fix, or state precisely which reviewed areas have no
findings and which were not reviewed. Fix findings in separate bounded tasks
and repeat this review/gates as justified by the changes.
```

Gate: blocking findings are resolved and reviewed; a review with untested areas
is not described as proof of zero bugs.

### P31 — Close the exact-build release gate

```text
Execute P31 only after all preceding required gates. Run the applicable complete
regression, native UI, integration, physical, security, performance and installed
artifact checks on the exact candidate commit/build. Reconcile every acceptance
A-H ID, I measurement, J requirement and master section-28 checkbox with actual
evidence in the P00 matrix. No unresolved known-defect xfail, silent deselection,
synthetic device result or old report may count as a pass. Identify any concrete
owner-approved limitation and its exact requirement separately; never assume
approval or call a missing locked capability implemented. Record hashes,
signatures, environment, commands/output, timings, ledger verification and all
remaining defects. Produce a concise factual release-readiness report and
explicitly state whether the locked definition of done is satisfied.
```

Gate: the final requirements are genuinely satisfied; otherwise record the
specific blocker and next bounded fix rather than advancing to merge.

### P32 — Reconcile GitHub and local branches safely

```text
Execute P32 only when the P31 gate and required reviews pass. Verify current
remote heads, clean source worktrees, PR dependencies and the exact approved
candidate. Reconcile the stacked UI integration/wiring branches with actual
GitHub main using the repository's chosen merge strategy; do not assume an
old SHA or rewrite shared history. Resolve conflicts narrowly and rerun the
relevant gates on the resulting commit before merging. This prompt authorizes
merging eligible reviewed PRs when their listed gates pass, not bypassing them.
Fetch and verify local main equals GitHub main without disturbing another
worktree or user changes. Verify the merged build/artifact, record release
commit/tag/hashes and keep recovery tags and branch history. Do not delete
branches or force-push merely to make the folder look clean.
```

Gate: GitHub and local main identify the actual verified integrated source;
release artifacts are tied to that result, not a stale pre-merge candidate.

### P33 — Deliver the usable product and maintenance handoff

```text
Execute P33. Provide the owner with the verified installed/release artifact,
simple launch and first-use instructions, actual text/voice/STOP shortcuts,
supported command examples, undo/history/settings access and clear unsupported
cases. Document backups and tested restoration for data/config/build source,
recovery after crash/update, safe sanitized diagnostics and known limitations.
Record exact versions and offline rebuild inputs, installer/signature/hash
checks, resource expectations and test commands for a future maintainer.
Update README, PROJECT_HANDOFF and the evidence matrix to the real final state.
Provide the release/main commit, GitHub links, recovery tag and file locations.
Remove remaining false completion or fixture-capability claims from current
documentation. Do not promise error-free operation forever or invent new
features. The handoff must be usable without this conversation or this account.
```

Gate: another developer can build/test/recover the verified product and the
owner can use it through the documented supported workflow.

## Coverage checks that prevent an incomplete finish

P00 must expand these into individual evidence rows. Range notation below is
not permission to count one passing example as every case in the range.

| Requirement source | Prompt coverage |
|---|---|
| A-01 through A-07: config/schema/targets/limits/factual copy | P00, P11-P13, P15, P24, P31 |
| B-01 through B-07: startup, idle, FAST and unload/cycles | P10, P13-P14, P22, P26, P28-P29, P31 |
| C-01 through C-10: mandatory capture, VAD, STT, parity and privacy | P07, P14, P19, P24, P26, P31 |
| D-01 through D-10: tools, postconditions, ownership and timeouts | P01-P06, P10-P11, P17, P20, P24, P31 |
| E-01 through E-10: UIA/OCR/freshness/geometry/privacy/STOP | P12, P23-P25, P27, P31 |
| F-01 through F-10: routing/plans/policy/limits/cancellation/privacy | P01-P03, P11, P13, P15, P24, P27, P31 |
| G-01 through G-10: STOP, rollback, ownership, crash and PID reuse | P01-P10, P17, P20, P27, P29, P31 |
| H-01 through H-08: risk, confirmation, elevation, redaction and user apps | P09, P11, P16, P21, P27-P29, P31 |
| I: actual-laptop resource/latency/quality budgets | P26, P31 |
| J and master section 28: full product definition of done | P00, P24-P33 |
| Master section 21: every named V1 capability, including unregistered gaps | P00, P11-P15, P24, P31 |
| Phase 14 owner direction and native placement acceptance | P16-P25, P31 |

| UI surfaces | Connection owner |
|---|---|
| 1 Dashboard | Existing status plus P17/P18/P22 |
| 2 Settings | P21 |
| 3 History/Activity | P20 |
| 4 Task running, 5 Step progress, 6 Route, 7 Tool call, 8 Tool result | P18 |
| 9 Rollback | P18/P20 |
| 10 Conflict alert | P20 |
| 11 Listening, 12 Live transcription, 13 Committed, 14 Silence timeout | P14/P19, one unified overlay |
| 15 Capture flash, 16 OCR match | P12/P23, target-window geometry |
| 17 Post-click verification | P18/P23, actual verification evidence |
| 18 Risk approval, 19 Policy block | P16/P18 |
| 20 Cancellation, 21 Worker termination | P17/P18, actual terminal/cleanup evidence |
| 22 Live message feed | P18/P20 |
| 23 Core health | P22, truthful status/readback |
| 24 Notices | P18, shared desktop host |
| 25 Critical error/recovery, 26 Setup | P22 |

## R1 — Resume after a long break or lost conversation

```text
Read PLUMA_COMPLETION_PROMPTS.md, current PROJECT_HANDOFF.md and the live
requirements/evidence map. Inspect actual Git branch/worktrees/remotes, recent
commits, current source and saved reports. Preserve unrelated local work.
Identify the first incomplete or invalidated milestone; do not assume the last
chat's claims are true. Reproduce the relevant baseline safely, state the exact
bounded next files/checks and complete that milestone only under the shared
contract. Do not restart completed phases, replay obsolete patch scripts or
silently advance past an unresolved gate. Update the handoff and recovery point.
```

## R2 — Recover without losing later work

```text
Use docs/workspace_cleanup.md and the wiring recovery document to identify
the exact source tag and any local data/config/build backup. Inspect current
state first. Create a separate checkout or restore into a separate destination
for verification; preserve current source and user data. For a shared code
regression prefer a reviewed revert commit with tests. Source recovery cannot
undo a runtime external commit; use actual executor undo evidence when valid.
Do not use broad reset/clean/delete/force-push or apply generated binary stashes
over newer code. Verify the recovered state and report exactly what was restored.
```

## M1 — Fix a bug after release

```text
Investigate this reported PLUMA behavior: [command, expected, actual, time/error].
Read the release handoff and relevant requirements. Reproduce it safely on the
recorded versions, create a meaningful failing regression, identify the cause
and implement the smallest bounded fix on an appropriate isolated branch.
Preserve supported behavior, dark styling and all safety/privacy invariants.
Run focused and relevant release regressions, verify the packaged result when
affected, commit/push, document recovery and report the exact fix and limits.
Do not bundle unrelated features or upgrade dependencies without evidence.
```

## M2 — Check an environment/dependency update

```text
Assess this proposed Windows/runtime/dependency/model update: [exact versions].
Compare it with the recorded working release and retain source, package and
data/config backups. Test it in an isolated supported environment before
changing the daily installation. Re-run the affected routing/voice/perception,
STOP/ownership, privacy, install and performance checks; compare quality and
resource behavior, not just compilation. Keep offline recovery/rebuild inputs.
Recommend retain/update with concrete evidence and a reversible migration plan.
Apply only the explicitly authorized bounded update and verify it afterward.
Do not enable automatic model downloads, hidden services or permanent elevation.
```

## What “build once and keep using it” should mean

Target a stable, reproducible, documented release with verified safety,
backups, versioned inputs and a tested recovery path. Windows, applications,
devices and runtime dependencies can change, so occasional bounded maintenance
may still be necessary. Pin and retain the known-good environment, then test
changes deliberately. This guide does not promise zero errors forever or add
an always-on updater, cloud dependency or maintenance service to PLUMA.
