"""Сортировка Inbox → библиотека Анабарры."""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Set, Tuple

from .models import ASSET_SUFFIXES
from .store import PropCatalogStore

# Расширение → подпапка внутри library_root.
DEFAULT_RULES: Dict[str, str] = {
    ".fbx": "Props/fbx",
    ".blend": "Blender",
    ".obj": "Props/obj",
    ".glb": "Props/glb",
    ".gltf": "Props/glb",
    ".png": "References/images",
    ".jpg": "References/images",
    ".jpeg": "References/images",
    ".webp": "References/images",
    ".zip": "Archives",
    ".7z": "Archives",
    ".rar": "Archives",
}

ARCHIVE_SUFFIXES = {".zip", ".7z", ".rar"}
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}

_FOLDER_RULE_PRIORITY: tuple[tuple[Set[str], str], ...] = (
    ({".blend"}, "Blender"),
    ({".fbx"}, "Props/fbx"),
    ({".obj"}, "Props/obj"),
    ({".glb", ".gltf"}, "Props/glb"),
)


@dataclass
class MovePlan:
    src: Path
    dest: Path
    kind: str = "file"


def _suffixes_in_tree(folder: Path, *, max_depth: int = 4) -> Set[str]:
    found: Set[str] = set()
    if not folder.is_dir():
        return found
    for path in folder.rglob("*"):
        if not path.is_file():
            continue
        try:
            depth = len(path.relative_to(folder).parts)
        except ValueError:
            continue
        if depth > max_depth:
            continue
        found.add(path.suffix.lower())
    return found


def _rel_for_file(ext: str, rules: Dict[str, str]) -> str:
    return rules.get(ext.lower(), "unsorted")


def _rel_for_folder(folder: Path, rules: Dict[str, str]) -> str:
    suffixes = _suffixes_in_tree(folder)
    for exts, rel in _FOLDER_RULE_PRIORITY:
        if suffixes & exts:
            return rel
    if suffixes & ARCHIVE_SUFFIXES:
        return "Archives"
    if suffixes & IMAGE_SUFFIXES:
        return "References/images"
    if suffixes & ASSET_SUFFIXES:
        return "unsorted"
    return "unsorted"


def _skip_inbox_entry(path: Path) -> bool:
    name = path.name
    if name.startswith("."):
        return True
    if name.lower() in ("desktop.ini", "thumbs.db"):
        return True
    return False


def plan_inbox_sort(
    inbox: Path,
    library_root: Path,
    rules: Dict[str, str] | None = None,
) -> List[MovePlan]:
    """План переноса верхнего уровня Inbox → Library."""
    inbox = inbox.expanduser().resolve()
    library_root = library_root.expanduser().resolve()
    rules = rules or DEFAULT_RULES
    plans: List[MovePlan] = []
    if not inbox.is_dir():
        return plans

    for path in sorted(inbox.iterdir(), key=lambda p: p.name.lower()):
        if _skip_inbox_entry(path):
            continue
        if path.is_dir():
            rel = _rel_for_folder(path, rules)
            dest = library_root / rel / path.name
            if dest.resolve() == path.resolve():
                continue
            plans.append(MovePlan(src=path, dest=dest, kind="folder"))
            continue
        if not path.is_file():
            continue
        ext = path.suffix.lower()
        rel = _rel_for_file(ext, rules)
        dest = library_root / rel / path.name
        if dest.resolve() == path.resolve():
            continue
        plans.append(MovePlan(src=path, dest=dest, kind="file"))
    return plans


# Обратная совместимость имён.
plan_downloads_sort = plan_inbox_sort


def _unique_dest(dest: Path) -> Path:
    if not dest.exists():
        return dest
    if dest.is_dir():
        stem = dest.name
        parent = dest.parent
        n = 1
        while dest.exists():
            dest = parent / f"{stem}_{n}"
            n += 1
        return dest
    stem, suffix = dest.stem, dest.suffix
    n = 1
    while dest.exists():
        dest = dest.with_name(f"{stem}_{n}{suffix}")
        n += 1
    return dest


def execute_moves(plans: List[MovePlan], *, dry_run: bool = True) -> List[str]:
    lines: List[str] = []
    for plan in plans:
        arrow = "📁" if plan.kind == "folder" else "📄"
        line = f"{arrow} {plan.src.name} → {plan.dest}"
        if dry_run:
            lines.append(f"[dry-run] {line}")
            continue
        plan.dest.parent.mkdir(parents=True, exist_ok=True)
        plan.dest = _unique_dest(plan.dest)
        shutil.move(str(plan.src), str(plan.dest))
        lines.append(f"OK {line}")
    return lines


def cleanup_empty_dirs(root: Path) -> List[str]:
    root = root.expanduser().resolve()
    if not root.is_dir():
        return []
    removed: List[str] = []
    for path in sorted(root.rglob("*"), key=lambda p: len(p.parts), reverse=True):
        if not path.is_dir() or path == root:
            continue
        try:
            if not any(path.iterdir()):
                path.rmdir()
                removed.append(str(path.relative_to(root)))
        except OSError:
            continue
    return removed


def _catalog_scan_roots(library_root: Path) -> Iterable[Path]:
    seen: Set[Path] = set()
    for rel in set(DEFAULT_RULES.values()):
        folder = (library_root / rel).resolve()
        if folder.is_dir() and folder not in seen:
            seen.add(folder)
            yield folder
    unsorted = (library_root / "unsorted").resolve()
    if unsorted.is_dir() and unsorted not in seen:
        yield unsorted


def sort_inbox_and_catalog(
    inbox: Path,
    library_root: Path,
    store: PropCatalogStore,
    *,
    dry_run: bool = False,
    blender_exe: str = "",
) -> Tuple[List[str], int]:
    """Переместить из Inbox в Library и добавить 3D в каталог."""
    from .scanner import scan_folder

    plans = plan_inbox_sort(inbox, library_root)
    lines = execute_moves(plans, dry_run=dry_run)
    new_in_catalog = 0
    if not dry_run:
        for rel in cleanup_empty_dirs(inbox):
            lines.append(f"очистка Inbox: {rel}")
        for folder in _catalog_scan_roots(library_root):
            n, _ = scan_folder(folder, store, recursive=True, blender_exe=blender_exe)
            new_in_catalog += n
    return lines, new_in_catalog


sort_downloads_and_catalog = sort_inbox_and_catalog
