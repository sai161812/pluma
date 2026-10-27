# E84 — P15 contract completion

## Result and scope

P15's required UI/core contract gate is complete. E81–E83 established
versioned submission/acknowledgement/readback, authenticated C# transport,
priority STOP and settings/history queries. E84 closes material confirmation
messages and factual event ordering, bounded retention, replay and reconnect.
The implemented [v1 protocol](p15_protocol_v1.md) records the exact semantics.

Confirmation calls originate from validated policy arguments and belong to the
existing registry-owned policy worker/capsule. A logical client lease enables
pending delivery; without one, policy retains REQUIRE_CONFIRMATION. Each call
has a fresh ID and salted exact-material binding. Wrong client/task/binding,
expired/lost/stopped calls and duplicates refuse. Decisions are consumed once;
there is no blanket/session approval. STOP and the registry deadline still
control executor admission. The broker creates no thread, timer or device.
Runtime shutdown denies outstanding calls and clears clients.

The SQLite migration projects actual committed task/action/undo/resource/
cleanup/screen record changes into an identity-only journal. One durable stream
UUID and global sequence provide ordering; the last 512 facts are retained and
responses contain at most 100. Transaction rollback leaves no event. Cursors
survive normal reopen/reconnect; overflow, replacement and impossible future
cursors require snapshot resynchronization. The C# cursor rejects gaps and
ignores duplicate facts. Consumers must read history/terminal snapshots before
claiming an operation completed. No raw command, argument, undo recipe,
clipboard, transcript, screenshot or model narrative enters this buffer.

Native UI interaction is intentionally owned by P16–P23. The production
dashboard remains action-disabled and calls only status. P15 uses explicit
bounded event queries; no push subscription, heartbeat or hidden polling loop
is claimed. P16 has not started. Independent Sol review is ready, not assumed.

## Source and build identity

- Tested implementation/protocol commit: `b0f80d5ea6cfb67ab4f005e6c83510e5848704cc`.
- Recovery point before E84: `a36e9596ca671c843ac4e553705ba47aeea26d16`.
- Branch: `p12-preparation`; no switch, merge, reset, clean or force-push.
- C# IPC test DLL SHA-256:
  `1B26FC19FE3BE30AAD260686CBB9C152C356BE63DF77B71D9EA45E97D1F8E11A`.
- Compiled WinUI DLL SHA-256:
  `C216A7416D44D26D2437EDEE5A0A4889544CCE3068ADAE3667A9B862793A0418`.

## Verification

The final Python child ran with unique LOCALAPPDATA, APPDATA, TEMP and TMP
folders under ignored output, plus a nonexistent isolated PLUMA_CONFIG path.
The 24 new focused cases cover exact decisions, privacy, malformed messages,
expiry, STOP, disconnect, changed arguments, client/call bounds, disposal,
every journal source, transaction rollback, concurrent writes, retention,
paging, replay and file-backed reopen. Existing policy assertions were kept.

```text
pytest -q tests/unit/test_p15_remaining_contracts.py tests/unit/test_ipc_priority_capacity.py tests/unit/test_ipc_versioned_pipe.py tests/unit/test_ipc_request_contract.py tests/unit/test_ipc.py tests/unit/test_stop_protocol.py tests/unit/test_runtime_shutdown.py tests/unit/test_resident.py tests/unit/test_app_lifecycle.py tests/unit/test_policy_boundary.py tests/unit/test_policy_engine.py tests/unit/test_db.py tests/unit/test_activity_ledger_lifecycle.py tests/unit/test_memory_stores.py tests/unit/test_tool_runner_ledger.py tests/unit/test_rollback_engine.py tests/unit/test_cleanup_evidence.py tests/unit/test_terminal_outcome.py tests/unit/test_ipc_credentials.py
311 passed in 30.31s; zero failures/errors/skips/xfails.
```

```text
python -m py_compile pluma/ui/ipc_confirmations.py pluma/core/ipc_contracts.py pluma/core/ipc.py pluma/core/resident.py pluma/memory/activity.py PLUMA.UI/CoreIpc.Tests/fixture_server.py
Passed. The final fixture script also executed successfully in the native run.
```

```text
dotnet build PLUMA.UI/CoreIpc.Tests/CoreIpc.Tests.csproj --no-restore
Build succeeded; 0 warnings, 0 errors.

dotnet exec PLUMA.UI/CoreIpc.Tests/bin/Debug/net8.0-windows/CoreIpc.Tests.dll
101 IPC checks passed. No production resident, microphone or personal desktop actions were started.

dotnet build PLUMA.UI/PLUMA.UI/PLUMA.UI.csproj --no-restore -p:Platform=x64 -p:SurfaceGalleryPreview=true -p:UseSharedCompilation=false -nr:false -v:minimal
Build succeeded; 0 warnings, 0 errors (26.81s).
```

The first production build found missing restore assets; restoring the existing
pinned project packages and rebuilding passed. No dependency version changed.
The final native C# run used production authenticated Windows message-mode IPC,
real resident handlers, policy/registry execution, owned temporary file reads
with independent postcondition verification, and an owned file-backed WAL
ledger. Approval, denial, STOP while waiting, late/duplicate/mismatched
approval, disconnect, uncertainty after decision write, history/terminal
readback and event/cursor/reconnect outcomes passed. Fixture teardown checks
that executor entries belong only to accepted approvals, at most once per task,
and drains registry/worker/IPC owners before deleting only its exact temp files.
This read fixture uses the registry's owned thread path; it does not claim new
process-isolation, physical dialog, microphone, OCR or model acceptance.

Intermediate findings were repaired before final results:

- Three native malformed-JSON cases reproduced Python dispatching duplicate
  properties and NaN. Strict decoding now refuses them before dispatch and
  returns fixed error text; all three regressions pass.
- An existing policy regression caught unavailable UI being labelled DENY
  rather than REQUIRE_CONFIRMATION. Availability is now explicit; the original
  policy assertion and remaining regressions pass without weakening it.
- Parent-side native fixture entry counters initially made a named HIGH
  executor picklable, selecting a different worker path. The fixture retains
  its original explicit owned-thread read path, so its counters are factual.

Full final logs are ignored: `output/p15-e84-python.log`,
`output/p15-e84-csharp.log`, and `output/p15-e84-winui-build.log`.
The source diff was checked for scope, privacy, false success and ownership;
no visual design or production dashboard source changed.

## Changed files and next milestone

Implementation and tests: app composition; Python IPC/contracts/resident;
confirmation interface, broker and policy availability; ActivityQuery and
migration 0005; C# protocol/client/cursor; native IPC fixture/runner/project;
application composition and new P15 regression tests. The source commit lists
all 18 exact paths, including the protocol document. The current handoff,
requirements matrix and UI surface/wiring references are updated by this
checkpoint.

There are no remaining P15 contract packets or unexecuted P15 acceptance checks.
The next safe milestone is P16: wire the existing native material approval
surface through these tested messages, including actual dialog lifetime and
one-operation elevation acceptance. Broader installed/physical/security/release
gates keep their existing later owners; this is not full-product readiness.
