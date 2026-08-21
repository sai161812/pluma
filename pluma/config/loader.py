"""pluma.config.loader - Configuration loading and validation.

Loads the PLUMA configuration from the baseline defaults.yaml, then merges
any user overrides from %APPDATA%\\PLUMA\\user_settings.json (or a path
supplied via the PLUMA_CONFIG environment variable).

Spec Appendix A: configuration baseline.
Spec section 25: Use %%APPDATA%%\\PLUMA for user configuration.

Contract:
  - load_config() must not import any ML runtime (whisper, llama_cpp, paddle).
  - load_config() is safe to call at import time.
  - The returned dict is a plain Python dict; callers must not mutate it.

No OS-automation or ML code in this module.
"""

from __future__ import annotations

import json
import os
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

# The baseline defaults file lives next to this package.
_DEFAULTS_FILE = Path(__file__).parent / "defaults.yaml"


def _load_yaml(path: Path) -> Dict[str, Any]:
    with open(path, encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def _merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    """Deep-merge *override* into *base* (non-destructive; returns new dict)."""
    result = deepcopy(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _merge(result[key], value)
        else:
            result[key] = deepcopy(value)
    return result


def _user_config_path() -> Optional[Path]:
    """Return the user config file path, or None if not found.

    Search order:
      1. PLUMA_CONFIG environment variable (absolute path).
      2. %%APPDATA%%\\PLUMA\\user_settings.json
    """
    env_path = os.environ.get("PLUMA_CONFIG")
    if env_path:
        p = Path(env_path)
        if p.exists():
            return p

    appdata = os.environ.get("APPDATA")
    if appdata:
        p = Path(appdata) / "PLUMA" / "user_settings.json"
        if p.exists():
            return p

    return None


def load_config() -> Dict[str, Any]:
    """Load and return the merged PLUMA configuration.

    Returns a deep copy so callers cannot mutate the shared defaults.
    Raises FileNotFoundError if defaults.yaml is missing.
    Raises yaml.YAMLError / json.JSONDecodeError on parse failures.
    Does NOT import any ML library.
    """
    config = _load_yaml(_DEFAULTS_FILE)

    user_path = _user_config_path()
    if user_path is not None:
        if user_path.suffix == ".json":
            with open(user_path, encoding="utf-8") as fh:
                overrides = json.load(fh)
        else:
            overrides = _load_yaml(user_path)
        config = _merge(config, overrides)

    return config


def get(config: Dict[str, Any], *keys: str, default: Any = None) -> Any:
    """Safely traverse nested config keys.

    Example:
        get(cfg, "agent", "max_plan_steps", default=8)
    """
    cur = config
    for key in keys:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(key, default)
    return cur
