"""Эмуляция мыши для лаборатории (Windows SendInput).

Один краткий клик для фокуса Cascadeur — без захвата курсора.
Позиция курсора сохраняется и восстанавливается сразу после клика.

По умолчанию мышь lab **только в режиме «меня нет»** (VIU_LAB_MOUSE_AWAY_ONLY=1).
На Linux/macOS — заглушка.
"""

from __future__ import annotations

import os
import sys
from typing import Optional, Tuple


def lab_mouse_enabled(config=None) -> bool:
    raw = os.environ.get("VIU_LAB_MOUSE", "1" if sys.platform == "win32" else "0")
    if raw.strip().lower() in ("0", "false", "no", "off"):
        return False
    if config is not None:
        try:
            from ...runtime_settings import get

            val = get(config, "lab_mouse", None)
            if val is not None and str(val).strip().lower() in ("0", "false", "no", "off"):
                return False
        except Exception:
            pass
    return sys.platform == "win32"


def lab_mouse_away_only(config=None) -> bool:
    """True — не трогать мышь, пока Ден «дома»."""
    raw = os.environ.get("VIU_LAB_MOUSE_AWAY_ONLY", "1")
    if raw.strip().lower() in ("0", "false", "no", "off"):
        return False
    if config is not None:
        try:
            from ...runtime_settings import get

            val = get(config, "lab_mouse_away_only", None)
            if val is not None and str(val).strip().lower() in ("0", "false", "no", "off"):
                return False
        except Exception:
            pass
    return True


def lab_mouse_allowed(config=None) -> bool:
    """Можно ли lab сейчас трогать мышь."""
    if not lab_mouse_enabled(config):
        return False
    if lab_mouse_away_only(config) and config is not None:
        from ...presence import is_away

        return is_away(config)
    if lab_mouse_away_only(config) and config is None:
        return False
    return True


def _cursor_pos() -> Optional[Tuple[int, int]]:
    if sys.platform != "win32":
        return None
    import ctypes
    from ctypes import wintypes

    pt = wintypes.POINT()
    if not ctypes.windll.user32.GetCursorPos(ctypes.byref(pt)):
        return None
    return int(pt.x), int(pt.y)


def _set_cursor_pos(x: int, y: int) -> bool:
    if sys.platform != "win32":
        return False
    import ctypes

    return bool(ctypes.windll.user32.SetCursorPos(int(x), int(y)))


def click_screen(
    x: int,
    y: int,
    *,
    button: str = "left",
    restore_cursor: bool = True,
) -> Tuple[bool, str]:
    """Клик в экранных координатах; по умолчанию возвращает курсор на место."""
    if sys.platform != "win32":
        return False, "Мышь: не Windows"

    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    saved = _cursor_pos() if restore_cursor else None

    sw = user32.GetSystemMetrics(0)
    sh = user32.GetSystemMetrics(1)
    ax = int(x * 65535 / max(sw - 1, 1))
    ay = int(y * 65535 / max(sh - 1, 1))

    MOUSEEVENTF_MOVE = 0x0001
    MOUSEEVENTF_ABSOLUTE = 0x8000
    MOUSEEVENTF_LEFTDOWN = 0x0002
    MOUSEEVENTF_LEFTUP = 0x0004
    MOUSEEVENTF_RIGHTDOWN = 0x0008
    MOUSEEVENTF_RIGHTUP = 0x0010

    class MOUSEINPUT(ctypes.Structure):
        _fields_ = [
            ("dx", wintypes.LONG),
            ("dy", wintypes.LONG),
            ("mouseData", wintypes.DWORD),
            ("dwFlags", wintypes.DWORD),
            ("time", wintypes.DWORD),
            ("dwExtraInfo", ctypes.POINTER(wintypes.ULONG)),
        ]

    class INPUT(ctypes.Structure):
        class _U(ctypes.Union):
            _fields_ = [("mi", MOUSEINPUT)]

        _anonymous_ = ("u",)
        _fields_ = [("type", wintypes.DWORD), ("u", _U)]

    INPUT_MOUSE = 0

    def _send(flags: int) -> None:
        inp = INPUT(type=INPUT_MOUSE)
        inp.mi = MOUSEINPUT(ax, ay, 0, flags | MOUSEEVENTF_ABSOLUTE, 0, None)
        if user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(inp)) != 1:
            raise OSError("SendInput failed")

    try:
        _send(MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE)
        if button == "right":
            _send(MOUSEEVENTF_RIGHTDOWN | MOUSEEVENTF_ABSOLUTE)
            _send(MOUSEEVENTF_RIGHTUP | MOUSEEVENTF_ABSOLUTE)
        else:
            _send(MOUSEEVENTF_LEFTDOWN | MOUSEEVENTF_ABSOLUTE)
            _send(MOUSEEVENTF_LEFTUP | MOUSEEVENTF_ABSOLUTE)
        suffix = ""
        if saved is not None:
            if _set_cursor_pos(saved[0], saved[1]):
                suffix = f"; курсор возвращён ({saved[0]}, {saved[1]})"
        return True, f"Клик ({x}, {y}){suffix}"
    except OSError as exc:
        if saved is not None:
            _set_cursor_pos(saved[0], saved[1])
        return False, str(exc)


def focus_window_center(hwnd: int) -> Tuple[bool, str]:
    """Активировать окно и кликнуть в центр; курсор Дена восстанавливается."""
    if sys.platform != "win32":
        return True, "Мышь: пропуск (не Windows)"

    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    rect = wintypes.RECT()
    if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
        return False, "GetWindowRect failed"

    user32.SetForegroundWindow(hwnd)
    cx = (rect.left + rect.right) // 2
    cy = (rect.top + rect.bottom) // 2
    ok, msg = click_screen(cx, cy, restore_cursor=True)
    if ok:
        return True, f"Фокус окна + клик в центр ({cx}, {cy}). {msg}"
    return ok, msg
