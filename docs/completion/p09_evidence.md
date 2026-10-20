# P09: private atomic Windows IPC credentials

Completed 2026-10-20 (Asia/Calcutta). BA-09 passes ordinarily; P01-P08 remain
green. All 15 raw audit cases now pass, with no audit xfails. P10 is next and
was not started. This bounded security/interoperability gate is not combined
Windows safety, physical device/UI, installed-artifact or release acceptance.
Native dark UI and action entry remain unchanged/disabled.

## Prerequisites and source

Started clean on local/remote `ui-wiring` at
`5853572842cd4706e9729e13fb483b7cae4639ff` (P08). Rechecked origin, four worktrees,
main `6dbf589`, integration `9544752` and draft/open/unmerged PRs 1/2. Read shared
contract/P09, current handoff and AGENTS; reread master security/verification/
privacy/local IPC/packaging contracts, Build Plan Phase 1, technology contract,
acceptance H-07/H-08, relevant A/G/I/J and native wiring/placement references.
The immutable master was read completely in P00 and remains unchanged.
Inspected Python creation/reuse, native Windows ACL APIs, the actual C# handle
reader and its test-owned production-Python status fixture before editing.

Before production edits, matrix **298 source items / 324 rows** passed;
P01-P08 prerequisites **285 passed in 30.97s**. BA-09 reproduced **1 failed in
0.48s**: a first-created credential inherited a Users-readable ACL and was
returned without validation. The original audit fixture/body/assertion and
Windows skip condition remain unchanged; only its strict xfail marker is removed.

Two runtime files, three test files and five evidence/handoff documents change.
Exact files/checks were announced before edits. Native C# production reader,
Python transport/authentication framing, STOP/supervisor/worker/admission,
model/voice/UI implementation, immutable spec/build/acceptance and dependencies
are unchanged. No production key was read, edited, repaired or rotated for tests.

Final tested source is the commit containing this record, parent `5853572`:

| File | Git blob |
|---|---|
| `pluma/core/ipc.py` | `1f5079bce28489535956d661e3773054d6c854b5` |
| `pluma/adapters/credentials.py` | `3dd91aca874af0698734b453d4974c86e491c64d` |
| `tests/unit/test_backend_wiring_audit.py` | `97fa8c00f4510c1f7b86f9153220d584df81efa4` |
| `tests/unit/test_ipc_credentials.py` | `30fea68b93c3651203e68db924a60a43440db73b` |
| `PLUMA.UI/CoreIpc.Tests/Program.cs` | `87f8199dba31165ffbeafeb4d10b74b49e3468a9` |
| `PLUMA.UI/PLUMA.UI/CoreIpcClient.cs` | `ac80a274c8e816911a7a51ada2dd923510bedb92` |
| `PLUMA.UI/CoreIpc.Tests/fixture_server.py` | `54cd6d49fac61978ff855b53a24d8a5eb2016879` |

## Windows credential contract

- Windows creation/reuse delegates to the replaceable credentials adapter using
  ctypes/Win32; no new package or inference runtime is installed/imported. The
  non-Windows fallback is unchanged and is not certified by this Windows gate.
- Fresh file creation uses CREATE_NEW with an explicit current-token-user owner
  and protected DACL granting that user full control. There is no permissive
  create-then-chmod/ACL window. The creator opens with no sharing; other readers
  cannot observe partially written bytes. It validates the opened handle before
  writing, writes exactly 32 random bytes, flushes, seeks and reads them back,
  revalidates owner/DACL/size, compares the bytes and closes before returning.
  CREATE_NEW never overwrites a competitor; no Windows truncation path remains.
- Existing files open read-only with reader sharing, without write/delete
  sharing. Validation, size checks and reads use that same opened handle, not an
  earlier named-file snapshot. Actual disk-file type, no final-component reparse
  point/directory, and one link are required. Replacement/write/delete during the
  read handle lifetime is refused. Opening the final reparse point does not
  follow it. Full ancestor-junction/adversarial filesystem acceptance is P27.
- Native owner must equal the current process-token user SID. Each allowed ACE
  must name that user, SYSTEM or Builtin Administrators, matching the unchanged
  C# reader. Broad grants including Everyone/Users/Authenticated Users/Anonymous/
  Owner Rights, null/invalid DACLs, unsupported ACE forms and wrong owner fail
  closed. Deny rules are not treated as grants. New protected ACLs suppress
  inherited broad permissions. Existing trusted inherited ACLs can be reused;
  P09 never rewrites existing permissions merely to force acceptance.
- Sharing/creation contention has one 500 ms retry budget. A valid winner is
  reopened/validated or the request is refused; an incomplete/busy/corrupt/
  insecure file is never repaired, truncated or rotated. A failed private first
  write can leave its exact file behind for explicit controlled recovery; no
  uncertain path is deleted. A pre-existing unsafe production credential will
  now be refused, not silently fixed. This is not power-loss durability or
  full installed recovery certification.
- Native file/token handles and allocated SID/security-descriptor buffers have
  explicit cleanup. Fixed RuntimeError copy suppresses raw native failures and
  security-descriptor dumps. Secret bytes/derived comparison fingerprints are
  never printed/stored in reports; fixtures use boolean-only comparisons. The
  credential bytes remain only in the private fixture file/transient memory.
  Normal HMAC still sends proofs, never the secret, over the application pipe.

The API design follows Microsoft's primary references for
[CreateFileW security attributes, creation and share modes](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-createfilew),
[opened-handle security descriptor retrieval and LocalFree ownership](https://learn.microsoft.com/en-us/windows/win32/api/aclapi/nf-aclapi-getsecurityinfo)
and [ACE enumeration](https://learn.microsoft.com/en-us/windows/win32/api/securitybaseapi/nf-securitybaseapi-getace).
The new implementation uses actual native readback; citing documentation is
not substituted for the fixture evidence below.

## Checks (E14)

Windows 11 build 26200 / Python 3.12.10 x64 / pytest 8.3.3 / .NET SDK 10.0.401
(target net8.0-windows). Each Python run uses unique LOCALAPPDATA/APPDATA/TEMP/TMP,
removes inherited PLUMA_* overrides and retains exact source SHA-256, command,
parent/environment, real pytest exit and JUnit under ignored `output/p09`.
All 115 inherited FAST cases carry desktop-isolation properties from the loaded
plugin; retain the P02 correction. Thread exceptions are errors. All fixture
keys remaining zero. Test ACL changes apply only to exact temporary fixture
files/directories; no Windows policy, production credential, user app/settings,
elevation, resident hotkey, microphone/model or unsigned-application bypass
was activated. No ML dependencies were installed.

The ignored Python runner externally bounds pytest to 180 seconds and individual
tests to 20 seconds. Its wrapper returns zero after recording pytest failure;
actual pytest exits below are authoritative. Commands normalize only Python
executable/report root; metadata retains exact absolute paths.

```powershell
python -m pytest tests/unit/test_stop_protocol.py tests/unit/test_backend_wiring_audit.py::test_ipc_stop_reply_distinguishes_residual_cleanup tests/unit/test_backend_wiring_audit.py::test_ipc_stop_reply_does_not_claim_nonterminal_task_stopped tests/unit/test_voice_session.py tests/unit/test_backend_wiring_audit.py::test_voice_stop_closes_capture_without_key_release tests/unit/test_backend_wiring_audit.py::test_empty_voice_capture_finalizes_its_capsule tests/unit/test_runtime_shutdown.py tests/unit/test_backend_wiring_audit.py::test_runtime_close_drains_active_task_and_registry tests/unit/test_terminal_outcome.py tests/unit/test_backend_wiring_audit.py::test_fast_stop_preserves_supervisor_residual_outcome tests/unit/test_cleanup_evidence.py tests/unit/test_backend_wiring_audit.py::test_failed_worker_cleanup_requires_residual_state tests/unit/test_worker_cancellation.py tests/unit/test_executor_admission.py tests/unit/test_global_stop_ordering.py tests/unit/test_backend_wiring_audit.py::test_worker_stop_interrupts_outstanding_response_wait tests/unit/test_backend_wiring_audit.py::test_stop_during_prestate_prevents_executor_start tests/unit/test_backend_wiring_audit.py::test_global_stop_latches_every_task_before_first_grace -q -o addopts= -o junit_family=xunit1 --timeout=20 --timeout-method=thread --tb=short -ra -W error::pytest.PytestUnhandledThreadExceptionWarning -p no:cacheprovider --junitxml=output/p09/prerequisite-before.xml
# 285 passed in 30.97s; pytest exit 0; outer wall 31.856s.
```

```powershell
python -m pytest tests/unit/test_backend_wiring_audit.py::test_first_windows_credential_is_verified_before_return -q -o addopts= -o junit_family=xunit1 --timeout=20 --timeout-method=thread --tb=short -ra -W error::pytest.PytestUnhandledThreadExceptionWarning -p no:cacheprovider --junitxml=output/p09/before.xml --runxfail
# 1 failed in 0.48s; pytest exit 1; outer wall 1.11s.
```

```powershell
python -m pytest tests/unit/test_ipc_credentials.py tests/unit/test_backend_wiring_audit.py::test_first_windows_credential_is_verified_before_return tests/unit/test_backend_wiring_audit.py::test_ipc_stop_reply_distinguishes_residual_cleanup tests/unit/test_backend_wiring_audit.py::test_ipc_stop_reply_does_not_claim_nonterminal_task_stopped tests/unit/test_stop_protocol.py tests/unit/test_ipc.py tests/unit/test_voice_session.py tests/unit/test_voice_pipeline.py tests/unit/test_voice_activation.py tests/unit/test_voice_vad.py tests/unit/test_brain_lifecycle.py tests/unit/test_voice_lifecycle.py tests/unit/test_voice_capture.py tests/unit/test_runtime_shutdown.py tests/unit/test_terminal_outcome.py tests/unit/test_db.py tests/unit/test_cleanup_evidence.py tests/unit/test_rollback_engine.py tests/unit/test_rollback_recipes.py tests/unit/test_worker_cancellation.py tests/unit/test_global_stop_ordering.py tests/unit/test_executor_admission.py tests/unit/test_task_supervisor.py tests/unit/test_tool_runner_ledger.py tests/unit/test_schemas.py tests/unit/test_ownership.py tests/unit/test_job_object.py -q -o addopts= -o junit_family=xunit1 --timeout=20 --timeout-method=thread --tb=short -ra -W error::pytest.PytestUnhandledThreadExceptionWarning -p no:cacheprovider --junitxml=output/p09/focused-final.xml
# 408 passed in 43.02s; pytest exit 0; outer wall 44.042s.
```

```powershell
python -m pytest tests/unit/test_backend_wiring_audit.py tests/unit/test_schemas.py tests/unit/test_router.py tests/unit/test_brain_validator.py tests/unit/test_policy_engine.py tests/unit/test_redaction.py tests/unit/test_activity_ledger_lifecycle.py tests/unit/test_rollback_engine.py tests/unit/test_rollback_recipes.py tests/unit/test_tool_runner_ledger.py tests/unit/test_perception_freshness.py tests/unit/test_phase13_7_ui_verification.py tests/unit/test_phase13_7_created_stop.py tests/unit/test_ipc.py tests/unit/test_ipc_credentials.py tests/unit/test_stop_protocol.py tests/unit/test_voice_session.py tests/unit/test_voice_pipeline.py tests/unit/test_voice_activation.py tests/unit/test_voice_vad.py tests/unit/test_brain_lifecycle.py tests/unit/test_voice_lifecycle.py tests/unit/test_voice_capture.py tests/unit/test_runtime_shutdown.py tests/unit/test_terminal_outcome.py tests/unit/test_cleanup_evidence.py tests/unit/test_worker_cancellation.py tests/unit/test_global_stop_ordering.py tests/unit/test_executor_admission.py tests/unit/test_fast_orchestrator.py tests/unit/test_multi_step_orchestrator.py -q -o addopts= -o junit_family=xunit1 --timeout=20 --timeout-method=thread --tb=short -ra -W error::pytest.PytestUnhandledThreadExceptionWarning -p no:cacheprovider --junitxml=output/p09/regression-isolated.xml -k "not test_elevation_broker_execution" -p tests.fixtures.desktop_isolation
# 734 passed, 3 skipped, 1 deselected in 57.27s; pytest exit 0; outer wall 58.418s.
```

```powershell
python -m pytest tests/unit/test_stop_protocol.py tests/unit/test_backend_wiring_audit.py::test_ipc_stop_reply_distinguishes_residual_cleanup tests/unit/test_backend_wiring_audit.py::test_ipc_stop_reply_does_not_claim_nonterminal_task_stopped tests/unit/test_voice_session.py tests/unit/test_backend_wiring_audit.py::test_voice_stop_closes_capture_without_key_release tests/unit/test_backend_wiring_audit.py::test_empty_voice_capture_finalizes_its_capsule tests/unit/test_runtime_shutdown.py tests/unit/test_backend_wiring_audit.py::test_runtime_close_drains_active_task_and_registry tests/unit/test_terminal_outcome.py tests/unit/test_backend_wiring_audit.py::test_fast_stop_preserves_supervisor_residual_outcome tests/unit/test_cleanup_evidence.py tests/unit/test_backend_wiring_audit.py::test_failed_worker_cleanup_requires_residual_state tests/unit/test_worker_cancellation.py tests/unit/test_executor_admission.py tests/unit/test_global_stop_ordering.py tests/unit/test_backend_wiring_audit.py::test_worker_stop_interrupts_outstanding_response_wait tests/unit/test_backend_wiring_audit.py::test_stop_during_prestate_prevents_executor_start tests/unit/test_backend_wiring_audit.py::test_global_stop_latches_every_task_before_first_grace -q -o addopts= -o junit_family=xunit1 --timeout=20 --timeout-method=thread --tb=short -ra -W error::pytest.PytestUnhandledThreadExceptionWarning -p no:cacheprovider --junitxml=output/p09/prerequisite-final.xml
# 285 passed in 28.13s; pytest exit 0; outer wall 29.031s.
```

```powershell
python -m pytest tests/unit/test_phase13_8_final_patch.py::TestTaskOwnedWorkerContainment -q -o addopts= -o junit_family=xunit1 --timeout=20 --timeout-method=thread --tb=short -ra -W error::pytest.PytestUnhandledThreadExceptionWarning -p no:cacheprovider --junitxml=output/p09/containment.xml
# 3 passed in 2.90s; pytest exit 0; outer wall 3.748s.
```

```powershell
python -m pytest tests/unit/test_app_lifecycle.py tests/unit/test_crash_recovery.py -q -o addopts= -o junit_family=xunit1 --timeout=20 --timeout-method=thread --tb=short -ra -W error::pytest.PytestUnhandledThreadExceptionWarning -p no:cacheprovider --junitxml=output/p09/recovery.xml
# 5 passed in 0.63s; pytest exit 0; outer wall 1.239s.
```

```powershell
python -m pytest tests/unit/test_backend_wiring_audit.py -q -o addopts= -o junit_family=xunit1 --timeout=20 --timeout-method=thread --tb=short -ra -W error::pytest.PytestUnhandledThreadExceptionWarning -p no:cacheprovider --junitxml=output/p09/raw-final.xml --runxfail
# 15 passed in 0.68s; pytest exit 0; outer wall 1.601s.
```

```powershell
dotnet run --project PLUMA.UI/CoreIpc.Tests/CoreIpc.Tests.csproj --verbosity quiet -p:UseSharedCompilation=false
# 39 IPC checks passed; exit 0; outer wall 11.358s; remaining fixture keys zero.
python docs/completion/verify_requirements_matrix.py
# PASS: 298 source items, 324 traceable rows.
git diff --check
python output/p09/review.py
# Separate scope, original assertions, native framing/reader, tested hashes/JUnit and secret review.
```

**27 new Python credential cases** cover first creation under a permissive
parent, reuse, five broad SID grants, null DACL, trusted SYSTEM/admin allow
rules, five corrupt lengths, native owner comparison with an injected expected
identity mismatch, actual read-access denial, 24 thread contenders, blocked
partial creation/bounded refusal, injected write/flush/read/verification errors,
opened-handle replacement/write refusal, a real hard link, directory refusal,
100 repeated validation cycles without native-handle growth and four real owned
Python subprocess creators sharing one stable winner. Original Popen handles
are retained/terminated only if needed, all children joined; JUnit records task,
PID, native creation time, class and ownership. Comparison fingerprints are
transient and unlogged. The owner-mismatch seam is not a claim of testing an
actual different-user/elevated token; broader identity/adversarial gates remain.

The actual C# client/reader source is unchanged. Its 37 existing assertions
remain, with two additional checks (null DACL refusal and no preseeded Python
credential). The production Python factory now creates the fixture credential
under a directory granting inherited Users read access; the unchanged C# reader
validates its actual opened-handle owner/ACL and authenticates twice for status
messages larger than one read buffer. No credential is seeded to bypass the
factory. C# fixture ownership retains PID/creation time/executable and performs
bounded exit/readback; no production resident/tool/device is started. This is
real Python/C# HMAC/native message framing interoperability, not a fake transport.
The console tests run normally; no WinUI/Application Control workaround is used.

The inherited 48 STOP, 29 voice and 46 shutdown cases are unchanged. Additional
three owned containment and five startup/recovery checks pass. Full native UI
build/render/physical acceptance was not rerun or claimed: production UI is
unchanged. The latest hosted full UI result must be checked separately at its
own gate; the current IPC fixture pass requirement is 39, not the historical 37.

Intermediate artifact limitation: `focused-first` pytest passed **407 in
45.37s**, but the ignored wrapper then tried unlinking a directory deliberately
named ipc_secret.key by the directory-refusal test. It exited before metadata
completion. The wrapper now removes/counts only exact fixture key files; the
remaining keys from that known isolated run were separately removed with
resolved-root checks and zero-key readback (`first-run-cleanup.json`). No broad
recursive deletion or production key cleanup occurred. Fixture comparisons were
also tightened to avoid secret values in failed assertion diagnostics, and a
null-DACL test was added. Only final reports match final tested source/blobs.
This wrapper failure is retained and not counted as a final successful run.

Final regression **734 passed, 3 skipped, 1 deselected**; raw audit **15 passed**.
There are **no remaining BA expected failures**. The three corpus skips (entries
without the no-LLM guarantee) and excluded elevation operation are not passes
or owner-approved limitations. A passing audit does not certify the complete
backend, combined ownership/recovery scenarios or release.

## Remaining gates, Git and recovery

P01-P09 bounded gates pass. **P10 is next**, for the combined real owned Windows
STOP/admission/descendant/identity/rollback/residual/shutdown boundary and fresh
memory/result/ledger/IPC reconciliation. This P09 gate does not automatically
complete P10. Mandatory catalog/policy/verification/undo, UIA/OCR, native model/
voice/device, full UI/events/settings/history, loaded p95/resource/soak, security,
installed artifacts and release gates remain. No requirement/limitation is
waived; physical emulation is not acceptance. Action entry remains disabled.

Commit/push is confined to `ui-wiring`; PR 2 targets `ui-polish-integration`,
PR 1 targets main, both draft/open/unmerged. Main/integration unchanged. Pre-P09
recovery is `5853572842cd4706e9729e13fb483b7cae4639ff`: inspect in a new detached
worktree without resetting this checkout. Existing archive/stash/tags/worktrees
remain. Keys, audio/models, raw reports and generated build output stay out of Git.

Next safe milestone: **P10 only**, after reading its shared contract and fresh
P01-P09/Git/PR prerequisite checks. P10 was not started; no merge or automatic
progression is authorized.
