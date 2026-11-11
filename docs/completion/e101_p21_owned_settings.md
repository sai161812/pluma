# E101 ? P21 owned Save and C# settings contracts

2026-11-03, Asia/Calcutta. Two bounded P21 packets: production typed settings
admission/verification/undo and its authenticated C# request/readback integration.
This does not complete P21 or authorize P22. Surface 2 and SettingsContract are
still unwired; no XAML, palette, typography or layout changes are included.

## Prerequisites, scope and recovery

Started on clean `p12-preparation` at `d9f1fbcc96c871e199bc22306a0894c31675d2ce`.
The unchanged master specification was rechecked by its Git blob
`01b693dbf898b662aa4cd67736c1a0e8a21cf3e3`; E100 and applicable P21/shared,
build-plan and acceptance A-01/A-03/A-05/A-07, G/H/lifecycle contracts were read.
Earlier unchanged full-master reading and E99/E100 evidence were reused.
Fresh pre-edit settings/IPC/memory/STOP/shutdown/startup selection: **180 passed**,
no skips/xfails. No unresolved independent-review approval is invented.

Commits: `163783a` introduces typed Save/readback, the owned tool and C# protocol;
`334fee5` corrects the native fixture and credential-test ordering;
`e54c9d8` adds durable owned staging/recovery and correct terminal semantics;
`45c2f07` links the shared protocol into native control builds;
`ef8013a08eecaf079f548373bf24ab0c989a7e24` verifies persisted staging release before
terminal history. The last commit is the final tested product/test source. Recovery ref `recovery/pre-p21-e101-20261103` points
to the original `d9f1fbc` and is pushed. Main remains `0468a03`; no merge, branch
switch, reset, clean, force-push, security bypass or new dependency occurs.

## Completed behavior

- New version-1 `settings_edit_query` and `settings_save` messages are strict,
  bounded and canonical-UUID correlated. Unknown/null/boolean/out-of-range fields
  fail before policy/task admission. The edit snapshot separates persisted
  values from constructed effective configuration, exact content revision and
  restart fields; its explicit editable-field list is only `max_plan_steps`.
  Three hotkeys are read-only configured values, not claimed OS registrations.
- Saves use the common resident admission/deduplication/STOP fence, one capsule,
  one exact FAST typed plan and registered MEDIUM `save_settings` ToolSpec.
  The existing material-confirmation broker decides the exact request. Policy
  denial produces no settings mutation; duplicates return the accepted task,
  and changed material cannot reuse a request UUID. Unknown writes are not
  automatically retried. The independent STOP transport/capacity is unchanged.
- The settings source comes from application composition, including explicit
  CLI config paths, never tool/planner arguments or an arbitrary request path.
  Pre-state capture, mutation and independent readback use required owned,
  bounded workers. A source revision mismatch refuses the mutation. Success
  requires actual disk readback; saved values never mutate the current runtime.
  A newly constructed real runtime reads the persisted limit into its actual
  planner validator/adapter while model and STT remain COLD.
- The inverse captures only changed public fields, presence/default semantics,
  relevant configuration revisions and ownership proofs, not unrelated config
  content/secrets. File-format migration is retained; undo restores semantic
  settings values (or original file absence), not original whitespace. Selected
  undo displays actual restoration material, uses the common durable once-only
  claim/consumption path and independently checks restored state. A later owner
  edit is preserved. Cross-source settings undo is refused if that source is
  not the currently configured source; no profile is guessed.
- Bare hash values were redacted by the existing secret filter in an initial
  inverse trial. Receipt hashes now use a strictly validated `sha256:` namespace;
  generic secret redaction is unchanged. The real persisted inverse/selected
  undo regression passes, including verified claim consumption and refusal to
  repeat. Unrelated synthetic private configuration never enters its receipt.
- Atomic writes now stage inside an exclusively created task-specific directory
  on the settings volume. The parent captures its identity and verifies the
  durable resource row before admitting any settings bytes. The same owned
  staging rule applies to manual inverse writes. Cleanup uses the existing
  identity/worker-absence safeguards; it never deletes the settings parent or
  an unrelated file. No random untracked sibling holds partial task data.
  The verified release time is read back from the persisted resource row before
  terminal history is published, keeping cleanup and ledger readback consistent.
  Released staging timestamps are independently read back from SQLite before
  the terminal cleanup report; the resource row cannot remain falsely active.
- Settings-specific pending recovery independently compares the atomic source
  with the captured before/after revisions: an exact before state establishes
  no settings change; an exact after state admits only the captured guarded
  inverse. Any third state remains a conflict with retained evidence. STOP and
  timeout cover both commit sides, real worker exit, partial staging-file
  cleanup, resource-journal readback and preservation of an owner sentinel.

## Deliberately unavailable fields and observed lifecycle gap

Inspection of `ResidentCore._hotkey_loop` shows Text/STOP RegisterHotKey failures
are logged and startup continues. No personal hotkey was probed to reproduce it.
New hotkey edits therefore remain absent from SettingsChanges/C# SettingsEdits
and fail before admission. Complete OS availability, safe registration/failure
handling and preservation of priority STOP are the next lifecycle requirement;
these configured strings are not native availability evidence.

Model/runtime paths, voice activation, warm grace, debug/privacy and policy
edits likewise remain absent from this production writer until their effective
behavior and validation are completed. E100's internal file-store capabilities
are not unrestricted UI/planner authority. No always-on microphone/network
service, permanent elevation, safety toggle or blanket confirmation bypass is
introduced. The only production editable setting in E101 is the bounded existing
planner step limit, with explicit confirmation and Core restart required.

## Fresh commands and evidence

Unique ignored root:
`D:/Workspace/DEVEL/PLUMA/output/p21-e101-20261103-115913-71e90ae8/`.
Historical reports are not overwritten. Python: declared dev/Windows environment
at `D:/Workspace/DEVEL/PLUMA-verified-integration-20261103/output/integration-checks-e98/test-env/Scripts/python.exe`,
3.12.10 on Windows 11 build 26300. All tests use isolated APPDATA, LOCALAPPDATA,
TEMP and TMP; existing FAST desktop isolation is enabled where applicable.
Only owned files/processes/pipes/credentials are used. No personal clipboard,
window/profile, audio device, power or hotkey registration is touched.

```powershell
python <evidence>/run_checks.py verified-final-focused tests/unit/test_settings_execution.py tests/unit/test_settings_store.py tests/unit/test_ipc_request_contract.py tests/unit/test_app_lifecycle.py tests/unit/test_memory_tools.py tests/unit/test_manual_undo.py tests/unit/test_p20_detail_undo.py -p tests.fixtures.desktop_isolation
python docs/completion/run_p01_p13_checks.py prerequisites --output-dir <evidence>/verified-final-prerequisites
python docs/completion/run_p01_p13_checks.py contracts --output-dir <evidence>/verified-final-contracts
dotnet build PLUMA.UI/CoreIpc.Tests/CoreIpc.Tests.csproj --verbosity quiet -p:UseSharedCompilation=false
./PLUMA.UI/verify-ui.ps1
python docs/completion/verify_requirements_matrix.py
git diff --check
```

Exact source/test identity, actual invocation, durations, stdout/JUnit and failure
counts are retained per run. `--runxfail` is used; skips and unhandled-thread
warnings are not accepted as passes. Existing fixture/mock checks are not
relabelled native model/device acceptance. Local Application Control's previously
recorded block is not bypassed or counted as successful C# execution; the normal
execution-authorized Windows CI provides the cross-language native gate.

Retained development failures:

- The first unit attempt records **2 failed / 13 passed** from incorrect new-test
  assumptions: terminal readback requires the original submission UUID, and the
  controller reference must be captured before STOP clears its capsule link.
- The durable selected-undo trial fails because raw receipt hashes were redacted;
  the guarded namespace fix and real selected-undo regression close that defect.
- CI `41633702312` on `163783a` fails at new fixture startup (wrong IPC constructor
  keyword); the fixture now uses the runtime's owned server and correct pipe
  address. A bounded local actual start/close regression covers that setup.
- The settings check is ordered after P09, preserving the original fresh-key
  precondition. No existing credential assertion is removed or relaxed.
- CI `41634041233` on `334fee5` passes actual Save and persisted/effective readback,
  then fails the new denial assertion. The production contract verifies a failed
  terminal lifecycle independently from action success: completion_verified can
  be true for FAILED while the saved action's verified flag is false. New Python
  and C# checks assert that distinction, persisted FAILED/no residual, unchanged
  values and a denied/unverified action; no action-success assertion is weakened.
- Initial staging tests retain the partial directory because generic pending
  rollback deliberately defers cleanup. Settings-specific atomic-state readback
  now resolves known before/after states; third states continue to fail closed.

- CI `41635574455` on `e54c9d8` passes **308 actual IPC checks**, including all
  new real settings Save/deny/restart cases. It then fails native control build:
  that linked-source test project omitted CoreSettingsProtocol.cs. `45c2f07`
  adds the actual dependency; no compile assertion or warning gate is weakened.
- `resource-release-before` reproduces a stale null release timestamp for the
  new journaled staging directory despite successful cleanup. The scoped
  persisted-resource release hook now reads back the exact verified timestamp
  before terminal history; `resource-release-after` passes. Cleanup-report rows
  are distinguished from actual temporary-resource rows.
- CI `41636376809` on `45c2f07` is superseded/cancelled by the final-source run,
  not counted as a pass.

Final tested source `ef8013a08eecaf079f548373bf24ab0c989a7e24` passes:

| Check | Result |
|---|---|
| Final affected selection | **124 passed in 43.250 s**, including 22 new settings cases |
| Final P01?P13 prerequisite selection | **501 passed in 52.469 s** |
| Final contract regressions | **352 passed in 26.875 s** |
| [Windows run 41636726654](https://github.com/sai161812/pluma/actions/runs/41636726654) | **308 authenticated IPC / 214 native UI / 663 popup / 195 formatting / 64,537 layout / 30 surface** checks; audio/copy gates pass, both builds zero warnings/errors |

No failures/errors/skips/xfails are counted as passes. Counts overlap. Prior
intermediate results remain historical evidence, not substitutes for this final
source. Failed/cancelled native artifacts remain retained, not reclassified.
The actual settings graph is used for native Save/deny/restart and checked for
joined close, actual planner limit and cold lifecycles. Existing P20 native Shell
folder visibility/saved verifier/new owned-window closure also pass. This gate
is not acceptance of the still-unwired native Settings page.

The final Windows host is interactive build 26100. Artifact `13231266252` was
downloaded and its API SHA-256 verified:
`2d660ea34c1f24b87a174c860a1fca108f2212ddeaba5290da2ccd04dec26fe0`.
Unsigned preview executable SHA-256:
`64F2AC0674485C47229F4543B5ECF2FDF4A2E74464A9AFB92CB056B20D112694`.
Native logs/summary are under
`ci-41636726654/extracted/20261103-123435-33e9bbaa/`; the source/JUnit/native
identity manifest is `verified-source-identity.json`. This is an unsigned test
build, not a signed installed release. Matrix validation passes **298 locked
source items / 336 traceable rows**; whitespace/scope checks pass. Only these
completion records change after exact-source testing. These two bounded packets
are complete and ready for independent Sol review, without assumed approval.

## Remaining P21 and next safe packet

1. Bind SettingsContract and the native dark surface to real edit/readback,
   Save/Cancel/reload, terminal/denial/conflict/error results; remove preview
   selections. Keep unsupported controls unavailable with factual explanations.
2. Repair/verify the hotkey lifecycle and native availability/conflict handling
   before allowing those edits. Preserve the independent STOP binding throughout.
3. Complete local model/runtime path admission and compatibility, voice activation,
   measured effective grace, privacy/logging and allowed policy application.
4. Complete controlled corrupt-source recovery and combined native Settings-page
   save/cancel/restart/application/rollback acceptance. A cold runtime/file fixture
   is not physical registration, microphone or native model acceptance.

Next safe packet is native Settings controller/view binding for the supported
subset and truthful read-only values, then guarded hotkey lifecycle. P21 remains
incomplete and P22 is not eligible. E94's owner-approved C-02 physical timing
retest remains deferred to P25; later install/physical/performance/security/release
gates remain open. Independent Sol approval is not assumed.

Recovery uses reviewed new reverts of dependent commits, preserving settings,
prior bytes, durable resources and uncertain inverse claims. Never delete/reset
receipts to retry a possibly committed inverse, restore an old loader over a
version-1 source without retaining/validating prior data, or force-push history.
