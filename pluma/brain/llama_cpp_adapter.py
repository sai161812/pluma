"""pluma.brain.llama_cpp_adapter — llama.cpp planner adapter (stub).

Spec §10: "Runtime baseline: llama.cpp launched locally through a replaceable adapter."
PLUMA_TECH_STACK.md: "Planner model: Qwen3-4B GGUF Q4_K_M (initial benchmark)."
Must NOT import llama_cpp at module level (idle runtime law).
Implemented in Phase 9.
"""

from pluma.brain.interface import PlannerInterface


class LlamaCppAdapter(PlannerInterface):
    """Stub: llama.cpp planner adapter. Implemented in Phase 9."""

    def plan(self, *args, **kwargs):  # type: ignore[no-untyped-def, override]
        raise NotImplementedError("LlamaCppAdapter not implemented until Phase 9.")
