# E74 — P14 task-owned native STT packet

**Status:** This bounded packet closes the native STT ownership/cancellation
and model-runtime wiring work for C-08 and B-04. P14 remains in progress; this
is not a milestone completion claim.

## Gap and implementation

At the E73 checkpoint, `WhisperSttAdapter.transcribe()` called blocking
`Model.transcribe()` in the resident release handler. Cancellation was checked
only before the call, confidence defaulted to `1.0` when the binding did not
return a probability, and the application selected `base.en.pt` under the
generic models root while reading a non-baseline idle setting.

The adapter now validates bounded 16 kHz mono int16 audio and sends it only to
the matching `TaskCapsule` worker from the shared `ToolRegistry`. That worker
loads the configured GGML model, calls whisper.cpp with its cooperative abort
callback and probability extraction enabled, frees the native model reference
before responding, and returns only structured transcript data. STOP and the
60-second deadline use the existing controller termination path; the adapter
requires worker cleanup readback before reporting cancellation or timeout.
Missing, NaN or out-of-range segment probabilities cannot become high
confidence. The resident process never imports the STT binding or holds the
model. Since the native model is released before each worker response, the
production STT lifecycle returns directly to COLD; it does not retain a warm
model for the configured grace period.

`PlumaApplicationRuntime` now defaults to
`%LOCALAPPDATA%\Pluma\models\whisper\ggml-base.en.bin`, honors explicit
`voice.model_path`/`voice.model_name`, and reads
`runtime.stt_idle_unload_seconds`. The lifecycle does not report WARM merely
because it validated a path. The voice extra declares `pywhispercpp>=1.5.1,<2`
and bounded NumPy support; README documents the extra and external model
placement. No model downloads occur in the product.

Voice task timeout is now finalized as FAILED with `TASK_TIMEOUT` preserved in
the pre-execution ledger report. The P13.7 voice STOP fixture now exposes
positive capture-closure readback and asserts the truthful residual state when
STOP overlaps the active release handler. It does not relax task cleanup.

## Acceptance evidence

Before the change, a blocking STT regression failed as expected: after the
cancellation latch was set, the caller remained blocked at the 100 ms assertion
until the inference fixture was released.

After the change, the focused voice/app/worker suite passed **60 tests** on
Windows 11 build 26200, Python 3.12.10, pytest 8.3.3; zero failures, errors,
skips or xfails. The affected voice, application lifecycle, worker ownership,
shutdown, cancellation, cleanup, job-object and ledger regression set passed
**246 tests** in the isolated P14 environment; zero failures/errors/skips/xfails
(two JUnit metadata warnings only). The P13.7 voice STOP fixture is included in
that final run.

The actual native acceptance used `pywhispercpp 1.5.1` on Windows CPython 3.12
with the official `ggml-base.en.bin` model and recorded `jfk.wav` sample. The
model SHA-1 was
`137c40403d78fd54d454da0f9bd998f78703390c`; the 352,000-byte sample SHA-256 was
`a29462b8ebd467318000e683b9117ade46230d3255ed2024e7db894abd9b38c9`. Native
transcription recognized the acceptance phrase with confidence `0.7721014766`
and 22 words. The runtime started cold, the STT binding remained absent from the
resident process, the model wrapper was released before the response, and the
lifecycle returned to COLD. The harness also observed CPU work in the
task-owned native worker during the bounded 30-second STT request, issued STOP,
and verified original worker absence, voice-caller cancellation, and the
pre-execution cleanup report read back from SQLite. No raw audio or transcript
appeared in that report, and the isolated PLUMA runtime created no `.wav`,
`.pcm` or `.raw` files.

Commands and outputs:

```powershell
python -m pytest tests/unit/test_voice_stt_adapter.py tests/unit/test_voice_lifecycle.py tests/unit/test_voice_pipeline.py tests/unit/test_voice_session.py tests/unit/test_app_lifecycle.py -q
# Prerequisite before editing: 48 passed, zero skips.

python -m pytest tests/unit/test_p14_stt_reproduction.py -q
# Before fix: 1 expected failure, "STOP did not interrupt blocked STT inference".
# This temporary reproduction was replaced by committed adapter/worker regressions.

python -m pytest tests/unit/test_voice_native_worker.py tests/unit/test_voice_stt_adapter.py tests/unit/test_voice_lifecycle.py tests/unit/test_voice_pipeline.py tests/unit/test_voice_session.py tests/unit/test_app_lifecycle.py tests/unit/test_phase13_7_voice_stop.py -q
# Focused final: 60 passed, zero skips.

& .\output\p14-native-env\Scripts\python.exe -m pytest tests/unit/test_voice_vad.py tests/unit/test_voice_stt_adapter.py tests/unit/test_voice_session.py tests/unit/test_voice_pipeline.py tests/unit/test_voice_orchestrator_integration.py tests/unit/test_voice_native_worker.py tests/unit/test_voice_lifecycle.py tests/unit/test_voice_capture.py tests/unit/test_voice_activation.py tests/unit/test_phase13_7_voice_stop.py tests/unit/test_app_lifecycle.py tests/unit/test_runtime_shutdown.py tests/unit/test_executor_admission.py tests/unit/test_worker_cancellation.py tests/unit/test_task_supervisor.py tests/unit/test_cleanup_evidence.py tests/unit/test_ownership.py tests/unit/test_job_object.py tests/unit/test_activity_ledger_lifecycle.py tests/unit/test_backend_wiring_audit.py -p tests.fixtures.desktop_isolation -q --junitxml=output/p14-native/affected-regression.xml
# 246 passed; zero failed/errors/skips/xfails; two JUnit metadata warnings.

& .\output\p14-native-env\Scripts\python.exe tests/windows/p14_native_stt_acceptance.py --model output/p14-native/ggml-base.en.bin --sample output/p14-native/jfk.wav
# Native runtime/model/sample, confidence, unload, in-flight STOP, worker absence and SQLite readback: passed.

& .\output\p14-native-env\Scripts\python.exe -m pip check
# No broken requirements.
```

Native model/sample and full test logs remain under ignored `output/p14-native/`.
The exact final native report is
`output/p14-native/acceptance-report-final.json`; the affected regression JUnit
report is `output/p14-native/affected-regression.xml`.

Tested source identity (SHA-256, before the E74 commit):

```text
pluma/voice/stt_adapter.py E66780A640C0FB26E1F23909A2ED572874A3D8BAD258AAF16E031294FC5291E5
pluma/voice/lifecycle.py C1C9B21BFAFDB6182D16642A544EA0614A62EFD606CFC29267AD3E5BCA5141B7
pluma/app.py B03534029EC6C99DF0182985C6F8B8C0BC653CEDC828C17C5EA23F9340EC0BBD
pluma/core/resident.py 4BADEB645EC6D825C82D9BF8157556B5E7342D7EB1C93C846D5619E6E5DCD3AF
pyproject.toml 43A7892B7AADD7703F4F905B47ED5345A679DB34454048E0107995B356BC86E6
tests/unit/test_voice_native_worker.py F3D6EC7C07C0ECA3E95801B09146BAF98F4074971FD91071A2E6F4037525F383
tests/unit/test_voice_lifecycle.py 5CB8277C08B0A088C270B82F9464CE8E2A600BBCD9FA47F874D2050B872FF4BF
tests/unit/test_voice_session.py A2989178435CDCC4230BCFB8DCC0F95406FADFB642E77E7EE8FE1394508CB4B1
tests/unit/test_app_lifecycle.py 7F4AE5AB5D51560D10D2BA90396D2A1C20083B6020697F9BD214047420B7CF87
tests/unit/test_phase13_7_voice_stop.py 63FE38BE588C8925BD9E5AE025E5C412EE17B48789BC042E26D66DF0CC74DE60
tests/windows/p14_native_stt_acceptance.py 11961A9DF7E260A0D4A8695F7A9F64F92EE723D6B4BB1E1375E04B451BFD69DC
```

The native report SHA-256 is
`B2F80030F7D9BCE8AF65E1D21BB8AB09F41842B83DB407A6679D0A8E934C268B`.
The report records the runtime/model/sample identities and worker PIDs for both
native calls; the model/sample themselves and report are ignored local output,
not committed artifacts.

The implementation uses the documented `abort_callback` and
`extract_probability=True` interface from
[pywhispercpp's API reference](https://absadiki.github.io/pywhispercpp/).
Whisper.cpp requires its converted GGML model format; the model identity is
listed in the upstream
[model table](https://github.com/ggml-org/whisper.cpp/blob/master/models/README.md).

## Matrix disposition and remaining P14 work

- **B-04:** Implemented and measured for the native fixture. The model is
  released before the inference response; configured STT idle seconds are read
  by the app, but no warm interval is used by this per-task worker design.
- **C-08:** Implemented and verified using the real native runtime, cooperative
  cancellation, controller termination, process identity and SQLite cleanup
  readback.
- **C-09:** Implemented for the backend path: P07 capture tests and this native
  fixture verify transient audio handling and no runtime audio-file or ledger
  persistence. The fixture itself is a recorded sample, not microphone input.
- **CORE-STT remains UNVERIFIED overall.** This packet does not finish physical
  microphone activation (C-01), the speech-end boundary (C-02), real voice/text
  route parity (C-03/C-04), complex voice planning (C-05), low-confidence
  material-target clarification with actual model output (C-06), or native
  microphone STOP during capture (C-07). C-10 is optional.
- No microphone, private recording, active window, clipboard, or power state
  was touched. Device evidence remains unverified. The one-sample result is
  runtime compatibility evidence, not a model-quality or accuracy benchmark.

Next safe P14 packet: C-01/C-02 user-activated microphone and speech-boundary
verification, distinguishing fixture behavior from device evidence. No P15 work
is authorized by this packet.
