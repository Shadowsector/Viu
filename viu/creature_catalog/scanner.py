"""Скан Inbox существ → creature_catalog."""

from __future__ import annotations

from pathlib import Path
from typing import List, Tuple

from ..config import Config
from .models import (
    ASSET_SUFFIXES,
    STATUS_NEW,
    CreatureEntry,
    creature_id_for_path,
    suggest_locomotion_from_name,
    suggest_size_from_name,
)
from .paths import creature_catalog_path, creatures_inbox_dir
from .store import CreatureCatalogStore


def _find_textures_nearby(asset: Path) -> Tuple[bool, str]:
    parent = asset.parent
    for name in ("textures", "Textures", "texture", "maps", "Maps"):
        d = parent / name
        if d.is_dir():
            return True, str(d)
    # sibling folder with same stem
    stem_dir = parent / asset.stem
    if stem_dir.is_dir() and any(stem_dir.glob("*.png")):
        return True, str(stem_dir)
    return False, ""


def scan_creatures_inbox(config: Config) -> Tuple[int, int, str]:
    """Добавить новые файлы из Creatures/Inbox (+ опционально Lab/Models/Inbox).

    Returns: (added, total, message)
    """
    store = CreatureCatalogStore(creature_catalog_path(config)).load()
    inbox = creatures_inbox_dir(config)
    roots = [inbox]
    # также lab models — часто туда кладут всё подряд
    try:
        from ..lab.paths import models_inbox_dir

        roots.append(models_inbox_dir(config))
    except Exception:
        pass

    added = 0
    seen_paths = {Path(e.path).resolve() for e in store.all() if e.path}

    for root in roots:
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*")):
            if not path.is_file():
                continue
            if path.suffix.lower() not in ASSET_SUFFIXES:
                continue
            # skip prepared / lineup outputs
            if "_prepared" in path.stem.lower() or "lineup" in path.parts:
                continue
            try:
                resolved = path.resolve()
            except OSError:
                continue
            if resolved in seen_paths:
                continue
            cid = creature_id_for_path(resolved)
            if store.get(cid):
                continue
            ext_tex, tex_dir = _find_textures_nearby(resolved)
            guesses = suggest_size_from_name(resolved.stem)
            loco = suggest_locomotion_from_name(resolved.stem)
            entry = CreatureEntry(
                id=cid,
                path=str(resolved),
                name=resolved.stem,
                locomotion=loco,
                textures_external=ext_tex,
                textures_dir=tex_dir,
                notes=(
                    f"кандидаты size: {', '.join(guesses) or '—'}"
                    if guesses
                    else "size: укажи вручную"
                ),
                tags=list(guesses),
            )
            # не ставим size_class автоматически — только подсказка в tags/notes
            store.upsert(entry)
            seen_paths.add(resolved)
            added += 1

    store.save()
    msg = (
        f"Скан существ: +{added} новых. Всего в каталоге: {len(store.all())}.\n"
        f"Inbox: {inbox}\n"
        f"{store.summary_text()}"
    )
    return added, len(store.all()), msg


def list_size_classes_text() -> str:
    from .models import QUAD_SIZE_CLASSES, SIZE_CLASSES

    lines = ["Классы роста (target ± допуск):", "", "Бипеды / антропоморфы:"]
    for sid, spec in SIZE_CLASSES.items():
        lines.append(
            f"  • `{sid}` — {spec['label_ru']}: "
            f"target {spec['target_m']}m ({spec['min_m']}–{spec['max_m']}) — {spec['notes']}"
        )
    lines.append("")
    lines.append("Четвероногие (высота):")
    for sid, spec in QUAD_SIZE_CLASSES.items():
        lines.append(
            f"  • `{sid}` — {spec['label_ru']}: "
            f"target {spec['target_m']}m ({spec['min_m']}–{spec['max_m']}) — {spec['notes']}"
        )
    return "\n".join(lines)
