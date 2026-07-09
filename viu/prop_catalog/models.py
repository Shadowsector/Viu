"""Модели каталога предметов (props) для Анабарры."""

from __future__ import annotations

import hashlib
import re
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

# Роль меша внутри составного .blend (домик, комната).
PROP_ROLES = ("", "shell", "interactive", "decor")

ASSET_SUFFIXES = {".fbx", ".blend", ".obj", ".glb", ".gltf"}


def prop_id_for_path(path: Path) -> str:
    norm = str(path.expanduser().resolve()).lower()
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()[:16]


def prop_id_for_mesh(path: Path, mesh_name: str) -> str:
    norm = f"{path.expanduser().resolve()}|{mesh_name}".lower()
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()[:16]


def suggest_role(mesh_name: str) -> str:
    """Угадывает роль по имени объекта в Blender (Shell_, Interactive_, Decor_)."""
    lower = mesh_name.lower().replace(" ", "_")
    for prefix, role in (
        ("shell_", "shell"),
        ("shell.", "shell"),
        ("interactive_", "interactive"),
        ("inter_", "interactive"),
        ("decor_", "decor"),
    ):
        if lower.startswith(prefix) or lower == prefix.rstrip("_."):
            return role
    if lower.startswith("shell"):
        return "shell"
    if lower.startswith("interactive") or lower.startswith("inter"):
        return "interactive"
    if lower.startswith("decor"):
        return "decor"
    return ""


def suggest_category_for_role(role: str) -> str:
    if role == "shell":
        return "building"
    if role == "interactive":
        return "furniture"
    if role == "decor":
        return "decor"
    return "unknown"


def suggest_from_collection(collection: str) -> tuple[str, str]:
    """Подсказка роли/категории по коллекции Blender (Building, Props…)."""
    key = collection.lower().strip()
    if key in ("building", "buildings"):
        return "shell", "building"
    if key in ("props", "prop", "furniture"):
        return "interactive", "furniture"
    if key in ("landscape", "environment", "terrain"):
        return "shell", "building"  # фон — часто shell/пропустить
    if key in ("stuff", "decor", "decoration"):
        return "decor", "decor"
    if key in ("lights", "light"):
        return "", "unknown"
    return "", "unknown"


def suggest_role_and_category(mesh_name: str, collection: str = "") -> tuple[str, str]:
    role = suggest_role(mesh_name)
    category = suggest_category_for_role(role)
    if role:
        return role, category
    cr, cc = suggest_from_collection(collection)
    if cr:
        return cr, cc
    return role, category


# Коллекции Blender — разметка без участия Дена (стены, трава, фон).
AUTO_SHELL_COLLECTIONS = frozenset({"building", "buildings", "landscape", "environment", "terrain"})
AUTO_DECOR_COLLECTIONS = frozenset({"stuff", "decor", "decoration"})
# Пыль, туман, трава, пламя (шейдер/меш) — не интерактив.
AUTO_DECOR_NAME_RE = re.compile(
    r"(dust|fog|smoke|particle|spark|ember|flame|great\s*brome|brome|grass|foliage|mist)",
    re.IGNORECASE,
)


def apply_auto_review(entry: "PropEntry") -> "PropEntry":
    """Авто-разметка по коллекции/имени — не заставляем Дена кликать 90 раз."""
    if entry.reviewed:
        return entry
    col = (entry.collection or "").lower().strip()
    name = (entry.mesh_name or entry.display_name or "").replace("_", " ")

    if col in AUTO_SHELL_COLLECTIONS:
        entry.role = "shell"
        entry.category = "building"
        entry.reviewed = True
        entry.interactions = []
        entry.can_lift = False
        entry.can_push = False
        entry.weight_kg = None
        return entry

    if col in AUTO_DECOR_COLLECTIONS:
        entry.role = "decor"
        entry.category = "decor"
        entry.reviewed = True
        entry.interactions = []
        return entry

    if AUTO_DECOR_NAME_RE.search(name):
        entry.role = "decor"
        entry.category = "decor"
        entry.reviewed = True
        entry.interactions = []
        return entry

    if col in ("props", "prop", "furniture") and not entry.role:
        entry.role = "interactive"
        entry.category = "furniture"

    return entry


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
    mesh_name: str = ""
    collection: str = ""
    role: str = ""
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
            mesh_name=d.get("mesh_name", ""),
            collection=d.get("collection", ""),
            role=d.get("role", ""),
            reviewed=bool(d.get("reviewed", False)),
            notes=d.get("notes", ""),
            library_rel=d.get("library_rel", ""),
        )

    def guess_display_name(self) -> str:
        if self.display_name.strip():
            return self.display_name.strip()
        if self.mesh_name.strip():
            return self.mesh_name.replace("_", " ").strip()
        return Path(self.source_path).stem.replace("_", " ").strip()

    def list_label(self) -> str:
        """Подпись в очереди: файл › коллекция › меш."""
        file_name = Path(self.source_path).name
        if self.mesh_name:
            if self.collection:
                return f"{self.collection} › {self.mesh_name}"
            return f"{file_name} › {self.mesh_name}"
        return f"{file_name}  (весь файл — нужен Blender)"

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
        tags = [self.category, "prop"]
        if self.role:
            tags.append(self.role)
        return {
            "name": self.guess_display_name(),
            "source_file": self.source_path,
            "mesh_name": self.mesh_name,
            "collection": self.collection,
            "role": self.role,
            "tags": tags,
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
