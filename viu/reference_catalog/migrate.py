"""Перенос референсов из старых путей → Inbox/references/."""

from __future__ import annotations

import shutil
from pathlib import Path

from ..anabarra_layout import inbox_dir, library_root
from ..config import Config
from .scanner import _IMAGE, _VIDEO
from .paths import references_inbox_dir

_LEGACY_REL = (
    "References/images",
    "References",
    "Lab/Refs/kept",
    "Lab/Refs",
)


def _is_ref_file(path: Path) -> bool:
    ext = path.suffix.lower()
    return ext in _IMAGE or ext in _VIDEO


def _unique_dest(dest_dir: Path, name: str) -> Path:
    dest = dest_dir / name
    if not dest.exists():
        return dest
    stem = Path(name).stem
    suffix = Path(name).suffix
    n = 2
    while True:
        candidate = dest_dir / f"{stem}_migrated_{n}{suffix}"
        if not candidate.exists():
            return candidate
        n += 1


def migrate_legacy_references(
    config: Config,
    *,
    copy: bool = True,
) -> tuple[int, list[str]]:
    """Скопировать/перенести картинки и видео из старых папок в Inbox/references/."""
    dest_dir = references_inbox_dir(config)
    dest_dir.mkdir(parents=True, exist_ok=True)
    moved = 0
    notes: list[str] = []

    sources: list[Path] = []
    try:
        lib = library_root(config)
        for rel in _LEGACY_REL:
            p = lib / Path(rel)
            if p.is_dir():
                sources.append(p)
    except OSError:
        pass

    # Картинки в корне Inbox (до подпапки references/)
    try:
        root_inbox = inbox_dir(config)
        if root_inbox.is_dir():
            sources.append(root_inbox)
    except OSError:
        pass

    seen_dest: set[str] = set()
    seen_files: set[tuple[str, int]] = set()
    for src_root in sources:
        if not src_root.is_dir():
            continue
        # Корень Inbox — только файлы верхнего уровня, не подпапки
        if src_root.name.lower() == "inbox":
            candidates = [p for p in src_root.iterdir() if p.is_file()]
        else:
            candidates = [p for p in src_root.rglob("*") if p.is_file()]
        for path in candidates:
            if path.name.lower() == "readme.txt":
                continue
            if not _is_ref_file(path):
                continue
            try:
                file_key = (path.name.lower(), path.stat().st_size)
            except OSError:
                continue
            if file_key in seen_files:
                continue
            if path.parent.resolve() == dest_dir.resolve():
                continue
            key = path.name.lower()
            if key in seen_dest:
                key = f"{path.stem}_{path.stat().st_size}{path.suffix}".lower()
            dest = _unique_dest(dest_dir, path.name)
            if dest.name.lower() in seen_dest:
                continue
            try:
                if copy:
                    shutil.copy2(path, dest)
                else:
                    shutil.move(str(path), str(dest))
                seen_dest.add(dest.name.lower())
                seen_files.add(file_key)
                moved += 1
                notes.append(f"{path} → {dest.name}")
            except OSError:
                continue

    if moved:
        notes.insert(0, f"Миграция референсов: +{moved} в {dest_dir}")
    return moved, notes
