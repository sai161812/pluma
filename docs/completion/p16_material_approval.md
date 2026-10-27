# E85 — P16 native material approval completion

## Verdict

P16's required gate passes: the existing native risk dialog now receives actual
policy requests through the P15 contract, displays the redacted exact material
operation, and returns only a current task/call-bound decision. Denial, expiry,
STOP, stale/changed views, mismatched/duplicate decisions, disconnect,
uncertain writes and owner close fail closed. P17 has not started.

The [wiring contract](../../PLUMA.UI/PLUMA.UI/docs/wiring_material_confirmations.md)
documents lifetime and display semantics. Existing dark native styling is
retained. Dashboard submission/STOP entry remains disabled and belongs to P17.

## Prerequisites and source

Before editing, inspected AGENTS, the unchanged immutable master, P16/shared
execution contract, handoff/matrix, build-plan Phase 14, H-04/H-05/D-08,
existing dialog/shell/formatting code and policy/elevation/IPC tests. Reused
unchanged E80/E84 and E59 evidence within its recorded scope. Historical full
product claims were not treated as current acceptance: owner-deferred physical
focus/audio, broad performance and release gates keep their later owners.

Fresh pre-edit prerequisites: **167 Python tests passed in 16.11s** and
**101 native authenticated IPC checks passed**. These cover affected P00–P15
policy, STOP, ownership, lifecycle, protocol and ledger behavior. No completed
milestone was restarted.

- Source checkpoint: `c16f73c028d5238e6a40c32eb28d37dd6c673ff3`.
- Final tested source: `429ad1a6628ac9aecd5f80b7ad8ed9d7f4cd1cbb` (strict
  self-contained fixture schema and literal-text audit correction).
- Recovery point: `05642c8dce6060c3d0f1a73277828b1aebc3be2d`.
- Branch: `p12-preparation`. No branch switch, merge, reset, clean or force-push.
- Independent Sol review is ready; independent approval is not assumed.

## Implementation

`ConfirmationController` is one shell-window-owned async loop, with one
native presenter/dialog at a time. It polls the typed pending contract after
a 250 ms delay between bounded queries while the shell is open. It continues
readback during presentation, checks the exact displayed material again before
sending one decision, and retains bounded displayed-ID history to suppress
duplicates. It never uses formatted text as execution arguments.

Connection loss cancels the dialog and attempts bounded disconnect, then
reconnects with a fresh logical client identity after one second. Unknown
post-write outcomes are not retried. Closing the shell cancels/drains the
controller and dialog before disposing the shared IPC client. Backend task
STOP/admission and lease/deadline checks remain authoritative; UI visibility
never proves tool success or completed cleanup.

The native dialog shows material effect/target plus arguments, defaults to
Deny, and disables duplicate Approve invocation. A scoped literal-text option
preserves filenames, Unicode, underscores, punctuation and internal argument
whitespace. Ordinary popup copy keeps its existing formatter. Bounded wrapping,
scrolling, accessible names, theme, body width and native typography remain.
The gallery audit still checks exact full text, bounds, scrolling and
accessibility; its expected text now respects the explicit literal-data mode.

Changed implementation/tests: MainWindow; ConfirmationController and
NativeConfirmationPresenter; RiskApprovalDialog XAML/code; PopupMessageText;
SurfaceGalleryAudit; native controls project/runner and new end-to-end checks;
console IPC project/runner/controller checks; and the owned Python file fixture.
The source commits list all exact paths. No backend adapter, policy rule,
rollback algorithm, master requirement or DashboardPage command-entry source changed.

## Passing checks

The Python child environments use isolated LOCALAPPDATA/APPDATA/config paths.
A private ignored venv adds the already-declared Windows dependency
`pywin32 312`; system/user project environments and dependency declarations
are unchanged. Local versions: Python 3.12.10, Pydantic 2.9.2, pytest 8.3.3.

```text
output/p16-windows-env/Scripts/python.exe -m pytest -q tests/unit/test_p15_remaining_contracts.py tests/unit/test_ipc_request_contract.py tests/unit/test_policy_boundary.py tests/unit/test_policy_engine.py tests/unit/test_stop_protocol.py tests/unit/test_app_lifecycle.py tests/unit/test_runtime_shutdown.py tests/unit/test_elevation_dispatch.py tests/unit/test_elevation_native.py
191 passed in 23.39s; no skips/xfails.

output/p16-windows-env/Scripts/python.exe -m pytest -q tests/unit/test_power_actions.py
54 passed in 20.49s; no skips/xfails.
```

The 245 final Python passes cover exact policy, timeout/STOP, pre-state refusal,
truthful terminal/ledger outcomes, owned worker/shutdown behavior, one-operation
elevation and inert power/irreversible-intent paths. Counts overlap the earlier
prerequisite run and are not added to it.

```text
dotnet build PLUMA.UI/CoreIpc.Tests/CoreIpc.Tests.csproj --no-restore
Build succeeded; 0 warnings/errors.

dotnet build PLUMA.UI/SurfaceControls.Tests/SurfaceControls.Tests.csproj -p:Platform=x64 -p:UseSharedCompilation=false -nr:false -v:minimal
Build succeeded; 0 warnings/errors.

dotnet build PLUMA.UI/PLUMA.UI/PLUMA.UI.csproj --no-restore -p:Platform=x64 -p:SurfaceGalleryPreview=true -p:UseSharedCompilation=false -nr:false -v:minimal
Build succeeded; 0 warnings/errors.
```

The normal local native control executable passed **63 UI checks**, including
21 new checks over real owned native dialogs, actual button invocation,
authenticated Python IPC, registered safe file reads, independent verifier
readback and an owned WAL ledger. Approve, Deny, STOP, expiry and lifetime close
all agree with persisted task/action state. It checks literal Unicode filenames,
material prompt, Deny default, once-only decisions and dialog/client drain.
Fixture teardown refuses unapproved or duplicate executor entry. These are
native integration observations, not mocked presenter acceptance.

The console suite also tests failure/race paths using explicit presenter/client
fixtures and real IPC. Those fixture cases are distinguished from the native
WinUI checks above. Its latest local assembly was blocked before Main by
Application Control (0x800711C7), so it was tested on the normal authorized
hosted Windows workflow, with no security policy change or alternate-host bypass.

## Hosted exact-source verification

[Windows UI run 40472600843](https://github.com/sai161812/pluma/actions/runs/40472600843)
**passes** on final source `429ad1a`:

- **117 IPC checks**, including all new controller cases and actual backend
  approval/STOP with ledger readback.
- **63 native UI checks**, including the actual native dialog/backend flow.
- **663 native popup checks**, **195 formatting checks**, **64,537 layout
  checks**, **30 surface contracts** and **15 audio-visualizer checks**.
- Native application/control builds: zero warnings/errors; complete gallery/
  popup export and visible-copy scan pass. This is owned fixture rendering,
  not owner appearance approval or P25 physical taskbar/DPI acceptance.

Host: Windows Server 2025, Python 3.12.10, .NET SDK 10.0.403; lightweight core
dependencies include Pydantic 2.14.1. The workflow uses the existing declared
dependencies and normal Windows execution; it does not change security policy.

Hosted apphost SHA-256:
`652344B25055B442D4A3CB2B24B937EEA7BBEE3A0A0DCB1251A91004028EA315`.
The artifact is unsigned on that execution-authorized host; no signed release
or installed-artifact acceptance is inferred. Local passing native control DLL:
`622D64C512C2DCFB0A078E47F07D5A0C9B6A12774EB863D72463E321B2E5E074`.
The local control binary's functional source is unchanged by the final
fixture/audit-only correction; the final hosted build covers that correction.

[Hosted report artifact](https://github.com/sai161812/pluma/actions/runs/40472600843/artifacts/12718962555)
ZIP SHA-256:
`AFFA9BEAA71EE20E4EAD880F7460298AD84BDF5C65E592AFF316AE060B7661B4`.
Retained locally under ignored `output/p16-ci-pass/` and
`output/p16-ci-pass.zip`. Risk-dialog normal/stress fixture renders were
inspected; buttons remain visible, and long text is bounded and scrollable.

## Findings resolved and acceptance boundaries

The first hosted run
[40471945571](https://github.com/sai161812/pluma/actions/runs/40471945571)
failed because the fixture's dictionary schema required an undeclared-in-CI
optional JSON-schema validator. Validation correctly refused before policy.
The fixture now uses strict Pydantic arguments from core dependencies, without
loosening validation or adding an implementation fallback. The first local
elevation run found missing pywin32; the isolated declared-dependency install
above closes that environment gap. These failures are not counted as passes.

No new power, destructive or UAC operation was used to demonstrate the dialog.
Fresh elevation checks include inert exact dispatch/intent, admission and
owned-child cleanup/native read-only cache observations. The separately
permitted actual DNS-only UAC proof remains [E59](p11_acceptance_retry.md):
operation exit/readback, verified ADMIN ledger and CLOSED_VERIFIED shutdown.
Its adapter/broker are unchanged; no new permanently elevated resident or
unrestricted shell was introduced. The shell manifest remains asInvoker.

There are no remaining P16 implementation/gate packets. P25 owner interaction,
mixed displays/taskbar/accessibility and later release/security breadth are
still separate requirements, not passing results here. Ready for independent
Sol review and then P17 when instructed. P17 has not started.

Full logs remain ignored: `output/p16-prerequisites.log`,
`output/p16-python-regression.log`, `output/p16-power-fixtures.log`,
`output/p16-native-controls.log`, build logs and hosted artifacts. Source
recovery starts from the preserved commit above; use a reviewed revert or a
separate checkout, preserving later source and runtime data. Source recovery
cannot undo an external operation; runtime undo still requires captured
tool-specific evidence.
