# E97 — audit repair follow-up

2026-11-03, Asia/Calcutta. This is a bounded test-compatibility and declared
test-environment repair, not a new product milestone and not a full-product
completion claim. Base checkpoint: `7ce58d58ce68fdf51da1c57453c5b9c1e00ea9df`
on `p12-preparation`. Master specification SHA-256 was unchanged at
`72FB7B21EBFE32D80C51450D02849F661DBF7B5C1E14CBC9ACCF78DC66001998`.

## Reproduced causes and bounded repairs

| Finding | Repair |
|---|---|
| Five P01–P13 prerequisite rollback cases failed because their shared `Job` double lacked `assign_process`; worker inverses failed during process containment. | `tests/unit/test_cleanup_evidence.py` now wraps a real `WindowsJobObject` for assignment, termination, active-process readback and close while retaining explicit failure injection. The assertions still require actual owned-worker execution and cleanup. |
| `test_phase135_adversarial.py` imported deleted `_ALLOWED_APP_ALIASES`. | Replaced the obsolete import with parameterized `OpenAppArgs` checks for all current closed aliases, canonicalization, and refusal of unregistered executables/options. No app is launched by these schema tests. |
| Test collection lacked Pillow, NumPy and sounddevice; native Windows fixtures additionally lacked `pywin32`, `comtypes` and `pycaw`. | Added these existing test/runtime adapter requirements to the `dev` optional extra and `requirements-dev.txt` (Windows dependencies are platform marked). `pip install -e ".[dev]"` and `pip install -r requirements-dev.txt` installed/resolved the declared test set. |
| Golden policy rows expected ALLOW for MEDIUM actions; current policy requires exact explicit confirmation when no trusted confirmation contract is supplied. | `tests/fixtures/golden_commands.yaml` now expects `REQUIRE_CONFIRMATION` for close-app, undo and file move/rename rows. Policy behavior was not relaxed. |
| P12's audit test and manifest expected 85 tools after the later bounded `open_folder` addition. | Renamed the assertion to 86 and updated the manifest selector. The 73 exact Section 21 names are unchanged. |
| The preparation/shutdown race test assumed one retry always observes preparation completion. With a real contained Job fixture, shutdown can truthfully report an incomplete outcomes stage while the preparation count is still unwinding. | The test now asserts the incomplete result keeps storage open, waits for the failed stage worker to finish, retries, and still requires verified shutdown and no published task. This adds state checks; it does not accept incomplete shutdown as success. |

## Fresh verification

Environment: Windows (`win32`), Python 3.12.10, pytest 8.3.3. APPDATA,
LOCALAPPDATA, TEMP and TMP were isolated for applicable suites. All full logs
and JUnit XML are under ignored `output/audit-fix-20261102-233100/`.

| Command/selection | Result |
|---|---|
| Five formerly failing P01–P13 rollback cases, before repair | **5 failed / 8 passed**; reproduced. |
| Focused current ownership, STOP, shutdown, policy, alias/schema and Pillow capture regressions | **131 passed**, no skips/xfails. |
| `docs/completion/p12_check_manifest.json` prerequisites selection | **500 passed**, no skips/xfails. |
| P01–P13 contracts selection | **352 passed**, no skips/xfails. |
| P12 selection after updating the 86-tool selector | **244 passed**, no skips/xfails. |
| P13 llama adapter/planner target/replan unit selections | **16 passed**, no skips/xfails. `llama_cpp` is not installed here; this is fixture/unit coverage, not native model evidence. |
| `pytest --collect-only -q tests/unit` | **2,415 tests collected**, no collection errors. The full unit suite was not executed. |
| `python -m pip install -r requirements-dev.txt` | **Passed**; all declared test dependencies resolved. |
| `python docs/completion/verify_requirements_matrix.py` | **Passed**: 298 source items / 334 traceable rows. |
| `tests/unit/test_app_launch_native.py` on owned private desktop/process fixtures | **16 passed**. |
| `tests/unit/test_audio_native.py` | **67 passed**. Its native checks read the selected endpoint; no physical audio writes are in this module. |
| `tests/unit/test_cross_volume_move_native.py` with pytest temp on C: and owned destinations on D: | **10 passed**. The initial same-volume attempt was invalid for this test and failed before fixture files were moved; the cross-volume precondition is now met. |
| `tests/unit/test_elevation_native.py` | **19 passed**; includes bounded owned child and read-only DNS-cache observation, not DNS flush/UAC acceptance. |
| Shutdown preparation race test, repeated in isolation | **5/5 passed**. |

The exact successful logs for the final source/test state are
`focused-verified-source.txt` and `prerequisites-verified-source.txt`.
Other successful scoped logs are `contracts-final.txt`, `p12-final2.txt`,
`p13-final.txt`, `collect-unit-final2.txt`, `app-launch-native-final.txt`,
`audio-native-final.txt`, `cross-volume-native-final.txt`,
`elevation-native.txt` and `shutdown-repeat2-*.txt` in the ignored output
directory above.

## Remaining limitations and unavailable evidence

- The isolated native clipboard suites produced **29 failures / 22 passes**.
  Every failure was at fixture creation: Windows returned `WinError 183` for
  `CreateWindowStationW(NULL, ...)` because the system-named station already
  exists. The fixture refuses to reuse it, so these failures occurred before
  clipboard access. The user's interactive clipboard was not used or changed.
  No fallback or assertion weakening was added. Native clipboard acceptance
  remains unverified in this sign-in.
- Browser native acceptance was not rerun. A process with an isolated
  `--user-data-dir` was present after the prior audit's interrupted browser
  fixture run, and its ownership was not established. It was not terminated or
  disturbed. Its browser native failures therefore remain unverified here.
- The old ignored `output/p01-p13-audit/catalog-final.txt` was overwritten by
  an aborted legacy audit runner before this repair task. Its former content is
  **unavailable**; it has not been reconstructed or presented as evidence. Its
  older XML/JSON files remain historical only.
- The full 2,415-test unit suite and the complete P01–P13 native catalog were
  not run. Some catalog tests can change audio state, invoke desktop tools,
  interact with browsers or clipboard, or use destructive APIs. Only inspected
  owned/read-only selections above were executed.
- `python -m pip check` reports pre-existing global environment conflicts:
  installed `google-genai 2.22.0` requires `httpx>=0.28.1` and `pydantic>=2.12.5`,
  while this interpreter has `httpx 0.27.2` and PLUMA's declared-compatible
  `pydantic 2.9.2`. No unrelated global package was upgraded.
- Physical microphone boundary timing remains owner-deferred to P25. Installed
  startup, upgrade/uninstall, recovery, performance/quality and other matrix
  gates remain open. P21 has not started. No P00–P20 product-wide completion
  is inferred from these test repairs.

The final tracked changes are committed in the E97 checkpoint; successful
verification commands above were run against the same source/test state. The
commit changes only tests, test dependency declarations and completion records.
