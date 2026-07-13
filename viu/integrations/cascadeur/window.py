"""Поиск окна Cascadeur (заголовок или PID процесса)."""

from __future__ import annotations

import sys
from typing import Optional, Tuple

from ..apps.process import app_pids
from ..screen.capture import find_hwnd, list_windows

_TITLE_HINTS = ("cascadeur", "каскад", "cascader")


def find_cascadeur_hwnd() -> Optional[int]:
    """HWND главного окна Cascadeur — по заголовку или cascadeur.exe."""
    for hint in _TITLE_HINTS:
        hwnd = find_hwnd(hint)
        if hwnd:
            return hwnd

    if sys.platform != "win32":
        return None

    pids = set(app_pids("cascadeur"))
    if not pids:
        return None

    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    best: Optional[tuple[int, int]] = None  # (area, hwnd)

    for hwnd, title in list_windows():
        if not user32.IsWindowVisible(hwnd):
            continue
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if int(pid.value) not in pids:
            continue
        rect = wintypes.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(rect))
        w = max(0, rect.right - rect.left)
        h = max(0, rect.bottom - rect.top)
        area = w * h
        if area < 400 * 300:
            continue
        if best is None or area > best[0]:
            best = (area, int(hwnd))

    return best[1] if best else None


def focus_cascadeur_window() -> Tuple[bool, str]:
    """Поставить Cascadeur на передний план (без клика мышью)."""
    if sys.platform != "win32":
        return False, "не Windows"
    hwnd = find_cascadeur_hwnd()
    if not hwnd:
        return False, "окно Cascadeur не найдено"
    import ctypes

    user32 = ctypes.windll.user32
    user32.ShowWindow(hwnd, 9)  # SW_RESTORE
    ok = bool(user32.SetForegroundWindow(hwnd))
    return ok, f"фокус HWND {hwnd}" if ok else "SetForegroundWindow не удался"
