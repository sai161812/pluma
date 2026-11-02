# E77 — P14 remaining voice-path fixes

**Status:** Superseded by [E78](p14_e78_c02_device_followup.md), which adds
input-specific C-02 diagnostics and records the passing physical boundary run.
E77 verifies clipboard preview redaction, extensionless read clarification,
and native complex-file Whisper→Qwen acceptance. The C-02 timing acceptance
rejects premature stops. P14's mandatory backend gate is complete; P15 has not
started.

## Findings and repairs

1. **Long clipboard commands exposed their leading payload in the log preview.**
   `Orchestrator` now redacts the complete command before slicing it to 120
   characters. The regression places a synthetic private value before the
   preview limit and the word `clipboard` after it, then checks both INFO logs
   and isolated SQLite `command_text`/`original_transcript`.
2. **Extensionless file reads skipped low-confidence clarification.**
   `VoicePipeline` now treats `open`, `read`, and `view` targets as material
   unless an `open` target is an explicitly recognized app alias. `open README`
   and `read LICENSE` at confidence 0.10 return `VoiceClarificationRequired`;
   `open notepad` remains a normal routable app launch.
3. **C-02 accepted stops too early.** The timing gate uses an asymmetric window:
   at most 100 ms early relative to the configured speech-end-plus-VAD boundary,
   and at most 750 ms late for device delay. With the 3,900 ms fixture speech
   end and 600 ms VAD tail, a stop at 3,800 ms has error −700 ms and is rejected.
   The fixture regression also checks both allowed endpoints and rejects values
   beyond either bound.
4. **C-05 native complex-file acceptance used a shallow diagnostic.** The Windows
   acceptance now runs actual local Whisper on generated speech and actual
   Qwen/llama.cpp planning for exactly `list_folder` and `file_info` against an
   owned fixture. A temporary `P:` mapping is created only when absent, read
   back to the fixture root, and removed with readback. Before dispatch, each
   native plan path is resolved through a Windows file handle and rejected
   unless it stays within the fixture. Both voice and typed equivalents verify
   the file listing/identity/size, route and tools, SQLite task/action state,
   same STT/planner task capsule, and worker absence.

## Verification

Focused regressions:

```powershell
& .\output\p14-native-env\Scripts\python.exe -m pytest tests/unit/test_voice_orchestrator_integration.py tests/unit/test_voice_pipeline.py tests/unit/test_voice_boundary_acceptance.py -p tests.fixtures.desktop_isolation -q
# 27 passed; zero failures, skips or xfails.
```

Affected P14 regressions:

```powershell
& .\output\p14-native-env\Scripts\python.exe -m pytest tests/unit/test_voice_capture.py tests/unit/test_voice_vad.py tests/unit/test_voice_session.py tests/unit/test_voice_pipeline.py tests/unit/test_voice_orchestrator_integration.py tests/unit/test_voice_native_worker.py tests/unit/test_phase13_7_voice_stop.py tests/unit/test_activity_ledger_lifecycle.py tests/unit/test_db.py tests/unit/test_voice_activation.py tests/unit/test_voice_lifecycle.py tests/unit/test_app_lifecycle.py tests/unit/test_runtime_shutdown.py tests/unit/test_worker_cancellation.py tests/unit/test_voice_boundary_acceptance.py -p tests.fixtures.desktop_isolation -q
# 182 passed; zero failures, errors, skips or xfails.
# Full output: ignored output/p14-native/p14-gap-regressions-e77.log
```

Native C-05 acceptance:

```powershell
$priorPythonPath = $env:PYTHONPATH
$env:PYTHONPATH = (Resolve-Path .\output\p14-native-env\Lib\site-packages).Path
try {
  & .\output\p13-native-env\Scripts\python.exe tests\windows\p14_voice_planner_acceptance.py --model output\p13-native\model\Qwen3-4B-Q4_K_M.gguf --stt-model output\p14-native\ggml-base.en.bin --speech-sample output\p14-native\p14-c05-native-planner.wav --report output\p14-native\voice-planner-native-complex-file-e77.json
} finally {
  if ($null -eq $priorPythonPath) { Remove-Item Env:PYTHONPATH -ErrorAction SilentlyContinue }
  else { $env:PYTHONPATH = $priorPythonPath }
}
# Passed with llama-cpp-python 0.3.36 and whisper.cpp; actual Whisper confidence
# 0.6982215566 (not low confidence). Voice and typed tasks both used SMART and
# list_folder → file_info. Each reported note.txt at 49 bytes with verified file
# identity; ledger readback, same voice STT/planner capsule and worker absence
# passed. The generated transcript was read from the isolated SQLite ledger;
it is not included in the report. No captured/raw audio was persisted by the
runtime. Full output:
# ignored output/p14-native/voice-planner-native-complex-file-e77.log
```

Fresh physical C-02 attempts did **not** pass. The default MME run at gain 0.2
reported no boundary in all three trials (errors +2787.1, +2787.4, +2787.4 ms).
At gain 0.8, only one of three trials passed (+2813.9, +339.8, −3440.3 ms);
the other two reported no boundary or an early stop. A DirectSound run on the
same named AMD microphone array and Realtek speaker also varied (−500.4,
−2930.5, +2987.2 ms; zero of three passed). A WASAPI attempt could not open
the microphone at the required 16 kHz sample rate. Reports and complete logs
are under ignored `output/p14-native/voice-boundary-e77*`. These failures are
not counted as passes. The asymmetric timing checks correctly reject them;
the acceptance window was not widened.

## Changed files

- Runtime: `pluma/core/orchestrator.py`, `pluma/core/router.py`,
  `pluma/voice/pipeline.py`
- Regressions: `tests/unit/test_voice_orchestrator_integration.py`,
  `tests/unit/test_voice_pipeline.py`,
  `tests/unit/test_voice_boundary_acceptance.py`
- Native/physical acceptance: `tests/windows/p14_voice_boundary_acceptance.py`,
  `tests/windows/p14_voice_planner_acceptance.py`
- Evidence: `docs/completion/p14_e77_gap_closure.md`,
  `docs/completion/p14_gap_repairs.md`,
  `docs/completion/p14_voice_acceptance.md`,
  `docs/completion/requirements_matrix.md`, `PROJECT_HANDOFF.md`

Recovery point before E77: `a675d1eea3f334bbe2c5972e32fe35437b43010d` on
`p12-preparation`. No branch switch, reset, merge or force push was used.
The next safe packet remains P14 C-02 physical boundary diagnosis and a fresh
three-trial acceptance on a stable permitted microphone/playback path.
