"""Каталог существ: размеры, locomotion, NSFW-сокеты, нормализация роста."""

from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# --- Рост (бипеды / антропоморфы). В пределах класса допускается variance. ---

SIZE_CLASSES: Dict[str, Dict[str, Any]] = {
    "mini": {
        "label_ru": "Мини (феи)",
        "target_m": 0.30,
        "min_m": 0.27,
        "max_m": 0.33,
        "notes": "faeries / tiny bipeds (±3 см)",
    },
    "small": {
        "label_ru": "Маленький (гоблины)",
        "target_m": 0.80,
        "min_m": 0.74,
        "max_m": 0.86,
        "notes": "goblins (±6 см)",
    },
    "humanoid": {
        "label_ru": "Нормальный (антропоморфы)",
        "target_m": 1.75,
        "min_m": 1.68,
        "max_m": 1.82,
        "notes": "рядом с Шаней (±7 см)",
    },
    "large": {
        "label_ru": "Большой",
        "target_m": 2.35,
        "min_m": 2.25,
        "max_m": 2.45,
        "notes": "~220–250 см (±10 см)",
    },
    "huge": {
        "label_ru": "Огромный",
        "target_m": 3.60,
        "min_m": 3.30,
        "max_m": 3.90,
        "notes": "хватает Шаню за талию (±30 см)",
    },
}

# Четвероногие — высота в холке / по bounds Y в A-pose.
QUAD_SIZE_CLASSES: Dict[str, Dict[str, Any]] = {
    "quad_mini": {
        "label_ru": "Четвероногие малые",
        "target_m": 0.30,
        "min_m": 0.26,
        "max_m": 0.34,
        "notes": "куницы, барсуки (±4 см)",
    },
    "quad_med": {
        "label_ru": "Четвероногие средние",
        "target_m": 0.75,
        "min_m": 0.68,
        "max_m": 0.82,
        "notes": "собака / волк (±7 см)",
    },
    "quad_large": {
        "label_ru": "Четвероногие крупные",
        "target_m": 1.60,
        "min_m": 1.50,
        "max_m": 1.70,
        "notes": "лошадь / корова (±10 см)",
    },
}

LOCOMOTION = (
    "biped",
    "quadruped",
    "amorph",      # слизни
    "tentacle",    # осьминоги / щупальца
    "mimic",       # сундуки-мимики
    "flyer",       # опционально
    "unknown",
)

# Половая разметка → набор NSFW-анимаций (все классы роста).
GENITAL_PROFILES = ("none", "penis", "vagina", "futa")

GENITAL_PROFILE_LABELS: Dict[str, str] = {
    "none": "нет половых органов",
    "penis": "пенис (мужское)",
    "vagina": "вагина (женское)",
    "futa": "futa (оба)",
}

# Контакт без гениталий: мимик (язык), цветок, щупальца…
CONTACT_MODES = ("oral", "tentacle", "hand")

CONTACT_MODE_LABELS: Dict[str, str] = {
    "oral": "рот / язык",
    "tentacle": "щупальца",
    "hand": "руки / лапы",
}

STATUS_NEW = "new"
STATUS_SIZED = "sized"          # Ден выбрал class
STATUS_NORMALIZED = "normalized"  # scale в Blender сделан
STATUS_READY = "ready"          # фото + sidecar
STATUS_SKIP = "skip"

ASSET_SUFFIXES = {".fbx", ".blend", ".obj", ".glb", ".gltf"}

# Сокеты на девушках (penetrator aim targets).
GIRL_SOCKETS: Tuple[Dict[str, str], ...] = (
    {"id": "socket_oral", "bone_hint": "head / jaw", "label_ru": "рот"},
    {"id": "socket_vaginal", "bone_hint": "hips / pelvis", "label_ru": "вагина"},
    {"id": "socket_anal", "bone_hint": "hips / pelvis rear", "label_ru": "анус"},
    {"id": "socket_hand_l", "bone_hint": "hand.L", "label_ru": "левая ладонь"},
    {"id": "socket_hand_r", "bone_hint": "hand.R", "label_ru": "правая ладонь"},
    {"id": "socket_cleavage", "bone_hint": "spine / chest", "label_ru": "меж грудей"},
)

ALL_SIZE_IDS = tuple(list(SIZE_CLASSES.keys()) + list(QUAD_SIZE_CLASSES.keys()))


def size_spec(size_id: str) -> Optional[Dict[str, Any]]:
    if size_id in SIZE_CLASSES:
        return SIZE_CLASSES[size_id]
    if size_id in QUAD_SIZE_CLASSES:
        return QUAD_SIZE_CLASSES[size_id]
    return None


def creature_id_for_path(path: Path) -> str:
    norm = str(path.expanduser().resolve()).lower()
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()[:16]


def suggest_size_from_name(name: str) -> List[str]:
    """Кандидаты size_class по имени файла (Ден подтверждает)."""
    low = (name or "").lower()
    hits: List[str] = []
    rules = (
        (("fairy", "faerie", "pixie", "sprite", "фея", "fairie"), "mini"),
        (("facehug", "face_hug", "imp", "goblin", "gnome", "гоблин", "карлик"), "small"),
        (("centaur", "кентавр"), "humanoid"),
        (
            (
                "werewolf",
                "wolfman",
                "orc",
                "troll",
                "ogre",
                "yeti",
                "тролль",
                "renekton",
                "croc",
                "крок",
            ),
            "large",
        ),
        (("dragon", "giant", "coloss", "титан", "гигант"), "huge"),
        (("slime", "slug", "ooze", "слиз"), "humanoid"),  # рост потом руками
        (("mimic", "chest", "сундук"), "humanoid"),
        (("wolf", "dog", "hound", "волк", "собак"), "quad_med"),
        (("horse", "cow", "deer", "лошад", "коров"), "quad_large"),
        (("weasel", "badger", "ferret", "куниц", "барсук"), "quad_mini"),
        (("octopus", "tentacle", "щупаль"), "humanoid"),
    )
    for keys, size in rules:
        if any(k in low for k in keys):
            if size not in hits:
                hits.append(size)
    return hits


def suggest_locomotion_from_name(name: str) -> str:
    low = (name or "").lower()
    if any(k in low for k in ("slime", "slug", "ooze", "слиз", "blob")):
        return "amorph"
    if any(k in low for k in ("octopus", "tentacle", "щупаль", "kraken")):
        return "tentacle"
    if any(k in low for k in ("mimic", "chest", "сундук")):
        return "mimic"
    if any(
        k in low
        for k in (
            "wolf",
            "dog",
            "horse",
            "cow",
            "quad",
            "волк",
            "лошад",
            "spider",
            "паук",
        )
    ):
        return "quadruped"
    if any(k in low for k in ("wing", "bat", "bird", "крыл", "летуч")):
        return "flyer"
    if any(k in low for k in ("goblin", "orc", "human", "girl", "woman", "man", "гоблин")):
        return "biped"
    return "unknown"


def scale_factor_to_target(measured_m: float, target_m: float) -> float:
    if measured_m <= 1e-6 or target_m <= 0:
        return 1.0
    return target_m / measured_m


def height_in_class_range(height_m: float, size_id: str) -> bool:
    spec = size_spec(size_id)
    if not spec:
        return False
    return float(spec["min_m"]) <= height_m <= float(spec["max_m"])


def slugify(name: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9_\-]+", "_", (name or "").strip().lower())
    return re.sub(r"_+", "_", s).strip("_")[:64] or "creature"


@dataclass
class CreatureEntry:
    """Одна модель существа в каталоге."""

    id: str
    path: str
    name: str
    slug: str = ""
    size_class: str = ""                 # основной класс
    size_alt: List[str] = field(default_factory=list)  # dual (малый+большой гоблин)
    locomotion: str = "unknown"
    status: str = STATUS_NEW
    measured_height_m: float = 0.0
    target_height_m: float = 0.0
    scale_applied: float = 1.0
    textures_external: bool = False
    textures_dir: str = ""
    genital_profile: str = "none"          # none | penis | vagina | futa
    contact_modes: List[str] = field(default_factory=list)  # oral | tentacle | hand
    nsfw_capable: bool = False            # авто: genital≠none или есть contact_modes
    genital_rig: str = ""                # none | pending | attached (legacy rig state)
    flaccid_default: bool = True
    # Не трогать при bake/normalize: уши, хвосты, гениталии и пр. часто живут
    # в shape keys / morph targets (в т.ч. «спрятанный» орган → вытянуть morph'ом).
    preserve_morphs: bool = True
    morph_notes: str = ""                # что нашли глазами: penis_reveal, ears, tail…
    prepared_path: str = ""
    prep_ok: bool = False
    ready_fbx_path: str = ""
    photo_front: str = ""
    photo_side: str = ""
    photo_ok: bool = False          # Ден подтвердил скрины lineup
    photo_notes: str = ""           # что не так: IK, текстуры, …
    # Внешность для анимации / Comfy (из VL по скрину или руками).
    appearance_en: str = ""              # English prompt / tags for Comfy
    appearance_ru: str = ""              # коротко для чата Вью
    appearance_tags: List[str] = field(default_factory=list)
    describe_model: str = ""             # llava / … чем описали
    described_at: str = ""
    notes: str = ""
    reviewed: bool = False
    tags: List[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.slug:
            self.slug = slugify(self.name)
        if self.size_class and not self.target_height_m:
            spec = size_spec(self.size_class)
            if spec:
                self.target_height_m = float(spec["target_m"])

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "CreatureEntry":
        e = CreatureEntry(
            id=str(d.get("id") or ""),
            path=str(d.get("path") or ""),
            name=str(d.get("name") or ""),
            slug=str(d.get("slug") or ""),
            size_class=str(d.get("size_class") or ""),
            size_alt=list(d.get("size_alt") or []),
            locomotion=str(d.get("locomotion") or "unknown"),
            status=str(d.get("status") or STATUS_NEW),
            measured_height_m=float(d.get("measured_height_m") or 0),
            target_height_m=float(d.get("target_height_m") or 0),
            scale_applied=float(d.get("scale_applied") or 1),
            textures_external=bool(d.get("textures_external")),
            textures_dir=str(d.get("textures_dir") or ""),
            genital_profile=str(d.get("genital_profile") or "none"),
            contact_modes=[
                m for m in (d.get("contact_modes") or []) if m in CONTACT_MODES
            ],
            nsfw_capable=bool(d.get("nsfw_capable")),
            genital_rig=str(d.get("genital_rig") or ""),
            flaccid_default=bool(d.get("flaccid_default", True)),
            preserve_morphs=bool(d.get("preserve_morphs", True)),
            morph_notes=str(d.get("morph_notes") or ""),
            prepared_path=str(d.get("prepared_path") or ""),
            prep_ok=bool(d.get("prep_ok")),
            ready_fbx_path=str(d.get("ready_fbx_path") or ""),
            photo_front=str(d.get("photo_front") or ""),
            photo_side=str(d.get("photo_side") or ""),
            photo_ok=bool(d.get("photo_ok")),
            photo_notes=str(d.get("photo_notes") or ""),
            appearance_en=str(d.get("appearance_en") or ""),
            appearance_ru=str(d.get("appearance_ru") or ""),
            appearance_tags=list(d.get("appearance_tags") or []),
            describe_model=str(d.get("describe_model") or ""),
            described_at=str(d.get("described_at") or ""),
            notes=str(d.get("notes") or ""),
            reviewed=bool(d.get("reviewed")),
            tags=list(d.get("tags") or []),
        )
        if not e.id and e.path:
            e.id = creature_id_for_path(Path(e.path))
        e._migrate_anatomy_from_legacy(d)
        e.sync_nsfw_capable()
        return e

    def _migrate_anatomy_from_legacy(self, d: Dict[str, Any]) -> None:
        gp = (self.genital_profile or "none").strip()
        if gp not in GENITAL_PROFILES:
            self.genital_profile = "none"
        if not d.get("genital_profile") and d.get("nsfw_capable"):
            # старая галочка NSFW — оставляем none, Ден уточнит в разметке
            pass

    def sync_nsfw_capable(self) -> None:
        gp = (self.genital_profile or "none").strip()
        self.nsfw_capable = (gp not in ("", "none")) or bool(self.contact_modes)

    def set_anatomy(
        self,
        *,
        genital_profile: str = "",
        contact_modes: Optional[List[str]] = None,
    ) -> None:
        if genital_profile:
            gp = genital_profile.strip()
            self.genital_profile = gp if gp in GENITAL_PROFILES else "none"
        if contact_modes is not None:
            self.contact_modes = [m for m in contact_modes if m in CONTACT_MODES]
        self.sync_nsfw_capable()

    def anatomy_summary(self) -> str:
        parts: List[str] = []
        gp = (self.genital_profile or "none").strip()
        if gp and gp != "none":
            parts.append(GENITAL_PROFILE_LABELS.get(gp, gp))
        for m in self.contact_modes or []:
            parts.append(CONTACT_MODE_LABELS.get(m, m))
        return " · ".join(parts) if parts else "—"

    def has_photo_files(self) -> bool:
        for p in (self.photo_front, self.photo_side):
            if p and Path(p).is_file():
                return True
        return False

    def needs_photo_lineup(self) -> bool:
        """Нужна съёмка в Blender (нет файлов или сброшено после правки)."""
        if self.status == STATUS_SKIP or not self.size_class:
            return False
        if self.photo_ok:
            return False
        return not self.has_photo_files()

    def needs_photo_review(self) -> bool:
        """Есть скрины, но Ден ещё не нажал «Скрины ок»."""
        if self.status == STATUS_SKIP or not self.size_class or self.photo_ok:
            return False
        return self.has_photo_files()

    def anim_bucket(self) -> str:
        """Ключ набора анимаций: size × locomotion [× анатомия]."""
        size = self.size_class or "unset"
        loco = self.locomotion or "unknown"
        base = f"{size}__{loco}"
        gp = (self.genital_profile or "none").strip()
        if gp and gp != "none":
            return f"{base}__{gp}"
        modes = sorted(set(self.contact_modes or []))
        if modes:
            return f"{base}__" + "+".join(modes)
        return base

    def render_line(self) -> str:
        size = self.size_class or "?"
        alt = f"+{','.join(self.size_alt)}" if self.size_alt else ""
        h = f"{self.measured_height_m:.2f}→{self.target_height_m:.2f}m" if self.target_height_m else "—"
        anat = self.anatomy_summary()
        anat_bit = f" | {anat}" if anat != "—" else ""
        return (
            f"[{self.status}] {self.name} | {size}{alt} | {self.locomotion} | "
            f"{h}{anat_bit} | {Path(self.path).name}"
        )
