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
- Direct deadline/verification cases:
  **3 passed in 1.54s** (shared policy/executor deadline, expired journal
  acknowledgement refuses dispatch, and blocked-verifier timeout).

## Remaining D-09 scope

This closes policy and journal time being added on top of the declared call
timeout. It does not establish the full D-09 gate: native legacy adapters,
every rollback path, catalog-wide whole-call cleanup and all task outcome
combinations still need evidence. D-09 therefore remains DEFECTIVE and P11
remains incomplete.
