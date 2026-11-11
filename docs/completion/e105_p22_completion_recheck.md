# E105 - P22 completion verified after bounded edge fixes

P22's documented implementation and required acceptance gate pass after this
recheck. No remaining P22 packet is open. Ready for independent Sol review;
P23 is the next milestone on owner instruction and has not started.
This supersedes E104's completion conclusion for current source while preserving
all historical results and explicitly unverified later gates.

## Scope and identity

Base/recovery: `38825bcd9cee6e27fd29626f2a77d6702cfba044`, pushed as
`recovery/pre-p22-e105-20261104`. Development stays on p12-preparation.
Main remains `0468a031238261bee5bc79bd04b16a3d1964a3a9`; no merge, reset,
clean, force-push, branch switch, dependency change or security bypass.
The complete unchanged master was reused (blob
`01b693dbf898b662aa4cd67736c1a0e8a21cf3e3`); AGENTS, P22/shared contract,
latest handoff, applicable build/acceptance, matrix, E104 and actual source/tests
and Git state were refreshed. Master and approved XAML styling are unchanged.

Pre-edit selection: 78 passed, no skips/xfails. Source review found the four
specific remaining edge cases below; changes stay within P22 health/recovery.

## Gaps closed

| Gap and expected versus actual behavior before repair | Fix and proof |
|---|---|
| Failed startup did not continue an incomplete owned drain: after its budget expired, advance left RECOVERY_ERROR indefinitely rather than finishing cleanup and restoring a usable control graph. | `CoreHost._construct` now schedules retained drain continuation. It creates a fresh control-only graph only after verified closure; leases/storage remain owned meanwhile. The new isolated regression fails at the expected state assertion on base and passes after repair. It uses real private graph/storage and an injected zero cleanup budget, not a physical driver failure. |
| Lost mandatory voice polling owner left READY/hotkeys available while the text/STOP registration owner lived. | Core readiness now checks both actual owners. Loss revokes hotkey/setup readiness and follows existing verified drain/control recovery. The new regression reproduces READY before repair. Native acceptance also stops only its own real voice-polling thread, observes RECOVERY_ERROR with revoked readiness and verifies a new cold HOTKEY_ERROR control graph. |
| Disconnected/failed health cleared setup proof but could leave ordinary command readiness cached. | HealthController revokes command readiness on failed explicit health reads or disconnected/not-ready runtime. Authenticated live runtime can restore it. C# regressions cover failure/reconnect; native acceptance actually stops the owned fixture IPC server and verifies disabled command entry, unavailable restart and joined shutdown. |
| Routine not-ready runtime updates discarded an authenticated configuration-error snapshot and its recovery authority. | Matching verified error identity is preserved for controlled recovery while commands and Continue stay disabled. Disconnect/changed instance/expiry still invalidate it. C# regression checks the exact transition; native UI waits for a subsequent measured runtime readback and verifies that recovery remains enabled without enabling commands. |

Source checkpoints: cebe81b implements retained startup drain, mandatory voice
liveness, disconnected UI readiness and stronger native tests. c8a2510 preserves
verified error-state recovery; 4e63df5 adds its actual native runtime-readback
assertion. The final documentation checkpoint changes no runtime/test source.

## Requirement closure

All P22 prompt requirements were checked against actual source and evidence:
health 23/Dashboard; critical recovery 25; setup 26; no fixture-granted Continue;
actual local model/OCR/STT/UIA/microphone and hotkey access; cold resident startup;
exact owned recovery/authenticated readback; stale-task, denial, missing models,
repeated restart and bad configuration behavior; redacted factual errors;
explicit bounded health updates. Existing typed admission, STOP generation fence,
worker/Job absence, storage-last drain, non-undoable intent and saved outcome
reconciliation remain in place. No confirmation, ownership, cleanup or undo
assertion was weakened. The [wire contract](../../PLUMA.UI/PLUMA.UI/docs/wiring_health_setup_recovery.md)
records the actual ownership, failure, freshness and update mechanisms.

Changed runtime files: pluma/core/host.py and native HealthController.cs.
Changed tests: test_p22_health.py, p22_native_health_acceptance.py, HealthChecks.cs,
health_server.py and NativeP22HealthChecks.cs. Documentation updates cover this
report, current handoff, affected matrix rows, E104's historical status and the
health/setup/recovery wire. No P23 implementation file or visual style changed.

## Fresh acceptance

Unique ignored root: `output/p22-e105-20261104-184859-3b59f9d2/`.
No report was overwritten; full logs/argv/JUnit/source and artifacts remain there.

| Check | Result and exact source |
|---|---|
| Prerequisites | prerequisites/: 78 passed on base 38825bc, no skips/xfails. |
| Reproduction/focused | edge-reproduction/: both new backend cases fail at the expected incorrect state assertions. focused-fixed/: 80 passed after fixes. These pre-commit results use base plus the bounded working diff subsequently committed as cebe81b. |
| Required Python regressions | required-regressions/: **1,059 passed**, zero failures/errors/skips/xfails, 124.28 seconds, source `cebe81b7f15ce5dc1435fa9202521bf6a8b3470f`. Includes 25 P22 cases and the E104 required routing/schema/voice/IPC/STOP/ownership/worker/storage/undo/settings selection. The 11 existing warnings concern record_property/xunit2 compatibility. Python runtime/tests are byte-identical at final 4e63df5. |
| Native local setup and voice loss | native-setup-voice-loss.json/.log: all five real capability checks PASSED, actual registration/polling owners, initial setup_ready=true, verified worker absence and cold resident. The intentional fixture voice-owner stop then revokes readiness and produces a new cold control graph. No audio/screenshot is saved. Exact source cebe81b; this Python runtime/harness is unchanged at final source. |
| First Windows gate | [Run 41837743803](https://github.com/sai161812/pluma/actions/runs/41837743803), cebe81b: 344 IPC, 237 legacy UI, 14 P22 native UI, 663 popup, 195 formatting and remaining gates pass. Artifact SHA256 `3d19cc61a13319580b9838ae86b814935d3358368f58ae097cc62f7cdba1ede7`, matched API digest. |
| Final exact-source Windows gate | [Run 41838806276](https://github.com/sai161812/pluma/actions/runs/41838806276), **4e63df5e28091b0417bc3b843d8b6836dafcaf2a**: **345 IPC/controller, 237 legacy native UI, 15 P22 native UI, 663 popup, 195 formatting, 64,537 layout, 30 surface**, audio/copy gates pass; zero build warnings/errors. Recovery, actual disconnect and joined teardown pass cleanly. |
| Final artifact/build | Artifact 13329055158, SHA256 `3aa560de50aac7704eb01241e51add999ad6fe2ed86b2113b228f0a30787d942`, matched API digest. Preview executable SHA256 `CE10CD8B18EB34D63FF99C178F177288255A976428185FD86E653F724397A447`. Native test builds remain unsigned on an execution-authorized Windows host; local Application Control was not bypassed. |
| Traceability/review | Matrix validator: 298 source items / 336 traceable rows, full unchanged requirement text and valid links. Git diff reviewed for scope, ownership, false success, privacy and styling; unchanged master/XAML confirmed. |

Exact Python argv, platform and JUnit results are in
required-regressions/command.json, results.xml and results.txt. The runner creates
isolated APPDATA/LOCALAPPDATA/TEMP/TMP, enables `--runxfail`, rejects skips and
loads `-p tests.fixtures.desktop_isolation`. Native UI uses private fixture files,
owned hotkeys/windows and authenticated IPC; it never closes personal windows.
The native voice-loss fault touches only its own polling thread.

Commands (choose new unique report paths):
```powershell
& <declared-test-python> <e105-output>/required_regressions.py
$env:PYTHONPATH="$PWD;$PWD/output/p13-native-env/Lib/site-packages;$PWD/output/p14-native-env/Lib/site-packages;$PWD/output/p12-ocr-env/Lib/site-packages"
& D:/Workspace/DEVEL/PLUMA-verified-integration-20261103/output/integration-checks-e98/test-env/Scripts/python.exe tests/windows/p22_native_health_acceptance.py --model output/p13-native/model/Qwen3-4B-Q4_K_M.gguf --speech output/p14-native/ggml-base.en.bin --verify-voice-loss --report <new-report.json>
Remove-Item Env:PYTHONPATH
./PLUMA.UI/verify-ui.ps1
```
The final command runs on the execution-authorized Windows test host via the
existing workflow. Individual 60-second native watchdogs/75-second owner budgets
are unchanged; legacy and P22 invocations remain mandatory with separate reports.
The real model files and existing native environments are read only.

## Limits and next milestone

No remaining P22 implementation/required gate is recorded after this recheck.
This does not establish zero bugs or full-product readiness. E104's prior failed
runs, including the unestablished historical native crash cause, remain retained;
both fresh E105 native runs complete teardown successfully. Fixture-injected
startup budget/permission/stale-record tests are not physical driver/reboot
acceptance. Native positive capability access and negative native UI readiness
remain separate evidence; no positive device-to-Continue UI run is claimed.

E94's owner-approved C-02 timing retest remains P25. Physical UI/device review,
installed startup/reboot/recovery/signing/install/uninstall, broad quality,
performance/security and release retain their later gates. No new waiver,
reconstructed evidence or promotion of broad unverified matrix rows occurs.

Recovery/pre-p22-e105-20261104 and meaningful source checkpoints are normally
pushed. Recover through reviewed dependent reverts while preserving profiles
and unrelated work; no reset/clean/force-push or concurrent hosts on one profile.

P23 prerequisites are satisfied for the next owner-authorized milestone, subject
to independent Sol review (ready, not approved). Its first safe packet is typed
readback of actual task-owned target capture/match facts before binding existing
surfaces 15/16. Preserve target identity/geometry/DPI/TTL/STOP and transient image
bytes. No P23 code, automatic advance or main merge occurred.
