# P11 owner-delegated scope decisions

2026-10-20. The owner instructed finishing remaining P11, not starting P12.
Asked about browser adapter scope and clipboard formats under AGENTS.md's
ambiguity rule, the owner replied "whichever is more accurate, effective" and
"decide the best". This delegates these implementation choices, not acceptance
waivers, private-profile access or unsupported execution.

Browser: Edge/Chrome sessions with separate PLUMA-owned profiles and native
DevTools Protocol target IDs. Keep personal profiles untouched. Reuse only
explicitly managed sessions; attach/ownership must be evidenced, and unknown
personal sessions must be surfaced as unsupported, never silently manipulated.
Task-owned targets and pre-existing managed targets must be distinguished and
read back before/after focus/close. Browser sessions are on-demand, not resident
startup work. A named ToolSpec/API, not arbitrary protocol/script/shell access,
is exposed to the planner. These choices still require implementation/native
verification; this record does not claim the browser tools exist.

Primary API references: [CDP target operations](https://chromedevtools.github.io/devtools-protocol/tot/Target/)
and [browser download events](https://chromedevtools.github.io/devtools-protocol/tot/Browser/).

Clipboard (owner correction, 2026-10-22): **plain-text copy/paste only**. The
owner rejected file-list/bitmap expansion as unnecessary. This supersedes the
earlier delegated multi-format choice; it does not change the immutable master,
which names the clipboard tools without requiring those extra formats. Keep
clipboard_get/set/clear usable for Unicode text and ordinary paste. No file-list,
image, rich-format or clipboard-manager features. Minimum safe undo remains in
memory; never persist private clipboard values. Required verification, conflict
checks and refusal before unsupported destructive replacement still apply.
Native tests preserve the user's actual clipboard. Test isolation is fixture
infrastructure, not product functionality or a new user setting.

Primary format references: [Windows clipboard formats](https://learn.microsoft.com/en-gb/windows/desktop/dataxchg/clipboard-formats)
and [clipboard ownership](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-openclipboard).

Terminal: the owner answered the command-template ambiguity with **"Fixed
read-only Windows diagnostics plus explicitly configured, confirmed project
commands (recommended)"**. Implement `run_command`/`run_powershell` as closed
typed template/configuration references, never unrestricted planner strings.
Project commands require explicit configuration and exact-call material-effect
confirmation. Command configuration is trusted owner input, not planner-created
permission. Bound output, time and owned process trees, preserve policy and
readback, and record irreversible effects truthfully. This decision resolves
scope. [E33](p11_terminal_commands.md) implements closed diagnostics plus a
separate typed run_project_command ID wrapper for the private owner catalog,
exact material confirmation and factual unavailable undo. open_terminal and the
remaining P11 native/inverse gates still require work.

Declared Windows dependencies may be exercised in an ignored project-local
virtual environment; do not alter global Python, Windows policy or personal
browser settings. No new visual design, P12 perception or UI command enabling.

## Resolved owner decision: safe_delete recovery (2026-10-21)

The owner answered **"Windows Recycle Bin only (recommended)"** to the question
that explicitly proposed refusal for unrecyclable targets and no permanent-delete
fallback. Use Windows Recycle Bin only. Do not substitute PLUMA quarantine,
permanent deletion, global Bin emptying or an invented retention policy.

[E31](p11_recycle_bin.md) implements a bounded native regular-file path with
exact returned-item identity/stream readback and non-overwriting restore.
[E32](p11_recycle_recovery.md) adds bounded folders and interrupted intent recovery
through owned inverse workers. Unsupported targets/volumes and explicit bounds
are refused; broader physical acceptance remains separate. This decision does not
waive safe_delete's broader acceptance, any other P11 gap or A/D/H checks.
P11 remains incomplete and P12 remains forbidden.

## Resolved owner decision: power-request commit (2026-10-22)

The owner selected **"Initiate the native Windows operation, without forcing
apps closed; record irreversible or uncertain effects (recommended)"** after
being asked whether sleep_request/restart_request/shutdown_request should commit
or only open Windows' power UI. Implement native initiation after exact material
confirmation, with no forced application close and factual non-undoable or
uncertain effects. This resolves behavior, not permission to disrupt the owner's
active session for automated validation, nor a waiver of required evidence.
P11 remains incomplete; P12 is forbidden.
