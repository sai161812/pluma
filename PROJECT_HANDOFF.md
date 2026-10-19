# PROJECT HANDOFF & TECHNICAL CONTINUITY RECORD

## Current checkpoint: 2026-10-19, P05 authoritative terminal outcomes

This checkpoint supersedes earlier next-step/count statements. Locked source
requirements and the native dark UI are unchanged. This is a bounded gate,
not full STOP, backend, device, installed-artifact or release acceptance.

- **P05 bounded gate passed: BA-05 repaired; P01-P04 preserved.** Started clean
  on local/remote `ui-wiring` at `8956cb7ec669df89b79e98c411e4c90f63016be0`.
  Coverage passed before editing. Prerequisites freshly passed **111 checks in
  13.72s**. Original BA-05 reproduced: **1 failed in 0.63s**, supervisor residual
  overwritten by returned/history STOPPED. Original assertion is unchanged;
  only its strict marker is removed.
- [P05 evidence and terminal contract](docs/completion/p05_evidence.md) records
  exact commands, source blobs, reports, SQLite/Windows facts, failure fixtures,
  remaining gaps and recovery. Five runtime files, three test files and four
  handoff/evidence documents change. All inherited P01-P04 assertions remain;
  FAST's old mock call-count check now asserts authoritative atomic terminal
  state/evidence. Intermediate failures/corrections are recorded.
- All routes project the supervisor's state, finished/pending finalization,
  persistence flag, residual and redacted rollback/cleanup facts. FAST failure
  and multi-step STOP/failure share its existing cleanup owner. No independent
  route terminal write or second rollback overwrites residual truth. Last-step
  STOP and terminal commitment share the short admission boundary; repeated
  finalization preserves outcome, timestamp and evidence. Incomplete cleanup
  remains nonterminal with pending copy; no stopped/success claim is fabricated.
- Terminal state, cleanup journal and resource mirror persist atomically and
  are read back. Failure makes success FAILED or clean STOP residual, records
  fixed persistence evidence and queues a conservative retry after the original
  write. Real blocked-writer tests prove late writes cannot be the last stale
  success. Unavailable storage reports `terminal_persisted=false`; explicit
  later reconciliation preserves state without repeating cleanup/rollback.
- Execute IPC adds factual completion/persistence/residual/rollback fields;
  authenticated native pipe and recent-history readback pass. Existing STOP
  acknowledgements remain BA-08 for P08. No runtime shutdown/voice/protocol/UI
  milestone was started. Action entry stays disabled.
- Final focused: **228 passed in 22.34s**, including **45 new outcome cases**.
  Relevant isolated regressions: **553 passed, 3 skipped, 1 deselected,
  6 xfailed in 36.87s**. Prerequisites rechecked **111 passed in 10.89s**;
  owned-worker containment **3 passed in 2.95s**. Raw audit: **6 failed,
  9 passed in 0.64s**. Matrix: **298 source items / 324 rows**. Windows 11
  build 26200 / Python 3.12.10 / pytest 8.3.3. Fixture keys remaining: zero;
  all 115 FAST cases have explicit desktop-isolation properties. Retain the
  P02 isolation correction. Skips/exclusion/xfails are not acceptance.
- Real file conflicts/partial rollback, reopened SQLite, aborted transactions,
  delayed queued commits and authenticated owned native pipes are verified.
  Planner/perception/device adapters are inert, audio emulated; existing real
  P03/P04 worker/descendant/unrelated-process checks pass unchanged. No physical
  microphone/model/OCR/hotkey, full unit/product/install or p95 claim is made.
- **Four findings remain: BA-06 through BA-09, six raw failures.** Runtime
  shutdown, capture/empty voice capsule, typed truthful STOP acknowledgements
  and conditional initial credential privacy remain. Full tool/model/screen/
  voice/UI/recovery/security/release gates remain in the matrix. No requirement
  or acceptance limitation is waived.
- P05 is committed/pushed on `ui-wiring`. PR 1/2 remain draft/open/unmerged;
  main remains `6dbf589`, integration `9544752`. Pre-P05 recovery is
  `8956cb7ec669df89b79e98c411e4c90f63016be0`; inspect in a new detached
  worktree. Existing tags/worktrees/archive/stash are preserved; no merge,
  worktree switch, destructive cleanup, force push or security bypass.
- **Next safe milestone: P06 only, BA-06 bounded runtime shutdown/drain.**
  Reproduce its original assertion before editing; reject work, latch/cancel,
  drain handlers and retained terminal/unpublished-preparation owners, verify
  cleanup, persist outcomes, close registry before storage, and test repeated
  bounded close. P10 combines real descendant/failure/ledger paths after all
  nine audit repairs. P06 was not started. Do not advance or enable actions.

## Previous checkpoint: 2026-10-19, P04 verified cleanup and residual ownership

This checkpoint supersedes earlier next-step/count statements. Locked source
requirements and the native dark UI are unchanged. This is a bounded gate,
not full STOP, backend, device, installed-artifact or release acceptance.

- **P04 bounded gate passed: BA-04 repaired; P01-P03 preserved.** Started clean
  on local/remote `ui-wiring` at `f6543d1a1df622e8f7d2a64131cd49d32343a298`.
  Coverage passed before editing. Prerequisites freshly passed **72 checks in
  12.67s**. Original BA-04 reproduced first: **1 failed in 0.42s**, clean
  STOPPED despite termination failure and lost worker reference. The original
  assertion is unchanged; its strict marker is removed.
- [P04 evidence and cleanup contract](docs/completion/p04_evidence.md) records
  exact commands, tested blobs, reports, verified Windows/SQLite facts, failure
  injections, limits, recovery and next gate. Typed cleanup evidence combines
  worker/root, Job Object, temporary resource, snapshot, rollback, irreversible
  effect and persistence readback. Errors use fixed factual codes, not raw
  exception bodies or tool arguments. Unresolved handles/identity survive
  terminal cleanup, registry close/acquisition and pruning.
- Native jobs read active-process count before handle closure; failures remain
  owned. A termination exception can resolve only through positive fallback
  absence/closure readback. Worker cleanup retains P03's original process
  handles, task/PID/creation/class identity, bounded I/O and shared latch.
  No new detached helper, model/capture workload or name/PID killer is added.
- Unknown worker/job absence defers rollback and temporary deletion. Partial
  rollback preserves remaining pre-state. Registered temps capture identity,
  reject changed/missing/reparse identity, and read absence before release;
  pre-existing resources and unregistered computed task paths are untouched.
  Existing file/audio rollback recipes read postconditions; database undo
  consumes only matching restored memory pre-state. Deferred resource identity
  is retained in reports for later inspection.
- Clean STOP requires resolved evidence; otherwise core state is
  STOPPED_WITH_RESIDUAL. Ordinary successful-terminal cleanup failures become
  FAILED. Failed unpublished preparations remain tracked without publishing a
  stale task. Migration 0002 journals redacted reports independently of task
  history insertion, atomically mirrors existing task resources and reads the
  journal back. This stores no fabricated command/input mode. Queue writes have
  two-second acknowledgement bounds; storage failure retains evidence and
  prevents clean core completion. Returned/history reconciliation remains P05.
- Final focused: **183 passed in 20.10s**, including 38 new cleanup cases and
  seven existing database migration/WAL/writer cases. Relevant regressions with
  explicit desktop isolation: **507 passed, 3 skipped, 1 deselected, 7 xfailed
  in 36.94s**. Additional owned-worker containment: **3 passed in 3.60s**.
  Raw audit: **7 failed, 8 passed in 0.88s**. Matrix: **298 source items /
  324 rows**. Windows 11 build 26200 / Python 3.12.10 / pytest 8.3.3; isolated
  storage, owned processes/jobs/files/pipes, SQLite and inert/audio emulation.
  Fixture keys remaining: zero. All 115 FAST cases have desktop-isolation tags;
  retain P02's isolation correction. Skips/exclusion/xfails are not acceptance.
- Real supervisor cleanup reads root/descendant exit, unrelated fixture
  survival, empty/closed jobs, absent late effects and SQLite cleanup/state
  back. Failures cover unknown worker exit, live/query/close failures, no-op
  deletion/rollback, conflicts, pre-existing ownership, pruning, repeated STOP,
  snapshot failure, unpublished preparation, persistence/redaction and bounded
  acknowledgement. No full unit/product/device/install or hotkey/p95 claim.
- P02/P03 inert doubles now expose explicit readback. P02's former expected
  ROLLING_BACK after resource error now requires factual residual state; latch
  and ordering assertions remain. BA-08's old resource-error setup ceased to
  be nonterminal after P04, so its injection now fails after the actual
  ROLLING_BACK boundary; original guard/assertion/strict marker remain. P08 is
  still defective. An initial new test's missing verifier was corrected; all
  intermediate reports are retained under ignored output/p04.
- **Five findings remain: BA-05 through BA-09, seven raw failures.** FAST
  returned/history residual truth, runtime drain, voice capture/empty-capsule,
  IPC outcome truth and initial credential privacy remain. Full tool/model/
  voice/screen/native-device/recovery and release gates remain in the matrix.
  UI action entry stays disabled. Core evidence alone does not repair results.
- P04 is committed/pushed on `ui-wiring`. PR 1/2 remain draft/open/unmerged;
  main remains `6dbf589`, integration `9544752`. Pre-P04 recovery is
  `f6543d1a1df622e8f7d2a64131cd49d32343a298`; inspect in a new detached
  worktree. Existing tags/worktrees/archive/stash are preserved; no merge,
  worktree switch, destructive cleanup, force push or security bypass.
- **Next safe milestone: P05 only, BA-05 authoritative terminal projection.**
  Reproduce `test_fast_stop_preserves_supervisor_residual_outcome` with
  `--runxfail`; align returned results/history with supervisor state and residual
  details, test racing STOP, partial/non-undoable effects and storage failures.
  P06 must include retained terminal/preparation owners in shutdown drain;
  P10 reruns combined P01-P09 Windows/failure/ledger paths and handle lifecycles.
  P05 was not started. Do not advance automatically or enable actions.

## Previous checkpoint: 2026-10-19, P03 interruptible owned workers

This checkpoint supersedes earlier next-step/count statements below. The master
specification is unchanged. This is a bounded gate, not complete STOP, backend,
UI, device, installed-artifact or release acceptance.

- **P03 bounded gate passed: BA-02 repaired; P01/P02 preserved.** Started clean
  on local/remote `ui-wiring` at `f303f231b825cad151fcf0846b3966e6ccc4a2a2`.
  Coverage passed before editing; prerequisites freshly passed **45 checks in
  3.21s**. Original BA-02 reproduced first: **1 failed in 0.50s**, STOP unable
  to acquire the controller during the outstanding response wait.
- [P03 evidence and worker lifetime contract](docs/completion/p03_evidence.md)
  records exact commands, tested blobs, isolated reports, real Windows readback,
  review, limitations and recovery. Request serialization is separate from
  short lifetime state and bounded cleanup locks. STOP latches before waiting;
  parent overlapped message-pipe sends/reads check deadline/cancellation, with
  bounded drain/close. No detached I/O or cleanup helper thread is introduced.
- Workers receive a cooperative view of the shared task latch. Explicit
  disposal wakes parent cancellation waiters. Startup and cleanup failures
  retain controller ownership for retry; a pending synchronous OS launch
  reports a bounded failure until its original caller can finish cleanup.
  No ToolCall is sent before identity and both Job Object assignments succeed.
  Root exit is read back; the original Process/creation identity is retained.
- Identity/readback and Job Object assignment use the original native process
  handle, avoiding a PID lookup/reuse race. Worker-only jobs contain descendants;
  shared capsule jobs are preserved. Idle pool acquisition uses a new controller
  rather than retagging one an earlier task could still reference. Force
  termination targets owned handles/jobs only. Same-task disposed restart is
  rejected; repeated/concurrent disposal remains bounded.
- Twenty-six new cases cover actual Windows pending writes/reads and hung/
  cooperative workers, full request pipes and response timeouts, owned descendant
  exit with an unrelated fixture surviving, startup races, PID substitution,
  failure/retry, pool ownership, repeated disposal and SQLite cancellation
  readback. BA-02's original 150ms assertion is unchanged; its process double
  now records killed exit for readback, and its strict marker is removed.
  Review caught/fixed an intermediate parent-cancel regression without changing
  P01's assertion. P01 cancellation/tests and P02 supervisor/tests are unchanged.
- Final focused: **126 passed in 14.48s**. Relevant regressions with explicit
  `-p tests.fixtures.desktop_isolation`: **468 passed, 3 skipped, 1 deselected,
  8 xfailed in 28.50s**. Additional owned-worker containment: **3 passed in
  2.89s**. Raw audit: **8 failed, 7 passed in 0.67s**. Matrix: **298 source
  items / 324 rows**. Windows 11 build 26200 / Python 3.12.10 / pytest 8.3.3;
  isolated user-local storage, test/audio emulation, owned fixtures; zero
  fixture keys remaining. All 115 FAST cases carry the isolation property.
  Skips, elevation exclusion, emulation and expected failures are not acceptance
  passes or approved limitations. Retain P02's inherited isolation correction.
- Actual controller cancellation-to-disposal observations were 63ms hung / 78ms
  cooperative against 30-second tool deadlines. Root/descendant exit, cooperative
  marker/exit code, absent late effects and unrelated fixture liveness were read
  back. These are single fixture observations, not hotkey/loaded-device p95 or
  whole-supervisor latency. P10 must rerun them through combined P01-P09 task,
  rollback, cleanup, ledger/IPC and runtime/voice paths; P26 measures performance.
- **Six findings remain: BA-04 through BA-09 (eight raw failures).** In
  particular supervisor/registry reference loss and aggregate cleanup readback
  remain defective; controller exceptions do not establish clean STOPPED.
  FAST residual truth, runtime/voice drain, IPC truth and initial credential
  privacy remain open. Action entry remains disabled; native dark UI unchanged.
- P03 is committed/pushed on `ui-wiring`; PR 1 and PR 2 remain draft/open and
  unmerged. Main remains `6dbf589`; UI integration remains `9544752`. No
  worktree switch, merge, force push, destructive cleanup or security bypass.
  Pre-P03 recovery: `f303f231b825cad151fcf0846b3966e6ccc4a2a2`; inspect in a
  new detached worktree. Existing recovery tags/archive/stash/worktrees remain.
- **Next safe milestone: P04 only, BA-04 cleanup readback and retention.**
  Reproduce `test_failed_worker_cleanup_requires_residual_state` with
  `--runxfail`; preserve failure/identity until verified absence, combine
  worker/job/resource/rollback evidence and persist factual residual state.
  Use P03's retained identity and pending-cleanup failure paths. P04 was not
  started. Do not advance automatically or enable UI actions.

## Previous checkpoint: 2026-10-19, P02 global latch-all

This checkpoint supersedes earlier next-step/count/isolation statements below.
The master specification is unchanged; this is a bounded milestone, not full
STOP, backend, UI or release completion.

- **P02 bounded gate passed: BA-01 repaired; P01 preserved.** Started clean on
  local/remote `ui-wiring` at `eab9d8d70ce2abbf45e0171501678a3c41736299`.
  Coverage passed before editing, and P01 prerequisites freshly passed
  **22 checks in 2.68s**. BA-01 reproduced first: **1 failed in 0.58s**, first
  cleanup observed `[(True, False), (True, True)]`.
- [P02 evidence and latch/request contract](docs/completion/p02_evidence.md)
  records exact commands, tested blobs, isolated reports, timings, limitations,
  recovery and the next gate. Global STOP now latches every affected
  nonterminal capsule before state claims or cleanup. A short state/publication
  lock is never held for resource construction, grace, worker I/O, rollback or
  cleanup. Existing cleanup remains owned by its single STOPPING claim, including
  overlapping STOP calls and repeated STOP during ROLLING_BACK.
- Requests published before STOP are included. Creation during global STOP is
  rejected before allocation; preparation crossing a STOP generation is rejected
  before publication and its prepared resources closed. Fresh explicit commands
  can proceed after all global callers return. No queued retry, detached cleanup
  branch or second cancellation tree is introduced. Terminal tasks are preserved.
- Twenty-two new controlled ordering cases cover blocked cleanup phases,
  later-task registry admission, native worker events, simultaneous/global/task
  STOP, terminal states, preparation/publication/start/success races, failure,
  empty/repeated STOP and real SQLite readback. P01's execution source/tests
  remain unchanged. BA-01's original assertion remains; only its marker is removed.
- Final focused checks: **100 passed in 7.45s**. Final relevant regressions,
  explicitly loading the desktop-isolation plugin: **441 passed, 3 skipped,
  1 deselected, 9 xfailed in 21.94s**. Raw audit: **9 failed, 6 passed in 0.84s**.
  Windows 11 build 26200 / Python 3.12.10 / pytest 8.3.3; isolated user-local
  storage, test/audio emulation and owned fixtures. Existing skips/unexecuted
  elevation and expected failures are not acceptance or approved limitations.
  No complete product/device/install suite is claimed. Fixture keys remaining: zero.
- **Test-isolation correction:** an earlier inherited FAST regression run was
  executed before review found its clipboard/window/app-close helpers could
  reach the real desktop. Prior desktop state was not captured; no no-impact
  or restoration claim is made. P01 used the same inherited sub-suite; its
  evidence now carries a correction. The final P02 run loads
  `-p tests.fixtures.desktop_isolation`, with in-memory clipboard, no target
  window and blocked desktop termination for FAST cases. This is fixture
  route/orchestration evidence, not native desktop acceptance. Use that plugin
  for future bounded runs of this suite; retain the original logs as disclosed.
- Controlled latch acknowledgement was recorded separately from cleanup in
  JUnit (0.196-2.381 ms to first cleanup boundary across four single fixture
  observations). These are not real hotkey/p95 or loaded-device measurements.
  Actual combined Windows descendant/cleanup and latency gates remain P10/P26.
- The [matrix](docs/completion/requirements_matrix.md) remains complete:
  **298 source items / 324 rows**. BA-01 and BA-03 pass bounded gates; seven
  findings remain (BA-02, BA-04 through BA-09), with nine raw failures. Typed
  acknowledgement/terminal truth remains P08; candidate IDs are not clean STOP
  proof. Action entry stays disabled; native dark UI and locked requirements
  are unchanged.
- Active folder/branch remain `D:\Workspace\DEVEL\PLUMA` / `ui-wiring`.
  P02 changes are committed/pushed there; PR 1 and PR 2 stay draft/unmerged,
  `main` stays `6dbf589`. Recovery point before P02:
  `eab9d8d70ce2abbf45e0171501678a3c41736299`; inspect in a new detached
  worktree as documented. Existing tags/archive/stash/worktrees are preserved.
- **Next safe milestone: P03 only, BA-02 interruptible owned-worker waits.**
  Reproduce `test_worker_stop_interrupts_outstanding_response_wait` using
  `--runxfail`, then separate execution serialization from cancellation and
  termination ownership. Preserve P01/P02 and bounded, verified owned cleanup.
  P03 was not started; do not advance automatically or enable UI actions.

## Previous checkpoint: 2026-10-19, P01 executor admission

This checkpoint supersedes the P00 next-step/count statements below. The master
specification remains immutable; this is a bounded work packet, not completion
of the STOP system, backend, UI or release.

- **P01 bounded gate passed: BA-03 repaired.** Before editing, P00 coverage
  passed and the clean local/remote `ui-wiring` checkout was
  `81cd450e8991f549f7605bebfb9231cf1e063452`. The raw reproduction failed with
  `Executor started after the latch was set: [True]` (**1 failed in 0.54s**).
- [P01 evidence and admission contract](docs/completion/p01_evidence.md) records
  exact commands, tested runtime/test blob hashes, environment, outputs,
  verification/SQLite/undo evidence, recovery and next gate. Reports, JUnit and
  working-file SHA-256 hashes remain ignored under `output/p01/`.
- `pluma/tools/registry.py` now invokes registered executors through the same
  worker-side admission wrapper for thread and process paths. Parent checks
  after policy/pre-state/controller waits do not grant a stale queued permit.
  Noncancellable metadata cannot bypass the latch. Rejected entry returns
  unverified cancellation, without inventing an effect or undo record.
- `CancellationToken` serializes thread admission with cancel and lazily
  publishes a native manual-reset Windows event for owned process workers.
  The zero-time worker kernel read is ordered against SetEvent without a
  child-held lock. Native handles are inherited during spawn and finalized
  with their lifetime. A call admitted before the latch is already in flight;
  no lock is held through its body. P03 still owns interrupting active waits.
- The original BA-03 assertion is unchanged and its xfail marker is removed.
  Twenty-one new admission cases cover policy/pre-state waits, queued thread
  cancellation/timeout, late worker preparation/startup/receive, task ownership,
  successful verification/undo/SQLite, failure readback and handle lifetime.
  Actual Job Object-contained spawned workers prove live gate inheritance,
  cancellation before marker creation, controller rebinding and latch safety
  after owned worker crash. Their exit is read back after fixture cleanup.
- Focused suite: **78 passed in 6.90s**. Relevant regressions: **418 passed,
  3 skipped, 1 deselected, 10 xfailed in 22.10s**. Raw audit: **10 failed,
  5 passed in 0.79s**. Windows 11 build 26200 / Python 3.12.10 / pytest 8.3.3;
  isolated user-local storage, owned inert fixtures, test/audio emulation.
  Existing corpus skips and the unexecuted elevation operation are recorded,
  not acceptance passes or approved limitations. No full unit/product/device/
  install suite or hotkey p95 is claimed. Remaining fixture keys: zero.
- [Live requirements matrix](docs/completion/requirements_matrix.md) still
  validates **298 source items / 324 rows**. BA-03 is implemented for its
  bounded gate; full F-08/G-02 and P10 integration remain open. Eight backend
  findings remain: BA-01/02/04/05/06/07/08/09, with ten failing assertions.
  No remaining assertion was weakened or defect marker removed.
- Active folder remains `D:\Workspace\DEVEL\PLUMA`, branch `ui-wiring`.
  Meaningful P01 changes are committed/pushed there. PR 1 and PR 2 remain
  draft/open and unmerged; `main` stays `6dbf589`. UI source/design and disabled
  action entry are unchanged. No automatic progression or worktree switch.
- Pre-P01 recovery: `81cd450e8991f549f7605bebfb9231cf1e063452`; use a new
  detached worktree as documented in P01 evidence. Existing recovery tags,
  archive/stash and detached audit worktree are preserved. No reset/clean/
  force push or security-policy bypass.
- **Next safe milestone: P02 only, BA-01 latch-all ordering.** Reproduce
  `test_global_stop_latches_every_task_before_first_grace` with `--runxfail`.
  Latch every affected CREATED/RUNNING task before any cleanup/grace wait;
  cover simultaneous STOP/racing requests and preserve P01 admission evidence.
  Keep action entry disabled. P02 must pass before P03; neither was started.

## Previous checkpoint: 2026-10-19, P00 requirements/evidence map

This dated checkpoint supersedes historical completion claims, test counts and
next-phase instructions below. The master specification remains authoritative.

- **P00 documentation gate passed.** The
  [live requirements matrix](docs/completion/requirements_matrix.md) contains
  324 traceable rows covering 298 extracted source items plus 26 cross-cutting
  contracts/optional items: all 72 A-H cases, seven I metrics, 17 J bullets,
  18 section-28 checkboxes, 73 section-21 tool names, 26 UI surfaces, nine BA
  findings, eight locked capabilities, 14 engineering laws, 39 build-plan gate
  bullets and 15 owner placement cases. No product phase or release is marked
  complete. All requirement definitions remain unchanged.
- [P00 evidence and recovery](docs/completion/p00_evidence.md) records the
  inspected source `88078bb3c625f0a741b329144f747bbb3fa1dd69`, actual GitHub
  state, source/test/build hashes, commands/results, historical-claim review,
  source findings and the prioritized bounded P01 packet. The documentation
  checker imports no PLUMA runtime; seven inert negative probes reject omitted
  requirements, altered wording, invalid status/owner/evidence, duplicate IDs
  and malformed rows. Coverage is documentation evidence, not runtime acceptance.
- Active development folder: `D:\Workspace\DEVEL\PLUMA`, branch `ui-wiring`.
  The former `PLUMA-ui-wiring` checkout remains detached at audited `55b625c`;
  the `main` and UI integration worktrees are retained separately.
- Dark native UI and authenticated read-only dashboard status are implemented.
  Command entry remains disabled; action/voice/event/settings/history wiring
  and physical/release acceptance are unfinished.
- [Backend audit](PLUMA.UI/PLUMA.UI/docs/backend_wiring_audit.md): nine open
  findings (eight P1, one conditional P2), reproduced by eleven assertions.
  Fresh P00 audit: **4 passed, 11 xfailed in 1.03s**; raw `--runxfail`:
  **11 failed, 4 passed in 0.90s**. Relevant bounded regressions:
  **277 passed, 1 deselected, 11 xfailed in 9.06s**. Windows 11 build 26200,
  Python 3.12.10 / pytest 8.3.3, isolated user-local storage; audio/test mode
  fixtures, one unexecuted elevation operation. Reports/command vectors/JUnit
  are ignored under `output/p00/`; remaining fixture credentials: zero.
  These are open defects, not backend/device/full-suite certification.
- Fresh source inspection identifies additional required gaps, mapped to their
  later packets: absent catalog ToolSpecs and placeholder browser/process/
  terminal modules; configured step limit not propagated; MEDIUM explicit
  intent and material approval/elevation wiring; clipboard readback and undo
  evidence; real model/STT/OCR cancellation/ONNX/device evidence; effective
  configuration and missing UI events/settings/history. Inspection findings
  require bounded reproduction before repairs and are not extra reproduced BA
  findings. Optional output/wake modes do not make voice input optional.
- Current GitHub query: `main` remains `6dbf589`; PR 1 is draft/open into
  `main`, PR 2 is draft/open from `ui-wiring` into `ui-polish-integration`.
  P00 changes are committed/pushed on the existing `ui-wiring` branch; no merge,
  retarget, force push or worktree switch. Hosted native run `39243181549`
  remains source-specific evidence (head `64559bd`, tested merge `b333e746`),
  not a fresh P00 physical UI test. See the evidence record for its build hash.
- [Completion prompts](PLUMA_COMPLETION_PROMPTS.md) define the remaining work
  against the existing specification/build/acceptance documents. **Next safe
  step: execute P01 only**, first reproducing BA-03 with `--runxfail`, then
  repair actual thread/process executor admission versus STOP during pre-state
  capture/queued work. Keep action entry disabled. P01 must pass its bounded
  gate before P02; P00 did not begin that repair.
  Execute one bounded prompt per task; do not start later milestones automatically.
- Requested workspace cleanup archives obsolete root patch scripts and generated
  output, retains historical records under `docs/history`, and keeps the owner's
  previously untracked capability note in ignored `docs/local`.
  [Cleanup/recovery record](docs/workspace_cleanup.md) names the backups and stash.
- GitHub recovery tags: `pre-ui-wiring-2026-10-19` at `04bc1fb` and
  `pre-project-cleanup-2026-10-19` at `55b625c`. Original branch histories and
  local generated-file state are preserved. No PR is merged by this preparation.
- Pre-P00 recovery source: `88078bb3c625f0a741b329144f747bbb3fa1dd69`.
  Inspect it in a new detached worktree as described in P00 evidence; do not
  reset the active branch or apply archived generated state over current source.
- P00 verification: `python docs/completion/verify_requirements_matrix.py`
  reports **298 source items, 324 traceable rows**, all required wording,
  ownership/status/evidence cells and local links valid; ignored
  `python output/p00/check_matrix.py` passes **seven negative probes**.
  `git diff --check` passes. A separate final diff review checks scope, secrets,
  fabricated success, misleading test claims and preservation of production
  sources/locked documents. No full product suite, device/performance/install
  gate or owner-approved limitation is claimed.
- Cleanup/guide verification: eight housekeeping checks passed (including 46
  resolved local links, 34 ordered prompts, 72 numbered acceptance IDs and 26
  surface IDs); packaging regressions **2 passed in 0.41s**; visible-copy source
  scan **33 compiled XAML files passed**. Helper output/package checks used
  mocked execution and inert binaries, not real acceptance or a distributable.
  Details and commands are in the cleanup record. Backend/tests/UI runtime and
  locked requirement documents remain unchanged from audited `55b625c`.

The sections below are retained historical engineering records. Their older
"COMPLETED", "Certified Stable" and "next Phase 11" statements do not override
this checkpoint or the current audit.

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
| **Phase 12** | Latency and quality benchmark tuning, leak testing | **COMPLETED** | 405 (cumul.) |
| **Phase 13** | Packaging, `%LOCALAPPDATA%` isolation, crash recovery | **COMPLETED** | **430 (cumul.)** |
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

### Next Phase: **Phase 14 — Creator-Directed UI Implementation**
Reference: `PLUMA_BUILD_PLAN.md` Phase 14 & `PLUMA_MASTER_SPEC.md` §16, §17, §18, §19.

### Notes for Phase 14:
- All non-visual functional UI contracts (`ConfirmationContract`, `ActivityViewContract`, `SettingsContract`) are in place.
- Per `PLUMA_BUILD_PLAN.md` §Phase 14 and `AGENTS.md`, Phase 14 is **blocked on user/owner direction** for visual styling.
- Do not invent colors, typography, cards, gradients, waveforms, or AI dashboard aesthetics until the user specifies the UI design.

### Summary of Completed Work (Phases 0–13):
- **414 automated unit and benchmark tests passing with 0 failures and 0 warnings**.
- Standalone packaging configuration in `packaging/pluma.spec`.
- Full production entry point in `pluma/app.py`.
- Windows storage hierarchy under `%LOCALAPPDATA%\Pluma\` and `%APPDATA%\Pluma\`.
- Automatic crash recovery and state reconciliation in `pluma/core/recovery.py`.

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

