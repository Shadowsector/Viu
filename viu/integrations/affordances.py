"""Сокеты и «аффордансы» — что с каким предметом можно делать и что с чем стыкуется.

Идея: у каждого объекта (персонаж, палка, стул) есть именованные точки привязки —
«сокеты» (в Blender это Empty или кость). У сокета есть теги и список того, что
он «принимает». Вью по тегам понимает совместимость: например, сокет ладони
`hand_R` (тег grip) стыкуется с сокетом палки `grip_center` (её принимают grip).

Модуль независим от Blender — его логику можно тестировать отдельно.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Dict, List, Tuple


@dataclass
class Socket:
    name: str
    tags: List[str] = field(default_factory=list)      # чем является этот сокет
    accepts: List[str] = field(default_factory=list)   # какие теги он готов принять

    @staticmethod
    def from_dict(d: dict) -> "Socket":
        return Socket(
            name=d["name"],
            tags=list(d.get("tags", [])),
            accepts=list(d.get("accepts", [])),
        )


@dataclass
class Affordance:
    """Описание объекта: его теги, сокеты и возможные взаимодействия."""

    name: str
    tags: List[str] = field(default_factory=list)
    sockets: List[Socket] = field(default_factory=list)
    interactions: List[str] = field(default_factory=list)

    @staticmethod
    def from_dict(d: dict) -> "Affordance":
        return Affordance(
            name=d.get("name", "?"),
            tags=list(d.get("tags", [])),
            sockets=[Socket.from_dict(s) for s in d.get("sockets", [])],
            interactions=list(d.get("interactions", [])),
        )

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "tags": self.tags,
            "sockets": [{"name": s.name, "tags": s.tags, "accepts": s.accepts} for s in self.sockets],
            "interactions": self.interactions,
        }


@dataclass
class SocketMatch:
    socket_a: str
    socket_b: str
    via_tag: str


def match_sockets(a: Affordance, b: Affordance) -> List[SocketMatch]:
    """Находит совместимые пары сокетов между двумя объектами.

    Совместимость: сокет A принимает один из тегов сокета B (или наоборот).
    """
    matches: List[SocketMatch] = []
    for sa in a.sockets:
        for sb in b.sockets:
            # A принимает B
            for tag in sb.tags:
                if tag in sa.accepts:
                    matches.append(SocketMatch(sa.name, sb.name, tag))
                    break
            else:
                # B принимает A
                for tag in sa.tags:
                    if tag in sb.accepts:
                        matches.append(SocketMatch(sa.name, sb.name, tag))
                        break
    return matches


def describe_compatibility(a: Affordance, b: Affordance) -> str:
    matches = match_sockets(a, b)
    lines = [f"Совместимость: {a.name} ↔ {b.name}"]
    if not matches:
        lines.append("  Совместимых сокетов не найдено.")
    else:
        for m in matches:
            lines.append(f"  {a.name}.{m.socket_a}  ⟷  {b.name}.{m.socket_b}   (через тег: {m.via_tag})")
    if a.interactions:
        lines.append(f"  Возможные действия с «{a.name}»: {', '.join(a.interactions)}")
    if b.interactions:
        lines.append(f"  Возможные действия с «{b.name}»: {', '.join(b.interactions)}")
    return "\n".join(lines)


# --- Небольшая стартовая библиотека примеров (Вью может её расширять) ---

DEFAULT_LIBRARY: Dict[str, Affordance] = {
    "шаня": Affordance(
        name="Шаня",
        tags=["character"],
        sockets=[
            Socket("hand_R", tags=["grip"], accepts=["grip_point", "weapon_grip"]),
            Socket("hand_L", tags=["grip"], accepts=["grip_point"]),
            Socket("hips", tags=["character_hips"], accepts=["sit_surface"]),
            Socket("feet", tags=["character_feet"], accepts=["stand_surface"]),
            Socket("back", tags=["character_back"], accepts=["lean_surface"]),
        ],
        interactions=["walk", "sit", "grab", "fight"],
    ),
    "стул": Affordance(
        name="Стул",
        tags=["furniture", "chair"],
        sockets=[
            Socket("seat", tags=["sit_surface"]),
            Socket("backrest", tags=["lean_surface"]),
            Socket("top", tags=["stand_surface"]),
        ],
        interactions=["sit", "sit_reversed", "lean_on", "stand_on"],
    ),
    "палка": Affordance(
        name="Палка",
        tags=["prop", "pole", "weapon"],
        sockets=[
            Socket("grip_center", tags=["grip_point", "weapon_grip"]),
            Socket("grip_end", tags=["grip_point"]),
        ],
        interactions=["wield_two_hand", "poke", "swing"],
    ),
}


def get_from_library(name: str) -> Affordance | None:
    return DEFAULT_LIBRARY.get((name or "").strip().lower())


def load_affordance(value) -> Affordance:
    """Принимает имя из библиотеки, dict или JSON-строку — возвращает Affordance."""
    if isinstance(value, Affordance):
        return value
    if isinstance(value, dict):
        return Affordance.from_dict(value)
    if isinstance(value, str):
        found = get_from_library(value)
        if found is not None:
            return found
        try:
            return Affordance.from_dict(json.loads(value))
        except (json.JSONDecodeError, KeyError, TypeError) as exc:
            raise ValueError(f"Не удалось разобрать affordance из строки: {exc}")
    raise ValueError("affordance должен быть именем из библиотеки, dict или JSON")
