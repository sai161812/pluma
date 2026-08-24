"""pluma.policy.rules — Policy rule definitions and risk classification.

Spec §14, §15:
- Rules classify ToolCalls into risk classes: READ, LOW, HIGH, RESTRICTED.
- Critical system directories and destructive commands are classified as RESTRICTED.
- Supports per-tool risk overrides from YAML configuration.
"""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Union

import yaml

from pluma.tools.base import RiskClass

logger = logging.getLogger(__name__)

# Protected Windows system paths where destructive or write operations are strictly RESTRICTED
_DEFAULT_PROTECTED_PATH_PATTERNS = [
    re.compile(r"^[a-zA-Z]:\\windows(\\.*)?$", re.IGNORECASE),
    re.compile(r"^[a-zA-Z]:\\program files\\windows defender(\\.*)?$", re.IGNORECASE),
    re.compile(r"^[a-zA-Z]:\\boot(\\.*)?$", re.IGNORECASE),
    re.compile(r"^[a-zA-Z]:\\system volume information(\\.*)?$", re.IGNORECASE),
    re.compile(r"^[a-zA-Z]:\\(pagefile\.sys|hiberfil\.sys|swapfile\.sys)$", re.IGNORECASE),
]

# Destructive shell patterns that are strictly RESTRICTED
_RESTRICTED_COMMAND_PATTERNS = [
    re.compile(r"\bformat\s+[a-zA-Z]:", re.IGNORECASE),
    re.compile(r"\bbcdedit\b", re.IGNORECASE),
    re.compile(r"\breg\s+delete\s+hklm\\(sam|security|system)\b", re.IGNORECASE),
    re.compile(r"\bvssadmin\s+delete\s+shadows\b", re.IGNORECASE),
    re.compile(r"\brmdir\s+/[sq]\s+/[sq]\s+[a-zA-Z]:\\?(windows)?\b", re.IGNORECASE),
    re.compile(r"\bdel\s+/[sqfa]\s+[a-zA-Z]:\\windows\b", re.IGNORECASE),
    re.compile(r"\bSet-ExecutionPolicy\s+.*Bypass\s+-Scope\s+LocalMachine\b", re.IGNORECASE),
]


class PolicyRules:
    """Classifies tool invocations into risk classes and detects restricted operations."""

    def __init__(
        self,
        config_path: Optional[Union[str, Path]] = None,
        overrides: Optional[Dict[str, str]] = None,
    ) -> None:
        self._overrides: Dict[str, RiskClass] = {}
        if overrides:
            for k, v in overrides.items():
                try:
                    self._overrides[k] = RiskClass(v.upper())
                except ValueError:
                    logger.warning("Invalid risk class override for %s: %s", k, v)

        if config_path and os.path.exists(config_path):
            self._load_config(config_path)

    def _load_config(self, config_path: Union[str, Path]) -> None:
        """Load per-tool risk class overrides from YAML file."""
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
                if isinstance(data, dict):
                    for tool_name, risk_str in data.items():
                        if isinstance(risk_str, str):
                            try:
                                self._overrides[tool_name] = RiskClass(risk_str.upper())
                            except ValueError:
                                logger.warning("Invalid risk class in config for %s: %s", tool_name, risk_str)
        except Exception as exc:
            logger.warning("Failed to load tool policy overrides from %s: %s", config_path, exc)

    def is_protected_path(self, path_str: str) -> bool:
        """Check if a path targets a critical Windows system location."""
        norm_path = os.path.normpath(str(path_str)).strip()
        for pat in _DEFAULT_PROTECTED_PATH_PATTERNS:
            if pat.match(norm_path):
                return True
        return False

    def contains_restricted_command(self, script_or_cmd: str) -> bool:
        """Check if a command string contains prohibited shell expressions."""
        for pat in _RESTRICTED_COMMAND_PATTERNS:
            if pat.search(script_or_cmd):
                return True
        return False

    def classify(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        default_risk: RiskClass = RiskClass.LOW,
    ) -> RiskClass:
        """Classify the risk tier of a tool call considering arguments and system boundaries."""
        # 1. Check for protected system path access in arguments
        for k, v in arguments.items():
            if isinstance(v, str) and ("\\" in v or "/" in v or ":" in v):
                if self.is_protected_path(v):
                    logger.warning(
                        "Tool '%s' targets protected system path '%s' -> RESTRICTED",
                        tool_name, v,
                    )
                    return RiskClass.RESTRICTED

            # Check shell command strings
            if isinstance(v, str) and (" " in v or ";" in v or "|" in v):
                if self.contains_restricted_command(v):
                    logger.warning(
                        "Tool '%s' contains restricted shell command '%s' -> RESTRICTED",
                        tool_name, v[:80],
                    )
                    return RiskClass.RESTRICTED

        # 2. Check explicit tool overrides
        if tool_name in self._overrides:
            return self._overrides[tool_name]

        # 3. Default tool risk class
        return default_risk
