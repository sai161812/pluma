"""tests.fixtures.fixture_app — Deterministic dummy process for PLUMA tests.

This script is run as a subprocess by tests that need a controllable target
process (e.g. STOP tests in Phase 1). It is deterministic: it sleeps for the
requested duration and exits with code 0, or echoes a string and exits.

Usage:
    python fixture_app.py sleep <seconds>
    python fixture_app.py echo <message>
    python fixture_app.py spin           # Busy-spin until SIGTERM/SIGINT

No ML, no automation code, no Windows-specific imports.
"""

from __future__ import annotations

import sys
import time


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: fixture_app.py <sleep|echo|spin> [args...]", file=sys.stderr)
        sys.exit(1)

    command = sys.argv[1].lower()

    if command == "sleep":
        duration = float(sys.argv[2]) if len(sys.argv) > 2 else 10.0
        time.sleep(duration)
        sys.exit(0)

    elif command == "echo":
        message = " ".join(sys.argv[2:]) if len(sys.argv) > 2 else "hello"
        print(message)
        sys.exit(0)

    elif command == "spin":
        # Busy spin — used to test STOP/termination paths.
        # Will exit when the process receives SIGTERM or is killed via Job Object.
        while True:
            time.sleep(0.1)

    else:
        print(f"Unknown command: {command!r}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
