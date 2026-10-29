"""Fast, foreground-game-only screenshots for the input bridge."""

import ctypes
import io
from ctypes import wintypes

from mcp.server.fastmcp import Image


def foreground_client_region() -> tuple[int, dict[str, int]]:
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.GetForegroundWindow.restype = wintypes.HWND
    user32.GetClientRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    user32.ClientToScreen.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.POINT)]
    hwnd = user32.GetForegroundWindow()
    rect, origin = wintypes.RECT(), wintypes.POINT()
    if not hwnd or not user32.GetClientRect(hwnd, ctypes.byref(rect)):
        raise OSError("Cannot locate the foreground game client area.")
    if not user32.ClientToScreen(hwnd, ctypes.byref(origin)):
        raise OSError("Cannot locate the game on the desktop.")
    width, height = rect.right - rect.left, rect.bottom - rect.top
    if width < 2 or height < 2:
        raise ValueError("The game is minimized or has no visible client area.")
    return hwnd, {"left": origin.x, "top": origin.y, "width": width, "height": height}


def capture_game_view(expected_hwnd: int, require_focus) -> tuple[Image, dict]:
    import mss
    from PIL import Image as PillowImage

    require_focus()
    hwnd, region = foreground_client_region()
    if hwnd != expected_hwnd:
        raise ValueError("The foreground game window changed; no screenshot was captured.")
    with mss.mss() as capture:
        shot = capture.grab(region)
    require_focus()
    current_hwnd, current_region = foreground_client_region()
    if current_hwnd != hwnd or current_region != region:
        raise ValueError("The game window changed during capture; the image was discarded.")
    frame = PillowImage.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
    if frame.width > 1280:
        frame = frame.resize((1280, round(frame.height * 1280 / frame.width)))
    output = io.BytesIO()
    frame.save(output, format="JPEG", quality=78)
    data = output.getvalue()
    return Image(data=data, format="jpeg"), {
        "source_width": region["width"], "source_height": region["height"],
        "image_width": frame.width, "image_height": frame.height,
        "image_bytes": len(data), "capture_scope": "foreground_game_client",
    }
