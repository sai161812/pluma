# E39: one registered argument-validation contract

2026-10-22, Asia/Calcutta; source parent `791853d`, branch `ui-wiring`.
P11 remains incomplete. P12 is forbidden.

PlanValidator now calls ToolRegistry.validate_call for every permitted registered
step. Dictionary schemas no longer degrade to a required-key-only check. The
planner and executor use the same Pydantic/JSON Schema contract, including nested
constraints, extra fields, types, bounds and unavailable/unsupported validators.
Invalid arguments cannot reach policy, capture, execution or verification.
Pydantic input values are no longer included in planner argument-validation errors.
No model, native desktop action, package dependency or configured plan limit changes.

The previous matrix description of a registry missing-validator fallback was
stale: inspection confirms the registry already refused a missing jsonschema
dependency. The reproduced permissive fallback was in PlanValidator. This repair
uses the existing registry behavior and does not introduce a second schema engine.

## Evidence

Ignored runner: `output/p11-native-env/Scripts/python.exe
output/p11_power_actions/run_checks.py <suite>`. Windows 11 build 26200,
Python 3.12.10, isolated application/temp paths; JSON retains actual command,
exit, source parent/hashes and fixture-key cleanup. Inert specs fail immediately
if invalid input reaches policy, pre-state, dispatch or readback.

| Suite | Actual result | Wall seconds |
|---|---|---|
| arguments-focused-before | 24 failed / 89 passed in 1.97s | 2.955 |
| arguments-focused-final | 113 passed in 1.41s | 2.259 |
| arguments-regression-final | 161 passed / 1 elevation deselected in 9.40s | 10.297 |
| raw-e39 | 15 passed with --runxfail in 0.72s | 1.623 |

All final actual exits zero, source hashes match and fixture keys zero. Counts
overlap. The elevation exclusion is not a pass. Coverage checker: 298 source
items / 324 rows PASS; diff check PASS. Real jsonschema is installed in this
declared local test environment; valid dictionary-schema positive cases passed.
An explicit missing-module case proves refusal even for otherwise valid input.

Tests exercise direct executor admission, instantiated plans and parsed JSON
plans for both schema representations. Cases cover missing fields, integer
bounds, numeric strings, booleans posing as integers, nested invalid values and
private extra fields, unavailable JSON Schema dependency and unsupported schema
types. Valid arguments survive unchanged. The original failing assertions are
retained. Existing validator, schema, policy, tool ledger, constrained tool-subset
and multi-step orchestration regressions pass. No actual model call or device
mutation is inferred from these admission tests.

A-03's bounded registered-schema invariant is implemented. P13 still owns actual
local-planner lifecycle, malformed output, configured step limits and loaded
execution evidence; those gates are unchanged. Catalog counts remain 48
registered / 25 unregistered; 30 IMPLEMENTED / 25 MISSING / 2 DEFECTIVE /
16 UNVERIFIED. Nine P11 tools and remaining native/inverse/A/D/H checks stay open.
