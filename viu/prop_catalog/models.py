"""Модели каталога предметов (props) для Анабарры."""

from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

# Доступные взаимодействия (стыкуются с affordances.py).
from .interactions import INTERACTION_CHOICES, INTERACTION_CHOICES_PROPS, normalize_interactions

PROP_CATEGORIES = (
    "unknown",
    "furniture",
    "decor",
    "shell",
    "tool",
    "food",
    "tableware",
    "character",
    "building",
)

# Роль меша внутри составного .blend (домик, комната).
PROP_ROLES = ("", "shell", "interactive", "decor", "atmosphere", "undefined")

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
    if role == "atmosphere":
        return "decor"
    if role == "undefined":
        return "unknown"
    return "unknown"


def suggest_category_from_mesh(mesh_name: str) -> str:
    """Тарелка/кувшин — tableware (grab), яблоко — food (eat)."""
    name = (mesh_name or "").replace("_", " ")
    if FOOD_NAME_RE.search(name):
        return "food"
    if TABLEWARE_NAME_RE.search(name):
        return "tableware"
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


# Коллекции Blender — стены/пол без ручной разметки.
AUTO_SHELL_COLLECTIONS = frozenset({"building", "buildings"})
AUTO_LANDSCAPE_COLLECTIONS = frozenset({"landscape", "environment", "terrain"})
AUTO_DECOR_COLLECTIONS = frozenset({"stuff", "decor", "decoration"})
# Только чистая атмосфера — не скрываем в Blender, не трогаем в разметке.
AUTO_ATMOSPHERE_NAME_RE = re.compile(r"^(dust|fog|mist|smoke)$", re.IGNORECASE)
# Деревья / кусты — shell + climb, остаются в сцене.
AUTO_TREE_NAME_RE = re.compile(
    r"(pine|tree|brome|foliage|spruce|oak|shrub|bush)",
    re.IGNORECASE,
)
# Служебные меши Blender (Plane, Cube…) — не для игры.
AUTO_UNDEFINED_MESH_RE = re.compile(
    r"^(plane|cube|sphere|cylinder|mesh|empty)(\.\d+)?$",
    re.IGNORECASE,
)
TABLEWARE_NAME_RE = re.compile(
    r"(plate|cup|mug|jug|jar|bowl|goblet|tankard|pitcher|tankard|flagon)",
    re.IGNORECASE,
)
FOOD_NAME_RE = re.compile(
    r"(apple|bread|meat|cheese|fish|food|sausage|loaf|pie|meal|drink)",
    re.IGNORECASE,
)


def apply_auto_review(entry: "PropEntry") -> "PropEntry":
    """Авто-разметка — Building и атмосфера; деревья с climb по умолчанию."""
    from .interactions import default_shell_flags, default_shell_interactions

    if entry.reviewed:
        return entry
    col = (entry.collection or "").lower().strip()
    name = (entry.mesh_name or entry.display_name or "").replace("_", " ")
    mesh_raw = (entry.mesh_name or "").strip()

    if mesh_raw and AUTO_UNDEFINED_MESH_RE.match(mesh_raw):
        entry.role = "undefined"
        entry.category = "unknown"
        entry.reviewed = True
        entry.notes = (entry.notes + "\nСлужебный меш Blender (Plane/Cube…) — не для игры.").strip()
        return entry

    if AUTO_ATMOSPHERE_NAME_RE.match(name.strip()):
        entry.role = "atmosphere"
        entry.category = "decor"
        entry.reviewed = True
        entry.interactions = []
        return entry

    if col in AUTO_SHELL_COLLECTIONS:
        entry.role = "shell"
        entry.category = "building"
        entry.reviewed = True
        entry.interactions = []
        entry.can_lift = False
        entry.can_push = False
        entry.weight_kg = None
        return entry

    if col in AUTO_LANDSCAPE_COLLECTIONS or AUTO_TREE_NAME_RE.search(name):
        entry.role = "shell"
        entry.category = "building"
        entry.interactions = default_shell_interactions(entry.mesh_name, entry.collection)
        flags = default_shell_flags(entry.mesh_name, entry.collection)
        entry.can_climb = flags.get("can_climb", False)
        entry.reviewed = True
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

    if col in ("props", "prop", "furniture") and not entry.role:
        entry.role = "interactive"
        cat = suggest_category_from_mesh(entry.mesh_name)
        entry.category = cat if cat != "unknown" else "furniture"

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
    can_climb: bool = False
    can_stack: bool = False
    nsfw_usable: bool = False
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
            can_climb=bool(d.get("can_climb", False)),
            can_stack=bool(d.get("can_stack", False)),
            nsfw_usable=bool(d.get("nsfw_usable", False)),
            interactions=normalize_interactions(list(d.get("interactions") or [])),
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
        """Подпись в очереди: коллекция › меш."""
        if self.mesh_name:
            if self.collection:
                return f"{self.collection} › {self.mesh_name}"
            return self.mesh_name
        return f"{Path(self.source_path).name}  (весь файл — нужен Blender)"

    def short_source(self) -> str:
        p = Path(self.source_path)
        name = p.name
        if len(name) > 22:
            return name[:10] + "…" + name[-10:]
        return name

    def to_affordance_dict(self) -> Dict[str, Any]:
        """Экспорт для integrations/affordances и Unity."""
        interactions = normalize_interactions(self.interactions)
        sockets: List[Dict[str, Any]] = []
        if "sit" in interactions:
            sockets.append({"name": "seat", "tags": ["sit_surface"]})
        if "lean_on" in interactions:
            sockets.append({"name": "backrest", "tags": ["lean_surface"]})
        if "stand_on" in interactions:
            sockets.append({"name": "top", "tags": ["stand_surface"]})
        if "grab" in interactions or "throw" in interactions or "pocket" in interactions:
            sockets.append({"name": "grip_center", "tags": ["grip_point"]})
        if self.can_climb:
            sockets.append({"name": "climb", "tags": ["climb_surface"]})
        tags = [self.category, "prop"]
        if self.role:
            tags.append(self.role)
        if self.can_climb:
            tags.append("climbable")
        if self.nsfw_usable:
            tags.append("nsfw_usable")
        if self.can_stack:
            tags.append("stackable")
        payload: Dict[str, Any] = {
            "name": self.guess_display_name(),
            "source_file": self.source_path,
            "mesh_name": self.mesh_name,
            "collection": self.collection,
            "role": self.role,
            "tags": tags,
            "sockets": sockets,
            "interactions": interactions,
            "weight_kg": self.weight_kg,
            "can_lift": self.can_lift,
            "can_push": "move" in interactions,
            "can_climb": self.can_climb,
            "can_stack": self.can_stack,
            "nsfw_usable": self.nsfw_usable,
        }
        if self.can_climb:
            payload["requires_character"] = ["can_climb"]
        return payload


def suggest_can_lift(weight_kg: Optional[float], max_lift_kg: float) -> bool:
    if weight_kg is None:
        return False
    return weight_kg <= max_lift_kg
