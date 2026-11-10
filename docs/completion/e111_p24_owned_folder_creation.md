# E111 - P24 owned folder-creation acceptance

Date: 2026-11-10 (Asia/Calcutta)
Tested source commit: `f30bb481c484f5b2dd7db5b66c400f38df69347e`
Branch: `p12-preparation`
Status: **bounded P24 packet passed; P24 remains incomplete**

## Defect and repair

Long fixture-owned paths in FAST `create_folder`, `move_file` and
`rename_file` commands were copied into `ToolCall.purpose` and the route reason.
`ToolCall.purpose` is limited to 128 characters, so otherwise valid long-path
calls failed schema validation before tool admission. The route now uses short,
factual purpose/reason strings and preserves the complete paths and names in the
registered typed arguments. No argument, safety or policy validation was
relaxed. The change is in `pluma/core/router.py` (methods
`_fast_create_folder`, `_fast_move_file` and `_fast_rename_file`); the unit
regression is in `tests/unit/test_router.py`.

Four additional corpus cases, GC-080, GC-081, GC-086 and GC-090, now run through
`PlumaApplicationRuntime` in `tests/windows/test_p24_owned_folder_creation_acceptance.py`.
Each case substitutes only the corpus root with a pytest-owned temporary root.
The test checks FAST routing, exact typed arguments, LOW/ALLOW policy, native
folder creation, independent identity/digest verification, saved task/action/
verification/undo-prestate records, worker absence and no model imports. These
tests do not invoke the inverse; the affected native file-operation regression
selection separately verifies owned folder undo and conflict refusal.

## Verification

Test environment: Windows, Python 3.12.10, pytest 9.2.0, pytest-timeout 2.4.0,
Pydantic 2.14.3 and PyYAML 6.0.3. The single pytest process ran sequentially;
process-local TEMP/TMP/APPDATA/LOCALAPPDATA were redirected under ignored
`output/`. A short unique `--basetemp` under ignored `output/` was required for
the native filesystem fixtures. No model, STT/OCR, resident app, microphone,
personal files/windows/clipboard or device/power operation was used.

The exact successful command was:

```powershell
$out = 'D:\Workspace\DEVEL\PLUMA\output\p24-20261110-f30bb48'
$base = 'D:\Workspace\DEVEL\PLUMA\output\p24-temp-f30bb48'
$env:TEMP = "$out\temp"
$env:TMP = "$out\tmp"
$env:APPDATA = "$out\appdata"
$env:LOCALAPPDATA = "$out\localappdata"
uv run --no-project --python 'D:\Workspace\DEVEL\PLUMA\output\p24-python\cpython-3.12.10-windows-x86_64-none\python.exe' --with 'pytest==9.2.0' --with 'pytest-timeout==2.4.0' --with 'pydantic==2.14.3' --with 'PyYAML==6.0.3' --with psutil --with jsonschema -- python -m pytest tests/unit/test_router.py tests/unit/test_file_operations_native.py tests/unit/test_tools_files.py tests/windows/test_p24_owned_readonly_acceptance.py tests/windows/test_p24_owned_folder_creation_acceptance.py --basetemp="$base" -p no:cacheprovider -q --junitxml="$out\p24-folder-commit-regressions-shorttemp.xml" *> "$out\p24-folder-commit-regressions-shorttemp.log"
```

Result: **247 passed, 0 failed, 0 errors, 0 skipped in 16.93 seconds**.
Breakdown: router 197, native file operations 26, file tools 4, P24 read-only
acceptance 16, and owned folder creation 4. JUnit and full output are retained
in `output/p24-20261110-f30bb48/`.

An initial attempt using pytest's default temporary root failed three existing
owned copy cases with `UNDO_PRESTATE_FAILED`. One such case passed with a short
owned `--basetemp`; then the full affected selection, including all copy cases,
passed with that same setup. The final JUnit report contains no skips or
xfails. The failed initial setup is retained in
`output/p24-20261110-f30bb48/p24-folder-commit-regressions.xml` and its log; it
is not counted as acceptance evidence.

After the test process ended, no `uv`, `python` or `pythonw` process remained.
The workspace root `uv.lock` is untracked and excluded from this packet.

## Scope limit and next packet

E110's 14 accepted cases plus these four make **18 of 140 unique corpus cases**.
The remaining 122 IDs are `GC-001`-`GC-045`, `GC-049`-`GC-055`,
`GC-060`-`GC-075`, `GC-082`-`GC-083`, `GC-088`-`GC-089`, `GC-091`-`GC-125` and
`GC-N001`-`GC-N015`.

P24 remains open. Screen/UIA/OCR, native-model planning, real STT, confirmation
UI, broader mutation/undo/conflict, multi-step STOP, live/saved UI and
reconnect/failure acceptance remain unverified. The next safe packet is the
owned-fixture confirmation path for GC-082/GC-083; it must exercise only
pytest-owned source/destination files and a test confirmation callback, not the
owner's desktop confirmation UI. Do not start P25 until P24 gates pass or an
applicable owner-approved limitation is recorded.
