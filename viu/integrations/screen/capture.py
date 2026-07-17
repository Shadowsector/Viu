"""Захват окон Windows без сторонних пакетов (ctypes + PNG)."""

from __future__ import annotations

import struct
import sys
import zlib
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple


def _write_png(path: Path, width: int, height: int, rgb: bytes) -> None:
    """rgb: top-to-bottom RGB, len = width*height*3."""
    if len(rgb) != width * height * 3:
        raise ValueError("rgb size mismatch")

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + tag
            + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        )

    raw = bytearray()
    stride = width * 3
    for y in range(height):
        raw.append(0)  # filter None
        raw.extend(rgb[y * stride : (y + 1) * stride])

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    data = b"\x89PNG\r\n\x1a\n"
    data += chunk(b"IHDR", ihdr)
    data += chunk(b"IDAT", zlib.compress(bytes(raw), 9))
    data += chunk(b"IEND", b"")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def list_windows() -> List[Tuple[int, str]]:
    """[(hwnd, title), ...] видимые окна с заголовком."""
    if sys.platform != "win32":
        return []

    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    results: List[Tuple[int, str]] = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def _enum(hwnd, _lp):  # noqa: N803
        if not user32.IsWindowVisible(hwnd):
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        if length <= 0:
            return True
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        title = buf.value.strip()
        if title:
            results.append((int(hwnd), title))
        return True

    user32.EnumWindows(_enum, 0)
    return results


def find_hwnd(title_substr: str) -> Optional[int]:
    needle = (title_substr or "").lower()
    if not needle:
        return None
    for hwnd, title in list_windows():
        if needle in title.lower():
            return hwnd
    return None


def capture_window_png(
    path: Path,
    *,
    title_substr: str = "",
    hwnd: int = 0,
) -> Tuple[bool, str]:
    """Снять окно по hwnd или подстроке заголовка → PNG. (ok, msg)."""
    if sys.platform != "win32":
        return False, "Захват окна только на Windows."

    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    gdi32 = ctypes.windll.gdi32

    target = hwnd or (find_hwnd(title_substr) if title_substr else 0)
    if not target:
        titles = [t for _, t in list_windows()[:25]]
        return False, f"Окно не найдено ({title_substr!r}). Видны: {titles}"

    # PrintWindow — лучше для layered/DWM, чем BitBlt чужого DC
    rect = wintypes.RECT()
    user32.GetClientRect(target, ctypes.byref(rect))
    width = int(rect.right - rect.left)
    height = int(rect.bottom - rect.top)
    if width < 8 or height < 8:
        user32.GetWindowRect(target, ctypes.byref(rect))
        width = int(rect.right - rect.left)
        height = int(rect.bottom - rect.top)
    if width < 8 or height < 8:
        return False, f"Окно слишком маленькое: {width}x{height}"

    hwnd_dc = user32.GetWindowDC(target)
    if not hwnd_dc:
        return False, "GetWindowDC failed"
    mem_dc = gdi32.CreateCompatibleDC(hwnd_dc)
    bmp = gdi32.CreateCompatibleBitmap(hwnd_dc, width, height)
    old = gdi32.SelectObject(mem_dc, bmp)

    PW_RENDERFULLCONTENT = 2
    ok = user32.PrintWindow(target, mem_dc, PW_RENDERFULLCONTENT)
    if not ok:
        # fallback BitBlt
        gdi32.BitBlt(mem_dc, 0, 0, width, height, hwnd_dc, 0, 0, 0x00CC0020)

    class BITMAPINFOHEADER(ctypes.Structure):
        _fields_ = [
            ("biSize", wintypes.DWORD),
            ("biWidth", wintypes.LONG),
            ("biHeight", wintypes.LONG),
            ("biPlanes", wintypes.WORD),
            ("biBitCount", wintypes.WORD),
            ("biCompression", wintypes.DWORD),
            ("biSizeImage", wintypes.DWORD),
            ("biXPelsPerMeter", wintypes.LONG),
            ("biYPelsPerMeter", wintypes.LONG),
            ("biClrUsed", wintypes.DWORD),
            ("biClrImportant", wintypes.DWORD),
        ]

    bmi = BITMAPINFOHEADER()
    bmi.biSize = ctypes.sizeof(BITMAPINFOHEADER)
    bmi.biWidth = width
    bmi.biHeight = -height  # top-down
    bmi.biPlanes = 1
    bmi.biBitCount = 32
    bmi.biCompression = 0

    buf_len = width * height * 4
    buf = (ctypes.c_ubyte * buf_len)()
    gdi32.GetDIBits(mem_dc, bmp, 0, height, ctypes.byref(buf), ctypes.byref(bmi), 0)

    gdi32.SelectObject(mem_dc, old)
    gdi32.DeleteObject(bmp)
    gdi32.DeleteDC(mem_dc)
    user32.ReleaseDC(target, hwnd_dc)

    # BGRA → RGB
    rgb = bytearray(width * height * 3)
    for i in range(width * height):
        b = buf[i * 4 + 0]
        g = buf[i * 4 + 1]
        r = buf[i * 4 + 2]
        rgb[i * 3] = r
        rgb[i * 3 + 1] = g
        rgb[i * 3 + 2] = b

    try:
        _write_png(path, width, height, bytes(rgb))
    except OSError as exc:
        return False, f"Не записала PNG: {exc}"

    return True, f"Скрин {width}x{height} → {path}"


def default_shot_path(data_dir: Path, prefix: str = "eye") -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return (data_dir / "shots" / f"{prefix}_{stamp}.png").resolve()
