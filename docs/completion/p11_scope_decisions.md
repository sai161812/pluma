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

Clipboard: support Unicode text, file lists and bitmap images through native
Windows APIs. Undo captures remain in memory; never persist private clipboard
payloads or raw bitmap data in logs/history. Refuse unsupported formats before
mutation. Every mutation needs sequence/identity checks, independent readback
and safe undo/conflict behavior. Test native clipboard operations inside an
isolated fixture context, preserving the user's actual clipboard.

Primary format references: [Windows clipboard formats](https://learn.microsoft.com/en-gb/windows/desktop/dataxchg/clipboard-formats)
and [Shell file-list formats](https://learn.microsoft.com/en-us/windows/win32/shell/clipboard).

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
