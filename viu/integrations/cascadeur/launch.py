"""Запуск Cascadeur и позиционирование на мониторе лаборатории."""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path
from typing import Tuple

from ...config import Config
from ..apps.process import app_running, restart_app
from ..screen.capture import find_hwnd
from ..screen.monitor import move_hwnd_to_monitor
from .paths import cascadeur_inbox


def ensure_cascadeur_running(config: Config, *, monitor_index: int = 2) -> Tuple[bool, str]:
    """Запустить Cascadeur если нет; сдвинуть на monitor_index (0-based)."""
    if not app_running("cascadeur"):
        ok, msg = restart_app("cascadeur", config)
        if not ok:
            return False, msg
        time.sleep(4.0)
    else:
        msg = "Cascadeur уже запущен."

    hwnd = find_hwnd("Cascadeur")
    if not hwnd:
        # часть сборок — другое имя окна
        hwnd = find_hwnd("cascadeur")
    if not hwnd:
        return True, msg + " Окно Cascadeur не найдено для переноса — открой вручную на 3-м мониторе."

    moved_ok, move_msg = move_hwnd_to_monitor(hwnd, monitor_index)
    parts = [msg, move_msg]
    return moved_ok or app_running("cascadeur"), " ".join(p for p in parts if p)


def seed_inbox_sample_fbx(config: Config) -> Tuple[bool, str, Path | None]:
    """Положить в Inbox один FBX для эксперимента (если пусто)."""
    inbox = cascadeur_inbox(config)
    existing = list(inbox.glob("*.fbx"))
    if existing:
        return True, f"Inbox уже есть: {existing[0].name}", existing[0]

    staging = Path(config.unity_anim_staging or "").expanduser()
    candidates: list[Path] = []
    if staging.is_dir():
        candidates.extend(sorted(staging.glob("*.fbx"), key=lambda p: p.stat().st_mtime, reverse=True))
    lib_anim = Path(config.library_root or "").expanduser().parent / "Animations"
    if lib_anim.is_dir():
        candidates.extend(sorted(lib_anim.glob("*.fbx"), key=lambda p: p.stat().st_mtime, reverse=True))

    for src in candidates:
        if "idle" in src.name.lower() or "walk" in src.name.lower() or "run" in src.name.lower():
            dst = inbox / f"lab_{src.name}"
            try:
                import shutil

                shutil.copy2(src, dst)
                return True, f"Скопировала в Inbox: {dst.name}", dst
            except OSError as exc:
                return False, str(exc), None

    if candidates:
        src = candidates[0]
        dst = inbox / f"lab_{src.name}"
        try:
            import shutil

            shutil.copy2(src, dst)
            return True, f"Скопировала в Inbox: {dst.name}", dst
        except OSError as exc:
            return False, str(exc), None

    return False, "Нет FBX для Inbox — положи файл в Library/Cascadeur/Inbox", None
