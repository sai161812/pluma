# P11 policy boundary checkpoint (E18)

2026-10-20. The owner has authorized finishing remaining P11 work, expressly
excluding P12. **P11 is still in progress.** This is one coherent safety block;
it does not certify missing catalog entries or physical confirmation/UI behavior.

Started clean on local/remote ui-wiring at
`87634db93efe5e01c4c64e16dcf50cc7d404b372`; main/integration/four worktrees and
draft/open/unmerged PRs 1/2 checked. Shared P11/handoff/AGENTS, master policy/
verification/ownership, build phases and A/D/H contracts reread before edits.

Prerequisite first run: 367 passed / 1 failed in 47.91s. The one-second blocked
metadata fixture timed out during cold worker import before reaching its marker;
actual result FAILED/TOOL_TIMEOUT and native cleanup were verified. The fixture
now warms the same capsule/controller/Job with a bounded inert read and asserts
identity reuse, retaining the one-second blocked response deadline. Fault-injected
ToolSpecs are restored after each case. SMART timeout copy no longer says user
request. Corrected file-info checks: 50 passed in 13.51s; fresh complete
prerequisites: **368 passed in 51.99s**, before policy feature edits.

## Implemented boundary

- MEDIUM no longer auto-allows absent explicit intent. This pipeline has no
  trusted request-to-exact-call intent attestation, so MEDIUM and HIGH require
  a trusted host approval callback for the exact owned task/tool/arguments.
  No planner flag or natural-language claim grants approval. READ/LOW behavior
  remains; ADMIN still requires its single-operation elevation boundary.
- Each approval receives a deep copy. Changed scope, malformed/truthy approval,
  callback exceptions and missing task identity fail closed. A real bool True
  from ConfirmationResponse is required. Each call asks independently; no
  remember-for-session blanket grant is implemented. Denial copy is fixed and
  does not echo callback reasons/secrets. Risk configuration can tighten, not
  lower, the registered intent/confirmation/elevation/deny floor.
- Policy callbacks run through the same capsule WorkGate/Future ownership,
  admission and cancellation tree. Caller budget is min(ToolSpec timeout, 30s).
  STOP/deadline discards late approval; running callbacks remain owned and
  prevent storage close until they actually exit. No forced Python thread kill
  or fake clean shutdown. POLICY_TIMEOUT is projected through existing failure
  ownership alongside TOOL_TIMEOUT. This is a backend functional contract;
  cancellable native approval surfaces and P15/P16 wire decisions remain later.
- Denied/failed pre-execution calls record sanitized actions with executed=false,
  actual policy decision/risk and verified=false; no executor/undo success is
  invented. Allowed actions carry the actual effective risk/approval state.
  Failed/missing reversible pre-state refuses mutation instead of continuing.
  Protected-path/command policy logs omit raw argument values.
- Native owned-file move after exact approval produces a verified action/undo;
  STOP restores the original path/content and consumes undo, verified again in
  reopened SQLite. STOP during pending approval retains owners/storage and no
  late approval can execute. Read-only file_info denial now asserts a factual
  denied action instead of the previous absence of one.

## Results and scope

| Check | Actual pytest result |
|---|---|
| Policy + admission + file_info + existing policy | 101 passed, 1 deselected in 21.86s |
| Focused | 503 passed, 1 deselected in 65.24s |
| Isolated regression | 821 passed, 3 skipped, 1 deselected in 73.63s |
| Raw audit --runxfail | 15 passed in 0.64s |
| Native containment | 3 passed in 3.56s |
| Startup/recovery | 5 passed in 0.70s |

Windows 11 build 26200 / Python 3.12.10. Unique isolated user-local storage,
PLUMA_* inheritance removed, owned files/processes/Jobs/SQLite/pipes, inert host
approval/model/device seams. Final actual exits 0, key files remaining 0 and
source hashes match. All 115 FAST cases retain desktop_isolation properties.
Skips and excluded system-changing elevation are not acceptance. No UI design,
physical approval/device, real browser or clipboard operation is certified here.

The first policy suite had 100 passed / 1 failed / 1 excluded in 24.28s: a new
fixture mutated a shared default ToolSpec without restoring it. Fault injection
now uses scoped monkeypatch, including the inherited file_info injected worker.
No executor failure assertion was removed. All intermediate reports are retained.

Commands: python output/p11_remaining/run_checks.py prerequisite-repaired,
policy-boundary-corrected, focused-policy, regression-isolated, raw-policy,
containment, recovery. Exact commands/options, source parent/hash, real exits,
environment/roots and logs/JUnit remain under ignored output/p11_remaining.
Final expanded focus/regression commands:

```text
C:\Users\saipr\AppData\Local\Programs\Python\Python312\python.exe -m pytest tests/unit/test_policy_boundary.py tests/unit/test_brain_tool_subset.py tests/unit/test_file_info.py tests/unit/test_tools_files.py tests/unit/test_tool_runner_ledger.py tests/unit/test_policy_engine.py tests/unit/test_backend_safety_integration.py tests/unit/test_ipc_credentials.py tests/unit/test_backend_wiring_audit.py::test_first_windows_credential_is_verified_before_return tests/unit/test_backend_wiring_audit.py::test_ipc_stop_reply_distinguishes_residual_cleanup tests/unit/test_backend_wiring_audit.py::test_ipc_stop_reply_does_not_claim_nonterminal_task_stopped tests/unit/test_stop_protocol.py tests/unit/test_ipc.py tests/unit/test_voice_session.py tests/unit/test_voice_pipeline.py tests/unit/test_voice_activation.py tests/unit/test_voice_vad.py tests/unit/test_brain_lifecycle.py tests/unit/test_voice_lifecycle.py tests/unit/test_voice_capture.py tests/unit/test_runtime_shutdown.py tests/unit/test_terminal_outcome.py tests/unit/test_db.py tests/unit/test_cleanup_evidence.py tests/unit/test_rollback_engine.py tests/unit/test_rollback_recipes.py tests/unit/test_worker_cancellation.py tests/unit/test_global_stop_ordering.py tests/unit/test_executor_admission.py tests/unit/test_task_supervisor.py tests/unit/test_schemas.py tests/unit/test_ownership.py tests/unit/test_job_object.py -q -o addopts= -o junit_family=xunit1 --timeout=20 --timeout-method=thread --tb=short -ra -W error::pytest.PytestUnhandledThreadExceptionWarning -p no:cacheprovider --junitxml=D:\Workspace\DEVEL\PLUMA\output\p11_remaining\focused-policy.xml -k "not test_elevation_broker_execution"

C:\Users\saipr\AppData\Local\Programs\Python\Python312\python.exe -m pytest tests/unit/test_backend_wiring_audit.py tests/unit/test_schemas.py tests/unit/test_router.py tests/unit/test_brain_validator.py tests/unit/test_policy_engine.py tests/unit/test_redaction.py tests/unit/test_activity_ledger_lifecycle.py tests/unit/test_rollback_engine.py tests/unit/test_rollback_recipes.py tests/unit/test_tool_runner_ledger.py tests/unit/test_perception_freshness.py tests/unit/test_phase13_7_ui_verification.py tests/unit/test_phase13_7_created_stop.py tests/unit/test_ipc.py tests/unit/test_policy_boundary.py tests/unit/test_brain_tool_subset.py tests/unit/test_file_info.py tests/unit/test_tools_files.py tests/unit/test_backend_safety_integration.py tests/unit/test_ipc_credentials.py tests/unit/test_stop_protocol.py tests/unit/test_voice_session.py tests/unit/test_voice_pipeline.py tests/unit/test_voice_activation.py tests/unit/test_voice_vad.py tests/unit/test_brain_lifecycle.py tests/unit/test_voice_lifecycle.py tests/unit/test_voice_capture.py tests/unit/test_runtime_shutdown.py tests/unit/test_terminal_outcome.py tests/unit/test_cleanup_evidence.py tests/unit/test_worker_cancellation.py tests/unit/test_global_stop_ordering.py tests/unit/test_executor_admission.py tests/unit/test_fast_orchestrator.py tests/unit/test_multi_step_orchestrator.py -q -o addopts= -o junit_family=xunit1 --timeout=20 --timeout-method=thread --tb=short -ra -W error::pytest.PytestUnhandledThreadExceptionWarning -p no:cacheprovider --junitxml=D:\Workspace\DEVEL\PLUMA\output\p11_remaining\regression-isolated.xml -k "not test_elevation_broker_execution" -p tests.fixtures.desktop_isolation

```

Tested source is the commit containing this record, parent 87634db:

| File | Git blob |
|---|---|
| `pluma/policy/engine.py` | `416a3fe2124913e667ca323a929879a5cd96feb5` |
| `pluma/policy/rules.py` | `7fb8c5a6745d82b7ca0fa072eb31b68307a7236a` |
| `pluma/tools/registry.py` | `5ff434edb5c7345080d2a7737d883f91320f24e1` |
| `pluma/core/orchestrator.py` | `b38707f6e1bf7f31acca8cc997c8d1f6fccd8a45` |
| `pluma/core/multi_step.py` | `6ea8cba9d4bc57549e4feeaaf36a4e9a86139451` |
| `tests/unit/test_policy_boundary.py` | `f05cd098a1c1cbd49b7597e7d2f91589efdafa5f` |
| `tests/unit/test_file_info.py` | `55ec35637056ac07eef8345d44eda01a10907e5c` |

Raw evidence remains local; no runtime data, keys, models, audio/screenshots or
build outputs are committed. Review matrix/local links, exact diff, source/JUnit
hashes, privacy and ownership before commit. Existing global STOP assertions are
unchanged. The file_info denial assertion is strengthened for the newly required
denied action record; fixture warm-up does not inflate its response deadline.

## Remaining P11 work

H-03's covered intent/pre-state gate and denied/risk logging are repaired.
Other catalog, pending mutation/partial-effect journaling, safe inverse/conflict,
backend adapter and native acceptance gaps remain mandatory. No blanket waiver
or P12 eligibility exists. Browser/clipboard scope decisions were delegated to
the agent by the owner and are recorded in [P11 decisions](p11_scope_decisions.md).
The owner authorized continuing through remaining P11 blocks without a new
permission request; do not start P12 or enable command entry. Recovery for this
checkpoint: 87634db93efe5e01c4c64e16dcf50cc7d404b372 in a new detached worktree.
