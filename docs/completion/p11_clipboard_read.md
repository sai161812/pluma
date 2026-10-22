# E40: plain-text clipboard read and owner scope correction

2026-10-22, Asia/Calcutta; source parent `12d11f9`, branch `ui-wiring`.
P11 remains incomplete; P12 is forbidden.

The owner explicitly narrowed clipboard functionality to practical plain-text
copy/paste and rejected file-list/bitmap expansion. The prior delegated format
choice is superseded in p11_scope_decisions.md and current handoff/audit/matrix.
No locked master requirement requires those additional formats. Their production
handling and dedicated tests were removed before this checkpoint. This is a
scope decision, not a new UI setting, undo waiver or full P11 completion claim.

clipboard_get and its get_clipboard_text compatibility name now use strict empty
arguments, required owned workers and separate native readback. Unicode text is
bounded to 65,536 UTF-16 units; raw memory/format enumeration and transient busy
waits are bounded. Missing/inaccessible/malformed data cannot become a claimed
empty clipboard. Non-text format IDs are reported without reading their data;
no file/image/rich-format operation is exposed. Windows APIs remain cold at idle.

Readback checks the native sequence, owner and full supported observation. Caller
data uses the protected clipboard_value field; payloads are redacted from SQLite
and private receipts are removed. A reproduced source privacy gap in the prompt
builder is also repaired: prior tool results now pass through deterministic
redaction before entering planner context. No model call is needed to test this.

## Evidence

Use `output/p11-native-env/Scripts/python.exe -m tests.fixtures.clipboard_logon
clipboard-focused-textfinal` or `clipboard-regression-textfinal`. The closed
fixture launcher uses native NETCREDENTIALS_ONLY with unused random network
credentials to create a temporary logon context with the **same user and same
integrity**, verified before resume. No account creation, elevation, network
access, profile load, machine-policy change or product run-as tool is added.
The original retained process handle is registered by task/PID/creation time,
assigned to its Job before resume, and drained with native absence readback.

The fresh context creates a system-named, create-only, private-ACL window station
and message-only fixture window. It never switches the visible desktop or reuses
an existing station. This is test infrastructure only. Fixture APIs restore and
close their own station/desktop/window handles. Outer checks confirm original
WinSta0 clipboard sequence unchanged and zero owned processes remaining.

| Suite | Actual result | Wall seconds |
|---|---|---|
| clipboard-focused-textfinal | 25 passed in 10.69s | 11.814 |
| clipboard-regression-textfinal | 179 passed in 31.81s | 32.701 |
| raw-e40 | 15 passed with --runxfail in 0.78s | 1.704 |

Final actual exits zero, source hashes match, fixture keys zero. Native launcher
metadata independently records same user/integrity, fresh logon, no requested
profile loading, unchanged interactive clipboard sequence and drained Job. Counts
overlap. Matrix coverage 298 source items / 324 rows PASS; diff check PASS.

Coverage includes native empty/Unicode/unsupported observations; exact native
text/voice capsule/SQLite paths; private result/prompt redaction; schema/denial;
changed/forged sequence, owner, digest and data; busy/failure; malformed and
oversized text; actual owned blocked-worker STOP/timeouts. Inert cases are labelled
explicitly. Safe legacy READ/spec checks pass inside the isolated station. Legacy
write/clear acceptance is not inferred from these reader checks.

Retained failures: initial named station was denied (administrator-only naming);
create-only system name then refused an already-existing station. Neither failure
read or mutated user clipboard contents. A generated oversized test ID exceeded
Windows' environment-variable limit; explicit short IDs fix the fixture. The
fresh local context resolves native isolation without weakening the boundary.
An initial token-integrity probe used the SID/attribute tuple incorrectly and
failed before process creation; the corrected probe checks its SID component.
Earlier multi-format runs remain historical and do not enlarge the final scope.

Catalog: **49 registered / 24 unregistered; 31 IMPLEMENTED / 24 MISSING /
2 DEFECTIVE / 16 UNVERIFIED**. Eight P11 names missing: open_file, clipboard_set,
open_terminal and browser five. Clipboard clear/private text undo and remaining
native/A/D/H gates remain open. Next bounded work is plain-text write/clear with
minimum in-memory undo and conflict refusal, without format expansion.

API basis: [window-station clipboard scope](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-setprocesswindowstation),
[create-only system naming](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-createwindowstationw),
[temporary same-permission logon](https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-createprocesswithlogonw).
