# P11 E53: legacy undo records no longer block newer guarded inverses

Date: 2026-10-22

`undo_last` now searches available records newest first and skips only known
pre-guard records that lack `guard_version: 1`. It leaves those legacy rows
available and unclaimed. The same selector supplies clipboard undo references,
so a lookup cannot pair a private clipboard receipt with a different row than
the durable claim will select.

Malformed rows, unknown actions, unresolved `pending_mutation` records,
current records with incomplete receipts, and inverse conflicts still fail
closed. A selected inverse must pass its existing compare/readback checks before
the claim is consumed.

The regression inserts a legacy `move_file` record after a guarded preference
write. `undo_last` restores and reads back the preference, while the legacy row
remains available with no rollback attempt or claim. A second fixture proves
clipboard pre-state lookup and claim selection agree across the same legacy
row and that absent private receipt data refuses before creating a claim.

Focused check:

```powershell
output/p11-native-env/Scripts/python.exe -m pytest tests/unit/test_manual_undo.py -q
```

Result: **5 passed in 8.16s** (exit 0).

The native clipboard-write suite was attempted but could not enter its isolated
Windows station: `CreateWindowStationW` returned `WinError 183` because the
system-named station already exists. The fixture refused to reuse that station
and made no clipboard changes. P11 `undo_last` remains open for the other
catalog inverses and their failure/conflict evidence; P12 remains forbidden.
