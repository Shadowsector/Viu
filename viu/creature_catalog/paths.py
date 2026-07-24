"""Пути каталога существ."""

from __future__ import annotations

import os
from pathlib import Path

from ..anabarra_layout import library_root, project_data_dir
from ..inbox_layout import ensure_inbox_readme, inbox_creatures_dir
from ..config import Config


def creature_catalog_path(config: Config) -> Path:
    return project_data_dir(config) / "creature_catalog.json"


def creatures_inbox_dir(config: Config) -> Path:
    """Входящие модели монстров / существ — U:\\Anabarra\\Inbox\\creatures."""
    env = os.environ.get("VIU_CREATURES_INBOX", "").strip()
    if env:
        p = Path(env).expanduser()
    else:
        ensure_inbox_readme(config)
        p = inbox_creatures_dir(config)
    p.mkdir(parents=True, exist_ok=True)
    readme = p / "README.txt"
    if not readme.is_file():
        readme.write_text(
            "Единый Inbox живых существ (волки, гоблины, humanoid, …).\n"
            "Положи .blend / .fbx / .glb. Текстуры — рядом (textures/) или внутри blend.\n"
            "Вью: «Подготовить модели» → «Студия существ» в Blender.\n"
            "Пропсы (мебель) — отдельный Prop Inbox.\n"
            "Шаня для студии: лучше Shanya.fbx в CascadeurReady (не rig-.blend).\n",
            encoding="utf-8",
        )
    return p


def creatures_processed_dir(config: Config) -> Path:
    p = library_root(config) / "Lab" / "Creatures" / "Processed"
    p.mkdir(parents=True, exist_ok=True)
    return p


def creature_processed_slug_dir(config: Config, slug: str) -> Path:
    """PNG front/side после lineup: Processed/<slug>/."""
    s = (slug or "creature").strip().strip("/\\") or "creature"
    p = creatures_processed_dir(config) / s
    p.mkdir(parents=True, exist_ok=True)
    return p


def creatures_studio_dir(config: Config) -> Path:
    p = library_root(config) / "Lab" / "Creatures" / "Studio"
    p.mkdir(parents=True, exist_ok=True)
    return p


def creatures_prep_dir(config: Config) -> Path:
    p = library_root(config) / "Lab" / "Creatures" / "Prep"
    p.mkdir(parents=True, exist_ok=True)
    return p


def creatures_prepared_dir(config: Config) -> Path:
    p = library_root(config) / "Lab" / "Creatures" / "Prepared"
    p.mkdir(parents=True, exist_ok=True)
    return p


def creatures_wardrobe_dir(config: Config) -> Path:
    p = library_root(config) / "Lab" / "Creatures" / "Wardrobe"
    p.mkdir(parents=True, exist_ok=True)
    return p


def creature_prepared_slug_dir(config: Config, slug: str, *, ensure: bool = False) -> Path:
    s = (slug or "creature").strip().strip("/\\") or "creature"
    d = creatures_prepared_dir(config) / s
    if ensure:
        d.mkdir(parents=True, exist_ok=True)
    return d


def creature_texture_manifest_path(config: Config, slug: str, *, stage: str = "prepared") -> Path:
    if stage == "processed":
        return creature_processed_slug_dir(config, slug) / "texture_manifest.json"
    return creature_prepared_slug_dir(config, slug, ensure=True) / "texture_manifest.json"


def creature_outfit_sets_path(config: Config, slug: str) -> Path:
    return creature_prepared_slug_dir(config, slug, ensure=True) / "outfit_sets.json"


def creature_prepared_blend_path(config: Config, slug: str, *, ensure_dir: bool = False) -> Path:
    s = (slug or "creature").strip().strip("/\\") or "creature"
    d = creature_prepared_slug_dir(config, s, ensure=ensure_dir)
    return d / f"{s}_prepared.blend"


def creature_ready_fbx_path(config: Config, slug: str) -> Path:
    d = creature_processed_slug_dir(config, slug)
    s = (slug or "creature").strip().strip("/\\") or "creature"
    return d / f"{s}_ready.fbx"


def creature_ready_blend_path(config: Config, slug: str) -> Path:
    """Эталонный очищенный .blend после ручной правки в студии."""
    d = creature_processed_slug_dir(config, slug)
    s = (slug or "creature").strip().strip("/\\") or "creature"
    return d / f"{s}_ready.blend"


def creatures_lineup_dir(config: Config) -> Path:
    p = library_root(config) / "Lab" / "Creatures" / "Lineup"
    p.mkdir(parents=True, exist_ok=True)
    return p


def girl_sockets_doc_path(config: Config) -> Path:
    return project_data_dir(config) / "girl_sockets.json"
