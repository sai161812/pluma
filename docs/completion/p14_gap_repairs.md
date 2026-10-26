# E76 — P14 targeted defect and evidence closure

**Status:** The six findings reviewed on 2026-10-26 are closed to the scope
described here. P14 is not declared complete by this packet: P19 still owns the
visible voice clarification surface, and complex native STT-to-multi-step file
planning from human speech remains unverified.

## Findings and repairs

1. **Uncertain filenames bypassed clarification.** `is_material_target` no
   longer depends on a short extension whitelist. It detects arbitrary
   filename suffixes, paths, file/folder nouns, and file mutation verbs, so
   extensionless targets such as `README` are material too. A low-confidence
   target yields a transcript-free clarification result.
2. **Averaged STT confidence hid weak target segments.** Native Whisper now
   reports the minimum confidence among nonempty segments. Empty segments do
   not lower or inflate the request score. The `0.99`/`0.40` regression reports
   `0.40` and is classified as low confidence.
3. **Spoken clipboard values appeared in logs and task history.** A deterministic
   command-text redactor removes utterances naming the clipboard or describing
   paste before voice/orchestrator INFO logging and task/original-transcript
   persistence. The request remains available transiently for routing. Clipboard
   action arguments continue to use the existing clipboard-specific ledger
   redaction.
4. **C-02 did not measure stop timing.** The physical harness now profiles the
   explicit speech fixture, rejects early internal silence, computes the
   expected stop from speech-active-end plus configured trailing silence, and
   compares captured duration after subtracting pre-playback capture time.
   Three AMD-array/Realtek-speaker trials passed within the declared 750 ms
   device tolerance; their timing errors were 456.8, 399.7 and 629.7 ms. Each
   also read back VAD completion, inactive stream, stable buffer and release
   closure. The fixture's active end was 3,900 ms; expected stop was 4,500 ms.
5. **The OS hotkey polling loop lacked coverage.** A new unit test executes
   production `_monitor_loop` with a mocked Win32 `GetAsyncKeyState` API and
   verifies press and release dispatch. This is loop coverage, not a physical
   keyboard injection; the device harness still invokes the production PTT
   trigger callback.
6. **Native STT-to-planner was unverified as one path.** A Windows acceptance
   run now transcribes generated speech with actual Whisper, then passes that
   request and its same `TaskCapsule` to actual Qwen/llama.cpp SMART planning.
   The bounded action is the fixed read-only `os_version` diagnostic. Voice and
   equivalent typed execution both verified the action and ledger; the STT and
   planner workers were absent after completion. This proves the combined
   native path for this bounded request. It does not prove native STT accuracy
   for complex, multi-step spoken file commands or human speech.

## Verification

Environment: Windows 11, CPython 3.12.10, pytest 9.1.1,
`pywhispercpp 1.5.1`, `llama-cpp-python 0.3.36`, `sounddevice 0.5.6`.
Native models, generated speech and full reports are in ignored `output/`.

Affected regressions:

```powershell
& .\output\p14-native-env\Scripts\python.exe -m pytest tests/unit/test_voice_capture.py tests/unit/test_voice_vad.py tests/unit/test_voice_session.py tests/unit/test_voice_pipeline.py tests/unit/test_voice_orchestrator_integration.py tests/unit/test_voice_native_worker.py tests/unit/test_phase13_7_voice_stop.py tests/unit/test_activity_ledger_lifecycle.py tests/unit/test_db.py tests/unit/test_voice_activation.py tests/unit/test_voice_lifecycle.py tests/unit/test_app_lifecycle.py tests/unit/test_runtime_shutdown.py tests/unit/test_worker_cancellation.py tests/unit/test_voice_boundary_acceptance.py -p tests.fixtures.desktop_isolation -q 2>&1 | Tee-Object -FilePath output/p14-native/p14-gap-regressions-e76.log
# 179 passed; 0 failed, errors, skipped or xfailed.
# Full output: output/p14-native/p14-gap-regressions-e76.log (ignored).
```

Native material-target clarification, rerun after the confidence change:

```powershell
& .\output\p14-native-env\Scripts\python.exe tests/windows/p14_material_target_acceptance.py --model output/p14-native/ggml-base.en.bin --sample output/p14-native/material-clarification-sapi.wav --report output/p14-native/material-target-acceptance-e76.json
# Passed with actual whisper.cpp; confidence 0.625466 below 0.65, no request,
# command task or tool admitted, transcript/audio not persisted, worker cleanup
# read back, model returned COLD.
```

Physical C-02 timing run:

```powershell
& .\output\p14-native-env\Scripts\python.exe tests/windows/p14_voice_boundary_acceptance.py --sample output/p14-native/material-clarification-sapi.wav --output-device 'Speaker (Realtek(R) Audio)' --repetitions 3 --report output/p14-native/voice-boundary-acceptance-report-final.json
# 3/3 passed; 600 ms VAD trailing silence; expected stop 4,500 ms after
# playback start; measured errors 456.8, 399.7 and 629.7 ms (750 ms tolerance).
```

Combined native STT-to-planner entry point:

```powershell
$priorPythonPath = $env:PYTHONPATH
$env:PYTHONPATH = (Resolve-Path .\output\p14-native-env\Lib\site-packages).Path
try {
  & .\output\p13-native-env\Scripts\python.exe tests/windows/p14_voice_planner_acceptance.py --model output/p13-native/model/Qwen3-4B-Q4_K_M.gguf --stt-model output/p14-native/ggml-base.en.bin --speech-sample output/p14-native/planner-native-stt-command.wav --report output/p14-native/voice-planner-native-stt-report.json
} finally {
  if ($null -eq $priorPythonPath) { Remove-Item Env:PYTHONPATH -ErrorAction SilentlyContinue }
  else { $env:PYTHONPATH = $priorPythonPath }
}
# Passed. Actual Whisper confidence was 0.5382; actual Qwen route was SMART.
# Voice and typed runs used run_powershell/os_version, read back their ledgers,
# and left no worker. The voice STT and planner shared one capsule.
```

The boundary and planner reports record model/device identities and fixture
hashes without persisting raw capture or transcript in the report. The planner
acceptance reads its synthetic transcript back from the isolated SQLite ledger
to verify task history; the transcript is intentionally excluded from the
report. No personal clipboard, files, application windows, or power state were
used by these checks.

## Changed files

- `pluma/voice/pipeline.py`, `pluma/voice/stt_adapter.py`
- `pluma/memory/redaction.py`, `pluma/memory/activity.py`,
  `pluma/core/orchestrator.py`
- `tests/unit/test_voice_pipeline.py`, `tests/unit/test_voice_native_worker.py`,
  `tests/unit/test_voice_activation.py`,
  `tests/unit/test_voice_boundary_acceptance.py`,
  `tests/unit/test_activity_ledger_lifecycle.py`,
  `tests/unit/test_voice_orchestrator_integration.py`
- `tests/windows/p14_voice_boundary_acceptance.py`,
  `tests/windows/p14_voice_planner_acceptance.py`
- `docs/completion/p14_voice_acceptance.md`,
  `docs/completion/requirements_matrix.md`, `PROJECT_HANDOFF.md`

Recovery point before E76: `80417f8175aa1d109752b44b49cce83f49ae7356` on
`p12-preparation`. No branch switch, reset, merge or force push was used.
