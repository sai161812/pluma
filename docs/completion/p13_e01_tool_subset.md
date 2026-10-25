# E70 — P13 first bounded packet: file/browser tool subset

Date: 2026-10-26  
Status: this packet is complete; P13 remains open.  
Branch: `p12-preparation`  
Implementation commit: `601fcb500badd87a415ddc322e17407f0cd6897f`  
Recovery point before this packet: `5c7c260a12c12849cfa7c44f61694f9d41482004`

## Scope and prerequisite

The current handoff's first P13 task was a SMART-route tool-subset defect.
`Find report.pdf in downloads and move it to archive` contained the substring
`download`, so `ToolSubsetSelector` returned browser schemas before checking
file intent. The planner then correctly rejected `find_file` because it was
not in the permitted schema list.

P12's E-01 through E-10 and screen-control gate were complete at recovery head
`5c7c260`; `origin/p12-preparation` matched that head before this packet. The
pre-fix P13 planner/lifecycle/schema baseline was **65 passed, 1 failed, zero
skips**. The failing case was reproduced directly with
`tests/unit/test_brain_llama_cpp_adapter.py::test_llama_cpp_adapter_complex_file_command`.

The repository completion records contained no standalone Sol review/findings
artifact. The packet therefore prioritized the reproduced handoff finding and
the applicable F-02 requirement, without inferring approval or waivers.

## Change

`pluma/brain/tool_subset.py` now selects browser tools for explicit browser,
website, web, URL, tab or URL-addressed requests. Otherwise, file operations,
Downloads paths and file-type requests select `FILE_TOOLS` before generic
download wording is considered. A plain download/status request still selects
browser tools. File-only requests no longer include `open_app` or
`focus_window`; explicitly requested clipboard tools remain included for a
clipboard-related file command.

The regression tests prove that:

- The reported Downloads move and a previously downloaded PDF move receive
  only file tool names.
- `Open Downloads` uses file tools.
- Website, URL and browser download-status requests retain browser tools.
- The planner adapter prompt for the reported move includes `find_file` and
  `move_file`, and excludes `open_url`, `download_status`, `open_app` and
  `focus_window`.
- The strict validator accepts the bounded mock response only after the real
  adapter selected its allowed tool schemas.

## Verification

Environment: Windows 11 build 26200, Python 3.12.10, pytest 8.3.3. The baseline
and route regression runs used isolated `APPDATA`, `LOCALAPPDATA`, `TEMP` and
`TMP` under ignored `output/p13-e01/`. They ran with `--runxfail`; JUnit skip
counts were checked and were zero.

Focused command:

```powershell
& .\output\p11-native-env\Scripts\python.exe -m pytest -q -p no:cacheprovider tests/unit/test_brain_tool_subset.py tests/unit/test_brain_llama_cpp_adapter.py::test_llama_cpp_adapter_complex_file_command
```

Result: **13 passed**, zero failures/skips/xfails.

P13 planner/lifecycle/schema baseline command:

```powershell
& .\output\p11-native-env\Scripts\python.exe -m pytest tests/unit/test_brain_llama_cpp_adapter.py tests/unit/test_brain_lifecycle.py tests/unit/test_brain_prompt_builder.py tests/unit/test_brain_tool_subset.py tests/unit/test_brain_validator.py tests/unit/test_schemas.py -q --runxfail -W error::pytest.PytestUnhandledThreadExceptionWarning --junitxml=output/p13-e01/p13-baseline.xml
```

Result on implementation commit `601fcb5`: **72 passed**, zero
failures/errors/skips/xfails, 1.63 seconds.

Route, FAST and multi-step regression command:

```powershell
& .\output\p11-native-env\Scripts\python.exe -m pytest tests/unit/test_router.py tests/unit/test_fast_orchestrator.py tests/unit/test_multi_step_orchestrator.py -q --runxfail -W error::pytest.PytestUnhandledThreadExceptionWarning -p tests.fixtures.desktop_isolation --junitxml=output/p13-e01/route-regressions.xml
```

Result on implementation commit `601fcb5`: **298 passed**, zero
failures/errors/skips/xfails, 38.73 seconds.
Counts overlap with the planner baseline. `git diff --check` passed.

Ignored logs and JUnit output are under `output/p13-e01/`. Tested source was
commit `601fcb500badd87a415ddc322e17407f0cd6897f`; SHA256 values:

| File | SHA256 |
|---|---|
| `pluma/brain/tool_subset.py` | `b6bf0589f3c283fa721827acde38006ef0edda8adaf7a1a201a6c7faa8cd7a59` |
| `tests/unit/test_brain_tool_subset.py` | `3f7c4baa1dd0ab1813d27d7a1a96f3141ac6cd2f7369d46031eed7f3fe16c1b4` |
| `tests/unit/test_brain_llama_cpp_adapter.py` | `44b7278af7873ede85e032be6051f387747a65ce5c31badc16e9f165e4b7e10d` |

## Remaining P13 work and next safe packet

This verifies selector and adapter prompt behavior with an injected mock
generation backend. It does **not** exercise a real llama.cpp model, infer model
quality, or prove native inference worker termination/unload. P13 remains
incomplete. Open gaps include configured `agent.max_plan_steps` enforcement,
native schema-generation fallback behavior, owned inference cancellation and
crash cleanup, malformed/invented output handling through the real adapter,
and real-model acceptance.

Next bounded packet: address planner inference timeout/STOP ownership
(F-07/F-08). The current global future timeout does not prove native generation
has stopped. Reproduce with a bounded owned inference fixture, require positive
worker-absence evidence before cleanup is reported complete, and preserve the
STOP latch against later tools/replans. Then propagate configured
`agent.max_plan_steps` (default 8) into `PlanValidator` and complete real local
llama.cpp acceptance. No P14 work or merge is authorized by this checkpoint.
