"""Эмуляция мыши для лаборатории (Windows SendInput).

На Linux/macOS — заглушка (Capture/launch без кликов).
Включение: VIU_LAB_MOUSE=1 (по умолчанию на win32).
"""

from __future__ import annotations

import os
import sys
from typing import Tuple


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


def click_screen(x: int, y: int, *, button: str = "left") -> Tuple[bool, str]:
    """Клик в экранных координатах."""
    if not lab_mouse_enabled():
        return False, "Мышь: только Windows (VIU_LAB_MOUSE=1)"

    if sys.platform != "win32":
        return False, "Мышь: не Windows"

    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    # Абсолютные координаты 0..65535
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
        return True, f"Клик ({x}, {y})"
    except OSError as exc:
        return False, str(exc)


def focus_window_center(hwnd: int) -> Tuple[bool, str]:
    """Активировать окно и кликнуть в центр (фокус для Cascadeur UI)."""
    if not lab_mouse_enabled():
        return True, "Мышь: пропуск (VIU_LAB_MOUSE=0 или не Windows)"

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
    ok, msg = click_screen(cx, cy)
    if ok:
        return True, f"Фокус окна + клик в центр ({cx}, {cy})"
    return ok, msg
