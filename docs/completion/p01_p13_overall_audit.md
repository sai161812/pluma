# E73 — Overall P01–P13 audit

2026-10-26, Asia/Calcutta. Source checkpoint:
`a9f77da9a6263ab6c019e7ca17795e54d8444ae3` on `p12-preparation`.
Recovery point: `ce25d711adba0ab4c9bbc13b03c47f0da7d38093`.

The audit found and repaired three source defects. The final local P01–P13
regression selections pass without skips or expected failures. Fresh Windows CI
interoperability also passes on the repaired source commit. P14 is eligible for
its next bounded packet; it has not started.

## Defects reproduced and repaired

| Finding | Repair and proof |
|---|---|
| A successful retired capsule could execute another thread tool | `CancellationToken.raise_if_cancelled` refuses retired tokens before policy/submission and at executor entry. The new inert registry regression failed before repair and now proves no callable starts or owned branch appears. |
| Retiring a successful native task lost its native admission fence | Snapshot the canonical native latch before closing its event handle. Existing success/failure/crash attribution tests now retain the fence without inventing a user STOP reason. |
| Planner `purpose` text was written to the application log | Execution logs now contain deterministic tool/step facts. The ledger regression also captures logs and proves the private reasoning marker is absent from both; it failed before repair. |

The first prerequisite run produced **436 passes / 6 failures**. The first
catalog run produced **1,248 passes / 34 failures**. Most failures were old
assertions reading `multiprocessing.Process.is_alive()` after P13 deliberately
closed its handle, reading a retired gate, or clearing a permanently completed
signal. Tests now independently read back absence by the original PID/creation
identity, assert handle closure, retain latch-order assertions, and inject a new
unpublished terminal signal. No test was deleted, skipped or relabeled as passed.

A later catalog run produced **1,281 passes / 1 failure**: a process-control
test raced journal visibility against executor admission. The hidden owned
Win32 fixture now acknowledges receiving `WM_CLOSE`; the test waits for that
native dispatch boundary before STOP. Its non-undoable residual, unrelated
target survival and journal assertions remain. The final full catalog passes.
Baseline/failure logs are retained under ignored `output/p01-p13-audit/`.

## Milestone reconciliation

| Milestone | Implementation and acceptance inspected |
|---|---|
| P01 | Registry schema-before-policy and worker/thread admission; pre-state, queued and spawn STOP races; retired-task refusal. |
| P02 | Supervisor latch-all before cleanup, simultaneous STOP and request publication; original native gate ordering retained. |
| P03 | Worker pipe/controller cancellation, bounded waits, original process handles and Job containment. |
| P04 | Worker/descendant absence, retained failed ownership, temporary-resource identity and rollback residual evidence. |
| P05 | Authoritative memory/result/SQLite/IPC terminal state, late STOP, non-undoable effects and persistence failures. |
| P06 | Intake rejection, handler/worker drain, resumable bounded shutdown and storage-last closure. |
| P07 | Same-capsule voice capture/empty/failed/denied/STOP lifecycle; inert devices as required by P07. Real voice remains P14. |
| P08 | Typed latch acknowledgment, pending cleanup, terminal/residual/error receipts and authenticated native pipe integration. |
| P09 | Atomic private Windows credentials, opened-handle ACL/owner checks, corruption/denial/races and Python/C# compatibility. |
| P10 | Real owned Windows worker/descendant STOP, unchanged unrelated fixture, safe rollback/conflicts, SQLite receipts and runtime closure. |
| P11 | All 57 non-screen catalog names, schema/policy/dispatch, pre-state, postconditions, native identity and guarded inverses. Focus/audio physical deferral remains. |
| P12 | All 16 exact screen names; E-01–E-10 guards, target-scoped capture, UIA before OCR, TTL/process/geometry/DPI checks, native Win32/WPF and generated-image OCR. |
| P13 | FAST bypass; route whitelist/replans; configured plan bound; malformed/invented output refusal; target admission; real llama.cpp STOP/timeout/crash, multi-step/replan, privacy, cleanup and ledger readback. |

All **73 required section-21 names** are present in the **85-tool registry**.
Each required ToolSpec was revalidated for its typed contract, positive bounded
timeout, callable verifier/executor and declared dispatcher order. This
inventory supplements the behavior tests and does not substitute for them.
The P11 dispatcher, elevated identity-failure cleanup and independent DNS cache
readback fixes remain wired in production and covered by current regressions.

## Final checks

Windows 11 build 26200; Python 3.12.10; pytest 8.3.3. Storage suites isolate
APPDATA/LOCALAPPDATA/TEMP/TMP. FAST orchestration uses the documented inert
desktop plugin; native windows/browser/process/file tests use owned fixtures.

| Check | Result |
|---|---|
| P01–P10 prerequisites, all 15 original BA assertions included | **443 passed**, no failure/error/skip |
| P11 catalog/policy/verification/undo | **1,282 passed**, no failure/error/skip |
| Routing/FAST/planner contracts | **329 passed**, no failure/error/skip |
| P12 regression | **233 passed**, no failure/error/skip |
| Actual native Win32/WPF acceptance | **10 passed**, no failure/error/skip |
| Additional P13 adapter/target/replan modules | **16 passed**, no failure/error/skip |
| Clipboard fresh-logon regression | **294 passed in 93.57s**; inner/outer exit zero; no remaining owned process; personal clipboard sequence unchanged |
| Actual Qwen3-4B llama.cpp acceptance | STOP/timeout/crash, native multi-step, one recovery replan, secret/history checks and cold cleanup passed |
| Actual model invented-tool proposal | Rejected before execution; FAILED ledger and worker-absence readback passed |
| Actual ONNX OCR generated-image sample | **288/288 lines**, 36 cases, valid bounds, minimum confidence **0.9386066198**; optional environment `pip check` passed |
| Fresh Python/C# IPC rerun | **39 passed** in [Windows CI run 40289004034](https://github.com/sai161812/pluma/actions/runs/40289004034) on the repaired source commit; local blocked attempt is not counted as a pass |

Counts overlap; they are not a sum of unique tests. Fixtures, actual model
inference and physical device evidence are explicitly distinguished. No skip,
xfail or unavailable check is counted as a pass. Focused repaired checks also
passed in 8-case, 42-case and 3-case runs; original failing outputs are retained.

The matrix checker passes **298 source items / 324 traceable rows**. All 278
production/test Python file hashes in the final catalog snapshot match the
working files at the source checkpoint. Changed files and the reproducible
audit runner compile; the runner's P13 selection also passes all 16 checks.
`git diff --check` passes. The immutable master and approved visual source were
not changed. Historical audit headers and stale defect labels are reconciled
with this checkpoint without deleting their earlier evidence.

### Reproduce the selections

[The audit runner](run_p01_p13_checks.py) reuses the exact checked-in
[P12 selection manifest](p12_check_manifest.json), adding the three P13 modules
not covered by the other selections. It isolates storage, bounds each suite to
900 seconds, runs original xfails as assertions and fails on any skip. Each run
records its expanded command, actual exit/JUnit summary and source SHA-256 map.

Local `dotnet run --project PLUMA.UI/CoreIpc.Tests/CoreIpc.Tests.csproj
--verbosity quiet -p:UseSharedCompilation=false`, with `PLUMA_TEST_PYTHON`
pointing to the isolated interpreter, was blocked before execution by Windows
Application Control (`0x800711C7`). IPC boundary sources match their previously
verified revision. The existing `ui-verification.yml` was then dispatched on
`p12-preparation`, exact head `a9f77da9a6263ab6c019e7ca17795e54d8444ae3`.
The successful Windows CI report independently records 39 IPC checks, 663
native popup checks, 195 formatting checks and 42 control checks. These native
UI fixtures are not physical taskbar/accessibility acceptance. The downloaded
artifact SHA-256 is
`42a81fc307993f02c21dc3d86ed581c13b1e4680aae10e11cefbcde3eed70ad7`;
full ZIP and verification summary are retained in the ignored audit directory.
No Windows security policy was changed.

```powershell
foreach ($auditSuite in @('prerequisites','catalog','contracts','p12','native','p13')) {
  & output\p11-native-env\Scripts\python.exe docs/completion/run_p01_p13_checks.py $auditSuite
  if ($LASTEXITCODE -ne 0) { break }
}
output\p11-native-env\Scripts\python.exe -m tests.fixtures.clipboard_logon clipboard-regression-p01-p13-e73
output\p12-ocr-env\Scripts\python.exe tests/quality/check_p12_ocr_quality.py
output\p12-ocr-env\Scripts\python.exe -m pip check
output\p13-native-env\Scripts\python.exe tests/windows/p13_native_runtime_acceptance.py --model output/p13-native/model/Qwen3-4B-Q4_K_M.gguf --cycles 1 --report output/p01-p13-audit/native-planner.json
output\p13-native-env\Scripts\python.exe tests/windows/p13_native_runtime_acceptance.py --model output/p13-native/model/Qwen3-4B-Q4_K_M.gguf --cycles 0 --skip-stop --unregistered-tool-only --report output/p01-p13-audit/native-invented-tool.json
```

Use a fresh `clipboard-regression-` evidence label for another clipboard run;
its wrapper correctly refuses stale evidence. Model identity/version remains
E72's Qwen3-4B Q4_K_M SHA-256
`7485FE6F11AF29433BC51CAB58009521F205840F5B4AE3A32FA7F92E8534FDF5`,
llama-cpp-python 0.3.36. Fresh native results ended COLD with no model in the
resident-side process, zero children and no handle growth. E72's 50-cycle and
600.6-second idle reports remain historical measured evidence; they were not
repeated or represented as fresh measurements in this audit.

Changed production hashes at the tested source checkpoint:

- `pluma/core/cancellation.py`:
  `183516110E06270D8C433D979DD2C14423A09F679100D842C4DC83E8911C932F`
- `pluma/core/multi_step.py`:
  `22C5E2B0F258E2942210F040A803669340980AC07EB947C1C61D615E43BB933A`

Full suite logs/XML/JSON, inventory and native-model reports are ignored under
`output/p01-p13-audit/`. Clipboard evidence remains under ignored
`output/p11_power_actions/clipboard-regression-p01-p13-e73*`.

## Preserved deferrals and P14 readiness

No deleted test was restored; existing deferred selections and skip/xfail
markers were not changed. Live foreground focus/audio changes retain the
owner's explicit final-validation deferral. Disruptive power tests and a new
UAC/DNS mutation were not invoked; their policy/intent/refusal/cleanup tests ran,
and prior native DNS evidence remains E59. Physical taskbar/DPI/accessibility,
full application/model quality corpora, resource/latency budgets, OCR lifecycle
measurement, install/release and adversarial product-wide acceptance retain
their documented later owners. This audit is not full-product release approval.

No unresolved implementation failure remains in the audited P01–P13 scope.
The next eligible implementation is P14, only when instructed. Its first safe
bounded packet is C-08/B-04: verify a real whisper.cpp
transcription worker under the existing task/cancellation owner, correct the
runtime STT unload/model configuration wiring, and prove STOP/timeout worker
absence with fixture audio and ledger readback. Microphone/VAD, confidence and
voice/text parity follow within P14. No P14 implementation was started here.
