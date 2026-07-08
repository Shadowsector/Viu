"""Каноническая структура папок Анабарры на диске.

U:\\Anabarra\\          — корень игры (данные, библиотека, Unity)
U:\\Anabarra\\Unity\\Anabarra\\ — Unity-проект (Assets/, Builds/)
U:\\Viu\\               — только программа Вью (код, exe), не рабочие файлы игры
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable, List

from .config import Config

# Подпапки внутри U:\\Anabarra\\Library\\ (создаются ensure_layout).
LIBRARY_SUBDIRS: tuple[str, ...] = (
    "Props/incoming/fbx",
    "Props/incoming/obj",
    "Props/incoming/glb",
    "Blender/incoming",
    "Archives/incoming",
    "References/images",
    "Incoming/unsorted",
)

DEFAULT_ANABARRA_ROOT = Path("U:/Anabarra")
DEFAULT_UNITY_PROJECT = DEFAULT_ANABARRA_ROOT / "Unity" / "Anabarra"


def _env(name: str) -> str:
    value = os.environ.get(name)
    return value if value not in (None, "") else ""


def anabarra_root(config: Config) -> Path:
    """Корень игры — не Unity-проект и не U:\\Viu."""
    raw = _env("VIU_ANABARRA_ROOT") or getattr(config, "anabarra_root", "") or ""
    if raw:
        return Path(raw).expanduser().resolve()

    unity_raw = (config.unity_project or _env("VIU_UNITY_PROJECT") or "").strip()
    if unity_raw:
        unity = Path(unity_raw).expanduser().resolve()
        if unity.name.lower() == "anabarra" and unity.parent.name.lower() == "unity":
            return unity.parent.parent
        if (unity / "Assets").is_dir():
            # Unity-проект лежит прямо в корне — считаем его корнем игры.
            return unity
        return unity.parent

    viu_root = config.root
    if viu_root.name.lower() == "viu" and viu_root.parent.exists():
        sibling = viu_root.parent / "Anabarra"
        if sibling.is_dir():
            return sibling.resolve()

    if DEFAULT_ANABARRA_ROOT.exists():
        return DEFAULT_ANABARRA_ROOT.resolve()
    return DEFAULT_ANABARRA_ROOT


def unity_project_path(config: Config) -> Path:
    raw = (config.unity_project or _env("VIU_UNITY_PROJECT") or "").strip()
    if raw:
        return Path(raw).expanduser().resolve()
    candidate = anabarra_root(config) / "Unity" / "Anabarra"
    if candidate.is_dir():
        return candidate.resolve()
    return DEFAULT_UNITY_PROJECT


def library_root(config: Config) -> Path:
    raw = _env("VIU_LIBRARY_ROOT") or getattr(config, "library_root", "") or ""
    if raw:
        return Path(raw).expanduser().resolve()
    return anabarra_root(config) / "Library"


def project_data_dir(config: Config) -> Path:
    """Служебные данные Вью — рядом с игрой, не в U:\\Viu."""
    explicit = _env("VIU_DATA_DIR")
    if explicit:
        return Path(explicit).expanduser().resolve()
    if config.data_dir:
        return config.data_dir.resolve()
    return anabarra_root(config) / ".viu"


def downloads_dir(config: Config) -> Path:
    raw = _env("VIU_DOWNLOADS_DIR") or getattr(config, "downloads_dir", "") or ""
    if raw:
        return Path(raw).expanduser().resolve()
    return Path.home() / "Downloads"


def ensure_layout(config: Config) -> List[Path]:
    """Создаёт стандартные каталоги; возвращает список созданных/существующих корней."""
    roots: List[Path] = []
    data = config.data_dir.resolve()
    data.mkdir(parents=True, exist_ok=True)
    roots.append(data)
    lib = library_root(config)
    lib.mkdir(parents=True, exist_ok=True)
    roots.append(lib)
    for sub in LIBRARY_SUBDIRS:
        (lib / sub).mkdir(parents=True, exist_ok=True)
    return roots


def describe_layout(config: Config) -> str:
    """Краткая справка для project_status и чата."""
    root = anabarra_root(config)
    unity = unity_project_path(config)
    viu_install = config.root if config.root.name.lower() == "viu" else None
    lines = [
        "Структура на диске:",
        f"  Корень игры (Анабарра):  {root}",
        f"  Unity-проект:            {unity}",
        f"  Библиотека ассетов:      {library_root(config)}",
        f"  Данные Вью (.viu):       {config.data_dir}",
        f"  Downloads (разбор):      {downloads_dir(config)}",
    ]
    if viu_install:
        lines.append(f"  Установка Вью (только код): {viu_install}")
    else:
        lines.append(f"  Запуск Вью из:           {config.root}")
    lines.extend(
        [
            "",
            "U:\\Viu — программа. U:\\Anabarra — игра и файлы для разбора.",
            "Папка U:\\Anabarra\\Anabarra (если есть) — не основной Unity-проект;",
            "рабочий проект: U:\\Anabarra\\Unity\\Anabarra.",
        ]
    )
    return "\n".join(lines)
