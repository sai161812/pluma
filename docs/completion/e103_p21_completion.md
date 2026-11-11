# E103 — P21 settings completion and verification

2026-11-03, Asia/Calcutta. Scope is P21 only. P22 is not implemented or started.
This checkpoint supersedes E100–E102's remaining-settings lists, while retaining
their narrower evidence and the separately recorded owner-approved deferrals.

## Authority, starting point and recovery

Started clean on `p12-preparation` at
`ef70aac78ad72b79ab66a92ca9cb0da05801aed3`. Pushed recovery ref
`recovery/pre-p21-e103-20261103` points to that source. Main remains
`0468a031238261bee5bc79bd04b16a3d1964a3a9`; no merge, branch switch, reset,
clean, force-push, new dependency or security bypass occurs.

AGENTS, the complete immutable master, P21/shared contract, current handoff,
build plan, acceptance A/B/C/G/H/J, affected matrix rows and preceding audit
findings were reviewed. The master's unchanged Git blob is
`01b693dbf898b662aa4cd67736c1a0e8a21cf3e3`. Existing unaffected P00–P20
evidence is reused, with fresh affected/prerequisite checks below. Pre-edit
settings/lifecycle/activation selection: **132 passed**, no skips/xfails.

Declared implementation files cover settings storage/schema/owned tools,
resident activation and runtime projection, application composition/logging,
planner/speech grace, policy evaluation, native hotkey adapter, Settings
page/controller/protocol, existing runtime observer/command entry and their
owned Python/C#/Windows tests. Existing dark resources, palette, typography and
card styling are retained. New controls use those existing components.

## Closed P21 requirements

| Requirement | Implemented behavior and evidence |
|---|---|
| SettingsContract / surface 2 | Native navigation attaches one shell-owned controller. Actual persisted/effective values, revision, restart fields, Save, Cancel, Reload, errors, STOP and explicit previous-source recovery replace preview selections. The Python interface remains an abstract alternate-host boundary; the native implementation is MainWindow/SettingsPage/SettingsController. |
| Typed ownership | Strict `settings_save` accepts supported non-null fields only. Changes use registered MEDIUM `save_settings`, the existing capsule, exact confirmation, bounded owned worker/Job, identity-recorded staging, durable journal, independent readback and factual ledger. Unknown submissions are never replayed. |
| Hotkeys | Text, STOP and push-to-talk bindings validate syntax and internal conflicts. Changed chords are probed in the owned pre-state worker, releasing only acquired registrations. Already live-owned chords come from trusted parent binding, not tool arguments, so saving back to an active binding does not self-conflict. Startup acquires STOP first and publishes IPC/voice readiness only after all required registrations succeed. Failure seals admission, latches tasks and drains the owned thread. Native registration status is read back, not guessed from configured strings. |
| Text activation | A native text-hotkey message produces a UUID/timestamp through authenticated runtime readback. The existing shell-owned observer opens/focuses command entry once, with a three-second expiry rechecked at UI dispatch. It executes no tool and starts no new polling worker. Expired/duplicate messages do not reopen the page. STOP remains independent. |
| Local model/runtime paths | Local absolute planner GGUF and speech GGML paths validate bounds, accessibility and expected format header before commit. Malformed relative/network/null paths fail schema validation; missing/wrong-format files fail owned pre-state without mutation. Current supported runtimes remain local llama.cpp and whisper.cpp; no arbitrary server/command/network toggle exists. Actual known native models are exercised after persisted settings and owned restart below. Format fixtures are never represented as working models. |
| Voice activation | V1 remains push-to-talk; its editable hotkey is consumed by the actual new VoiceActivation owner. Mandatory voice, no wake/background microphone and shared request/STOP behavior remain enforced. No unmeasured wake-phrase mode is advertised. |
| Grace | Editable model/STT/OCR delays are bounded upper limits, 0–30 seconds; the separate permission flag can disable grace. Off applies zero to the actual planner/STT managers after restart. Zero now unloads an in-process adapter immediately rather than leaving it warm without a timer. Current production native task workers release their models after each request, even when grace is permitted; OCR workers likewise release on completion. No warm cache or measured speed benefit is falsely claimed. |
| Privacy / logging | Saved diagnostic logging uses the existing DEBUG/INFO host behavior after restart. CLI `--debug` is reflected in effective configuration. Command-preview privacy hides typed/spoken previews and route detail from logs while preserving required factual Activity/request data. Sensitive-value redaction stays mandatory at both levels. Raw audio/screenshots remain transient; no debug-capture persistence or redaction-disable switch is exposed. |
| Allowed policy setting | Optional `confirm_low_risk` raises LOW actions to the existing MEDIUM material-confirmation path. It cannot lower registered risk, bypass protected targets, high-risk confirmation, denied operations or one-operation elevation. Disabling this optional stricter rule restores the baseline LOW behavior; mandatory controls remain locked. |
| Atomic persistence / undo | E100/E101 atomic versioned storage, last-valid backup, exact revision, selected-source authority, denial/readback restoration and minimum pre-state are retained. Undo now restores touched fields across agent/brain/voice/runtime/logging/policy sections, preserving original section presence and unrelated settings. Later edits conflict rather than being overwritten. Existing once-only selected inverse and STOP-before/after-commit staging checks still pass. |
| Corrupt-source recovery | Only a valid, exact previous revision can be explicitly restored. The rejected source is independently preserved under the selected source's `.rejected.<digest>` name. Symlinks, changed revisions, missing/invalid backups and denied writes refuse safely. Recovery uses registered non-undoable `recover_settings`, exact material confirmation, owned staging, durable intent, independent source/retained-original verification and truthful no-automatic-undo history. Ordinary reload never silently restores or switches profiles. |
| Offline recovery | If a corrupt source prevents startup, `python -m pluma --restore-previous-settings --config <selected.json>` runs the same owned typed recovery pipeline without starting resident hotkeys, capture or ML. It requires the exact interactive `RESTORE` confirmation. A missing valid backup is a preserved-source error, not permission to replace the profile with defaults. |

All behavioral settings above require Core restart. Saving never pretends to
change the current live graph. Runtime restart controls/setup remain P22's scope;
P21 verifies owned shutdown/new construction and native registration directly.
The master baseline defaults are unchanged. Migration preserves legacy JSON
semantics; unsupported/security-invalid overrides cannot be laundered into a
valid backup. YAML remains read-only, as previously recorded in E100.

## Verification and exact identities

Unique ignored root: `output/p21-e103-20261103-222120-3dfb6de1/`.
Per-run JSON/JUnit/stdout retain exact commands, results and source identity;
test APPDATA/LOCALAPPDATA/TEMP/TMP are isolated. Full logs are not checked in.

Commits: `903c5a8` adds the settings lifecycle/recovery implementation;
`26ccdc1` adds live-owned hotkey readback and the native model harness;
`e4180c96765ed27e77c3eb1f5033c71360ce55b6` adds functional privacy/logging/stricter
policy controls; `fdfb5d4` strengthens actual saved-hotkey restart acceptance;
`a041b1a3d23488f0788bb1cec4553631cde8147c` closes the discovered text-hotkey
command-entry gap and adds bounded authenticated activation checks.

Fresh final combined Python selection at `e4180c9`: **1,025 passed**, no
failures/errors/skips/xfails, 116.157 seconds wall time. This combines the prior
501 prerequisite and 352 routing/planner/executor selections with settings,
policy, privacy, IPC, ownership and STOP regressions, deduplicating modules.
`final-required/command.json` records the complete command. It uses
`-p tests.fixtures.desktop_isolation` for inert FAST clipboard/window/audio
fixtures; these are not native personal-desktop acceptance. Native Jobs,
isolated storage, process absence, owned atomic writes and SQLite readback
retain their real adapters.

Test Python:
`D:/Workspace/DEVEL/PLUMA-verified-integration-20261103/output/integration-checks-e98/test-env/Scripts/python.exe`.
All runs use `--runxfail -W error::pytest.PytestUnhandledThreadExceptionWarning`.
The later production delta is confined to resident/runtime activation protocol;
saved-setting/model/policy/privacy code remains the tested `e4180c9` source.
Final affected runtime/IPC/STOP selection at `a041b1a`: **136 passed**, no
failures/errors/skips/xfails, 28.141 seconds wall time. Exact command/results
are in `final-runtime/command.json` and its JUnit/stdout. This includes P18
runtime/activity/detail, P21 settings, strict IPC, P17 submission/STOP, activation
and shutdown. The full 1,025 selection is reused for unchanged
app/brain/voice/config/policy/tool production code; `git diff e4180c9 a041b1a`
confirms no changes to those paths. Runtime protocol and shell changes receive
the final affected selection and exact-source native gate below.

### Actual native model settings use

Commands (through `run_native_verified.py`, with isolated host directories):

```text
output/p13-native-env/Scripts/python.exe tests/windows/p21_settings_native_acceptance.py --kind planner --model output/p13-native/model/Qwen3-4B-Q4_K_M.gguf --report <evidence>/verified-native/planner-native.json
output/p14-native-env/Scripts/python.exe tests/windows/p21_settings_native_acceptance.py --kind speech --model output/p14-native/ggml-base.en.bin --sample output/p14-native/jfk.wav --report <evidence>/verified-native/speech-native.json
```

Both pass at `e4180c9`. Each cycle saves through the real owned ToolSpec, closes
the graph, constructs a new one from the persisted source, verifies cold startup
and effective manager/path values, uses the actual model and verifies returned
COLD and owned-worker absence. Permission-on/off cycles use a two-second
configured ceiling, consumed as 2/0 seconds by the actual managers. Neither
production task-owned runtime retains native weights after completion. This
measures observed end-of-task release and request durations, not a cache benefit
or hardware unload latency of exactly zero seconds.

- Qwen3-4B Q4_K_M: 2,497,280,256 bytes; SHA-256
  `7485fe6f11af29433bc51cab58009521f205840f5b4ae3a32fa7f92e8534fdf5`.
  Actual read-only owned-directory tasks take 36.046 / 33.141 seconds and verify
  their file results, saved actions, terminal/cleanup and no parent model load.
- Whisper base.en GGML: 147,964,211 bytes; SHA-256
  `a03779c86df3323075f5e796cb2ce5029f00ec8869eee3fdfb897afe36c6d002`.
  Recorded-fixture native transcription takes 2.203 / 2.125 seconds. The matching
  capsule owns inference and controller/worker absence is verified on teardown.
  No microphone opens and no raw audio copy is saved. These are separate native
  environment checks, not a new combined Whisper-to-planner acceptance claim.

### Windows native UI gate

Final product/test source
`a041b1a3d23488f0788bb1cec4553631cde8147c` passes
[Windows run 41684268644](https://github.com/sai161812/pluma/actions/runs/41684268644):
**329 IPC/controller checks, 236 native UI checks, 663 native popup checks,
195 formatting checks, 64,537 layout checks and 30 surface-contract checks**,
plus audio/visible-copy gates. The 236 UI report contains no skipped, xfailed
or UNEXECUTED check. The original P20 folder visibility, saved verifier and
owned-window cleanup condition passes at its unchanged deadline. The new native
text-hotkey message reaches the actual command-entry page. All native control
and preview builds have zero warnings/errors. Local C# execution restrictions
are retained; no Windows policy is bypassed.

Artifact **13254832301**, SHA-256
`db3b56dce7de8ec1f5d2b3a855d280899d035b21f4db1d2c19c2f93299c7e66f`,
was downloaded and verified against the GitHub API digest. Extracted reports:
`ci-41684268644/extracted/20261103-172735-82a88d66/` under the evidence root.
Unsigned preview executable SHA-256:
`A4E0CED1893052AC52BE7A4C12A30026ABB0714C02E4A63B66CAE200F2E0A017`.
This is native test/build evidence, not signed release/installation acceptance.

`python docs/completion/verify_requirements_matrix.py` passes **298 source
items / 336 traceable rows**. `git diff ef70aac HEAD --check` passes. Final
checkpoint changes are documentation only; tested runtime source is unchanged.

Native tests use the disposable GitHub desktop, fresh profiles/pipes/credentials,
owned files and explicitly acquired hotkeys. WM_HOTKEY is posted only to the
owned message thread; no global input is injected. Registration conflicts and
release use actual Win32 calls. The production native page saves all three
bindings, local format-fixture paths, grace/privacy/logging/policy settings,
starts an owned Core with the saved bindings, checks material approval/denial,
stale refusal, recovery, navigation and joined close. Format fixtures verify
wiring/storage; the actual model runs above verify native model use.

## Earlier failures and limitations retained

- Initial scope-change failures used obsolete assertions that hotkeys/grace
  were unsupported and non-format placeholder model files were accepted. Tests
  now exercise the expanded contract and retain explicit invalid/unsafe cases.
- New integration tests exposed a missing required non-undoable intent flag;
  the tool now supplies the canonical journal proof instead of bypassing it.
  Fixture mistakes (wrong undo shape, missing context source, and attempting to
  attach worker-only execution binding to a Pydantic capsule) were corrected.
  One test invocation referenced a nonexistent policy test file and ran no
  tests; its exit 4 is retained and not counted as a pass.
- Windows run 41680455811 at `903c5a8` passes 328 IPC / 235 native UI, popup,
  formatting and other normal gates. Run 41681817449 at `26ccdc1` fails the
  existing P20 owned-folder six-second UI condition before reaching P21. No
  longer timeout, skipped assertion, Explorer termination or unrelated source
  workaround was introduced. Its logs/artifact are retained. Final normal gate
  readback must pass the original condition; a later pass does not diagnose the
  internal cause of that intermittent earlier Shell/Explorer delay.
- Superseded Windows runs 41683025674 and 41683567077 are cancelled, never
  retrospectively passed. Earlier
  numeric native-retention report fields are superseded by the final Boolean
  weight-retention observations above; no exact zero-duration claim is made.
- C-02 physical timing retains the owner's explicit P25 deferral. Physical
  microphone/keyboard/device review, installation/signing, broad performance,
  full corpus/security and release scopes remain their recorded later gates.
  These are not new P21 waivers or fixture-as-native claims.

## Completion / next safe step

**P21 is complete against its settings/restart/readback gate. No P21 work packet
is left pending.** The broader CORE-CONFIG row remains UNVERIFIED for exhaustive
Appendix A/corpus/performance validation; P21 does not establish full-product
readiness or zero bugs. Independent Sol review is the next safe step; no Sol
approval is inferred. P22 is the next milestone after review/owner instruction,
and is not started here.
Recovery uses reviewed dependent reverts from the pushed recovery point,
preserving later work and selected settings/retained rejected-source evidence;
never reset, clean or force-push. Preserve/export the selected profile before
reverting code: older hosts do not apply the new privacy/policy fields. Review
those overrides and required privacy behavior before starting an older host;
never silently rewrite the current profile to fit old code.
