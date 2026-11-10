# E117 - Interrupted upgrade recovery code preparation

Date: 2026-11-10 (Asia/Calcutta)

Branch: `p12-preparation`

Source base: `cd62b5e28c6694b4f468f9f3e033ba2377eebc61`

Status: **CODE PREPARED ONLY - NO TESTS, BUILDS, INSTALLER RUNS OR PLUMA PROCESSES**

## Source changes

- `install.ps1` now creates a unique transaction record under the selected PLUMA
  install root before moving an existing marked Core or UI payload. It retains
  the prior ownership marker and exact existing startup/UI shortcut bytes.
- Payload moves stay on the install volume. The installer does not move user
  data, models or configuration outside the two marked application payloads.
- An `installing` marker now identifies its transaction and previous-payload
  state. On a later invocation, a valid interrupted transaction checks for
  processes still running from that install, refuses rather than terminating
  them, restores the prior payload and shortcuts, and only then continues.
- A failed first install rolls back its partial Core/UI and newly created
  shortcuts. A rollback marker makes cleanup restartable after another
  interruption. Transaction cleanup removes payload trees before transaction
  metadata, so a cleanup interruption retains enough information to retry.
- Successful install publication now reads back both shortcuts before changing
  the marker to `installed`. A committed old-payload backup is removed only
  through its validated transaction identity. If cleanup fails after the new
  install is committed, the script reports the retained backup and allows a
  later installer run to finish cleanup.
- `uninstall.ps1` refuses an `installing` marker and directs the owner to rerun
  the installer for recovery. It validates and removes only a committed
  transaction backup during ordinary uninstall; user data remains preserved by
  default.
- Recovery includes hidden transaction directories in its scan, rejects a
  Python/Core/UI process whose executable path cannot be read, and validates
  the saved prior install marker before publishing it as restored. The prior
  marker may describe either an installed app or an app already removed with
  user data preserved.
- README, the requirements matrix, project handoff and remaining-work record
  distinguish source preparation from acceptance.

## Review performed

Source review traced the normal first-install, upgrade, caught failure,
interruption between the two payload moves, interruption during rollback,
committed backup cleanup and uninstaller flows. The rollback logic refuses
ambiguous marker/transaction identities, reparse points, changed shortcut
ownership, unreadable process identity and processes still executing from the
selected install. It never uses process-name termination. This was static
source inspection only.

## Required acceptance remains open

No test, PowerShell parser, installer, uninstaller, build, resident or UI was
run. The following disposable-profile checks remain required before P29 or
release completion:

1. First install succeeds and both shortcut targets and ownership marker read
   back correctly.
2. Upgrade succeeds while retaining the prior payload until the candidate is
   fully verified and both shortcut targets read back.
3. Inject interruption before either move, between the Core/UI moves, during
   Core install, during shortcut publication, and during rollback cleanup.
   Rerun recovery and confirm the previous app and shortcut bytes are restored,
   or the first-install partial payload is removed.
4. Confirm an owned process or open UI blocks recovery without termination and
   that unrelated processes/shortcuts are preserved.
5. Confirm default uninstall preserves user data and removes only the validated
   current install, shortcuts and any committed old-payload backup.
6. Run the exact P28 package on disposable clean profiles, then verify installed
   UI/Core launch, authenticated IPC, local data/model separation, crash/restart
   behavior and uninstall readback.

Legacy `installing` markers without the new transaction fields intentionally
fail closed; their files are preserved for manual recovery rather than guessed
at or deleted. This packet does not fix the authorized signing route, run the
builder, close P24/P25/P26/P27, or authorize P32 integration. P29, P31 and the
release remain unverified.
