# E94: P19 unified voice overlay completion

Date: 2026-11-02. Branch: `p12-preparation`.
Tested source: `7a56915ad82595265d71352ebb92531af7fa9b36`.
Recovery: `fe5888d24d0257a8fb1c193acd522a71158d7b1e` (E93).

**P19's scoped implementation and acceptance gate is complete, with the
owner-approved physical boundary-timing retest deferred below.** E92's real
native segments and E93's typed lifecycle are now connected to the existing
single overlay. This is not full-product release or independent Sol approval.

## Implementation

- The main window owns one serialized `VoiceController`, its cancellation
  lifetime and task. It starts after the initial dashboard status read drains,
  preserving the four ordinary IPC slots and separate priority STOP slot.
  Navigation shares that observer; shutdown cancels and joins it. Queries do
  not activate a microphone, create a command or load an inference runtime.
- The existing shared popup host uses one `voice` entry and one `VoiceOverlay`
  for surfaces 11-14. Updates preserve its native window and transcript reader.
  A new generation resets the old text/viewport. Disconnect clears text before
  dismissal. Stream, generation, request correlation, recognition sequence,
  task identity and terminal-state regression checks reject stale readback.
- Capture exports bounded measured amplitude, 32 spectrum bands, sample
  sequence, speech activity and configured VAD silence progress. Analysis copies
  one 1024-sample window under a bounded lock, then uses pure DSP outside it.
  Raw PCM stays inside capture; no extra device, timer, worker or dependency was
  added. Repeated reads do not advance progress or refresh an old spectrum.
- LISTENING follows actual capture; the silence bar reflects detector frames.
  Speech boundary, empty speech and task deadline remain distinct. DECODING
  displays real recognition segments; COMMITTED requires actual same-capsule
  orchestrator admission and shows the final transcript plus existing received
  banner. No preview driver or sample text enters the production binding.
- Denial, unavailable capture, clarification, empty input, cancellation and
  timeout have deterministic factual status copy. They do not claim commitment
  or replay uncertain targets. Capture and STT STOP preserve their original
  supervisor/cancellation, verification, cleanup and ledger ownership.
- Literal filenames/Unicode remain intact in the fixed transcript viewport.
  Updates follow new speech only at the tail and preserve earlier-text reading.
  Committed transcript and banner share the existing fixed card dimensions.
  Dark palette, typography, placement and shared stack behavior are retained.

Production files: `pluma/voice/{capture,meter,presentation}.py`,
`pluma/core/ipc_contracts.py`, and the existing native voice DTO/controller,
main window, dashboard startup readback, overlay/transcript controls and enum.
Tests add measured DSP/metadata checks, controller checks and actual native
whole-window acceptance. Both test hosts link the controller. The expanded
native acceptance has a bounded 60-second watchdog/75-second outer budget;
this is a fixture budget, not a changed product latency assertion.

## Prerequisites and regressions

The unchanged complete master was reused and its blob refreshed:
`01b693dbf898b662aa4cd67736c1a0e8a21cf3e3`. Shared/P19 prompts, AGENTS,
handoff, matrix, applicable Phase 6/14 and voice requirements/source/tests were
inspected. The checkout was clean at E93. Existing P00-P18 evidence retains its
recorded scopes; completed milestones were not restarted.

Pre-edit affected checks: **144 passed in 14.11 s**. Final affected checks:
**331 passed in 39.22 s**, no skips/xfails:

```powershell
output/p14-native-env/Scripts/python.exe -m pytest -q tests/unit/test_p19_meter.py tests/unit/test_p19_voice_bridge.py tests/unit/test_p19_recognition.py tests/unit/test_voice_session.py tests/unit/test_voice_pipeline.py tests/unit/test_voice_orchestrator_integration.py tests/unit/test_voice_capture.py tests/unit/test_voice_activation.py tests/unit/test_voice_stt_adapter.py tests/unit/test_voice_native_worker.py tests/unit/test_voice_lifecycle.py tests/unit/test_voice_vad.py tests/unit/test_ipc_request_contract.py tests/unit/test_p15_remaining_contracts.py tests/unit/test_stop_protocol.py tests/unit/test_p18_runtime.py tests/unit/test_runtime_shutdown.py tests/unit/test_ipc_versioned_pipe.py -p tests.fixtures.desktop_isolation
```

These preserve typed admission, STOP, task/worker ownership, guarded shared
execution, verification/undo and factual/private history. Stream and tool
fixtures are inert or owned; they are not physical/model acceptance.

An initial native run reproduced the added observer crowding out initial status:
the dashboard remained unable to submit. Starting voice after that bounded read
resolved it without expanding IPC capacity or weakening STOP. Existing P18
whole-shell assertions remain and pass. A test cleanup error initially masked
the failure; its diagnostic now prints the original failure before teardown.

## Native Windows UI and artifact identity

[Windows gate 41403835475](https://github.com/sai161812/pluma/actions/runs/41403835475)
passed on the exact tested source:

- **247 IPC / 176 native UI / 663 native popup / 195 formatting** checks.
- Existing layout/surface/audio/copy gates pass; builds have zero warnings/errors.
- Actual MainWindow acceptance covers measured listening/VAD, literal partials,
  no fabricated commit, preserved reader/tail, actual admitted final text,
  navigation, disconnect/reconnect, new generation, clarification, empty input,
  denial, timeout, capture/STT STOP and joined shutdown. It uses owned pipes,
  storage and inert speech adapters; it is native UI evidence, not a microphone
  or native-model claim. Existing P18 saturation/priority STOP and WAL checks pass.
- Final local native window run also passed **176 UI checks**. Local UI/IPC
  builds have zero warnings/errors. Native popup/gallery voice renders were
  inspected for the unchanged dark card and readable committed viewport.
- Artifact `13122379322`, SHA-256
  `8f7a7c57f07b3318e0a90a2a711d765a4b5f8ff199ed60c01c1e1dad52eb6c4c`,
  was downloaded and digest-verified before inspection. Preview executable
  SHA-256: `F85BC36F0B8403F63CF9C7129A803FE8E6AE323CAE9466B021E45C94E81215E5`.
  It is unsigned test output; signing/release remains P28-P31.

The workflow ran `PLUMA.UI/verify-ui.ps1`; relevant local commands were:

```powershell
dotnet build PLUMA.UI/CoreIpc.Tests/CoreIpc.Tests.csproj --verbosity quiet -p:UseSharedCompilation=false
dotnet build PLUMA.UI/SurfaceControls.Tests/SurfaceControls.Tests.csproj --verbosity quiet -p:UseSharedCompilation=false
dotnet run --no-build --project PLUMA.UI/SurfaceControls.Tests/SurfaceControls.Tests.csproj --verbosity quiet
```

The native runner writes `control-tests.txt`; an empty console/exit alone was
not counted as a pass. `PLUMA_TEST_PYTHON` selected the isolated Python fixture
environment. No Windows security policy was changed or bypassed.

## Actual local models and physical capture

On the same source, with isolated APPDATA/LOCALAPPDATA/PLUMA_CONFIG:

```powershell
output/p14-native-env/Scripts/python.exe -m tests.windows.p19_recognition_acceptance --model output/p14-native/ggml-base.en.bin --sample output/p14-native/jfk.wav --report <root>/recognition/report.json
output/p14-native-env/Scripts/python.exe -m tests.windows.p14_native_stt_acceptance --model output/p14-native/ggml-base.en.bin --sample output/p14-native/jfk.wav --report <root>/native-stop/report.json
output/p14-native-env/Scripts/python.exe -m tests.windows.p14_material_target_acceptance --model output/p14-native/ggml-base.en.bin --sample output/p14-native/material-clarification-sapi.wav --report <root>/clarification/report.json
output/p14-native-env/Scripts/python.exe -m tests.windows.p14_voice_planner_acceptance --model output/p13-native/model/Qwen3-4B-Q4_K_M.gguf --stt-model output/p14-native/ggml-base.en.bin --speech-sample output/p14-native/p14-c05-native-planner.wav --report <root>/models-combined/report.json
output/p14-native-env/Scripts/python.exe -m tests.windows.p14_voice_device_acceptance --model output/p14-native/ggml-base.en.bin --report <root>/device-final/report.json
```

- Actual Whisper segments before final delivery, STOP after a genuine segment,
  deadline, original-worker absence, independent SQLite cleanup and cold parent
  pass in **4.6852 s**. The callback barrier establishes STOP before final delivery;
  it is not physical or mid-decode latency evidence.
- Actual CPU-STT STOP passes after **0.1875 worker CPU seconds observed**, with
  original-process absence and ledger cleanup. No latency percentile is claimed.
- Native material speech produces clarification below the 0.65 threshold, with
  no admitted tool, attached transcript or persisted speech.
- Actual Whisper -> Qwen complex read-only file planning passes: confidence
  **0.6982215566212651**, list_folder/file_info voice/text SMART parity, owned
  fixture paths/results, same-capsule commitment readback, verified ledger and
  worker absence. Decoding was not called committed before real admission.
- The combined run used pywhispercpp **1.5.1** and llama-cpp-python **0.3.36**.
  PYTHONPATH contained the absolute p14-native-env and p13-native-env
  `Lib/site-packages` directories, in that order. The initial p13-only attempt
  failed because Whisper was absent; it is retained as a failed environment
  attempt. No application dependencies or existing test environment were changed.
- The physical default AMD microphone opens only on PTT, exposes same-capsule
  measured 32-band readback, and closes on release/STOP. Capture STOP exposes
  CANCELLED with no text or meter, admits no processing and verifies closure via
  SQLite. This uses a physical input and discards PCM; it does not assess human
  transcription accuracy. Models use explicit recorded/generated fixtures.

## Owner-approved physical timing limitation

Fresh C-02 speaker-to-microphone timing attempts did **not** pass. MME input 1 /
Realtek speaker at fixture gain 0.5 failed 0/3, then gain 1 failed 0/3: only
0-5 speech-active frames were captured, insufficient to establish the boundary.
Every capture closed. WASAPI input 9 refused the fixed 16 kHz stream with
Invalid sample rate, so that attempt established no timing evidence. Windows
speaker/microphone volume and mute were read without mutation; thresholds and
timing assertions were not changed.

After these results were disclosed, the owner explicitly answered:
**"Defer this physical timing retest to P25".** This approves only this concrete
physical C-02 timing retest limitation under AGENTS.md. E78's earlier passing
physical evidence remains historical evidence, not a fresh pass. The failed
attempts remain recorded; P25 owns an audible external-speech/device route and
three passing timing/closure trials. No requirement was deleted or made optional.

## Checkpoint and recovery

Full logs, artifact, model/device reports and source/build hashes are under the
ignored root named by `output/p19-overlay-current.txt`. No raw microphone PCM,
speech previews or personal desktop data were persisted. Explicit source audio
fixtures remain only under ignored output. Traceability and diff checks pass.

Remaining P19 implementation packets: **none**. The concrete physical timing
retest above is transferred to P25 by owner approval. Human-speech quality,
broader scenarios, physical taskbar/DPI/accessibility, measurements, security and
release gates retain their later milestone scopes.

Ready for independent Sol review; approval is not assumed. Next safe milestone
is P20 (history/details/undo/conflicts), only after owner instruction. No P20
work or merge was performed. Recover via a reviewed revert toward `fe5888d`,
preserving unrelated work; never reset/clean/force-push automatically.
