# P11 slice 1: file_info contract and evidence (E17)

Completed 2026-10-20 (Asia/Calcutta). **This bounded slice passes; P11 remains
incomplete and P12 is ineligible.** No automatic next slice, UI enabling or merge.

## Prerequisites and source

Started clean on local/remote ui-wiring at
`29fa6eb59f2aaa0b3322aaa966e28de97bce63bc`. Rechecked origin/four worktrees,
main `6dbf589`, integration `9544752`, draft/open/unmerged PRs 1/2. Read shared
P11/current handoff/AGENTS and relevant master 11-16/21/24-25, build-plan typed
framework/policy/orchestration, acceptance A-02/A-03/A-07/D-09/H-01/H-06/H-07,
technology and UI references. The complete master read from earlier gates is
retained; immutable requirements are unchanged. Inspected 73 catalog rows in
13 categories and source ASTs of 13 tool modules; actual process/browser/terminal
stubs and nonaccepted aliases remain gaps. Selected exact missing file_info,
not the entire catalog. H-03 explicit MEDIUM intent remains open.

Before tracked edits: P01-P10 prerequisites **318 passed in 36.75s**; matrix
**298 source items / 324 rows**. Existing tests/assertions are unchanged. Final
source is the commit containing this record, parent `29fa6eb`:

| File | Git blob |
|---|---|
| `pluma/tools/files.py` | `bd5cc4b6bc1be2e023f9c9de23695d1f3710a221` |
| `pluma/tools/registry.py` | `a3cea733ba8b5cdcbf3956bcf72add7182b0a05e` |
| `pluma/core/task_supervisor.py` | `c2d8357bb179b81f8aa9dbc7348aa89b2daa70f9` |
| `pluma/core/orchestrator.py` | `fb4bb96c32ed4d3367bf081cf2d70b223be81c8b` |
| `pluma/core/multi_step.py` | `b81bc41641c6ebd02138ac0cf87383205dd90bef` |
| `pluma/brain/tool_subset.py` | `652802823460026a87007f2f4f1505a9c645da7c` |
| `tests/unit/test_file_info.py` | `143c9cc6d50fe73182163c19487fcd107d8cc722` |

Six runtime, one test and four evidence/handoff files change. No runtime/test
source was edited during pytest. No UI/C#/protocol, physical voice/model,
immutable requirement, dependency or action-entry change.

## Functional contract

Exact default-registered READ ToolSpec `file_info` accepts only required strict
string path (1-32767 characters), no extra fields. A fully qualified literal
Windows filesystem path is required: no relative/current-directory guesses,
glob, environment/shell expansion, parent traversal, device/reserved/stream
syntax or trailing aliases. Ordinary local/UNC syntax is accepted; live UNC/
other-filesystem acceptance is not established by these local Windows fixtures.
Validation precedes policy and I/O; no unrestricted shell/admin API is exposed.

The registry isolates even this READ tool in its existing task-owned process,
with native admission, original worker identity/Jobs and five-second deadline.
No potentially blocking filesystem query runs in the parent verifier. SMART/
DEEP file schema subsets expose file_info; FAST/screen-only planning subsets do
not. No new natural-language grammar or real-model planning is claimed. Typed
plans exercise the real registry/orchestrator; action entry remains disabled.

Two matching native lstat observations query ancestors root-to-target and reject
observed symlink/reparse boundaries. Only regular files/directories with native
identity are supported. Result fields:

| Field | Meaning |
|---|---|
| path | pathlib-normalized literal, without resolving links |
| kind | file or directory |
| size_bytes | Native file length; null for directory, no recursive total |
| modified_ns | Native modification timestamp in nanoseconds |
| device / file_id | Native stat identity, not reboot-stable ownership |

No file contents or directory enumeration. The actual executor queries supply
readback; the strict verifier checks schema, verified native-adapter proof and
file/directory size consistency. Missing/denied/I/O/unsupported/reparse/changed
observations produce fixed codes/copy and no fabricated/partial metadata.
New executor errors do not include native exception strings. Existing ledger
redaction is retained. This is point-in-time metadata, not an atomic locked
snapshot or adversarial namespace guarantee; dynamic reparse/swap attacks remain
P27. Observed static target/ancestor junctions are refused in native tests.

The inspected resource is never claimed as PLUMA-created. No state mutation,
undo record or inverse is promised for a READ query. Tests read back unchanged
file content/identity/mtime, directory children and empty undo records. An actual
fixture change between observations is preserved while the query is refused.

## Timeout accounting fix required by the slice

The first blocked-read test exposed inherited process timeout accounting:
disposal latched default user_stop before TOOL_TIMEOUT projection. The controller
now latches task_timeout before disposal; the registry's queued/deadline timeout
branch does likewise. One-way first-cause semantics are preserved.

FAST projection and multi-step handling recognize an actual TOOL_TIMEOUT result
with task_timeout and use the existing failure/rollback owner. That owner now
accepts task_timeout as well as internal_error, producing FAILED with cleanup/
residual evidence preserved. Earlier user_stop is not overwritten. Explicit
supervisor STOP carrying a timeout reason retains its prior STOPPED semantics;
a reason alone is not proof of executor failure. Existing global ordering tests
remain untouched. Native deadline/STOP tests on FAST and SMART reconcile memory,
result, task/action SQLite and typed terminal STOP readback; tested FAILED
timeouts have zero clean stopped_count. Broader ordinary in-process timeout
finalization remains D-09/P11 work, not certified by this correction.

## Checks and actual output

Windows 11 build 26200 / Python 3.12.10 x64 / pytest 8.3.3. Every run has its own
user-local LOCALAPPDATA/APPDATA/TEMP/TMP root and removes inherited PLUMA_*
overrides. Owned files/processes/Jobs/pipes/SQLite, inert voice/model/UI seams;
no production credential or user application is read/repaired/operated for tests.
Thread exceptions are errors. Final actual pytest exits are zero, source SHA-256
matches and fixture keys remaining zero. Runner return alone is not evidence.

| Check | Actual output |
|---|---|
| Pre-edit P01-P10 | 318 passed in 36.75s |
| Final focused | 481 passed, 1 deselected in 58.00s |
| Isolated regression | 799 passed, 3 skipped, 1 deselected in 74.56s |
| Raw audit, --runxfail | 15 passed in 0.76s |
| Native containment | 3 passed in 3.60s |
| Startup/recovery | 5 passed in 0.79s |
| Matrix | 298 source items / 324 rows |

All 50 new cases pass in final suites: 22 invalid schemas before policy/I/O;
unknown tool; real file/directory/Unicode metadata via text/voice requests;
policy refusal and failed task history; missing target; injected permission/I/O
copy redaction; actual content change between reads; native junction/ancestor
refusal; malformed/unproved result rejection; native blocked READ deadline/STOP
on FAST/SMART; first-cause failure ownership; route schema discovery. Original
file tools, policy, rollback, cancellation, shutdown and all raw audit assertions
pass in the selected regressions. All 115 FAST cases have desktop_isolation
properties from the explicitly loaded plugin; preserve P02's correction.

Voice mode tests shared request handling, not a physical microphone/STT. The
blocked native-query executor and permission/I/O errors are explicit injections;
real process/Jobs/admission/timeout/cleanup and persistence are retained. Actual
different-token/ACL access denial is not claimed. Native junction fixtures use
bounded hidden cmd/mklink /J on exact owned temp paths. No real desktop/input,
capture, model, security-policy bypass or system-changing elevation ran.

Before dispatch, the inherited registry policy-denial return precedes executor
action logging. Tests verify the actual failed task history, no worker/target
mutation and no private-target leakage; no nonexistent action row is invented.
Detailed denied-action logging remains a separate P11 gap. Three corpus skips
and one excluded elevation operation are not passes or approved limitations.
No audit xfail remains. No physical UI/device, actual planner interruption,
loaded p95, UNC/reboot/security/install/package/release acceptance is claimed.

Commands: `python output/p11/run_checks.py <name>`, using the isolated environment
above. Exact expanded prerequisite/final commands are also retained in JSON:

```text
C:\Users\saipr\AppData\Local\Programs\Python\Python312\python.exe -m pytest tests/unit/test_backend_safety_integration.py tests/unit/test_ipc_credentials.py tests/unit/test_backend_wiring_audit.py::test_first_windows_credential_is_verified_before_return tests/unit/test_stop_protocol.py tests/unit/test_backend_wiring_audit.py::test_ipc_stop_reply_distinguishes_residual_cleanup tests/unit/test_backend_wiring_audit.py::test_ipc_stop_reply_does_not_claim_nonterminal_task_stopped tests/unit/test_voice_session.py tests/unit/test_backend_wiring_audit.py::test_voice_stop_closes_capture_without_key_release tests/unit/test_backend_wiring_audit.py::test_empty_voice_capture_finalizes_its_capsule tests/unit/test_runtime_shutdown.py tests/unit/test_backend_wiring_audit.py::test_runtime_close_drains_active_task_and_registry tests/unit/test_terminal_outcome.py tests/unit/test_backend_wiring_audit.py::test_fast_stop_preserves_supervisor_residual_outcome tests/unit/test_cleanup_evidence.py tests/unit/test_backend_wiring_audit.py::test_failed_worker_cleanup_requires_residual_state tests/unit/test_worker_cancellation.py tests/unit/test_executor_admission.py tests/unit/test_global_stop_ordering.py tests/unit/test_backend_wiring_audit.py::test_worker_stop_interrupts_outstanding_response_wait tests/unit/test_backend_wiring_audit.py::test_stop_during_prestate_prevents_executor_start tests/unit/test_backend_wiring_audit.py::test_global_stop_latches_every_task_before_first_grace -q -o addopts= -o junit_family=xunit1 --timeout=20 --timeout-method=thread --tb=short -ra -W error::pytest.PytestUnhandledThreadExceptionWarning -p no:cacheprovider --junitxml=D:\Workspace\DEVEL\PLUMA\output\p11\prerequisite-before.xml

C:\Users\saipr\AppData\Local\Programs\Python\Python312\python.exe -m pytest tests/unit/test_brain_tool_subset.py tests/unit/test_file_info.py tests/unit/test_tools_files.py tests/unit/test_tool_runner_ledger.py tests/unit/test_policy_engine.py tests/unit/test_backend_safety_integration.py tests/unit/test_ipc_credentials.py tests/unit/test_backend_wiring_audit.py::test_first_windows_credential_is_verified_before_return tests/unit/test_backend_wiring_audit.py::test_ipc_stop_reply_distinguishes_residual_cleanup tests/unit/test_backend_wiring_audit.py::test_ipc_stop_reply_does_not_claim_nonterminal_task_stopped tests/unit/test_stop_protocol.py tests/unit/test_ipc.py tests/unit/test_voice_session.py tests/unit/test_voice_pipeline.py tests/unit/test_voice_activation.py tests/unit/test_voice_vad.py tests/unit/test_brain_lifecycle.py tests/unit/test_voice_lifecycle.py tests/unit/test_voice_capture.py tests/unit/test_runtime_shutdown.py tests/unit/test_terminal_outcome.py tests/unit/test_db.py tests/unit/test_cleanup_evidence.py tests/unit/test_rollback_engine.py tests/unit/test_rollback_recipes.py tests/unit/test_worker_cancellation.py tests/unit/test_global_stop_ordering.py tests/unit/test_executor_admission.py tests/unit/test_task_supervisor.py tests/unit/test_schemas.py tests/unit/test_ownership.py tests/unit/test_job_object.py -q -o addopts= -o junit_family=xunit1 --timeout=20 --timeout-method=thread --tb=short -ra -W error::pytest.PytestUnhandledThreadExceptionWarning -p no:cacheprovider --junitxml=D:\Workspace\DEVEL\PLUMA\output\p11\focused-refined.xml -k "not test_elevation_broker_execution"

C:\Users\saipr\AppData\Local\Programs\Python\Python312\python.exe -m pytest tests/unit/test_backend_wiring_audit.py tests/unit/test_schemas.py tests/unit/test_router.py tests/unit/test_brain_validator.py tests/unit/test_policy_engine.py tests/unit/test_redaction.py tests/unit/test_activity_ledger_lifecycle.py tests/unit/test_rollback_engine.py tests/unit/test_rollback_recipes.py tests/unit/test_tool_runner_ledger.py tests/unit/test_perception_freshness.py tests/unit/test_phase13_7_ui_verification.py tests/unit/test_phase13_7_created_stop.py tests/unit/test_ipc.py tests/unit/test_brain_tool_subset.py tests/unit/test_file_info.py tests/unit/test_tools_files.py tests/unit/test_backend_safety_integration.py tests/unit/test_ipc_credentials.py tests/unit/test_stop_protocol.py tests/unit/test_voice_session.py tests/unit/test_voice_pipeline.py tests/unit/test_voice_activation.py tests/unit/test_voice_vad.py tests/unit/test_brain_lifecycle.py tests/unit/test_voice_lifecycle.py tests/unit/test_voice_capture.py tests/unit/test_runtime_shutdown.py tests/unit/test_terminal_outcome.py tests/unit/test_cleanup_evidence.py tests/unit/test_worker_cancellation.py tests/unit/test_global_stop_ordering.py tests/unit/test_executor_admission.py tests/unit/test_fast_orchestrator.py tests/unit/test_multi_step_orchestrator.py -q -o addopts= -o junit_family=xunit1 --timeout=20 --timeout-method=thread --tb=short -ra -W error::pytest.PytestUnhandledThreadExceptionWarning -p no:cacheprovider --junitxml=D:\Workspace\DEVEL\PLUMA\output\p11\regression-isolated.xml -k "not test_elevation_broker_execution" -p tests.fixtures.desktop_isolation

C:\Users\saipr\AppData\Local\Programs\Python\Python312\python.exe -m pytest tests/unit/test_backend_wiring_audit.py -q -o addopts= -o junit_family=xunit1 --timeout=20 --timeout-method=thread --tb=short -ra -W error::pytest.PytestUnhandledThreadExceptionWarning -p no:cacheprovider --junitxml=D:\Workspace\DEVEL\PLUMA\output\p11\raw-final.xml --runxfail

C:\Users\saipr\AppData\Local\Programs\Python\Python312\python.exe -m pytest tests/unit/test_phase13_8_final_patch.py::TestTaskOwnedWorkerContainment -q -o addopts= -o junit_family=xunit1 --timeout=20 --timeout-method=thread --tb=short -ra -W error::pytest.PytestUnhandledThreadExceptionWarning -p no:cacheprovider --junitxml=D:\Workspace\DEVEL\PLUMA\output\p11\containment.xml

C:\Users\saipr\AppData\Local\Programs\Python\Python312\python.exe -m pytest tests/unit/test_app_lifecycle.py tests/unit/test_crash_recovery.py -q -o addopts= -o junit_family=xunit1 --timeout=20 --timeout-method=thread --tb=short -ra -W error::pytest.PytestUnhandledThreadExceptionWarning -p no:cacheprovider --junitxml=D:\Workspace\DEVEL\PLUMA\output\p11\recovery.xml

```

Intermediate failures retained: file-info-first **40 passed / 1 failed in
12.65s** exposed STOPPED/user_stop on actual timeout. File-info-final **43 passed
in 11.66s** followed initial timeout changes. The first broad focused run had
**477 passed / 1 failed / 1 excluded in 58.27s**: an unchanged explicit STOP test
expected STOPPED. The repair was narrowed to actual TOOL_TIMEOUT failure owners,
without changing that assertion. file-info-refined **49 passed in 14.56s**
preceded final route/readback/denial checks (50 cases in final suites). No old
failure is erased or counted as the final tested source. A documentation review
wrapper's class-name filter was corrected to include FAST test classes; actual
JUnit results were unaffected.

## Artifacts, remaining gate and recovery

Ignored output/p11 retains run_checks.py, catalog/source inventories, every
named log/JSON/JUnit including failed intermediates, source hashes, isolated
roots and actual exits/wall durations. Final local metadata hashes:

| Artifact | SHA-256 |
|---|---|
| `prerequisite-before.json` | `73831b20ba5c8baddb5371de4fae68a5e9744ee0ee0289b4b6d1f6897d28d578` |
| `focused-refined.json` | `5d2ac78c18e00ccb164d3f1985c718213e744270b4f1a30b303c03447d53e95b` |
| `regression-isolated.json` | `28eb802d79159427605b900a5b798b0691dae805a013694e068e561afd6a0436` |
| `raw-final.json` | `77bf4055a74ef1dc5800f81ee767fa25defcaf0139c05ed6e68ecc01145deb8d` |
| `containment.json` | `1532f714f7f900cf8ff1d21f55591046b54d7438f338197d19485ab12349973f` |
| `recovery.json` | `d896e024fc9277843d23b4214716af2160f01f3d58da20672235d799f8be718c` |
| `run_checks.py` | `9d43fd68f43b30ee65d02ea52f9fbd3e9bbb1ad07bd0af3b475e67b76a128aac` |
| `catalog-review.json` | `0b3e9279827fece994d8b2533a02df116cfb987c209ddd9f71bb67abf817c52d` |
| `source-catalog-review.json` | `baffea62586090dc83834172cc18f80982b0c26ee69a657daf614df9e421ac7e` |

Only CAT-file_info moves from MISSING to bounded IMPLEMENTED. The full catalog
still has 49 MISSING, 4 DEFECTIVE and 19 UNVERIFIED entries across P11/P12/etc.
No mandatory entry is optionalized. H-03 explicit MEDIUM intent, existing
mutating-tool verification/undo/denied logging and other catalog capabilities
remain open. No owner-approved blanket limitation exists; later device/UI/
inference/performance/security/install/release gates remain mandatory.

**Next safe milestone: another separately instructed P11 slice**, with H-03 still
a priority candidate. P11 full gate has not passed; P12 is ineligible. Do not
start another slice automatically, enable action entry or merge. Commit/push
only ui-wiring; PRs 1/2 draft/open/unmerged, main/integration/worktrees/archive/
stash/tags retained. Recovery: `29fa6eb59f2aaa0b3322aaa966e28de97bce63bc` in a
new detached worktree.

Final review passed: matrix/local links, git diff --check, bounded AST function
changes, unchanged existing tests/requirements/UI, factual copy, no content
logging, ownership cleanup and final source/JUnit hashes. Exact staged paths
are checked before commit. No full UI or C# rerun is
claimed for unchanged production components.
