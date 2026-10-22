# P11 native audio observations and fail-closed readback (E20)

2026-10-20. P11 remains in progress; the owner expressly forbids P12. Starting
source `f19f261` was clean and pushed on ui-wiring. Its prerequisite safety/
process block passed 560 focused, 878 isolated regression, 15 raw audit, 3 native
containment and 5 recovery checks immediately before this block. Other branches,
worktrees, archive/stash/tags, disabled action entry and immutable contracts stay
preserved. No approval UI or appearance work is included.

## Reproduction and repair

Before editing, the installed native endpoint was available but the existing
helper returned None: it called Activate on pycaw's newer AudioDevice wrapper,
which exposes EndpointVolume instead. Injecting a successful setter and missing
readback made set_volume, mute and unmute all return ok=True/verified=True.
No physical write ran in this reproduction.

- New `pluma/adapters/audio.py` uses stable Core Audio interfaces through lazy
  comtypes/pycaw bindings. It activates the default multimedia render IMMDevice
  directly, reads scalar/mute and checks active state/default endpoint identity
  around the operation. COM initialization is balanced on the calling thread;
  interface references are cleared before uninitialization even on failure.
- Exact registered `get_volume` and `list_audio_devices` close two catalog-name
  gaps. `get_volume_status` remains a compatible typed read with the same proof.
  Volume includes endpoint ID, scalar, rounded percentage, mute and explicit
  fixture flag. Device enumeration includes both flows/all native states,
  endpoint IDs, optional names, actual observed count and truncation; a strict
  1..128 bound defaults to 64. Missing display-name properties are null, not
  invented names/devices. A failed required identity/state query fails the read.
- Strict argument/output models reject coercion, extras, NaN, incoherent scalar/
  percentage, unknown direction/state, duplicate endpoints and false truncation.
  READ schema validation precedes policy and dispatch. All six audio ToolSpecs
  require five-second killable owned workers with no thread fallback.
- Mutators read an endpoint identity before writing, require that identity in
  the native setter and independently read it back afterwards. Missing, changed
  endpoint/mode or contradictory state fails with fixed error copy and no fake
  requested-value substitute. Set volume also preserves/compares mute state.
  Native setters themselves read back the write; call return alone is not proof.
- Parent verifiers validate the trusted worker observation/proof without another
  unbounded resident-thread COM call. Explicit PLUMA_EMULATE_AUDIO remains a
  fixture seam with emulated adapter and fixture copy/proof. Native failures,
  non-Windows execution and PLUMA_TEST_MODE cannot implicitly select emulation.
  Real audio state is never written to the fixture cache.

These changes do **not** finish mutating audio acceptance. Caller-side pre-state
capture, mutation/partial-effect journaling, endpoint-bound conflict-safe inverse
and bounded rollback still require P11 work. Existing set_volume/mute/unmute
catalog rows remain UNVERIFIED; no physical write/undo was performed here.

Primary contracts checked: [endpoint enumeration](https://learn.microsoft.com/en-us/windows/win32/api/mmdeviceapi/nf-mmdeviceapi-immdeviceenumerator-enumaudioendpoints),
[native scalar readback](https://learn.microsoft.com/en-us/windows/win32/api/endpointvolume/nf-endpointvolume-iaudioendpointvolume-getmastervolumelevelscalar).

## Verification and limits

Interpreter: ignored `output/p11-native-env/Scripts/python.exe`, Python 3.12.10
x64 on Windows 11 10.0.26200. Windows packages are confined to that environment:
pywin32 312, pycaw 20260927, comtypes 1.4.17; existing declared dependencies are
unchanged. No global package installation or Windows security/power-policy change.

Ignored runner `output/p11_audio/run_checks.py` allocates isolated local/roaming/
temp roots, clears PLUMA_* overrides, bounds pytest/external commands and saves
logs/JUnit/JSON with actual exit/source hashes. Fixture key deletion is limited to
files under the verified isolated root. Runtime/test source never changed while
pytest was running. No audio, screenshot, credential, device names or raw logs
are committed; durable evidence is redacted here.

Initial audio/legacy fault checks: **62 passed in 16.57s**. Initial combined
focused run: **621 passed / 1 failed / 1 excluded in 328.99s**. The failed native
voice/device-list case spent 234.427 seconds. Read-only SQLite shows its action
verified in 614.687ms; task FAILED retained WORKER_CLEANUP_UNVERIFIED, verified
empty Jobs and deferred temporary cleanup. A later owned retry verified worker
exit. We do not relabel this failed run as a pass.

Windows System Kernel-Power events 506/507 show Modern Standby entering
**18:13:22** and leaving **18:17:28**, overlapping the case (run began 18:12:06,
Asia/Calcutta). This supports suspension affecting cleanup; it does not recreate
the exact suspended worker state. No test deadline/assertion was weakened.

The same failed case passed unchanged in **1.75s**, then the combined focused
suite passed **622 / 1 excluded in 98.75s**. During these and final runs only,
the local runner requests ES_CONTINUOUS|ES_SYSTEM_REQUIRED and restores the
prior thread state in finally. No display/away-mode flag, persistent policy or
resident feature is added. User-initiated sleep remains permitted. This is
documented by [SetThreadExecutionState](https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-setthreadexecutionstate);
it is an active-test environment condition, not suspend/recovery acceptance.

Review then corrected one fixture proof string that said native and added nine
explicit-emulation/endpoint-before-write/COM-balance/malformed-device checks.
Final source focused: **631 passed / 1 excluded in 94.13s**. Final isolated regressions: **949 passed / 3 skipped / 1 excluded in 126.04s**
(pytest time; runner wall 272.908s). Raw --runxfail audit **15 passed in 0.77s**;
native containment **3 passed in 3.47s**; recovery **5 passed in 0.84s**.
All final source hashes match, pytest exits are zero, fixture key counts zero
and all 115 FAST cases carry isolation tags. Skips/exclusion are not acceptance.
The runner/pytest elapsed gap is retained; the temporary power request is not a
guarantee against Modern Standby. This block makes no performance/soak claim.

Commands, using the interpreter above:

```text
output/p11_audio/run_checks.py audio-tools-first
output/p11_audio/run_checks.py focused-final
output/p11_audio/run_checks.py audio-unchanged-repro
output/p11_audio/run_checks.py focused-verified
output/p11_audio/run_checks.py focused-final-source
output/p11_audio/run_checks.py regression-isolated
output/p11_audio/run_checks.py raw-final
output/p11_audio/run_checks.py containment
output/p11_audio/run_checks.py recovery
python docs/completion/verify_requirements_matrix.py
git diff --check
```

Real native tests clear emulation overrides and exercise the three read names
through typed registry/policy, actual task-owned spawned workers/Jobs, SQLite
verification, cleanup, storage-last close and reopened text/voice request history.
The observed physical endpoint state is unchanged before/after; 26 native
capture/render endpoints were observed, with unknown names explicit. Voice/STT/
planner seams are inert; this is not microphone or inference acceptance.

Denied calls create no worker and record executed=false. Blocked owned probes
use the same prewarmed native worker, retain the one-second response deadline
and verify STOP/timeout, first cause, worker absence, history and no late marker.
Write refusal, missing/changed post-read, backend failure and COM error/balance
checks are injected and never counted as physical mutation/undo acceptance.

## Remaining P11 and recovery

Only CAT-get_volume and CAT-list_audio_devices become bounded IMPLEMENTED.
Totals: 6 IMPLEMENTED, 44 MISSING, 4 DEFECTIVE, 19 UNVERIFIED; all 73 remain.
Native write/undo, mutation journaling and the other mandatory catalog/A/D/H
gaps stay open. Next safe work is a bounded P11 mutation-evidence/undo block,
under the existing instruction. Do not start P12, enable command entry or merge.
Recovery before this block: `f19f261` in a separate detached worktree. Commit
and push only ui-wiring; no missing capability is waived.
