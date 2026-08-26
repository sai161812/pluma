"""pluma.core.router — Deterministic intent router.

Spec §9: Route selection rules.
  FAST   — deterministic: no LLM, no OCR.
  SCREEN — UIA ± targeted OCR, no LLM if target unambiguous.
  SMART  — small local planner + tools for complex/ambiguous commands.
  DEEP   — planner + UIA + OCR + bounded multi-step.

The Router is the gatekeeper that decides which path is taken. It must:
  1. Classify high-confidence commands to FAST without loading any model.
  2. Produce a fully-resolved typed Plan (list of ToolCalls) for FAST commands.
  3. Annotate the route decision with a human-readable reason for the ledger.
  4. Treat voice and text commands identically (Spec §3, non-negotiable law 3).

No ML, OS-automation, or adapter code in this module.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Union

from pluma.brain.schemas import Plan, PlanMode, RouteMode, ToolCall
from pluma.core.request import PlumaRequest


# ---------------------------------------------------------------------------
# Spoken-number word-to-integer table
# ---------------------------------------------------------------------------

_WORD_NUMBERS: Dict[str, int] = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15,
    "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19,
    "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50,
    "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90,
    "hundred": 100,
}

_TENS = {"twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety"}


def _parse_number(tokens: List[str]) -> Optional[int]:
    """Convert a token list (e.g. ['thirty', 'five'] or ['35']) to an int.

    Returns None if no valid number found.
    Supports: bare digits, single word-numbers, tens + unit (e.g. twenty five).
    Clamps the result to [0, 100].
    """
    s = " ".join(tokens)
    # Bare digit(s)
    m = re.search(r"\b(\d+)\b", s)
    if m:
        return max(0, min(100, int(m.group(1))))

    # Word number(s)
    parts = s.lower().split()
    total = 0
    found = False
    i = 0
    while i < len(parts):
        w = parts[i]
        if w in _WORD_NUMBERS:
            found = True
            val = _WORD_NUMBERS[w]
            if w in _TENS and i + 1 < len(parts) and parts[i + 1] in _WORD_NUMBERS:
                val += _WORD_NUMBERS[parts[i + 1]]
                i += 1
            total += val
        i += 1
    if found:
        return max(0, min(100, total))
    return None


# ---------------------------------------------------------------------------
# RouteResult
# ---------------------------------------------------------------------------

@dataclass
class RouteResult:
    """Output of the Router for one request.

    Attributes:
        route:      The resolved route mode (FAST / SCREEN / SMART / DEEP).
        reason:     Short factual explanation for the ledger.
        plan:       Fully resolved Plan for FAST commands; None for other routes.
        confidence: Float 0.0–1.0 indicating match quality.
    """
    route: RouteMode
    reason: str
    plan: Optional[Plan] = None
    confidence: float = 1.0


# ---------------------------------------------------------------------------
# Known application name normalization
# ---------------------------------------------------------------------------

_APP_ALIASES: Dict[str, str] = {
    "notepad": "notepad",
    "notepad++": "notepad++",
    "calc": "calc",
    "calculator": "calc",
    "paint": "mspaint",
    "mspaint": "mspaint",
    "word": "winword",
    "excel": "excel",
    "powerpoint": "powerpnt",
    "explorer": "explorer",
    "file explorer": "explorer",
    "cmd": "cmd",
    "command prompt": "cmd",
    "powershell": "powershell",
    "terminal": "wt",
    "windows terminal": "wt",
    "edge": "msedge",
    "chrome": "chrome",
    "firefox": "firefox",
    "vlc": "vlc",
    "spotify": "spotify",
    "teams": "teams",
    "outlook": "outlook",
    "discord": "discord",
    "vs code": "code",
    "vscode": "code",
    "visual studio code": "code",
    "task manager": "taskmgr",
    "taskmgr": "taskmgr",
    "settings": "ms-settings:",
    "control panel": "control",
    "clock": "clock",
    "camera": "microsoft.windows.camera:",
    "photos": "ms-photos:",
}


def _normalise_app_name(raw: str) -> str:
    """Resolve common app aliases to executable names."""
    return _APP_ALIASES.get(raw.lower().strip(), raw.strip())


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

class Router:
    """Deterministic route classifier and FAST plan builder.

    The router inspects the normalised command text using ordered regex rules.
    Rules are evaluated in priority order. The first matching rule wins.
    No model, no screen scan, no subprocess is started in this class.
    """

    def __init__(self) -> None:
        # Pre-compile patterns in priority order for FAST classification.
        self._fast_rules: List[Tuple[re.Pattern[str], str]] = [
            # --- STOP / UNDO (highest priority) ---
            (re.compile(r"^\s*(?:stop\s+current\s+task|stop\s+current|stop|cancel\s+task|abort)\s*$", re.I), "_fast_stop"),
            (re.compile(r"^\s*(?:undo\s+last|undo)\s*$", re.I), "_fast_undo"),

            # --- Audio / Volume (up/down and status checked before general volume) ---
            (re.compile(r"^\s*(?:mute\s+audio|mute\s+sound|mute)\s*$", re.I), "_fast_mute"),
            (re.compile(r"^\s*(?:unmute\s+audio|unmute\s+sound|unmute)\s*$", re.I), "_fast_unmute"),
            (re.compile(r"^\s*(?:get\s+volume\s+status|check\s+volume|sound\s+status|volume\s+status)\s*$", re.I), "_fast_get_volume_status"),
            (re.compile(r"^\s*volume\s+up\s*$", re.I), "_fast_volume_up"),
            (re.compile(r"^\s*volume\s+down\s*$", re.I), "_fast_volume_down"),
            (re.compile(r"^\s*(?:set\s+)?volume\s+(?:to\s+)?(.+?)(?:\s*percent)?\s*$", re.I), "_fast_volume"),
            (re.compile(r"^\s*turn\s+volume\s+to\s+(.+?)(?:\s*percent)?\s*$", re.I), "_fast_volume"),

            # --- Window State ---
            (re.compile(r"^\s*minimize(?:\s+all|\s+window|\s+this\s+window|\s+current\s+window|\s+active\s+window)?\s*$", re.I), "_fast_minimize"),
            (re.compile(r"^\s*(?:maximise|maximize)(?:\s+window|\s+this\s+window|\s+current\s+window|\s+active\s+window)?\s*$", re.I), "_fast_maximize"),
            (re.compile(r"^\s*restore(?:\s+window|\s+this\s+window|\s+current\s+window|\s+active\s+window)?\s*$", re.I), "_fast_restore"),
            (re.compile(r"^\s*(?:list\s+windows|show\s+open\s+windows|open\s+windows\s+list)\s*$", re.I), "_fast_list_windows"),
            (re.compile(r"^\s*(?:focus\s+window|switch\s+window)\s*$", re.I), "_fast_focus_window_bare"),

            # --- System & Activity ---
            (re.compile(r"^\s*(?:show\s+(?:activity|history)|activity|recent\s+activity|recent\s+actions|activity\s+history)\s*$", re.I), "_fast_show_activity"),
            (re.compile(r"^\s*(?:get\s+system\s+status|system\s+status|cpu\s+memory\s+status|system\s+health|status)\s*$", re.I), "_fast_system_status"),
            (re.compile(r"^\s*(?:battery\s+status|check\s+battery|battery|power\s+status)\s*$", re.I), "_fast_battery_status"),
            (re.compile(r"^\s*(?:list\s+apps|list\s+applications|running\s+applications|running\s+apps)\s*$", re.I), "_fast_list_apps"),

            # --- Clipboard ---
            (re.compile(r"^\s*(?:clear\s+clipboard|clipboard\s+clear|wipe\s+clipboard|empty\s+clipboard|clean\s+clipboard|reset\s+clipboard)\s*$", re.I), "_fast_clear_clipboard"),
            (re.compile(r"^\s*(?:get\s+clipboard(?:\s+text|\s+content)?|read\s+clipboard|show\s+clipboard|view\s+clipboard|inspect\s+clipboard|pasteboard\s+read|clipboard\s+history|copy\s+status)\s*$", re.I), "_fast_get_clipboard_text"),

            # --- Files & Folders (Deterministic exact paths/globs) ---
            (re.compile(r"^\s*(?:list\s+files(?:\s+in\s+current\s+directory)?|list\s+directory(?:\s+contents)?)\s*$", re.I), "_fast_list_files"),
            (re.compile(r"^\s*(?:find\s+file|search\s+file|locate\s+file)\s+([^\s]+)\s*$", re.I), "_fast_find_file"),
            (re.compile(r"^\s*find\s+([\w\.\*\?_-]+)\s*$", re.I), "_fast_find_file"),
            (re.compile(r"^\s*(?:create\s+folder|make\s+folder|mkdir)\s+([^\s]+)\s*$", re.I), "_fast_create_folder"),
            (re.compile(r"^\s*move\s+(?:file\s+)?([^\s]+)\s+to\s+([^\s]+)\s*$", re.I), "_fast_move_file"),
            (re.compile(r"^\s*rename\s+(?:file\s+)?([^\s]+)\s+to\s+([^\s]+)\s*$", re.I), "_fast_rename_file"),

            # --- App Launch / Focus / Close ---
            (re.compile(r"^\s*(?:open|launch|start)\s+(.+?)\s*$", re.I), "_fast_open_app"),
            (re.compile(r"^\s*(?:close|quit|exit)\s+(.+?)\s*$", re.I), "_fast_close_app"),
            (re.compile(r"^\s*focus\s+(?:on\s+)?(.+?)\s*$", re.I), "_fast_focus_app"),
        ]

        # Deep-route indicators (combined visual perception + multi-step reasoning)
        self._deep_patterns: List[re.Pattern[str]] = [
            re.compile(r"\b(?:look\s+at|inspect|read|analyze|locate)\s+.*?\b(?:form|table|dialog|prompt|screen|window|visual)\b.*?\b(?:and|fill|check|remedy|copy|enter)\b", re.I),
            re.compile(r"\b(?:unlabelled\s+checkbox|visual\s+prompt|error\s+message\s+dialog)\b", re.I),
            re.compile(r"\b(?:finish|complete)\s+(?:the\s+)?(?:remaining\s+)?configuration\b", re.I),
            re.compile(r"\bmulti-?step\b", re.I),
        ]

        # Smart-route indicators (temporal/complex/destructive multi-step ops)
        self._smart_patterns: List[re.Pattern[str]] = [
            re.compile(r"\byesterday\b|\btoday\b|\blast\s+month\b|\blast\s+week\b", re.I),
            re.compile(r"\blatest\b|\bnewest\b|\boldest\b", re.I),
            re.compile(r"\bdelete\s+all\b|\bremove\s+all\b|\bclean\s+up\b|\borganize\b|\bprepare\b|\bautomate\b|\bbatch\b|\bcount\b", re.I),
            re.compile(r"\bfind\s+all\b|\bfind\s+(?:all\s+)?(?:my|the|python|pdf)\s+\w+\b", re.I),
            re.compile(r"\band\s+(?:archive|copy|move|report|arrange|save|delete|notify|setup)\b", re.I),
        ]

        # Screen-route indicators (UI interaction terms)
        self._screen_patterns: List[re.Pattern[str]] = [
            re.compile(r"\bclick\b", re.I),
            re.compile(r"\bpress\s+(?:the\s+)?button\b", re.I),
            re.compile(r"\bsubmit\b", re.I),
            re.compile(r"\bcheck\s+box\b|\bcheckbox\b", re.I),
            re.compile(r"\btype\s+(?:into|in)\b|\btype\s+.+\s+into\b", re.I),
            re.compile(r"\bfill\s+(?:in|out)\b", re.I),
            re.compile(r"\binspect\s+(?:active\s+window|window\s+controls)\b", re.I),
            re.compile(r"\bon\s+(?:this|the)\s+screen\b", re.I),
        ]

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def route(self, request: Union[PlumaRequest, str]) -> RouteResult:
        """Classify *request* into a route and produce a Plan for FAST routes.

        Voice and text produce the same RouteResult for matching commands
        (Spec §3, non-negotiable law 3).
        """
        if isinstance(request, str):
            request = PlumaRequest.from_text(request)
        text = request.text.strip()

        # 1. Deep route indicators (multi-step visual + reasoning) checked first
        for pat in self._deep_patterns:
            if pat.search(text):
                return RouteResult(
                    route=RouteMode.DEEP,
                    reason=f"Command requires combined visual perception and multi-step reasoning: '{text[:80]}'",
                    confidence=0.85,
                )

        # 2. Smart route multi-step indicators checked before single-step FAST rules
        for pat in self._smart_patterns:
            if pat.search(text):
                return RouteResult(
                    route=RouteMode.SMART,
                    reason=f"Command requires contextual multi-step interpretation; routing to local planner: '{text[:80]}'",
                    confidence=0.75,
                )

        # 3. Try FAST rules in order
        for pattern, handler_name in self._fast_rules:
            m = pattern.match(text)
            if m:
                handler = getattr(self, handler_name)
                return handler(request, m)

        # 4. Screen route indicators
        for pat in self._screen_patterns:
            if pat.search(text):
                return RouteResult(
                    route=RouteMode.SCREEN,
                    reason=f"Command contains UI-interaction term; requires UIA/OCR: '{text[:80]}'",
                    confidence=0.85,
                )

        # 5. Default: SMART
        return RouteResult(
            route=RouteMode.SMART,
            reason=f"No deterministic match found; routing to local planner: '{text[:80]}'",
            confidence=0.5,
        )

    # ------------------------------------------------------------------
    # FAST plan builders
    # ------------------------------------------------------------------

    def _make_fast_plan(self, task_id: str, tool: str, arguments: dict, purpose: str) -> Plan:
        return Plan(
            task_id=task_id,
            mode=PlanMode.DIRECT,
            steps=[ToolCall(tool=tool, arguments=arguments, purpose=purpose)],
        )

    def _fast_stop(self, req: PlumaRequest, m: re.Match[str]) -> RouteResult:
        plan = self._make_fast_plan(
            req.request_id, "stop_current", {}, "Stop active task execution immediately."
        )
        return RouteResult(route=RouteMode.FAST, reason="Exact match: 'stop'", plan=plan)

    def _fast_undo(self, req: PlumaRequest, m: re.Match[str]) -> RouteResult:
        plan = self._make_fast_plan(
            req.request_id, "undo_last", {}, "Reverse the most recent reversible action."
        )
        return RouteResult(route=RouteMode.FAST, reason="Exact match: 'undo'", plan=plan)

    def _fast_mute(self, req: PlumaRequest, m: re.Match[str]) -> RouteResult:
        plan = self._make_fast_plan(req.request_id, "mute", {}, "Mute system audio.")
        return RouteResult(route=RouteMode.FAST, reason="Exact match: 'mute'", plan=plan)

    def _fast_unmute(self, req: PlumaRequest, m: re.Match[str]) -> RouteResult:
        plan = self._make_fast_plan(req.request_id, "unmute", {}, "Unmute system audio.")
        return RouteResult(route=RouteMode.FAST, reason="Exact match: 'unmute'", plan=plan)

    def _fast_get_volume_status(self, req: PlumaRequest, m: re.Match[str]) -> RouteResult:
        plan = self._make_fast_plan(req.request_id, "get_volume_status", {}, "Query master audio volume status.")
        return RouteResult(route=RouteMode.FAST, reason="Exact match: 'get_volume_status'", plan=plan)

    def _fast_volume(self, req: PlumaRequest, m: re.Match[str]) -> RouteResult:
        raw_level = m.group(1).strip()
        level = _parse_number(raw_level.split())
        if level is None:
            return RouteResult(
                route=RouteMode.SMART,
                reason=f"Volume command present but level '{raw_level}' could not be parsed; routing to planner.",
                confidence=0.6,
            )
        plan = self._make_fast_plan(
            req.request_id, "set_volume", {"level": level},
            f"Set master audio volume to {level}%."
        )
        return RouteResult(
            route=RouteMode.FAST,
            reason=f"Deterministic volume command matched; level={level}%",
            plan=plan,
        )

    def _fast_volume_up(self, req: PlumaRequest, m: re.Match[str]) -> RouteResult:
        plan = self._make_fast_plan(req.request_id, "set_volume", {"level": 60}, "Increase master volume.")
        return RouteResult(route=RouteMode.FAST, reason="Matched 'volume up'", plan=plan)

    def _fast_volume_down(self, req: PlumaRequest, m: re.Match[str]) -> RouteResult:
        plan = self._make_fast_plan(req.request_id, "set_volume", {"level": 20}, "Decrease master volume.")
        return RouteResult(route=RouteMode.FAST, reason="Matched 'volume down'", plan=plan)

    def _fast_open_app(self, req: PlumaRequest, m: re.Match[str]) -> RouteResult:
        app_raw = m.group(1).strip()
        app_exe = _normalise_app_name(app_raw)
        plan = self._make_fast_plan(
            req.request_id, "open_app", {"app_name": app_exe},
            f"Launch application '{app_exe}'."
        )
        return RouteResult(
            route=RouteMode.FAST,
            reason=f"Deterministic app-launch matched: '{app_exe}'",
            plan=plan,
        )

    def _fast_close_app(self, req: PlumaRequest, m: re.Match[str]) -> RouteResult:
        app_raw = m.group(1).strip()
        app_exe = _normalise_app_name(app_raw)
        plan = self._make_fast_plan(
            req.request_id, "close_app", {"app_name": app_exe},
            f"Close application '{app_exe}'."
        )
        return RouteResult(
            route=RouteMode.FAST,
            reason=f"Deterministic app-close matched: '{app_exe}'",
            plan=plan,
        )

    def _fast_focus_app(self, req: PlumaRequest, m: re.Match[str]) -> RouteResult:
        app_raw = m.group(1).strip()
        plan = self._make_fast_plan(
            req.request_id, "focus_app", {"app_name": app_raw},
            f"Focus application '{app_raw}'."
        )
        return RouteResult(
            route=RouteMode.FAST,
            reason=f"Deterministic app-focus matched: '{app_raw}'",
            plan=plan,
        )

    def _fast_minimize(self, req: PlumaRequest, m: re.Match[str]) -> RouteResult:
        plan = self._make_fast_plan(req.request_id, "minimize_window", {}, "Minimize active window.")
        return RouteResult(route=RouteMode.FAST, reason="Exact match: 'minimize window'", plan=plan)

    def _fast_maximize(self, req: PlumaRequest, m: re.Match[str]) -> RouteResult:
        plan = self._make_fast_plan(req.request_id, "maximize_window", {}, "Maximize active window.")
        return RouteResult(route=RouteMode.FAST, reason="Exact match: 'maximize window'", plan=plan)

    def _fast_restore(self, req: PlumaRequest, m: re.Match[str]) -> RouteResult:
        plan = self._make_fast_plan(req.request_id, "restore_window", {}, "Restore active window.")
        return RouteResult(route=RouteMode.FAST, reason="Exact match: 'restore window'", plan=plan)

    def _fast_list_windows(self, req: PlumaRequest, m: re.Match[str]) -> RouteResult:
        plan = self._make_fast_plan(req.request_id, "list_windows", {}, "List all visible windows.")
        return RouteResult(route=RouteMode.FAST, reason="Exact match: 'list windows'", plan=plan)

    def _fast_focus_window_bare(self, req: PlumaRequest, m: re.Match[str]) -> RouteResult:
        plan = self._make_fast_plan(req.request_id, "focus_window", {}, "Focus active window.")
        return RouteResult(route=RouteMode.FAST, reason="Matched 'focus window'", plan=plan)

    def _fast_show_activity(self, req: PlumaRequest, m: re.Match[str]) -> RouteResult:
        plan = self._make_fast_plan(req.request_id, "show_activity", {}, "Show recent Activity Ledger entries.")
        return RouteResult(route=RouteMode.FAST, reason="Exact match: 'show activity'", plan=plan)

    def _fast_system_status(self, req: PlumaRequest, m: re.Match[str]) -> RouteResult:
        plan = self._make_fast_plan(req.request_id, "get_system_status", {}, "Query system resource metrics.")
        return RouteResult(route=RouteMode.FAST, reason="Exact match: 'system status'", plan=plan)

    def _fast_battery_status(self, req: PlumaRequest, m: re.Match[str]) -> RouteResult:
        plan = self._make_fast_plan(req.request_id, "battery_status", {}, "Query battery and AC power status.")
        return RouteResult(route=RouteMode.FAST, reason="Exact match: 'battery status'", plan=plan)

    def _fast_list_apps(self, req: PlumaRequest, m: re.Match[str]) -> RouteResult:
        plan = self._make_fast_plan(req.request_id, "list_apps", {}, "List running applications.")
        return RouteResult(route=RouteMode.FAST, reason="Exact match: 'list apps'", plan=plan)

    def _fast_clear_clipboard(self, req: PlumaRequest, m: re.Match[str]) -> RouteResult:
        plan = self._make_fast_plan(req.request_id, "clipboard_clear", {}, "Clear system clipboard.")
        return RouteResult(route=RouteMode.FAST, reason="Exact match: 'clear clipboard'", plan=plan)

    def _fast_get_clipboard_text(self, req: PlumaRequest, m: re.Match[str]) -> RouteResult:
        plan = self._make_fast_plan(req.request_id, "get_clipboard_text", {}, "Get text from system clipboard.")
        return RouteResult(route=RouteMode.FAST, reason="Exact match: 'get_clipboard_text'", plan=plan)

    def _fast_list_files(self, req: PlumaRequest, m: re.Match[str]) -> RouteResult:
        plan = self._make_fast_plan(req.request_id, "list_files", {"path": "."}, "List directory files.")
        return RouteResult(route=RouteMode.FAST, reason="Exact match: 'list_files'", plan=plan)

    def _fast_find_file(self, req: PlumaRequest, m: re.Match[str]) -> RouteResult:
        pattern = m.group(1).strip()
        plan = self._make_fast_plan(req.request_id, "find_file", {"pattern": pattern, "directory": "."}, f"Find file '{pattern}'.")
        return RouteResult(route=RouteMode.FAST, reason=f"Matched 'find_file' for '{pattern}'", plan=plan)

    def _fast_create_folder(self, req: PlumaRequest, m: re.Match[str]) -> RouteResult:
        folder_name = m.group(1).strip()
        plan = self._make_fast_plan(req.request_id, "create_folder", {"path": folder_name}, f"Create folder '{folder_name}'.")
        return RouteResult(route=RouteMode.FAST, reason=f"Matched 'create_folder' for '{folder_name}'", plan=plan)

    def _fast_move_file(self, req: PlumaRequest, m: re.Match[str]) -> RouteResult:
        src = m.group(1).strip()
        dst = m.group(2).strip()
        plan = self._make_fast_plan(req.request_id, "move_file", {"source": src, "destination": dst}, f"Move file '{src}' to '{dst}'.")
        return RouteResult(route=RouteMode.FAST, reason=f"Matched 'move_file' from '{src}' to '{dst}'", plan=plan)

    def _fast_rename_file(self, req: PlumaRequest, m: re.Match[str]) -> RouteResult:
        path = m.group(1).strip()
        new_name = m.group(2).strip()
        plan = self._make_fast_plan(req.request_id, "rename_file", {"path": path, "new_name": new_name}, f"Rename file '{path}' to '{new_name}'.")
        return RouteResult(route=RouteMode.FAST, reason=f"Matched 'rename_file' from '{path}' to '{new_name}'", plan=plan)
