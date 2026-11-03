# E89 - P18 packet 3: route, recorded result and policy surfaces

Date: 2026-10-30 (Asia/Calcutta). Branch: `p12-preparation`.
Implementation: `975cbafaa1882e010fb75f2f1e5cf80dea799bdd`.
Final source: `ef178524548eb43ed1c573f22959184e364785d1`, including caption
wrapping (`af5e99b`), its formatter-aware native assertion (`6a19059`),
the journal/readback race fix (`15004a0`) and deferred settling (`ef17852`).
Recovery: `52116bad7650bf6b119a400838a3e95e1c8f729d` (completed E88).

## Bounded scope

This packet binds existing route badge 6, recorded action/result card 8 and
policy-denial notice 19 through the P18 consumer and shared popup host.
**This bounded packet passed its gate; overall P18 remains incomplete.**
No later milestone or merge is authorized.

Changed runtime files: EventFeedController, CoreActivityProtocol's shared
message template, ActivitySurfaceFact/ActivitySurfacePresentation, MainWindow,
RouteBadgePopup XAML/code and ToolResultCard XAML/code. Tests update console/
native runner links, SurfaceFactChecks, the fake feed client signature and
NativeEventFeedChecks. Backend Python, ToolSpecs, policy, STOP, undo, master,
theme resources, typography, dimensions and popup placement logic are unchanged.

## Behavior and evidence semantics

Task events read the actual saved route. Action events require their exact saved
action ID. The consumer reuses a matching correlation-page action or performs
a scoped one-action query after that ID minus one, then checks task/request and
action identity. Missing IDs, mismatches and unavailable evidence fail closed.
No route, action surface, task notice or cursor is published from a partial
failed batch. Historical reset seeds route fingerprints silently; repeated
unchanged events do not replay cards. Material verification/denial changes reuse
the same task/action key, allowing the existing native host to replace content.
Surface fingerprint state is bounded to 512 keys.

Coalesced task groups retain their journal order. Within a group, route and
recorded action evidence is delivered before the task-terminal notice. This is
current factual readback, not simulated replay of transient tool execution.
A bounded coherence barrier drains up to 22 event pages per attempt and checks
the journal again after material readback. New commits cause a retry from the
uncommitted cursor (at most four attempts within the existing 30-second budget).
An unsettled stream retains the previous view, publishes an explicit settling/
stale status and retries uncommitted events on the next poll. No partial task
or action evidence is published. Delivery yields between callbacks and checks
cancellation, so larger retained batches do not form one synchronous UI burst.
MainWindow owns the subscription under the existing window lifetime, marshals
presentation to its dispatcher and unsubscribes on close. Surface creation and
dismissal issue no tool, STOP or undo calls. Existing host capacity refusal and
whole-application burst arbitration remain explicitly open P18 work.

The route default is Unavailable. The result card defaults to unavailable/
unverified evidence instead of a fabricated opened-file success. It displays
the actual formatted tool identity, a deterministic recorded-issue or verified/
unverified postcondition message and a separate verification indicator. An
action issue is not automatically execution failure, and a verified action is
not aggregate task completion. Policy 19 requires the explicit saved denial
flag and displays the exact tool with a fixed factual denial template. No
commands, arguments, private result bodies or exception strings are introduced.

The existing dark controls, shared stack, reading holds, class sizes and
taskbar motion are retained. The tool-name caption now wraps bounded unbroken
identifiers. The native stress check preserves the full 64-character name while
allowing the established title-case formatter; it also checks multiline height.

## Prerequisites and checks

Refreshed AGENTS, P18/shared prompt, handoff/matrix and source/tests. Reused the
complete unchanged master (blob `01b693dbf898b662aa4cd67736c1a0e8a21cf3e3`),
owner decisions and applicable build/acceptance material already read. The
starting runtime/test tree exactly matches E88's tested `65d458b`; E88's actual
Windows report records 171 IPC / 105 native UI and passing popup/format gates.
Historical claims alone were not treated as a new test result.

Fresh Python prerequisite command, with isolated APPDATA/LOCALAPPDATA/config:

```text
output/p16-windows-env/Scripts/python.exe -m pytest -q tests/unit/test_p18_activity_query.py tests/unit/test_p15_remaining_contracts.py tests/unit/test_ipc_request_contract.py tests/unit/test_p17_submission_stop.py tests/unit/test_stop_protocol.py tests/unit/test_policy_boundary.py
127 passed in 20.14s; no skips/xfails.
```

The unchanged console executable was blocked by Windows Application Control
before Main. That attempt is not a pass. The source-equivalent E88 native
evidence was reused for prerequisites; changed native behavior is tested by the
normal authorized Windows workflow. No alternate loading route, policy change
or security bypass was attempted.

Local console, native controls and production preview builds passed with zero
warnings/errors; 33 compiled-XAML copy scans passed. Final-source hosted
builds and counts are recorded below. No unrelated Python audit was repeated
after this UI-only change.

New deterministic tests cover silent historical routes, failed action-readback
atomicity, exact action selection, replay suppression, same-key verification
replacement, policy surface selection, stream reset and unidentified action
refusal. A ninth check reproduces material readback racing ahead of its
initial journal query and requires all action facts before the terminal notice.
Two further checks exercise all four unsettled attempts, unchanged prior view,
no partial callbacks, explicit settling status and subsequent exactly-once retry.
Native checks use real authenticated owned tasks/WAL readback to bind
route, recorded result and denial controls, check delivery ordering and prove
neutral defaults. The maximum-name layout case uses synthetic UI text, without
executing an unregistered tool.

## Native gate

Exact-source Windows run [41046523711](https://github.com/sai161812/pluma/actions/runs/41046523711)
passed on `ef178524548eb43ed1c573f22959184e364785d1`:

- `./PLUMA.UI/verify-ui.ps1`: **182 IPC / 113 native UI / 663 native popup /
  195 formatting** checks passed; no skipped or xfailed acceptance checks.
- **64,537** layout/queue checks across 5,000 scenarios; **30** surface checks;
  audio visualizer suite and **33** compiled-XAML copy scans passed.
- Hosted production-preview and native-control builds: **0 warnings / 0 errors**.
- The native checks retained exact WAL comparison, route and denial identity,
  result verification, full maximum-length name wrapping, result-before-notice
  ordering, dismissal without cancellation, replay suppression and navigation.
- Downloaded artifact `12972926386`, SHA256
  `d95deb54861eaf7dbf177d463d946f8f74cdd5489f2cb2b81f2f05ab485de059`.
  Ignored extraction: `output/p18-surfaces-final-ci/20261030-111450-4e490604/`.
- Report: `status=passed`, `stage=complete`, Windows build 26100, preview apphost
  SHA256 `A8FAAD00F06121E3A5E1729EE3947310064C681E00F04229B9AF35E1039392A0`,
  development signature `NotSigned`. This is not a packaged release.

Diagnostic runs below are not acceptance passes. The earlier `6a19059` run [41043762555](https://github.com/sai161812/pluma/actions/runs/41043762555)
passed 179 console checks but failed the native action lookup: completed
material readback arrived before the action journal events had been consumed.
The coherence barrier and ninth console regression fix that reproduced race;
the native ordering and exact action lookup checks remain intact. Its ignored
artifact digest is `a0357d2aff52485b1a3353519fe8aa94587fbce2ac15f778ad6c50eea29bcda9`.
The intermediate `15004a0` run [41045523621](https://github.com/sai161812/pluma/actions/runs/41045523621)
passed 180 console checks and the native read-result/order/wrapping case, then
failed when the denial task advanced during all four retry attempts. `ef17852`
retains the view with explicit settling status and retries next poll; two
regressions cover this behavior without relaxing native assertions. Its ignored
artifact digest is `cc156bf2cb0f120bb54b172dbb543854f081b5e1313046f3fc2c7f0b1b7df2d8`.
Two earlier dispatches were superseded/cancelled and are not passes. The caption
formatter correction retains full-name and multiline-layout checks.

Owned native feed/notice/control integration and desktop-host placement/motion
are separate fixtures, not full event-driven MainWindow/backend acceptance.
No personal desktop, file, clipboard, browser profile, microphone, model, power
or UAC operation is used. P25 physical monitor/taskbar/accessibility and owner
appearance acceptance remain separate.

## Remaining components and next safe step

- Task-running surface 4, step progress 5 and tool-call surface 7; establish
  actual live-start/step/argument evidence before presenting those states.
- Rollback surface 9, verification indicator 17, verified owned-worker
  termination 21, the remaining live-message panel 22 and core-health
  projection 23 (the dedicated health milestone remains P22).
- Broader notices/current/recent activity panels, richer result detail where
  required, host-capacity arbitration and full multi-surface desktop/backend
  burst/replacement/reconnect/STOP/navigation/shutdown acceptance.
- Detailed result/error messages for surface 8 and exact matched-policy reason
  for surface 19 need a safe typed readback. This packet binds recorded flags;
  it does not claim those fuller component contracts are complete.
- Cleanup detail beyond existing bounded summaries and P25 physical checks
  retain their separate recorded gates. A cleanup summary or event name never
  proves worker termination.

Next safe packet: typed, redacted factual result/error and matched-denial reason
readback to finish surfaces 8/19. Then add actual live task/step/tool/rollback
evidence before displaying executing states or totals. P19 has not started.

Full logs stay ignored under `output/p18-surfaces-20261030-155403/` and
`output/p18-surfaces-*.log`. Preserve recovery `52116ba` and existing recovery
branches; use reviewed revert or a separate checkout without replacing unrelated
runtime data. Source rollback cannot undo external operations. No reset, clean,
force-push, merge or branch switch occurred. This packet is ready for independent Sol review; approval is not assumed.
Overall P18 is not ready to advance.
