# E80 - P00-P14 audit finding closure

Date: 2026-10-27. Branch: `p12-preparation`.
Recovery/tested parent: `7ebd282adbe24c92b8d57d052ba27c01aeaf5481`.

The read-only audit of that parent found A1-A6. This packet repairs those
findings and an additional reproduced router-reason privacy leak. The assigned
P00-P14 backend gates are ready for independent Sol review and P15 preparation,
with the existing recorded owner-approved physical limits retained. No P15
implementation, UI styling change, merge, branch switch, reset or force push
was performed. This is not a claim of zero bugs or full-product readiness.

## Reproduction and repairs

| Finding | Repair and completion evidence |
|---|---|
| A1: failed/missing DPI silently became 100% | `ActiveWindowContext` refuses unknown DPI instead of inventing 96 DPI. Both observation APIs invalidate the context; production shared target admission refuses zero/error/missing reads before input. Four valid DPI ratios, including 131/96, remain exact. Current owned Win32/WPF acceptance passes. |
| A2: raw UIA/OCR secrets entered model prompts | Snapshot extraction carries the native password classification. Prompt construction excludes password controls and editable controls whose classification is unavailable, and redacts retained UIA labels/automation IDs/OCR labels. Direct prompt and actual adapter/custom-backend regressions verify exclusion without altering execution identities or raw snapshots. These are deterministic privacy fixtures, not native screen-model action acceptance. |
| A3: normalization changed material targets | Only recognized target-free commands and full known app launches receive whitespace/sentence punctuation normalization. Literal filename punctuation, globs and internal whitespace are preserved. High-confidence typed/voice rename arguments both retain `notes!`; uncertain-target clarification remains conservative. Numeric volume sentence punctuation is handled only inside that numeric rule. |
| A4: positive FAST examples violated current schemas | Production routing uses the orchestrator's actual registry and validates FAST calls before returning a plan. Unsupported app aliases, missing exact window identities and unresolved file roots refuse without policy/execution or guessing. Explicit `find ... in C:\PLUMA_Corpus` produces a schema-valid rooted search. Tool admission still validates again. Seventeen positive corpus examples now specify supported targets; all seventeen original commands remain refusal regressions. Three malicious/admin negatives require no plan and a refusal. No tool schema or ownership restriction was relaxed, no app was substituted at runtime, and this does not claim P24 corpus execution. |
| A5: crash fixture raced a closed Process handle | The fixture retains original PID/creation identity and positively verifies absence instead of calling `join` on a controller-retired handle. STOP latch, refusal of admission, failed/unverified result, absent late-execution marker, cleanup and closed-handle assertions all remain. Current prerequisites/catalog and three isolated repeats pass. No production STOP escape was established by the original test failure. |
| A6: contradictory evidence notes | Matrix notes now acknowledge the actual E59 fixed-DNS UAC result, registered `open_file`, and repaired BA backend gates while keeping live UI, scenario breadth and release acceptance open. Accepted command transcripts are distinguished from transient raw audio and transcript-free clarification. E79's blanket claim is explicitly superseded. |
| Additional privacy regression | Three initial tests using the real router reproduced clipboard payloads in generic SMART/SCREEN/DEEP reason logs despite redacted command previews. Generic explanations now contain deterministic routing facts without command excerpts. The orchestrator also projects a private-text-free reason for any full clipboard command before logging/returning it, including numeric-rule fallback; five real-router cases cover these paths. INFO output, returned reason and stored command/original-transcript fields exclude the payload. No route was injected in these regressions. |

Before source repairs, the first corrected focused reproduction had **10 failed /
86 passed** (`before-final.log`). The initial exploratory `before.log` also
included a test-fixture ctypes setup error; that fixture was corrected, not
counted as a product defect. The separate real-router privacy reproduction had
**3 failed / 9 deselected** (`router-privacy-before.log`). Final selections below
have zero failures, errors, skips or xfails. Counts overlap; do not sum them as
unique tests. Tests/fixtures were inspected before execution.

## Final verification

| Selection | Result | Evidence under ignored `output/p14-e80/` |
|---|---|---|
| Required prerequisite manifest, including all 15 original BA checks with `--runxfail` | 500 passed | `prerequisites.json/.log/.xml` |
| Safely selected catalog regressions | 1,236 passed | `catalog.json/.log/.xml` |
| Router, registry-schema, planner prompt, orchestration and freshness contracts | 352 passed | `contracts.json/.log/.xml` |
| P12 affected grounding, screen, OCR and adapter regression manifest | 244 passed | `p12.json/.log/.xml` |
| Actual owned Win32/WPF semantic providers | 10 passed | `native.json/.log/.xml` |
| P13 adapter/target/replan/prompt/redaction checks | 25 passed | `p13.json/.log/.xml` |
| P14 voice, STT, boundary, activation, privacy and router checks | 351 passed | `p14.json/.log/.xml` |
| Crash absence/admission repeat | 3 of 3 passed | `crash-repeat-1..3.json/.log/.xml` |
| Actual Whisper material-target clarification | passed, exit 0 | `native-material-command.json`, `native-material-report.json`, `native-material.log` |
| Actual Whisper to Qwen read-only complex file task and typed equivalent | passed, exit 0 | `native-complex-command.json`, `native-complex-report.json`, `native-complex.log` |

The catalog selection deliberately does not execute
`test_recycle_bin_native.py`, `test_cross_volume_move_native.py` or
`test_browser_native.py`: this repair does not require new recycling, volume or
browser-profile changes. These exclusions are not passes; unchanged catalog
behavior retains its bounded E55-E60/E73 evidence. Fixture/mock passes elsewhere
are not represented as physical audio, power, foreground interaction or browser
acceptance. Raw microphone capture, clipboard and personal profiles were not
accessed. The prerequisites/catalog/P12 selections preceded final reason-only
privacy hardening in the orchestrator; contracts, P14 and native combined checks
were rerun afterward. No adapter, ownership, STT/capture or cleanup implementation
changed between these selections. The earlier orchestrator SHA-256 was
`9bcb2c1c0772020a9434efc5aafb3776ecc1a3e181602d2d086e3464be711a82`; current identities are below. Owned file/window/process fixtures and isolated storage were used.

Commands and selections are recorded exactly in the JSON files above.
Reproduce the manifest groups with isolated APPDATA/LOCALAPPDATA/TEMP/TMP:

```python
import json, subprocess
from pathlib import Path
manifest = json.loads(Path('docs/completion/p12_check_manifest.json').read_text())
# Run each named group; preserve the desktop-isolation plugin in contracts.
# The catalog exclusions are explicit, not skips or native acceptance passes.
excluded = {'tests/unit/test_recycle_bin_native.py',
            'tests/unit/test_cross_volume_move_native.py',
            'tests/unit/test_browser_native.py'}
for group in ('prerequisites', 'catalog', 'contracts', 'p12', 'native'):
    args = [x for x in manifest[group] if group != 'catalog' or x not in excluded]
    subprocess.run(['output/p11-native-env/Scripts/python.exe', *args], check=True)
```

P13 additional command:

```powershell
output/p11-native-env/Scripts/python.exe -m pytest tests/unit/test_brain_llama_cpp_adapter.py tests/unit/test_planner_target_admission.py tests/unit/test_planner_route_replan.py tests/unit/test_brain_prompt_builder.py tests/unit/test_phase13_5_stage_f_redaction.py -q --runxfail
```

P14 affected command:

```powershell
output/p14-native-env/Scripts/python.exe -m pytest tests/unit/test_voice_session.py tests/unit/test_voice_pipeline.py tests/unit/test_voice_activation.py tests/unit/test_voice_vad.py tests/unit/test_voice_capture.py tests/unit/test_voice_lifecycle.py tests/unit/test_voice_stt_adapter.py tests/unit/test_voice_native_worker.py tests/unit/test_voice_boundary_acceptance.py tests/unit/test_voice_orchestrator_integration.py tests/unit/test_redaction.py tests/unit/test_router.py -q --runxfail
```

Native material command:

```powershell
output/p14-native-env/Scripts/python.exe tests/windows/p14_material_target_acceptance.py --model output/p14-native/ggml-base.en.bin --sample output/p14-native/material-clarification-sapi.wav --report output/p14-e80/native-material-report.json
```

Native complex-file command (only its child environment adds
`output/p14-native-env/Lib/site-packages` to PYTHONPATH so both installed
bindings are available):

```powershell
output/p13-native-env/Scripts/python.exe tests/windows/p14_voice_planner_acceptance.py --model output/p13-native/model/Qwen3-4B-Q4_K_M.gguf --stt-model output/p14-native/ggml-base.en.bin --speech-sample output/p14-native/p14-c05-native-planner.wav --report output/p14-e80/native-complex-report.json
```

Whisper confidence was **0.6254661999** below 0.65 for material clarification:
no transcript in the event/history, no command/tool admitted, cleanup read back
and lifecycle COLD. The generated complex-file speech scored **0.6982215566**;
actual Whisper and actual Qwen/llama-cpp-python 0.3.36 used the same voice task
capsule and the same SMART `list_folder` then `file_info` path as typed input.
Both tasks independently read back owned `note.txt` (49 bytes), file identity,
SQLite actions/terminal outcome and worker absence. Temporary fixture-drive
mapping was checked and removed. Runtime persisted no raw audio; accepted
non-sensitive command text remained factual ledger data, not hidden reasoning.
No transcript was injected. This is generated-speech evidence, not a general
human-speech accuracy measurement.

## Retained acceptance and P15 readiness

- P00-P10: the current prerequisites and catalog retain covered STOP admission,
  priority, cleanup, terminal/ledger agreement, shutdown and credential gates.
- P11: all 57 required non-screen names remain among 85 registered tools; all 73
  required Section 21 names, including 16 screen names, remain present. Current
  adapter dispatch, elevation cleanup and DNS postcondition regressions pass.
  E59's actual fixed-DNS UAC proof stands; no new elevation was requested.
- P12: E69's assigned E-01 through E-10 gate is retained with the unknown-DPI
  defect repaired. Current owned providers and affected regressions pass.
  Broad human-screen OCR quality/latency remains P26, not a new P14 claim.
- P13: native planner STOP/timeout/crash, idle and repeated-cycle evidence in
  E72/E73 remains limited to its recorded graph and build. Inference, worker,
  lifecycle and admission sources are unchanged by this repair. Current prompt
  privacy/adapter and native combined acceptance cover the changed boundary.
- P14: E74/E75/E76 retain native STT ownership/unload and permitted physical
  activation/STOP. E78's three physical timing trials remain valid because
  capture, VAD and boundary-harness sources are unchanged from that proof.
  C-03/C-04 literal parity, C-05 combined native planning, C-06 clarification
  and privacy have current evidence. C-01 through C-09 backend scope is closed;
  C-10 is optional. No new microphone run or physical accuracy claim was made.

Owner-approved deferred physical focus/audio/power checks remain recorded in
E57/E59/E73, not silently converted to passes. P15 protocol work, P16 native
confirmation UI, P19 visible voice/clarification, P24 full scenario corpus,
P25 physical UI, P26 broad quality/performance, security/install/release gates
remain outside this completion claim. The approved dark Windows UI is unchanged.

There are no known unresolved A1-A6 findings in this packet. Ready for independent
Sol review; approval is not assumed. Next safe packet, only when instructed:
P15's first versioned UI/core request, acknowledgement and terminal-readback
contract slice after inspecting current IPC and executor events. Do not begin
P15 automatically.

## Tested source identity

The tested working tree was based on the recovery commit above. SHA-256 hashes
below identify source/test contents rather than merely citing an old packet.
Full commands, logs, JUnit and the machine-readable hash list stay under ignored
`output/p14-e80/`. Python compilation, matrix structure/link checks and
`git diff --check` passed; the matrix remains 298 source items / 324 rows.

```text
pluma/brain/llama_cpp_adapter.py 013a980add1a94bf14ed94e258a1e8ab09e052a8e6d374efe180e1e61161a8f7
pluma/brain/prompt_builder.py 0df2d977b7be327fe959392056ec72a6c809fd21c5adfa6864e1f6c505280604
pluma/core/orchestrator.py 9c0327bef57b0c1d52f94166f16e38a07226fa053406a33ab281fd8d366754fd
pluma/core/router.py e533700309113c6adb497404b09f014eefec681766233090a1a09b6806835224
pluma/perception/context.py e83d23d08994e49ad88b7abcab021853c1a7633030b1361240a76f9f9631df52
pluma/perception/uia_snapshot.py f27af414a9bcbf2b0dbd715c69f014dd8b8b8db553f3a6c933d8f01fad84779e
pluma/voice/capture.py 0bae4cb69d6702995431952489cc87a433d19722762b5f8aa2b462dd266a4bbc
pluma/voice/pipeline.py 603e33e094a779c927a08d8b9d4926d5567b4f3076f18f51e206ab0b98807b4b
pluma/voice/stt_adapter.py 45af79accec2e18379c5c31008786e1504301b39138c614c835e6179e8ccc28f
pluma/voice/vad.py a843cb9543d6f85f69b00b313208069e0958f53d51c6cd60341f220068563a92
tests/unit/test_brain_prompt_builder.py e7e7f1c3a4564e0d02be665ff87fc677ff96d153b47eef97275fc5c5b35b3852
tests/unit/test_executor_admission.py c76156888053d6e7e646ac798c0adb123094c9306b64e4a59dd85f0d66797ed5
tests/unit/test_fast_orchestrator.py f2759006ece8a3fc36355a86fb4152fd32547fe4b26bd679ce51cd906f59cef4
tests/unit/test_p12_completion_guards.py aa8ae9b3605cf67a94795542423e191f4b3e3a868dfbbc7e24b901fdbb7326fe
tests/unit/test_perception_context.py 2debd773eff6d154db2046984e28428caf03eba21a896da0a0e180ff24ca52da
tests/unit/test_perception_uia_snapshot.py de6e49f193e93335bf3b5859f0e4a3110523664a349802343d2b8ccbff43af81
tests/unit/test_phase13_8_final_patch.py 86553557a2c6f8bd55efc62e510262c10ae13e833f953115a48340b4f0b80c3c
tests/unit/test_router.py d24552e54c6ffae332962d44f724eaea5796dac9d9733a5dd09ad8c8eb30a965
tests/unit/test_voice_orchestrator_integration.py fe8ceb3bd5382030b9ad9e7ba9a74537977a6898f36c87b3fb4d5807437794ef
tests/unit/test_voice_pipeline.py 0a7badb0bae59e2247245bcabdb5a5280bd8e2c81a90936c5803ef1f659149b3
tests/windows/p14_material_target_acceptance.py 5bd6b40ee2a9eaebb49e82343dfa118adbec7c4512722bf6ff414301c335fad9
tests/windows/p14_voice_boundary_acceptance.py e24267b3b05e595d680875e540a07b3f2ddfc6e4ba8e06300e0f74be5aea1598
tests/windows/p14_voice_planner_acceptance.py 594c4fe54dd21c922054d5d36befb69e57fb265aef746e758c6f85aa8e096c46
```
