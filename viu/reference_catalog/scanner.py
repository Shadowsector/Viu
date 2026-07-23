"""Скан Inbox/references → reference_catalog.json."""

from __future__ import annotations

import re
from pathlib import Path

from ..config import Config
from .models import ReferenceEntry
from .paths import reference_catalog_path, references_inbox_dir
from .store import ReferenceCatalogStore

_IMAGE = frozenset({".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif"})
_VIDEO = frozenset({".mp4", ".webm", ".mov", ".mkv", ".avi"})


def _slugify(name: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9_\-]+", "_", name.strip())
    s = re.sub(r"_+", "_", s).strip("_").lower()
    return s or "ref"


def _entry_id(path: Path) -> str:
    return _slugify(path.stem)


def scan_references_inbox(config: Config) -> tuple[int, int]:
    """Вернуть (новых, всего в каталоге)."""
    try:
        from .migrate import migrate_legacy_references

        migrate_legacy_references(config, copy=True)
    except OSError:
        pass
    inbox = references_inbox_dir(config)
    store = ReferenceCatalogStore(reference_catalog_path(config)).load()
    known_paths = {e.path.lower() for e in store.all_entries()}
    added = 0
    for path in sorted(inbox.rglob("*")):
        if not path.is_file():
            continue
        if path.name.lower() == "readme.txt":
            continue
        ext = path.suffix.lower()
        if ext not in _IMAGE and ext not in _VIDEO:
            continue
        key = str(path.resolve()).lower()
        if key in known_paths:
            continue
        eid = _entry_id(path)
        n = 2
        while store.get(eid):
            eid = f"{_entry_id(path)}_{n}"
            n += 1
        kind = "video" if ext in _VIDEO else "image"
        store.upsert(
            ReferenceEntry(
                id=eid,
                path=str(path.resolve()),
                kind=kind,
                title=path.stem.replace("_", " "),
            )
        )
        known_paths.add(key)
        added += 1
    if added:
        store.save()
    return added, len(store.all_entries())
