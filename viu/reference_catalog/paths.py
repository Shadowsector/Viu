"""Пути каталога референсов."""

from __future__ import annotations

from ..anabarra_layout import project_data_dir
from ..config import Config
from ..inbox_layout import inbox_references_dir, ensure_inbox_readme


def reference_catalog_path(config: Config):
    from pathlib import Path

    return project_data_dir(config) / "reference_catalog.json"


def references_inbox_dir(config: Config):
    ensure_inbox_readme(config)
    return inbox_references_dir(config)
