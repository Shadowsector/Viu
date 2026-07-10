"""Каталог анимаций Шани."""

from .categories import ANIMATION_CATEGORIES, all_category_ids, category_label
from .matcher import match_fbx_to_wish, suggest_rename_for_wish
from .models import DEFAULT_WISHES, AnimationWish
from .paths import animation_catalog_path, animation_staging_dir
from .store import AnimationCatalogStore

__all__ = [
    "ANIMATION_CATEGORIES",
    "AnimationCatalogStore",
    "AnimationWish",
    "DEFAULT_WISHES",
    "all_category_ids",
    "animation_catalog_path",
    "animation_staging_dir",
    "category_label",
    "match_fbx_to_wish",
    "suggest_rename_for_wish",
]
