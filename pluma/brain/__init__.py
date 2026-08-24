"""pluma.brain — Local planner interface, llama.cpp adapter, lifecycle, and schemas."""

from pluma.brain.interface import (
    PlannerCancelledError,
    PlannerError,
    PlannerInterface,
    PlannerTimeoutError,
)
from pluma.brain.lifecycle import (
    LlmLifecycleManager,
    LlmLifecycleState,
    get_default_llm_lifecycle_manager,
    set_default_llm_lifecycle_manager,
)
from pluma.brain.llama_cpp_adapter import (
    LlamaCppAdapter,
    LlamaCppBackend,
)
from pluma.brain.prompt_builder import PromptBuilder
from pluma.brain.schemas import (
    MAX_PLAN_STEPS_HARD_CAP,
    Plan,
    PlanMode,
    RouteMode,
    ToolCall,
)
from pluma.brain.tool_subset import (
    APP_WINDOW_TOOLS,
    FILE_TOOLS,
    ROUTE_TOOL_MAP,
    SYSTEM_CLIPBOARD_TOOLS,
    UI_PERCEPTION_TOOLS,
    ToolSubsetSelector,
)
from pluma.brain.validator import PlanValidationError, PlanValidator

__all__ = [
    # Interfaces & Errors
    "PlannerInterface",
    "PlannerError",
    "PlannerTimeoutError",
    "PlannerCancelledError",
    # Adapters & Lifecycle
    "LlamaCppAdapter",
    "LlamaCppBackend",
    "LlmLifecycleManager",
    "LlmLifecycleState",
    "get_default_llm_lifecycle_manager",
    "set_default_llm_lifecycle_manager",
    # Prompt & Subsets
    "PromptBuilder",
    "ToolSubsetSelector",
    "FILE_TOOLS",
    "APP_WINDOW_TOOLS",
    "UI_PERCEPTION_TOOLS",
    "SYSTEM_CLIPBOARD_TOOLS",
    "ROUTE_TOOL_MAP",
    # Validation & Schemas
    "PlanValidator",
    "PlanValidationError",
    "MAX_PLAN_STEPS_HARD_CAP",
    "Plan",
    "PlanMode",
    "RouteMode",
    "ToolCall",
]
