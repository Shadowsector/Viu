"""Каноническая структура папок на диске U: — три зоны для Вью.

U:\\Viu\\              — программа Вью, данные (.viu), Inbox (по одному паку)
U:\\Anabarra\\         — игра (Unity, Library, Animations)
U:\\Desktop Mascot\\   — архив сотен файлов (Вью НЕ сканирует сама)
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import List

from .config import Config

LIBRARY_SUBDIRS: tuple[str, ...] = (
    "Blender",
    "Lab/Models/Inbox",
    "Props/fbx",
    "Props/obj",
    "Props/glb",
    "Archives",
    "References/images",
    "Processed",
    "unsorted",
)

DEFAULT_ANABARRA_ROOT = Path("U:/Anabarra")
DEFAULT_VIU_ROOT = Path("U:/Viu")
DEFAULT_UNITY_PROJECT = DEFAULT_ANABARRA_ROOT / "Unity" / "Anabarra"
DEFAULT_MASCOT_ARCHIVE = Path("U:/Desktop Mascot")
INBOX_FOLDER_NAME = "Inbox"


def _env(name: str) -> str:
    value = os.environ.get(name)
    return value if value not in (None, "") else ""


def viu_install_root(config: Config) -> Path:
    """Где установлена Вью (U:\\Viu)."""
    raw = _env("VIU_ROOT") or ""
    if raw:
        p = Path(raw).expanduser().resolve()
        if p.name.lower() == "viu" or (p / "viu").is_dir():
            return p if p.name.lower() == "viu" else p
    if config.root.name.lower() == "viu":
        return config.root.resolve()
    if DEFAULT_VIU_ROOT.is_dir():
        return DEFAULT_VIU_ROOT.resolve()
    return config.root.resolve()


def anabarra_root(config: Config) -> Path:
    """Корень игры — U:\\Anabarra."""
    raw = _env("VIU_ANABARRA_ROOT") or getattr(config, "anabarra_root", "") or ""
    if raw:
        return Path(raw).expanduser().resolve()

    unity_raw = (config.unity_project or _env("VIU_UNITY_PROJECT") or "").strip()
    if unity_raw:
        unity = Path(unity_raw).expanduser().resolve()
        if unity.name.lower() == "anabarra" and unity.parent.name.lower() == "unity":
            return unity.parent.parent
        if (unity / "Assets").is_dir():
            return unity
        return unity.parent

    viu_root = viu_install_root(config)
    if viu_root.parent.exists():
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


def inbox_dir(config: Config) -> Path:
    """Вход: сюда кладёшь ОДИН пак для разбора. Не C:\\Downloads."""
    for key in ("VIU_INBOX_DIR", "VIU_DOWNLOADS_DIR"):
        raw = _env(key)
        if raw:
            return Path(raw).expanduser().resolve()
    cfg_raw = getattr(config, "inbox_dir", "") or getattr(config, "downloads_dir", "") or ""
    if cfg_raw:
        return Path(cfg_raw).expanduser().resolve()
    return viu_install_root(config) / INBOX_FOLDER_NAME


def downloads_dir(config: Config) -> Path:
    """Обратная совместимость — то же, что inbox_dir."""
    return inbox_dir(config)


def mascot_archive_dir(config: Config) -> Path:
    """Архив Desktop Mascot — только для ручного выбора, без автоскана."""
    raw = _env("VIU_MASCOT_DIR") or getattr(config, "mascot_dir", "") or ""
    if raw:
        return Path(raw).expanduser().resolve()
    return DEFAULT_MASCOT_ARCHIVE


def project_data_dir(config: Config) -> Path:
    explicit = _env("VIU_DATA_DIR")
    if explicit:
        return Path(explicit).expanduser().resolve()
    if config.data_dir:
        return config.data_dir.resolve()
    return viu_install_root(config) / ".viu"


def ensure_layout(config: Config) -> List[Path]:
    """Создаёт Inbox, .viu и Library."""
    roots: List[Path] = []
    for path in (config.data_dir.resolve(), inbox_dir(config), library_root(config)):
        path.mkdir(parents=True, exist_ok=True)
        roots.append(path)
    lib = library_root(config)
    for sub in LIBRARY_SUBDIRS:
        (lib / sub).mkdir(parents=True, exist_ok=True)
    return roots


def describe_layout(config: Config) -> str:
    viu = viu_install_root(config)
    mascot = mascot_archive_dir(config)
    lines = [
        "Три папки на U: (Вью не лезет на C: без явной настройки):",
        "",
        f"  1. U:\\Viu\\          программа:     {viu}",
        f"     Inbox (разбор):    {inbox_dir(config)}",
        f"     Данные (.viu):     {config.data_dir}",
        "",
        f"  2. U:\\Anabarra\\      игра:          {anabarra_root(config)}",
        f"     Unity:             {unity_project_path(config)}",
        f"     Library (склад):   {library_root(config)}",
        "",
        f"  3. Desktop Mascot   архив:         {mascot}",
        "     (сотни файлов — Вью НЕ сканирует сама; бери оттуда один пак → Inbox)",
        "",
        "Workflow: подготовил пак → U:\\Viu\\Inbox → «Разобрать Inbox» → «Разметить предметы».",
        "Подробнее: docs/ANABARRA_FOLDERS.md",
    ]
    return "\n".join(lines)
