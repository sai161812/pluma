# E78 - P14 C-02 physical-device follow-up

Current completion disposition: [E79](p14_e79_clarification_privacy.md) repairs
the later clarification/privacy findings. The physical C-02 results below
remain valid; E78 alone did not establish those additional invariants.

**Status:** The false-pass timing defect is fixed and unit-tested. The
acceptance harness records the selected input and captured speech-frame timing
without persisting raw microphone audio. A pass now requires captured VAD-active
speech followed by the configured 600 ms silence (with at most one 30 ms frame
of capture slack), in addition to the playback-relative timing bound. The final physical run passed all
three trials using the built-in AMD microphone and Realtek speaker. This closes
the last mandatory P14 backend gate; P14 is complete and P15 has not started.

## What changed

The C-02 harness accepts an explicit `--input-device-index`, selects that
physical input only for its own process, pairs it with an output on the same
PortAudio host API, and restores the process's previous device defaults. Each
trial now reports whether the captured transient buffer contained VAD-active
speech frames and their timing, without storing the PCM. This distinguishes a
real speech-boundary measurement from a completion flag produced when the
fixture did not reach the selected microphone.

The E77 implementation still compares the stop against the fixture's final
speech activity plus configured trailing silence, with -100 ms maximum early
and +750 ms maximum late allowance. Unit coverage rejects the previously
accepted stop 100 ms before speech ends and tests both bounds.

## Verification

Focused unit tests:

```powershell
& .\output\p14-native-env\Scripts\python.exe -m pytest tests/unit/test_voice_orchestrator_integration.py tests/unit/test_voice_pipeline.py tests/unit/test_voice_boundary_acceptance.py -p tests.fixtures.desktop_isolation -q
# 29 passed; zero failures, skips or xfails.
```

Affected P14 regressions:

```powershell
& .\output\p14-native-env\Scripts\python.exe -m pytest tests/unit/test_voice_capture.py tests/unit/test_voice_vad.py tests/unit/test_voice_session.py tests/unit/test_voice_pipeline.py tests/unit/test_voice_orchestrator_integration.py tests/unit/test_voice_native_worker.py tests/unit/test_phase13_7_voice_stop.py tests/unit/test_activity_ledger_lifecycle.py tests/unit/test_db.py tests/unit/test_voice_activation.py tests/unit/test_voice_lifecycle.py tests/unit/test_app_lifecycle.py tests/unit/test_runtime_shutdown.py tests/unit/test_worker_cancellation.py tests/unit/test_voice_boundary_acceptance.py -p tests.fixtures.desktop_isolation -q
# 184 passed; zero failures, errors, skips or xfails.
# Full output: ignored output/p14-native/p14-gap-regressions-e78-final.log
```

Physical C-02 with the connected headset's MME input/output pair:

```powershell
& .\output\p14-native-env\Scripts\python.exe tests\windows\p14_voice_boundary_acceptance.py --sample output\p14-native\material-clarification-sapi.wav --input-device-index 2 --output-device 'Headphones (Noise Buds VS104)' --gain 0.2 --repetitions 3 --report output\p14-native\voice-boundary-e78-headset-profile.json
# Failed 0/3. Captured speech-active frames: 0, 0, 0. Capture streams closed.
```

The headset Hands-Free WDM-KS pair also accepted 16 kHz and failed 0/3 with
zero captured speech-active frames:

```powershell
& .\output\p14-native-env\Scripts\python.exe tests\windows\p14_voice_boundary_acceptance.py --sample output\p14-native\material-clarification-sapi.wav --input-device-index 17 --output-device Headset --gain 0.2 --repetitions 3 --report output\p14-native\voice-boundary-e78-headset-wdmks.json
# Failed 0/3. Captured speech-active frames: 0, 0, 0. Capture streams closed.
```

The reports and logs are under ignored `output/p14-native/`. They contain
device names and VAD timing summaries only; neither raw audio nor transcript was
written. The headset trials above remain failed because those routes captured
no speech. The final built-in microphone and Realtek speaker route did receive
the fixture and passed the configured timing and cleanup checks.

## Final physical C-02 result (2026-10-26)

The AMD microphone array on MME input index 1 captured speech played through the
Realtek speaker. Three consecutive final trials passed. Playback-relative
timing errors were 429.7 ms, 429.8 ms and 429.8 ms, within the configured
-100 ms early and +750 ms late bounds. The captured-buffer boundary error was
0 ms in all three trials: detected speech was followed by exactly 600 ms of
silence. Captured VAD-active frame counts were 110, 104 and 109. Each trial
observed the VAD boundary, a stable buffer, inactive capture stream at the
boundary, and a closed stream after release. Raw PCM and transcript were not
saved.

```powershell
& .\output\p14-native-env\Scripts\python.exe tests\windows\p14_voice_boundary_acceptance.py --sample output\p14-native\material-clarification-sapi.wav --input-device-index 1 --output-device 'Speaker (Realtek(R) Audio)' --gain 0.5 --repetitions 3 --report output\p14-native\voice-boundary-e78-amd-realtek-final.json
# passed 3/3; playback-relative timing errors 429.7, 429.8, 429.8 ms; captured-boundary errors 0 ms.
```

## Disposition

- Clipboard preview redaction, extensionless file-read clarification, and
  native Whisper-to-Qwen complex-file planning remain verified by E77.
- C-02's asymmetric playback timing criteria, captured-speech/600 ms tail
  requirement, and premature-stop regression pass.
- C-02 physical boundary timing is **PASS** on the built-in microphone and
  speaker path; all three trials met the unchanged timing bounds and cleanup
  checks.
- The P14 backend gate is complete. The next milestone is P15; it has not
  started.

Recovery point before E78: `894fdbc` (`Close remaining P14 voice gaps`) on
`p12-preparation`. No branch switch, reset, merge or force push was used.
