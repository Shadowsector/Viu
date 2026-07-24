"""Каталог визуальных референсов — inbox + JSON, без подпапок в каталоге."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class ReferenceEntry:
    id: str
    path: str
    kind: str = "image"  # image | video
    title: str = ""
    ru: str = ""
    en_pose: str = ""
    en_look: str = ""
    tags: List[str] = field(default_factory=list)
    verdict: str = ""
    vision_ok: bool = False
    reviewed: bool = False
    notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "path": self.path,
            "kind": self.kind,
            "title": self.title,
            "ru": self.ru,
            "en_pose": self.en_pose,
            "en_look": self.en_look,
            "tags": self.tags,
            "verdict": self.verdict,
            "vision_ok": self.vision_ok,
            "reviewed": self.reviewed,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, raw: Dict[str, Any]) -> "ReferenceEntry":
        tags = raw.get("tags") or []
        if isinstance(tags, str):
            tags = [t.strip() for t in tags.split(",") if t.strip()]
        return cls(
            id=str(raw.get("id") or ""),
            path=str(raw.get("path") or ""),
            kind=str(raw.get("kind") or "image"),
            title=str(raw.get("title") or ""),
            ru=str(raw.get("ru") or ""),
            en_pose=str(raw.get("en_pose") or ""),
            en_look=str(raw.get("en_look") or ""),
            tags=list(tags),
            verdict=str(raw.get("verdict") or ""),
            vision_ok=bool(raw.get("vision_ok")),
            reviewed=bool(raw.get("reviewed")),
            notes=str(raw.get("notes") or ""),
        )
