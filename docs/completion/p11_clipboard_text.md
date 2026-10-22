# E41: practical plain-text clipboard copy, clear and undo

2026-10-22, Asia/Calcutta; source parent `049c0e9`, branch `ui-wiring`.
P11 remains incomplete; P12 is forbidden.

The owner's corrected scope is plain-text copy/paste only. clipboard_set and
clipboard_clear, with compatibility names set_clipboard_text/clear_clipboard,
now use strict typed arguments, bounded owned native workers, independent native
readback and a minimum private undo capture. No clipboard manager, image/file-list
support, UI setting or new dependency was added. The old stub/no-op verification
paths and false non-Windows successes were removed.

Windows receives Unicode text through a temporary message-only owner window and
an HGLOBAL transferred to Windows. The owner window closes before readback;
clipboard data remains usable after the worker exits. Capture and compare happen
under the native clipboard lock before replacement. Unsupported non-text pre-state,
changed contents, expired undo, busy/unavailable clipboard and invalid arguments
refuse factually. There is no lossy rich-format backup. Partial effects without
proof remain uncertain; they are never reported as successful or blindly restored.

Before dispatch, SQLite contains only an opaque volatile undo reference. Previous
text and native guards remain in the executor's bounded RAM cache (16 entries),
not in Activity history, prompts or undo JSON. Terminal-task entries may expire
at capacity; active-task entries are never evicted. Shutdown clears the cache only
after owned execution drains. Restart/expiry makes the inverse unavailable.
Manual undo uses the existing at-most-once claim and verifies both native state
and durable consumption. Automatic rollback uses the closed owned inverse after
executor drain. Both preserve newer copies; verified ordered inverses rebase only
their exact own predecessor receipt. Clipboard argument values are redacted.

## Verification

Existing isolated clipboard fixtures execute native APIs in a fresh same-user,
same-integrity logon and create-only private station. They never switch the visible
desktop. The original interactive clipboard sequence was unchanged, no profile
was loaded, and owned Job process counts returned to zero. No personal clipboard
was used for acceptance. Test fixtures are not product runtime features.

| Evidence label | Actual pytest result | Runner wall seconds |
|---|---|---|
| clipboard-focused-writefinal | 26 passed in 60.83s | 61.477 |
| clipboard-regression-writes | 274 passed in 139.59s | 140.551 |
| clipboard-focused-fast-e41-final | 1 passed in 1.42s | 2.308 |
| raw-e41 (--runxfail) | 15 passed in 0.80s | 1.716 |
| containment-e41 | 3 passed in 3.40s | 4.193 |
| recovery-e41 | 5 passed in 0.70s | 1.523 |

Commands: `output/p11-native-env/Scripts/python.exe -m
tests.fixtures.clipboard_logon clipboard-focused-writefinal` and
`clipboard-regression-writes`; remaining labels use
`output/p11-native-env/Scripts/python.exe output/p11_power_actions/run_checks.py
<label>`. Raw/JUnit/JSON and independent logon metadata are local ignored artifacts
under output/p11_power_actions. Actual exits zero, fixture keys zero. Regression
source hashes match except the subsequently corrected legacy FAST test setup.
Only that test was rerun after its setup correction; the runtime was unchanged.

Positive cases cover all four mutation names, empty/text pre-state, an actual
WM_PASTE into an owned EDIT control after worker exit, text/voice FAST capsules,
intent-before-dispatch, private history, manual and automatic ordered undo.
Negative cases cover unsupported formats, schema errors, absent journal, newer
clipboard contents and expired private undo. Existing owned cancellation,
verification, policy, memory, mutation-journal and rollback regressions pass.
The FAST fixture remains explicitly inert and is not counted as native acceptance.

Retained follow-up failure: the legacy FAST test expected mutation success with
ledger=None. The required journal correctly refused it. The test now supplies its
own temporary ActivityLedger, preserving its original success assertion; its
isolated adapter fixture matches the new private receipt contract. A stale runner
class name was corrected before executing that single check. E40's extra EOF blank
line is removed; current diff whitespace and matrix coverage checks must pass.

Catalog: **50 registered / 23 unregistered; 33 IMPLEMENTED / 23 MISSING /
1 DEFECTIVE / 16 UNVERIFIED**. clipboard_set/clear are implemented; seven P11
names remain missing: open_file, open_terminal and the five browser tools.
Full undo_last, app/window mutations, cross-volume moves, physical audio/system
effects and remaining A/D/H gates remain open. No P11 completion or P12 eligibility
is inferred. Continue the next bounded P11 gap using the existing evidence.
