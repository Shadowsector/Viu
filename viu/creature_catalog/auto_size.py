"""Авторазметка size_class по имени файла (уверенные догадки)."""

from __future__ import annotations

from pathlib import Path
from typing import List, Tuple

from .models import (
    suggest_locomotion_from_name,
    suggest_size_from_name,
)
from .store import CreatureCatalogStore


def _default_loco(size: str, entry_loco: str, name: str) -> str:
    if entry_loco and entry_loco != "unknown":
        return entry_loco
    guessed = suggest_locomotion_from_name(name)
    if guessed != "unknown":
        return guessed
    if size.startswith("quad_"):
        return "quadruped"
    return "biped"


def auto_apply_size_guesses(store: CreatureCatalogStore) -> Tuple[int, List[str]]:
    """Проставить size, если по имени ровно один кандидат.

    Returns: (applied_count, human lines)
    """
    lines: List[str] = []
    applied = 0
    for e in list(store.pending()):
        guesses = suggest_size_from_name(e.name)
        if not guesses and e.tags:
            guesses = [t for t in e.tags if t]
        # только одна уверенная догадка
        if len(guesses) != 1:
            continue
        size = guesses[0]
        loco = _default_loco(size, e.locomotion, e.name)
        updated = store.set_size(
            e.id,
            size,
            locomotion=loco,
            notes="auto: по имени файла",
        )
        if updated is None:
            continue
        applied += 1
        lines.append(f"  • {e.name} → {size} / {loco}")
    if applied:
        store.save()
    return applied, lines


def apply_size_to_same_stem(
    store: CreatureCatalogStore,
    source_id: str,
    size: str,
    *,
    locomotion: str = "",
    nsfw: bool = False,
    target_m: float | None = None,
) -> int:
    """Той же разметкой пометить другие файлы с тем же stem (fbx+blend и т.п.)."""
    src = store.get(source_id)
    if src is None:
        return 0
    stem = Path(src.path).stem.lower()
    extra = 0
    for e in list(store.all()):
        if e.id == source_id:
            continue
        if Path(e.path).stem.lower() != stem:
            continue
        updated = store.set_size(
            e.id,
            size,
            locomotion=locomotion or src.locomotion,
            target_m=target_m if target_m is not None else (src.target_height_m or None),
        )
        if updated is None:
            continue
        if nsfw:
            updated.nsfw_capable = True
            store.upsert(updated)
        extra += 1
    return extra
