# E112 - P24 owned mutation and confirmation acceptance

Date: 2026-11-10 (Asia/Calcutta)
Tested source baseline: `d3df79308aa806cc0494853e5e3ca9854b2cfc30`
Branch: `p12-preparation`
Status: **bounded P24 packet passed on warm rerun; P24 remains incomplete**

## Scope

Added `tests/windows/test_p24_owned_mutation_acceptance.py` for GC-082 and
GC-083. Each case substitutes the fixed corpus root with a pytest-owned folder,
creates one owned source file, then submits the original move/rename wording to
the real `PlumaApplicationRuntime`. The test checks the FAST route and exact
typed arguments, MEDIUM policy, the scoped confirmation request and callback
approval, the native move/rename result, source absence and destination bytes,
saved task/action/verifier/undo records, worker identity cleanup and absence of
model imports. The callback is a test contract; it does not exercise the
production confirmation UI.

No production source changed in E112. Existing `tests/unit/test_file_move_identity.py`
provides the affected manual-undo, conflict-refusal, identity and cleanup
regressions; `tests/unit/test_policy_boundary.py` checks the confirmation gate.

## Verification

Environment: Windows, Python 3.12.10, pytest 9.2.0, pytest-timeout 2.4.0,
Pydantic 2.14.3 and PyYAML 6.0.3. Temporary app storage and test files were
isolated below ignored `output/`; pytest ran sequentially in one process with a
unique short `--basetemp`. No model, resident app, microphone, desktop
confirmation, personal file/window/clipboard, device or power operation was
used. The final run's invoking PowerShell process was set to BelowNormal
priority. After completion, no `uv`, `python` or `pythonw` process remained.

The final affected regression selection was:

```powershell
$runner = [System.Diagnostics.Process]::GetCurrentProcess()
try { $runner.PriorityClass = 'BelowNormal' } catch {}
$out = 'D:\Workspace\DEVEL\PLUMA\output\p24-e112'
$base = 'D:\Workspace\DEVEL\PLUMA\output\p24-tmp-e112-final'
$env:TEMP = "$out\temp"
$env:TMP = "$out\tmp"
$env:APPDATA = "$out\appdata"
$env:LOCALAPPDATA = "$out\localappdata"
uv run --no-project --python 'D:\Workspace\DEVEL\PLUMA\output\p24-python\cpython-3.12.10-windows-x86_64-none\python.exe' --with 'pytest==9.2.0' --with 'pytest-timeout==2.4.0' --with 'pydantic==2.14.3' --with 'PyYAML==6.0.3' --with psutil --with jsonschema -- python -m pytest tests/unit/test_router.py tests/unit/test_file_move_identity.py tests/unit/test_policy_boundary.py tests/unit/test_tools_files.py tests/windows/test_p24_owned_mutation_acceptance.py tests/windows/test_p24_owned_folder_creation_acceptance.py -k 'not stale' --basetemp="$base" -p no:cacheprovider -q --junitxml="$out\p24-mutation-regressions.xml" *> "$out\p24-mutation-regressions.log"
```

Result: **259 passed, 0 failed, 0 errors, 0 skipped in 18.53 seconds**.
Breakdown: router 197, file-move identity/undo 25, policy boundary 27, file
tools 4, owned mutation acceptance 2 and owned folder acceptance 4. Full output
and JUnit are retained under `output/p24-e112/`.

The initial cold two-case run failed both acceptance cases after `uv` installed
19 packages. The move result recorded `TEMP_CLEANUP_DEFERRED_ROLLBACK_UNVERIFIED`;
the rename cleanup report recorded a verified rollback with zero attempted
steps. The assertion output did not retain the exact executor error, so the
cause is unknown. This initial run is retained in
`output/p24-e112/p24-mutation-focused.xml` and `.log` and is not counted as
acceptance. After dependencies were warm, GC-082 passed alone in 0.85 seconds,
GC-083 passed alone in 0.69 seconds, and the complete affected selection passed.
The cold-run failure remains a recorded environment-sensitive observation for
P24 failure analysis; it is not reclassified as a product pass or a confirmed
product defect.

The final tested acceptance file SHA-256 is
`73AA3CD38B32DB59EFD4E743661F26AF495FA31FDE42181BE9235F91BD606676`. No
changes were made to the master specification or UI styling.

## Scope limit and next packet

E110-E112 cover **20 of 140 unique corpus cases**. Remaining cases (120):
`GC-001`-`GC-045`, `GC-049`-`GC-055`, `GC-060`-`GC-075`, `GC-088`-`GC-089`,
`GC-091`-`GC-125` and `GC-N001`-`GC-N015`.

P24 remains open: remaining route classes, semantic/OCR actions, native-model
planning, real STT, production confirmation UI, broader mutation/undo/conflict,
multi-step STOP, saved/live UI, reconnect/failure scenarios and section 26
acceptance are not established by this packet. The next safe packet is another
small FAST/READ corpus slice over owned fixture data, after checking each
candidate's route, tool and expected readback. P25 remains gated by P24.
