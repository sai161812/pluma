# E59: P11 native acceptance retry

2026-10-25, Asia/Calcutta; branch `ui-wiring`; source parent `1de78b9`.
P12 has not started. This is a bounded acceptance retry, not a claim that every P11 gate is complete.

## Environment and scope

Windows 11 build 26200, Python 3.12.10, AMD64 Family 26 Model 96, 16 logical CPUs, 23.0 GiB RAM. Python executable: `output/p11-native-env/Scripts/python.exe`. Production UAC runner clears PLUMA test/emulation flags and uses isolated application directories with voice disabled only for this tool acceptance. Clipboard uses the same-user, same-integrity fresh-logon fixture; private window fixtures never switch the visible desktop. Unit audio mutation fixtures remain explicitly emulated; real audio read tests clear emulation. No model, microphone or OCR acceptance is inferred.

Before editing, inspected the master, AGENTS, P11 prompt, acceptance A/D/H gates, build-plan policy/elevation gate, current handoff and failed fixture paths. Changed only elevation resource lifetime metadata, its assertion, native desktop test-thread setup, and atomic verifier marker publication. Updated this evidence, handoff and requirements matrix. No UI design or P12 functionality changed.

## Fixed defects found during acceptance

The first native DNS run returned `JOB_CONTAINMENT_FAILED` after 6158ms: the registry attempted persistent adoption of a child that had already exited. The elevated subprocess resource omitted `lifetime: task`. Adding that field matches the existing controlled command adapter's lifecycle, preserves identity/registration/Job containment, and prevents promotion of a completed task child. The focused native fixture now asserts the lifetime field.

The first combined audio/window retry reproduced E58's 14 failures: **258 passed / 14 failed in 99.57s**, zero skipped. Native audio initializes COM on pytest's main thread; subsequent fixture `SetThreadDesktop` calls on that thread fail. `tests/fixtures/desktop_thread.py` runs only the relevant native private-desktop test bodies on fresh, joined threads. Parameterization, real native calls, policy, ledger, postcondition, inverse and cleanup assertions are unchanged. Pytest fixture teardown waits for the body and its cleanup; no detached branch or inert replacement is introduced.

The next combined run passed **271 tests and failed one in 119.20s**, zero skipped: the verifier fixture exposed `verification-entered` before writing its PID. The fixture now writes a temporary file then atomically renames it. The PID/ownership assertion remains unchanged.

## Passing evidence

- `python -m pytest tests/windows/test_p11_desktop_acceptance.py tests/unit/test_window_state_native.py tests/unit/test_terminal_window_native.py -q --runxfail --junitxml=output/p11-e59-desktop.xml`: **28 passed in 28.07s**, zero skipped. Actual foreground inspection succeeds. This is a foreground read, not a focus transition.
- `python -m tests.fixtures.clipboard_logon clipboard-regression-e59`: **283 passed in 136.39s**, zero skipped; outer runner and inner test exit both zero. Same user/integrity, distinct logon, no profile loaded, zero remaining owned processes, interactive clipboard sequence unchanged. Actual Unicode copy/paste/clear/undo runs on the private fixture clipboard. This replaces E58's current-session clipboard blocker without changing the plain-text-only product scope.
- `python -m pytest tests/unit/test_elevation_native.py tests/unit/test_elevation_dispatch.py tests/unit/test_policy_engine.py tests/unit/test_policy_boundary.py tests/unit/test_tool_adapter_dispatch.py tests/unit/test_clipboard_logon_evidence.py -q --runxfail --junitxml=output/p11-e59-focused.xml`: **77 passed in 8.43s**, zero skipped.
- `python -m tests.windows.p11_native_elevation --run-dns-flush` after the resource-lifetime fix: exit zero. Actual fixed `flush_dns_cache`, `ok=true`, `verified=true`, adapter `one_operation_uac`, operation exit zero, process exit observed, independent DNS cache entry count zero. Duration **4935.918ms**. Ledger risk ADMIN, approval REQUIRE_ELEVATION, verified one; effect committed/non-undoable. Task `67525000-fd84-466e-aeb5-f96f0219cbc5`; runtime close `CLOSED_VERIFIED`, complete true. Artifact: `output/p11-e58-uac-97effe72570543a089c0cfbfc6a1c169/result.json` (runner retains its historical directory prefix). No DNS names or private clipboard values are stored in this evidence.

Final combined regression: **272 passed in 113.95s**, zero failed/errors/skipped. This includes the original audio-before-window order and all 14 formerly failing private-desktop cases. Command:

```text
python -m pytest tests/unit/test_audio_native.py tests/unit/test_audio_guards.py tests/unit/test_window_state_native.py tests/unit/test_terminal_window_native.py tests/unit/test_power_actions.py tests/unit/test_runtime_shutdown.py tests/unit/test_prestate_ownership.py tests/unit/test_verification_ownership.py -q --runxfail --junitxml=output/p11-e59-regression-clean.xml
```

## Acceptance boundaries

E58's clipboard/UAC/foreground-read failures are superseded by the fresh passing checks above. E58's initial failing runs remain historical evidence. Actual focus transitions (D-02) and physical volume/mute/device mutation/readback (D-03 and related catalog rows) remain unverified; a foreground read does not close D-02. Full P11 acceptance is not claimed.

D-08 explicitly requires risk policy and confirmation before power/system execution. The power-action fixture suite tests that boundary and native initiation flags/read-only observations; it does not physically lock, sleep, restart or shut down the owner's computer. Such physical effects are not claimed, and are not a substitute requirement added to D-08. H-04 native approval presentation remains P16. Next safe work stays within the remaining P11 focus/audio acceptance; do not start P12 automatically.

## Additional checks and review

- `python -m pytest tests/unit/test_verification_ownership.py -q --runxfail --junitxml=output/p11-e59-verification.xml`: **24 passed in 21.11s**, zero skipped after atomic marker publication.
- `python -m pytest tests/unit/test_schemas.py tests/unit/test_tools_ui.py -q --junitxml=output/p11-e59-contracts.xml`: **45 passed in 1.37s**, zero skipped.
- Requirements matrix verifier: PASS, **298 source items / 324 traceable rows**. Changed Python modules compile. `git diff --check` passes. Diff inspection preserves the master, production containment/readback/undo, personal resources and P12 boundary. No secrets or generated UI copy added.

The 272-case pass covers the repaired interaction and relevant ownership regression; it is not a fresh rerun of every historical 1,203-case E58 test. No excluded case, unavailable physical effect or expected failure is reported as passing.
