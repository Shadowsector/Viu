"""Краткий блок для reflect — совместные анимации."""

from __future__ import annotations

from ..config import Config
from .paths import interaction_catalog_path
from .store import InteractionCatalogStore


def format_interactions_for_reflect(config: Config, *, max_holes: int = 4) -> str:
    store = InteractionCatalogStore(interaction_catalog_path(config)).load()
    brief = store.graph_brief(max_holes=max_holes).strip()
    if not brief:
        return ""
    return (
        "--- Совместные анимации (multi-actor; docs/INTERACTION_PIPELINE.md) ---\n"
        + brief
    )
