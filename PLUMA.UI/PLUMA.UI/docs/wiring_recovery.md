# Return to the pre-wiring checkpoint

Before wiring, the clean `ui-wiring` branch was at
`04bc1fb7d1efa1744b1027a51ce10e3b3ef7eccc`. The annotated recovery tag
`pre-ui-wiring-2026-10-19` is pushed to GitHub and points to that commit.
It includes the previously verified dark UI and the wiring handoff.

To inspect or build that exact phase without discarding later work, create a
separate checkout. Run these commands in PowerShell, using a new destination
directory and branch name if the example names already exist:

```powershell
git -C D:\Workspace\DEVEL\PLUMA fetch origin --tags
git -C D:\Workspace\DEVEL\PLUMA worktree add -b recovery/pre-ui-wiring D:\Workspace\DEVEL\PLUMA-before-wiring pre-ui-wiring-2026-10-19
git -C D:\Workspace\DEVEL\PLUMA-before-wiring rev-parse HEAD
git -C D:\Workspace\DEVEL\PLUMA-before-wiring status --short
```

The expected HEAD is `04bc1fb7d1efa1744b1027a51ce10e3b3ef7eccc` and the new
worktree should be clean. Existing wiring commits and uncommitted work remain
available. The original `ui-polish` generated-file edits are preserved in the
local stash named in [the cleanup record](../../../docs/workspace_cleanup.md).
No reset, clean, deletion
or force push is needed. The original UI integration also remains at
`9544752` on `ui-polish-integration`.

To undo a published wiring change on the development branch instead, identify
the particular wiring commit and use a normal reviewed `git revert` commit.
Revert dependent changes in reverse order and rerun the relevant checks. Do not
rewrite shared branch history or blindly revert the imported UI.

This checkpoint restores source code only. It cannot undo actions performed by
a later running build; those require the executor's verified undo records.
The first wiring step is limited to authenticated read-only health status and
does not execute tools, alter core configuration, start the core or activate
voice/model workers. The local Application Control restriction still applies
to rebuilt unsigned UI executables; this recovery path does not bypass it.
