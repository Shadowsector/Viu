"""Сортировка Downloads и прочего «хлама» в библиотеку Анабарры."""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple

from .models import ASSET_SUFFIXES, PropEntry, prop_id_for_path
from .store import PropCatalogStore

# Расширение → подпапка внутри library_root (относительный путь).
DEFAULT_RULES: Dict[str, str] = {
    ".fbx": "Props/incoming/fbx",
    ".blend": "Blender/incoming",
    ".obj": "Props/incoming/obj",
    ".glb": "Props/incoming/glb",
    ".gltf": "Props/incoming/glb",
    ".png": "References/images",
    ".jpg": "References/images",
    ".jpeg": "References/images",
    ".webp": "References/images",
    ".zip": "Archives/incoming",
    ".7z": "Archives/incoming",
    ".rar": "Archives/incoming",
}


@dataclass
class MovePlan:
    src: Path
    dest: Path


def plan_downloads_sort(
    downloads: Path,
    library_root: Path,
    rules: Dict[str, str] | None = None,
) -> List[MovePlan]:
    downloads = downloads.expanduser().resolve()
    library_root = library_root.expanduser().resolve()
    rules = rules or DEFAULT_RULES
    plans: List[MovePlan] = []
    if not downloads.is_dir():
        return plans
    for path in sorted(downloads.iterdir()):
        if not path.is_file():
            continue
        ext = path.suffix.lower()
        rel = rules.get(ext)
        if not rel:
            rel = "Incoming/unsorted"
        dest_dir = library_root / rel
        dest = dest_dir / path.name
        if dest.resolve() == path.resolve():
            continue
        plans.append(MovePlan(src=path, dest=dest))
    return plans


def execute_moves(plans: List[MovePlan], *, dry_run: bool = True) -> List[str]:
    lines: List[str] = []
    for plan in plans:
        line = f"{plan.src.name} → {plan.dest}"
        if dry_run:
            lines.append(f"[dry-run] {line}")
            continue
        plan.dest.parent.mkdir(parents=True, exist_ok=True)
        if plan.dest.exists():
            stem, suffix = plan.dest.stem, plan.dest.suffix
            n = 1
            while plan.dest.exists():
                plan.dest = plan.dest.with_name(f"{stem}_{n}{suffix}")
                n += 1
        shutil.move(str(plan.src), str(plan.dest))
        lines.append(f"OK {line}")
    return lines


def sort_downloads_and_catalog(
    downloads: Path,
    library_root: Path,
    store: PropCatalogStore,
    *,
    dry_run: bool = False,
    blender_exe: str = "",
) -> Tuple[List[str], int]:
    """Переместить файлы из Downloads и добавить 3D-ассеты в каталог."""
    from .scanner import scan_folder

    plans = plan_downloads_sort(downloads, library_root)
    lines = execute_moves(plans, dry_run=dry_run)
    new_in_catalog = 0
    if not dry_run:
        for rel_dir in set(DEFAULT_RULES.values()):
            folder = library_root / rel_dir
            if folder.is_dir():
                n, _ = scan_folder(folder, store, recursive=False, blender_exe=blender_exe)
                new_in_catalog += n
        unsorted = library_root / "Incoming/unsorted"
        if unsorted.is_dir():
            n, _ = scan_folder(unsorted, store, recursive=False, blender_exe=blender_exe)
            new_in_catalog += n
    return lines, new_in_catalog
