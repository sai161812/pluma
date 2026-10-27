# E81 — P15 versioned request/acknowledgement/readback slice

## Scope and result

This bounded P15 packet adds version 1 typed envelopes for text submission,
independent STOP and terminal readback. Python resident dispatch now accepts a
text request into a resident-owned task thread and returns a correlation/task
acknowledgement without waiting for completion. Exact duplicate request IDs
return the same acceptance while the bounded resident record is present;
changed payloads are refused. A request ID already in the durable task ledger
after restart is refused rather than replayed. Terminal readback reports the
supervisor capsule's state, verification, persistence, residual status and
factual summary, or returns a deliberately limited durable-ledger projection
after the resident restarts. The durable projection does not claim completion
verification because detailed execution evidence is unavailable in that
session. Versioned STOP uses a separate IPC request and returns the existing
evidence-bearing `pluma.stop.v1` receipt; STOP cleanup is not serialized behind
text execution within the resident handler.

The C# side now has typed request, acknowledgement, STOP and readback wire
models with the same snake-case JSON names, strict fields, UUID checks, bounds,
duplicate-property refusal and consistency checks. It does not yet send
versioned requests from the production UI. No confirmation, settings/history
query, event stream, buffering/reconnect contract or UI action control was
implemented in this packet.

## Changed files

- `pluma/core/ipc_contracts.py`
- `pluma/core/resident.py`
- `pluma/memory/activity.py`
- `tests/unit/test_ipc_request_contract.py`
- `tests/unit/test_resident.py`
- `PLUMA.UI/PLUMA.UI/CoreRequestProtocol.cs`
- `PLUMA.UI/CoreIpc.Tests/CoreIpc.Tests.csproj`
- `PLUMA.UI/CoreIpc.Tests/Program.cs`
- `PROJECT_HANDOFF.md`
- `docs/completion/requirements_matrix.md`
- `PLUMA.UI/PLUMA.UI/docs/wiring_handoff.md`
- `PLUMA.UI/PLUMA.UI/docs/phase14_ui_surfaces.md`

## Verification

Source identity before this packet: `fcd22c3513a68762b56f6d8b0852178c2b073c70`
on `p12-preparation`. The focused Python fixtures use an in-memory SQLite
ledger and deterministic fake orchestrators; they do not invoke a real tool or
model. The C# IPC runner uses owned test pipes and test credentials.

Commands and results:

```text
pytest -q tests/unit/test_ipc_request_contract.py
3 passed

pytest -q tests/unit/test_ipc_request_contract.py tests/unit/test_ipc.py tests/unit/test_stop_protocol.py tests/unit/test_runtime_shutdown.py tests/unit/test_resident.py
104 passed

dotnet run --project PLUMA.UI/CoreIpc.Tests/CoreIpc.Tests.csproj
49 IPC checks passed; no production core, microphone or tool execution started.
```

The first resident regression run exposed a stale assertion that expected the
word `stopped` in the STOP reply. It was corrected to assert the existing
evidence-bearing `pluma.stop.v1` receipt fields. The final affected suite passes.

The C# protocol models and Python resident handler were tested separately; the
existing C# suite still proves authenticated Python status IPC, but this packet
does not prove a C# v1 submit call over the authenticated pipe. STOP was tested
through the resident handler alongside a blocked executor, not under native
pipe saturation. The legacy IPC server's shared client bound is unchanged;
reserved STOP transport capacity remains an explicit gap for the next packet.
Production UI integration and cross-language request transport remain open.

`python -m ruff check ...` was attempted for changed Python sources, but Ruff
is not installed in this environment (`No module named ruff`).

## Remaining P15 work and next safe packet

P15 remains incomplete. Next connect the typed C# protocol to an authenticated
versioned request transport and prove actual Python/C# request and response
compatibility over the existing native message-mode pipe. Add reserved STOP
capacity and test it under client saturation. Then implement the
remaining bounded contracts for confirmation, settings/history queries,
factual events, ordering/buffering, duplicate handling, disconnect/reconnect,
malformed/oversized messages and disposal. Keep the production UI action entry
disabled until its safety and confirmation gates pass.

No independent Sol review or P15 completion is claimed.
