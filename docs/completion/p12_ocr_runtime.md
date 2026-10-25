# P12 production OCR runtime (E67)

## Outcome

The production OCR adapter now uses the locked local PaddleOCR/ONNX Runtime
path on demand. It selects `PP-OCRv6_small_det` and `PP-OCRv6_small_rec`,
requires ONNX Runtime's CPU provider, and converts PaddleOCR 3.x text, confidence
and polygon/box output into bounded `OcrWord` values. The optional dependencies
are exposed as `pluma[ocr]`; the base resident install remains free of OCR
imports and packages.

`CORE-OCR` is implemented for P12. A real adapter smoke recognized all four
expected UI-like labels on one generated 1000x300 image, with valid bounds and
confidence scores. This is a runtime sanity/accuracy sample, not the P26 fixed
quality corpus or a multi-scale accuracy/latency benchmark.

## Implementation

- `pluma/perception/ocr_adapter.py` imports ONNX Runtime and PaddleOCR only in
  `load()`. It refuses to load without `CPUExecutionProvider`, explicitly sets
  the ONNX engine and CPU provider, and disables document orientation,
  unwarping and textline orientation. There is no implicit PaddlePaddle/GPU
  fallback.
- Recognition uses PaddleOCR 3.x `predict()` and reads its structured `json`
  result (`rec_texts`, `rec_scores`, `rec_polys`, with `rec_boxes` as the
  rectangle fallback). Misaligned arrays, invalid confidence or invalid
  coordinates fail instead of becoming an empty/partial success.
- Image bytes are decoded from `BytesIO`, passed to inference as an in-memory
  RGB array, and never passed to a result-save API.
- `pyproject.toml` adds a separately installable, pinned `ocr` extra. The
  default dependency set and `all` extra remain lightweight; `README.md`
  documents the optional install command.

## Verification

Baseline: clean `p12-preparation` at `971ca59f01d89533a4645b112b601254d0246c1a`,
equal to `origin/p12-preparation`. Implementation was committed and tested at
`412e0d7bd9a436d7594db36c44a01894f6ff5c08`. Windows 11 build 26200, Python
3.12.10.

Exact verification commands:

```powershell
& .\output\p11-native-env\Scripts\python.exe -m pytest tests/unit/test_perception_ocr_adapter.py -q
& .\output\p11-native-env\Scripts\python.exe -m pytest tests/unit/test_tools_ui.py tests/unit/test_verify_screen.py tests/unit/test_tool_adapter_dispatch.py tests/unit/test_perception_uia_snapshot.py tests/unit/test_perception_context.py tests/unit/test_perception_freshness.py tests/unit/test_adapters_win32.py tests/unit/test_window_geometry_native.py tests/unit/test_perception_ocr_adapter.py tests/unit/test_ocr_grounding_integration.py tests/unit/test_perception_capture.py tests/unit/test_perception_ocr_lifecycle.py tests/unit/test_phase13_7_ocr_grounding.py tests/unit/test_phase13_5_regression.py tests/unit/test_phase13_8_final_patch.py tests/unit/test_phase13_5_stage_e_perception.py tests/unit/test_phase13_5_release_audit_fixes.py::test_audit_registry_exposes_85_tools tests/unit/test_screen_control_catalog.py tests/unit/test_worker_cancellation.py -q
& .\output\p11-native-env\Scripts\python.exe -m pytest tests/windows/test_p12_uia_semantic_controls.py -q -s
& .\output\p12-ocr-env\Scripts\python.exe -m pip install --disable-pip-version-check --no-cache-dir -e ".[ocr]"
& .\output\p12-ocr-env\Scripts\python.exe -m pip check
& .\output\p12-ocr-env\Scripts\python.exe output\p12_ocr_smoke.py
& .\output\p11-native-env\Scripts\python.exe -m py_compile pluma\perception\ocr_adapter.py tests\unit\test_perception_ocr_adapter.py
& .\output\p11-native-env\Scripts\python.exe docs\completion\verify_requirements_matrix.py
git diff --check
```

Source hashes for the tested implementation commit:

| File | SHA256 |
|---|---|
| `pluma/perception/ocr_adapter.py` | `F6D2C43DE1082AFE6FA7940ECD807C8AA49A2B38D9521C9B8590AFAB77DF3203` |
| `tests/unit/test_perception_ocr_adapter.py` | `1A652895C2AA1D747CA0D0E04AD49C1B365F7F0C83909CEA21705C53436BAD20` |
| `pyproject.toml` | `935AF8F11E0F13ABE91C593A1A1467033C44476ECB3A7AAF818DB4C3B0303229` |
| `README.md` | `351C3A887D7CE0B68456E2C3E223F03488C25C8DF30B3920288D8C59A06BA92C` |

```text
Pre-edit P12 prerequisite suite (OCR adapter/lifecycle, OCR grounding, screen catalog, owned Win32 UIA): 53 passed in 5.76s; zero skips.
Post-change OCR adapter suite: 12 passed in 0.63s; zero skips.
Optional runtime install into ignored output/p12-ocr-env: passed with paddleocr 3.7.0, paddlex 3.7.2, onnxruntime 1.31.0, numpy 2.3.5 and Pillow 13.0.0.
Final P12-focused regression group: 183 passed in 42.29s; zero skips.
Current owned Win32 UIA acceptance: 7 passed in 4.04s; zero skips.
Real OcrAdapter smoke on generated in-memory text: exact 4/4 lines; all bounds inside the 1000x300 image; confidence 0.999, 0.999, 1.000, 0.993; one inference after model load took 504.7 ms; ONNX CPU provider explicitly selected.
OCR environment pip check: passed; importing the OCR adapter/lifecycle with the optional runtime installed left PaddleOCR/ONNX Runtime unloaded and the manager COLD.
Python compilation, requirements matrix validation (298 source items/324 rows), and git diff --check: passed.
```

The smoke image contained `PLUMA SCREEN CHECK`, `Save Changes`, `Cancel`, and
`WINDOW SCALE 100%`. It was created in a `BytesIO` buffer and was not saved.
The official model weights were cached under the user's `.paddlex` directory,
outside the repository. No screenshot or model file was staged.

The automated sample does not claim general screen OCR quality. The fixed
corpus and 100%, 125%, and 150% scaling accuracy/latency measurements remain
assigned to P26.

An additional broad regression command also included the full, unchanged
`tests/unit/test_phase13_5_release_audit_fixes.py` module: 193 passed and four
older cross-phase cases failed before reaching their asserted postconditions
(policy preemption for move/timeout, unverified app launch, and a changed
window-state refusal code). The P12-scoped run above includes that file's
85-tool catalog assertion, which passes. These unrelated failures were not
changed as part of P12.

## Remaining P12 acceptance

E-02 through E-10 have current owned-fixture evidence in E62-E66. E-01 passes
for Win32 in E66, and E62 records an earlier WPF pass. The most recent current
WPF test attempt failed before fixture readiness because Windows Application
Control blocked its generated fixture DLL (`0x800711C7`). The policy was not
changed or bypassed, so a permitted current-build WPF retest is still required
before P12 can be marked fully closed. No P13 work was started.
