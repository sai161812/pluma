# P11 native battery observation checkpoint (E23)

2026-10-20. Clean/pushed starting source `19b3ad3` on ui-wiring. Its preceding
661 focused / 979 isolated regression / 15 raw / 3 containment / 5 recovery
checks passed before this block. P11 remains authorized; P12 is forbidden.
No UI, immutable requirement, dependency, power/security policy or device setting
changes. Other worktrees, archives/stash/tags and disabled action entry preserved.

## Reproduction

Three injected Windows status packets reproduce **3 failures in 0.43s**:
AC connected without the charging flag claimed charging; unsigned unknown bytes
became negative/misinterpreted known values; GetSystemPowerStatus failure still
returned ok/verified. The original registered verifier was verify_noop.
Artifacts: `output/p11_battery/battery-before.*`, isolated native interpreter.

The first repaired run encountered **3 fixture import errors**, not new product
assertion failures: its global fake WinDLL intercepted unrelated adapter/core
imports. Loading the adapter before installing the narrow read fixture fixes
setup without changing the reproduction assertions. Corrected **3 passed in
0.38s**; expanded **34 passed in 4.71s**. All failed artifacts are retained.

## Implemented boundary

- New `pluma/adapters/power.py` lazily invokes native GetSystemPowerStatus, with
  unsigned BYTE/DWORD declarations, explicit function signature and return-code
  handling. No device call, watcher or heavy dependency at import/startup.
- `battery_status` remains the exact typed READ ToolSpec, now requiring its
  killable owned worker and five-second timeout. Unknown arguments fail before
  policy/worker admission; policy denial is logged without starting a worker.
- The charging flag alone determines charging. AC connection is a separate
  observation. Unknown AC, presence, percent and charging remain null; no-battery
  is distinguished from unknown. Unknown lifetime sentinels and AC-powered
  estimates remain null. Unknown battery-saver values are explicit nulls.
  Invalid/contradictory reserved status fields fail closed.
- Structured observation includes native numeric fields, strict normalized data
  and deterministic human-readable copy. The verifier validates and recomputes
  the interpretation from the native snapshot and rejects mismatches. READ
  verification does not mutate hardware or perform an unowned second device call.
- A failed/unsupported read cannot claim success or turn test mode into an
  emulated device. Fixed errors exclude injected private exception values.
- The extra EOF blank line identified in E22's staged diff check is removed in
  this block. E22's command sequence mistakenly continued after that check; this
  formatting correction does not change its runtime behavior. Fresh checks below
  hash the corrected test source. No history rewrite or force push.

Interpretation follows Microsoft's [SYSTEM_POWER_STATUS contract](https://learn.microsoft.com/en-us/windows/win32/api/winbase/ns-winbase-system_power_status).
Its independent charging/AC fields, unsigned unknown sentinels and battery-saver
definitions are preserved rather than replaced with inferred power states.

## Verification

`output/p11-native-env/Scripts/python.exe output/p11_battery/run_checks.py`
uses isolated application/temp roots, actual Windows Jobs/process identities,
bounded subprocesses, source hashes, JUnit/log/JSON and actual pytest exits.
Test-only temporary system execution request restores in finally; no persistent
policy change or production idle feature.

Thirty-four focused cases cover native text/voice-mode FAST request pipelines,
real SQLite/reopened final history, original worker identity/verified exit, native
unknown/no-battery/error packet injection, strict schema/policy ordering, private
errors, observation mismatch and blocked-worker STOP/deadline. Native power reads
only: no battery/AC setting or physical power transition is requested. Voice-mode
requests use existing request construction, not physical microphone/STT acceptance.
No-battery/unknown/failure packets and blocked execution are explicit fixtures.

Final reviewed-source run arguments and actual pytest output:

| Run | Actual output | Runner wall |
|---|---|---|
| `focused-final` | 699 passed / 1 excluded, 106.74s | 107.704s |
| `regression-final` | 1017 passed / 3 skipped / 1 excluded, 130.30s | 131.473s |
| `raw-final` (`--runxfail`) | 15 passed, 0.74s | 1.695s |
| `containment-final` | 3 passed, 3.08s | 3.751s |
| `recovery-final` | 5 passed, 0.59s | 1.193s |

Actual exits zero; final source hashes match, fixture keys zero, all 115 FAST
cases isolated. Matrix traceability checker passes 298 source items / 324 rows.
Three existing fixed-corpus skips and the excluded system-changing elevation
case are disclosed separately. `git diff --check` and staged diff checks pass.
Catalog totals: 7 IMPLEMENTED / 44 MISSING / 4 DEFECTIVE / 18 UNVERIFIED.
Skips/exclusions do not count as acceptance. No performance/soak claim.

## Remaining P11 and recovery

This closes the bounded native battery READ catalog row, not full P11: native
power requests, system/network read gaps, clipboard/browser/terminal, identity-
safe inverse, verifier bounds, irreversible evidence and remaining A/D/H gates
still require work. No owner-approved waiver exists. Physical power-transition
and other device/release acceptance are not claimed by read-only fixtures.

Recovery before this block is `19b3ad3` in a separate detached worktree. Preserve
all recovery points and push only ui-wiring. Next safe work remains a bounded
P11 catalog/verification/inverse gap; P12 is not eligible or authorized.
