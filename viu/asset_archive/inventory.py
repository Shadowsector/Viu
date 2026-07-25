"""Инвентаризация архива: только top-level или один выбранный пак.

Вью НЕ делает rglob по всему Desktop Mascot.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ..anabarra_layout import inbox_dir, mascot_archive_dir
from ..config import Config
from ..inbox_layout import ensure_inbox_readme
from .layout import (
    MASCOT_TOP_CATEGORIES,
    classify_mascot_category,
    inbox_subdir_for_category,
    missing_mascot_categories,
)

# Суффиксы, которые считаем ассетами при инвентаре одного пака.
PACK_ASSET_SUFFIXES = {
    ".blend",
    ".fbx",
    ".obj",
    ".glb",
    ".gltf",
    ".png",
    ".jpg",
    ".jpeg",
    ".tif",
    ".tiff",
    ".exr",
    ".zip",
    ".7z",
    ".rar",
}


def inventory_archive_top(config: Config, archive: Optional[Path] = None) -> Dict[str, Any]:
    """Только имена папок верхнего уровня + наличие канонических категорий.

    Никакого рекурсивного обхода файлов.
    """
    root = Path(archive) if archive is not None else mascot_archive_dir(config)
    result: Dict[str, Any] = {
        "root": str(root),
        "exists": root.is_dir(),
        "auto_scan": False,
        "canonical_categories": list(MASCOT_TOP_CATEGORIES),
        "present_categories": [],
        "missing_categories": [],
        "other_top_dirs": [],
        "top_files": [],
    }
    if not root.is_dir():
        result["missing_categories"] = list(MASCOT_TOP_CATEGORIES)
        return result

    top_dirs = sorted([p.name for p in root.iterdir() if p.is_dir()], key=str.lower)
    top_files = sorted([p.name for p in root.iterdir() if p.is_file()], key=str.lower)
    present: List[str] = []
    other: List[str] = []
    for name in top_dirs:
        cat = classify_mascot_category(name)
        if cat and name == cat:
            present.append(cat)
        elif cat:
            present.append(cat)
            other.append(f"{name}→{cat}")
        else:
            other.append(name)
    # Нормализуем present по канону
    present_set = set()
    for name in top_dirs:
        cat = classify_mascot_category(name)
        if cat:
            present_set.add(cat)
    result["present_categories"] = [c for c in MASCOT_TOP_CATEGORIES if c in present_set]
    result["missing_categories"] = missing_mascot_categories(root)
    result["other_top_dirs"] = [n for n in top_dirs if not classify_mascot_category(n)]
    result["top_files"] = top_files[:40]
    return result


def inventory_pack(pack_dir: Path, *, max_files: int = 200) -> Dict[str, Any]:
    """Рекурсивный учёт одного пака (то, что Ден скопировал / выбрал)."""
    root = Path(pack_dir)
    out: Dict[str, Any] = {
        "path": str(root),
        "exists": root.is_dir(),
        "asset_count": 0,
        "by_suffix": {},
        "samples": [],
        "truncated": False,
    }
    if not root.is_dir():
        return out
    by_suffix: Dict[str, int] = {}
    samples: List[str] = []
    count = 0
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        suf = path.suffix.lower()
        if suf not in PACK_ASSET_SUFFIXES:
            continue
        count += 1
        by_suffix[suf] = by_suffix.get(suf, 0) + 1
        if len(samples) < 30:
            try:
                samples.append(str(path.relative_to(root)))
            except ValueError:
                samples.append(path.name)
        if count >= max_files:
            out["truncated"] = True
            break
    out["asset_count"] = count
    out["by_suffix"] = dict(sorted(by_suffix.items()))
    out["samples"] = samples
    return out


def stage_pack_to_inbox(
    config: Config,
    source: Path,
    *,
    category: str = "Women",
    dest_name: str = "",
) -> Tuple[bool, str, Path]:
    """Скопировать один пак/файл из архива в Inbox (не двигает оригинал)."""
    src = Path(source)
    if not src.exists():
        return False, f"нет источника: {src}", Path()
    ensure_inbox_readme(config)
    sub = inbox_subdir_for_category(category)
    if sub is None:
        return False, f"неизвестная категория: {category}", Path()
    base = inbox_dir(config)
    dest_root = base / sub if sub else base
    dest_root.mkdir(parents=True, exist_ok=True)
    name = dest_name or src.name
    dest = dest_root / name
    if dest.exists():
        return False, f"уже есть в Inbox: {dest}", dest
    try:
        if src.is_dir():
            shutil.copytree(src, dest)
        else:
            shutil.copy2(src, dest)
    except OSError as exc:
        return False, f"не скопировалось: {exc}", Path()
    return True, f"в Inbox: {dest}", dest


def describe_archive_brief(config: Config) -> str:
    inv = inventory_archive_top(config)
    lines = [
        f"Архив: {inv['root']}",
        f"  существует: {'да' if inv['exists'] else 'нет'}",
        "  автоскан: нет (только top-level / один пак)",
        f"  категории на месте: {', '.join(inv['present_categories']) or '—'}",
    ]
    if inv["missing_categories"]:
        lines.append(f"  нет папок: {', '.join(inv['missing_categories'])}")
    if inv["other_top_dirs"]:
        lines.append(f"  прочее top: {', '.join(inv['other_top_dirs'][:12])}")
    return "\n".join(lines)
