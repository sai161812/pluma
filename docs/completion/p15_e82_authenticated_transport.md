# E82 — P15 authenticated request transport and reserved STOP capacity

Current follow-up: the earlier C# runtime limitation recorded below was
resolved in [E83](p15_e83_settings_history.md). The full current runner passes
three consecutive 64-check runs on the execution-authorized Windows host.
E82 retains its original checkpoint results as historical evidence.

## Scope

Continues E81's versioned request contract with authenticated C# submit,
terminal-readback and STOP methods over the existing Python Windows
message-mode named pipe. Calls use one connection per request, preserve HMAC
authentication and native message framing, bound each request/response at 1 MiB,
and never retry a submission or STOP. A timeout after request write returns an
explicit `OutcomeUnknown` result. The C# client has four ordinary in-flight
slots plus one independent STOP slot.

The Python IPC server now allows 32 owned authenticated client handlers while
allowing at most 31 ordinary commands into handlers. The remaining slot serves
STOP, including existing legacy STOP command names. Requests beyond normal
capacity receive a bounded BUSY response and are not dispatched. This was
verified against 31 blocked authenticated ordinary requests and a STOP request.

The C# integration runner now contains tests using the production authenticated
Python IPC server and a deterministic in-memory ResidentCore fixture. It covers
submit acknowledgement, terminal ledger readback, STOP during blocked
execution, and STOP while four ordinary C# calls are stalled. A first runtime
attempt passed authenticated C# submit, readback and STOP during blocked
execution, then failed during saturation-fixture teardown because the fixture
assumed a submission-thread map existed when no task had been submitted. That
cleanup defect was fixed. On the subsequent rebuild, Windows Application
Control blocked the test assembly before Main, so the full runner and repaired
saturation teardown remain unverified. The project compiles, but the C# suite
does not have a green final runtime result.

## Changed files

- `PLUMA.UI/PLUMA.UI/CoreIpcClient.cs`
- `PLUMA.UI/PLUMA.UI/CoreRequestProtocol.cs`
- `PLUMA.UI/PLUMA.UI/CoreStatus.cs`
- `PLUMA.UI/CoreIpc.Tests/Program.cs`
- `PLUMA.UI/CoreIpc.Tests/fixture_server.py`
- `pluma/core/ipc.py`
- `tests/unit/test_ipc_priority_capacity.py`
- `tests/unit/test_ipc_versioned_pipe.py`
- `PLUMA.UI/PLUMA.UI/docs/wiring_status_connection.md`
- `PLUMA.UI/PLUMA.UI/docs/wiring_handoff.md`
- `PLUMA.UI/PLUMA.UI/docs/phase14_ui_surfaces.md`
- `PROJECT_HANDOFF.md`
- `docs/completion/requirements_matrix.md`
- this evidence record

## Verification

Base source: E81 commit `c5a702837c853dfd51f109a0bac2de8067bd39c2` on
`p12-preparation`.

```text
pytest -q tests/unit/test_ipc_priority_capacity.py tests/unit/test_ipc_versioned_pipe.py tests/unit/test_ipc_request_contract.py tests/unit/test_ipc.py tests/unit/test_stop_protocol.py tests/unit/test_runtime_shutdown.py tests/unit/test_resident.py
106 passed in 13.79s; no skips or xfails.

python -m py_compile PLUMA.UI/CoreIpc.Tests/fixture_server.py
passed.

dotnet build PLUMA.UI/CoreIpc.Tests/CoreIpc.Tests.csproj --no-restore
Build succeeded; 0 warnings, 0 errors.

dotnet exec PLUMA.UI/CoreIpc.Tests/bin/Debug/net8.0-windows/CoreIpc.Tests.dll
First run: authenticated C# v1 submit/ack/readback and STOP-during-blocked-task
checks passed; overall runner failed at owned fixture teardown (cleanup bug fixed).
After rebuilding, Application Control blocked before Main: FileLoadException,
0x800711C7. The full runner has no final green runtime result.
```

The partial C# run used owned pipe names, an isolated test credential,
an in-memory ledger and deterministic fixture execution; it never uses the
production resident, personal files, clipboard, windows or models. The Python
native-pipe tests use authenticated `IpcServer`/`IpcClient` with a temporary
`LOCALAPPDATA` and owned SQLite memory storage. Python STOP saturation evidence
is native to the current Windows host; it is not the blocked C# run.

`dotnet run --no-build` was also blocked by Application Control on the generated
apphost. No policy bypass or alternate unsigned execution path was attempted.

## Remaining P15 work

P15 remains incomplete. The full C# suite, including reserved-slot saturation
and repaired fixture teardown, needs a green runtime result on an
execution-authorized Windows test host. Settings/history query contracts,
confirmation-decision message contracts, factual event projections and their
ordering/cursor/buffer/reconnect behavior remain unimplemented. The C# dashboard
does not call the new submit/STOP methods, and no live event feed is wired. The
existing 1 MiB message cap, malformed-message rejection, authentication/ACLs,
client disposal and explicit no-retry behavior remain in the shared transport;
the new v1 request methods still need runtime interoperability evidence.

Next safe packet: run the current C# integration suite in an authorized Windows
test environment and repair any failures; then add bounded settings/history
query contracts using the existing `PreferencesStore` and `ActivityQuery` data.
Do not advance to P16; confirmation UI wiring belongs to P16.

No P15 completion or independent Sol approval is claimed.
