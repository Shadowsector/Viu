"""Каталог предметов — пути по умолчанию."""

from __future__ import annotations

from pathlib import Path

from ..config import Config


def catalog_path(config: Config) -> Path:
    return config.data_dir / "prop_catalog.json"


def library_root(config: Config) -> Path:
    raw = getattr(config, "library_root", "") or ""
    if raw:
        return Path(raw).expanduser().resolve()
    unity = (config.unity_project or "").strip()
    if unity:
        return Path(unity).expanduser().resolve().parent / "Library"
    return config.root / "Anabarra" / "Library"


def downloads_dir(config: Config) -> Path:
    raw = getattr(config, "downloads_dir", "") or ""
    if raw:
        return Path(raw).expanduser().resolve()
    return Path.home() / "Downloads"
