# P11 native resource and network reads (E24)

2026-10-20. Starting clean/pushed ui-wiring `1a4137c`. Its prior checks passed:
699 focused / 1017 isolated regression / 15 raw / 3 containment / 5 recovery.
P11 remains authorized and incomplete; P12 is forbidden. No UI, immutable
requirements, dependencies, user configuration, network or power settings change.
Other worktrees and recovery archives/stash/tags are preserved.

## Reproduction

`system-before`: **2 failed in 0.85s**. A failed native CPU observation became
verified zero CPU rather than failure; required `network_status` was unregistered.
The old system tool also used a first nonblocking CPU sample and reported the
working drive rather than identifying the Windows system volume. Source/result
copy contained an em dash and verify_noop did not validate resource observations.
Failed isolated log/JUnit/JSON are retained under `output/p11_system`.

## Implemented boundary

- New lazy native adapter `pluma/adapters/system_status.py`: CPU sampling with
  an explicit 0.1-second interval and measured elapsed time, native available/total
  RAM, Windows-directory-derived system volume and native free/total disk bytes.
  Zero CPU is allowed only as an actual successful observation. Failure to read
  a required metric refuses with fixed diagnostics; no synthetic fallback.
- Exact `get_system_status` and compatibility `system_status` use strict schemas,
  required capsule-owned killable workers, five-second timeouts and pure snapshot
  verifiers. Alias output preserves its own exact tool identity. Raw metric sizes
  and sampling data must agree with bounded normalized observations.
- Exact new `network_status` is registered and available to SMART/DEEP schemas.
  Strict `max_entries` 1..128, default 32; native interface name/up/MTU/link-speed
  snapshot is sorted, unique and bounded, with observed count/truncation. Zero
  link speed is unknown, not invented speed. No IP/MAC/SSID/credentials or network
  transmission/probing is requested. Link state never implies internet access;
  connectivity is explicitly unknown in data and deterministic result copy.
- Native errors, unsupported platform/test mode, malformed snapshots and
  serialization failure cannot claim success or fall back to caller-side I/O.
  Schema/policy precede execution; denied reads create factual no-execution history.
- No changes to app/window control, perception/OCR/input or planner inference.
  No persistent monitoring. Parent verifier bounds for other tools remain open;
  these READ verifiers validate their worker snapshots without new native calls.

CPU sampling, available-memory and link-stat fields follow the
[psutil API contract](https://psutil.io/api/), cross-checked against installed
7.2.2 Windows adapter source and actual native reads. A first nonblocking CPU
sample is unsuitable; interface state does not establish internet reachability.

## Verification

Initial repaired reproduction: **2 passed in 0.63s**. Expanded boundary:
**52 passed / 1 failed in 14.68s**; the fake CPU sampler returned immediately
and produced a zero-duration sample correctly rejected by the verifier. The
fixture now waits its requested interval; no assertion or production deadline
was weakened. Reviewed boundary **62 passed in 15.73s**.

Native `get_system_status` uses its real FAST route. Alias/network SMART plans
use an explicitly inert planner seam. Text and voice-mode requests use the same
runtime policy/executor/verification/ledger pipeline; this is not physical
microphone/STT/model acceptance. Six native success cases read back actual SQLite
observations, original Job-worker identities, verified exit and reopened final
history. Six blocked-worker STOP/deadline cases preserve first cause and clean
owned workers. Synthetic counts/interfaces, invalid fields, native I/O failures,
denials and unsupported-platform cases are disclosed fixtures.

Ignored evidence runner uses the native interpreter, isolated application/temp
storage, bounded subprocesses, JUnit/log/JSON, source SHA-256 and actual pytest
exits. Temporary test-only system execution request restores in finally; no
power/security policy change. FAST regressions use desktop isolation.

Final reviewed-source command prefix:
`output/p11-native-env/Scripts/python.exe output/p11_system/run_checks.py`.

| Run argument | Actual pytest output | Runner wall |
|---|---|---|
| `focused-final` | 761 passed / 1 excluded, 141.69s | 142.957s |
| `regression-final` | 1079 passed / 3 skipped / 1 excluded, 174.22s | 175.625s |
| `raw-final` (`--runxfail`) | 15 passed, 0.79s | 1.660s |
| `containment-final` | 3 passed, 3.58s | 4.561s |
| `recovery-final` | 5 passed, 0.74s | 1.633s |

Actual exits zero; final runtime/test source hashes match, fixture keys zero and
all 115 FAST cases carry desktop isolation. Sixty-two new system/network cases.
The enlarged regression orchestration command has a fixed 240-second bound
(after the 141.69s focused run); original per-test 20-second and actual tool
five-second deadlines are unchanged. Per-run runner hashes preserve this change.
Three existing no-LLM corpus skips and system-changing elevation exclusion remain
separate. Matrix traceability and diff/staged checks pass. Catalog: 9 IMPLEMENTED /
43 MISSING / 4 DEFECTIVE / 17 UNVERIFIED.
Skips/excluded elevation are not passes; no performance/soak/release claim.

## Remaining P11

This closes two bounded READ catalog rows, not P11. Remaining native power
requests, process/window/app mutations, file/clipboard/browser/terminal tools,
safe inverses, irreversible evidence, verifier bounds and A/D/H gates remain.
No requirement is optionalized or waived. Physical device transitions, complete
catalog scenarios and later release evidence remain separate requirements.

Recovery before this block: separate detached worktree at `1a4137c`. Push only
ui-wiring; no merge or other worktree modification. Next work remains P11,
beginning with bounded verification and irreversible/inverse/catalog gaps.
P12 is not eligible or authorized.
