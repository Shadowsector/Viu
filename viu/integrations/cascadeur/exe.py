"""Поиск Cascadeur на Windows."""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path
from typing import Iterable, Optional

from ...config import Config

# Типичные установки (Den: U:\Cascadeur\App\Cascadeur\cascadeur.exe).
_EXTRA_CANDIDATES: tuple[str, ...] = (
    r"U:\Cascadeur\App\Cascadeur\cascadeur.exe",
    r"U:\Cascadeur\App\Cascadeur\Cascadeur.exe",
    r"U:/Cascadeur/App/Cascadeur/cascadeur.exe",
    r"U:/Cascadeur/App/Cascadeur/Cascadeur.exe",
)


def _candidate_paths() -> Iterable[Path]:
    for raw in _EXTRA_CANDIDATES:
        yield Path(raw)
    if sys.platform == "win32":
        for root in (
            Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Cascadeur",
            Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "Cascadeur",
        ):
            yield root / "Cascadeur.exe"
            yield root / "cascadeur.exe"


def discover_cascadeur_exe() -> Optional[Path]:
    """Первый найденный exe без env (для Den на U:)."""
    for candidate in _candidate_paths():
        try:
            if candidate.is_file():
                return candidate.resolve()
        except OSError:
            continue
    return None


def resolve_cascadeur_exe(config: Optional[Config] = None, override: str = "") -> Path:
    raw = (
        override
        or (config.cascadeur_exe if config else "")
        or os.environ.get("VIU_CASCADEUR_EXE", "")
    ).strip()
    if raw:
        candidate = Path(raw).expanduser()
        if candidate.is_file():
            return candidate.resolve()
        found = shutil.which(raw)
        if found:
            return Path(found).resolve()
        discovered = discover_cascadeur_exe()
        if discovered:
            return discovered
        raise FileNotFoundError(
            f"Cascadeur не найден: {raw}\n"
            "Проверь путь или положи exe в U:\\Cascadeur\\App\\Cascadeur\\"
        )

    discovered = discover_cascadeur_exe()
    if discovered:
        return discovered

    raise FileNotFoundError(
        "Cascadeur.exe не задан и не найден автоматически.\n"
        "В U:\\Viu\\.env добавь:\n"
        "  VIU_CASCADEUR_EXE=U:\\Cascadeur\\App\\Cascadeur\\cascadeur.exe\n"
        "(см. docs/CASCADEUR.md)"
    )
