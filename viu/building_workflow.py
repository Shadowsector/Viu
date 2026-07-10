"""Домики/сараи: notes.txt → чеклист (отрезать стену, варианты)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .anabarra_layout import library_root
from .config import Config

OPEN_WALL_RE = re.compile(
    r"open_wall\s*[=:]\s*(front|back|left|right|north|south|east|west|перед|зад|лев|прав)",
    re.IGNORECASE,
)
BUILDING_TYPE_RE = re.compile(
    r"building_type\s*[=:]\s*(\w+)",
    re.IGNORECASE,
)
SIDECAR_NAMES = ("notes.txt", "описание.txt", "readme.txt", "README.txt")

_WALL_RU = {
    "перед": "front",
    "front": "front",
    "north": "front",
    "зад": "back",
    "back": "back",
    "south": "back",
    "лев": "left",
    "left": "left",
    "west": "left",
    "прав": "right",
    "right": "right",
    "east": "right",
}


@dataclass
class BuildingNotes:
    raw: str = ""
    open_wall: str = ""
    building_type: str = ""

    @property
    def wants_open_wall(self) -> bool:
        return bool(self.open_wall)


def normalize_wall(side: str) -> str:
    key = (side or "").strip().lower()
    return _WALL_RU.get(key, key)


def parse_building_notes(text: str) -> BuildingNotes:
    raw = (text or "").strip()
    notes = BuildingNotes(raw=raw)
    m = OPEN_WALL_RE.search(raw)
    if m:
        notes.open_wall = normalize_wall(m.group(1))
    m2 = BUILDING_TYPE_RE.search(raw)
    if m2:
        notes.building_type = m2.group(1).strip().lower()
    return notes


def read_sidecar_for_blend(blend: Path) -> str:
    blend = blend.expanduser().resolve()
    for base in (blend.parent, blend.parent.parent):
        for name in SIDECAR_NAMES:
            sidecar = base / name
            if sidecar.is_file():
                try:
                    return sidecar.read_text(encoding="utf-8", errors="replace").strip()
                except OSError:
                    continue
    return ""


def find_prepared_blend(
    config: Config,
    *,
    name_hint: str = "",
) -> Optional[Path]:
    """Последний *_prepared.blend в Library/Processed (опционально по имени)."""
    processed = library_root(config) / "Processed"
    if not processed.is_dir():
        return None
    prepared = [p for p in processed.rglob("*_prepared.blend") if p.is_file()]
    if not prepared:
        return None
    hint = (name_hint or "").lower()
    if hint:
        matched = [p for p in prepared if hint in p.stem.lower() or hint in p.parent.name.lower()]
        if matched:
            return max(matched, key=lambda p: p.stat().st_mtime)
    return max(prepared, key=lambda p: p.stat().st_mtime)


def open_wall_checklist(notes: BuildingNotes, *, blend_label: str = "домик") -> str:
    """Чеклист для Blender: отделить стенку под dollhouse, не удалять."""
    wall = notes.open_wall or "front"
    btype = notes.building_type or "building"
    wall_ru = {
        "front": "переднюю (к камере / dollhouse)",
        "back": "заднюю",
        "left": "левую",
        "right": "правую",
    }.get(wall, wall)
    return (
        f"Чеклист «{blend_label}» ({btype}) — стенка для режима «кукольный домик»:\n"
        "1. Работай с *_prepared.blend из Library/Processed.\n"
        f"2. Outliner → Building: выдели {wall_ru} стену как **отдельный меш** "
        "(если слита с сараем — Edit Mode → P Separate).\n"
        "3. **Не удаляй.** Переименуй, напр. Wall_Front — Unity потом **скроет или "
        "сделает прозрачной**, когда Шаня внутри, и вернёт фасад, когда вышла.\n"
        "4. Ctrl+S в тот же prepared (или копия — как удобнее).\n"
        "5. «Следующий шаг» во Вью → разметка Props.\n"
        "Вход сбоку не мешает: для вида внутрь всё равно нужна прозрачная/скрытая "
        "**передняя** стенка (к камере), а не «левая»."
    )


def building_status_text(config: Config, *, name_hint: str = "") -> str:
    prepared = find_prepared_blend(config, name_hint=name_hint)
    lines = ["Домик / сарай — где что лежит:"]
    if prepared:
        lines.append(f"• Prepared: {prepared}")
        notes = parse_building_notes(read_sidecar_for_blend(prepared))
        if notes.raw:
            lines.append(f"• notes.txt: {notes.raw[:200]}{'…' if len(notes.raw) > 200 else ''}")
        if notes.wants_open_wall:
            lines.extend(["", open_wall_checklist(notes, blend_label=prepared.stem)])
        else:
            lines.append(
                "\nСтену режем в Blender вручную. Добавь в notes.txt: open_wall=front"
            )
    else:
        lines.append(
            "• Prepared ещё нет — положи blend+Textures в U:\\Viu\\Inbox, "
            "«Принять asset» / «Следующий шаг»."
        )
        lines.append("• Сырой .blend из Desktop Mascot не размечен — сначала prepare.")
    return "\n".join(lines)
