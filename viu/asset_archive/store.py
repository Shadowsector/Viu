"""JSON-хранилище provenance в .viu."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional

from ..config import Config
from .provenance import ProvenanceEntry, seed_pilot_entries


def provenance_path(config: Config) -> Path:
    return Path(config.data_dir) / "asset_provenance.json"


class ProvenanceStore:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.items: Dict[str, ProvenanceEntry] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.is_file():
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return
        for raw in data.get("items") or []:
            try:
                entry = ProvenanceEntry.from_dict(raw)
                self.items[entry.id] = entry
            except (KeyError, TypeError, ValueError):
                continue

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": 1,
            "items": [e.to_dict() for e in sorted(self.items.values(), key=lambda e: e.id)],
        }
        self.path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    def get(self, entry_id: str) -> Optional[ProvenanceEntry]:
        return self.items.get(entry_id)

    def upsert(self, entry: ProvenanceEntry, *, save: bool = True) -> None:
        self.items[entry.id] = entry
        if save:
            self.save()

    def all(self) -> List[ProvenanceEntry]:
        return sorted(self.items.values(), key=lambda e: e.title.lower())

    def ensure_pilots(self, *, save: bool = True) -> int:
        """Добавить канонические пилоты, не затирая ручные правки."""
        added = 0
        for entry in seed_pilot_entries():
            if entry.id in self.items:
                continue
            self.items[entry.id] = entry
            added += 1
        if added and save:
            self.save()
        return added

    def render_summary(self) -> str:
        if not self.items:
            return "Provenance пуст — вызови asset_archive_scan или ensure_pilots."
        lines = [f"Provenance: {len(self.items)} записей"]
        for e in self.all():
            lines.append(f"  • {e.id}: {e.title} [{e.license or '?'}] ({e.source})")
        return "\n".join(lines)
