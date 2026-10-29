"""Safety checks shared by the local game-input MCP server."""

import time
import json
from pathlib import Path
from collections.abc import Callable

MAX_HOLD_MS = 2000
MAX_MOUSE_DELTA = 600

# Input profiles are selected from the checked foreground title. Unknown games
# use physical keyboard input and are explicitly marked as unverified.
GAME_PROFILES = {
    "online_mode": {
        "window_title": "Online Mode", "keyboard_backend": "sendinput_scancode",
        "movement": "WASD", "camera": "relative mouse", "interact": "server binding",
        "jump": "Space", "menu": "Escape", "sprint": "Shift+W; use sprint=false",
    },
    "legacy_camera_mode": {
        "window_title": "Legacy Camera Mode", "keyboard_backend": "sendinput_scancode",
        "movement": "WASD", "camera": "relative mouse", "interact": "context binding",
        "jump": "Space", "menu": "Escape", "sprint": "Shift+W; use sprint=false",
    },
    "alternate_camera_mode": {
        "window_title": "Alternate Camera Mode", "keyboard_backend": "sendinput_scancode",
        "movement": "W/S forward/back; Q/E strafe; A/D turn",
        "jump": "Space", "interact": "F", "menu": "Escape", "sprint": None,
    },
    "pointer_mode": {
        "window_title": "Pointer Mode", "keyboard_backend": "sendinput_scancode",
        "movement": "WASD", "camera": "pointer", "interact": "right mouse",
        "use_tool": "left mouse", "menu": "E", "sprint": None,
    },
    "camera_mode": {
        "window_title": "Camera Mode", "keyboard_backend": "pyautogui_virtual_key",
        "movement": "WASD", "camera": "relative mouse", "interact": "right mouse",
        "use_tool": "left mouse", "menu": "E", "sprint": "Ctrl+W",
    },
}


def _apply_local_settings():
    path = Path(__file__).with_name("input-settings.local.json")
    if not path.exists():
        return
    if path.stat().st_size > 4096:
        raise ValueError("Input settings are too large.")
    settings = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(settings, dict) or set(settings) - {"window_title", "input_style", "keyboard_backend"}:
        raise ValueError("Input settings accept window_title, input_style and keyboard_backend only.")
    title = settings.get("window_title")
    style = settings.get("input_style", "camera")
    backend = settings.get("keyboard_backend", "sendinput_scancode")
    if not isinstance(title, str) or not title.strip() or len(title) > 200 or any(ord(c) < 32 for c in title):
        raise ValueError("window_title must be nonempty text of at most 200 characters.")
    if style not in ("pointer", "camera"):
        raise ValueError("input_style must be pointer or camera.")
    if backend not in ("sendinput_scancode", "pyautogui_virtual_key"):
        raise ValueError("Unsupported keyboard_backend.")
    key = "pointer_mode" if style == "pointer" else "camera_mode"
    GAME_PROFILES[key] = dict(GAME_PROFILES[key], window_title=title.strip(), keyboard_backend=backend)


_apply_local_settings()


def game_profile_for_window(title: str) -> tuple[str, dict]:
    for name, profile in GAME_PROFILES.items():
        if profile["window_title"].casefold() in title.casefold():
            return name, dict(profile)
    return "unverified", {"keyboard_backend": "sendinput_scancode"}

KEY_ALIASES = {
    "spacebar": "space",
    "esc": "escape",
    "return": "enter",
    "control": "ctrl",
    "slash": "/", "minus": "-", "equals": "=", "comma": ",",
    "period": ".", "backslash": "\\",
}
ALLOWED_KEYS = {
    "w", "a", "s", "d", "space", "shift", "ctrl", "e", "q", "f", "r",
    "escape", "enter", "tab", "up", "down", "left", "right",
    *"abcdefghijklmnopqrstuvwxyz0123456789",
    "backspace", "delete", "home", "end", "pageup", "pagedown",
    "/", "-", "=", ",", ".", "\\",
    *(f"f{number}" for number in range(1, 13)),
}
ALLOWED_MOUSE_BUTTONS = {"left", "right", "middle"}
MOVEMENT_KEYS = {"w", "a", "s", "d", "space", "shift", "ctrl"}

STEP_DEFAULTS = {
    "keys": [], "dx": 0, "dy": 0, "duration_ms": 160, "sprint": False,
    "button": None, "click_ms": 140, "slot": None, "settle_ms": 200,
    "turn_first": False, "turn_ms": 140, "tap": None, "tap_ms": 140,
    "pointer_x": None, "pointer_y": None, "view_width": None, "view_height": None,
}
MAX_SEQUENCE_STEPS = 3
MAX_SEQUENCE_MS = 8000


def validate_step_options(options: dict) -> dict:
    """Validate an entire action before any input, including optional targeting."""
    if not isinstance(options, dict) or set(options) - set(STEP_DEFAULTS):
        raise ValueError("An action contains unsupported options.")
    result = {**STEP_DEFAULTS, **options}
    result["keys"] = validate_movement_keys(result["keys"])
    result["dx"], result["dy"] = validate_mouse_delta(result["dx"], result["dy"])
    for field in ("duration_ms", "click_ms", "turn_ms", "tap_ms"):
        result[field] = validate_duration_ms(result[field])
    for field in ("sprint", "turn_first"):
        if not isinstance(result[field], bool):
            raise ValueError(f"{field} must be true or false.")
    if result["sprint"]:
        if "w" not in result["keys"] or "shift" in result["keys"]:
            raise ValueError("Sprint requires W and cannot be combined with sneak.")
        result["keys"] = validate_movement_keys([*result["keys"], "ctrl"])
    if result["button"] is not None:
        result["button"] = validate_mouse_button(result["button"])
    slot = result["slot"]
    if slot is not None and (isinstance(slot, bool) or not isinstance(slot, int) or not 1 <= slot <= 9):
        raise ValueError("Hotbar slot must be an integer from 1 to 9.")
    settle = result["settle_ms"]
    if isinstance(settle, bool) or not isinstance(settle, int) or not 0 <= settle <= 500:
        raise ValueError("Render wait must be an integer from 0 to 500 ms.")
    if result["tap"] is not None:
        result["tap"] = validate_key(result["tap"])
    point_fields = ("pointer_x", "pointer_y", "view_width", "view_height")
    if any(result[field] is not None for field in point_fields):
        if any(isinstance(result[field], bool) or not isinstance(result[field], int) for field in point_fields):
            raise ValueError("Pointer targeting requires integer x, y, view_width and view_height.")
        if not 2 <= result["view_width"] <= 1280 or not 2 <= result["view_height"] <= 8192:
            raise ValueError("Use the dimensions of the latest bridge image.")
        if not 0 <= result["pointer_x"] < result["view_width"] or not 0 <= result["pointer_y"] < result["view_height"]:
            raise ValueError("The pointer target must stay inside the game image.")
        if result["dx"] or result["dy"]:
            raise ValueError("Use either pointer targeting or relative camera movement in an action.")
    return result


def step_budget_ms(step: dict) -> int:
    """Upper bound of requested input and render waits, excluding capture overhead."""
    budget = step["duration_ms"] if step["keys"] or step["dx"] or step["dy"] else 0
    if step["turn_first"] and step["keys"] and (step["dx"] or step["dy"]):
        budget += step["turn_ms"]
    budget += step["click_ms"] if step["button"] is not None else 0
    budget += step["tap_ms"] if step["tap"] is not None else 0
    budget += 140 if step["slot"] is not None else 0
    budget += 60 if step["pointer_x"] is not None else 0
    return budget + (step["settle_ms"] if budget else 0)


def validate_sequence_steps(steps: list[dict]) -> list[dict]:
    if not isinstance(steps, list) or not 1 <= len(steps) <= MAX_SEQUENCE_STEPS:
        raise ValueError(f"Provide one to {MAX_SEQUENCE_STEPS} short actions.")
    result = [validate_step_options(step) for step in steps]
    if sum(step_budget_ms(step) for step in result) > MAX_SEQUENCE_MS:
        raise ValueError(f"The combined requested action time is limited to {MAX_SEQUENCE_MS} ms.")
    return result


def validate_movement_keys(keys: list[str]) -> list[str]:
    if not isinstance(keys, list) or len(keys) > 4:
        raise ValueError("Provide up to four movement keys as a list.")
    normalized = list(dict.fromkeys(validate_key(key) for key in keys))
    if any(key not in MOVEMENT_KEYS for key in normalized):
        raise ValueError("Coordinated input accepts movement keys only: W, A, S, D, Space, Shift, Ctrl.")
    if {"w", "s"} <= set(normalized) or {"a", "d"} <= set(normalized):
        raise ValueError("Opposing movement directions cannot be held together.")
    return normalized


def validate_target(expected_window: str, active_window: str) -> bool:
    expected = str(expected_window).strip()
    active = str(active_window).strip()
    if not expected:
        raise ValueError("Provide the expected game window title.")
    if not active or expected.casefold() not in active.casefold():
        raise ValueError("The active window does not match the requested game window; no input was sent.")
    return True


def validate_key(key: str) -> str:
    normalized = str(key).strip().casefold()
    normalized = KEY_ALIASES.get(normalized, normalized)
    if normalized not in ALLOWED_KEYS:
        raise ValueError("Unsupported key. Use a listed game key such as W, A, S, D, Space, Shift, E, or Escape.")
    return normalized


def validate_duration_ms(duration_ms: int) -> int:
    if isinstance(duration_ms, bool) or not isinstance(duration_ms, int):
        raise ValueError("Hold duration must be a whole number of milliseconds.")
    if duration_ms < 1 or duration_ms > MAX_HOLD_MS:
        raise ValueError(f"Hold duration must be between 1 and {MAX_HOLD_MS} ms.")
    return duration_ms


def validate_mouse_delta(dx: int, dy: int) -> tuple[int, int]:
    for value in (dx, dy):
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError("Mouse movement must use whole-pixel offsets.")
        if abs(value) > MAX_MOUSE_DELTA:
            raise ValueError(f"Mouse movement per call is limited to {MAX_MOUSE_DELTA} pixels per axis.")
    return dx, dy


def validate_mouse_button(button: str) -> str:
    normalized = str(button).strip().casefold()
    if normalized not in ALLOWED_MOUSE_BUTTONS:
        raise ValueError("Mouse button must be left, right, or middle.")
    return normalized


def bounded_hold(
    press: Callable[[], None],
    release: Callable[[], None],
    duration_ms: int,
    *,
    sleep: Callable[[float], None] = time.sleep,
) -> None:
    duration = validate_duration_ms(duration_ms)
    try:
        press()
        sleep(duration / 1000)
    finally:
        release()
