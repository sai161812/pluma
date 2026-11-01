# E92: P19 native recognition-segment prerequisite

Date: 2026-11-02. Branch: `p12-preparation`.
Recovery: `34b67362c4429fc43a9cf9c640b0dbdd427fbc8c` (E91).
Tested production/test source: `196574118815ed912ef41908ec8b0ee027916aed`,
following implementation `dd405eb`.

**This bounded packet is complete; P19 remains in progress.** P19 explicitly
permits a separate slice for its missing partial-result contract. This closes
that backend prerequisite; it does not claim surfaces 11-14 are wired.

## Prerequisites and source inspection

The unchanged complete master was reused; Git blob
`01b693dbf898b662aa4cd67736c1a0e8a21cf3e3` was refreshed. AGENTS, shared/P19
prompts, latest handoff, applicable voice/build gates and matrix rows were read.
The checkout was clean at E91, with the authorized branch/remotes/worktrees
inspected. No branch switch, merge or unrelated work was performed.

P00-P15 claims retain their documented scopes, rather than blanket certification.
E80's earlier safety/privacy findings and E81-E84 typed IPC contracts were checked
against current voice/session, registry, supervisor, pipeline, lifecycle and
request source. Their affected prerequisites ran before editing: **212 passed
in 24.00 s**, without skips/xfails. Existing P14 native/device evidence is retained
within its recorded scope; E91 supplies unchanged UI/host evidence. No fresh
physical microphone, planner-model or P19 UI acceptance is inferred from it.

The actual adapter returned only a final result. Installed pywhispercpp 1.5.1
provides a real `new_segment_callback` during decoding. Its callbacks contain
newly decoded segments, not token hypotheses or capture-time transcription.
A short utterance may yield only one callback; no extra partials are invented.

## Implemented contract

- `WorkerRequest.recognition_updates` opts only `voice_stt` into a scoped owned
  worker channel. The controller requires an observation owner, matching task,
  strict contiguous integer sequence, nonempty text and UTF-8 bounds. Other
  calls keep the default disabled. Unexpected/out-of-order frames fail closed.
- The real native binding callback publishes segments before the final worker
  response. Final returned segments are never replayed as manufactured progress.
- `TaskCapsule.recognition_progress` owns one volatile inference generation and
  is excluded from capsule serialization. `RecognitionSnapshot` is an internal
  immutable contract, **not a new public UI IPC endpoint or ledger event**.
- States are DECODING, RECOGNIZED, EMPTY, FAILED, CANCELLED, TIMED_OUT and
  UNAVAILABLE. RECOGNIZED means decoded text, not request admission or commitment.
  Material confidence checking, normalization, clarification, routing, policy,
  ToolSpecs, verification and undo remain in the existing pipeline.
- At most 128 updates, 4096 UTF-8 bytes per segment and 16384 bytes of preview
  are retained. Oversized preview is withheld; execution input is not truncated.
  Reads have a 20 ms lock bound. No observer thread, timer, capture loop or model
  is started by this contract. A new inference gets a distinct generation ID.
- Prefix copy passes the canonical whole-command redactor. Raw incremental text
  is private in memory and cleared at completion/failure; no preview is logged,
  journaled or written to history. Until later segments arrive, partial text can
  be incomplete or not yet classifiable; it must stay transient, not enter the
  Activity feed or be used as an execution/confirmation API.
- STOP/timeout suppress text at snapshot and publication. Failure cannot be
  reanimated by a late final result. Missing/empty speech does not imply commit.

## Reproduced defects and bounded corrections

1. The first actual callback-enabled inference failed model-unload verification.
   The binding retains the bound Model callback in native parameters; GC alone
   did not release it. The adapter now unregisters segment/abort callbacks before
   releasing the model. Unregistration failure remains a failed/unverified
   result. Native success and a deterministic cleanup-failure regression pass.
2. Native cancellation after a genuine segment exposed a retired-admission race:
   the supervisor could retire the event before the waiting controller unwound,
   yielding a closed-handle error instead of cancellation. Repeated controller
   cleanup now tolerates an already-retired gate, preserves the first cause and
   still performs owned termination/absence readback. No live cancellation or
   cleanup check was removed; real process and disposal regressions pass.
3. The prior native absence helper compared Windows FILETIME with Unix seconds,
   so it could accept a live worker as absent. It now converts units, uses zero
   relative tolerance, and checks identity around CPU sampling. The regression
   rejects a matching live identity and distinguishes a reused PID. The real
   native callback harness positively checks its worker alive before STOP and
   absent afterward, independently of controller and SQLite cleanup evidence.

## Verification

Final source has **282 affected passes in 42.63 s**, no skips/xfails:

```powershell
output/p14-native-env/Scripts/python.exe -m pytest -q tests/unit/test_p19_recognition.py tests/unit/test_voice_session.py tests/unit/test_voice_native_worker.py tests/unit/test_voice_pipeline.py tests/unit/test_voice_orchestrator_integration.py tests/unit/test_voice_stt_adapter.py tests/unit/test_voice_lifecycle.py tests/unit/test_worker_cancellation.py tests/unit/test_executor_admission.py tests/unit/test_worker_disposal_cause.py tests/unit/test_stop_protocol.py tests/unit/test_p18_runtime.py tests/unit/test_redaction.py -p tests.fixtures.desktop_isolation
```

The pre-edit 212 selection additionally covered capture, activation, VAD and
P15 request/remaining contracts. Fixtures were inspected; microphone capture
uses an inert stream seam, and the desktop-isolation plugin protects affected
orchestration fixtures. Fixture assertions are not physical acceptance.

Actual native commands, both exit 0 on tested source:

```powershell
output/p14-native-env/Scripts/python.exe -m tests.windows.p19_recognition_acceptance --model output/p14-native/ggml-base.en.bin --sample output/p14-native/jfk.wav --report <packet-root>/native-final/report.json
output/p14-native-env/Scripts/python.exe -m tests.windows.p14_native_stt_acceptance --model output/p14-native/ggml-base.en.bin --sample output/p14-native/jfk.wav --report <packet-root>/native-regression-final/report.json
```

`<packet-root>` is recorded in ignored `output/p19-recognition-current.txt`.
APPDATA, LOCALAPPDATA and PLUMA_CONFIG were isolated; each harness creates its
own runtime storage. Full logs, reports and source hashes stay under that root.

- Windows, CPython 3.12.10, pywhispercpp 1.5.1; native GGML base.en model SHA-256
  `a03779c86df3323075f5e796cb2ce5029f00ec8869eee3fdfb897afe36c6d002`.
- Decoded owned public-fixture PCM SHA-256
  `a29462b8ebd467318000e683b9117ade46230d3255ed2024e7db894abd9b38c9`.
- New native acceptance: **passed in 4.4788 s**. One genuine callback was observed
  before the final result and matched the final native segment prefix. STOP
  after a genuine segment suppressed text/final delivery; a real owned deadline
  ended TIMED_OUT with worker absence and ledger readback. All three cases pass.
- The cancellation test uses an explicit parent callback barrier, not simulated
  speech. It establishes STOP before final delivery, not mid-decode latency.
  The deadline may expire at startup/model load; it is not advertised as a
  decode-time performance measurement.
- Fresh P14 native regression recognized 22 fixture words with confidence
  0.772101476623658 and verified STOP after **0.2031 CPU seconds observed** in
  the identity-matched worker, then caller cancellation/absence/SQLite cleanup.
- Parent native bindings stay unloaded, lifecycle returns COLD, owned worker
  maps drain, and runtime storage contains no PCM/WAV/raw audio. Reports contain
  only counts/hashes/identities. No microphone, personal clipboard, windows,
  browser profile, power state or personal files are touched.

No C#/XAML source changed. E91's native UI/placement evidence is reused only for
those unchanged surfaces; **no P19 UI or physical-device pass is claimed**.
Traceability and diff checks pass; no Windows security policy was bypassed.

## Remaining P19 work and next safe packet

1. Add the typed transient voice lifecycle/readback bridge: capture/VAD, decoding,
   real request commitment, clarification, empty/denied/error/timeout outcomes,
   scope/generation, reconnect/reset and terminal retention. The internal
   recognition snapshot alone must not become a committed-request signal.
2. Bind the existing single VoiceOverlay (11-14), preserving dark classes,
   viewport/reading/tail behavior, real waveform/recognition provenance and no
   production samples. P19's C# IPC consumer is not implemented by this packet.
3. Complete native UI/core and permitted real-device acceptance: capture/STT
   STOP, denial, silence, low-confidence clarification, text/voice parity,
   reconnect and shutdown, with fresh model/device evidence distinguished.

Next safe packet is (1), then scoped overlay wiring and acceptance. This packet
is ready for independent Sol review; approval is not assumed. P20 has not started.
Recovery is a reviewed revert of this packet toward `34b6736`, preserving unrelated
work; never reset, clean, merge, switch branches or force-push automatically.
