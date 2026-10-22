# E49 — Shared ToolSpec deadline across policy and execution

Date: 2026-10-22

## Change

The registry now starts one wall-clock deadline after tool lookup and argument
validation. Policy evaluation, safe pre-state capture, executor dispatch and
postcondition readback consume that same `ToolSpec.timeout_s` budget. If policy
uses the full budget, the call is refused before dispatch; if execution or
readback runs out of budget, it returns a factual `TOOL_TIMEOUT` result and
keeps the existing owned-worker / pending-mutation cleanup rules.
The registry also refreshes the remaining budget after durable mutation
journaling and refuses executor admission if that required acknowledgement
used the remaining time.

## Evidence

- Regression: `test_policy_and_executor_share_the_declared_tool_deadline`
  uses an inert policy and executor whose separate delays exceed the declared
  budget together. It confirms the action starts only with the remaining time,
  times out within the total budget and owned work drains.
- Focused command:
  `output/p11_power_actions/run_checks.py verification-tools-focused`
- Result: **79 passed in 49.91s** (exit 0), including verification ownership,
  executor admission, mutation journal, pre-state ownership and ledger runner.
- Broader deadline/cleanup/rollback command:
  `output/p11-native-env/Scripts/python.exe -m pytest tests/unit/test_tool_runner_ledger.py tests/unit/test_verification_ownership.py tests/unit/test_executor_admission.py tests/unit/test_prestate_ownership.py tests/unit/test_cleanup_evidence.py tests/unit/test_rollback_engine.py tests/unit/test_rollback_recipes.py tests/unit/test_manual_undo.py -q`
- Result: **117 passed in 40.52s** (exit 0), covering factual timeout results,
  owned worker drainage, durable pending-state cleanup, rollback and manual undo.
- Direct deadline/verification cases:
  **3 passed in 1.54s** (shared policy/executor deadline, expired journal
  acknowledgement refuses dispatch, and blocked-verifier timeout).

## D-09 disposition

The shared call budget plus the focused timeout/cleanup/rollback evidence above
close the D-09 backend acceptance behavior. This does not certify physical
device, installed-release or crash-recovery behavior, which remains tracked in
the later milestones. Other P11 matrix gates remain open; D-09 itself is now
IMPLEMENTED.
