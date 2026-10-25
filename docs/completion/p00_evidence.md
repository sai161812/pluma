# P00 evidence and next gate

Checkpoint: 2026-10-19, Asia/Calcutta. Scope: establish current truth only.
Read the [live matrix](requirements_matrix.md) and the
[shared contract / P00 prompt](../../PLUMA_COMPLETION_PROMPTS.md).
No product feature, execution fix, UI redesign, action enablement or merge is
part of this change. No acceptance limitation has been assumed or approved.

## Source and GitHub checkpoint

Inspection and Python evidence use source
`88078bb3c625f0a741b329144f747bbb3fa1dd69` in
`D:\Workspace\DEVEL\PLUMA`, branch `ui-wiring`. The worktree was clean before
P00. The P00 documentation commit is identified by the Git commit containing
this file; its parent is the inspected source above. Fresh backend tests remain
applicable because P00 changes only this documentation, its coverage checker
and the current handoff. No production source or existing test is edited.

Observed with `git status --short`, `git branch -vv`, `git remote -v`,
`git worktree list`, `git ls-remote origin` for named branches/tags, and bounded
read-only GitHub REST queries on 2026-10-19:

| Item | Verified state before the P00 documentation push |
|---|---|
| origin | `https://github.com/sai161812/pluma.git` |
| local / remote ui-wiring | `88078bb3c625f0a741b329144f747bbb3fa1dd69` |
| local / remote main | `6dbf58925352d41a0196dda33044b18282cc6ddf` |
| local / remote ui-polish-integration | `9544752d1af4d675b50ff7aa8e99fb27da9c722f` |
| [PR 1](https://github.com/sai161812/pluma/pull/1) | OPEN, draft, `ui-polish-integration` into `main`, unmerged |
| [PR 2](https://github.com/sai161812/pluma/pull/2) | OPEN, draft, `ui-wiring` into `ui-polish-integration`, unmerged |
| backend source tree | `b3ae9d24471ee38ebc5e08965d4e128c9ac3a5f0`, identical to main |
| tests tree | `aacf95e4b6e5b1ef9383de9c5eb1ee526055ed57` |
| PLUMA.UI tree (including docs) | `85501556f8f92a854558387fdccf3c2a982d3c28` |

`gh` is unavailable locally; no installation was needed. Read-only PR metadata
came from `GET https://api.github.com/repos/sai161812/pluma/pulls?state=all`
using `Invoke-RestMethod -TimeoutSec 20`. The native run below was checked with
`GET /repos/sai161812/pluma/actions/runs/39243181549`, also bounded to 20 seconds.
No issue/comment/message/review was sent. The existing stacked draft PRs stay
draft; updating `ui-wiring` does not authorize merging or retargeting them.

Retained worktrees:

- `D:\Workspace\DEVEL\PLUMA-backend-audit`: `main`, `6dbf589`.
- `D:\Workspace\DEVEL\PLUMA-ui-integration`: `ui-polish-integration`, `9544752`.
- `D:\Workspace\DEVEL\PLUMA-ui-wiring`: detached `55b625c`, original audit evidence.

Other branch histories, including `ui-polish`, `sai` and local
`archive/main-before-ui-sync-20261019-90aa05e`, are preserved. No worktree was
switched, cleaned or reset.

## Evidence identifiers

| ID | Kind | Meaning and limits |
|---|---|---|
| E01 | Fresh bounded regressions | Selected schema/router/policy/redaction/ledger/rollback/freshness/IPC/control checks below. Does not certify all tools or the backend. |
| E02 | Fresh reproduced defects | Actual required assertions run with `--runxfail`: 11 failures across nine BA findings. Fixture seams are distinguished below. |
| E03 | Fresh registry inspection | Enumerated 33 actual default ToolSpecs and executor modules/risk/verifier/undo metadata, without executing a tool. |
| E04 | Source inspection / test inventory | Implementation and test files were read; these references do not claim that every named test was run or is sufficient. |
| E05 | Retained hosted native UI evidence | Source-specific native fixtures and exported renders from run 39243181549; verified completed/success through GitHub. No new physical Windows/UI run in P00. |

## Fresh Python evidence

Environment: Windows 11 build 26200, Python 3.12.10, pytest 8.3.3, x64.
Hardware-specific performance was not measured. These are audit fixture runs,
not target-device acceptance. `output/p00/metadata.json` records exact command
vectors, source hash, OS/Python, child environment root and wall durations;
`audit.txt`, `audit-raw.txt`, `regression.txt` and matching JUnit XML are ignored
local artifacts under `output/p00/`.

The ignored `output/p00/run_evidence.py` ran three sequential bounded child
processes. Each used isolated LOCALAPPDATA, APPDATA, TEMP and TMP directories
under a new user-local Temp root, with inherited `PLUMA_*` overrides removed.
Each child had a 120-second outer bound; each test had a 15-second thread-method
timeout. `tests/conftest.py` explicitly enables audio emulation and test mode.
Test mode also makes an elevation-broker return a mock result, so it cannot
establish actual UAC execution. The elevation-operation test was excluded from
this bounded suite and is recorded as unexecuted, not passing or waived.

No production resident, hotkeys, microphone, user application, model, production
credential, real power/system-changing operation or Windows security-policy
change was activated by these selected tests. IPC uses owned fixture pipes.
BA-09 uses an intentionally permissive newly created fixture directory, never
the user's credential or its ACL. Fixture secret files were removed after the
runs; remaining fixture `ipc_secret.key` count was **zero**. Other harmless
isolated fixture files remain for inspection outside Git.

Commands below ran inside that child environment. Common options:

```text
-q -o addopts= --timeout=15 --timeout-method=thread --tb=short -ra -p no:cacheprovider
```

Each also received `--junitxml=<output/p00/run-name.xml>`.

```powershell
python -m pytest tests/unit/test_backend_wiring_audit.py <common options>
# 4 passed, 11 xfailed in 1.03s; exit 0; outer wall 1.541s.

python -m pytest tests/unit/test_backend_wiring_audit.py --runxfail <common options>
# 11 failed, 4 passed in 0.90s; exit 1; outer wall 1.330s.
```

The raw failure names are:

```text
test_global_stop_latches_every_task_before_first_grace                 BA-01
test_worker_stop_interrupts_outstanding_response_wait                 BA-02
test_stop_during_prestate_prevents_executor_start                     BA-03
test_failed_worker_cleanup_requires_residual_state                   BA-04
test_fast_stop_preserves_supervisor_residual_outcome                  BA-05
test_runtime_close_drains_active_task_and_registry                   BA-06
test_voice_stop_closes_capture_without_key_release                   BA-07
test_empty_voice_capture_finalizes_its_capsule                        BA-07
test_ipc_stop_reply_distinguishes_residual_cleanup                    BA-08
test_ipc_stop_reply_does_not_claim_nonterminal_task_stopped            BA-08
test_first_windows_credential_is_verified_before_return              BA-09
```

BA-05 reads real in-memory SQLite final state; BA-09 reads actual Windows ACL
inheritance. The remaining defect tests use actual control flow with inert
controllers/connections/capture, fake jobs and owned joined threads. They do
not establish OS worker survival/exit, microphone behavior, physical hotkey
latency or real model cancellation. The four passing controls cover unknown
tool rejection before policy, invalid-argument rejection before policy, failed
verification not becoming success, and already-cancelled admission rejection.
An early cancellation check is therefore tested; the later BA-03 gap still
fails. `xfail(strict=True, raises=AssertionError)` makes unexpected exceptions
fail; an expected failure is still an unmet requirement.

Subsequent selected regression:

```powershell
python -m pytest tests/unit/test_backend_wiring_audit.py tests/unit/test_schemas.py tests/unit/test_router.py tests/unit/test_brain_validator.py tests/unit/test_policy_engine.py tests/unit/test_redaction.py tests/unit/test_activity_ledger_lifecycle.py tests/unit/test_rollback_engine.py tests/unit/test_rollback_recipes.py tests/unit/test_tool_runner_ledger.py tests/unit/test_perception_freshness.py tests/unit/test_phase13_7_ui_verification.py tests/unit/test_phase13_7_created_stop.py tests/unit/test_ipc.py -k "not test_elevation_broker_execution" <common options>
# 277 passed, 1 deselected, 11 xfailed in 9.06s; exit 0; outer wall 9.651s.
```

This is 273 pre-existing passes plus four audit controls. It is the relevant
bounded regression set used by the backend audit, freshly repeated against the
inspected source. No full unit suite, acceptance runner, benchmark suite,
physical UI or installed release suite was run for this documentation task.
The full-suite instruction for completion of a product phase is not fulfilled
by these checks; P00 does not claim completion of a product phase.

## Registry, implementation and test-validity reconciliation

E03 used `ToolRegistry()`, `register_default_tools(registry)`, `list_specs()` and
`registry.close()` in a short Python command. It enumerated executor module,
name, risk, verifier name and presence of an undo builder. No executor was
invoked. The default registry has **33 names**, including aliases and names
that differ from the master catalog. A count of 33 is not catalog coverage.
Every catalog name and related internal implementation is mapped separately.

Source findings for later bounded reproduction and repair:

- `processes.py`, `terminal.py` and `browser.py` raise `NotImplementedError`.
  Catalog process, browser and terminal operations remain required. File
  open/copy/info/delete, window move/resize, audio-device management, power
  operations and registered preference/routine tools also have missing entries.
- `PlanValidator` defaults to hard cap 20; the current app/orchestrator path
  does not propagate configured `agent.max_plan_steps` (default 8). The schema
  tests check hard cap 20; their configured-limit heading overstates coverage.
  Snapshot tests invoke freshness helpers directly; they do not prove rejection
  of every arbitrary `ToolCall.target_ref` at executor admission.
- Registry Pydantic validation precedes policy. Dict-schema validation degrades
  to required-key checking without jsonschema; planner dict-schema validation
  also only checks required keys. Invalid Pydantic fixtures do not certify
  arbitrary JSON Schema argument validation.
- All locked risk enum values now exist. `PolicyEngine` nonetheless auto-allows
  MEDIUM without an explicit-intent signal; HIGH uses a generic approval prompt;
  REQUIRE_ELEVATION is not dispatched by registry to the typed broker. Existing
  callback/mock tests are not native material approval/UAC acceptance.
- Clipboard setters/clearers report verified from Win32 call return, without
  independent postcondition readback or safe private pre-state. Window state
  mutators do perform Windows state reads but lack undo builders. A no-op
  registry verifier alone does not prove failure where the executor has a real
  readback; inspect both layers, as these distinctions demonstrate.
- Undo-builder exceptions are logged and execution continues. `undo_last` pops
  in-memory evidence before inverse success; its DB consumption is separate
  from inverse execution. Failure retention and concurrent consumption need
  tests. `show_activity` fallback reads `activity.db`, unlike runtime's
  `data/pluma.db`, and swallows query errors into empty results.
- Planner inference runs through a global thread pool. A future timeout does
  not stop native generation; the native backend only prechecks cancellation
  and broadly retries after schema-generation exceptions. STT/OCR also make
  blocking native calls with token checks around them. Mock cancellation is
  not proof of interruptible owned inference or orphan-free finalization.
- Audio capture is ended on release; VAD trims buffered audio afterwards. The
  byte cap does not close the microphone stream at an utterance boundary.
  `app.py`'s `base.en.pt` default is not evidence of a valid whisper.cpp model;
  effective voice/model grace keys differ from `runtime.*` baseline keys.
- OCR constructs PaddleOCR without explicit ONNX Runtime or tiny/small model
  configuration. Lazy import and a fixture recognizer do not satisfy the
  locked PaddleOCR/ONNX technology path or prove DPI/accuracy.
- `SettingsPage` and `HistoryPage` have constructor-only code-behind;
  `SettingsContract` is abstract. SetupChecklist starts Pending and consumes
  host results but has no connected capability checker. The dashboard has
  authenticated read-only status and disabled command entry. Other native
  controls and popup host tests do not establish backend event subscriptions.
- `ResidentCore` handles execute/request/submit, stop/stop_all/STOP, stop_task,
  status and recent_tasks/get_recent_tasks. Windows IPC uses per-user native
  message framing and HMAC authentication, one response per connection. No
  live event subscription, JSON-RPC 2.0, partial STT stream or heartbeat is
  established. Surface-reference `Wire` examples are future intentions.
- The 140-entry golden corpus exists. `benchmark/idle_baseline.py` samples its
  own process and system GPU; it is not ten-minute installed-resident ML/GPU
  attribution. Fast synthetic loops and mock audio are not fifty real model
  cycles, quality certification or physical endpoint acceptance.

Historical handoff totals of 377, 393, 414 and 430, and historical reports claiming
completed/certified phases, predate the current audit. They are not current
release evidence. The older reports remain archived with their disclaimers.
`run_acceptance_verification.py` conditionally asserts app ownership only when
`open_res.ok`; that path can avoid proving an actual successful launch. Its
33-tool-count assertion and successful function return do not establish all
catalog contracts. Do not weaken tests or publish these totals as full product
completion. No old helper was executed as acceptance in P00.

## Retained hosted native UI evidence

GitHub confirms [run 39243181549](https://github.com/sai161812/pluma/actions/runs/39243181549)
completed successfully for head `64559bd256b18bc33a04b47076bbc3f89fa4f2eb`.
The retained `verification-summary.json` identifies tested PR merge
`b333e746914fcd03a8b52258c3792a3432f3c250`, Windows build 26100, interactive
session, unsigned executable SHA-256:

```text
C22C92BFB761FE4FC6E51F6949B137F2031A97ECAFF048E8618DD024500595E7
```

It reports 37 IPC, 663 native popup, 195 formatting and 42 UI control checks
passed, with 58 retained PNG exports. The retained artifact is under ignored
`output/ci-artifacts/run-39243181549/20261019-111539-fdf3c2db/`; the
[status wiring contract](../../PLUMA.UI/PLUMA.UI/docs/wiring_status_connection.md)
and [integration review](../../PLUMA.UI/PLUMA.UI/docs/ui_integration_review.md)
describe scope and earlier failures/corrections. Head and tested merge differ
because this is PR CI, not a locally tested P00 executable. Current production
C#/XAML remains unchanged; P00 does not rerun or replace native acceptance.

Hosted geometry/motion fixtures establish their measured native paths only.
Real Windows 11 auto-hide reveal/hide, monitor/DPI, reading/accessibility and
owner appearance/motion review remain open. Local unsigned WinUI execution was
blocked by Application Control in the recorded integration review; P00 does
not retry through another host, change policy or assume an approved exception.
Preserve [the placement contract](../../PLUMA.UI/PLUMA.UI/docs/popup_placement_contract.md),
including all P-01..P-15 cases, fixed classes, reading holds and replacement
readiness. Those cases are a separate physical UI gate, not a passing backend
integration inferred from gallery images.

## P00 coverage verification

Run `python docs/completion/verify_requirements_matrix.py`. It independently
extracts numbered A-H items, every I metric and J bullet, every section-28
checkbox, every section-21 name, all 26 surface headings, section-1.1 locked
capabilities, all section-3 engineering laws, BA findings and explicit build-plan
gate bullets and all 15 owner placement cases. It checks exact normalized source wording, unique IDs, nonempty
implementation/evidence/status/gap cells, next-prompt ownership and local links.
It imports no product runtime. Cross-cutting architecture/privacy/configuration
and optional items add traceability beyond the extracted source items.

The checker demonstrates coverage, not acceptance truth. Source-inspection
findings remain open until reproduced and fixed in their named packets. Product
requirements, acceptance files, technology/build contracts and surface reference
are preserved rather than rewritten to match missing implementation.

Actual output:

```text
PASS: 298 source items, 324 traceable rows; unique IDs, full requirement text, statuses, next prompts and local links.
A=7, B=7, BA=9, BP=39, C=10, CAP=8, CAT=73, D=10, E=10, F=10, G=10, H=8, I=7, J=17, LAW=14, PLACE=15, S28=18, UI=26
```

The ignored `python output/p00/check_matrix.py` also passed seven inert negative
probes: omitted catalog capability, altered locked wording, invalid status,
missing next prompt, missing evidence, duplicate ID and malformed table row.
The checker loaded no PLUMA runtime modules. Fixed extraction counts make source
parser omissions fail visibly instead of silently reducing coverage.

Final review is a separate read-through of the matrix, evidence and full staged
diff. It checks that only the four announced files change, production/locked
sources remain byte-identical, all claims distinguish fixture/source/physical
evidence, and no logs, keys, generated build data or raw captures enter Git.
`git diff --check` passes. The P00 documentation gate is satisfied; product
gates and all nine BA findings remain open.

The ignored `python output/p00/review_scope.py` passed the final scope/evidence
review: exactly four announced staged files, unchanged runtime/tests/locked
sources, JUnit counts matching the reported results, all BA rows defective,
only source-optional items marked optional, no credential patterns in the
changed files, and exactly 58 retained native fixture PNGs.

## Recovery

Pre-P00 source recovery point is `88078bb3c625f0a741b329144f747bbb3fa1dd69`.
To inspect it without overwriting current work, choose a new unused directory:

```powershell
git -C D:\Workspace\DEVEL\PLUMA worktree add --detach D:\Workspace\DEVEL\PLUMA-before-p00 88078bb3c625f0a741b329144f747bbb3fa1dd69
git -C D:\Workspace\DEVEL\PLUMA-before-p00 status --short
```

Existing remote annotated tags peel to:

- `pre-project-cleanup-2026-10-19`: `55b625c74d769de1219378a16d4621f4f49b3d10`.
- `pre-ui-wiring-2026-10-19`: `04bc1fb7d1efa1744b1027a51ce10e3b3ef7eccc`.

[Workspace cleanup/recovery](../workspace_cleanup.md) preserves local archive
`D:\Workspace\DEVEL\PLUMA-local-archive\20261019-pre-completion-cleanup`, its
manifests and original generated-state stash
`4c72146410a14352d0b33165e8910b6ae1a53b28`. These were not deleted, applied or
popped. Inspect archives in separate locations; do not apply old patch scripts
or generated binaries over current source. Use reviewed revert commits for
shared changes, never reset/clean/force-push. Source recovery cannot undo runtime
external effects.

## Prioritized bounded P01 work packet

**Next eligible task: P01 only, BA-03 executor admission after STOP.**
P00 does not implement or authorize automatic progression into it. Keep command
entry disabled and retain current UI styling/read-only status.

1. Re-read the current handoff, matrix, master sections 3/6/11-13/15, Build Plan
   Phase 1/2/10 gates, acceptance F-08/G-02 and P01 prompt. Check branch/remotes,
   worktree changes and the audited source hashes before editing.
2. Reproduce
   `test_stop_during_prestate_prevents_executor_start` with `--runxfail`; the
   audit executor currently records entry with its actual token already latched.
   Inspect queued thread dispatch, `TaskWorkerController.execute_call`, process
   worker entry and any policy/pre-state waits before choosing the synchronization
   boundary. Define exactly when executor admission occurs relative to latch.
3. Planned production touch points: `pluma/tools/registry.py` and, only if the
   proven admission/latch protocol needs it, `pluma/core/cancellation.py`.
   Planned evidence: convert the BA-03 reproduction in
   `tests/unit/test_backend_wiring_audit.py` to an ordinary passing regression;
   add controlled ordering/queued thread/process-entry tests in a focused
   `tests/unit/test_executor_admission.py`. Update this matrix, this evidence
   record and `PROJECT_HANDOFF.md`. State the final exact files before edits.
   No BA-01/02 cleanup redesign, feature, catalog expansion or UI wiring belongs
   in P01.
4. Prove STOP during pre-state capture, STOP while queued, cancellation before
   actual thread/process execution and policy/undo wait races; no executor may
   enter after latch. Preserve minimum pre-state, verification, ownership,
   timeouts and ledger facts. An early extra check or successful return alone
   is insufficient. Never hold a cancellation-blocking lock through the whole
   tool execution. Verify safe failure/cleanup for rejected admission.
5. Run focused admission/cancellation/registry tests, then relevant regressions
   in isolated storage. Remaining BA expected failures stay visible; do not
   claim all of `--runxfail` green while P02-P09 remain open. Record the separate
   real owned Windows worker/Job Object checks required at P10.
6. Review diff for scope, fake success and escaped queued work; update evidence,
   commit a coherent fix, push `ui-wiring`, report exact outputs and stop.
   P02 becomes eligible only after P01's bounded gate passes.

P01 gate: admission ordering is precise and exercised for both entry paths;
the BA-03 regression passes without an expected-failure marker and no covered
post-latch executor starts. P10 remains the real-worker acceptance gate.
