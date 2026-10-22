# P11 E26: factual worker disposal and failure causes

2026-10-20, Asia/Calcutta. Parent checkpoint `0c2e8e6`, ui-wiring.
This closes overall-audit R01 only. **P11 remains incomplete; P12 is forbidden.**

## Defect and bounded repair

Reopened E25 owned-success SQLite contained SUCCEEDED / user_stop with no user
STOP. Normal TaskCapsule/registry disposal called the cancellation path. A real
owned worker transport crash also sealed admission and was projected as STOPPED.

`TaskWorkerController.dispose_owned_worker` seals admission before termination,
retains original ownership/Job/exit readback and does not request parent STOP.
TaskCapsule and registry lifecycle disposal use that operation. Explicit STOP
and timeout still use cancellation and preserve the first actual cause.
Both orchestrators classify an admission fence without an explicit cause as an
internal execution failure and use authoritative failure/rollback cleanup.
Successful disposal records no cancellation cause. Internal failure records
internal_error, genuine STOP user_stop, and deadlines task_timeout.

Cancellation docstrings distinguish admission fencing from explicit parent
cancellation. No latch is reset. A genuine cancellation arriving after a
disposal-only fence can still record its actual cause. Cleanup evidence,
residual handling, admission barriers and owned-only termination remain required.

Changed runtime/contract files: pluma/tools/registry.py,
pluma/core/task_supervisor.py, pluma/core/orchestrator.py,
pluma/core/multi_step.py and pluma/core/cancellation.py. Tests:
tests/unit/test_worker_disposal_cause.py, test_cleanup_evidence.py and
test_backend_wiring_audit.py (the latter two in the same tests/unit directory).
Updated this evidence, overall audit, requirements matrix, PROJECT_HANDOFF.md
and PLUMA.UI/PLUMA.UI/docs/backend_wiring_audit.md. Historical rows are not
rewritten to hide the earlier defect.

## Acceptance and reproduction

New `tests/unit/test_worker_disposal_cause.py` uses native owned workers/Jobs,
isolated SQLite and inert router/planner fixtures. FAST and SMART success,
tool failure and deliberate owned-worker exit are checked through terminal
result, capsule, cleanup readback and reopened database. Disposal-only, user STOP
and deadline cases assert admission closure and first-cause preservation.
Existing E25 native STOP/deadline and shutdown regressions remain unchanged.

First fixture run: 7 failed / 2 passed in 3.90s, including two fixture mistakes
(nonexistent PlanMode.SINGLE_STEP and incorrect ownership enum casing). Corrected
before runtime edits: **5 failed / 4 passed in 5.72s**, reproducing false successful
causes, both crash projections and disposal-only cancellation. After repair:
**9 passed in 4.68s**, actual pytest exit zero. No xfail/skip/deadline relaxation.

Commands use the ignored isolated native runner:

```text
output/p11-native-env/Scripts/python.exe output/p11_disposal/run_checks.py disposal-before-corrected
output/p11-native-env/Scripts/python.exe output/p11_disposal/run_checks.py disposal-tools
output/p11-native-env/Scripts/python.exe output/p11_disposal/run_checks.py focused-reviewed
output/p11-native-env/Scripts/python.exe output/p11_disposal/run_checks.py regression-reviewed
output/p11-native-env/Scripts/python.exe output/p11_disposal/run_checks.py raw-fixture-reviewed
output/p11-native-env/Scripts/python.exe output/p11_disposal/run_checks.py containment-final
output/p11-native-env/Scripts/python.exe output/p11_disposal/run_checks.py recovery-final
output/p11-native-env/Scripts/python.exe output/p11_disposal/run_ipc_audit.py
output/p11-native-env/Scripts/python.exe docs/completion/verify_requirements_matrix.py
```

First broad run: 791 passed / 1 failed / 1 excluded in 106.94s. The existing
cleanup Worker double lacked the new disposal interface. Added a delegating
fixture method; all failure/retention/readback assertions remain unchanged.
Focused run: **792 passed / 1 excluded in 105.68s**, actual exit zero,
runner wall 106.545s. First full regression: 1109 passed / 1 failed / 3 skipped /
1 excluded in 125.01s. The original BA runtime-close bare Mock synthesized an
optional disposal method, bypassing its observed terminate mock. Explicitly
aliased that fixture method to its existing termination mock; the original BA
assertion is unchanged. Raw audit with --runxfail then passed **15 in 0.39s**.
Production sources did not change after the 792-pass run; its recorded test-file
hash predates this one fixture alias. Final regression/raw hashes cover the
alias. Final results are below.
| Check | Actual output | Runner wall |
|---|---|---|
| focused-reviewed | 792 passed / 1 excluded, 105.68s | 106.545s |
| regression-reviewed | 1110 passed / 3 skipped / 1 excluded, 161.90s | 162.944s |
| raw-fixture-reviewed (--runxfail) | 15 passed, 0.39s | 0.957s |
| containment-final | 3 passed, 3.95s | 4.907s |
| recovery-final | 5 passed, 0.60s | 1.435s |
| native authenticated Python/C# IPC | 39 passed | 7.057s |

Actual exits zero. Windows 11/Python 3.12.10 native venv as E25; no dependency
change. Final regression/raw/containment/recovery/IPC source hashes match;
focused production hashes match, with the documented subsequent test alias.
115/115 FAST regression cases carry desktop isolation. Every final fixture-key
count is zero. Independent read-only SQLite inspection finds exactly two
SUCCEEDED/NULL and four FAILED/internal_error owned disposal rows. review.json
retains that consolidation. Matrix: 298 source items / 324 traceable rows PASS.
Three corpus skips and excluded system-changing elevation are not acceptance
passes or owner waivers. Test duration is not a product latency claim.

The copied IPC runner initially retained E25's fixed output directory, refreshing
its ignored IPC log. Fresh E26 artifacts were copied into output/p11_disposal
and its runner output directory corrected; the durable E25 historical summary
is retained. No production source or earlier commit history was rewritten.

Runner logs/JUnit/JSON retain source hashes, environment, durations and real
pytest exit codes under ignored output/p11_disposal. The wrapper's exit alone
is not treated as test success. Same isolated storage/native interpreter,
20s test bounds and 240s suite bounds as E25. Temporary system-awake request
restored afterward; no security-policy changes or user resources mutated.

## Limits and next safe milestone

No catalog status is promoted by this repair. The audit remains 9 bounded READs,
27 missing non-P12 tools, 4 defective and 17 unverified. Existing unimplemented
catalog/inverse/irreversible/backend policy gates remain. No physical device,
UI, STT/model, performance, installation or release acceptance is claimed.
The next safe milestone is another bounded P11 defective-tool repair. Do not
start P12 or automatically choose a later milestone.
