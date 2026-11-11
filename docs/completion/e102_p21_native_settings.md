# E102 — P21 native Settings page packet

2026-11-03, Asia/Calcutta. This bounded packet binds surface 2 to the supported
E101 settings contract. It does not complete the full P21 scope or authorize P22.

## Prerequisites and scope

Started on clean `p12-preparation` at
`9936c116cfe99fb9e4ac936c1a0d4cbfcd747df9`. Recovery branch
`recovery/pre-p21-e102-20261103` is pushed at that checkpoint. Main remains
`0468a031238261bee5bc79bd04b16a3d1964a3a9`. The master remains immutable at Git
blob `01b693dbf898b662aa4cd67736c1a0e8a21cf3e3`; earlier complete reading and
unchanged E99–E101 prerequisite evidence are reused. Current AGENTS, P21/shared
execution contract, build plan, A-01/A-03/A-05 and applicable ownership/STOP,
privacy and settings acceptance were inspected before editing.

Declared files: native SettingsPage XAML/code-behind, new SettingsController,
MainWindow navigation/lifetime, shared CommandController typed settings entry,
the two C# test projects, controller checks, owned Python fixture, native page
acceptance and necessary surface/alternate-host contract documentation. Existing
theme resources, palette, typography and card styling remain. No dependency,
master change, branch switch, merge or P22 work occurs.

Pre-edit affected checks: **142 passed**, no skips/xfails, at `9936c11`.
The checkpoint closes the supported page's Save/Cancel/reload/readback/errors,
owned shared command lifecycle, same-turn STOP fencing and shell teardown when
the native checks below pass. Other editable settings are outside this packet.

## Implementation and review

- Native navigation attaches one shell-owned SettingsController. Controls read
  real persisted/effective configuration; no preview model path, binding,
  permission selection or audio-emulation toggle remains. Only the currently
  admitted `max_plan_steps` field is editable. Model/voice/privacy/policy data
  are read-only and configured hotkeys are explicitly not OS-availability proof.
- Save sends one typed request through the shared command owner, exact observed
  revision and existing policy/material confirmation, owned worker, atomic
  storage, verifier and ledger. It never submits generated natural language.
  Active and saved limits remain distinct; the page states Core restart is
  required. E101's actual owned-runtime restart/application evidence is reused.
- Cancel discards only the draft. Reload is read-only. Invalid drafts cannot
  submit. Lost reads clear stale values; unknown writes remain blocked and are
  reconciled without replay. Repeated clicks share the same owned operation.
- Save claims the command request synchronously before its first UI await.
  A deterministic held-dispatcher regression exercises STOP in that interval:
  the exact request is fenced and the client receives no late Save call.
  Independent STOP does not wait for Settings reads or confirmation rendering.
- Reads have linked owner cancellation and a three-second budget; only Busy
  reads are retried. Navigation unsubscribes page events while the shell owns
  the operation. Shell closure cancels/joins command and Settings lifetimes.
- Native tests use fresh fixture storage/credentials and actual Python
  application composition plus authenticated IPC. The fixture exposes only
  IPC readiness to the shell; it does not register global hotkeys or start
  microphone/ML workers. An explicit fixture-owner command edits only the
  fixture's settings to reproduce stale revisions. Tests independently query
  saved values/action verification, and fixture teardown checks the active
  planner limit stayed unchanged, STT/model remained COLD, workers drained and
  storage closed. This is native UI/storage evidence, not physical-device or
  model-compatibility acceptance.
- The Python SettingsContract is accurately documented as an abstract
  alternate-host boundary. Production navigation is the C# MainWindow entry;
  no unused fake Python display implementation is claimed.

## Verification

Evidence root: `output/p21-e102-20261103-125317-022c7a8f/` (ignored, unique).
Every pytest run records its exact command, source identity, stdout and JUnit;
isolated APPDATA/LOCALAPPDATA/TEMP/TMP never target personal storage.

Pre-edit and affected command (via the evidence-root `run_checks.py` wrapper):

```text
<declared-test-python> -m pytest tests/unit/test_settings_execution.py tests/unit/test_settings_store.py tests/unit/test_ipc_request_contract.py tests/unit/test_p17_submission_stop.py tests/unit/test_runtime_shutdown.py tests/unit/test_app_lifecycle.py -q --runxfail -W error::pytest.PytestUnhandledThreadExceptionWarning --junitxml=<unique-run>/results.xml
```

Declared Python is
`D:/Workspace/DEVEL/PLUMA-verified-integration-20261103/output/integration-checks-e98/test-env/Scripts/python.exe`.
Affected run at `5e267d85084287dc8842375a92ea37649582296a`: **142 passed**,
0 errors/failures/skips, 16.172 seconds wall time. Subsequent source changes
only strengthen native fixture/material assertions; Python production behavior
is unchanged. E101's 501 prerequisite/352 contract checks are reused rather than
repeating unaffected backend suites.

Local `dotnet build` for CoreIpc.Tests and SurfaceControls.Tests passes with
zero warnings/errors. Local C# execution remains subject to the previously
recorded Application Control limitation; compilation is not acceptance and
no policy is bypassed. The execution-authorized Windows gate runs the real
assemblies via the existing `PLUMA.UI/verify-ui.ps1` workflow.

Final tested product/test source:
`1c2572c038c6fbf32d8c02134deb3f071ceab2b2` (following implementation `5e267d8`).
[Windows run 41642718466](https://github.com/sai161812/pluma/actions/runs/41642718466)
passes **324 IPC/controller checks, 229 native WinUI checks, 663 popup checks,
195 formatting checks, 64,537 layout checks and 30 surface-contract checks**,
plus audio/visible-copy gates. UI/control builds have zero warnings/errors.
The native page's 15 new checks pass actual persisted/runtime readback,
Cancel-without-file-creation, approval, stale-revision refusal, denial, saved
action verification, restart-needed copy, queued STOP, navigation and joined
shutdown. Controller fault/draft fixtures are distinguished from those actual
native UI/backend cases. The full run also reruns prior native owned-folder
visibility, saved verification and owned-window cleanup. No skips/xfails or
UNEXECUTED checks occur in the final native control report.

Artifact **13232889856**, SHA-256
`39a7464ee67838b5720050d5c0cd066d2c073fc9fd632b73a334a11d1ffee3cd`,
was downloaded and verified against the GitHub API digest. Extracted reports:
`ci-41642718466/extracted/20261103-131717-bbcbffa1/` under the evidence root.
The tested unsigned preview executable SHA-256 is
`0623BA8B43C8A35B16EBF6CDC3F59BF6DE9F9ACF085438556A00B9658BA8036C`;
this is not a signed release/installation gate. Earlier superseded run
41642454886 is **cancelled**, not passed. Its recorded status is retained.

`python docs/completion/verify_requirements_matrix.py` passes 298 source items,
336 traceable rows. `git diff --check` passes after surface-reference whitespace
cleanup. Final documentation-only checkpoint does not alter tested source.
The bounded packet is ready for independent Sol review, with no approval assumed.

## Remaining gates and recovery

Full P21 still requires guarded Text/STOP/voice hotkey registration/conflict and
failure handling; compatible local model/runtime-path edits and owned restart;
voice activation settings; measured warm-grace behavior; permitted privacy,
logging and policy settings without safety bypass; controlled corrupt-source
recovery; combined native save/restart/application/rollback acceptance for those
fields. CORE-CONFIG stays UNVERIFIED. The observed startup log-and-continue
registration failure remains a blocker for editable hotkeys, not a waived gate.

Next safe packet: guarded hotkey lifecycle before adding hotkey edits. Existing
owner-approved C-02 physical timing deferral to P25 and installation/recovery,
performance/security/release gates remain recorded. Independent Sol approval is
not assumed. Recovery uses reviewed dependent reverts preserving subsequent
work and persisted settings; no reset/clean/force-push is required.
