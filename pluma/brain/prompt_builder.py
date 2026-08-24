"""pluma.brain.prompt_builder — Route-specific prompt builder.

Spec §10: "Never provide the model with the complete desktop state,
full file tree, full Activity Ledger or all tool schemas by default."
Spec §16, Acceptance Test F-09: Sensitive context (passwords, tokens,
private clipboard) is excluded or redacted from prompts.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from pluma.brain.tool_subset import ToolSubsetSelector
from pluma.memory.redaction import redact_sensitive_data
from pluma.perception.element_refs import ScreenSnapshot

logger = logging.getLogger(__name__)

SYSTEM_PROMPT_TEMPLATE = """You are the PLUMA planning engine. Your job is to translate user commands into a structured plan using ONLY the permitted tools.

RULES:
1. Propose ONLY tools from the PERMITTED TOOLS list below. Never invent new tool names.
2. Every tool call MUST include all required arguments matching the tool schema.
3. Keep plans short, concise, and direct (max 20 steps).
4. Output MUST be valid JSON conforming exactly to the following Plan JSON schema:
{{
  "route": "SMART" | "SCREEN" | "DEEP",
  "mode": "direct" | "multi_step",
  "steps": [
    {{
      "tool": "<registered_tool_name>",
      "arguments": {{ ... }},
      "purpose": "<short reason for this step>"
    }}
  ]
}}
5. Do NOT include markdown code blocks, conversational text, explanations, or commentary. Output raw JSON only.

PERMITTED TOOLS:
{tools_description}
"""


class PromptBuilder:
    """Builds token-efficient, sanitized prompts for the local planner."""

    def __init__(self, subset_selector: Optional[ToolSubsetSelector] = None) -> None:
        self._subset_selector = subset_selector or ToolSubsetSelector()

    def build_system_prompt(self, permitted_tool_schemas: List[Dict[str, Any]]) -> str:
        """Construct the system prompt with permitted tool schemas."""
        tools_desc = self._subset_selector.format_tools_for_prompt(permitted_tool_schemas)
        if not tools_desc:
            tools_desc = "No tools permitted."
        return SYSTEM_PROMPT_TEMPLATE.format(tools_description=tools_desc)

    def build_user_prompt(
        self,
        command: str,
        context: Optional[Dict[str, Any]] = None,
        screen_snapshot: Optional[ScreenSnapshot] = None,
        prior_step_results: Optional[List[Dict[str, Any]]] = None,
    ) -> str:
        """Construct the user prompt with command, minimal context, and screen elements."""
        sanitized_cmd = str(redact_sensitive_data(command))
        sections = [f"USER COMMAND: {sanitized_cmd}"]

        # 1. Active window / process context
        if context:
            clean_context: Dict[str, Any] = {}
            for k, v in context.items():
                if k in ("active_process", "active_window_title", "current_dir", "cwd", "os"):
                    clean_context[k] = redact_sensitive_data(v)
            if clean_context:
                sections.append(f"CONTEXT: {json.dumps(clean_context)}")

        # 2. Screen perception elements (if available)
        if screen_snapshot and not screen_snapshot.is_expired:
            elem_summaries = []
            for c in screen_snapshot.controls[:30]:  # Limit to 30 controls to avoid token bloat
                elem_summaries.append(
                    f"[{c.control_type or 'Control'}] label='{c.label}' auto_id='{c.uia_automation_id or ''}'"
                )
            for w in screen_snapshot.ocr_words[:20]:  # Limit to 20 OCR words
                elem_summaries.append(f"[OCR] '{w.label}' (conf={w.confidence:.2f})")

            if elem_summaries:
                sections.append("VISIBLE SCREEN ELEMENTS:\n" + "\n".join(elem_summaries))

        # 3. Prior step results in multi-step execution
        if prior_step_results:
            step_lines = []
            for idx, res in enumerate(prior_step_results, start=1):
                tool = res.get("tool", "unknown")
                ok = res.get("ok", False)
                msg = res.get("factual_message", "")
                data = res.get("data", {})
                step_lines.append(f"Step {idx}: {tool} -> ok={ok}, message='{msg}', data={data}")
            sections.append("PRIOR STEP RESULTS:\n" + "\n".join(step_lines))

        sections.append("Produce JSON Plan:")
        return "\n\n".join(sections)
