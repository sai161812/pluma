# P10: blocked prerequisite revalidation (E15)

Attempted 2026-10-20 (Asia/Calcutta). **P10 is incomplete; P11 is ineligible.**
The prompt requires "Record failures as blockers and stop". Applied this rule
at the first failing prerequisite run: no runtime/test edits, fixture addition,
assertion relaxation, repeat-until-green run or owner limitation was substituted.
This is a durable failure record, not combined safety acceptance.

## Source, scope and prerequisites

Clean local/remote `ui-wiring` source `b0e486a0ce323da66be630ac55048b756f9f6182`
(P09). Production Python tree `287d19783e053ea4859097aceb44b5d4e43e3cd0`;
`tests/unit/test_worker_cancellation.py` blob
`c6b5d524aac2b2d3e50597261d81aa72107c47a1`. Source files were not edited during
or after the runs. The commit containing this record changes documentation only.

Read shared execution/P10/current handoff/AGENTS, immutable master (complete
read in P00 and reread this turn), build plan, acceptance and technology contract;
inspected native worker/controller/Job Object/ownership, runtime shutdown,
outcome/rollback and STOP fixtures plus current native UI wiring/placement
references. Git remotes/worktrees checked; main `6dbf589`, integration `9544752`,
legacy detached `55b625c` remain unchanged. PRs 1/2 queried through GitHub REST:
both draft/open/unmerged. No merge, worktree switch, reset or broad deletion.

Windows 11 build 26200, Python 3.12.10 x64. An adapted ignored P09 runner
creates a unique temporary root per run; overrides LOCALAPPDATA/APPDATA/TEMP/TMP,
removes inherited PLUMA_* overrides and enables UTF-8. Owned temporary files,
native pipes/processes/Jobs and SQLite; inert device/model fixtures. No physical
microphone/OCR/desktop UI or system-changing elevation test was requested/run.
No new FAST corpus run occurred, so its desktop-isolation plugin was not needed.
Preserve the historical P02 isolation correction; do not retroactively describe
older unisolated runs as contained. Both current runs report zero remaining
fixture key files. No production credential was read/repaired/rotated for tests.

## Commands and actual results

Matrix before edits: `python docs/completion/verify_requirements_matrix.py`:
**PASS, 298 source items / 324 traceable rows**. This checks coverage and links,
not runtime acceptance.

The ignored runner commands were `python output/p10/run_checks.py
prerequisite-before` and `python output/p10/run_checks.py raw-before`.
The exact expanded pytest commands follow (paths identify the test interpreter
and ignored reports, not production storage):

```text
C:\Users\saipr\AppData\Local\Programs\Python\Python312\python.exe -m pytest tests/unit/test_ipc_credentials.py tests/unit/test_backend_wiring_audit.py::test_first_windows_credential_is_verified_before_return tests/unit/test_stop_protocol.py tests/unit/test_backend_wiring_audit.py::test_ipc_stop_reply_distinguishes_residual_cleanup tests/unit/test_backend_wiring_audit.py::test_ipc_stop_reply_does_not_claim_nonterminal_task_stopped tests/unit/test_voice_session.py tests/unit/test_backend_wiring_audit.py::test_voice_stop_closes_capture_without_key_release tests/unit/test_backend_wiring_audit.py::test_empty_voice_capture_finalizes_its_capsule tests/unit/test_runtime_shutdown.py tests/unit/test_backend_wiring_audit.py::test_runtime_close_drains_active_task_and_registry tests/unit/test_terminal_outcome.py tests/unit/test_backend_wiring_audit.py::test_fast_stop_preserves_supervisor_residual_outcome tests/unit/test_cleanup_evidence.py tests/unit/test_backend_wiring_audit.py::test_failed_worker_cleanup_requires_residual_state tests/unit/test_worker_cancellation.py tests/unit/test_executor_admission.py tests/unit/test_global_stop_ordering.py tests/unit/test_backend_wiring_audit.py::test_worker_stop_interrupts_outstanding_response_wait tests/unit/test_backend_wiring_audit.py::test_stop_during_prestate_prevents_executor_start tests/unit/test_backend_wiring_audit.py::test_global_stop_latches_every_task_before_first_grace -q -o addopts= -o junit_family=xunit1 --timeout=20 --timeout-method=thread --tb=short -ra -W error::pytest.PytestUnhandledThreadExceptionWarning -p no:cacheprovider --junitxml=D:\Workspace\DEVEL\PLUMA\output\p10\prerequisite-before.xml

C:\Users\saipr\AppData\Local\Programs\Python\Python312\python.exe -m pytest tests/unit/test_backend_wiring_audit.py -q -o addopts= -o junit_family=xunit1 --timeout=20 --timeout-method=thread --tb=short -ra -W error::pytest.PytestUnhandledThreadExceptionWarning -p no:cacheprovider --junitxml=D:\Workspace\DEVEL\PLUMA\output\p10\raw-before.xml --runxfail
```

| Check | Actual pytest output | Exit | Wrapper wall |
|---|---|---|---|
| P01-P09 prerequisite set | 1 failed, 312 passed in 294.55s | 1 | 300.364s |
| Raw audit, xfail handling bypassed | 15 passed in 0.46s | 0 | 1.046s |

No skip or xfail was counted as acceptance in either run. Unhandled pytest
thread exceptions were configured as errors. The wrapper process itself exits
zero even on pytest failure; the real exit recorded in JSON/JUnit/log is 1 for
the prerequisites and is the gate result. The raw audit was launched before
the prerequisite result was inspected; it is read-only supplementary evidence,
not permission to continue after the failure.

## Blocker P10-01: owned worker did not reach executor entry

```text
FAILED tests/unit/test_worker_cancellation.py::test_registry_cancellation_is_unverified_and_persisted
tests/unit/test_worker_cancellation.py:413: await_file(tmp_path / "entered", executing)
tests/unit/test_worker_cancellation.py:35: AssertionError: Owned fixture did not reach boundary.
```

This unchanged test registers a HIGH typed fixture ToolSpec, with a real Windows
Job Object, worker and SQLite ledger. `await_file` waits up to six seconds for
executor entry before the test calls token.cancel/terminate_and_join. The
marker was absent, so this run did not exercise the case's STOP and ledger
assertions. This establishes a failing prerequisite, not a diagnosed STOP bug.

JUnit records **267.168s** for this case, despite the configured pytest 20-second
thread timeout and runner 180-second subprocess timeout. Total duration also
exceeds that configured outer budget. Their behavior and any host scheduling/
suspension effects have not been established. Do not claim bounded timeout or
latch latency from these numbers; preserve the anomaly for diagnosis.

Read-only post-run observation of the exact isolated failed fixture directory:
`ledger.db` remained, `entered` and `late` did not exist. SQLite contained one
`worker_probe` action with `verified = false` and `duration_ms = 267011.0873`.
No claim about a specific error code is derived from that minimal observation.
The fixture's finally blocks returned through registry/capsule/database close,
and pytest exited normally with failure; this is not an independent all-process
absence proof. No name-based process kill or unrelated resource cleanup was
performed by this task. Existing other native fixture cases passed, including
runtime tree shutdown and unrelated-process survival; they do not replace the
failed case or combined acceptance.

No root cause was guessed, no test timing/assertion changed, no production fix
was attempted. A missing startup marker may have multiple causes. Diagnose the
worker admission/startup/response boundary and elapsed-time anomaly explicitly
before assigning a product defect or environment-only explanation.

## Coverage left incomplete and next gate

The new combined real-owned fixture, memory/result/ledger/authenticated IPC
reconciliation, independent latch acknowledgement versus terminal cleanup
measurement, and final relevant regression/containment/recovery checks were
not completed after the failure. No hardware p95, reboot/PID reuse, physical
voice/UI/device, elevation, install, package or release acceptance is claimed.
All nine original BA regressions still passed the raw audit; no BA marker was
restored. Their historical bounded repair evidence remains distinct from this
failed P10 prerequisite attempt.

Next safe milestone remains **P10**, a bounded diagnosis of P10-01, followed by
fresh passing P01-P09 prerequisites and only then combined owned acceptance.
P11 tool work, UI enabling and merges remain unauthorized here. No approved
limitation or requirement waiver exists. Pre-P10 recovery:
`b0e486a0ce323da66be630ac55048b756f9f6182`, inspect in a new detached worktree.

## Retained evidence and documentation review

Ignored `output/p10/` retains `run_checks.py`, prerequisite-before and raw-before
JSON/TXT/XML, and `failure-observation.json`. JSON records actual pytest exits,
commands, source parent/SHA-256, environment, isolated roots and wall durations.
Artifacts stay local; this redacted durable record carries the failure forward.

| Local artifact | SHA-256 |
|---|---|
| `run_checks.py` | `3d91f762d1073cf2f0722980680482e07bfb2a7d95628fd9f6caac063b829e3c` |
| `prerequisite-before.json` | `02ddf07bb3811b53ae2ba7f41154efb9641a4ffbaa94868f8a2c266df8d44f44` |
| `prerequisite-before.txt` | `7179345801ef9c90a9c3143ec26662ad849598d29eb0530b5b560b0f01568b06` |
| `prerequisite-before.xml` | `5ce6559bcfe141ea9f0434d27c1f098a3d6c7cd7ea75ae3f63b7701463eeea78` |
| `raw-before.json` | `94b5d9c07f273f7696fe45bfe8d830bc29b4125472391c47c5a8d602c44e0deb` |
| `raw-before.txt` | `470724cd2dbdcdd22cf2d3123a6f9fafb828eea66d823f264222cf35dfa98f7e` |
| `raw-before.xml` | `84c3d2da4f2385091b0deabe46ec62de7be44ad34e0506a7c4410a09c8fc1f04` |
| `failure-observation.json` | `e0b8b796f116f79687bd8bc14cc293d7088efb5009ff37b8a2a0d9fc4efdaf9a` |

Only this evidence, PROJECT_HANDOFF, requirements matrix and backend audit
checkpoint change. Documentation checks passed: matrix coverage (298 source items / 324 rows),
local links, `git diff --check`, exact changed-path review and confirmation that
all recorded runtime/test source hashes remain unchanged. Immutable requirements
are absent from the changed-path list. No runtime tests are rerun solely for
these documentation changes. Git push/readback is verified at completion.
