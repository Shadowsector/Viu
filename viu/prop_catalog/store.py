"""Хранилище каталога предметов."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional

from .models import PropEntry


class PropCatalogStore:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.items: Dict[str, PropEntry] = {}
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
                entry = PropEntry.from_dict(raw)
                self.items[entry.id] = entry
            except (KeyError, TypeError):
                continue

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"items": [e.to_dict() for e in self.items.values()]}
        self.path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    def get(self, prop_id: str) -> Optional[PropEntry]:
        return self.items.get(prop_id)

    def upsert(self, entry: PropEntry) -> None:
        self.items[entry.id] = entry
        self.save()

    def pending(self) -> List[PropEntry]:
        return sorted(
            [e for e in self.items.values() if not e.reviewed],
            key=lambda e: (
                e.source_path.lower(),
                e.collection.lower(),
                e.mesh_name.lower(),
            ),
        )

    def reviewed(self) -> List[PropEntry]:
        return sorted(
            [e for e in self.items.values() if e.reviewed],
            key=lambda e: e.guess_display_name().lower(),
        )

    def render_summary(self) -> str:
        pending = len(self.pending())
        total = len(self.items)
        lines = [f"Каталог предметов: {total} всего, {pending} ждут разметки."]
        for e in self.pending()[:20]:
            label = e.list_label()
            role = f" [{e.role}]" if e.role else ""
            lines.append(f"  • [{e.id[:8]}] {label}{role}")
        if pending > 20:
            lines.append(f"  … и ещё {pending - 20}")
        return "\n".join(lines)
