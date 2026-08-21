"""pluma.adapters.uia — UI Automation (UIA/pywinauto) adapter (stub).

Spec §13: UIA adapter wraps pywinauto behind an interface; imported lazily.
Implemented in Phase 4.
Boundary: must not import pywinauto at module level.
"""


class UiaAdapter:
    """Stub: UIA/pywinauto automation adapter. Implemented in Phase 4."""

    def find_control(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        raise NotImplementedError("UiaAdapter not implemented until Phase 4.")
