# E119 - P24 read-only volume-status corpus acceptance

Date: 2026-11-10 (Asia/Calcutta)
Branch: `p12-preparation`
Tested production-source base: `f1f7c5d58ebc284a16a231d4044753b7223dc3af`
Status: **BOUNDED FIXTURE ACCEPTANCE PASSED; P24 REMAINS INCOMPLETE**

## Scope

Extended `tests/windows/test_p24_owned_readonly_acceptance.py` with GC-013,
GC-014 and GC-015 (`get volume status`, `check volume`, `sound status`). Each
case traverses the production router, registered typed tool, policy, owned
worker, verifier and SQLite ledger. The test explicitly selects PLUMA's audio
emulation seam, verifies the fixture file is under the run's isolated TEMP,
and compares the returned and saved state with the unchanged pre-run fixture.
It also checks FAST routing, READ/ALLOW, task terminal state, verifier readback,
worker cleanup and absence of newly loaded model modules.

This is fixture evidence only. It did not access or change a physical audio
endpoint and does not satisfy P25 physical or P26 device/quality acceptance.

## Verification

The tested source base is commit `f1f7c5d58ebc284a16a231d4044753b7223dc3af`;
the modified test file had SHA-256
`0C781AC71ECA1C2102862840FE84C87B1E82ECE2CE21D30D476DAB518BE74ABE`.
Python 3.12.10, pytest 9.2.0, pytest-timeout 2.4.0, Pydantic 2.14.3,
PyYAML 6.0.3, psutil and jsonschema ran offline from the ignored UV cache.
Each runner was BelowNormal priority, ran sequentially, and used fresh
`TEMP`, `TMP`, `APPDATA`, `LOCALAPPDATA` and pytest basetemp paths under its
unique ignored output directory. Pytest's cache provider was disabled for the
final focused run.

Focused command:

```powershell
uv run --offline --no-project --python 'D:\Workspace\DEVEL\PLUMA\output\p24-python\cpython-3.12.10-windows-x86_64-none\python.exe' --with 'pytest==9.2.0' --with 'pytest-timeout==2.4.0' --with 'pydantic==2.14.3' --with 'PyYAML==6.0.3' --with psutil --with jsonschema -- python -m pytest tests/windows/test_p24_owned_readonly_acceptance.py -q --tb=short --timeout=90 --basetemp 'D:\Workspace\DEVEL\PLUMA\output\p24-volume-readonly-final-20261110-232702-85ed88\pytest-temp' -p no:cacheprovider --junitxml 'D:\Workspace\DEVEL\PLUMA\output\p24-volume-readonly-final-20261110-232702-85ed88\p24-volume-readonly.xml'
```

Result: **19 passed in 9.91 seconds**, 0 failures, 0 skips. The 19 include all
17 read-only corpus cases in this test file and its two existing text/voice
parity cases.

Affected fixture-only regressions:

```powershell
uv run --offline --no-project --python 'D:\Workspace\DEVEL\PLUMA\output\p24-python\cpython-3.12.10-windows-x86_64-none\python.exe' --with 'pytest==9.2.0' --with 'pytest-timeout==2.4.0' --with 'pydantic==2.14.3' --with 'PyYAML==6.0.3' --with psutil --with jsonschema -- python -m pytest tests/unit/test_audio_native.py tests/unit/test_router.py -k 'not native_read_in_owned_worker and not com_apartment_is_balanced_on_operation_failure' -q --tb=short --timeout=90 --basetemp 'D:\Workspace\DEVEL\PLUMA\output\p24-volume-regressions-fixtures-20261110-232533-5ead89\pytest-temp' -p no:cacheprovider --junitxml 'D:\Workspace\DEVEL\PLUMA\output\p24-volume-regressions-fixtures-20261110-232533-5ead89\p24-volume-regressions.xml'
```

Result: **257 passed, 7 deselected in 8.48 seconds**. Six deselected cases
would read the physical audio endpoint; the remaining deselected COM-helper
unit test could not import `comtypes`, which is declared in the Windows/dev
extras but absent from the isolated test environment. An initial attempt
without that dependency had 257 passes and this one environment failure. Its
offline setup retry could not resolve the package from the workspace-local
cache, and the default UV cache was access-denied. No physical-device test was
run. The final selected regression set passes; the missing helper test remains
unverified, not a product pass.

Full logs and JUnit are retained in:

- `output/p24-volume-readonly-final-20261110-232702-85ed88/`
- `output/p24-volume-regressions-fixtures-20261110-232533-5ead89/`
- Initial dependency-limited run: `output/p24-volume-regressions-20261110-232335-367a2f/`

E119 adds **three** unique corpus cases to E110-E113. P24 now has **25 of 140**
unique cases accepted; 115 cases and the remaining multi-flow gates are still
open. E112's initial cold-run failure remains unexplained despite a passing
fresh rerun. No claim is made for physical audio, native STT/planner, OCR,
multi-step STOP, production UI confirmation, full live-feed/reconnect, or
whole-milestone completion.

## Next safe packet

Select another fixed-corpus FAST/READ case only after confirming its effect is
confined to test-owned data or an explicitly emulated fixture. Keep hardware,
desktop, power and personal-data cases out of this fixture batch. P24 remains
in progress; do not advance to P25 until its required acceptance is complete.
