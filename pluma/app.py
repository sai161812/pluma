"""pluma.app — PLUMA entry point.

Starts the resident core only. LLM, STT and OCR workers are never started
here. Implemented fully in Phase 1 (resident core).

Spec §25: 'Windows startup launches only the resident core.'
"""


import time

def main() -> None:
    """Start PLUMA resident core."""
    from pluma.core.resident import ResidentCore
    core = ResidentCore()
    core.start()
    try:
        # Keep the main thread alive while background threads do the work.
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        core.stop()

if __name__ == "__main__":
    main()
