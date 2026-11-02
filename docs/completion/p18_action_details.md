# E90 - P18 packet 4: factual results and policy reasons

Date: 2026-10-30 (Asia/Calcutta). Branch: `p12-preparation`.
Source: `06db4c78e07ce29f50c35f960188500310c8b899`, following implementation
`c9dbf58` and strict wire/view separation `650805d`.
Recovery: `3aa79ba4b6399e74fcddbdc2bc95956f57c68b4e` (E89).

## Bounded scope

This packet addresses the first remaining group: detailed recorded result/error
and matched-policy reason readback for surfaces 8/19. P18 overall remains in
progress. Live task/step/tool/rollback, termination, broader projections and full
multi-surface acceptance are separate remaining packets; P19 is untouched.

The actual gap was in storage: `result_json` retained tool data, not the final
executor factual message. The policy refusal stored an error body without a
dedicated reason. The UI consequently had only generic flags and templates.

Migration 0006 adds nullable `presentation_json`. Registry success, failure,
refusal, priority STOP and prepared/finalized mutation paths now preserve final
executor copy; the policy refusal captures `PolicyEvaluationResult.reason`
directly. This does not reconstruct messages from planner prose, private result
bodies or undo recipes. Historical rows remain explicitly unavailable.

The existing action-change trigger is extended, rather than duplicated. A
combined action/presentation update produces one journal event in the same
transaction. Mutation result and inverse finalization retain their atomic path.

## Typed and private readback

The new `action_detail_query` / `action_detail` v1 pair scopes a single record
by canonical task ID and positive action ID, with exact request/task/originating
request/action/tool correlation. Original `activity_query` / `activity_page`
envelopes and wire records stay unchanged for strict E88 clients. Detail is
separate UI state, not an ignored property on the activity wire DTO. A new UI needs the paired core
for the new endpoint; an unavailable endpoint fails closed, not a fabricated
detail fallback.

The response contains only the saved redacted factual message, canonical error
code and actual policy reason. No command/transcript, arguments, result/error
body, inverse recipe or process/resource identity is fetched by this query.
Copy and reason are each bounded to 1,024 UTF-8 bytes; error identities are
uppercase ASCII identifiers of at most 64 characters. Complete-value redaction
precedes truncation; bounded text ends with an ellipsis when truncated. Known
clipboard/paste result values and secret-shaped error identities are withheld
on both write and read. Historical missing fields are null;
malformed, oversized or contradictory saved data refuses. Readback reapplies
redaction and never creates an action or journal event.

All scoped detail reads finish before the existing coherence barrier commits
the batch. Unavailable/foreign detail leaves routes, results, notices and cursor
uncommitted. Fingerprints include presentation content, excluding transient
query IDs. Changed detail replaces the same action key; unchanged evidence does
not replay solely because it was requested again.

Surface 8 binds the actual saved factual message and error code, with separate
recorded verification flags. Pre-mutation intent is explicitly Pending, not a
completed result. Surface 19 binds the actual saved policy reason. Historical
absence is displayed as unavailable. Neither display issues a tool, cancellation
or undo action. Existing dark styles, sizes and popup host behavior are retained;
no XAML/theme/placement resource was changed.

## Verification

Prerequisites: clean authorized branch at E89; unchanged complete master blob
`01b693dbf898b662aa4cd67736c1a0e8a21cf3e3` and applicable prior specification/
owner/acceptance material reused. Refreshed AGENTS, P18/shared prompt, handoff,
matrix, Phase 14 and relevant source/tests. E89's exact-source hosted gate
remains valid for its unchanged baseline scope.

Fresh isolated prerequisite command:

```text
output/p16-windows-env/Scripts/python.exe -m pytest -q tests/unit/test_p18_activity_query.py tests/unit/test_p15_remaining_contracts.py tests/unit/test_policy_boundary.py
66 passed in 12.09s
```

Final affected Python command:

```text
output/p16-windows-env/Scripts/python.exe -m pytest -q tests/unit/test_p18_action_details.py tests/unit/test_p18_activity_query.py tests/unit/test_db.py tests/unit/test_mutation_journal.py tests/unit/test_tool_runner_ledger.py tests/unit/test_policy_boundary.py tests/unit/test_p15_remaining_contracts.py tests/unit/test_redaction.py tests/unit/test_stop_protocol.py
182 passed in 37.69s; no skips/xfails
```

Additional affected Activity-view/lifecycle command:

```text
output/p16-windows-env/Scripts/python.exe -m pytest -q tests/unit/test_activity_ledger_lifecycle.py tests/unit/test_activity_tool.py
17 passed in 2.25s; no skips/xfails
```

The 182-check run includes 18 new checks for exact read-only scope, strict requests, legacy
wire preservation, privacy before bounds, Unicode, historical absence, corrupted
data, actual registry/owned-file verification and policy refusal, mutation
finalization and journal readback. Earlier fixture-construction failures were
fixed without weakening production policy or postcondition checks; full logs
remain under ignored output.

Local console/native-control builds pass with zero warnings/errors. Native
execution uses the existing authorized Windows workflow, not a local policy
bypass. The `650805d` hosted gate passed 194 IPC / 121 native UI / 663 popup /
195 formatting checks. Final review found that a secret-shaped canonical error
identity could bypass text redaction; `06db4c7` fixes both write/read paths and
adds its regression. Exact-source rerun [41051248953](https://github.com/sai161812/pluma/actions/runs/41051248953)
passed on `06db4c78e07ce29f50c35f960188500310c8b899`:

- `./PLUMA.UI/verify-ui.ps1`: **194 IPC / 121 native UI / 663 native popup /
  195 formatting** checks passed. No skipped/xfail acceptance checks.
- **64,537** layout/queue checks over 5,000 scenarios, **30** surface checks,
  audio visualizer suite and **33** compiled-XAML copy scans passed.
- Hosted preview/native-control builds: **0 warnings / 0 errors**.
- Downloaded artifact `12974498741` has verified SHA256
  `949f2dec229417f93eb2556af571a7408c9068deab5b1d2e743615a6f44f82cd`.
  Full reports are under ignored `output/p18-details-privacy-ci/`.
- Report: `status=passed`, `stage=complete`, Windows build 26100; preview apphost
  SHA256 `2567C10125FE3AE550219CB2E28C4A784B840E4FC7596C9A46A84DF1CD49D719`,
  development signature `NotSigned`. This is not packaged-release acceptance.
- Initial dispatch `41049516602` was superseded/cancelled, not a pass. The earlier
  passing `650805d` build is superseded by the exact-source result above. New console checks cover strict
detail parsing, callback atomicity, foreign identity, material replacement and
deduplication; native checks use separate real registered success, failure and
denial tasks plus the existing independent WAL outcome comparison. The pending
label and maximum-name layout cases are explicitly UI fixtures.

## Remaining P18 and recovery

- Actual live task/step/tool/rollback facts and displays (4, 5, 7, 9).
- Verification 17, verified owned-worker termination 21, remaining live-feed 22
  and core-health projection 23 (dedicated health remains P22).
- Broader current/recent panels and notices, host capacity arbitration, and full
  event-driven multi-surface burst/replacement/reconnect/STOP/navigation/shutdown
  acceptance. Separate native controls and host fixtures do not establish this
  whole-application gate. P25 retains physical monitor/taskbar/accessibility.

Next safe packet: establish actual owned live-task/tool/step/rollback evidence
before binding executing states, totals or elapsed timers. The first remaining
packet is the live-task/tool lifecycle contract and its real readback, followed
by actual planned-step totals and rollback progress. Do not infer these
from an action row or a cleanup summary.

Logs: ignored `output/p18-details-*`; isolated APPDATA/LOCALAPPDATA/config root is
recorded in `output/p18-details-current.txt`. Recovery uses reviewed reverts or
a separate checkout of E89, preserving newer work and runtime data. Source
rollback cannot undo external operations. No reset, clean, force push, branch
switch or merge is authorized. This bounded packet is ready for independent Sol review; approval is not
assumed. The overall P18 gate remains open.
