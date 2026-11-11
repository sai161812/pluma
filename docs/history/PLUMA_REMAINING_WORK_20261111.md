# PLUMA: remaining work, completion prompts and final release audit

Prepared **2026-11-10 (Asia/Calcutta)** from the checkout and evidence below.
This is a continuation handoff, not a replacement specification or a new claim
of release readiness. Refresh its cursor and findings as work is completed.

Latest source packet, local commit
`ac8a65df7e9b7ca25d18e932cd8272830b63b494`: [E117](docs/completion/e117_interrupted_upgrade_recovery_code_only.md)
adds transaction-backed interrupted-upgrade rollback and guarded cleanup;
[E118](docs/completion/e118_offline_rebuild_source_preparation.md) adds
hash-validated Python and locked local NuGet inputs, exact toolchain checks and
offline rebuild mode. The earlier [E116](docs/completion/e116_package_shutdown_code_only.md)
prepares the unified Core + WinUI x64 candidate and identity-bound graceful
Core shutdown. E116-E118 are local, unpushed and unverified. The owner has now
resumed verification; P24 E119 adds three accepted emulated volume-status
cases, bringing the corpus total to 25/140. This does not
close P24 or P25-P33 acceptance, signing, recovery or exact-build gates.

## 1. What is finished

**Scoped implementation is recorded complete through P23. P24 is in progress:**
bounded acceptance packets are recorded in [E110](docs/completion/e110_p24_readonly_corpus_slice.md),
[E111](docs/completion/e111_p24_owned_folder_creation.md),
[E112](docs/completion/e112_p24_owned_mutation_acceptance.md),
[E113](docs/completion/e113_p24_owned_undo_prepared.md) and
[E119](docs/completion/e119_p24_volume_status_readonly.md).
That is P01-P23 plus the P00 baseline: **24 of the 34 labels P00-P33**.
**Ten milestones remain: P24-P33.** These numbers are the completion guide's
milestones; they are different from the build plan's original phases 0-14.
The remaining validation and release work is substantial; the count is not a
percentage of effort or a guarantee that no implementation fixes remain.

| Current fact | Checked state |
| --- | --- |
| Working checkout | `D:\Workspace\DEVEL\PLUMA`, branch `p12-preparation`; E112 production-source baseline `d3df79308aa806cc0494853e5e3ca9854b2cfc30` |
| Current tested checkout | E119 commit `ca37ee3ae7817b15825ea7e75d8f5d61e5f73c2a`, based on production-source parent `f1f7c5d58ebc284a16a231d4044753b7223dc3af`; test-source SHA-256 `0C781AC71ECA1C2102862840FE84C87B1E82ECE2CE21D30D476DAB518BE74ABE`. Focused acceptance: 19 passed; fixture-only audio/router regressions: 257 passed, 7 deselected. E117/E118 release code at `ac8a65d` remains unverified; untracked root `uv.lock` is preserved |
| P23 product baseline | `60414fab69a7958170d810532da4530907744ae2`; E111 adds a bounded FAST file-route purpose fix in `pluma/core/router.py`; E112 changes tests/evidence only |
| P24 packet evidence | [E110](docs/completion/e110_p24_readonly_corpus_slice.md): 14 cases / 238 checks; [E111](docs/completion/e111_p24_owned_folder_creation.md): 4 additional cases / 247 checks; [E112](docs/completion/e112_p24_owned_mutation_acceptance.md): 2 additional cases / 259 checks; [E113](docs/completion/e113_p24_owned_undo_prepared.md): 2 undo cases and 261 regressions passed; [E119](docs/completion/e119_p24_volume_status_readonly.md): GC-013–015, 19 focused acceptance passed and 257 fixture-only regressions passed / 7 deselected. Accepted count is 25/140; a fresh E112 rerun passed 2/2 but did not reproduce its historical cold-run failure, whose original cause remains unknown. |
| Remote development head at packet start | `origin/p12-preparation` matched `c9f597f0f8ee4e0e0531fb724fff5105a5a3cfec`; P24 commits require a normal push |
| Last recorded main checkpoint | `0468a031238261bee5bc79bd04b16a3d1964a3a9` (P00-P20); main was not refreshed or merged in this packet |
| Integration still pending | P21-P23 and subsequent work; refresh remote refs during the P32 gated integration step |
| Latest readiness record | [E109](docs/completion/e109_p00_p23_readiness.md), following [E108 P23 closure](docs/completion/e108_p23_live_hosting.md) |
| Traceability snapshot | 336 rows: **229 IMPLEMENTED, 102 UNVERIFIED, 5 OPTIONAL**; no MISSING, DEFECTIVE or UNWIRED rows recorded |
| Locked catalog / UI | E109 records all 73 master tool names in 90 registered tools; all 26 required surfaces have scoped implementation evidence |
| Existing fixed corpus | 140 unique cases: FAST 93, SCREEN 15, SMART 27, DEEP 5; E110-E113 and E119 execute 25 FAST/READ/LOW/MEDIUM cases end-to-end, with fixture-owned path substitutions and test confirmation |

`IMPLEMENTED` means the narrow invariant described in the matrix, not that every
physical, installed, performance or adversarial scenario has passed. The 102
UNVERIFIED rows overlap: they are not 102 separate confirmed bugs. Optional SAPI
output, wake phrase, alternative Windows OCR evaluation and vector memory must
not become new mandatory work; mandatory voice input remains required.

### Completed implementation and its boundaries

| Milestones | Recorded completed work | Evidence / retained qualification |
| --- | --- | --- |
| P00 | Requirement/evidence map and owner scope | [Matrix](docs/completion/requirements_matrix.md), [E109](docs/completion/e109_p00_p23_readiness.md) |
| P01-P10 | Admission/STOP, cancellation, owned cleanup, authoritative outcomes, shutdown, voice lifetime, authenticated private IPC | E109 and linked native safety evidence; broader combined crash/device acceptance remains later |
| P11-P13 | Typed tools, policy/elevation, verification/undo, UIA/OCR grounding, constrained local planner/lifecycle | E109; actual native model/OCR evidence is historical and identified there; physical focus/audio deferrals remain |
| P14 | Mandatory voice/text backend parity, STT cancellation and clarification/privacy | [E80](docs/completion/p14_e80_audit_closure.md); fresh C-02 timing retest is still deferred to P25 |
| P15-P17 | Versioned IPC/reconnect, scoped approvals, text submission and independent STOP | [P15](docs/completion/p15_e84_contract_completion.md), [P16](docs/completion/p16_material_approval.md), [P17](docs/completion/p17_command_submission.md) |
| P18-P20 | Live factual projections, unified voice overlay, history/details/undo/conflicts | [P18](docs/completion/p18_live_runtime.md), [P19](docs/completion/p19_overlay_acceptance.md), [E99 main integration](docs/completion/e99_p20_shell_main_integration.md) |
| P21 | Persistent validated settings, effective application/recovery and guarded undo | [E103](docs/completion/e103_p21_completion.md) |
| P22 | Truthful setup/readiness, controlled owned Core restart and recovery | [E104](docs/completion/e104_p22_completion.md), [E105 recheck](docs/completion/e105_p22_completion_recheck.md) |
| P23 | Live capture/OCR feedback, target geometry, composed native pixels, priority STOP and owned cleanup | [E108](docs/completion/e108_p23_live_hosting.md); physical monitor/device review remains P25 |
| P24 | Bounded acceptance packets only; full milestone remains open | [E110](docs/completion/e110_p24_readonly_corpus_slice.md), [E111](docs/completion/e111_p24_owned_folder_creation.md), [E112](docs/completion/e112_p24_owned_mutation_acceptance.md), [E113](docs/completion/e113_p24_owned_undo_prepared.md) and [E119](docs/completion/e119_p24_volume_status_readonly.md): 25 unique cases overall; E119's focused 19 and selected 257 regressions pass. Seven audio regressions remain deselected for physical-device access or unavailable `comtypes`; the historical E112 cold-run failure did not reproduce in a fresh rerun, but its original cause is unknown |

### Evidence available, without inventing a fresh full-suite pass

- E109's broad selection originally ended **2318 passed / 1 failed**. The stale
  tool-count test was then repaired without weakening assertions. The affected
  P12 selection is **247 passed**, committed affected native/registration checks
  **14 passed**, voice/privacy **36 passed**, owned native checks **13 passed**,
  and authenticated Python/C# IPC **403 passed**. Their local XML/logs were read
  during this task; these are retained November 5 results, not reruns today.
- E108's normal [Windows run 41982933518](https://github.com/sai161812/pluma/actions/runs/41982933518)
  on `6e8790109bb4634eca8d8730e0c49bee3c977cdf` passed **403 IPC, 237 native UI,
  15 health, 28 P23 perception, 663 popup and 195 formatting checks**. E108 also
  records three successful additional P20 folder/undo runs, 26 checks each.
  The CI service was not queried again during this handoff task.
- `git diff --name-only 6e87901 60414fa` shows only completion records and
  verification compatibility changes: production Python and WinUI sources are
  unchanged from that accepted P23 source. E109 uses that explicit reuse basis.
- Counts overlap; never add them into a fictional number of unique tests.
- The old overwritten `output/p01-p13-audit/catalog-final.txt` is unavailable
  historical evidence. Do not reconstruct it or present its replacement as the
  original pass. Preserve retained XML/JSON with their actual identities.

## 2. Errors, risks and fixes still requiring work

No new application-runtime failure was reproduced during this documentation
inventory. The following are recorded failures, source-confirmed release gaps
or unexecuted gates, distinguished explicitly. They must be addressed by their
owning milestone, not silently relabeled complete.

| ID / priority | What is known | Required next action and evidence |
| --- | --- | --- |
| R1 / high validation priority, P25 | **Recorded physical failure:** C-02's E94 MME timing trials at gains 0.5 and 1 each passed 0/3, with only 0-5 speech frames; WASAPI refused 16 kHz. Owner explicitly deferred the fresh retest to P25. Earlier E78 success is historical. | Reproduce on the permitted physical microphone, diagnose capture/device/sample-rate/VAD behavior, fix only a demonstrated cause, and pass the existing timing/stream-closure criteria. Preserve the failed evidence and thresholds. See [E94](docs/completion/p19_overlay_acceptance.md) and C-02 in the matrix. |
| R2 / reliability concern, P24/P27 | **Historical intermittent failures:** P20 folder readback, P21 fixture startup, P22 recovery-dialog/shutdown timing. Latest normal gate and extra folder repetitions pass; E108 does not establish a root cause for every intermittent event. | Recheck through the full-flow harness under original budgets, retaining owned-worker/COM/startup/drain diagnostics if reproduced. Separate product hangs from fixture/readback races. Repair reproduced causes and rerun affected STOP/ownership/native checks; longer timeouts alone are not a fix. [E108](docs/completion/e108_p23_live_hosting.md) retains the failures. |
| R3 / release blocker, P28 | E116 prepares the Core + WinUI x64 candidate; E118 adds hash-validated Python wheelhouse inputs and locked local NuGet restore. **No build, offline rebuild or artifact inspection was run; code signatures and the authorized signing route remain absent.** | Build and inspect a fresh exact candidate, rebuild it offline from its retained inputs, prove source/build provenance, obtain the authorized signing path, verify signatures and launch/IPC under applicable Windows policy. The unsigned candidate is not a completed PLUMA release. |
| R4 / high installation risk, P29 | E116 prepares SHA-256 preflight, offline dependency installation, exact Core-version checks, installed UI readback, resident-only Startup and explicit UI Start Menu launch. E117 adds rollback/recovery source for marked Core/UI payloads and owned shortcuts. **No PowerShell or disposable-profile acceptance was run.** | On isolated profiles, verify clean install, missing/corrupt inputs, old/missing Python, failed install/import, exact paths, UI/Core handshake, hotkeys/microphone, data separation, upgrade migration and recovery at each interruption point. Keep models external. |
| R5 / high cleanup risk, P27/P29 | E116 adds identity-bound authenticated Core shutdown with bounded exit readback; E117 refuses uncommitted uninstall and validates committed backups. The installer never force-kills and recovery refuses processes still running under the selected install. **No shutdown race, PowerShell, upgrade/recovery or disposable-profile acceptance was run.** | Verify exact and same-name unrelated processes, Core drain/ack/exit, open UI refusal, STOP/worker cleanup, interrupted-upgrade recovery at each boundary, default/custom/purge behavior and cleanup interruption. Preserve user data. |
| R6 / build isolation risk, P28 | E116 isolates Python, NuGet and UI outputs, prevents output reuse, and limits MSBuild to one worker. E118 adds retained build constraints and offline package-source mode. **The builder has not been run; resource use, isolation, archive contents, hashes and offline repeatability remain unverified.** | Build once in a fresh output directory; inspect the candidate; extract and rebuild offline from its retained inputs; prove source/dependency/output identity and that existing bundles/reports/environments/unrelated changes remain untouched. |
| R7 / measurement evidence gap, P26 | E115 changes [benchmark/idle_baseline.py](benchmark/idle_baseline.py) to require an explicit target PID for target CPU/RAM, include the current descendant tree, guard PID reuse, and leave GPU attribution and remote module inspection unverified. **No measurement was run; the P26 gate remains open.** | Measure the installed resident and owned worker tree; add/obtain target-attributable GPU and loaded-runtime evidence; verify cold runtimes/capture absence and report missing telemetry as unverified. Measure ten minutes and 50 cycles on the target laptop. Do not infer a product pass from the script alone. |
| R8 / unexecuted release gates, P24-P31 | **Not established:** E110-E113 and E119 cover 25 of 140 unique corpus cases; 115 cases remain, as do physical display/accessibility/device behavior, target-laptop quality/performance/soak, adversarial installed recovery, signed reproducible release and clean install/upgrade/uninstall. | Continue sequentially through owned corpus and regression fixtures, triage E112's initial cold-run cleanup failure, then perform physical/device and release gates in their required order. Keep desktop/device/model work isolated; reuse unchanged-source evidence accurately. No claim of zero bugs, instant inference or lifetime compatibility is justified. |

For each new reproduced defect, append: severity, requirement ID, source and
line, source/build identity, exact safe reproduction, expected/actual result,
evidence path, recommended bounded fix, owning milestone and closure result.
Source concerns above must not be mislabeled as freshly reproduced product bugs.

### Already repaired: do not restart old work without a current reproduction

- The five old `Job.assign_process` rollback fixture failures and obsolete
  `_ALLOWED_APP_ALIASES`/missing declared test dependency problems were repaired
  in [E97](docs/completion/e97_test_environment_audit_repairs.md) and revalidated
  in [E98](docs/completion/e98_verified_integration.md).
- The P20 Shell automatic type-information RPC dependency was repaired in
  [E99](docs/completion/e99_p20_shell_main_integration.md) and integrated into
  `main`. R2 tracks later intermittent results; it does not erase that repair
  or make an old failing report the current whole-milestone verdict.
- P23 composed transparency/client bounds, pointer pass-through, successful
  metadata after sealed worker disposal and original-request terminal readback
  were repaired and accepted in E108.
- The stale P12 selector/87-versus-90 count, injected-OCR preparation and native
  target-DPI expectation were repaired in E109 at `88a17ac`. Preserve the stronger
  checks; do not edit the expected catalog to conceal a missing tool.

## 3. Ordered remaining roadmap

Use the detailed P24-P33 entries in [PLUMA_COMPLETION_PROMPTS.md](PLUMA_COMPLETION_PROMPTS.md)
with its shared execution contract. Do not repeat P00-P23 implementation merely
because an older historical paragraph still describes it as unfinished.

| Milestone | Remaining deliverable | Gate before advancing |
| --- | --- | --- |
| **P24** | Owned-target end-to-end harness and actual 140-case corpus; voice/text parity; FAST cold; UIA/OCR; native planning; confirmations; mutation/undo/conflict; STOP and factual saved/live outcomes; failure/reconnect cases | Required scenarios executed with expected route/tools/arguments/risk, independent postcondition/ledger/cleanup evidence. All failures accounted for and blocking fixes retested. Start with read-only cases; never run the entire action corpus blindly on personal apps/files. |
| **P25** | Physical Windows 11 review of all 26 surfaces, taskbar/monitor/DPI/accessibility/input/reduced motion; long transcript/copy layout; C-02 retest and deferred live focus/audio acceptance | Actual permitted device/physical evidence, distinct from hosted renders or injected geometry. Preserve dark styling and the owner's popup contract. Disruptive power effects remain untested unless explicitly permitted in a controlled environment. |
| **P26** | Target-laptop 10-minute idle, p50/p95 FAST/UIA/OCR/STOP, cold/warm STT/planner, quiet/noisy speech and candidate model quality; 50 active/idle cycles | Actual resident/worker/GPU attribution, no orphan/handle/memory leak, effective unload/grace. Use master section 23 budgets; a legacy test's arbitrary median threshold is not a new requirement. Select the smallest model that passes quality, without removing safety checks. |
| **P27** | Adversarial IPC/auth/ACL/message/concurrency checks, privacy, planner boundaries, model/worker/Core/storage failures, partial rollback, crash recovery/PID reuse | Reproduced blocking security/ownership/privacy defects repaired; exact residuals and verified owned-resource recovery. Preserve pre-existing resources. Include R2/R5 and honest unsupported boundaries. |
| **P28** | Unified reproducible signed backend + WinUI package, full manifests, dependencies, external model strategy and offline inputs | Actual packaged launch works under applicable Windows policy, integrity/signatures checked, lightweight startup preserved. Fix R3/R6; source tests or a gallery EXE alone do not pass. |
| **P29** | Controlled clean install, startup, model/config/data layout, hotkeys/microphone, upgrade/migration, crash/interrupted-update recovery and uninstall | Exact P28 artifact tested in disposable profiles; backup restoration exercised, unrelated data/processes preserved, installed capabilities read back. Fix R4/R5. |
| **P30** | Fresh independent full-spec review of the resulting candidate, including evidence quality and all open rows | Read-only review first; severity/file/reproduction/test evidence. Fix blocking findings in separate bounded packets, then obtain a review of the repairs. No assumed independent approval. |
| **P31** | Exact candidate/build final regression, native, physical, security, performance and installed-artifact acceptance | Every applicable A-H, I, J and master section 28 item reconciled. No known-defect xfail, stale report, silent exclusion or fixture-only physical pass. Owner-approved limitations remain explicit and cannot silently remove locked scope. |
| **P32** | Safe verified integration into current GitHub `main`, local branch reconciliation and release tag/artifact association | Only after P31/reviews; inspect remote heads/worktrees and recoverability, test the merged result, verify remote/local equality and artifact provenance. No shared-history rewrite or branch cleanup by deletion. |
| **P33** | Usable final artifact and user/developer instructions, supported commands, model/setup needs, backups/restore/crash/update recovery and maintenance | Owner can launch/use supported text/voice/STOP/history/settings flows; another developer can build/test/recover using retained versions/hashes/instructions without this chat. Final records match the real release. |

## 4. Execution rules and continuation cursor

Authority remains: `AGENTS.md`, immutable `PLUMA_MASTER_SPEC.md`, relevant
`PLUMA_BUILD_PLAN.md` phase, `PLUMA_ACCEPTANCE_TESTS.md`, current handoff/matrix,
technology contract and owner UI/placement decisions. Read the master completely
before code changes. This file routes work; it cannot relax requirements.

- Inspect current Git state, source and tests. Create a recovery branch before
  substantial implementation/integration; preserve dirty, untracked and unrelated
  work. No reset, clean, force-push or destructive workspace cleanup.
- State exact files and acceptance checks before each bounded change. Preserve
  completed implementation and the approved native dark UI. Notifications retain
  shared bottom-right placement, newest below, uniform class sizes, readable
  bounded text, aligned indicators, taskbar glide and smooth entry/reflow/exit.
  Display copy contains no underscores or em dashes; raw paths/data stay intact.
- Keep typed registered execution, exact policy/confirmation, verified
  postconditions, safe undo pre-state, one task owner/cancellation tree and
  priority STOP. No new admission/replan after the latch. Never kill pre-existing
  resources or bypass Application Control to get a pass.
- Use isolated data and owned fixtures. Verify prerequisites before launching a
  suite; do not change the global Python environment or personal Windows setup
  as an incidental test action. Check actual process exit and fresh report
  identity; old output or stale `$LASTEXITCODE` cannot establish success.
- Keep fresh logs under a unique ignored `output/<milestone>-<timestamp>-<id>/`.
  Preserve failed runs. Commit redacted durable evidence summaries, not models,
  raw audio/screenshots, secrets, caches, binaries or private ledger content.
- Run focused checks and relevant regressions after fixes. Reuse genuinely
  applicable unchanged-source evidence explicitly; do not rerun everything after
  a wording change or keep testing indefinitely once the required gate passes.
  Physical/corpus/release checks still require their missing actual execution.
- Commit each meaningful coherent change and push the authorized branch. Update
  this cursor, `PROJECT_HANDOFF.md`, the live matrix and the milestone evidence.
  The owner has now explicitly authorized continuing across all existing
  remaining milestones without stopping between packets and asked to defer
  tests/builds. Do not invent milestones or claim their acceptance gates passed.
  Finish independent source/documentation work first; keep physical, signing,
  installation, measurement and test gates visibly open until actually run.
  Explain only genuine owner-only blockers; otherwise finish routine authorized
  work without repeated questions.

**Current cursor:**

```text
Last completed milestone: P23; P00-P23 readiness record E109.
Current milestone: P24, IN PROGRESS, not complete. E113 GC-054/GC-055 and E119
GC-013/014/015 pass at production-source base
`f1f7c5d58ebc284a16a231d4044753b7223dc3af`; E119's test source SHA-256 is
`0C781AC71ECA1C2102862840FE84C87B1E82ECE2CE21D30D476DAB518BE74ABE`.
E119's focused acceptance passed 19/19 and selected audio/router regressions
passed 257 with 7 deselected. The accepted corpus count is 25/140. E112's
initial cold-run failure remains unexplained.
Current source-only packets: E117 adds interrupted-upgrade recovery and
transaction cleanup; E118 adds retained-input offline rebuild mode with exact
toolchain checks. Both are committed but untested at code commit `ac8a65d`.
The builder and installer/uninstaller were not invoked. Continue P24 acceptance
in bounded sequential packets; preserve physical, signing and installed gates.
Accepted packets: E110 at `530dfceaf39d33907f71f261e3f617ecfdab560b`, E111
source at `f30bb481c484f5b2dd7db5b66c400f38df69347e`, and E112 on production
source baseline `d3df79308aa806cc0494853e5e3ca9854b2cfc30`.
Accepted unique cases (25): GC-013, GC-014, GC-015, GC-046, GC-047, GC-048,
GC-054, GC-055, GC-056, GC-057, GC-058, GC-059, GC-076, GC-077, GC-078,
GC-079, GC-080, GC-081, GC-082, GC-083, GC-084, GC-085, GC-086, GC-087,
GC-090.
Remaining unique corpus IDs (115): GC-001–GC-012, GC-016–GC-045,
GC-049–GC-053,
GC-060–GC-075, GC-088–GC-089, GC-091–GC-125, and GC-N001–GC-N015.
Next safe step: continue a small FAST/READ corpus slice over owned fixture data.
Preserve E112's initial cold-run failure; its cause remains unknown. No owner's
confirmation UI, personal files, clipboard, windows,
device or power state; no model or resident process.
Development branch: p12-preparation; push packet commits normally after checks.
No branch switch, merge or main integration is part of P24.
Recovery: pushed `recovery/pre-remaining-work-20261110-c9f597f` preserves
`c9f597f0f8ee4e0e0531fb724fff5105a5a3cfec`; E110-E113 are accepted local
commits. E119 is an uncommitted test/documentation packet. Local source commit `ac8a65df7e9b7ca25d18e932cd8272830b63b494`
and documentation follow-ups `7119766`/`682a381` are unpushed and unverified.
Code-only checkpoint `4918bf5a70c987f72b9c2f562e58b1809015270f`
and its documentation commit `408ec8a` are pushed on `p12-preparation`; E113-E118
remain unverified. Root `uv.lock` remains untracked and untouched. E116-E118
source changes are local and unpushed; do not push them as acceptance-complete
work.
Do not start P25 until P24 passes or an applicable concrete owner-approved
limitation is recorded. Do not merge/tag until P32's prerequisites pass.
```

Every packet handoff must name: branch/HEAD, completed case or requirement IDs,
files/commits, exact commands and pass/fail/skip/error counts, evidence locations,
model/build hashes and environment where relevant, still failing/untested IDs,
limitations with their approvals, recovery ref, and the exact next safe packet.
Packet completion alone never means the milestone is complete.

## 5. Copy-and-paste prompts through completion

Use these **one milestone at a time**. Packet continuation can use the same chat;
use a fresh independent review for P30/final audit. Each prompt incorporates the
rules and roadmap above and the original detailed milestone contract.

### Continue: P24

```text
Read the current handoff/cursor, E110-E112, AGENTS.md, the master specification,
requirements matrix and the original P24 contract in PLUMA_COMPLETION_PROMPTS.md.
Verify the current branch/source, inspect E112's initial cold-run failure, and do
not restart E110-E112's 20 accepted cases unless triage requires it. Execute the
next bounded P24 packet only after the failure is accounted for; use owned
fixtures and do not read the owner's clipboard/files/windows or exercise
device/power state.
Run the focused gate and affected regressions, record exact IDs/counts/evidence,
commit and push normally, and update the cursor with the remaining IDs. Do not
start P25 before P24 passes or an applicable owner-approved limitation is
recorded.
```

### P25: physical Windows and device acceptance

```text
Read PLUMA_REMAINING_WORK.md and execute only the next unfinished P25 packet
under its rules and the original P25 contract. First verify P24's gate. Close
the permitted physical UI/taskbar/DPI/accessibility and deferred microphone,
focus/audio checks, including C-02. Preserve the approved dark style; distinguish
physical evidence from hosted/injected tests. Reproduce/fix actual failures,
verify cleanup, commit/push and update remaining IDs. Do not start P26 or assume
permission for disruptive power/session changes.
```

### P26: lightweight operation, speed and model quality

```text
Read PLUMA_REMAINING_WORK.md and execute only the next unfinished P26 packet
under its rules and the original P26 contract. Verify prior gates. Measure the
actual resident and owned workers, not the standalone sampler PID; missing GPU
telemetry is unverified. Close the ten-minute idle, cold/warm quality/latency,
scaling, STOP and fifty-cycle gates on the target hardware. Fix demonstrated
waste without sacrificing accuracy or safety. Record exact versions, hashes,
raw results and p50/p95; commit/push and update the cursor. Do not start P27.
```

### P27: security, privacy, crash and cleanup

```text
Read PLUMA_REMAINING_WORK.md and execute only the next unfinished P27 packet
under its rules and the original P27 contract. Verify prior gates. Test the
documented adversarial IPC/policy/privacy/ownership and crash/recovery cases in
isolated fixtures. Investigate retained reliability failures if reproduced;
preserve original budgets and independent readback. Repair one coherent cause
at a time and rerun affected regressions. Commit/push and record unresolved
threat/device boundaries and the next packet. Do not start P28.
```

### P28: complete reproducible signed package

```text
Read PLUMA_REMAINING_WORK.md and execute only the next unfinished P28 packet
under its rules and the original P28 contract. Verify prior gates. Fix the
recorded packaging/cleanup gaps using isolated build output. Produce the actual
core plus WinUI distribution, required native assets, full integrity/signature
manifest and offline reproducible inputs. Keep models external and startup
lightweight. Verify packaged launch/IPC/capabilities under the authorized Windows
policy. Record any unavailable signing prerequisite honestly. Commit/push source
and evidence summaries; keep bundles ignored. Do not start P29.
```

### P29: installation, updates and recovery

```text
Read PLUMA_REMAINING_WORK.md and execute only the next unfinished P29 packet
under its rules and the original P29 contract. Test the exact accepted P28
artifact in clean controlled profiles. Reproduce and repair installer false
success, runtime provisioning and uninstall ownership/path issues safely.
Verify install/startup, upgrade/migration, backup restoration, interrupted
update/crash recovery and uninstall/data preservation. Read back actual installed
state; do not modify the personal installation prematurely. Commit/push and
record exact artifact evidence and remaining cases. Do not start P30.
```

### P30: independent complete implementation review

```text
Read PLUMA_REMAINING_WORK.md and perform P30 as an independent read-only review
first, following the original P30 contract. Verify prior gates and audit current
implementation/evidence against the entire immutable spec, acceptance requirements
and matrix. Reproduce suspected defects safely. Report severity, requirement,
file/line, reproduction, test evidence, reviewed scope and recommended fixes.
Challenge stale/synthetic/skip-only passes and remaining fixtures. Record the
findings and next bounded repair; do not edit product code, merge or start P31.
```

### P31: exact-build final release acceptance

```text
Read PLUMA_REMAINING_WORK.md and execute P31 under its rules and the original
P31 contract only after P30's blocking findings are fixed and reviewed. Verify
all applicable full regression/native/integration, physical, security,
performance and installed-artifact gates against the exact candidate/build.
Reconcile every open matrix item, acceptance A-J and master section 28 with
valid evidence and explicit approved limits. No stale report, hidden failure,
xfail or fixture-only physical pass. Commit/push the factual readiness report
and remaining blockers. Do not merge or start P32 if the gate is incomplete.
```

### P32: verified main integration and release tag

```text
Read PLUMA_REMAINING_WORK.md and execute P32 only after the exact P31 gate and
required reviews pass. This prompt authorizes eligible reviewed main integration
and release tagging under the original P32 contract. Verify current GitHub heads,
worktrees, dirty/untracked work and dependencies; create recovery refs. Integrate
only accepted work using normal history-preserving Git operations, test the
merged result and verify artifact/source/signature provenance before publishing
main/tag. Verify remote and local main agree. Preserve other worktrees/branches;
no reset, clean, force-push or unrelated deletion. Record results and recovery.
```

### P33: working-product delivery and maintenance handoff

```text
Read PLUMA_REMAINING_WORK.md and execute P33 under its rules and the original
P33 contract after verified P32 integration. Deliver the real release artifact,
exact install/launch/model setup and text/voice/STOP instructions, supported
examples, history/undo/settings access, limitations and tested backup/restore,
update/crash recovery and offline rebuild steps. Reconcile README, handoff,
matrix and this file with actual main/tag/artifact hashes. Verify the documented
first-use path and maintenance commands. Commit/push the final handoff and state
any remaining requirement explicitly; do not invent features or promise no bugs.
```

### Reusable packet continuation

```text
Read PLUMA_REMAINING_WORK.md and PROJECT_HANDOFF.md. Verify actual Git state
and the active milestone's recorded evidence. Continue its next unfinished
packet under the shared rules; preserve accepted work and styling. Do not
repeat completed implementation or advance to another milestone. Fix/verify
the bounded work, commit/push and update exact remaining IDs, evidence and
the next continuation step. If blocked, record the concrete unmet prerequisite
and finish independent work within this milestone without claiming its gate.
```

### Fix findings from P30, P31 or a later audit

```text
Read PLUMA_REMAINING_WORK.md, current audit findings and the authoritative
contracts. Reproduce the highest-severity unresolved finding safely. State
exact files/checks, fix its root cause within one coherent packet and run the
focused failure regression plus affected suites. Preserve safety, requirements
and styling; do not hide failures with retries, extra timeouts or weaker tests.
Commit/push, attach exact-source evidence and update the finding/cursor. Obtain
independent review of the repair before treating the audit gate as passed.
```

### Final overall audit on released main

```text
Read PLUMA_REMAINING_WORK.md and independently audit the final main/release
against AGENTS.md, the complete master specification, acceptance A-J, build
gates, owner UI contracts and live requirements matrix. Start read-only: verify
GitHub/local main/tag, artifact hashes/signatures and installed-build identity.
Check all mandatory requirements have adequate current evidence; run missing or
invalidated regressions/native/full-flow/physical/performance/security/install
checks safely. Reproduce suspected bugs and report severity, file/line, exact
commands/results and fix recommendations. Distinguish prior reused evidence,
fresh passes, assumptions and owner-approved limits. Save a durable final audit
report with reviewed/unreviewed scope and a truthful readiness decision. Do not
edit product code during this review or assume full readiness from green CI.
```

## 6. Prerequisites the next agent must verify

- Use a working isolated Python 3.12+ environment with the repository-declared
  dependencies. The E109 environment was
  `output/p23-e108-20261104-230308-e366ce50/test-env/`. It is a historical path,
  not a permanent installation contract. In this task `python` was absent from
  the shell PATH and sandboxed launch could not access its base interpreter;
  the authorized read-only launch outside that sandbox succeeded. Do not infer
  a missing installation or product defect from that restricted launch error.
- Verify local llama.cpp, whisper.cpp and PaddleOCR/ONNX packages/models before
  required native scenarios. Prior tested assets include Qwen3-4B Q4_K_M and
  Whisper `ggml-base.en.bin`; recheck actual paths/hashes and quality. Do not add
  cloud keys/providers or a new model family to speed up completion.
- Native UI verification requires Windows 11, the declared .NET/Windows App SDK
  toolchain and PowerShell 7.2+ for `PLUMA.UI/verify-ui.ps1`. Set the validated
  `PLUMA_TEST_PYTHON` for Python-backed IPC/native fixtures as documented in the
  evidence. Do not confuse a compile or gallery render with physical acceptance.
- Physical microphone/speech, monitor/taskbar/DPI/accessibility and owner
  appearance feedback need the real permitted environment. Signing requires
  actual authorized signing inputs/policy. Do not fabricate unavailable results
  or silently approve previous deferrals on the owner's behalf.

Useful existing entry points (inspect prerequisites and current selectors first):

```text
python docs/completion/verify_requirements_matrix.py
python docs/completion/run_p01_p13_checks.py <declared-mode> --output-dir <fresh-output-path>
dotnet run --project PLUMA.UI/CoreIpc.Tests/CoreIpc.Tests.csproj -c Release --verbosity quiet -p:UseSharedCompilation=false
pwsh -NoProfile -File PLUMA.UI/verify-ui.ps1
git diff --check
```

These are not the whole release gate. Use the actual per-milestone/native
commands and exact arguments from their current contracts/evidence. The
P01-P13 runner supports only its declared modes. Old benchmark tests may change
audio/clipboard or test uninstalled/injected paths; inspect isolation before use.

## 7. All currently UNVERIFIED rows: snapshot, not a substitute for the matrix

The live matrix owns full requirement text, evidence, limits and next owners.
Refresh this snapshot when closing rows; never close a range from one example.

| Group | Open IDs at 60414fa |
| --- | --- |
| Acceptance B-H | B-01, B-05, C-02, D-02, D-03, G-01, G-02, G-04, G-08, G-09, G-10, H-08 |
| Performance I | I-01, I-02, I-03, I-04, I-05, I-06, I-07 |
| Final acceptance J | J-01, J-02, J-07, J-08, J-09, J-14, J-15, J-16, J-17 |
| Master definition of done | S28-01, S28-02, S28-03, S28-04, S28-08, S28-09, S28-10, S28-15, S28-16, S28-17, S28-18 |
| Catalog physical checks | CAT-focus_app, CAT-focus_window, CAT-set_volume, CAT-mute, CAT-unmute, CAT-set_default_audio_device |
| Capabilities | CAP-01, CAP-03, CAP-04, CAP-05, CAP-07 |
| Engineering laws | LAW-01, LAW-03, LAW-07, LAW-08, LAW-09, LAW-10, LAW-11, LAW-13, LAW-14 |
| Build-plan gates | BP-00-01, BP-00-02, BP-00-03, BP-00-04, BP-01-01, BP-01-02, BP-01-03, BP-01-04, BP-03-01, BP-03-02, BP-10-01, BP-10-02, BP-12-01, BP-12-02 |
| Physical placement | PLACE-01, PLACE-02, PLACE-03, PLACE-04, PLACE-05, PLACE-06, PLACE-07, PLACE-08, PLACE-09, PLACE-10, PLACE-11, PLACE-12, PLACE-13, PLACE-14, PLACE-15 |
| Aggregate contracts | CORE-NAME, CORE-STATES, CORE-BOUNDARIES, CORE-LIFECYCLE, CORE-SNAPSHOT, CORE-PROCESS, CORE-PRIVACY, CORE-UI, CORE-CONFIG, CORE-PERF, CORE-FAILURE, CORE-PACKAGE, CORE-TRACES, CORE-LIMITS |

## 8. Scope and checks of this handoff task

Fresh work on 2026-11-10: read the specification/contracts and current completion
records; inspect Git source differences, selected release/benchmark scripts and
retained XML/logs; verify remote heads; validate the matrix and parse the corpus.
The matrix validator passes **298 source items / 336 traceable rows**. The YAML
contains **140 unique IDs** and the route counts above. This validates inventory
and documentation structure, not behavior of all 140 cases.

Only this file, the current `PROJECT_HANDOFF.md` entry and the prompt guide's
entry instructions are changed. No milestone implementation, product styling,
master requirement, merge, release, install/uninstall or physical desktop action
is performed. Full application regression/native/device/performance suites were
not rerun for this documentation-only change. Use E109/E108's scoped results
with the stated source identities, and perform the remaining gates above.
