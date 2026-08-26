"""pluma.tools.base — ToolSpec, ToolResult, RiskClass, AdapterPriority.

Every real action in PLUMA is a registered ToolSpec. This module defines
the contract types used by the registry, policy engine, executor, verifier,
rollback engine, and Activity Ledger.

Spec §11: "A tool is a contract used by the router, planner, policy engine,
Task Supervisor, verifier, Activity Ledger and tests."

No OS-automation, ML, or adapter code in this module.
"""

from __future__ import annotations

from enum import Enum, IntEnum
from typing import Any, Callable, Dict, List, Optional, Type

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Risk classification
# ---------------------------------------------------------------------------

class RiskClass(str, Enum):
    """Policy risk tier for a tool call.

    Spec §14 table:
      READ   — inspect only; no state change.
      LOW    — low-impact state change; allow + log + verify.
      MEDIUM — moderate impact; requires explicit user request + undo capture.
      HIGH   — significant / hard-to-reverse; requires material-effect confirmation.
      ADMIN  — needs elevation; one-operation UAC only.
      DENY   — operation not permitted or not safely groundable.
    """
    READ = "READ"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    ADMIN = "ADMIN"
    RESTRICTED = "RESTRICTED"
    DENY = "DENY"


# ---------------------------------------------------------------------------
# Adapter priority order
# ---------------------------------------------------------------------------

class AdapterPriority(IntEnum):
    """Spec §11.1 adapter preference order (lower = preferred)."""
    NATIVE_API = 1          # Win32 / application API
    POWERSHELL = 2          # Controlled PowerShell/CLI wrapper
    UIA = 3                 # Windows UI Automation / pywinauto
    KEYBOARD = 4            # SendInput / stable shortcuts
    OCR_GROUNDED = 5        # OCR-based window-relative interaction
    RAW_COORDINATE = 6      # Last resort: validated fresh snapshot coordinate


# ---------------------------------------------------------------------------
# ToolSpec — the contract for one registered tool
# ---------------------------------------------------------------------------

class ToolSpec(BaseModel):
    """Complete contract for one PLUMA tool.

    Spec §11 ToolSpec fields:
      name, description, args_schema, risk_class, timeout_s,
      executor, verifier, undo_builder?, adapter_priority[], cancellable,
      creates_resources?

    Callables (executor, verifier, undo_builder) are stored as references and
    not serialised to JSON — only the registry needs them at runtime. The ledger
    stores the tool name and sanitised arguments, not the callable itself.
    """

    model_config = {"arbitrary_types_allowed": True}

    # Identity
    name: str = Field(
        min_length=1,
        max_length=64,
        pattern=r"^[a-z][a-z0-9_]*$",
        description="Snake_case tool identifier. Must be unique in the registry.",
    )
    description: str = Field(
        min_length=1,
        max_length=256,
        description="One-sentence human-readable description of what the tool does.",
    )
    version: str = Field(default="1.0", pattern=r"^\d+\.\d+$")

    # Schema for argument validation. A Pydantic model class or a JSON Schema dict.
    args_schema: Any = Field(
        description=(
            "Pydantic model class or JSON Schema dict for argument validation. "
            "Used by the registry before policy and execution."
        )
    )

    # Risk and policy
    risk_class: RiskClass

    # Execution contract
    timeout_s: float = Field(gt=0, le=300, description="Hard wall-clock timeout in seconds.")
    executor: Callable[..., "ToolResult"] = Field(
        description="Callable that performs the action. Injected by the adapter layer."
    )
    verifier: Callable[["ToolResult"], "VerifyResult"] = Field(
        description="Callable that reads back state and confirms postcondition."
    )
    undo_builder: Optional[Callable[..., Dict[str, Any]]] = Field(
        default=None,
        description=(
            "Callable that captures pre-state before execution and returns an undo record. "
            "None for non-reversible operations."
        ),
    )

    # Adapter selection
    adapter_priority: List[AdapterPriority] = Field(
        default_factory=lambda: [AdapterPriority.NATIVE_API],
        description="Preferred adapter order. Registry retries in declared sequence.",
    )

    # Cancellation
    cancellable: bool = Field(
        default=True,
        description="Whether this tool respects the task cancellation token.",
    )

    # Resource tracking
    creates_resources: bool = Field(
        default=False,
        description="True if this tool may create task-owned resources (temp files, tabs, etc.).",
    )


# ---------------------------------------------------------------------------
# ToolResult — what the executor returns
# ---------------------------------------------------------------------------

class VerifyResult(BaseModel):
    """Result of a postcondition verification check."""
    model_config = {"frozen": True}

    ok: bool
    method: str = Field(description="How the state was read back: 'api', 'uia', 'ocr', 'state'.")
    detail: str = Field(description="Factual one-liner about what was checked and found.")
    duration_ms: Optional[float] = None


class ToolResult(BaseModel):
    """What the executor returns after running one tool call.

    Spec §11 ToolResult fields:
      ok, tool, data, factual_message, verified, duration_ms, error?, undo_record?

    factual_message must come from a deterministic template, never from the LLM.
    Spec §16.4: "User-visible Activity messages must be generated from deterministic
    templates owned by the executor, not by the LLM."
    """

    model_config = {"frozen": True, "arbitrary_types_allowed": True}

    ok: bool
    tool: str = Field(description="Tool name from ToolSpec.name.")
    data: Dict[str, Any] = Field(
        default_factory=dict,
        description="Structured output from the tool. Schema is tool-specific.",
    )
    factual_message: str = Field(
        description=(
            "Concise, deterministic, template-generated result text. "
            "Examples: 'Opened Notepad', 'Moved 1 file', 'Volume set to 30%'."
        )
    )
    verified: bool = Field(
        default=False,
        description="True only when the verifier confirmed the postcondition.",
    )
    verify_detail: Optional[Any] = None
    duration_ms: Optional[float] = None
    adapter_used: Optional[str] = None
    error: Optional[str] = None                 # Factual error message.
    error_code: Optional[str] = None            # Machine-readable error class.
    undo_record: Optional[Dict[str, Any]] = None  # Pre-state for rollback.

    @classmethod
    def success(
        cls,
        tool: str,
        data: Optional[Dict[str, Any]] = None,
        factual_message: str = "",
        verified: bool = True,
        verify_detail: Optional[VerifyResult] = None,
        duration_ms: Optional[float] = None,
        adapter_used: Optional[str] = None,
        undo_record: Optional[Dict[str, Any]] = None,
    ) -> "ToolResult":
        """Convenience constructor for a successful tool result."""
        return cls(
            ok=True,
            tool=tool,
            data=data or {},
            factual_message=factual_message or f"Executed {tool} successfully.",
            verified=verified,
            verify_detail=verify_detail,
            duration_ms=duration_ms,
            adapter_used=adapter_used,
            undo_record=undo_record,
        )

    @classmethod
    def failure(
        cls,
        tool: str,
        error: str,
        error_code: str = "TOOL_FAILED",
        duration_ms: Optional[float] = None,
        adapter_used: Optional[str] = None,
    ) -> "ToolResult":
        """Convenience constructor for a failed tool result."""
        return cls(
            ok=False,
            tool=tool,
            factual_message=f"Failed: {error}",
            error=error,
            error_code=error_code,
            duration_ms=duration_ms,
            adapter_used=adapter_used,
        )
