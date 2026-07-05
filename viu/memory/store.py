"""Долгосрочная память на основе JSON-файла.

Простое, но рабочее хранилище: записи с тегами и временными метками,
поиск по ключевым словам с ранжированием. Формат специально сделан
человекочитаемым, чтобы пользователь мог просматривать память вручную.
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import List


@dataclass
class MemoryRecord:
    text: str
    tags: List[str] = field(default_factory=list)
    ts: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(d: dict) -> "MemoryRecord":
        return MemoryRecord(text=d.get("text", ""), tags=list(d.get("tags", [])), ts=float(d.get("ts", 0.0)))


class MemoryStore:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self._records: List[MemoryRecord] = []
        self._load()

    def _load(self) -> None:
        if self.path.exists():
            try:
                raw = json.loads(self.path.read_text(encoding="utf-8"))
                self._records = [MemoryRecord.from_dict(r) for r in raw]
            except (json.JSONDecodeError, ValueError):
                # Повреждённый файл не должен ронять агента.
                self._records = []

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps([r.to_dict() for r in self._records], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def add(self, text: str, tags: List[str] | None = None) -> MemoryRecord:
        record = MemoryRecord(text=text.strip(), tags=list(tags or []))
        self._records.append(record)
        self._save()
        return record

    def all(self) -> List[MemoryRecord]:
        return list(self._records)

    def search(self, query: str, limit: int = 5) -> List[MemoryRecord]:
        """Поиск по ключевым словам с простым ранжированием по совпадениям."""
        terms = [t for t in query.lower().split() if t]
        if not terms:
            return list(reversed(self._records))[:limit]

        scored: list[tuple[int, float, MemoryRecord]] = []
        for rec in self._records:
            haystack = (rec.text + " " + " ".join(rec.tags)).lower()
            score = sum(haystack.count(term) for term in terms)
            if score > 0:
                scored.append((score, rec.ts, rec))
        scored.sort(key=lambda x: (x[0], x[1]), reverse=True)
        return [rec for _, _, rec in scored[:limit]]

    def recent(self, limit: int = 5) -> List[MemoryRecord]:
        return list(reversed(self._records))[:limit]
