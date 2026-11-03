# P12 implementation audit and closure (E69)

Checkpoint: 2026-10-26, Asia/Calcutta. This supersedes the overall completion
claims in E68; E68 remains evidence for its successful WPF inspection test.

## Scope and outcome

P12 implements the semantic-screen and targeted-OCR work packet in
`PLUMA_COMPLETION_PROMPTS.md`: E-01 through E-10 and all 16 Section 21
screen-control names. The initial implementation audit reproduced three
failures with inert adapters. This checkpoint repairs those failures and the
related production paths found during the wider review. P13 is not implemented
or started by this checkpoint.

Implementation commit: `a53940794873acc143ca2b0e3ba876b651a1d52d`.
Final test-fixture commit: `a30a80ffe4c56bfe31e3f5e95b40d5d2cb9569b4`.
Final verification runs use the latter source head. Documentation commits do
not change the tested Python implementation.

Recovery point before this audit: `5c3e9414fdc421a5011047594978a209ab2a490c`.

## Repairs and review findings

| Finding | Resulting behavior and evidence |
|---|---|
| Foreground/TTL/process drift during UIA lookup or focus could reach global input | Tools re-resolve their task snapshot and re-read target identity, geometry and DPI immediately before mutation, including after focus. Focus itself requires UIA keyboard-focus readback. Guard tests inject foreground, expiry, process, geometry and DPI changes and assert no input. |
| Rejected input or an already-present postcondition could become verified success | Incomplete `SendInput` submissions raise failure. Keys/modifiers are released with bounded cleanup attempts, including partial Unicode/mouse input. Already-present postconditions are refused before dispatch. A successful action requires the requested state change to be read back. |
| UIA permission/provider errors could become verified empty inspections | Missing dependencies, access denial, provider failure and invalid HWNDs produce failures. Child enumeration errors do not silently produce a partial successful tree. Empty successful trees represent completed observations with no controls. |
| Compatibility aliases had weaker execution/undo boundaries | All three legacy inspection/semantic aliases require owned process isolation. Click aliases use HIGH policy and non-undoable intent journals. The text alias uses the catalog's private pre-state, UIA Value pattern, exact readback and guarded undo. Registry tests verify policy cannot be bypassed. |
| UIA adapters could silently inject coordinates or key syntax | Invoke/Value patterns are used directly. Unsupported patterns refuse; there is no `click_input`/`type_keys` fallback inside the semantic adapter. Literal braces and shortcut-like text remain literal text. Native UIA password classification uses `CurrentIsPassword`. |
| OCR could bypass available UIA or accept a partial/uncertain label | Fresh semantic inspection precedes OCR actions. An available UIA target must use its semantic reference. OCR action labels match exactly, require confidence at least 0.90, and refuse duplicates. Planner arguments cannot lower the confidence floor. |
| Failed native capture could become a valid-looking blank bitmap | Target-window DC/allocation/pixel-copy/read failures now fail. A complete bitmap read is required; no synthetic image substitutes for failed target capture. Resources are released on failure. |
| OCR without an explicit snapshot could outlive its pixel observation | Such calls enforce the same three-second observation age before input. Process creation identity, window title/class, full geometry and DPI are checked again. Changed observations fail rather than guessing coordinates. |
| SCREEN/DEEP initial context bypassed registered execution; DEEP eagerly started OCR | Both routes now use registered, process-owned `inspect_window_controls`. The snapshot is registered to the capsule before planning. Failed/denied inspection prevents planning; OCR stays cold until a later explicit target-scoped tool needs it. Route tests prove the planner can resolve its supplied snapshot from the same task registry. |

`tests/unit/test_p12_completion_guards.py` contains the new failure regressions.
The existing screen/dispatch/rollback suites remain part of final verification.
Native tests additionally exercise real UIA Value readback and private undo on
an owned Win32 Edit control, and prove that a real Submit control prevents OCR.

## E-01 through E-10 evidence

| Gate | Evidence |
|---|---|
| E-01 | Current native Win32 and WPF UIA semantic inspection passes. |
| E-02 | Native Submit invocation uses UIA Invoke and independently reads the resulting enabled/status state; OCR is forbidden in that fixture. |
| E-03 | Duplicate semantic and exact OCR labels are refused before mutation. |
| E-04 | Changed HWND/process/creation identity and changes during lookup/focus are refused before input. |
| E-05 | Geometry and DPI are freshly checked. Owned-window movement during OCR and injected small DPI drift refuse input. No display setting is changed. |
| E-06 | Only the requested HWND/region is captured. The native crop fixture verifies the actual 160x100 in-memory bitmap dimensions. |
| E-07 | OCR actions recheck freshness and target identity and require target-specific transition readback; unrelated text changes or OCR exceptions do not establish success. Keyboard postconditions must also change from their pre-state. |
| E-08 | Textless/inaccessible targets and unsupported semantic patterns refuse without guessed input. Permission errors remain factual failures. |
| E-09 | Captures remain in memory. No image bytes/image references are published to the ledger; no default image-save API is used. |
| E-10 | Real owned-process STOP checks cover blocked OCR and a blocked UIA wait provider: the worker is absent after STOP and no late action marker is created. |

The native suites bind production context reads to exact owned HWNDs because
this session has no usable foreground window. They use real Win32/UIA/WPF
providers and close only their owned fixtures. Their harmless fixture-button
operations use local test specs; production HIGH policy/intent and process
containment are independently verified. They do not claim physical foreground
focus, user-device, secure-desktop or UAC acceptance. Those broader release
checks retain their existing owners and approved P11 limitation.

The OCR-transition/native-crop and STOP tests inject explicit OCR/provider
behavior. Actual OCR model recognition is verified separately below. Neither
injected OCR output nor a native bitmap capture is presented as model accuracy.

## OCR accuracy and runtime

The locked `PP-OCRv6_small_det`/`PP-OCRv6_small_rec` models still run through
ONNX Runtime CPU on demand. The input decoder now supplies BGR arrays, matching
the installed PaddleX ndarray reader. Runtime/model imports remain cold until
needed. Models live outside Git in the existing user PaddleX cache.

The reproducible quality command is:

```powershell
& .\output\p12-ocr-env\Scripts\python.exe tests/quality/check_p12_ocr_quality.py
```

It generates 36 images in memory: Segoe UI and Arial, 12/16/22 pixel base fonts,
light/dark themes, colored text, and 100%/125%/150% rendered scales. Eight labels
per image include filenames, a shortcut chord, decimal punctuation and numbers.
Every expected line must match exactly, every box must lie inside its input,
and every recognized line must clear the 0.90 action confidence floor.

Final result: **288/288 exact lines**, valid bounds, minimum confidence
**0.9386066198**; the 36 inference calls took **16.23 seconds** in that run.
This is a bounded correctness sample, not a guarantee of universal OCR accuracy.

An earlier controlled comparison on 72 simpler lines compared RGB/BGR input
and detector minimum-side settings 64/256/736. Each recovered 72/72 lines;
736 did not improve the score and took 9.14 seconds versus 2.10 seconds for BGR
64 across that sample. No accuracy reduction was accepted to gain speed. The
default small-model path is retained with corrected channel order and stricter
action matching. See the official [PaddleOCR pipeline documentation](https://github.com/PaddlePaddle/PaddleOCR/blob/main/docs/version3.x/pipeline_usage/OCR.en.md)
for the supported detector settings.

The rendered-scale sample does not change Windows display scaling. P26 still
owns the full fixed application corpus, physical scaling, multilingual/edge
cases, p50/p95 latency and hardware measurements. A 0.90 confidence score is a
refusal threshold, not a calibrated probability or a claim of 90% accuracy.

## Final checks

Environment: Windows 11 build 26200; Python 3.12.10; pytest 8.3.3;
pywinauto 0.6.9. Optional OCR runtime: PaddleOCR 3.7.0, PaddleX 3.7.2,
ONNX Runtime 1.31.0. All fresh test reports are under ignored
`output/p12-verified/`; the earlier probes/failures remain under
`output/p12-audit/`.

[The check manifest](p12_check_manifest.json) preserves every suite's exact
pytest selection and arguments. The ignored runner executes these arguments
with isolated APPDATA/LOCALAPPDATA/TEMP/TMP, bounded subprocess timeouts,
`--runxfail`, thread-exception failures, xunit1 reports, source hashes and a
nonzero exit for any skip. Commands used for final verification:

```powershell
& .\output\p11-native-env\Scripts\python.exe output/p12-verified/run_manifest.py prerequisites
& .\output\p11-native-env\Scripts\python.exe output/p12-verified/run_manifest.py catalog
& .\output\p11-native-env\Scripts\python.exe output/p12-verified/run_manifest.py contracts
& .\output\p11-native-env\Scripts\python.exe output/p12-verified/run_manifest.py p12
& .\output\p11-native-env\Scripts\python.exe output/p12-verified/run_manifest.py native
& .\output\p12-ocr-env\Scripts\python.exe tests/quality/check_p12_ocr_quality.py
& .\output\p12-ocr-env\Scripts\python.exe -m pip check
& .\output\p11-native-env\Scripts\python.exe docs/completion/verify_requirements_matrix.py
git diff --check
```

| Check | Result |
|---|---|
| Safety/lifecycle prerequisites | **435 passed in 36.07s; zero failures/errors/skips** |
| Catalog/rollback/policy regression | **1276 passed in 252.12s; zero failures/errors/skips** |
| Routing/contracts | **319 passed in 27.58s; zero failures/errors/skips** |
| P12 regression and new guards | **233 passed in 25.77s; zero failures/errors/skips** |
| Native Win32/WPF acceptance | **10 passed in 8.50s; zero failures/errors/skips** |
| Real generated-image OCR quality | 288/288 exact lines; valid bounds; minimum confidence 0.9386066198 |
| Optional runtime dependency check and cold imports | `pip check` passed; OCR manager COLD; PaddleOCR/ONNX/LLM libraries unloaded on import |
| Compilation, matrix and diff validation | Python compilation passed; matrix 298 source items / 324 rows passed; git diff --check passed |

Counts overlap between suites and are not a count of unique tests. No passing
test, skip or xfail is substituted for the original failing probes. Earlier
integration fixtures were updated for the registered observation path without
removing their terminal-state assertions. One app-launch cleanup test raced
asynchronous Windows process exit; it now uses the existing 300 ms bounded
wait on the same PID/creation identity. Its full 16-test module passed after
the fixture correction; no production app-launch logic was changed.

The full repository release suite is not claimed by this checkpoint. The older
cross-phase release-audit cases described in E67 and the P11 owner-approved
physical-effects limitation remain visible in their records. P12's applicable
acceptance checks are separately enumerated above.

## Next safe milestone

P12 has no remaining implementation or E-01 through E-10 blocker. Do not
start P13 or merge automatically.

A read-only forward P13 baseline ran its planner/lifecycle/schema suites:
**65 passed, 1 failed, zero skips**. The failure is an existing P13 tool-subset
bug: the file command `Find report.pdf in downloads and move it to archive`
matches the browser keyword `download`, offers only browser tools, and rejects
the proposed `find_file`. The validator correctly refuses the unpermitted
tool. No P13 production code was changed or weaker validation introduced.

The first bounded P13 task is to correct and verify file-versus-browser tool
subset selection for Downloads paths while retaining explicit browser-download
requests. Then continue the P13 prompt's owned inference, schema-constrained
generation and real local llama.cpp checks. The existing schema-only fallback
and inference worker boundaries require that milestone's review; mock plans
are not real-model acceptance.

## Tested source hashes

SHA256 values for the final implementation/test-fixture head:

| File | SHA256 |
|---|---|
| `pluma/adapters/input.py` | `aa755ddc19776d1942f864f2593633785fe9469a341ec9cc009a7d8b9ac60b5d` |
| `pluma/adapters/screen.py` | `505080732a3c0876bc0203048d23256f4ee158a59f63ecf1c0861016ff18d586` |
| `pluma/adapters/uia.py` | `795d93d8ae7a64e09001f6fca148c99903d90c538c51ec7a83ffb22f29bc3515` |
| `pluma/core/orchestrator.py` | `fa39741618fff6f78278b13e30c49981cffdc553f99f95c560ae5e8c4a37d754` |
| `pluma/perception/ocr_adapter.py` | `a2c589a6bb7de5de74422cbc2a612b41596f69c53b742e227873a995043f5c99` |
| `pluma/perception/uia_snapshot.py` | `7577e30a8277f8893c253746ac8ade5944ab6e822108327b2e079fc7530da5fe` |
| `pluma/tools/registry.py` | `2d32f4e8e85d0892f653d43cd8426a2baba313e5b10d6dfb9c9c141c84b9cfc2` |
| `pluma/tools/screen_catalog.py` | `0fa76461b2d31f34c71e648bf37c7b2b6dd9bd25abf1e62da3ac23acbc6f631b` |
| `pluma/tools/ui.py` | `d5716fd60ebb401101ef69dc601df935a8148bf31e05b6d8d27734dc0412cdb0` |
| `tests/quality/check_p12_ocr_quality.py` | `c48893d4301486b4802700b2938c5323364d674d241bce592a283d6db2535f21` |
