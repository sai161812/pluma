r"""pluma.config.paths — Standardized Windows storage and filesystem hierarchy.

Spec §20, §25:
- %LOCALAPPDATA%\Pluma\
    data\pluma.db
    models\ (llm\, whisper\, ocr\)
    cache\
    logs\
    temp\task_<id>\
- %APPDATA%\Pluma\
    user_settings.json
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional


class PlumaPaths:
    """Resolves and manages standard Windows directory hierarchies for PLUMA."""

    def __init__(
        self,
        local_app_data: Optional[Path | str] = None,
        roaming_app_data: Optional[Path | str] = None,
    ) -> None:
        # Resolve base %LOCALAPPDATA%
        if local_app_data is not None:
            self._local_root = Path(local_app_data)
        elif "PLUMA_LOCALAPPDATA" in os.environ:
            self._local_root = Path(os.environ["PLUMA_LOCALAPPDATA"])
        elif "LOCALAPPDATA" in os.environ:
            self._local_root = Path(os.environ["LOCALAPPDATA"]) / "Pluma"
        else:
            # Fallback for non-Windows / CI environments
            self._local_root = Path.home() / ".local" / "share" / "Pluma"

        # Resolve base %APPDATA% (Roaming)
        if roaming_app_data is not None:
            self._roaming_root = Path(roaming_app_data)
        elif "PLUMA_APPDATA" in os.environ:
            self._roaming_root = Path(os.environ["PLUMA_APPDATA"])
        elif "APPDATA" in os.environ:
            self._roaming_root = Path(os.environ["APPDATA"]) / "Pluma"
        else:
            self._roaming_root = Path.home() / ".config" / "Pluma"

    # ------------------------------------------------------------------
    # Directory Properties
    # ------------------------------------------------------------------

    @property
    def local_root(self) -> Path:
        r"""Root directory under %LOCALAPPDATA%\Pluma."""
        return self._local_root

    @property
    def roaming_root(self) -> Path:
        r"""Root directory under %APPDATA%\Pluma."""
        return self._roaming_root

    @property
    def data_dir(self) -> Path:
        """Directory containing SQLite database files."""
        if "PLUMA_DATA_DIR" in os.environ:
            return Path(os.environ["PLUMA_DATA_DIR"])
        return self._local_root / "data"

    @property
    def db_path(self) -> Path:
        """Primary SQLite database file path."""
        return self.data_dir / "pluma.db"

    @property
    def models_dir(self) -> Path:
        """Root directory for ML model weights."""
        if "PLUMA_MODELS_DIR" in os.environ:
            return Path(os.environ["PLUMA_MODELS_DIR"])
        return self._local_root / "models"

    @property
    def llm_models_dir(self) -> Path:
        """Directory for GGUF local planner models."""
        return self.models_dir / "llm"

    @property
    def whisper_models_dir(self) -> Path:
        """Directory for Whisper STT model weights."""
        return self.models_dir / "whisper"

    @property
    def ocr_models_dir(self) -> Path:
        """Directory for PaddleOCR / ONNX models."""
        return self.models_dir / "ocr"

    @property
    def logs_dir(self) -> Path:
        """Directory for structured log files."""
        if "PLUMA_LOG_DIR" in os.environ:
            return Path(os.environ["PLUMA_LOG_DIR"])
        return self._local_root / "logs"

    @property
    def cache_dir(self) -> Path:
        """Directory for ephemeral cache files."""
        if "PLUMA_CACHE_DIR" in os.environ:
            return Path(os.environ["PLUMA_CACHE_DIR"])
        return self._local_root / "cache"

    @property
    def temp_dir(self) -> Path:
        """Root directory for per-task temporary workspaces."""
        if "PLUMA_TEMP_DIR" in os.environ:
            return Path(os.environ["PLUMA_TEMP_DIR"])
        return self._local_root / "temp"

    @property
    def user_settings_path(self) -> Path:
        """Path to user_settings.json configuration override file."""
        return self._roaming_root / "user_settings.json"

    # ------------------------------------------------------------------
    # Task-Specific Helpers
    # ------------------------------------------------------------------

    def task_temp_dir(self, task_id: str) -> Path:
        """Get or create isolated scratch directory for a specific task."""
        safe_task_id = "".join(c for c in task_id if c.isalnum() or c in ("-", "_"))
        return self.temp_dir / f"task_{safe_task_id}"

    def ensure_directories(self) -> None:
        """Ensure all required standard directory structures exist on disk."""
        dirs = [
            self.data_dir,
            self.models_dir,
            self.llm_models_dir,
            self.whisper_models_dir,
            self.ocr_models_dir,
            self.logs_dir,
            self.cache_dir,
            self.temp_dir,
            self._roaming_root,
        ]
        for d in dirs:
            d.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Process-wide Singleton
# ---------------------------------------------------------------------------

_default_paths: Optional[PlumaPaths] = None


def get_paths() -> PlumaPaths:
    """Get process-wide default PlumaPaths instance."""
    global _default_paths
    if _default_paths is None:
        _default_paths = PlumaPaths()
    return _default_paths


def set_paths(paths: Optional[PlumaPaths]) -> None:
    """Override or reset process-wide PlumaPaths instance."""
    global _default_paths
    _default_paths = paths
