"""pluma.memory.aliases — User-defined command alias store (stub).

Spec §18: Aliases are persisted in the SQLite Activity Ledger database.
Implemented in Phase 2.
"""


class AliasStore:
    """Stub: SQLite-backed user alias store. Implemented in Phase 2."""

    def get(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        raise NotImplementedError("AliasStore not implemented until Phase 2.")

    def set(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        raise NotImplementedError("AliasStore not implemented until Phase 2.")
