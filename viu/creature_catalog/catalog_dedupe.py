"""Ранжирование записей каталога для дедупа."""

from __future__ import annotations

from .models import CreatureEntry


def catalog_entry_rank(e: CreatureEntry) -> int:
    score = 0
    if e.prep_ok:
        score += 32
    if e.prepared_path:
        score += 16
    if e.outfit_sets_path:
        score += 8
    if (e.path or "").lower().endswith(".blend"):
        score += 4
    if e.photo_ok:
        score += 2
    return score
