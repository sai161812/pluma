# E91: P18 live state and combined shell acceptance

Date: 2026-11-01. Recovery checkpoint: `f73bcdc5e5c9ca4f015304cc2e6e65a00d4bf58f`.
**P18's scoped implementation and acceptance gate is complete.** This closes
requested groups 2–4 and follows E90's result/policy-reason packet. Final source:
`b60bdeafd13a2ec6df5eb10777725886470deaa7`. Compilation alone was not acceptance.

## Behavior and ownership

- Surfaces 4/5/7 use a capsule-owned, standard-library presentation mirror:
  validated plan revision and selected step, actual dispatch/worker entry,
  verification and recording phases, redacted UTF-8-bounded arguments and
  measured elapsed time. Dispatch never implies executor entry. Nested tool
  completion restores only a still-owned parent. STOP admission is unchanged.
- Surface 9 shows the actual selected inverse and current inverse count.
  Progress stays indeterminate: a selected inverse is not a completed restore.
  Saved rollback/cleanup and independent file readback establish the outcome.
- New strict read-only `runtime_query` and `action_verification_query` contracts
  leave E88/E90 wire records intact. A busy, contradictory or malformed read
  fails closed. Snapshot disappearance dismisses a view without claiming success.
- Surface 17 requires exact task/request/action/tool scope and actual saved
  verifier proof. Missing proof is unavailable; contradictory proof prevents
  batch publication. Surface 21 requires verified `WORKER_ABSENCE_VERIFIED`,
  PLUMA ownership, exact task/PID/creation time, tool-worker class and observed
  exit code. Resource release alone cannot produce this notification.
- A reproduced IPC STOP race checked a cooperative owned tool future before
  its cancellation wakeup completed, permanently deferring a safe inverse.
  Cleanup now gives only tool futures one shared 100 ms drain budget after
  the latch; unknown work remains owned and blocks rollback. Planner/shutdown
  pending-worker evidence is preserved. The new regression fails before the
  fix; shutdown and STOP regressions pass after it.
- Combined acceptance also reproduced a Windows console-startup stall before
  executor entry in a redirected/headless host. The scoped Windows worker
  adapter now uses CREATE_NO_WINDOW with the ordinary spawn bootstrap,
  original process handles and unchanged Job/admission boundaries. It does
  not patch global multiprocessing or Win32 functions. Temporary diagnostics
  were removed. Actual redirected-host process entry, STOP/absence, inverse
  selection, owned-file restoration and separate WAL readback pass.
- One shell-owned, cancellable observer performs bounded runtime readback every
  250 ms, with a 3-second per-read budget. Widgets own no loops. Connection
  health/latency reports that readback only, not model/device/capability health.
  Active tasks and termination DTOs are bounded to 256; notification dedup and
  terminal fences to 512; the factual live-message panel to 200 entries.
- Initial termination history seeds silently; reconnect/replay retains stable
  identity deduplication. Runtime views cannot reopen a task already observed
  terminal. Navigation restores shell-owned facts without another submission.
  The bounded message projection includes saved redacted executor copy with
  its separate verification/error status and committed action-event timestamp,
  followed by the task outcome. Query IDs cannot replay unchanged messages.
- Live rendering admits at most 32 shared-host entries and processes at most
  12 updates per frame, rotating fairly. Ordinary notifications leave one of
  the 48 host slots reserved for STOP. Capacity refusal does not fabricate
  display/success or build an unbounded queue; feed/history remain authoritative.
  Existing reading holds, sizing, ordering, native layout readiness, dark
  resources, motion and dismissal remain in the shared host.
- Shell close cancels/drains its observers and owned popup windows/timer. It
  does not implicitly cancel an admitted backend task.

## Changes

Backend: `live_presentation.py`, `worker_process.py`, supervisor, FAST/SMART orchestrators, registry
entry evidence, rollback selection, scoped Activity query and resident/v1 DTOs.
UI: typed runtime/verification client, owned observer, deterministic surface
mapping, existing 4/5/7/9/17/21 controls, dashboard feed/health and MainWindow.
Tests: `test_p18_runtime.py`, importable owned worker fixture, C# runtime checks,
native event/readback checks and actual whole-shell acceptance.

Verifier projection includes the exact registered screen mutators and the
existing `click_ocr_text` / `type_into_element` compatibility tools. Functional
consumer regressions require their exact saved scoped proof before surface 17.

The legacy clipboard routing unit test now uses an inert owned dictionary and
isolated ledger. It tests routing to canonical `clipboard_clear` and never
touches the personal clipboard. It is not native clipboard evidence.

## Verification

Fresh pre-edit isolated P18 detail/activity/STOP prerequisites: **81 passed in
3.33 s**. Final affected Python: **341 passed in 75.47 s**, no skips/xfails:

```powershell
output/p16-windows-env/Scripts/python.exe -m pytest -q tests/unit/test_p18_runtime.py tests/unit/test_executor_admission.py tests/unit/test_worker_cancellation.py tests/unit/test_worker_disposal_cause.py tests/unit/test_fast_orchestrator.py tests/unit/test_multi_step_orchestrator.py tests/unit/test_rollback_engine.py tests/unit/test_stop_protocol.py tests/unit/test_p18_action_details.py tests/unit/test_p18_activity_query.py tests/unit/test_ipc_request_contract.py tests/unit/test_runtime_shutdown.py
```

`LOCALAPPDATA`, `APPDATA` and `PLUMA_CONFIG` point to owned ignored storage under
the directory recorded by `output/p18-runtime-current.txt`. Actual spawned
worker entry, priority STOP, identity-bound absence and real owned-file inverse
readback pass; synthetic malformed/unowned proof cases are explicitly fixtures.

Local CoreIpc.Tests, SurfaceControls.Tests and production app builds pass with
zero warnings/errors; `check-surface-copy.ps1` passes 33 compiled XAML files.
The local Application Control executable restriction is respected: no alternate
loading route or security bypass. Native execution uses the authorized hosted
Windows workflow.

After the console-free worker correction, the final affected worker/admission/
shutdown/STOP/rollback suite, including the actual headless-host regression,
passed **178 checks in 32.37 s**, without skips/xfails. Command:

```powershell
output/p16-windows-env/Scripts/python.exe -m pytest -q tests/unit/test_p18_runtime.py tests/unit/test_executor_admission.py tests/unit/test_worker_cancellation.py tests/unit/test_worker_disposal_cause.py tests/unit/test_runtime_shutdown.py tests/unit/test_stop_protocol.py tests/unit/test_rollback_engine.py
```

The new regression
launches an owned, redirected, no-console Python fixture and observes real
process entry and inverse/terminal readback through authenticated IPC. The
earlier standalone startup timeouts and failed/superseded hosted runs are
reproductions, not passes.

Exact-source native gate:
[Windows run 41335025620](https://github.com/sai161812/pluma/actions/runs/41335025620)
passed `./PLUMA.UI/verify-ui.ps1` on Windows NT 10.0.26100, Python 3.12.10:

| Check | Result |
| --- | --- |
| Strict C# IPC/observer/readback/compatibility projection | 215 passed |
| Actual native controls and whole-shell/backend acceptance | 160 passed |
| Shared native popup placement, motion, reading and ownership | 663 passed |
| Native gallery formatting | 195 passed |
| Display/queue layout | 64,537 passed across 5,000 scenarios |
| Surface contracts | 30 passed |
| Audio visualizer (no device capture) | all checks passed |
| UI and control builds | zero warnings/errors |

Artifact `13095272096`, SHA-256
`43cdf6f15f262d4e23e57414430e56e3fdb7adb2acbd4e089d95eaccd7ba49af`, was
downloaded and its summary/control logs inspected under ignored
`output/p18-final-native/20261101-180850-7e9e4466/`.
Tested gallery-preview executable SHA-256:
`0A47CD11DD738FC9E8D977B3C4A1C90B96A5EC1E70F259C4F01647E0DF2DB1BF`.
It is unsigned and was executed only on the authorized hosted test host, not by
bypassing local policy. The native control executable instantiates the actual
production MainWindow with owned IPC options; this is not an installed release
package or personal-device acceptance.

Earlier successful run 41334556672 covered source `9dd6535` before compatibility
mapping coverage. Final-source acceptance is the run above; failed and cancelled
runs are not passes. Native fixture timing corrections await actual readback/
layout, fill the observed host count after retirement, and accumulate a delivery
burst within the existing four-running-task limit. They do not weaken production
admission, silently retry actions or skip assertions. Traceability and the
33-XAML copy scan also pass. Test/evidence differences from the final source
are documentation only after this checkpoint.

## Acceptance boundaries

The combined test instantiates actual MainWindow, production typed authenticated
transport, registry/orchestration/verification/WAL and native shared popup host.
It checks actual live task/step/tool cards, replacement HWND stability, navigation,
capacity/STOP, owned process termination, a real owned-file inverse, result/
verification/denial bursts, reconnect/replay and whole-shell shutdown with active
backend work. All paths/keys/processes are newly owned fixtures. The rollback
fixture adds bounded inverse latency so actual selection is observable; it still
runs the production file inverse and reads the restored file. The `invoke_control`
projection fixture is an inert owned-file tool with a real verifier, not native
UIA or personal-window acceptance. No audio, personal clipboard, browser profile,
power state or personal files are changed.

P25 physical Windows taskbar/DPI/accessibility/owner appearance acceptance and
P22 extended health/capability work remain their own milestones. P18 does not
claim full-product readiness or independent Sol approval. P19 has not started.
No P18 items remain open. The next safe step is independent Sol review of E91;
P19 requires the owner's next instruction. No merge is authorized by this packet.
Recovery is via a reviewed revert of this packet's commits, preserving unrelated
work; never reset, clean or force-push.
