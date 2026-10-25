# E50 — P11 factual copy, policy acceptance and exact deletion confirmation

Date: 2026-10-22

## Change and evidence

- Added end-to-end ledger checks for allowed READ (`get_preference`) and LOW
  (`create_folder`) calls. Both are verified and logged with the actual risk and
  `ALLOW`; the reversible folder call also persists its inverse.
- Added an explicit-DENY integration check: the registered executor is not
  called, the result explains the denial, and the ledger records `DENY` with
  `executed: false`.
- Added an integration check that a secret in validated arguments and returned
  data does not appear in persisted action history. Existing redaction unit
  cases remain in the same run.
- HIGH-risk `safe_delete` confirmation now states that the exact target moves to
  the Windows Recycle Bin, can be restored there, and will not be permanently
  deleted. Its exact target is separately included in the confirmation summary.
  The callback test approves only this request; no delete operation is run.
- Added an A-07 regression where planner `purpose` fields contain invented
  narrative. The multi-step user-facing summary contains only executor-provided
  `ToolResult.factual_message` text; the planner narrative is absent.
- Adapter priority contracts now reject empty, duplicate or out-of-order lists.
  The built-in `inspect_active_window` list was corrected to Native API before
  UIA. This validates declarations; it does not establish runtime retry/fallback
  behavior, so D-10 remains open.
- Command: `output/p11-native-env/Scripts/python.exe -m pytest tests/unit/test_schemas.py::test_tool_adapter_priority_is_unique_and_in_declared_order tests/unit/test_tools_ui.py tests/unit/test_policy_boundary.py tests/unit/test_policy_engine.py tests/unit/test_redaction.py tests/unit/test_multi_step_orchestrator.py::test_multi_step_successful_execution_chain -q`
- Result: **58 passed in 6.53s** (exit 0).

## Scope still open

H-04 native dialog wiring remains P16 work; this evidence closes the backend
material description for the registered HIGH-risk safe-delete operation.
Elevation broker dispatch remains unimplemented in the registry, and P11 has no
registered ADMIN ToolSpec to bind to one. No elevated action or UAC prompt was
started. D-10 runtime adapter selection/retry remains open.
