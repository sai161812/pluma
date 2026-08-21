"""pluma.adapters.input — Keyboard and mouse input adapter (stub).

Spec §13: Input adapter wraps SendInput behind an interface; imported lazily.
Implemented in Phase 4.
Boundary: must not import SendInput or low-level input libs at module level.
"""


class InputAdapter:
    """Stub: Keyboard and mouse input adapter. Implemented in Phase 4."""

    def send_input(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        raise NotImplementedError("InputAdapter not implemented until Phase 4.")
