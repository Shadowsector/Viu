"""Поиск Cascadeur на Windows."""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path
from typing import Optional

from ...config import Config


def resolve_cascadeur_exe(config: Optional[Config] = None, override: str = "") -> Path:
    raw = (
        override
        or (config.cascadeur_exe if config else "")
        or os.environ.get("VIU_CASCADEUR_EXE", "")
    ).strip()
    if not raw:
        raise FileNotFoundError(
            "Cascadeur.exe не задан.\n"
            "В U:\\Viu\\.env добавь:\n"
            "  VIU_CASCADEUR_EXE=C:\\Program Files\\Cascadeur\\Cascadeur.exe\n"
            "(путь подставь свой — см. docs/CASCADEUR.md)"
        )
    candidate = Path(raw).expanduser()
    if candidate.is_file():
        return candidate.resolve()
    found = shutil.which(raw)
    if found:
        return Path(found).resolve()
    if sys.platform == "win32":
        for root in (
            Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Cascadeur",
            Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "Cascadeur",
        ):
            exe = root / "Cascadeur.exe"
            if exe.is_file():
                return exe.resolve()
    raise FileNotFoundError(f"Cascadeur не найден: {raw}")
