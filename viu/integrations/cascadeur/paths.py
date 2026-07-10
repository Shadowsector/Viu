"""Пути FBX для Cascadeur ↔ Unity."""

from __future__ import annotations

from pathlib import Path

from ...anabarra_layout import library_root
from ...config import Config


def cascadeur_inbox(config: Config) -> Path:
    """Входящие FBX для правки в Cascadeur."""
    root = library_root(config) / "Cascadeur" / "Inbox"
    root.mkdir(parents=True, exist_ok=True)
    return root


def cascadeur_export(config: Config) -> Path:
    """Готовые из Cascadeur → Unity Animations."""
    explicit = (config.unity_anim_staging or "").strip()
    if explicit:
        p = Path(explicit).expanduser()
        p.mkdir(parents=True, exist_ok=True)
        return p
    root = library_root(config).parent / "Animations"
    root.mkdir(parents=True, exist_ok=True)
    return root
