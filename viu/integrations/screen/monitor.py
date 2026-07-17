"""Перемещение окон между мониторами (Windows)."""

from __future__ import annotations

import sys
from typing import List, Optional, Tuple


def list_monitor_rects() -> List[Tuple[int, int, int, int]]:
    """[(left, top, right, bottom), ...] по индексу монитора."""
    if sys.platform != "win32":
        return [(0, 0, 1920, 1080)]

    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    rects: List[Tuple[int, int, int, int]] = []

    @ctypes.WINFUNCTYPE(
        wintypes.BOOL,
        wintypes.HMONITOR,
        wintypes.HDC,
        ctypes.POINTER(wintypes.RECT),
        wintypes.LPARAM,
    )
    def _cb(hmon, _hdc, lprect, _lp):  # noqa: N803
        r = lprect.contents
        rects.append((int(r.left), int(r.top), int(r.right), int(r.bottom)))
        return True

    user32.EnumDisplayMonitors(0, 0, _cb, 0)
    return rects or [(0, 0, 1920, 1080)]


def move_hwnd_to_monitor(hwnd: int, monitor_index: int) -> Tuple[bool, str]:
    if sys.platform != "win32":
        return False, "Перемещение окна только на Windows."
    if hwnd <= 0:
        return False, "Неверный hwnd"

    rects = list_monitor_rects()
    idx = min(max(0, monitor_index), len(rects) - 1)
    left, top, right, bottom = rects[idx]
    width = max(800, right - left - 40)
    height = max(600, bottom - top - 80)

    import ctypes

    user32 = ctypes.windll.user32
    SWP_NOSIZE = 0x0001
    SWP_NOZORDER = 0x0004
    ok = user32.SetWindowPos(hwnd, 0, left + 20, top + 20, width, height, 0)
    if not ok:
        # попробовать с изменением размера
        ok = user32.SetWindowPos(hwnd, 0, left + 20, top + 20, width, height, SWP_NOZORDER)
    if ok:
        return True, f"Окно на монитор {idx + 1} ({left},{top})"
    return False, "SetWindowPos не удался"
