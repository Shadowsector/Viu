"""Поиск blender.exe на Windows и в PATH."""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path
from typing import Optional

from ...config import Config


def resolve_blender_exe(config: Optional[Config] = None, override: str = "") -> Path:
    """Возвращает путь к blender.exe или понятную ошибку (WinError 2)."""
    raw = (override or (config.blender_exe if config else "") or os.environ.get("VIU_BLENDER_EXE") or "blender").strip()
    candidate = Path(raw).expanduser()
    if candidate.is_file():
        return candidate.resolve()

    found = shutil.which(raw)
    if found:
        return Path(found).resolve()

    if sys.platform == "win32":
        roots = [
            Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Blender Foundation",
            Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "Blender Foundation",
            Path("C:/Program Files/Blender Foundation"),
        ]
        for root in roots:
            if not root.is_dir():
                continue
            versions = sorted(root.glob("Blender *"), key=lambda p: p.name, reverse=True)
            for folder in versions:
                exe = folder / "blender.exe"
                if exe.is_file():
                    return exe.resolve()

    raise FileNotFoundError(
        "Blender.exe не найден.\n"
        "Задай переменную окружения:\n"
        "  VIU_BLENDER_EXE=C:\\Program Files\\Blender Foundation\\Blender 5.1\\blender.exe\n"
        "Или добавь Blender в PATH."
    )
