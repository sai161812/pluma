# E100 ? P21 settings persistence foundation

2026-11-03, Asia/Calcutta. This is the first bounded P21 packet, not full
milestone completion. P22 and later work are not started or authorized here.

## Prerequisites and source

The clean authorized checkout was `p12-preparation` at
`0468a031238261bee5bc79bd04b16a3d1964a3a9`, matching origin/main and
origin/p12-preparation. E99's exact-source native P20 gate and merged results
remain applicable to the unchanged folder/UI path. The immutable master Git
blob is still `01b693dbf898b662aa4cd67736c1a0e8a21cf3e3`.
The shared contract, P21 prompt, current handoff, build phases 0/13/14,
acceptance A-01 and applicable lifecycle/STOP/privacy requirements were reviewed.
The existing SettingsContract is abstract; surface 2 is still preview-only;
P15 defines a read-only snapshot, not Save or effective-setting activation.

Pre-edit isolated regression: **157 passed**, no skips/xfails. Two added
regressions then fail on the old implementation: startup loads default plan
limit 8 instead of 3 from the explicitly selected roaming directory; a missing
PLUMA_CONFIG source instead loads another profile's plan limit 2. Both failures
and original output are retained. No personal settings are used.

Initial implementation/test commit: `6534ded6c8208d5a32067ab77ca621698c05b81a`.
Review then reproduced one compatibility regression: an explicitly empty config
must retain the original default-loading behavior. `empty-config-review` records
**1 failed / 1 passed** before correction. Follow-up and final tested source:
`41c45c818a8e5e811e05d8659b9d98fbcc66f366`. It preserves fallback semantics while
using the selected source; both None/empty cases are now tested. Subsequent
checkpoint changes are documentation only. Pushed recovery ref:
`recovery/pre-p21-e100-20261103` at the original `0468a03`.

## Behavior closed by this packet

- `pluma/config/settings.py` provides explicit local JSON storage, a 256 KiB
  read/write bound, strict envelope version 1, duplicate/non-finite JSON
  refusal, sanitized errors and content revisions. Legacy override objects
  migrate in memory without an automatic write. Unrelated keys are preserved.
  Legacy YAML remains readable but this writer never writes JSON into YAML.
- Save takes an observed revision and a small explicit field allowlist: three
  hotkeys, existing planner step limit, and planner/STT model file paths. It
  checks known hotkey syntax/aliases and duplicate bindings, the existing
  planner hard cap, file existence/readability/nonempty content and basic
  absolute/non-UNC model path shape. Unknown fields, including new policy,
  raw-audio, wake-trigger and grace edits, are refused. Existing locked safety
  overrides cannot be laundered through a save. No runtime or model is started.
- A non-waiting native cross-process writer lock protects cooperating writers.
  A uniquely created sibling is flushed/fsynced and atomically renamed;
  success requires a fresh snapshot with exact revision and value readback.
  Exact valid prior file bytes are retained in `.previous` before replacing an
  existing source. On failed postcommit verification, only this operation's
  exact candidate bytes can be rolled back, with independent restoration
  readback; an intervening different edit is preserved and failure is factual.
- Corrupt or unknown-version sources fail closed and are left intact. A valid
  `.previous` remains readable for controlled recovery. No silent fallback,
  automatic corrupt-file replacement or user-facing recovery action is added.
  Cancel means discarding the in-memory draft, with no persistence side effect.
- `loader.py` consumes legacy/versioned JSON and honors PLUMA_APPDATA via
  PlumaPaths. Explicit missing PLUMA_CONFIG never falls through to another
  profile. `app.py` loads its selected roaming source when no config is supplied.
  New application instances consume saved limits/paths/bindings, and the
  existing settings_query agrees with effective constructed values. The
  planner/STT lifecycles remain COLD and verified close joins owned lifecycle
  work. This is runtime construction evidence, not native model inference.

This module is an internal storage primitive, not an execution entry point.
No planner tool, unauthenticated save request, direct UI file write or bypass
of ToolSpec/policy/task ownership has been introduced. A future production Save
must be admitted through typed owned execution with material/pre-state evidence
and STOP semantics. All supported edits currently require core restart; saving
never mutates an active runtime or claims that a shortcut was registered.

## Commands and evidence

Fresh ignored directory (historical evidence is not overwritten):
`D:/Workspace/DEVEL/PLUMA/output/p21-e100-20261103-085246-82bc280c/`.
The retained runner records exact commands, source commit, platform, durations,
stdout/JUnit, failures and isolated APPDATA/LOCALAPPDATA/TEMP/TMP locations.
Python is 3.12.10 from the existing declared dev/Windows environment:
`D:/Workspace/DEVEL/PLUMA-verified-integration-20261103/output/integration-checks-e98/test-env/Scripts/python.exe`.
Local Windows version: `Windows-11-10.0.26300-SP0`.

```powershell
python <evidence>/run_checks.py pre-edit tests/unit/test_config.py tests/unit/test_schemas.py tests/unit/test_ipc_request_contract.py tests/unit/test_app_lifecycle.py tests/unit/test_runtime_shutdown.py tests/unit/test_stop_protocol.py tests/unit/test_ownership.py
python <evidence>/run_checks.py reproduced tests/unit/test_settings_store.py
python <evidence>/run_checks.py source-focused tests/unit/test_settings_store.py tests/unit/test_config.py tests/unit/test_schemas.py tests/unit/test_app_lifecycle.py tests/unit/test_ipc_request_contract.py tests/unit/test_runtime_shutdown.py tests/unit/test_stop_protocol.py tests/unit/test_ownership.py
python docs/completion/run_p01_p13_checks.py prerequisites --output-dir <evidence>/prerequisites
python docs/completion/run_p01_p13_checks.py contracts --output-dir <evidence>/contracts
python <evidence>/run_checks.py final-paths tests/unit/test_paths.py tests/unit/test_phase13_5_stage_i_packaging.py tests/unit/test_phase13_5_release_audit_fixes.py::test_audit_5_production_runtime_lifecycle_wiring tests/unit/test_phase13_5_release_audit_fixes.py::test_audit_6_config_path_loading
dotnet run --project PLUMA.UI/CoreIpc.Tests/CoreIpc.Tests.csproj --verbosity quiet -p:UseSharedCompilation=false
python docs/completion/verify_requirements_matrix.py
git diff --check
```

`run_checks.py` uses pytest `--runxfail`, treats unhandled-thread warnings as
errors and writes unique JUnit/command files. Skips are rejected, not counted as
passes. All tests use owned temporary files/storage. The model files are tiny
owned path fixtures, not runnable model evidence. The real Windows sharing-denial
check uses an owned open file handle, closes it in finally and verifies unchanged
primary/previous bytes. The remaining failure injections are clearly fixtures.
No personal file, clipboard, window, browser profile, device or power operation
is performed. A fresh Python child also proves save/reload import no ML/device
runtime; it has a bounded subprocess lifetime and starts no descendants.

Final source `41c45c8`: **209 focused** in 11.421 s (52 new cases),
**501 prerequisites** in 53.594 s, **8 paths/legacy packaging checks** in 1.640 s,
zero failures/errors/skips/xfails. The **352 contract regressions** in 20.891 s
passed on `6534ded`; the follow-up only restores the empty-config startup case
and adds its fixture. Contract source/behavior is unchanged; those checks are
reused rather than relabelled as a new run. Counts overlap. The prerequisite suite includes existing STOP admission,
worker cancellation, ownership, cleanup, rollback, shutdown and crash checks.
No unchanged native model/device/physical evidence is relabelled as fresh.

The local C# build completed, but Application Control blocked its assembly before
execution (`0x800711C7`, FileLoadException). `native-ipc/results.txt` and
`command.json` preserve the nonzero result; it is not an IPC acceptance pass.
Security policy was not altered. The initial Windows CI run
`41608113785` on `6534ded` was cancelled by the workflow's existing concurrency
rule after the corrected source was dispatched; it is not a pass.
[Normal Windows CI run 41608724329](https://github.com/sai161812/pluma/actions/runs/41608724329)
passes on exact source `41c45c818a8e5e811e05d8659b9d98fbcc66f366`:
**285 IPC / 214 native UI / 663 popup / 195 formatting / 64,537 layout / 30
surface** checks, plus audio visualization and copy gates. Both builds report
zero warnings/errors. Windows native host is interactive, build 26100. Original
P20 native folder visibility, saved verification and newly owned window cleanup
also execute and pass; no longer deadline, skipped operation or diagnostic
callback is used. This is the existing native integration/regression gate, not
acceptance of an unwired native Settings Save action.

Artifact `13219075024`, downloaded and API digest verified:
`5d7d852605153cb8e867345f7c7555e7d9bb2d4549aa07d0802c5d610b002f80`.
Unsigned preview executable SHA-256:
`AC10335508DE7A3A6F25872AB3145F009BD6579C0041CA7850EE1DC8E25EE777`.
Reports are retained under
`ci-41608724329/extracted/20261103-091047-d545dd10/`.
This is a test build, not a signed installed release. `verified-source-identity.json`
records source, JUnit digests, native summary and artifact identity. The final
matrix validator passes **298 source items / 335 traceable rows**; whitespace
and scope checks pass. No product/test change follows the exact-source checks.

## Remaining P21 and next safe packet

1. Implement the typed authenticated settings edit/save/readback contract,
   distinguishing persisted and effective values and explicit restart needs.
   Use registered task-owned policy/admission, bounded workers, captured
   pre-state, evidence-based undo and priority STOP; never expose this storage
   helper directly as resident/UI mutation authority.
2. Bind the existing dark surface 2 and SettingsContract to actual draft,
   Save/Cancel/reload/conflict/error results. Remove production preview choices
   and preserve layout, typography, spacing and approved styling.
3. Prove native OS hotkey availability/conflicts and safe owned re-registration
   without losing the independent STOP binding. Current tests establish syntax,
   configured collisions and constructed readback, not OS registration.
4. Finish local runtime/model path admission (including reparse/mapped-volume
   and runtime-format/compatibility validation), voice activation, effective
   measured grace, privacy/logging and allowed policy behavior. File readability
   alone is not proof of model compatibility. Do not add unsupported toggle
   semantics, benchmark claims or a permanent service/privilege.
5. Verify the combined native save/cancel/restart/application/error/rollback
   flow. Controlled corrupt-source recovery remains a future admitted operation;
   valid backup availability is established here without overwriting corruption.

Next safe packet is item 1, using this store inside the typed owned boundary,
followed by the native page binding. **P21 remains incomplete; P22 is not
eligible.** The bounded persistence packet and its integration checks are
complete and ready for independent Sol review; independent approval is not
assumed. E94's owner-approved physical C-02 timing retest remains deferred to P25.
Other physical, performance, installation/recovery, security and release gates
keep their documented scope.

Recovery: reviewed new reverts of `41c45c8` and `6534ded` after inspecting dependents; preserve
user settings and `.previous` bytes. Do not reset/clean/force-push, reinterpret
new envelope metadata as legacy overrides after downgrade, or delete uncertain
runtime evidence. Older binaries do not understand version 1; before an actual
binary downgrade, retain the versioned source and explicitly restore validated
legacy prior bytes if available. No installer/schema rollback is claimed.
