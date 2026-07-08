"""Модели каталога предметов (props) для Анабарры."""

from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

# Доступные взаимодействия (стыкуются с affordances.py).
INTERACTION_CHOICES: List[tuple[str, str]] = [
    ("sit", "Сидеть"),
    ("sit_reversed", "Сидеть задом"),
    ("lean_on", "Опереться"),
    ("stand_on", "Встать на"),
    ("grab", "Взять / поднять"),
    ("push", "Толкать"),
    ("pull", "Тянуть"),
    ("open", "Открыть"),
    ("close", "Закрыть"),
    ("sleep", "Лечь / спать"),
    ("read", "Читать"),
    ("eat", "Есть"),
]

PROP_CATEGORIES = (
    "unknown",
    "furniture",
    "decor",
    "shell",
    "tool",
    "food",
    "character",
    "building",
)

ASSET_SUFFIXES = {".fbx", ".blend", ".obj", ".glb", ".gltf"}


def prop_id_for_path(path: Path) -> str:
    norm = str(path.expanduser().resolve()).lower()
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()[:16]


@dataclass
class PropEntry:
    """Один предмет в каталоге."""

    id: str
    source_path: str
    display_name: str = ""
    category: str = "unknown"
    weight_kg: Optional[float] = None
    can_lift: bool = False
    can_push: bool = False
    interactions: List[str] = field(default_factory=list)
    mesh_names: List[str] = field(default_factory=list)
    reviewed: bool = False
    notes: str = ""
    library_rel: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(d: dict) -> "PropEntry":
        return PropEntry(
            id=d["id"],
            source_path=d.get("source_path", ""),
            display_name=d.get("display_name", ""),
            category=d.get("category", "unknown"),
            weight_kg=d.get("weight_kg"),
            can_lift=bool(d.get("can_lift", False)),
            can_push=bool(d.get("can_push", False)),
            interactions=list(d.get("interactions") or []),
            mesh_names=list(d.get("mesh_names") or []),
            reviewed=bool(d.get("reviewed", False)),
            notes=d.get("notes", ""),
            library_rel=d.get("library_rel", ""),
        )

    def guess_display_name(self) -> str:
        if self.display_name.strip():
            return self.display_name.strip()
        return Path(self.source_path).stem.replace("_", " ").strip()

    def to_affordance_dict(self) -> Dict[str, Any]:
        """Экспорт для integrations/affordances и Unity."""
        sockets: List[Dict[str, Any]] = []
        if "sit" in self.interactions or "sit_reversed" in self.interactions:
            sockets.append({"name": "seat", "tags": ["sit_surface"]})
        if "lean_on" in self.interactions:
            sockets.append({"name": "backrest", "tags": ["lean_surface"]})
        if "stand_on" in self.interactions:
            sockets.append({"name": "top", "tags": ["stand_surface"]})
        if "grab" in self.interactions:
            sockets.append({"name": "grip_center", "tags": ["grip_point"]})
        return {
            "name": self.guess_display_name(),
            "tags": [self.category, "prop"],
            "sockets": sockets,
            "interactions": list(self.interactions),
            "weight_kg": self.weight_kg,
            "can_lift": self.can_lift,
            "can_push": self.can_push,
        }


def suggest_can_lift(weight_kg: Optional[float], max_lift_kg: float) -> bool:
    if weight_kg is None:
        return False
    return weight_kg <= max_lift_kg
