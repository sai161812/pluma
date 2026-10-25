# E72 — P13 planner and runtime acceptance

**P13's assigned planner and lifecycle acceptance is complete on
`p12-preparation`.** This
checkpoint closes the previously open A-04/A-05/A-06, B-02/B-06/B-07 and
F-01/F-03/F-05/F-06/F-07/F-08/F-09/F-10 evidence. P14 has not started.

Implementation commits: `93cb0ae052298aaff745525743e67930feb782cf` and
`4e325a4397be70256ac3b6f60cd4630f162ef6dc`. Recovery point before this packet:
`b00fbd70b910555fe9eae554706aab5132137747`.

## Changes

- Native llama.cpp generation now runs in the task-owned worker process. The
  task registers the worker with its process controller/Job Object, and STOP,
  timeout and worker crash terminate only that owned process. Cleanup verifies
  process absence and persists the terminal/cleanup result before retiring
  Windows synchronization handles.
- Planner route schemas remain restricted through replans. Planner
  `target_ref` values reach registry admission and unknown, expired, malformed
  or mismatched references fail before policy or execution.
- `agent.max_plan_steps` now controls both generation schema and strict
  validation. Required structured fields are enforced; schema-generation
  errors no longer fall back to unconstrained JSON generation.
- Activity writes redact active-window/process context. Model output and
  hidden-reasoning fields are not included in stored task/action history.

## Verification

Environment: Windows 11 build 26200, Python 3.12.10, pytest 8.3.3,
psutil 7.2.2, llama-cpp-python 0.3.36, NVIDIA GeForce RTX 5060 Laptop GPU.
The actual model was Qwen3-4B Q4_K_M, 2,497,280,256 bytes,
SHA-256 `7485FE6F11AF29433BC51CAB58009521F205840F5B4AE3A32FA7F92E8534FDF5`.
The harness and isolated settings/SQLite/file fixtures live under ignored
`output/p13-native/`.

The production source tested by the focused suite is commit
`93cb0ae052298aaff745525743e67930feb782cf`. Key source hashes:

- `pluma/brain/llama_cpp_adapter.py` —
  `013A980ADD1A94BF14ED94E258A1E8AB09E052A8E6D374EFE180E1E61161A8F7`
- `pluma/core/task_supervisor.py` —
  `B332E3C9D33F9B4B1782D413D78095FCCA44DDFB520C6CA9BDF165C9C445EE6F`
- `pluma/tools/registry.py` —
  `EACF750B17A3C0B84BD6EFEC38A07A60E61D4CC669A39EA8A7AED6E0839E1363`
- final acceptance harness `tests/windows/p13_native_runtime_acceptance.py` —
  `C5C38F25AD33BDDD8E2A64E88D1300A3FA792FEF46AA55AC49EDD306B3EDC207`

Focused P13 regressions:

```powershell
output\p11-native-env\Scripts\python.exe -m pytest tests\unit\test_app_lifecycle.py tests\unit\test_brain_lifecycle.py tests\unit\test_brain_llama_cpp_adapter.py tests\unit\test_brain_prompt_builder.py tests\unit\test_brain_tool_subset.py tests\unit\test_brain_validator.py tests\unit\test_planner_target_admission.py tests\unit\test_planner_route_replan.py tests\unit\test_router.py tests\unit\test_multi_step_orchestrator.py tests\unit\test_activity_ledger_lifecycle.py tests\unit\test_redaction.py tests\unit\test_executor_admission.py tests\unit\test_task_supervisor.py tests\unit\test_worker_cancellation.py tests\unit\test_cleanup_evidence.py tests\unit\test_runtime_shutdown.py -q
```

Result: **398 passed in 31.44s; zero failures, errors, skips or xfails.**
`python -m compileall -q` on all changed production and new acceptance files
passed. `git diff --check` passed (only Git's LF-to-CRLF working-copy notices).

Actual-model planner acceptance used the isolated `output/p13-native-env` and
the model hash above:

```powershell
output\p13-native-env\Scripts\python.exe tests\windows\p13_native_runtime_acceptance.py --model output\p13-native\model\Qwen3-4B-Q4_K_M.gguf --cycles 1 --report output\p13-native\acceptance-report-final.json
```

All scenarios passed: FAST `show activity` bypassed llama.cpp; loaded native
workers were observed consuming 1.93–2.03 GB RSS and CPU before controlled
STOP, timeout and owned-worker crash; all three workers were absent afterward,
cleanup and SQLite terminal/error records were read back, and no tool action
was admitted before planning. STOP ended `STOPPED`; timeout/crash ended
`FAILED` with a recorded tool failure. The real model produced a two-read plan
for a fixture directory (F-05) and recovered from a missing-file result by
re-observing/replanning to a successful directory listing (F-06). Sensitive
active-window test context and planner reasoning markers were absent from
stored history (F-09/F-10). Each native task returned the lifecycle to COLD.
The final committed-harness combined run passed all scenarios. Its STOP worker
PID was 16228, timeout PID 17904 and injected-crash PID 8984; each loaded
worker used about 1.95–1.99 GB RSS and was absent after cleanup. The native
multi-step plan completed two reads and the failure/replan case completed one
replan. The final cycle returned COLD; the combined run's handle delta was -4
and child-process delta was zero. Full JSON report:
`output/p13-native/acceptance-report-final.json` (ignored).

One intermediate combined run exposed a brittle harness assertion that
required exactly two model-generated calls in one fixed order. The model also
produced valid repeated read-only observations within the configured limit.
The harness now requires a bounded multi-step plan, both expected registered
read-only tools, fixture-only paths, successful results and exact SQLite action
readback. The final combined run passed those checks; no production behavior or
assertion about the configured plan maximum was relaxed.

F-03 adversarial native proposal:

```powershell
output\p13-native-env\Scripts\python.exe tests\windows\p13_native_runtime_acceptance.py --model output\p13-native\model\Qwen3-4B-Q4_K_M.gguf --cycles 0 --skip-stop --unregistered-tool-only --report output\p13-native\acceptance-report-native-unregistered.json
```

The actual model proposed `p13_unregistered_tool_fixture`; strict planner
validation rejected it as unknown/unpermitted, no action was recorded or
executed, SQLite reported `FAILED`, worker absence was verified, and lifecycle
returned COLD. FAST routing also passed in this run.

B-07 native repeated-cycle run:

```powershell
output\p13-native-env\Scripts\python.exe tests\windows\p13_native_runtime_acceptance.py --model output\p13-native\model\Qwen3-4B-Q4_K_M.gguf --cycles 50 --skip-stop
```

**50/50** actual native planning cycles passed. Every cycle ended COLD with no
child worker. Across the run: RSS delta **+835,584 bytes**, process-handle
delta **0**, child-process delta **0**. The report is
`output/p13-native/acceptance-report-50-cycles.json` (ignored).

B-02 cold-idle measurement:

```powershell
output\p13-native-env\Scripts\python.exe tests\windows\p13_native_runtime_acceptance.py --model output\p13-native\model\Qwen3-4B-Q4_K_M.gguf --cycles 0 --skip-stop --idle-seconds 600 --report output\p13-native\acceptance-report-idle.json
```

Measured **600.6 seconds / 48 samples**. Throughout the interval the model
stayed COLD, llama.cpp was not imported into the resident-side process, there
were no children or screen-capture loop, and continuous screen polling was
false. CPU p95/max was **0.48% / 1.01%**; RSS delta **-184,320 bytes**;
handle delta **-1**. All 48 NVIDIA samples reported **0.0% GPU utilization**
and **0 bytes GPU memory**; the PLUMA PID was absent from compute-app listings.
Report: `output/p13-native/acceptance-report-idle.json` (ignored).

## Scope and limitations

Idle measurement used an isolated Python process with the real
`PlumaApplicationRuntime` graph and resident-core object, but did not start
global hotkeys or IPC. It is evidence for cold runtime resource behavior, not
installed/package startup; B-01 and packaging/startup acceptance remain owned
by later milestones. Native inference used CPU llama.cpp; GPU inference and
candidate-model quality selection on the broader fixed corpus are not claimed
here. The latter belongs to the documented P24/P26 quality/performance gates.

No fixture result is represented as native model evidence. Native scenarios
above ran with llama-cpp-python and the identified GGUF. No P14 implementation
or acceptance was started.
