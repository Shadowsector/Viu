"""Пути каталога анимаций."""

from __future__ import annotations

from pathlib import Path

from ..config import Config
from ..anabarra_layout import project_data_dir


def animation_catalog_path(config: Config) -> Path:
    return project_data_dir(config) / "animation_catalog.json"


def animation_staging_dir(config: Config) -> Path:
    """Промежуточный склад FBX анимаций (до Unity Animations/)."""
    raw = (config.unity_anim_staging or "").strip()
    if raw:
        return Path(raw).expanduser().resolve()
    from ..anabarra_layout import anabarra_root

    return anabarra_root(config) / "Animations"
