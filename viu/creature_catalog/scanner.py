"""Скан Inbox существ → creature_catalog."""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Tuple

from ..config import Config
from .models import (
    ASSET_SUFFIXES,
    STATUS_NEW,
    CreatureEntry,
    creature_id_for_path,
    creature_identity_from_inbox_path,
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
    """Добавить новые файлы из Lab/Creatures/Inbox (единый inbox существ).

    Returns: (added, total, message)

    Важно: считается **каждый файл** (.fbx/.blend/.glb…), рекурсивно.
    Models/Inbox — только Шаня / humanoid lab, не сканируется как существо.
  """
    store = CreatureCatalogStore(creature_catalog_path(config)).load()
    inbox = creatures_inbox_dir(config)
    roots = [inbox]

    added = 0
    per_root_added: Dict[str, int] = {}
    per_root_seen: Dict[str, int] = {}
    seen_paths = {Path(e.path).resolve() for e in store.all() if e.path}

    for root in roots:
        root_key = str(root)
        per_root_added.setdefault(root_key, 0)
        per_root_seen.setdefault(root_key, 0)
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
            per_root_seen[root_key] = per_root_seen.get(root_key, 0) + 1
            cid = creature_id_for_path(resolved)
            existing = store.get(cid)
            if existing:
                if not existing.prep_ok:
                    name, slug = creature_identity_from_inbox_path(resolved, inbox)
                    existing.name = name
                    existing.slug = slug
                    store.upsert(existing)
                seen_paths.add(resolved)
                continue
            if resolved in seen_paths:
                continue
            ext_tex, tex_dir = _find_textures_nearby(resolved)
            display_name, slug = creature_identity_from_inbox_path(resolved, inbox)
            guesses = suggest_size_from_name(display_name)
            loco = suggest_locomotion_from_name(display_name)
            entry = CreatureEntry(
                id=cid,
                path=str(resolved),
                name=display_name,
                slug=slug,
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
            per_root_added[root_key] = per_root_added.get(root_key, 0) + 1

    store.save()
    breakdown = []
    for root in roots:
        rk = str(root)
        breakdown.append(
            f"  • {rk}\n"
            f"    файлов-кандидатов: {per_root_seen.get(rk, 0)}, "
            f"+новых в этот скан: {per_root_added.get(rk, 0)}"
        )
    msg = (
        f"Скан существ: +{added} новых. Всего в каталоге: {len(store.all())}.\n"
        f"Считается каждый .fbx/.blend/.glb/.obj (рекурсивно), не «папка = 1 модель».\n"
        f"Откуда брали:\n" + "\n".join(breakdown) + "\n"
        f"{store.summary_text()}"
    )
    return added, len(store.all()), msg


def list_size_classes_text() -> str:
    from .models import QUAD_SIZE_CLASSES, SIZE_CLASSES, SPECIAL_SIZE_CLASSES

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
    lines.append("")
    lines.append("Особые (мимик / слизень / насекомое / щупальца) — locomotion отдельно:")
    for sid, spec in SPECIAL_SIZE_CLASSES.items():
        lines.append(
            f"  • `{sid}` — {spec['label_ru']}: "
            f"target {spec['target_m']}m ({spec['min_m']}–{spec['max_m']}) — {spec['notes']}"
        )
    return "\n".join(lines)
