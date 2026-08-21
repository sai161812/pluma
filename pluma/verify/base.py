"""pluma.verify.base — Verifier abstract base class.

Spec §15: "No state-changing tool may report success only because the call
returned without an exception. The tool defines a postcondition and reads the
state back using the strongest method available."

Each ToolSpec carries a verifier callable. That callable must return a
VerifyResult (defined in pluma.tools.base). This module provides the abstract
base class that all concrete verifiers should implement.

No OS-automation or ML code in this module.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pluma.tools.base import ToolResult, VerifyResult


class Verifier(ABC):
    """Abstract base class for tool postcondition verifiers.

    Subclasses are registered as the `verifier` field on a ToolSpec.
    The executor calls verify() after the tool returns and before writing
    the final ledger record.

    A verifier must:
      - Read state back using the strongest available method (API > UIA > OCR).
      - Return a VerifyResult with ok=True only when the postcondition is met.
      - Never return ok=True based solely on "no exception was raised".
      - Set a factual detail string describing what was checked and what was found.
    """

    @abstractmethod
    def verify(self, result: "ToolResult") -> "VerifyResult":
        """Check the postcondition of the action described by *result*.

        Args:
            result: The ToolResult returned by the executor. May contain
                    structured data fields that the verifier uses to know
                    what to check (e.g. the file path that was moved).

        Returns:
            A VerifyResult with ok, method, detail and optional duration_ms.
        """
        ...

    def __call__(self, result: "ToolResult") -> "VerifyResult":
        """Allow verifier instances to be used as callables (matches ToolSpec.verifier type)."""
        return self.verify(result)


class NoopVerifier(Verifier):
    """Verifier for read-only tools that produce no state change to verify.

    Spec §14: READ-class tools are allowed and logged. There is no postcondition
    to check beyond "the call completed".

    Must only be used on tools with risk_class=READ. Any tool that changes
    state must use a real verifier.
    """

    def verify(self, result: "ToolResult") -> "VerifyResult":
        from pluma.tools.base import VerifyResult
        return VerifyResult(
            ok=result.ok,
            method="none",
            detail="Read-only operation; no state postcondition to verify.",
        )
