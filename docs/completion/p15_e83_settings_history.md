# E83 — P15 settings and history query contracts

Follow-up: [E84](p15_e84_contract_completion.md) completes the remaining P15
confirmation/event contracts. The E83 packet status below is historical.

## Scope

This bounded packet adds read-only version 1 `settings_query` and
`history_query` requests to the authenticated native Windows pipe. The Python
resident and C# protocol use canonical request/task UUIDs and strict, bounded
fields. Settings are an explicit allowlist that includes the effective planner
and STT paths supplied by application composition, three hotkeys, model/runtime
and voice behavior, privacy toggles, and selected policy/runtime values. It
does not return arbitrary configuration or permit edits.

Recent history is newest first and capped at 100 tasks. A task query returns
that task and its step-ordered actions when the action count is within the
requested limit (1–100); larger task histories return an explicit bounded error.
The projection re-redacts command text and JSON records at the IPC boundary,
includes factual verification/rollback status, and never includes saved undo
recipes. Missing tasks, oversized histories, unavailable storage and malformed
queries fail with bounded protocol errors. Responses exceeding the native
message cap are refused. Stable secondary sort keys make equal-time/equal-step
history deterministic.

The C# client uses the existing authenticated, bounded, no-retry transport for
these read-only calls. The production dashboard still calls only status; its
action entry remains disabled. This packet does not implement confirmation
decisions or a factual event feed.

## Changed implementation and tests

- `pluma/core/ipc_contracts.py`
- `pluma/core/resident.py`
- `pluma/memory/activity.py`
- `pluma/app.py`
- `PLUMA.UI/PLUMA.UI/CoreRequestProtocol.cs`
- `PLUMA.UI/PLUMA.UI/CoreIpcClient.cs`
- `PLUMA.UI/CoreIpc.Tests/Program.cs`
- `PLUMA.UI/CoreIpc.Tests/fixture_server.py`
- `tests/unit/test_ipc_request_contract.py`
- `tests/unit/test_app_lifecycle.py`

Checkpoint documentation: `PROJECT_HANDOFF.md`,
`docs/completion/requirements_matrix.md`, this E83 record,
`docs/completion/p15_e82_authenticated_transport.md`,
`PLUMA.UI/PLUMA.UI/docs/wiring_handoff.md`,
`PLUMA.UI/PLUMA.UI/docs/wiring_status_connection.md`, and
`PLUMA.UI/PLUMA.UI/docs/phase14_ui_surfaces.md`.

The C# runner adds actual authenticated Python-server round trips for settings,
recent history and one-task history. Its owned fixture uses a private temporary
credential location, isolated default-only configuration and an in-memory
Activity Ledger. It starts no production resident, tools, models, microphone or
personal desktop state.

## Verification

Tested source commit: `94b19fa9e192142be83ec385cea04bccff0f7a60`
(`Implement P15 settings and history queries`),
based on E82 `4724c5e747ee4001a8aad979ac85b1d476d23ef5` on branch
`p12-preparation`. The exact C# test assembly SHA-256 is
`0E9B5E68DAC43A1FCD29547CABA2207BA5E89BE91B25A41B352224EFCCD0D13C` at
`PLUMA.UI/CoreIpc.Tests/bin/Debug/net8.0-windows/CoreIpc.Tests.dll`.

```text
pytest -q tests/unit/test_ipc_priority_capacity.py tests/unit/test_ipc_versioned_pipe.py tests/unit/test_ipc_request_contract.py tests/unit/test_ipc.py tests/unit/test_stop_protocol.py tests/unit/test_runtime_shutdown.py tests/unit/test_resident.py tests/unit/test_app_lifecycle.py
113 passed in 13.84s; no skips or xfails.

python -m py_compile PLUMA.UI/CoreIpc.Tests/fixture_server.py pluma/core/ipc_contracts.py pluma/core/resident.py pluma/memory/activity.py pluma/app.py
Passed.

dotnet build PLUMA.UI/CoreIpc.Tests/CoreIpc.Tests.csproj --no-restore
Build succeeded; 0 warnings, 0 errors.

dotnet exec PLUMA.UI/CoreIpc.Tests/bin/Debug/net8.0-windows/CoreIpc.Tests.dll
Three consecutive full Windows runs passed: 64 IPC checks each.
```

The C# runner passed on the current execution-authorized Windows host using
actual authenticated Python IPC, including submit/ack/readback, settings and
history queries, independent STOP during blocked execution, and reserved STOP
capacity with four ordinary calls stalled. It also covers malformed/oversized
messages, credential refusal, bounded cancellation/disposal and explicit
reconnect. Full logs are retained under ignored `output/p15-e83-csharp-run-*.log`.

Two intermediate runner defects were fixed before the final three runs: the C#
fixture cleanup grace was shorter than the Python IPC server's shutdown budget,
and concurrent Python fixture events could interleave on stdout. The fixture
now waits beyond the server's cleanup budget, retains its process identity
guard, releases test gates before shutdown, and serializes event writes. No
assertion was removed or weakened.

## Remaining P15 work

- Define and test confirmation request/decision messages with task/call and
  argument correlation, stale/mismatch refusal, duplicate handling and
  disconnect/STOP behavior. Native confirmation UI remains P16 work.
- Define executor-sourced factual event projections and prove sequence/order,
  bounded buffering, duplicate handling, disconnect/reconnect and readback.
- Keep production dashboard submission/STOP wiring for its later milestone;
  the dashboard remains action-disabled.

This packet is ready for independent Sol review. P15 remains incomplete and no
independent approval is assumed.
