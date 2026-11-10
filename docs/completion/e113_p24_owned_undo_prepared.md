# E113 - P24 owned undo acceptance preparation

Date: 2026-11-10 (Asia/Calcutta)
Branch: `p12-preparation`
Prepared against: `caaec5b0f9f1bcebc27b4eb5c6dd627c7065b8ad`
Status: **BOUNDED ACCEPTANCE PASSED; P24 remains incomplete**

## Prepared scope

Added `tests/windows/test_p24_owned_undo_acceptance.py` for GC-054 and GC-055.
The cases use a test-owned temporary file and the real application runtime to
seed a confirmed move, submit the corpus undo request, and assert inverse file
state, verifier and SQLite readback, one-time undo-claim consumption, and
worker-absence evidence. Confirmation is supplied by a test callback, so this
does not establish production confirmation-UI behavior.

## Verification

Tested commit: `f1f7c5d58ebc284a16a231d4044753b7223dc3af` on `p12-preparation`.
Environment: Windows, Python 3.12.10, pytest 9.2.0, pytest-timeout 2.4.0,
Pydantic 2.14.3 and PyYAML 6.0.3. Other declared test dependencies were resolved
by uv into the ignored cache below. Pytest ran sequentially at BelowNormal
priority with per-run temporary storage and APPDATA/LOCALAPPDATA isolated under
`output/`; no personal files, clipboard, windows, device, power state or PLUMA
resident were used.

The PowerShell wrapper set `TEMP`, `TMP`, `APPDATA` and `LOCALAPPDATA` below
each run's unique output directory, `PYTHONDONTWRITEBYTECODE=1`, and
`UV_CACHE_DIR=output/p24-resume-20261110-ac8a65d-retry2/uv-cache`. It set the
current runner priority to `BelowNormal` before invoking uv.

Focused acceptance command:

```powershell
uv run --offline --no-project --python 'D:\Workspace\DEVEL\PLUMA\output\p24-python\cpython-3.12.10-windows-x86_64-none\python.exe' --with 'pytest==9.2.0' --with 'pytest-timeout==2.4.0' --with 'pydantic==2.14.3' --with 'PyYAML==6.0.3' --with psutil --with jsonschema -- python -m pytest tests/windows/test_p24_owned_undo_acceptance.py --basetemp 'D:\Workspace\DEVEL\PLUMA\output\p24-resume-20261110-ac8a65d-retry3-tmp' -p no:cacheprovider -q --junitxml 'D:\Workspace\DEVEL\PLUMA\output\p24-resume-20261110-ac8a65d-retry3\p24-e113-undo.xml'
```

Result: **2 passed in 4.42 seconds** (GC-054 and GC-055).

Affected sequential regressions:

```powershell
uv run --offline --no-project --python 'D:\Workspace\DEVEL\PLUMA\output\p24-python\cpython-3.12.10-windows-x86_64-none\python.exe' --with 'pytest==9.2.0' --with 'pytest-timeout==2.4.0' --with 'pydantic==2.14.3' --with 'PyYAML==6.0.3' --with psutil --with jsonschema -- python -m pytest tests/unit/test_router.py tests/unit/test_file_move_identity.py tests/unit/test_policy_boundary.py tests/unit/test_tools_files.py tests/windows/test_p24_owned_mutation_acceptance.py tests/windows/test_p24_owned_folder_creation_acceptance.py tests/windows/test_p24_owned_undo_acceptance.py --basetemp 'D:\Workspace\DEVEL\PLUMA\output\p24-resume-20261110-ac8a65d-retry4-tmp' -p no:cacheprovider -q --junitxml 'D:\Workspace\DEVEL\PLUMA\output\p24-resume-20261110-ac8a65d-retry4\p24-e113-regressions.xml'
```

Result: **261 passed in 39.16 seconds; 0 failed, 0 skipped**. Full logs and
JUnit are retained at `output/p24-resume-20261110-ac8a65d-retry3/` and
`output/p24-resume-20261110-ac8a65d-retry4/`; the dependency cache is in
`output/p24-resume-20261110-ac8a65d-retry2/uv-cache/`. An initial offline
attempt could not find pytest; the sandbox-blocked online attempt did not start
pytest. A later malformed JUnit argument collected zero tests and is not
acceptance. Only the two-case and 261-case successful runs count. No uv or
Python test process remained afterward.

E113 adds **two** accepted corpus cases, bringing P24 to **22/140**. The test
uses a callback confirmation contract, so production confirmation UI remains
unverified. A fresh isolated rerun of both E112 mutation cases passed **2/2 in
3.95 seconds** at the same tested commit; this did not reproduce the historical
cold-run failure. Its original executor cause remains unknown and the original
failure stays in the record. The other 118 corpus cases and remaining P24 flows
are still open. P24 is not complete.

E112 reproduction output is in
`output/p24-resume-20261110-ac8a65d-retry5/p24-e112-cold-repro.xml` and
`.log`.

The fresh E112 repro used the same offline uv environment and isolated wrapper:

```powershell
uv run --offline --no-project --python 'D:\Workspace\DEVEL\PLUMA\output\p24-python\cpython-3.12.10-windows-x86_64-none\python.exe' --with 'pytest==9.2.0' --with 'pytest-timeout==2.4.0' --with 'pydantic==2.14.3' --with 'PyYAML==6.0.3' --with psutil --with jsonschema -- python -m pytest tests/windows/test_p24_owned_mutation_acceptance.py --basetemp 'D:\Workspace\DEVEL\PLUMA\output\p24-resume-20261110-ac8a65d-retry5-tmp' -p no:cacheprovider -q --junitxml 'D:\Workspace\DEVEL\PLUMA\output\p24-resume-20261110-ac8a65d-retry5\p24-e112-cold-repro.xml'
```

## Next safe packet

Continue with a small FAST/READ corpus slice over owned fixture data, checking
each case's route, tools and expected readback before execution. Keep the
unexplained E112 cold-run failure in the P24 failure ledger.
