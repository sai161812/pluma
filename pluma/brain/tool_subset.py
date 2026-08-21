"""pluma.brain.tool_subset — Route-specific tool schema selector (stub).

Spec §10: "Never provide the model with ... all tool schemas by default."
Implemented in Phase 9. Uses ToolRegistry.schema_for_planner(names).
"""


class ToolSubsetSelector:
    """Stub: selects route-appropriate tool schemas. Implemented in Phase 9."""

    def select(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        raise NotImplementedError("ToolSubsetSelector not implemented until Phase 9.")
