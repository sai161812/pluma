# Native UI verification runner

The draft integration PR includes `.github/workflows/ui-verification.yml` and
`PLUMA.UI/verify-ui.ps1`. They provide a repeatable test gate on a standard
GitHub-hosted Windows x64 runner without changing the owner's local signing or
Application Control configuration. The workflow has read-only repository
permissions, pinned first-party action revisions and a 20-minute job timeout.

The PowerShell 7.2+ script performs the existing layout, surface-contract, audio
and visible-copy checks, builds the unpackaged/self-contained WinUI preview and
control runner, then launches their existing native fixture entry points in
sequence. The script requires completed pass reports, correct render counts and
a successful native control-runner exit code. Missing reports, error files,
early exit, launch refusal or a timeout fail verification; a successful process
start alone never counts as a pass.

Each run uses a fresh artifact directory under `output/ui-verification/`, records
the commit, Windows version, interactive-session flag, executable hash and
signature status, and tracks owned process IDs/creation times. Native audits
are bounded to 150 seconds and the control runner to 45 seconds. Cleanup first
closes the owned fixture window, then verifies process identity before any
necessary termination of its owned process tree. No existing user application,
taskbar setting, security policy, microphone or backend is changed.

Reports and fixture-only PNGs are uploaded even on failure and retained for
seven days. Compiled binaries, credentials and arbitrary desktop screenshots
are not uploaded. Saved output remains ignored by Git. On a permitted local
Windows runner with PowerShell 7 and the required SDKs, use:

```powershell
pwsh -File ./PLUMA.UI/verify-ui.ps1
```

## Executed hosted verification

[Run 5](https://github.com/sai161812/pluma/actions/runs/39158908362), head `d312ac6`,
completed successfully: **658 native popup, 195 formatting and 35 native control
checks**, all 26 Dark gallery renders, all 15 floating class renders, and the
64,537/30/15 pure regression checks. Both native projects built with zero
warnings/errors. See [ui_integration_review.md](ui_integration_review.md) for
the exact source, environment, hash, corrections and artifact location.

The initial hosted job failed its client-width assertion; it is retained as
failure evidence. A diagnostic rerun passed, then the startup layout gate and
native InfoBar height were corrected and passed the current expanded audit.
Successful process start or a historical passing run never substitutes for a
completed report for the source being reviewed.

The owner's local Application Control restriction remains unchanged. A hosted
Windows Server result does not establish physical taskbar/DPI/accessibility
behavior on the owner's Windows 11 laptop. Keep those checks and backend wiring
separate, and keep the integration PR in draft.

Primary references:

- [GitHub-hosted Windows runner specifications](https://docs.github.com/en/actions/reference/runners/github-hosted-runners)
- [Windows 2025 runner image](https://github.com/actions/runner-images/blob/main/images/windows/Windows2025-Readme.md)
- [Windows App SDK self-contained deployment](https://learn.microsoft.com/en-us/windows/apps/package-and-deploy/unpackage-winui-app)
