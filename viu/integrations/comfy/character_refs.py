"""Привязка референсов к персонажам: Вью / Шаня / минотавр."""

from __future__ import annotations

import json
import re
import shutil
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from ...config import Config
from ...inbox_layout import inbox_references_dir
from .face_refs import ensure_face_refs_dir
from .paths import comfy_refs_dir

CHARACTERS = ("viu", "shanya", "minotaur")

_ALIASES: Dict[str, tuple[str, ...]] = {
    "viu": ("viu", "вью", "вьюшка", "ты", "тебя", "тебе", "собой", "себе"),
    "shanya": ("shanya", "shania", "шаня", "шанька", "шане", "шаню"),
    "minotaur": ("minotaur", "минотавр", "минотавра", "бык", "мино"),
}

_FACE_NAMES = {
    "viu": "viu.png",
    "shanya": "shanya.png",
}


@dataclass
class CharacterRef:
    id: str
    path: str = ""
    body_path: str = ""
    title: str = ""
    notes: str = ""
    tags: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, raw: dict) -> "CharacterRef":
        return cls(
            id=str(raw.get("id") or ""),
            path=str(raw.get("path") or ""),
            body_path=str(raw.get("body_path") or ""),
            title=str(raw.get("title") or ""),
            notes=str(raw.get("notes") or ""),
            tags=[str(t) for t in (raw.get("tags") or []) if str(t).strip()],
        )


def character_refs_path(config: Config) -> Path:
    d = comfy_refs_dir(config) / "character_refs"
    d.mkdir(parents=True, exist_ok=True)
    return d / "character_refs.json"


def _default_store() -> Dict[str, CharacterRef]:
    titles = {"viu": "Вью", "shanya": "Шаня", "minotaur": "Минотавр"}
    return {cid: CharacterRef(id=cid, title=titles[cid]) for cid in CHARACTERS}


def load_character_refs(config: Config) -> Dict[str, CharacterRef]:
    path = character_refs_path(config)
    store = _default_store()
    if not path.is_file():
        return store
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return store
    items = raw.get("characters") if isinstance(raw, dict) else raw
    if not isinstance(items, dict):
        return store
    for cid, data in items.items():
        if cid not in store or not isinstance(data, dict):
            continue
        store[cid] = CharacterRef.from_dict({**data, "id": cid})
    return store


def save_character_refs(config: Config, store: Dict[str, CharacterRef]) -> Path:
    path = character_refs_path(config)
    payload = {
        "version": 1,
        "comment": "Референсы персонажей для Comfy/чата (Вью / Шаня / минотавр)",
        "characters": {k: v.to_dict() for k, v in store.items()},
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def resolve_character_id(text: str) -> Optional[str]:
    low = (text or "").lower()
    # более длинные / специфичные первыми
    for cid, aliases in (
        ("minotaur", _ALIASES["minotaur"]),
        ("shanya", _ALIASES["shanya"]),
        ("viu", _ALIASES["viu"]),
    ):
        for a in aliases:
            if re.search(rf"(?<!\w){re.escape(a)}(?!\w)", low):
                return cid
    return None


def assign_character_ref(
    config: Config,
    character: str,
    image_path: str | Path,
    *,
    notes: str = "",
) -> tuple[bool, str]:
    """Привязать картинку к персонажу + скопировать в FaceRefs при нужде."""
    cid = (character or "").strip().lower()
    if cid not in CHARACTERS:
        # попробовать алиас
        cid = resolve_character_id(character or "") or cid
    if cid not in CHARACTERS:
        return False, f"Неизвестный персонаж: {character}. Жду: Вью / Шаня / минотавр."

    src = Path(image_path).expanduser()
    if not src.is_file():
        return False, f"Файл не найден: {image_path}"

    dest_dir = character_refs_path(config).parent / cid
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"{cid}{src.suffix.lower() or '.png'}"
    body_dest = dest_dir / f"{cid}_body{src.suffix.lower() or '.png'}"
    try:
        raw = src.read_bytes()
        dest.write_bytes(raw)
        body_dest.write_bytes(raw)
    except OSError as exc:
        return False, f"Не скопировать реф: {exc}"

    # Inbox — чтобы каталог референсов тоже видел
    try:
        inbox = inbox_references_dir(config)
        inbox_copy = inbox / f"char_{cid}{dest.suffix}"
        shutil.copy2(dest, inbox_copy)
        shutil.copy2(body_dest, inbox / f"char_{cid}_body{body_dest.suffix}")
    except OSError:
        inbox_copy = None

    store = load_character_refs(config)
    titles = {"viu": "Вью", "shanya": "Шаня", "minotaur": "Минотавр"}
    entry = store[cid]
    entry.path = str(dest.resolve())
    entry.body_path = str(body_dest.resolve())
    entry.title = titles[cid]
    if notes:
        entry.notes = notes.strip()[:400]
    tags = list(entry.tags)
    if "body" not in tags:
        tags.append("body")
    if cid in _FACE_NAMES and "face" not in tags:
        tags.append("face")
    if cid == "minotaur" and "creature" not in tags:
        tags.append("creature")
    entry.tags = list(dict.fromkeys(tags))
    save_character_refs(config, store)

    face_note = ""
    if cid in _FACE_NAMES:
        face_dir = ensure_face_refs_dir(config)
        face_dest = face_dir / _FACE_NAMES[cid]
        try:
            shutil.copy2(dest, face_dest)
            if cid == "viu":
                shutil.copy2(dest, face_dir / "default.png")
            face_note = f"Лицо для съёмки тоже обновила ({face_dest.name})."
        except OSError as exc:
            face_note = f"Лицо для съёмки не обновилось: {exc}"

    bits = [
        f"Ок — запомнила тебя целиком ({titles[cid]}): и лицо, и фигуру.",
    ]
    if inbox_copy:
        bits.append(f"Лежит в референсах: {inbox_copy.name}")
    if face_note:
        bits.append(face_note)
    return True, "\n".join(bits)


def format_character_refs_status(config: Config) -> str:
    store = load_character_refs(config)
    lines = ["Персонажи и референсы:"]
    for cid in CHARACTERS:
        e = store[cid]
        path = e.path or "— нет"
        lines.append(f"• {e.title}: {path}")
    return "\n".join(lines)


def character_image_path(config: Config, character: str = "viu") -> Optional[Path]:
    """Полный реф персонажа (фигура), если уже сохраняли."""
    cid = (character or "").strip().lower()
    if cid not in CHARACTERS:
        cid = resolve_character_id(character or "") or cid
    if cid not in CHARACTERS:
        return None
    store = load_character_refs(config)
    entry = store[cid]
    for raw in (entry.body_path, entry.path):
        p = Path(str(raw or ""))
        if p.is_file():
            return p
    return None


def active_face_character(config: Config) -> Optional[str]:
    """Кого сейчас считаем лицом для ReActor (viu предпочтительнее shanya)."""
    store = load_character_refs(config)
    for cid in ("viu", "shanya"):
        if store[cid].path and Path(store[cid].path).is_file():
            return cid
    return None
