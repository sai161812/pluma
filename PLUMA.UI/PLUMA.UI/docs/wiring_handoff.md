# UI wiring handoff

Workspace update after the requested cleanup: active `ui-wiring` development is
now in `D:\Workspace\DEVEL\PLUMA`. The former `PLUMA-ui-wiring` worktree is
detached at `55b625c`, preserving its existing evidence. The original generated
`ui-polish` edits are preserved in a local stash; all branch histories remain.
See [cleanup/recovery](../../../docs/workspace_cleanup.md) and the
[completion prompts](../../../PLUMA_COMPLETION_PROMPTS.md). Earlier workspace
paths and branch-state descriptions below are historical preparation records.

**Current progress (2026-10-27):** dashboard status remains read-only and is
refreshed on load or explicit user action. P15 E81/E82 add Python versioned
submit/STOP/readback contracts and authenticated C# transport methods; the
dashboard does not invoke them. See [E81](../../../docs/completion/p15_e81_versioned_requests.md)
and [E82](../../../docs/completion/p15_e82_authenticated_transport.md).
The historic backend audit and branch/worktree descriptions below are retained
as preparation records; their failure counts are superseded by the later P00-P14
audit closures. Action entry remains disabled. No JSON-RPC dispatcher, heartbeat
or live push event stream is implemented. Confirmation, settings/history,
cross-language request transport, UI action wiring and P15/P16+ acceptance
remain open.

Prepared 2026-10-19 before wiring. This is repository preparation and a source
inventory, not an implementation of the IPC adapter or a release-completion claim.

## Branch and workspace state

| Branch | State |
|---|---|
| `main` | Local branch now matches `origin/main`, `6dbf58925352d41a0196dda33044b18282cc6ddf`. |
| `archive/main-before-ui-sync-20261019-90aa05e` | Preserves the former local `main` at `90aa05e`, including its 49 local-only commits. Local archive; no force push or history deletion. |
| `ui-polish` | Original source/history retained at `9150e81`, matching GitHub. Existing generated/IDE changes and unrelated untracked files remain in the original workspace. |
| `ui-polish-integration` | Verified UI at `9544752d1af4d675b50ff7aa8e99fb27da9c722f`, matching GitHub. [PR 1](https://github.com/sai161812/pluma/pull/1) remains draft. |
| `ui-wiring` | Based on verified UI commit `9544752`; initially documentation-only, now contains step 1 described above. |
| `sai` | Pre-existing branch left unchanged. |

Use `D:\Workspace\DEVEL\PLUMA-ui-wiring` for subsequent wiring work.
The original workspace remains on `ui-polish`; the integration worktree remains
on `ui-polish-integration`. Do not switch or clean the original dirty worktree
to prepare wiring. Do not push the archived local history into `main` or replace
the original `ui-polish` history.

The wiring branch depends on the unmerged UI integration. The owner subsequently
authorized starting wiring against that branch; its draft PR is stacked on
`ui-polish-integration`, without merging either PR. Finish the
recorded UI acceptance gate before merging PR 1. After that merge, reconcile the
wiring branch with the actual resulting `main` commit before retargeting its
existing implementation PR; do not assume a particular merge strategy or commit SHA.

## Executed baseline

The UI code passed two complete hosted Windows verification runs:
[run 8](https://github.com/sai161812/pluma/actions/runs/39159608742) and
[run 9](https://github.com/sai161812/pluma/actions/runs/39160052427).
Run 9 tests the final UI integration head `9544752` as PR merge `812ddb7`.

- 661 native popup checks, including actual intermediate fade/reflow/glide
  readback, class dimensions, layout readiness, non-overlap and 50 lifecycles
  with animations disabled.
- 195 native formatting checks and 35 native control checks.
- 64,537 pure layout checks across 5,000 scenarios, 30 surface contracts and
  15 audio-visualizer checks.
- Visible-copy scan passes for all 33 compiled XAML files.
- Both native projects build with zero warnings/errors; 26 Dark gallery
  surfaces and all 15 floating classes export successfully.

The additional pre-wiring backend baseline uses Python 3.12.10 / pytest 8.3.3:

```powershell
python -m pytest tests/unit/test_ipc.py tests/unit/test_phase13_5_stage_h_model_ipc.py::test_stage_h_ipc_server_client_roundtrip_and_timeout tests/unit/test_policy_engine.py tests/unit/test_phase13_7_ui_verification.py -k "not test_elevation_broker_execution" -q -o addopts= --timeout=20 --timeout-method=thread
# 12 passed, 1 deselected in 6.05s. Process exit code 0.
```

The child test process received unique LOCALAPPDATA, APPDATA, TEMP and TMP
directories under the user's local Temp directory. The normal user profile,
resident process, hotkeys, microphone and authentication key were not used.
Only test-owned named pipes were started. The elevation-operation test was
deselected because this preflight does not execute system-changing operations.
The existing test fixtures enable audio emulation; this is not physical voice
or release acceptance. The child process had a 120-second outer bound.

An earlier attempt used storage under the workspace, where inherited Users
permissions caused two authenticated IPC failures (10 pass, 2 fail). Retesting
with isolated user-local storage, matching normal application placement, passes
all selected checks. Authentication was not disabled, backend code was not
modified, and no Windows security policy or existing file ACL was changed.
Throwaway authentication keys created by these owned fixtures were removed.
Logs, summaries and JUnit reports are ignored local artifacts under
`output/wiring-preflight/`; the passing run is `20261018-195329-0acf39d5`.

## Existing source contracts

Read these implementations before defining any client messages:

- `pluma/core/ipc.py`: per-user local named pipe, Python
  `multiprocessing.connection` message framing, bounded JSON messages and
  HMAC-SHA256 challenge/response authentication. This is not a plain newline-JSON
  stream or an implemented JSON-RPC 2.0 interface. C# wire compatibility needs
  explicit round-trip tests.
- `pluma/core/resident.py::ResidentCore.handle_ipc_command`: current command
  families are `execute`/`request`/`submit`, `stop`/`STOP`/`stop_all`,
  `stop_task`, `status`, and `recent_tasks`/`get_recent_tasks`.
- `pluma/ui/shell_contract.py`, `activity_contract.py`, `settings_contract.py`
  and `confirmations.py`: functional interfaces, not a completed C# bridge or
  settings/event IPC API. `SettingsContract` is still abstract.
- `MainWindow.Popups`: lazy shared popup host. It does not connect to the core.
- [Surface reference](phase14_ui_surfaces.md): intended surface purposes and
  future wiring references. Its generic named-pipe/JSON-RPC wording does not
  establish an implemented transport or event subscription.

The current IPC request handler returns one response per connection and has no
UI push subscription. Live task steps, partial/final transcription, policy
confirmations, settings updates and richer activity details therefore need
explicit typed contracts before their surfaces can be connected. Inventory
existing executor events first; do not invent event names as though implemented.

An `execute` response can have `status: ok` with `success: false`: transport
success is not verified action success. Preserve final task state, verification,
factual executor messages, rollback/residual results and redaction. A STOP
acknowledgement does not replace verified terminal state and cleanup evidence.

## Bounded implementation order

1. Add an authenticated C# local IPC adapter and typed request/response models.
   Start with read-only status and disconnect/reconnect handling. Prove Python/C#
   framing and authentication, payload bounds, cancellation, timeouts and owned
   disposal against an isolated test server. No network service or security
   bypass, and no model/microphone startup merely from opening the shell.
2. Connect text submission and global STOP through the resident request and
   TaskSupervisor pipeline. STOP must remain responsive while execute is in
   flight; do not serialize cancellation behind the outstanding execute request
   or block the WinUI dispatcher. Verify cleanup and factual failure/results.
3. Define and test the missing typed event/push contract, then connect live task,
   tool, route, rollback, policy and verification state to stable popup identities.
   Retain the approved dark appearance, class sizes, bottom-right ordering and
   taskbar behavior in [the placement contract](popup_placement_contract.md).
4. Connect voice activation and partial/final transcript/state through the same
   core pipeline as text. Keep one voice overlay and on-demand workers; the
   legacy microphone preview is not production wiring or acceptance evidence.
5. Connect history/details, settings persistence, material confirmations, health,
   setup checks and recovery through verified core contracts. Keep default
   states disconnected/unverified until actual evidence arrives; production
   surfaces must not retain preview task/results or fabricated capability data.
6. Run focused adapter/projection tests, the relevant core/UI regressions and
   full end-to-end acceptance, including STOP under load, voice/text equivalence,
   verification, undo/residuals, crash/reconnect, idle resource behavior and
   packaging on the permitted Windows environment.

Each meaningful change receives a commit. Define exact files and acceptance
tests for each bounded step; do not implement all steps in one unreviewable
change or automatically advance into another phase.

## Remaining completion gates

Physical Windows 11 auto-hide taskbar reveal/hide, real monitor/DPI,
reading/accessibility and owner appearance/motion review remain open. Local
Application Control still rejects the unsigned rebuilt preview; no security
configuration has been changed and no limitation approval is assumed.
See [the integration evidence](ui_integration_review.md).

Wiring is the next implementation work, followed by these physical checks and
end-to-end/regression/release acceptance in `PLUMA_ACCEPTANCE_TESTS.md` and
`PLUMA_MASTER_SPEC.md` section 28. Neither a rendered surface nor a passing
transport response makes the whole product done. This preparation does not
merge PR 1 or mark Phase 14 complete. Original preparation did not start wiring
code; subsequent authorized step 1 is recorded in the progress link above.
