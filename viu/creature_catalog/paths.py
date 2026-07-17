"""Пути каталога существ."""

from __future__ import annotations

import os
from pathlib import Path

from ..anabarra_layout import library_root, project_data_dir
from ..config import Config


def creature_catalog_path(config: Config) -> Path:
    return project_data_dir(config) / "creature_catalog.json"


def creatures_inbox_dir(config: Config) -> Path:
    """Входящие модели монстров / существ."""
    env = os.environ.get("VIU_CREATURES_INBOX", "").strip()
    if env:
        p = Path(env).expanduser()
    else:
        p = library_root(config) / "Lab" / "Creatures" / "Inbox"
    p.mkdir(parents=True, exist_ok=True)
    readme = p / "README.txt"
    if not readme.is_file():
        readme.write_text(
            "Inbox существ (монстры, четвероногие, аморфы).\n"
            "Положи .blend / .fbx / .glb. Текстуры — рядом (textures/) или внутри blend.\n"
            "Вью: creature_catalog_scan → разметка size_class → lineup рядом с Шаней.\n",
            encoding="utf-8",
        )
    return p


def creatures_processed_dir(config: Config) -> Path:
    p = library_root(config) / "Lab" / "Creatures" / "Processed"
    p.mkdir(parents=True, exist_ok=True)
    return p


def creatures_lineup_dir(config: Config) -> Path:
    p = library_root(config) / "Lab" / "Creatures" / "Lineup"
    p.mkdir(parents=True, exist_ok=True)
    return p


def girl_sockets_doc_path(config: Config) -> Path:
    return project_data_dir(config) / "girl_sockets.json"
