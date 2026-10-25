# E71 — P13 bounded packet: planner STOP responsiveness

Date: 2026-10-26

Status: the bounded STOP-responsiveness subtask is complete. The E70 F-07/F-08
worker-absence gate remains open; P13 remains incomplete.

Branch: `p12-preparation`

Implementation commits:

- `6a06fc41a92a397e002f5a9bef0aa822fde1c79c` — `fix(p13): interrupt planner waits on STOP`
- `15c19a4a1cdc7a2093999d308332c391ad678083` — `fix(p13): cancel queued planner work on STOP`

Recovery point before E71: `bee6626fb83c20c87df0f3ea12b470eb164b6701`

## Scope and reproduced gap

The E70 handoff selected planner timeout/STOP ownership (F-07/F-08). A new
blocked-backend regression reproduced the waiter defect before the code change:
after the task cancellation latch was set, `LlamaCppAdapter.plan()` remained
blocked in `Future.result()` for the backend's full timeout. The assertion that
the planner returned within 250 ms failed while the fixture generation remained
blocked.

## Change

- The adapter now polls the task latch while awaiting the owned inference future,
  checks the latch before validation and before returning a validated plan, and
  requests cancellation of work that has not started on STOP or inference
  timeout.
- A backend-raised `TimeoutError` is preserved as a generation failure instead
  of being mistaken for the adapter's wait deadline.
- SMART, SCREEN and DEEP planning error paths preserve an already latched user
  STOP as a STOP result.
- The blocked SMART integration fixture verifies that STOP acknowledges the
  latch, returns a STOP outcome, starts no tool, and leaves the blocked
  `planner_inference` future recorded on the task until it exits.

The poll interval is 25 ms. Cancelling a running `Future` does not terminate its
thread. When the backend is unresponsive, cleanup remains residual and owned;
this change does not report that worker as terminated or cleanup as complete.

## Verification

Environment: Windows, Python 3.12.10, pytest 8.3.3. Fixture data and JUnit XML
are under ignored `output/p13-f08/`.

The pre-fix reproduction command was:

```powershell
& .\output\p11-native-env\Scripts\python.exe -m pytest -q -p no:cacheprovider tests/unit/test_runtime_shutdown.py::test_native_planner_stop_interrupts_wait_and_never_returns_late_plan
```

It failed at `returned.wait(0.25)` while inference was held by the fixture.

The final affected regression command was:

```powershell
New-Item -ItemType Directory -Force -Path output\p13-f08\appdata, output\p13-f08\localappdata, output\p13-f08\temp | Out-Null
$runRoot = (Resolve-Path output\p13-f08).Path
$env:APPDATA = Join-Path $runRoot 'appdata'
$env:LOCALAPPDATA = Join-Path $runRoot 'localappdata'
$env:TEMP = Join-Path $runRoot 'temp'
$env:TMP = Join-Path $runRoot 'temp'
$plannerTests = rg --files tests/unit | Where-Object { $_ -match '\\test_brain_.*\.py$' }
& .\output\p11-native-env\Scripts\python.exe -m pytest tests/unit/test_runtime_shutdown.py @plannerTests tests/unit/test_schemas.py tests/unit/test_multi_step_orchestrator.py tests/unit/test_router.py tests/unit/test_fast_orchestrator.py -q --runxfail -W error::pytest.PytestUnhandledThreadExceptionWarning -p tests.fixtures.desktop_isolation --junitxml=output/p13-f08/planner-stop-final.xml
```

Result: **420 passed, 0 failed, 0 errors, 0 skipped**, 42.00 seconds. The suite
includes planner adapter/lifecycle/validator, schemas, all runtime-shutdown
tests, multi-step orchestration, routing and FAST/zero-ML coverage. Its STOP
regressions cover running and queued futures; `--runxfail` was enabled. JUnit
reports `tests=420 failures=0 errors=0 skipped=0`. `git diff --check` passed.

The `llama_cpp` module is unavailable (`find_spec('llama_cpp')` returned false)
in this environment. No model package was installed and no weights were
downloaded for this packet, so this run is fixture evidence only. It does not
verify native llama.cpp cancellation, process absence, crash cleanup, model
quality, real-model malformed-output handling, or physical memory unload.

SHA256 of the tested implementation/test files:

| File | SHA256 |
|---|---|
| `pluma/brain/llama_cpp_adapter.py` | `5991a356296fc8b40ac09d90552f6bd77c9471c65e4fbae8fda13ba17248e6c9` |
| `pluma/core/orchestrator.py` | `92bcd4c6be46362443cf837591b8c9e3f58b3ce0ba7e6b9169dd0c5361c27ade` |
| `tests/unit/test_runtime_shutdown.py` | `3ff3695cd490f78c1647e2c1eba8c25f2c8e685f679762ddfce21133b4a93be7` |
| `tests/unit/test_brain_llama_cpp_adapter.py` | `08a05d7671f0edf9f71768eef486e7f013ea7a6bee09b709194947d29810b505` |

## Remaining P13 gates

- **F-07/F-08 and B-06:** run native local inference in a task-owned,
  verifiably cancellable worker; prove timeout/STOP termination and process
  absence before clean task completion, including ledger readback and no later
  tool/replan. The current thread remains owned and yields residual evidence.
- **A-05:** pass configured `agent.max_plan_steps` (default 8) into the production
  `PlanValidator`; test values above and below that setting while preserving the
  hard cap.
- **A-06:** remove broad generation retry behavior that can hide a schema-mode
  failure; prove malformed/native output fails closed without a fabricated plan.
- **A-04:** prove unknown and expired planner `target_ref` values are rejected at
  actual tool admission.
- **F-01/F-03/F-05/F-06/F-09/F-10:** close the remaining end-to-end planner
  acceptance, including real constrained plans, invalid/invented calls,
  execute-observe-replan, sensitive context and factual history. Fixture tests
  pass in the affected suite but do not prove native-model behavior.
- **B-02/B-07 and related CORE-PLANNER/CORE-PROCESS/CORE-CONFIG rows:** record
  real idle/unload and repeated-cycle evidence, and verify effective runtime
  configuration. Do not infer these from mock lifecycle tests.

Next safe packet: design and implement the task-owned native inference worker
boundary and prove cancellation, timeout, process absence and cleanup readback.
Then address configured plan limits and remaining planner acceptance. No P14
work is authorized or started here.
