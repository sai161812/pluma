"""pluma.adapters.win32 — Win32 API adapter (stub).

Spec §13: Win32 adapter wraps pywin32/ctypes behind an interface; imported lazily.
Implemented in Phase 4.
Boundary: must not import pywin32 or ctypes at module level.
"""


class Win32Adapter:
    """Stub: Win32 API adapter. Implemented in Phase 4."""

    def call(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        raise NotImplementedError("Win32Adapter not implemented until Phase 4.")
