"""tests/unit/test_router.py — Phase 3: Deterministic Router tests.

Validates all 22 golden commands from tests/fixtures/golden_commands.yaml:
  - Route classification matches expected_route.
  - Plan tool(s) match expected_tools for FAST routes.
  - no_llm commands: no LLM module is in sys.modules after routing.
  - Voice and text produce the same route for matching commands.
  - Voice number words (e.g. 'twenty') resolve to correct integer levels.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, List

import pytest
import yaml

from pluma.core.request import InputMode, PlumaRequest
from pluma.core.router import Router, RouteResult, _parse_number
from pluma.brain.schemas import RouteMode

# ---------------------------------------------------------------------------
# Golden corpus loader
# ---------------------------------------------------------------------------

FIXTURE_PATH = Path(__file__).parent.parent / "fixtures" / "golden_commands.yaml"

_GOLDEN_COMMANDS: List[Dict[str, Any]] = []

if FIXTURE_PATH.exists():
    with FIXTURE_PATH.open("r", encoding="utf-8") as fh:
        _data = yaml.safe_load(fh)
    _GOLDEN_COMMANDS = _data.get("commands", [])


def _golden(gc_id: str) -> Dict[str, Any]:
    for cmd in _GOLDEN_COMMANDS:
        if cmd["id"] == gc_id:
            return cmd
    raise KeyError(f"Golden command {gc_id!r} not found in fixture.")


def _make_request(command: str, mode: str = "text") -> PlumaRequest:
    return PlumaRequest(
        input_mode=InputMode.TEXT if mode == "text" else InputMode.VOICE,
        text=command,
        original_transcript=command if mode == "voice" else None,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

ML_MODULE_PREFIXES = ("torch", "tensorflow", "onnx", "transformers", "openai", "anthropic", "whisper")


def _assert_no_ml_loaded() -> None:
    for mod_name in list(sys.modules):
        for prefix in ML_MODULE_PREFIXES:
            assert not mod_name.startswith(prefix), (
                f"ML module '{mod_name}' was loaded during a no_llm FAST command!"
            )


# ---------------------------------------------------------------------------
# _parse_number unit tests
# ---------------------------------------------------------------------------

class TestParseNumber:
    def test_bare_integer(self) -> None:
        assert _parse_number(["30"]) == 30

    def test_word_number_single(self) -> None:
        assert _parse_number(["twenty"]) == 20

    def test_word_number_compound(self) -> None:
        assert _parse_number(["thirty", "five"]) == 35

    def test_word_number_in_phrase(self) -> None:
        assert _parse_number("forty two".split()) == 42

    def test_clamp_over_100(self) -> None:
        assert _parse_number(["110"]) == 100

    def test_negative_digit_string_extracts_digits(self) -> None:
        # The regex strips digits only; -5 extracts 5. No negative volumes in practice.
        assert _parse_number(["-5"]) == 5

    def test_unknown_word(self) -> None:
        assert _parse_number(["banana"]) is None

    def test_empty(self) -> None:
        assert _parse_number([]) is None


# ---------------------------------------------------------------------------
# Router unit tests — individual behaviours
# ---------------------------------------------------------------------------

class TestRouterPatterns:
    @pytest.fixture(autouse=True)
    def make_router(self) -> None:
        self.router = Router()

    def _route(self, text: str, mode: str = "text") -> RouteResult:
        return self.router.route(_make_request(text, mode))

    # --- Audio ---
    def test_mute_text(self) -> None:
        r = self._route("mute")
        assert r.route == RouteMode.FAST
        assert r.plan is not None
        assert r.plan.steps[0].tool == "mute"

    def test_unmute_text(self) -> None:
        r = self._route("unmute")
        assert r.route == RouteMode.FAST
        assert r.plan.steps[0].tool == "unmute"

    def test_volume_integer(self) -> None:
        r = self._route("volume 30")
        assert r.route == RouteMode.FAST
        assert r.plan.steps[0].tool == "set_volume"
        assert r.plan.steps[0].arguments["level"] == 30

    def test_volume_percent_phrase(self) -> None:
        r = self._route("set volume to 50 percent")
        assert r.route == RouteMode.FAST
        assert r.plan.steps[0].arguments["level"] == 50

    def test_volume_word_twenty(self) -> None:
        r = self._route("volume twenty", "voice")
        assert r.route == RouteMode.FAST
        assert r.plan.steps[0].arguments["level"] == 20

    def test_volume_word_thirty_five(self) -> None:
        r = self._route("volume thirty five")
        assert r.route == RouteMode.FAST
        assert r.plan.steps[0].arguments["level"] == 35

    # --- App launch ---
    def test_open_notepad(self) -> None:
        r = self._route("open notepad")
        assert r.route == RouteMode.FAST
        assert r.plan.steps[0].tool == "open_app"

    def test_open_calculator(self) -> None:
        r = self._route("open calculator")
        assert r.route == RouteMode.FAST
        assert r.plan.steps[0].arguments["app_name"] == "calc"

    def test_launch_notepad(self) -> None:
        r = self._route("launch notepad")
        assert r.route == RouteMode.FAST
        assert r.plan.steps[0].tool == "open_app"

    def test_close_app(self) -> None:
        r = self._route("close notepad")
        assert r.route == RouteMode.FAST
        assert r.plan.steps[0].tool == "close_app"

    def test_focus_app(self) -> None:
        r = self._route("focus notepad")
        assert r.route == RouteMode.FAST
        assert r.plan.steps[0].tool == "focus_app"

    # --- Window state ---
    def test_minimize_window(self) -> None:
        r = self._route("minimize window")
        assert r.route == RouteMode.FAST
        assert r.plan.steps[0].tool == "minimize_window"

    def test_maximize_window(self) -> None:
        r = self._route("maximize window")
        assert r.route == RouteMode.FAST
        assert r.plan.steps[0].tool == "maximize_window"

    def test_list_windows(self) -> None:
        r = self._route("list windows")
        assert r.route == RouteMode.FAST
        assert r.plan.steps[0].tool == "list_windows"

    # --- System / activity ---
    def test_show_activity(self) -> None:
        r = self._route("show activity")
        assert r.route == RouteMode.FAST
        assert r.plan.steps[0].tool == "show_activity"

    def test_system_status(self) -> None:
        r = self._route("system status")
        assert r.route == RouteMode.FAST
        assert r.plan.steps[0].tool == "get_system_status"

    def test_battery_status(self) -> None:
        r = self._route("battery status")
        assert r.route == RouteMode.FAST
        assert r.plan.steps[0].tool == "battery_status"

    def test_list_apps(self) -> None:
        r = self._route("list apps")
        assert r.route == RouteMode.FAST
        assert r.plan.steps[0].tool == "list_apps"

    # --- Clipboard ---
    def test_clear_clipboard(self) -> None:
        r = self._route("clear clipboard")
        assert r.route == RouteMode.FAST
        assert r.plan.steps[0].tool == "clipboard_clear"

    def test_clipboard_clear_phrase(self) -> None:
        r = self._route("clipboard clear")
        assert r.route == RouteMode.FAST

    # --- Control ---
    def test_stop(self) -> None:
        r = self._route("stop")
        assert r.route == RouteMode.FAST
        assert r.plan.steps[0].tool == "stop_current"

    def test_undo(self) -> None:
        r = self._route("undo")
        assert r.route == RouteMode.FAST
        assert r.plan.steps[0].tool == "undo_last"

    # --- SCREEN route ---
    def test_click_submit_screen(self) -> None:
        r = self._route("click submit")
        assert r.route == RouteMode.SCREEN

    def test_click_ok_screen(self) -> None:
        r = self._route("click OK on this screen")
        assert r.route == RouteMode.SCREEN

    # --- SMART route ---
    def test_temporal_file_smart(self) -> None:
        r = self._route("move the PDF I downloaded yesterday to my Documents folder")
        assert r.route == RouteMode.SMART

    def test_latest_screenshot_smart(self) -> None:
        r = self._route("rename the latest screenshot to project_demo")
        assert r.route == RouteMode.SMART

    def test_delete_all_smart(self) -> None:
        r = self._route("delete all files in temp folder")
        assert r.route == RouteMode.SMART

    # --- Voice/text parity ---
    def test_mute_voice_same_route(self) -> None:
        r_text = self._route("mute", "text")
        r_voice = self._route("mute", "voice")
        assert r_text.route == r_voice.route
        assert r_text.plan.steps[0].tool == r_voice.plan.steps[0].tool


# ---------------------------------------------------------------------------
# Golden corpus: all 22 commands
# ---------------------------------------------------------------------------

class TestGoldenCorpus:
    """Validate every golden command against the Router.

    FAST commands: route matches, first tool matches, no ML loaded.
    SCREEN/SMART commands: only route checked (plan is None or deferred).
    """

    @pytest.fixture(autouse=True)
    def make_router(self) -> None:
        self.router = Router()

    @pytest.mark.parametrize("entry", _GOLDEN_COMMANDS, ids=[c["id"] for c in _GOLDEN_COMMANDS])
    def test_golden_command(self, entry: Dict[str, Any]) -> None:
        gc_id = entry["id"]
        text = entry["command"]
        mode = entry.get("input_mode", "text")
        expected_route = RouteMode(entry["expected_route"])
        expected_tools: List[str] = entry["expected_tools"]
        no_llm: bool = entry.get("no_llm", False)

        req = _make_request(text, mode)
        result = self.router.route(req)

        assert result.route == expected_route, (
            f"{gc_id}: expected route {expected_route.value}, got {result.route.value}. "
            f"reason: {result.reason}"
        )

        # For FAST: verify plan and first tool
        if expected_route == RouteMode.FAST:
            assert result.plan is not None, f"{gc_id}: FAST route must produce a Plan"
            assert len(result.plan.steps) >= 1, f"{gc_id}: Plan must have at least one step"
            actual_first_tool = result.plan.steps[0].tool
            assert actual_first_tool == expected_tools[0], (
                f"{gc_id}: expected first tool {expected_tools[0]!r}, got {actual_first_tool!r}"
            )

        if no_llm:
            _assert_no_ml_loaded()
