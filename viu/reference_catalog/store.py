"""reference_catalog.json — плоский список, без подпапок в JSON."""

from __future__ import annotations

import json
from pathlib import Path

from .models import ReferenceEntry


class ReferenceCatalogStore:
    def __init__(self, path: Path) -> None:
        self.path = path.expanduser().resolve()
        self._items: dict[str, ReferenceEntry] = {}

    def load(self) -> "ReferenceCatalogStore":
        if self.path.is_file():
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
                for raw in data.get("entries") or []:
                    e = ReferenceEntry.from_dict(raw)
                    if e.id:
                        self._items[e.id] = e
            except (json.JSONDecodeError, OSError, TypeError, KeyError):
                self._items = {}
        return self

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        entries = sorted(self._items.values(), key=lambda e: e.path.lower())
        payload = {
            "version": 1,
            "comment": "Визуальные референсы — плоский каталог, файлы в Inbox/references/",
            "entries": [e.to_dict() for e in entries],
        }
        self.path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    def all_entries(self) -> list[ReferenceEntry]:
        return list(self._items.values())

    def pending(self) -> list[ReferenceEntry]:
        return [e for e in self._items.values() if not e.reviewed]

    def get(self, entry_id: str) -> ReferenceEntry | None:
        return self._items.get(entry_id)

    def upsert(self, entry: ReferenceEntry) -> None:
        self._items[entry.id] = entry

    def remove(self, entry_id: str) -> None:
        self._items.pop(entry_id, None)
