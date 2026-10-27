# E86 — P17 dashboard submission and independent STOP

Follow-up: [P18 E87](p18_event_feed.md) now implements its first bounded feed/
notice packet. P18-not-started statements below describe this P17 checkpoint.

Date: 2026-10-27 (Asia/Calcutta). Branch: `p12-preparation`.
Tested implementation: `fc552ee04f152644da43da68a215141541185528`.
Recovery point: `af855cb97a1571effd22f9aca8f67d144dc383c0`, whose tracked tree
is identical to completed P16 `83309554be856593cbd6e8996d2152d7d1b9b76f`.

## Verdict and scope

P17's required gate passes. Dashboard Enter/Run submits one typed request through
the shared backend; one shell-owned controller preserves identity and blocks
duplicates. A separately tracked priority STOP remains available while execution,
planning, observation or cancellation presentation is waiting. Exact persisted
terminal, verification and residual evidence govern UI results. Unknown writes
are never replayed. P18 has not started; independent Sol approval is not assumed.

The [wiring contract](../../PLUMA.UI/PLUMA.UI/docs/wiring_command_submission.md)
describes admission, readback, fencing, navigation and close. Changed runtime
files: CommandController, Dashboard XAML/code, MainWindow, C# client/protocol,
Python IPC schemas and ResidentCore. Changed tests: console/native runners and
project links, owned Python fixture, new controller/native command/fence tests,
native fixture lifetime helper and capability assertion. No adapters, planner,
policy, rollback implementation, immutable master or theme resources changed.

## Prerequisites and safe reproduction

Read AGENTS, unchanged master, P17/shared contract, relevant build phase and
acceptance, current handoff/matrix, owner decisions and earlier findings. The
checkout was clean on the P16-equivalent rollback. Compared implementation and
evidence rather than assuming prior completion: all **23 E80 recorded Python
source/test hashes match** (raw or LF-normalized). P00–P14's scoped E80 closure
and physical deferrals remain applicable; P15 E81–E84 contracts and P16 E85
confirmation source were inspected. Fresh pre-edit checks passed **191 Python
prerequisites in 22.76s** and **117 authenticated C# IPC checks**.

Reused the preserved P17 implementation from `0993e4f`/`862b3fd` after source/test
review, without switching branches or restarting earlier work. Before applying
it, ran its fence tests from an ignored copy: **3 failed / 5 passed**. P16 refused
the unknown fence field and had no fence state. After implementation: **8 passed
in 0.45s**. The blocked-history reproduction proves STOP returns before the
ordinary insertion lock releases; late executor admission is refused and the
actual interrupted-history residual is retained rather than called clean STOP.

## Fresh verification

All Python runs use the ignored declared-dependency venv and isolated
LOCALAPPDATA/APPDATA/PLUMA_CONFIG beneath
`output/p17-authorized-20261027-191615/`. No skips or xfails were counted.

```text
output/p16-windows-env/Scripts/python.exe -m pytest -q tests/unit/test_p17_submission_stop.py
8 passed in 0.45s

output/p16-windows-env/Scripts/python.exe -m pytest -q tests/unit/test_p17_submission_stop.py tests/unit/test_p15_remaining_contracts.py tests/unit/test_ipc_request_contract.py tests/unit/test_policy_boundary.py tests/unit/test_policy_engine.py tests/unit/test_stop_protocol.py tests/unit/test_app_lifecycle.py tests/unit/test_runtime_shutdown.py tests/unit/test_elevation_dispatch.py tests/unit/test_elevation_native.py
199 passed in 24.65s

output/p16-windows-env/Scripts/python.exe -m pytest --runxfail -q tests/unit/test_backend_wiring_audit.py tests/unit/test_worker_cancellation.py tests/unit/test_rollback_engine.py tests/unit/test_power_actions.py
100 passed in 26.81s
```

The additional suite includes the 15 original BA assertions, actual owned worker
cancellation/absence, evidence-based reverse rollback/conflicts and inert power
policy. These are not physical power, clipboard or personal-desktop acceptance.
The focused eight overlap the 199; the earlier prerequisite count is not added.

```text
dotnet build PLUMA.UI/CoreIpc.Tests/CoreIpc.Tests.csproj --no-restore -p:UseSharedCompilation=false -nr:false -v:minimal
dotnet build PLUMA.UI/SurfaceControls.Tests/SurfaceControls.Tests.csproj -p:Platform=x64 -p:UseSharedCompilation=false -nr:false -v:minimal
dotnet build PLUMA.UI/PLUMA.UI/PLUMA.UI.csproj --no-restore -p:Platform=x64 -p:SurfaceGalleryPreview=true -p:UseSharedCompilation=false -nr:false -v:minimal
All three builds: zero warnings/errors.

PLUMA.UI/CoreIpc.Tests/bin/Debug/net8.0-windows/CoreIpc.Tests.exe
138 authenticated native IPC checks passed.

PLUMA.UI/SurfaceControls.Tests/bin/x64/Debug/net8.0-windows10.0.19041.0/win-x64/SurfaceControls.Tests.exe
95 actual native UI checks passed; fresh dedicated control-tests.txt copied to ignored output.

dotnet run --project PLUMA.UI/PopupStack.Tests/PopupStack.Tests.csproj --verbosity quiet
64,537 checks passed across 5,000 varied display/queue scenarios.
dotnet run --project PLUMA.UI/SurfaceContracts.Tests/SurfaceContracts.Tests.csproj --verbosity quiet
30 checks passed.
dotnet run --project PLUMA.UI/AudioVisualizer.Tests/AudioVisualizer.Tests.csproj --verbosity quiet
All 15 visualizer checks passed.
PLUMA.UI/check-surface-copy.ps1
33 compiled XAML copy scans passed.

output/ui-gallery-preview/PLUMA.UI.exe --popup-stack-audit <owned-output>/popup
675 native popup checks passed; 15 owned dark renders.
output/ui-gallery-preview/PLUMA.UI.exe --surface-gallery --surface-gallery-export <owned-output>/gallery
195 formatting checks passed; 26 owned dark component renders exported.
```

The native dashboard tests invoke real Run/Stop controls through production
orchestration, policy, registry, verifier and SQLite WAL. Success, denial,
failure, execution/planning STOP, residuals, lost acknowledgement, readback
disconnect/reconnect and real window close agree with ledger readback. Teardown
asserts no duplicate executor entry, terminal rows, drained workers and owned
resources. Console fixtures separately cover double submission, unverified or
unpersisted terminal results, legacy capability refusal and STOP during blocked
presentation. Fixture routing/planner waits and lost replies are explicitly
injected; no native model, microphone or power action was exercised here.

The PS7-only combined verification wrapper could not launch because `pwsh` is
absent. Its constituent gates above ran individually on normal Windows without
changing security policy. A first preview harness used the conventional bin
path, but this project writes preview output to `output/ui-gallery-preview`;
the corrected ignored harness passed. Neither launch error is a passing check.
Native preview processes were individually owned, bounded, recorded and exited.
The dashboard fixture render was inspected: existing dark layout is retained,
Run/Stop fit, and preview copy explicitly says commands are not executed.

## Evidence, recovery and remaining work

SHA-256 identities for the tested native binaries:

```text
SurfaceControls.Tests.dll 81bf054353db836f22d8f47fba6d847fd531842f2be296f577312fcbde773724
PLUMA.UI.dll 74597905d09245e46b1d0c72d355de7539be63b35d44660e349347ccd78532db
```

Ignored full logs: `output/p17-authorized-20261027-191615/` (prerequisites,
reproductions, regressions, source-hash comparison, safety/undo, native renders
and preview process provenance); `output/p17-authorized-*.log` for builds,
console/native UI, layout/surface/audio and previews. A source/build hash manifest
is retained with these logs. The tested source commit above covers all runtime
and test changes; subsequent checkpoint edits are documentation only.

No P17 gate packet remains. Later P18 factual event consumption, P19 voice UI,
P20 history/undo surfaces, P21 settings, P22 health/recovery, P23 perception UI
and broader P24–P33 scenario/physical/performance/security/release gates remain
open. P25 owner appearance, actual monitor/taskbar/DPI and accessibility review
are not inferred from fixtures. Existing owner-approved P00–P14 limitations
remain recorded; no requirement was waived here.

Recovery: preserve `af855cb` and the earlier P17 recovery branch
`recovery/p17-before-rollback-20261027-862b3fd`. Use a reviewed revert of the new
implementation/checkpoint commits or a separate checkout; never reset/clean or
replace unrelated runtime data. Source recovery cannot undo external actions.
Ready for independent Sol review. Do not start P18 or merge automatically.
