# E87 — P18 packet 1: factual event feed and terminal notices

Follow-up: [E88](p18_activity_evidence.md) adds typed paginated activity evidence
and removes the feed's 100-action correlation dependency. Its remaining popup
bindings and full P18 gate remain open. Historical next-step statements below
describe this earlier packet.

Date: 2026-10-27 (Asia/Calcutta). Branch: `p12-preparation`.
Source: `83417432f150f26b6e1189d8ed0cfa7e768d02c6`.
Recovery: `48b959b1ca35ba5f37d961d634cd67f6a29d353f` (completed P17).

## Scope and status

This bounded packet implements the committed event consumer, dashboard live
feed and task-terminal notices through surface 24. **P18 overall is incomplete.**
This packet passes its exact-source hosted native gate; the remaining P18 work is listed below.
P19 has not started; no merge, branch switch, reset or force-push occurred.

[The wiring contract](../../PLUMA.UI/PLUMA.UI/docs/wiring_event_feed.md) describes
ownership, data bounds, cursor/readback ordering, reconnect and privacy. Runtime
changes are EventFeedController, its notice factory, CoreEventCursor.Fork,
Dashboard XAML/code and MainWindow. Tests add EventFeedChecks and native feed
checks plus console/native runner/project links. No backend adapter, policy,
undo, model, capture, Python source or theme resource changed.

## Prerequisites and findings

Inspected AGENTS, unchanged complete master (blob
`01b693dbf898b662aa4cd67736c1a0e8a21cf3e3`), P18/shared execution contract,
current handoff/matrix, build Phase 14, acceptance G/H/J, P15 event contracts,
P17 implementation, popup placement and surface references. Reused unchanged
P00–P15 evidence within its recorded scope: all 23 E80 source/test identities
still match raw/LF-normalized SHA-256 values. E81–E84 protocol, policy/STOP and
ledger source were inspected. Earlier owner-approved physical deferrals remain
limitations, not fresh passes. The checkout was clean before edits.

Fresh pre-edit affected prerequisites:

```text
output/p16-windows-env/Scripts/python.exe -m pytest -q tests/unit/test_p17_submission_stop.py tests/unit/test_p15_remaining_contracts.py tests/unit/test_ipc_request_contract.py tests/unit/test_policy_boundary.py tests/unit/test_policy_engine.py tests/unit/test_stop_protocol.py tests/unit/test_app_lifecycle.py tests/unit/test_runtime_shutdown.py
175 passed in 21.59s; no skips/xfails. Isolated LOCALAPPDATA/APPDATA/PLUMA_CONFIG.

PLUMA.UI/CoreIpc.Tests/bin/Debug/net8.0-windows/CoreIpc.Tests.exe
138 authenticated IPC checks passed.
```

Source inspection established the missing production event consumer; no earlier
milestone was reopened. During packet verification, reproduced one new timing
failure: terminal ledger commit can precede the resident's cached detailed
verification, without another ledger event afterward. The new settling test
failed before repair, and passes after active-state/fair bounded readback and
three extra reads for completed-but-unverified success. No success fallback or
assertion relaxation was used. Missing proof remains explicitly unverified.

## Local checks and safety

```text
dotnet build PLUMA.UI/CoreIpc.Tests/CoreIpc.Tests.csproj --no-restore -p:UseSharedCompilation=false -nr:false -v:quiet
PLUMA.UI/CoreIpc.Tests/bin/Debug/net8.0-windows/CoreIpc.Tests.exe
154 checks passed, including 16 new consumer assertions and the existing real IPC suites.

dotnet build PLUMA.UI/SurfaceControls.Tests/SurfaceControls.Tests.csproj -p:Platform=x64 -p:UseSharedCompilation=false -nr:false -v:minimal
dotnet build PLUMA.UI/PLUMA.UI/PLUMA.UI.csproj --no-restore -p:Platform=x64 -p:SurfaceGalleryPreview=true -p:UseSharedCompilation=false -nr:false -v:minimal
Final builds: zero warnings/errors.
PLUMA.UI/check-surface-copy.ps1
33 compiled XAML copy scans passed.
```

Consumer fixtures cover silent historical snapshots, coalescing/order, replay,
private-text exclusion, failed-batch atomicity/retry, terminal persistence and
verification, residual/failure messages, stream replacement, gaps, a 200-entry
buffer, fair refresh of more than 25 pending identities and cancellation of an
outstanding read-only poll. These deterministic fixtures are not native UI proof.
Existing authenticated IPC checks retain STOP saturation, exact policy approval,
registered owned-file verification, WAL readback and no duplicate execution.

The final native control executable was blocked before Main by Windows
Application Control. Its old report was positively rejected as stale; the
blocked invocation is not a pass. No alternate local launch, security-policy
change or bypass was attempted. Earlier native build warnings were fixed with
explicit non-null observation checks; final builds have zero warnings.

## Exact-source native acceptance

The normal existing [Windows workflow 40518641201](https://github.com/sai161812/pluma/actions/runs/40518641201)
**passes** on `8341743`: **154 IPC checks**, **105 actual native UI checks**
(including ten new feed/notice/navigation cases), **663 native popup checks**,
**195 formatting checks**, **64,537 layout checks / 5,000 scenarios**, **30
surface checks**, **15 visualizer checks**, all 33 XAML copy scans and zero-warning
native builds. No skips/xfails are counted. Windows Server 2025 ran the existing
workflow normally; its own native fixture reports and renders were retained.

Hosted apphost SHA-256:
`FAEE4EC9CAA742CD7F4905F3A5C014AD7ED64904D06C01C6EDE03489B5455B37`.
It is unsigned on this execution-authorized host; no signed release is claimed.
[Artifact 12740139509](https://github.com/sai161812/pluma/actions/runs/40518641201/artifacts/12740139509)
ZIP SHA-256: `6250510fd00d553d0aca3bdfdf489cadaf93b4d37e5641ae01d6c9235412dff7`.
The downloaded ZIP hash matches GitHub's artifact digest. Full reports are under
ignored `output/p18-ci/20261027-141221-f923a3db/`; the summary identifies the exact
source, interactive test host and completed stage. The owned dashboard gallery
render was inspected; native dark styling and command layout remain intact.

Native checks use only owned windows/dialogs, private credentials,
temporary files, a real authenticated Python resident fixture and SQLite WAL.
The fixture has production orchestration/policy/registry/verification; route and
planner waits are explicitly injected. No personal files, clipboard, browser
profile, microphone, model or power/UAC operation is exercised.

The new native checks compare dashboard entries and actual task IDs with saved
action/terminal history, construct the production notice control, verify that
dismissal changes no task outcome, and restore the shared feed after navigation.
The production MainWindow-to-desktop-host call is inspected; native desktop
host placement/motion and native backend/feed/notice control checks are separate
fixtures. This is not a single whole-shell/backend acceptance run or P25 physical
monitor/taskbar/owner appearance approval.

## Remaining P18 work and recovery

- Detailed task/step/route/tool/result/rollback projections and surfaces 4–9.
- Policy, perception/postcondition indicators and remaining surfaces 17, 19–23.
- Typed cleanup/resource evidence sufficient for verified owned-worker
  termination; an event name or released resource alone is not termination proof.
- Broader notice types, current/recent activity panels and complete production
  sample-path review across all remaining wired surfaces.
- Full multi-surface event-driven desktop-host/backend acceptance for bursts,
  replacement, navigation, reconnect, STOP and shutdown. P25 physical checks
  retain their owner; no later milestone is automatically started.
- Resolve/verify multi-surface burst arbitration at host capacity (a card may
  be refused while its factual feed entry remains). The existing 100-action
  task-history cap fails closed on oversized readback; detailed projection
  contracts must cover larger supported task histories before broad acceptance.

Next safe packet: typed action/state/cleanup evidence and deterministic
projections, followed by its affected existing surfaces. Do not start P19.

Full logs are ignored under `output/p18-events-20261027-192645/` (use
`output/p18-events-current.txt` for the actual run directory) and
`output/p18-*.log`; the source/build hash manifest stays with those logs.
Preserve `48b959b` and existing recovery branches. Use reviewed reverts or a
separate checkout to recover source, preserving unrelated files/runtime data;
source rollback cannot undo external actions. This bounded packet is ready for independent Sol review; approval is not
assumed. Overall P18 readiness requires the remaining work above.
