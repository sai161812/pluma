# E58: P11 production dispatch, elevation cleanup and DNS readback repair

2026-10-25; branch `ui-wiring`; source parent `4b8057d`.

## Scope and acceptance decision

E57's completion claim was premature: source inspection confirmed all three owner-reported defects. This checkpoint repairs those defects and audits the non-screen catalog. It does not start P12 or change the immutable master specification. The owner's latest requirement is passing checks without skipped tests. Their October 25 answer, ?Interactive checks unavailable now?, does not waive those checks. P11 acceptance remains open.

## Implementation

- `pluma/tools/base.py` rejects multiple adapter priorities without a bound `AdapterDispatcher`. `pluma/tools/ui.py` now wires the four production UI ToolSpecs through that dispatcher. Context-only inspection tries native API; semantic controls decline that route before dispatch and use UIA. Unimplemented keyboard/raw fallback declarations were removed. An ordinary failure never triggers weaker dispatch; STOP is checked before each adapter. This repairs existing dispatch metadata without delivering P12 screen features.
- `pluma/adapters/elevation.py` retains the exact child process handle before identity lookup. Every failure and return closes through original-handle termination, Job close and exit observation. A named admission event prevents the fixed elevated child from flushing until identity, Job containment and task resource registration succeed. The gate has a bounded wait and is never released after cancellation or admission deadline. ShellExecute uses balanced COM initialization. Successful process exit and an empty child Job precede readback.
- The fixed DNS operation reads actual cache entry count through a separate owned, suspended-before-containment controlled PowerShell invocation. No DNS names are persisted. `pluma/tools/system.py` refuses exit-only, malformed, missing or nonempty-cache receipts. Only process exit plus independently observed zero cache entries can verify success. Concurrent refill or hosts entries can conservatively produce `DNS_CACHE_NOT_EMPTY`; that is unverified, never a success claim.
- `tests/fixtures/clipboard_logon.py` now checks the inner pytest JSON result, refuses stale evidence labels and returns failure when pytest fails. The ignored historical runner exits zero after writing failed results; this wrapper no longer treats its process exit as acceptance.

## Verification

Python: `output/p11-native-env/Scripts/python.exe`, version 3.12.10. No test skip or expected failure is counted as a pass.

1. `python -m pytest tests/unit/test_tool_adapter_dispatch.py tests/unit/test_elevation_dispatch.py tests/unit/test_elevation_native.py tests/unit/test_policy_engine.py tests/unit/test_policy_boundary.py tests/unit/test_schemas.py tests/unit/test_tools_ui.py -q --runxfail --junitxml=output/p11-e58-focused-final.xml`: **113 passed in 10.14s**, zero skipped. This includes actual non-elevated owned-child termination after injected identity failure, real admission event access before/after release and actual read-only DNS enumeration. Injected elevated paths are explicitly fixtures; they do not prove UAC.
2. `python -m pytest tests/unit/test_clipboard_logon_evidence.py -q --junitxml=output/p11-e58-evidence.xml`: **9 passed in 0.35s**, zero skipped, covering inner failure codes and missing/malformed evidence.
3. Broad regression: **1,189 passed, 14 failed, zero skipped in 378.89s**. All 13 window-state failures and one terminal-window failure occurred in `tests/unit/test_window_state_native.py:desktop` at `SetThreadDesktop` / restoration, rather than a verified production effect. The isolated 19-case window suite passes; combined-run thread/desktop contamination remains unresolved. Exact test file command is retained in `output/p11-e58-regression-command.json` with JUnit `output/p11-e58-regression.xml`; no `-k` exclusion and `--runxfail` enabled.
4. `python -m tests.fixtures.clipboard_logon clipboard-regression-e58`: inner pytest **254 passed, 29 failed in 68.63s**, zero skipped. The failed assertions reached `OpenClipboard` in the private fixture and Windows returned access denied before seeding test contents. The outer runner misleadingly exited zero; the recorded JSON exit was one. The wrapper reporting defect above was subsequently fixed. Same user/integrity, distinct logon, no loaded profile, zero remaining owned processes, interactive clipboard sequence unchanged. This run is a failure, not accepted clipboard evidence.
5. `python -m pytest tests/unit/test_window_state_native.py -q -x --tb=short --junitxml=output/p11-e58-window-diagnostic.xml`: **19 passed in 22.11s**, all collected cases ran. The broad combined run exposed window-state failures; this isolated pass does not erase them.
6. Real foreground inspection failed `NO_ACTIVE_WINDOW` in the first native-focused run (**27 passed, 1 failed**). The assertion is retained without skip in `tests/windows/test_p11_desktop_acceptance.py`; it was separated into explicit interactive acceptance rather than replaced with a mock. Native GetForegroundWindow returned zero; Windows refused SetForegroundWindow for an owned fixture. Fixtures were destroyed and no personal window was targeted.
7. `python -m tests.windows.p11_native_elevation --run-dns-flush`: exit one, `TOOL_TIMEOUT` after 20.085s; ADMIN / REQUIRE_ELEVATION, verified false, non-undoable effect unknown. Production runtime shutdown returned `CLOSED_VERIFIED`, complete true. This attempt preceded the final balanced COM and child-Job-wait changes; those changes passed the focused suite but real UAC was not retried because interactive checks are unavailable. No DNS flush success is claimed.

The source inventory audit found all **57 non-screen master section-21 names registered**; no missing verifier, pre-state or non-undoable intent metadata on audited state changes (excluding intentional agent control/routine dispatch contracts). The 16 missing screen-control catalog names remain P12 work. This metadata audit does not establish native effects or every possible runtime behavior.

## Remaining gates and next safe action

Current native clipboard access and combined window-state failures must be resolved or reproduced in a permitted session. Successful foreground/focus, physical audio change/readback, physical lock/sleep/restart/shutdown acceptance and native fixed-operation UAC/DNS readback remain unverified. Existing fixtures establish refusal, policy, ownership and inverse contracts only. Do not infer physical acceptance from them or from historical E57 owner limitations.

When an interactive environment is available, rerun these bounded P11 checks using owned fixtures and standard UAC. Do not weaken foreground restrictions, touch the personal clipboard, force-close applications or label unavailable assertions passing. P12 is not the next authorized action.

## Repository checks

`python docs/completion/verify_requirements_matrix.py`: PASS, 298 immutable source items and 324 traceable rows. `python -m compileall -q` on changed modules, fixtures and Windows acceptance scripts: PASS. `git diff --check`: PASS after removing trailing blank lines. Diff review found no master changes, P12 implementation, secrets or generated UI copy. Local JUnit reports are ignored artifacts; the counts and failures above are committed evidence.
