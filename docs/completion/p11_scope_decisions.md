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

Declared Windows dependencies may be exercised in an ignored project-local
virtual environment; do not alter global Python, Windows policy or personal
browser settings. No new visual design, P12 perception or UI command enabling.
