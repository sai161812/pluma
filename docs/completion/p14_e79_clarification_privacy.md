# E79 - P14 clarification and spoken clipboard privacy closure

Current completion disposition: [E80](p14_e80_audit_closure.md) supersedes the
blanket closure below after the later DPI, screen-context privacy, material
punctuation, FAST/schema and crash-test findings were reproduced and repaired.
E79's test counts remain historical evidence for its bounded packet.

**Status (2026-10-26):** The two findings discovered after E78 are repaired and
verified. Mandatory backend acceptance C-01 through C-09 is complete; C-10 is
optional. P15 has not started. This checkpoint supersedes E78's completion
claim while retaining its physical C-02 evidence.

## Findings and changes

1. Low-confidence quoted/extensionless filenames, additional clauses and spoken
   amounts could bypass the material-target keyword patterns. At confidence
   0.10, examples included `open "README"`, `read "LICENSE"`,
   `read LICENSE, then summarize it` and `set volume to half`.
   The pipeline now conservatively clarifies unresolved low-confidence speech.
   Only complete recognized app launches and an explicit set of commands with
   no material target are exempt. Every target-free exception is checked against
   the production router for one deterministic tool with no arguments. Unknown
   wording cannot enter the planner merely because it lacks a known extension,
   numeral or file noun. STOP remains exempt. High-confidence request text and
   original transcript are preserved through the normal shared pipeline.
2. The paste-word regex matched `pasteing` rather than `pasting`, allowing a
   spoken payload into voice/orchestrator INFO logs and command/original-
   transcript history. The canonical redactor now covers `paste`, `pasted`,
   `pastes`, `pasting`, `clip board` and `pasteboard`. Regression payloads no
   longer contain the word `clipboard`, which previously could mask a defective
   verb match. Synthetic sentinels are absent from INFO logs and SQLite
   command/original-transcript fields; the transient request stays routable.

Production changes are limited to `pluma/voice/pipeline.py` and
`pluma/memory/redaction.py`. Four focused test files add coverage. No capture,
native worker, planner, ToolSpec, policy or UI implementation changed.

## Verification

Environment: Windows, CPython 3.12.10, pytest 9.1.1, pywhispercpp 1.5.1,
sounddevice 0.5.6. Fixture tests used isolated storage/inert desktop adapters.
They did not access personal files, clipboard, application windows or devices.

The added regressions reproduced **24 failures and 88 passes** before the
production fix. An additional exception-to-router consistency check was then
added. Final focused run: **113 passed in 6.83 s**, no failures, errors, skips
or xfails.

```powershell
& .\output\p14-native-env\Scripts\python.exe -m pytest tests/unit/test_voice_pipeline.py tests/unit/test_voice_orchestrator_integration.py tests/unit/test_voice_session.py tests/unit/test_redaction.py -p tests.fixtures.desktop_isolation -q
```

Affected voice, STOP/ownership, lifecycle, ledger, redaction and routing
regressions: **425 passed in 23.82 s**, zero failures, errors, skips or xfails.
The focused count overlaps this run.

```powershell
& .\output\p14-native-env\Scripts\python.exe -m pytest tests/unit/test_voice_capture.py tests/unit/test_voice_vad.py tests/unit/test_voice_session.py tests/unit/test_voice_pipeline.py tests/unit/test_voice_orchestrator_integration.py tests/unit/test_voice_native_worker.py tests/unit/test_voice_stt_adapter.py tests/unit/test_phase13_7_voice_stop.py tests/unit/test_activity_ledger_lifecycle.py tests/unit/test_db.py tests/unit/test_voice_activation.py tests/unit/test_voice_lifecycle.py tests/unit/test_app_lifecycle.py tests/unit/test_runtime_shutdown.py tests/unit/test_worker_cancellation.py tests/unit/test_voice_boundary_acceptance.py tests/unit/test_redaction.py tests/unit/test_phase13_5_stage_f_redaction.py tests/unit/test_router.py -p tests.fixtures.desktop_isolation -q
```

Fresh actual whisper.cpp material-target acceptance exited 0 and reported
`passed`. Confidence was 0.6254661999 below 0.65: transcript-free clarification,
no command task/tool admission, cleanup readback and COLD state were verified.
The expected refusal warning appears on stderr. This used an explicit generated
audio fixture, not a microphone or injected transcript.

```powershell
& .\output\p14-native-env\Scripts\python.exe tests/windows/p14_material_target_acceptance.py --model output/p14-native/ggml-base.en.bin --sample output/p14-native/material-clarification-sapi.wav --report output/p14-native/material-target-acceptance-e79.json
```

Model SHA-1: `137c40403d78fd54d454da0f9bd998f78703390c`.
Fixture PCM SHA-256:
`4585b896e2cf254702064678093efe7b6e470df1240a904f92101f872b2717ea`.
No raw audio or transcript was persisted by this acceptance.

Full output stays under ignored `output/p14-native/`:
`p14-e79-before.log`, `p14-e79-focused.log`, `p14-e79-regressions.log`,
`material-target-acceptance-e79.log` and `material-target-acceptance-e79.json`.

Documentation verification passed: **298 source items / 324 traceable rows**,
with full requirement text, statuses and links preserved. Recorded hashes match
all six tested files. Python compilation and the whitespace check passed.

```powershell
& .\output\p14-native-env\Scripts\python.exe docs/completion/verify_requirements_matrix.py
& .\output\p14-native-env\Scripts\python.exe -m py_compile pluma/voice/pipeline.py pluma/memory/redaction.py tests/unit/test_voice_pipeline.py tests/unit/test_voice_orchestrator_integration.py tests/unit/test_voice_session.py tests/unit/test_redaction.py
git diff --check
```

## Retained gates and remaining scope

- [E74](p14_stt_worker.md): actual task-owned native STT cancellation/unload.
- [E75](p14_voice_acceptance.md): physical activation/STOP, transient audio and
  shared voice/text backend fixtures; [E76](p14_gap_repairs.md) adds polling-loop
  unit coverage and conservative per-segment confidence.
- [E77](p14_e77_gap_closure.md): actual generated-speech Whisper-to-Qwen
  `list_folder`/`file_info` acceptance, voice/text parity, same capsule, owned
  paths, file results, ledger readback and worker absence.
- [E78](p14_e78_c02_device_followup.md): three physical C-02 trials passed on the
  AMD microphone/Realtek speaker route with exactly 600 ms captured silence
  after speech. These capture files and the acceptance harness are unchanged
  from `299324e`; physical timing was not repeated for this text-only fix.

There are no known remaining mandatory P14 backend findings. The P19 visible
overlay/clarification surface and broader human-speech quality/latency and
release acceptance remain in their later milestones. C-10 spoken output stays
optional. Ready for independent Sol review; no review approval is assumed.

## Tested source identity and recovery

Recovery point: `299324e87ca95e620acc56e350fe0908c8ce9436` on
`p12-preparation`. The tested tree was based on that commit with the following
working-file SHA-256 identities before committing E79:

```text
pluma/voice/pipeline.py aa955ad60a51a6d73b06fa5d9555539682103efa6532aac81f20655b6da1f7e8
pluma/memory/redaction.py 0ddb8d0f8524ea6b017cc11be2f0f4609ea9d0a190d85d719fde976d08753316
tests/unit/test_voice_pipeline.py 74335e5b91da023c410bc93cafa3148f1f5d576a094acc6b249a4d3bfb12bbc6
tests/unit/test_voice_session.py 795c69c9ddcb205b5833096ac491634d2346e7877e4dd93c13ad7e3494c46f02
tests/unit/test_voice_orchestrator_integration.py 0cbffb61da1fab28be6b3509e99c45a567f83c4125722d59c0ce07bcfbdf54fb
tests/unit/test_redaction.py bb6fdbc02b45969f80e8075dc87e3de778a3f39deecce889e9a3caaa2d358508
```

No branch switch, reset, merge or force push was used. Next safe milestone is
P15's first bounded UI/core contract task after this checkpoint is reviewed.
Do not advance automatically.
