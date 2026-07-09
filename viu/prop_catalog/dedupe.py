"""Дубликаты одного меша в разных .blend — без агрессивного «объединения»."""

from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path
from typing import List

from .models import PropEntry
from .store import PropCatalogStore


def asset_pack_key(path: Path) -> str:
    """Old Stables_1 + Old Stables_prepared → old stables."""
    stem = path.stem.lower()
    stem = re.sub(r"_prepared(_\d+)?$", "", stem)
    stem = re.sub(r"_\d+$", "", stem)
    return stem


def source_priority(source_path: str) -> tuple[int, str]:
    p = Path(source_path)
    name = p.name.lower()
    if "_prepared" in name or "processed" in str(p).lower():
        return (0, source_path)
    if "library" in str(p).lower() and "blender" in str(p).lower():
        return (2, source_path)
    return (1, source_path)


def mesh_group_key(entry: PropEntry) -> tuple[str, str] | None:
    if not entry.mesh_name:
        return None
    return (asset_pack_key(Path(entry.source_path)), entry.mesh_name.lower())


def duplicate_siblings(store: PropCatalogStore, entry: PropEntry) -> List[PropEntry]:
    key = mesh_group_key(entry)
    if not key:
        return [entry]
    return [e for e in store.items.values() if mesh_group_key(e) == key]


def pick_canonical_entry(entries: List[PropEntry]) -> PropEntry:
    """Какую строку показывать в очереди — prepared, иначе с разметкой пользователя."""
    if not entries:
        raise ValueError("empty entries")
    reviewed = [e for e in entries if e.reviewed and is_user_review(e)]
    if reviewed:
        reviewed.sort(key=lambda e: source_priority(e.source_path))
        return reviewed[0]
    entries = sorted(entries, key=lambda e: source_priority(e.source_path))
    return entries[0]


def is_user_review(entry: PropEntry) -> bool:
    """Отличить ручную разметку от auto-shell / auto-undefined."""
    if not entry.reviewed:
        return False
    if entry.role == "interactive":
        return bool(entry.interactions or entry.weight_kg is not None or entry.can_lift)
    if entry.role == "shell":
        return bool(entry.interactions or entry.can_climb)
    if entry.role in ("decor", "atmosphere", "undefined"):
        return False
    return True


def pending_for_display(store: PropCatalogStore) -> List[PropEntry]:
    raw_pending = [e for e in store.items.values() if not e.reviewed]
    file_level = [e for e in raw_pending if not e.mesh_name]
    mesh_pending = [e for e in raw_pending if e.mesh_name]

    groups: dict[tuple[str, str], list[PropEntry]] = defaultdict(list)
    for e in mesh_pending:
        key = mesh_group_key(e)
        if key:
            groups[key].append(e)

    shown = [pick_canonical_entry(g) for g in groups.values()]
    return sorted(
        shown + file_level,
        key=lambda e: (
            e.source_path.lower(),
            e.collection.lower(),
            e.mesh_name.lower(),
        ),
    )


def propagate_entry_to_duplicates(store: PropCatalogStore, entry: PropEntry) -> int:
    """После «Сохранить» — та же разметка на _1.blend и _prepared.blend."""
    if not entry.reviewed or not entry.mesh_name:
        return 0
    n = 0
    for sib in duplicate_siblings(store, entry):
        if sib.id == entry.id:
            continue
        data = entry.to_dict()
        data["id"] = sib.id
        data["source_path"] = sib.source_path
        store.upsert(PropEntry.from_dict(data), save=False)
        n += 1
    if n:
        store.save()
    return n


def repair_overmerged_duplicates(store: PropCatalogStore) -> int:
    """Откатить ложные «Дубликат — reviewed» после старого auto-merge."""
    groups: dict[tuple[str, str], list[PropEntry]] = defaultdict(list)
    for entry in store.items.values():
        key = mesh_group_key(entry)
        if key:
            groups[key].append(entry)

    fixed = 0
    for entries in groups.values():
        if len(entries) < 2:
            continue
        for e in entries:
            if not e.reviewed or "Дубликат —" not in e.notes:
                continue
            if is_user_review(e):
                continue
            canonical = pick_canonical_entry(entries)
            if e.id == canonical.id:
                continue
            if is_user_review(canonical):
                continue
            e.reviewed = False
            e.notes = re.sub(r"\n?Дубликат —[^\n]*", "", e.notes).strip()
            store.upsert(e, save=False)
            fixed += 1
    if fixed:
        store.save()
    return fixed
