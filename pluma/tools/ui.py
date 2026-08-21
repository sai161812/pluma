"""pluma.tools.ui — UI interaction tools (stub).

Spec §12: UI interactions are registered ToolSpecs; pywinauto imported lazily via UiaAdapter.
Implemented in Phase 4.
Boundary: must not import pywinauto at module level.
"""


class UiInteractionTools:
    """Stub: UI click, type, and read tools via UIA/pywinauto adapter. Implemented in Phase 4."""

    def execute(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        raise NotImplementedError("UiInteractionTools not implemented until Phase 4.")
