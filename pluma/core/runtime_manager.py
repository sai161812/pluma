"""pluma.core.runtime_manager — Heavy-runtime lifecycle manager (stub).

Spec §4: Runtime states and elastic intelligence.
LLM, STT, OCR workers are cold at startup and load on demand.
Implemented in Phase 9 (planner lifecycle) and Phase 6 (STT lifecycle).
"""


class RuntimeManager:
    """Stub: manages STT/OCR/planner warm/cold lifecycle."""

    def ensure_idle(self) -> None:
        """Ensure all heavy runtimes are cold. Call at startup."""
        # Phase 0: nothing to unload. This is a verified no-op.
        pass
