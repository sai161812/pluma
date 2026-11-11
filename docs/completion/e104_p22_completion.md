# E104 - P22 health, setup and controlled recovery complete

Current-status note: [E105](e105_p22_completion_recheck.md) supersedes this
completion conclusion after four additional edge fixes and fresh acceptance.
The source-specific E104 results below remain historical evidence.

P22's scoped implementation and required gate are complete. P23 has not started.
Ready for independent Sol review; approval and full-product readiness are not assumed.

## Scope and source identity

Base/recovery: `9d6653e3df6eb1ca7bd509590d58e401376a7262`, pushed as
`recovery/pre-p22-e104-20261103`. Active development is `p12-preparation`.
Main remains `0468a031238261bee5bc79bd04b16a3d1964a3a9`; no merge, reset,
clean, force-push, branch switch, security bypass or dependency change occurred.
The complete master, AGENTS, P22/shared contract, handoff, build/acceptance,
affected matrix rows, owner decisions and prior findings were reviewed.
Immutable master blob stays `01b693dbf898b662aa4cd67736c1a0e8a21cf3e3`.
Pre-edit affected/prerequisite selection: 117 passed, no skips/xfails.

Exact final native UI/runtime source: `864b867890f93c233265d7cb6294c9086a6f0af7`.
The final documentation commit changes no runtime or test source. Python backend
and tests match `718c05793a62719c0850eca4f39d4d7ac37cd0b9`, whose final required
selection passes 1,057 checks. Later commits change only the C# reconciliation
path and its regression test. Native setup access passes on
`ab2e31c7b46be3c043086d188ee85a524dd4b9b0`; its probe/tool/harness source is
unchanged. Later host changes fence restart against STOP, covered by the final
Python selection and native UI gate.

## Completed requirements

| P22 requirement | Implementation and evidence |
|---|---|
| Health 23 / Dashboard | Authenticated host UUID, PID/creation time, actual state/code, config fingerprint, native receipts and actual hotkey proof. Existing bounded runtime reads invalidate stale/disconnected/not-ready proof. Explicit reads/checks add no background health poller. |
| Setup 26 | Explicit owned 30-second worker validates local llama.cpp vocabulary/model access, whisper.cpp model open/release, actual OCR ONNX sessions, native UIA root and separately consented microphone open/start/close. No downloads, inference, retained samples or screenshots. Actual hotkeys are read from the live registration owner. |
| Truthful readiness | Individual failures remain FAILED/UNVERIFIED even when the observation task succeeds. Continue requires all five PASSED native receipts, real hotkeys, worker absence, current config/instance and freshness. Core proof expires after 60 seconds; UI after 45. Duplicate requests cannot renew it. Continue re-reads health; fixture display results cannot grant it. |
| Exact typed admission | Registered check_setup/restart_core use the shared capsule, validation, policy, priority STOP, verification and factual ledger. A nonserialized exact capsule binding prevents planner/routine output inventing microphone consent or restart authority. Registry has 90 tools; all 73 locked Section 21 names remain unchanged. |
| Recovery 25 | One leased CoreHost retains authenticated IPC while replacing only its own drained graph. PID/creation time stay fixed; graph UUID changes. Exact MEDIUM material approval precedes the non-undoable restart intent. Same-process/new-instance authenticated READY plus actual hotkeys must verify recovery. It never spawns or kills an unverified/dead Core; manual startup is required there. |
| Duplicate prevention | Exclusive profile and endpoint leases are acquired before storage reconciliation. Another profile cannot own the same endpoint. No pre-existing user window/process/profile is terminated. |
| Failure/control mode | Invalid settings, hotkey loss and startup-recovery problems leave a control-only graph with normal actions/setup blocked. Safe settings recovery/read, confirmation, history and STOP remain. Corrupt source is preserved, never overwritten by defaults. Private stale tasks reconcile to ABORTED_BY_CRASH before readiness. |
| STOP / storage / reconnect | Global STOP generation withdraws queued replacement even after intent task completion. Unexpected hotkey loss drains before discarding old queued task references and issuing a new graph identity. All authenticated health handlers enter the existing graph drain gate, preserving storage-last closure. Interrupted terminal readback is reconciled from saved original request/task history after new-Core authentication; restart is never replayed. |
| UI lifecycle and styling | Existing dark resources/palette/dimensions are retained. Critical recovery yields its modal root to the existing material approval and reopens on failure. Navigation keeps shared task ownership; close cancels/joins health, commands, dialogs and existing observers before client disposal. |

The [wire contract](../../PLUMA.UI/PLUMA.UI/docs/wiring_health_setup_recovery.md)
details messages, ownership, deadlines, failure states and freshness. Main source
files are adapters/capabilities.py, tools/health.py, core/host.py,
core/health_contracts.py, app.py and the registry/resident/orchestrator integration;
native UI uses CoreHealthProtocol, HealthController, MainWindow, SetupWizard,
Dashboard and the existing shared command/runtime/settings controllers.

## Required final evidence

Unique ignored root: `output/p22-e104-20261103-233337-bd70b644/`.
Full logs, JUnit, argv, commit/platform records and failed artifacts remain there.
Reports were created with new names; historical evidence was not overwritten.

| Check | Exact evidence/result |
|---|---|
| Final Python prerequisites/affected regressions | `final-718c057/command.json`, `results.xml`, `results.txt`: 1,057 passed, 0 failures/errors/skips/xfails, 78.36 seconds. Includes P01-P13 routing/schema/ownership/Job/STOP/worker/storage/undo, voice, IPC, P17, P21 and 23 P22 cases. The 11 warnings are existing record_property/xunit2 compatibility warnings. |
| Real local capability acceptance | `native-health-ab2e31c.json/.log`: all five actual native probes PASSED, actual hotkeys, setup_ready=true, verified worker absence and cold resident. No audio/screenshot saved. Known existing Qwen GGUF, whisper.cpp base.en and local PP-OCR ONNX files were read only. |
| Exact-source full Windows gate | [Run 41832693148](https://github.com/sai161812/pluma/actions/runs/41832693148), source 864b867: 341 IPC/controller, 237 existing native UI, 12 P22 native UI, 663 popup, 195 formatting, 64,537 layout and 30 surface checks pass; audio/copy gates pass; builds have zero warnings/errors. |
| Native recovery/cleanup | `ci-41832693148/extracted/20261104-125051-d6e34348/p22-health-tests.txt`: actual unavailable models/unconsented microphone keep Continue disabled; three exact approved restarts cover normal/configuration-error/repaired states; same PID/creation-time with new graph UUID, normal actions blocked on invalid config, persisted intent reconciliation and complete joined shutdown all pass. |
| Artifact/build identity | Artifact 13325105224, SHA256 `b3e35ea99e96226b9b7b9a52a809edb886a9bdb56c94b8f290ddea877ad30e71`, matched API digest. Preview executable SHA256 `6CEA7F5A052A7713CE19434F16347CF75188BC8194F0A802FC17AD00591EBBF6`. Native Windows build is unsigned on an execution-authorized test host; no local Application Control bypass. |
| Traceability | verify_requirements_matrix.py passes: 298 source items / 336 traceable rows, unique IDs, full locked requirement text and valid local links. |

Exact Python argv is saved in final-718c057/command.json. It unions the E103
required selection with P22/crash/worker disposal checks. The isolated runner
creates new APPDATA/LOCALAPPDATA/TEMP/TMP, uses `--runxfail`, rejects skips and
loads `-p tests.fixtures.desktop_isolation`; owned fixtures protect personal data.
The native gate runs `./PLUMA.UI/verify-ui.ps1` in the declared GitHub Windows
workflow. Both legacy and P22 invocations are mandatory with unchanged individual
60-second watchdogs/75-second owner budgets and separate retained reports.

Native command (use a new report path each run):
```powershell
$env:PYTHONPATH="$PWD;$PWD/output/p13-native-env/Lib/site-packages;$PWD/output/p14-native-env/Lib/site-packages;$PWD/output/p12-ocr-env/Lib/site-packages"
& D:/Workspace/DEVEL/PLUMA-verified-integration-20261103/output/integration-checks-e98/test-env/Scripts/python.exe tests/windows/p22_native_health_acceptance.py --model output/p13-native/model/Qwen3-4B-Q4_K_M.gguf --speech output/p14-native/ggml-base.en.bin --report <new-unique-report.json>
Remove-Item Env:PYTHONPATH
```
Use the declared Windows environment as the executable so pywin32's .pth support
initializes; adding only its site-packages to another Python was insufficient.
The actual model/speech/OCR environments are existing project environments.

## Retained failures and resolved defects

- Initial local UIA probe environments lacked pywinauto/pywin32 initialization;
  unavailable was truthfully reported. The declared environment's real native
  probe passes. These initial reports are not all-capability passes.
- Initial admission regressions exposed an undeclared capsule field and two
  incorrect test API calls; corrected focused checks pass. They are retained.
- queued-hotkey-repro fails once before the stale queued-reference fix;
  queued-hotkey-fixed passes 74 checks. handler-drain-repro fails once before
  storage/handler ownership repair; handler-drain-fixed passes 77. global-stop-
  repro fails before the generation fence; global-stop-fixed passes 143.
- Windows 41696973673 failed when a stale fixture invoked correctly disabled
  Continue. ca54b31 asserts native refusal and no event without relaxing the gate.
- 41697858809 hit the original whole-suite 60-second watchdog after P22 was
  appended. 99116c9 makes P22 a separate mandatory bounded invocation; no timeout
  was extended, assertion removed or test skipped.
- 41698879574 passed its assertions but exited with native access violation
  during teardown; it remains FAILED. No native stack established its cause and
  no speculative native/UI styling rewrite is claimed as its fix.
- 41700107457 exposed the pending-command readback gap after actual Core
  replacement. 864b867 reconciles persisted identity/outcome without replay;
  its new regression plus the final full native gate pass cleanly, including
  teardown. Earlier failed artifacts/digests remain under their unique ci-* paths.

## Limits, recovery and next step

No remaining P22 implementation packet or required P22 gate is open. Fixture
permission-denial/blocked-worker/crash-record checks are identified as fixtures;
they are not claimed as physical OS denial, real reboot or native power/device
acceptance. Model access does not establish inference/transcription/OCR corpus
accuracy. Full positive capability access is native Python evidence; the native
UI gate uses actual unavailable runtimes and verifies the negative readiness path.
This layered evidence is not represented as a positive device-to-Continue UI run.

E94's owner-approved C-02 physical timing retest stays P25. Physical UI/device
review, installed startup/reboot/recovery, signing/install/uninstall, broad
quality/performance/security and release gates retain their later milestones.
CORE-CONFIG/CORE-FAILURE and other broad rows are not promoted to full completion.
No new waiver or reconstructed historical evidence is introduced.

All meaningful source commits and the recovery branch are normally pushed.
Recovery requires reviewed dependent reverts in reverse order, preserving saved
profiles and unrelated work; an old host must not run concurrently on the same
profile/pipe and E103's configuration caveats remain. No reset/clean/force-push.
Next safe step: independent Sol review of E104; P23 only on owner instruction.
