# E76 — P14 targeted defect and evidence closure

See [E76](p14_gap_repairs.md) for the six source/verification findings closed
after this E75 checkpoint. E76 adds arbitrary extensionless file-target
clarification, conservative per-segment confidence, spoken clipboard redaction,
measured C-02 stop timing, production hotkey-loop unit coverage, and a bounded
native Whisper-to-Qwen same-capsule run. E76 also corrects the historical C-01
polling and C-02 timing claims below. Complex native STT-to-multi-step file
planning from human speech and P19 visible clarification remain unverified.

# E75 — P14 backend voice acceptance

**Status as of E75:** This checkpoint recorded C-01 through C-09 backend voice
evidence and called the backend acceptance complete. E76 supersedes six
implementation/evidence findings and narrows the remaining limitations; see
[E76](p14_gap_repairs.md) before relying on that historical status. C-10
remains optional. P15 has not started.

## Gap and implementation

At E74, the capture callback only accumulated PCM until push-to-talk release;
VAD trimmed audio later and did not stop the live stream at the speech
boundary. The resident did not pass its configured VAD to capture. Voice/text
tests used inert devices, the native planner had not been exercised with a
voice-originated request, and a low-confidence material transcript was
discarded without a typed backend outcome. The request's original transcript
was not read back from the Activity Ledger.

`EnergyVAD` now provides task-local incremental frame detection using the
configured minimum speech and trailing-silence durations (defaults: 300 ms and
600 ms). `AudioCapture` stops its callback at that boundary, excludes later
frames, keeps its existing duration bound, and closes/clears transient data on
release or STOP. The resident supplies its VAD to capture.

Low-confidence material speech now produces a transcript-free
`VoiceClarificationRequired` value with a fixed code and confidence. The
resident sends it to the optional clarification callback and does not create a
command task or invoke a tool. The callback is the backend handoff for P19; this
packet adds no UI or IPC contract. The warning log no longer includes a
material-target transcript.

Voice task history now stores the redacted original transcript in a new
`tasks.original_transcript` migration. Accepted voice requests still use the
same `PlumaRequest`, router, policy, registered tools, verification and ledger
path as typed requests. README now documents both microphone and STT extras.

## Verification

Environment: Windows 11 build 26200, CPython 3.12.10, pytest 9.1.1,
`sounddevice` 0.5.6, `pywhispercpp` 1.5.1, `llama-cpp-python` 0.3.36. Native
models, generated/recorded audio and reports are under ignored `output/`.

```powershell
& .\output\p14-native-env\Scripts\python.exe -m pytest tests/unit/test_voice_capture.py tests/unit/test_voice_vad.py tests/unit/test_voice_session.py tests/unit/test_voice_pipeline.py tests/unit/test_voice_orchestrator_integration.py tests/unit/test_voice_native_worker.py tests/unit/test_phase13_7_voice_stop.py tests/unit/test_activity_ledger_lifecycle.py tests/unit/test_db.py tests/unit/test_voice_activation.py tests/unit/test_voice_lifecycle.py tests/unit/test_app_lifecycle.py tests/unit/test_runtime_shutdown.py tests/unit/test_worker_cancellation.py -q
# 161 passed; zero failed, errors, skips or xfails. Full output: output/p14-native/final-voice-regressions.log

& .\output\p14-native-env\Scripts\python.exe tests/windows/p14_voice_device_acceptance.py --model output/p14-native/ggml-base.en.bin
# Passed on the physical default input "Microphone Array (AMD Audio Dev".
# Capture remained closed before activation, opened only after the production
# activation callback, held 10,816 bytes in memory, and closed on release.
# Physical microphone STOP closed the live stream, admitted no processing and
# read back STOPPED/user_stop cleanup. No audio or transcript was saved.

& .\output\p14-native-env\Scripts\python.exe tests/windows/p14_voice_boundary_acceptance.py --sample output/p14-native/material-clarification-sapi.wav --output-device 'Speaker (Realtek(R) Audio)' --repetitions 3
# Passed 3/3 on the physical default AMD microphone array and Realtek speaker
# (MME). Each trial observed VAD completion, inactive stream, stable buffer,
# and closure after release. Full report: output/p14-native/voice-boundary-acceptance-report.json

& .\output\p14-native-env\Scripts\python.exe tests/windows/p14_native_stt_acceptance.py --model output/p14-native/ggml-base.en.bin --sample output/p14-native/jfk.wav
# Passed using real whisper.cpp/GGML: confidence 0.7721014766, model returned
# COLD, active worker CPU observed for 0.1719 seconds before STOP, original
# process absent, caller cancelled and cleanup read back from SQLite.

& .\output\p14-native-env\Scripts\python.exe tests/windows/p14_material_target_acceptance.py --model output/p14-native/ggml-base.en.bin --sample output/p14-native/material-clarification-sapi.wav
# Passed using actual whisper.cpp on generated Microsoft Zira speech. The
# material-target result was 0.625466 confidence (threshold 0.65); a typed
# clarification outcome was emitted, no transcript was attached, no command
# task/tool was admitted, and the worker was cleaned up. Audio/text stayed
# transient. This is generated fixture evidence, not human speech quality.

& .\output\p13-native-env\Scripts\python.exe tests/windows/p14_voice_planner_acceptance.py --model output/p13-native/model/Qwen3-4B-Q4_K_M.gguf
# Passed using native llama.cpp and the 2.497 GB Qwen3-4B-Q4_K_M model
# (SHA-256 7485fe6f11af29433bc51cab58009521f205840f5b4ae3a32fa7f92e8534fdf5).
# Typed and fixture-transcribed voice requests both used SMART and completed
# list_folder then file_info within the owned fixture directory. Worker
# absence, SQLite task/action state and original voice transcript readback
# passed. No microphone was opened in this planner run.
```

The fixture VAD tests feed speech/silence frames into the real capture callback
and prove the configured boundary stops the stream and excludes later frames.
The E75 physical C-02 check played the generated Microsoft Zira speech fixture
through the Realtek speaker at 20% sample gain and captured it using the default
physical AMD microphone array. Three consecutive trials observed VAD completion,
an inactive stream, no buffer growth after completion, and release closure.
E75 did not calculate expected-versus-measured stop timing; E76 adds that
measurement and its explicit tolerance. A two-second post-playback wait allows
the microphone's noise processing to settle. This is physical-device evidence
with generated speech, not human speech-quality evidence; no microphone audio or
transcript was saved. The PCM
fixture is 152,480 bytes with SHA-256
`4585b896e2cf254702064678093efe7b6e470df1240a904f92101f872b2717ea`; the
three physical captures held 165,120, 158,400 and 180,480 bytes respectively
in memory before release.

C-03/C-04 use in-memory registered fixture tools so the checks do not open
Notepad or change system volume. The native C-05 run uses the real Qwen planner
but injects an explicit fixture transcript; it does not establish a complete
human-speech-to-Whisper-to-planner acoustic run. The real STT/model checks are
separate and labeled above.

## Changed files

- `README.md`
- `pluma/core/orchestrator.py`, `pluma/core/resident.py`
- `pluma/memory/activity.py`, `pluma/memory/migrations/0004_voice_original_transcript.sql`
- `pluma/voice/__init__.py`, `pluma/voice/capture.py`, `pluma/voice/pipeline.py`, `pluma/voice/vad.py`
- `tests/unit/test_activity_ledger_lifecycle.py`, `tests/unit/test_db.py`
- `tests/unit/test_voice_capture.py`, `tests/unit/test_voice_orchestrator_integration.py`, `tests/unit/test_voice_pipeline.py`, `tests/unit/test_voice_session.py`
- `tests/windows/p14_material_target_acceptance.py`, `tests/windows/p14_voice_boundary_acceptance.py`, `tests/windows/p14_voice_device_acceptance.py`, `tests/windows/p14_voice_planner_acceptance.py`

## Disposition

- **C-01:** Physical input opens only after the activated production callback and closes on release. At E75, the OS hotkey polling loop was not covered; the device harness invoked the trigger callback rather than synthesizing a keyboard press. E76 adds a production-loop unit test against a mocked Win32 polling API; it does not synthesize a physical keypress.
- **C-02:** Incremental VAD and callback boundary pass fixture tests and three repeated physical generated-speech trials. E75 observed completion/cleanup but did not measure timing against the expected speech boundary. E76 adds that timing check and reports the tolerance and measurements. Human speech quality is not measured here.
- **C-03/C-04:** Shared voice/text fast-route behavior and tool parity pass with side-effect-free registered fixtures.
- **C-05:** Actual local planner passes a two-step voice-originated fixture request and its typed equivalent.
- **C-06:** Actual local STT crosses the material-target confidence threshold, emits a transcript-free clarification outcome, and admits no command/tool. Resident callback delivery is fixture-tested. User-visible clarification is left for the P19 overlay.
- **C-07:** STOP during physical capture closes the microphone and prevents voice processing or task admission.
- **C-08/C-09:** Actual task-owned STT STOP, worker absence, cleanup readback and transient-audio behavior pass; see the fresh E74 harness run above.
- **C-10:** Optional local SAPI result remains optional and is not implemented.

All required P14 backend gates C-01 through C-09 now have evidence. The next
safe milestone is P15's UI/core request and event contracts when explicitly
instructed. No P15 work has started.
