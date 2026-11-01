# E93: P19 typed transient voice lifecycle bridge

Date: 2026-11-02. Branch: `p12-preparation`.
Recovery: `f7df3108327951e288519140d49d2c25f8596dff` (E92 checkpoint).
Tested source: `4d0d6cf53416e2aed6323f3822508d1bfa6a0dce`.

**This bounded packet is complete; full P19 is still in progress.** This closes
E92's next lifecycle/readback prerequisite in Python and C#. It does not bind
the overlay controls or establish physical microphone/UI acceptance.

## Prerequisites and scope

The unchanged complete master was reused and its blob refreshed:
`01b693dbf898b662aa4cd67736c1a0e8a21cf3e3`. AGENTS, the shared execution
contract, P19, E92/latest handoff, matrix, voice source/tests and applicable
Phase 6/14 and C-01 through C-09 requirements were inspected before editing.
The authorized branch was clean at `f7df310`; no branches were switched, merged
or reset. Existing P00-P18 evidence retains its stated scopes and limitations.
Fresh affected prerequisites passed **212 checks in 32.11 s**, with no skips or
xfails. This is not a fresh whole-project or physical audit.

The gap was a final/partial-recognition contract without typed capture,
clarification or real request-admission readback. Files changed are:

- `pluma/voice/presentation.py`: one volatile presentation generation.
- `pluma/voice/capture.py`: bounded atomic metadata observation, without PCM.
- `pluma/core/task_supervisor.py`: excluded capsule presentation owner.
- `pluma/core/resident.py`: real lifecycle publication and read-only query.
- `pluma/core/orchestrator.py`: commitment after same-capsule execution admission.
- `pluma/core/ipc_contracts.py`: strict request/response models.
- `PLUMA.UI/PLUMA.UI/CoreVoiceProtocol.cs` and `CoreIpcClient.cs`: matching strict
  native DTO/parser and authenticated read-only client method.
- Both test-host project files link the new contract; Python bridge tests,
  `VoiceChecks.cs` and `CoreIpc.Tests/Program.cs` exercise the contract.

No XAML, popup placement, theme, visual class, tool implementation, policy,
verification, undo recipe or durable ledger schema changed.

## Contract and evidence boundaries

`voice_query` is a normal authenticated v1 read, not a mutation, subscription,
planner entry or voice trigger. It requires a canonical query `request_id` and
accepts nullable `stream_id` and `voice_id`; a voice ID requires its stream.
Unknown fields and invalid identities are refused before handling.

`voice_snapshot` always includes query identity, resident `stream_id`, explicit
`reset_required`, and nullable `voice`. It contains at most the latest generation.
A different stream/generation, including expiry to null, requires replacement
of the old view. Reconnect reads the current snapshot; there is no historical
transcript replay. The future UI controller must serialize reads, correlate
responses, clear stale state on failure/reset and own its cancellation lifetime.

The nested view has generation/task identities, nullable committed request ID,
phase/code, nullable capture/boundary facts, recognition identity/sequence and
bounded redacted text. Phases are STARTING, LISTENING, DECODING, COMMITTED,
CLARIFICATION, EMPTY, ERROR, CANCELLED and TIMED_OUT.

- LISTENING follows successful capture startup. Atomic recording and boundary
  metadata come from the capture object, not animation or inferred duration.
  Unknown adapter metadata remains null. An actual VAD boundary is not called a
  timeout; silence/empty returns EMPTY. No automatic silence-commit is invented.
- DECODING may contain E92's real native segment prefix. A recognized final
  result alone cannot set COMMITTED. The orchestrator enters its execution gate,
  starts the same capsule, and then publishes request commitment with matching
  task/token/request ownership. It does not claim successful tool execution.
- Low-confidence material speech publishes CLARIFICATION with no transcript,
  guessed target or admitted request ID. PermissionError at capture startup is
  CAPTURE_DENIED; other startup failures are CAPTURE_UNAVAILABLE. Other voice
  failures use VOICE_FAILED. Raw exception/driver details are never projected.
- STOP/timeout dominate active capture/decoding and suppress preview text. Late
  recognition or commitment cannot revive a cancelled voice generation. An
  already committed request remains a historical voice-admission fact; subsequent
  tool STOP, failure, undo and outcome still use the existing task APIs.
- Terminal readback expires after 30 monotonic seconds. Expiry is checked lazily
  on reads, clears presentation text and releases the resident's latest pointer.
  This is bounded one-generation storage, not a timer-based memory-erasure claim.
  Existing supervisor ownership remains authoritative for still-running work.
- Each observation lock acquisition is bounded to 20 ms. Busy, changed-generation
  or inconsistent ownership reads return VOICE_UNAVAILABLE without a stale view.
  Reads start no timer, observer thread, microphone, model or worker. Presentation
  is excluded from capsule serialization; previews are not ledger/feed events.

As in E92, early speech prefixes may be incomplete or not yet classifiable. They
are transient display data and must never enter Activity/history/logging or be
used as an execution API. Complete-command redaction precedes text limits.

Startup inspection also found that an exception could leave a session marked
unreleased, blocking a later push-to-talk attempt despite verified closure.
The failure path now releases its session state, retains any unclosed owner and
allows retry only when closure is verified. The existing missing-capture test
caught an initial stale-session regression during development; it was fixed
without weakening that assertion. The denial/retry and closure regressions pass.

A separate shutdown reproduction closed the execution gate after voice decoding
but before a capsule STOP latch. `execute` raised TaskCancelledError before
entry, while the resident had already marked it dispatched. The prior handler
left a nonterminal CREATED capsule and decoding view. The new regression first
failed on that exact condition. The handler now records a voice error and
finalizes that non-admitted capsule; an actual latched STOP/deadline retains its
first cancellation cause. No executor is entered and no commitment is invented.

## Verification

Logs are under the ignored directory in `output/p19-lifecycle-current.txt`.
APPDATA, LOCALAPPDATA and PLUMA_CONFIG were isolated. Stream fixtures are inert;
no personal files, clipboard, browsers, power state or microphone were used.
Native IPC fixtures create private test credentials, pipes and SQLite storage,
retain owned process identities and close/join their fixture hosts.

Final affected Python selection: **324 passed in 40.45 s**, no skips/xfails:

```powershell
output/p14-native-env/Scripts/python.exe -m pytest -q tests/unit/test_p19_voice_bridge.py tests/unit/test_p19_recognition.py tests/unit/test_voice_session.py tests/unit/test_voice_pipeline.py tests/unit/test_voice_orchestrator_integration.py tests/unit/test_voice_capture.py tests/unit/test_voice_activation.py tests/unit/test_voice_stt_adapter.py tests/unit/test_voice_native_worker.py tests/unit/test_voice_lifecycle.py tests/unit/test_voice_vad.py tests/unit/test_ipc_request_contract.py tests/unit/test_p15_remaining_contracts.py tests/unit/test_stop_protocol.py tests/unit/test_p18_runtime.py tests/unit/test_runtime_shutdown.py tests/unit/test_ipc_versioned_pipe.py -p tests.fixtures.desktop_isolation
```

This includes 31 bridge checks, actual orchestrator/owned-ledger admission,
recognition without commitment, closed admission refusal, capture failure/retry,
STOP and timeout text suppression, independent SQLite cleanup readback,
clarification, silence, generation/reset/expiry, redaction, ownership mismatch,
bounded busy reads, strict replies and shutdown. Existing regressions preserve
guarded routing, verification/undo, priority STOP and factual history. Inert
speech/tool fixtures are not native recognition or physical-device acceptance.

Native Windows C# commands:

```powershell
dotnet build PLUMA.UI/CoreIpc.Tests/CoreIpc.Tests.csproj --verbosity quiet -p:UseSharedCompilation=false
dotnet build PLUMA.UI/SurfaceControls.Tests/SurfaceControls.Tests.csproj --verbosity quiet -p:UseSharedCompilation=false
dotnet run --no-build --project PLUMA.UI/CoreIpc.Tests/CoreIpc.Tests.csproj --verbosity quiet
```

`PLUMA_TEST_PYTHON` pointed to the absolute path of
`output/p14-native-env/Scripts/python.exe`. Both builds passed with **zero
warnings/errors** (4.23 s / 32.27 s). The final local native runner passed
**239 IPC checks**, including strict new voice DTOs, all lifecycle phases,
invalid/oversized/contradictory evidence, authenticated cold-state Python voice
queries and reconnect identity, existing real request/history/confirmation
interoperability and saturated-handler priority STOP. Final run exited 0 on
the recorded source. A native UI host build is not a rendered-overlay test.

Intermediate test failures (incorrect test API usage, the missing-capture
regression and a mistyped test filename that collected nothing) are not counted
as passes. All corrected required selections above passed. No Windows security
policy was changed or bypassed. Traceability and whitespace checks pass.

E92's actual Whisper callback/cleanup evidence remains applicable to unchanged
STT transport; this packet does not claim a new model or microphone pass.
Full logs, source hashes and built IPC-runner hashes remain under ignored output.

## Remaining P19 and recovery

1. Bind the existing single VoiceOverlay (11-14) to these contracts. Own/cancel
   polling and reconnect state, remove production samples, preserve reading/tail
   behavior, fixed viewport and dark styling. Add bounded measured audio/VAD
   progress needed by the existing visualizer; this packet exposes capture/
   boundary metadata, not waveform amplitudes or a silence countdown. Never
   manufacture those values from animation or elapsed UI time.
2. Finish native UI/core and permitted device acceptance: capture/STT STOP,
   denial, empty/boundary/timeout, clarification, voice/text parity, generation
   replacement/reconnect and shutdown. Distinguish rendered fixtures, native
   models and physical microphone evidence; do not substitute one for another.

Next safe packet is overlay/controller binding with focused native host checks.
This bridge packet has no outstanding failed check and is ready for independent
Sol review; approval is not assumed. P19 is not declared complete and P20 has not
started. Recovery is a reviewed revert toward `f7df310`, preserving unrelated
work; never reset, clean, force-push, switch branches or merge automatically.
