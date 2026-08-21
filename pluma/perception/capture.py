"""pluma.perception.capture — Window/region screen capture (stub).

Spec §8.2: "Capture only when screen context is needed; no loop."
Implemented in Phase 8. Must NOT import capture library at module level.
"""


class WindowCapture:
    """Stub: target-window capture adapter. Implemented in Phase 8."""

    def capture_window(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        raise NotImplementedError("WindowCapture not implemented until Phase 8.")
