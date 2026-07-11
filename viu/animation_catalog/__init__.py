"""Каталог анимаций Шани."""

from .categories import ANIMATION_CATEGORIES, all_category_ids, category_label
from .matcher import match_fbx_to_wish, suggest_rename_for_wish
from .models import (
    ANIMATION_SCOPES,
    DEFAULT_SCOPE,
    DEFAULT_WISHES,
    AnimationImportReview,
    AnimationWish,
    applies_to_shanya,
    normalize_scope,
    scope_save_warning,
)
from .paths import animation_catalog_path, animation_staging_dir
from .review_gui import open_animation_review
from .store import AnimationCatalogStore

__all__ = [
    "ANIMATION_CATEGORIES",
    "AnimationCatalogStore",
    "AnimationWish",
    "DEFAULT_SCOPE",
    "DEFAULT_WISHES",
    "applies_to_shanya",
    "normalize_scope",
    "scope_save_warning",
    "all_category_ids",
    "animation_catalog_path",
    "animation_staging_dir",
    "category_label",
    "match_fbx_to_wish",
    "open_animation_review",
    "suggest_rename_for_wish",
]
