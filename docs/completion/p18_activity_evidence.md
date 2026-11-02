# E88 - P18 packet 2: typed activity evidence and projections

Date: 2026-10-27 (Asia/Calcutta). Branch: `p12-preparation`.
Tested source: `65d458b8152c068e93d6419210dc7ae3bf8cfba1`.
Recovery: `337a09f15818098113a5a077984da5a74d8ef47b` (E87).

## Scope

This packet implements the read-only `activity_query` / `activity_page` contract,
its strict C# parser/client, deterministic action/rollback/cleanup projections,
and production task-feed correlation through the new bounded query. **P18
overall remains incomplete.** Remaining popup bindings are not claimed complete.
This bounded packet passes its exact-source native regression gate below.

Changed runtime files: `ipc_contracts.py`, `resident.py`, `activity.py`,
`CoreActivityProtocol.cs`, `CoreIpcClient.cs`, `EventFeedController.cs`.
Tests: `test_p18_activity_query.py`, `ActivityChecks.cs`, EventFeedChecks,
console runner and console/native project links. No tool adapter, policy,
rollback algorithm, master, visual resources, XAML or popup layout changed.

## Contract and resolved gap

The task feed previously fetched a whole task's history only to establish
request identity. The legacy history API deliberately refuses more than 100
actions. This packet preserves that refusal and uses a one-action activity
page for feed correlation, so larger histories no longer stall that path.
The owned 105-action regression proves the old refusal and enumerates every
action through the new bounded pages, with no duplicates or cross-task rows.

The query validates canonical request/task IDs, an Int64 nonnegative action
cursor and a 1-100 page bound before dispatch. One SQLite SELECT reads task,
action and cleanup evidence in a page snapshot, fetching one extra action to
determine continuation. Actions are ordered by stable action ID, not step index.
The cursor enumerates rows; it is not a change cursor. On action/rollback events,
consumers must re-read affected evidence rather than treating earlier pages as
immutable or a collection of pages as one atomic snapshot.

The response contains task/request identity, nullable saved state/route, bounded
action IDs/step indices/tool names/risk, explicit verification/issue/denial flags,
undo/rollback flags, and an optional cleanup summary. Commands, transcripts,
arguments, result/error bodies, inverse recipes, resource IDs and process
identities are omitted. A recorded issue is not automatically execution failure:
it can represent pending mutation evidence. A verified action is not aggregate
task success. Saved task state is not an invented live step/execution signal.

Cleanup summaries require valid version-1 evidence, strict booleans and agreement
between the stored complete flag and recomputed latest unresolved checks. Latest
evidence wins per kind/resource. Missing reports remain null; malformed,
contradictory or oversized reports fail closed. Bounds are 65,536 characters and
512 entries. No field or template claims a worker was terminated: a complete
cleanup report or a released resource cannot establish that operation.

The C# projection templates provide stable task/action keys and factual issue,
postcondition, rollback and cleanup messages. They are ready for the next popup
binding packet; they are not yet presented as tool/rollback popups in production.

## Prerequisites and verification

Reused unchanged master/AGENTS/build/acceptance/owner decisions and E87/E80-E86
material already read in this conversation; refreshed Git, handoff, selected
P18 contract, matrix, query/cleanup/policy/registry and existing tests. The
checkout was clean. No completed milestone was restarted or branch switched.

Fresh pre-edit prerequisites: **112 Python tests in 15.07s** and **154 native
authenticated IPC checks**. No skips/xfails were counted. Python storage was
isolated beneath ignored `output/p18-details-20261027-202451/`.

```text
output/p16-windows-env/Scripts/python.exe -m pytest -q tests/unit/test_p18_activity_query.py
15 passed in 0.54s (final source and final regression assertions).

output/p16-windows-env/Scripts/python.exe -m pytest --runxfail -q tests/unit/test_p18_activity_query.py tests/unit/test_p15_remaining_contracts.py tests/unit/test_ipc_request_contract.py tests/unit/test_p17_submission_stop.py tests/unit/test_stop_protocol.py tests/unit/test_policy_boundary.py tests/unit/test_app_lifecycle.py tests/unit/test_runtime_shutdown.py tests/unit/test_cleanup_evidence.py tests/unit/test_rollback_engine.py tests/unit/test_backend_wiring_audit.py
239 passed in 24.58s; zero skips/xfails.

dotnet build PLUMA.UI/CoreIpc.Tests/CoreIpc.Tests.csproj --no-restore -p:UseSharedCompilation=false -nr:false -v:quiet
PLUMA.UI/CoreIpc.Tests/bin/Debug/net8.0-windows/CoreIpc.Tests.exe
171 checks passed: 13 new schema/projection checks and four real activity IPC checks join the prior 154.

dotnet build PLUMA.UI/SurfaceControls.Tests/SurfaceControls.Tests.csproj -p:Platform=x64 -p:UseSharedCompilation=false -nr:false -v:minimal
dotnet build PLUMA.UI/PLUMA.UI/PLUMA.UI.csproj --no-restore -p:Platform=x64 -p:SurfaceGalleryPreview=true -p:UseSharedCompilation=false -nr:false -v:minimal
All three final builds: zero warnings/errors.
```

Python covers strict request bounds, empty/unknown tasks, pagination beyond 100
rows, read-only event-count stability, privacy, rollback flags, latest cleanup
evidence, corrupt/contradictory/oversized reports and STOP while a read is blocked.
The C# parser rejects missing or wrongly typed flags, duplicate/unordered IDs,
wrong tails, unknown states and contradictory cleanup/rollback. Projection
checks prohibit fabricated aggregate completion or worker termination. Existing
feed tests now reject any attempt to use scoped legacy history for correlation.

Native authenticated activity tests compare task/request/action identity and
verification/undo flags with independent WAL history; payload fields remain
absent and continuation advances. Existing IPC suites retain policy, STOP,
owned-file verification, residual and ledger readback checks. These use only
owned fixtures and private temporary storage, with no personal desktop/device,
clipboard, power or UAC operation. Mock/fixture checks are not native model or
physical UI evidence. An initial test-harness failure used the wrong cleanup
helper and an oversized automatic pytest parameter ID; the fixture helper and
short parameter IDs were corrected, not production assertions weakened.

## Hosted regression gate

[Windows workflow 40527808375](https://github.com/sai161812/pluma/actions/runs/40527808375)
passes on the exact source above: **171 IPC/protocol checks**, **105 actual
native UI checks**, **663 native popup checks**, **195 formatting checks**,
**64,537 layout checks / 5,000 scenarios**, **30 surface contracts**, **15
visualizer checks**, 33 compiled-XAML copy scans and zero-warning native builds.
The UI fixture now exercises the new activity endpoint through production feed
correlation. Native control/desktop placement fixtures remain separate from
full multi-surface application acceptance and P25 physical checks.

Host: normal execution-authorized Windows Server 2025, interactive fixture run.
The apphost is unsigned; no signed-release or installed-product claim is made.
Apphost SHA-256: `E267C92D298DAB608B4B05E806CAC10B83B35169C21616717C9689B93DBD9EAB`.
[Artifact 12744668979](https://github.com/sai161812/pluma/actions/runs/40527808375/artifacts/12744668979)
ZIP SHA-256: `5927767e7613a80cd655cd3400e2e05f7d9d09336fe53ddcc12fe208f65effca`.
The downloaded digest matches GitHub metadata; full native reports/renders are
under ignored `output/p18-details-ci/20261027-150842-306d6280/`. The known local native Application Control
restriction is respected; no alternate launch or policy bypass was attempted.

## Remaining P18 and recovery

Next safe packet: bind the validated activity projections to the existing
task/route/tool/result/rollback/policy surfaces, removing their preview samples
from production paths. Establish any missing live-step/start/argument contracts
before showing those facts. Add verified owned termination proof before surface
21; this packet deliberately does not expose such a claim.

Perception surfaces, broader notices/current/recent panels, host-capacity burst
arbitration and complete event-driven desktop-host/backend acceptance across
all P18 surfaces remain open. Cleanup reports beyond this packet's explicit
bounds fail closed and need bounded detail/paging before broader acceptance.
P19 has not started; P25 physical/owner and later release gates stay separate.

Full logs stay ignored under `output/p18-details-20261027-202451/` and
`output/p18-details-*.log`. Source/build hash manifests stay with the reports.
Preserve recovery commit `337a09f` and existing recovery branches. Recover by
reviewed revert or a separate checkout, preserving unrelated/runtime data; source
rollback cannot undo external effects. No merge/reset/clean/force-push occurred.
This bounded packet is ready for independent Sol review; approval is not assumed.
P18 overall is not ready to advance.
