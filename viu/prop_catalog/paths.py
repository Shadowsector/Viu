"""Каталог предметов — пути по умолчанию."""

from __future__ import annotations

from pathlib import Path

from ..anabarra_layout import (
    downloads_dir,
    ensure_layout,
    inbox_dir,
    library_root,
    mascot_archive_dir,
    project_data_dir,
)
from ..config import Config


def catalog_path(config: Config) -> Path:
    return config.data_dir / "prop_catalog.json"


__all__ = [
    "catalog_path",
    "library_root",
    "inbox_dir",
    "downloads_dir",
    "mascot_archive_dir",
    "ensure_layout",
    "project_data_dir",
]
