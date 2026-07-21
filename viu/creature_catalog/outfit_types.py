"""Стандартные типы наборов одежды (id + подпись для UI)."""
from __future__ import annotations

from typing import List, Tuple

# (id_prefix, label_en) — variant 01..03 добавляется отдельно
OUTFIT_TYPE_CHOICES: Tuple[Tuple[str, str], ...] = (
    ("casual", "Casual"),
    ("fitness", "Fitness"),
    ("swimsuit", "Swimsuit"),
    ("pajama", "Pajama"),
    ("undies", "Undies"),
    ("lingerie", "Lingerie"),
    ("half_nude", "Half-nude"),
    ("nude", "Nude"),
)

OUTFIT_VARIANTS: Tuple[str, ...] = ("01", "02", "03")

_BLENDER_TYPE_ITEMS: List[Tuple[str, str, str]] = [
    (tid, label, "") for tid, label in OUTFIT_TYPE_CHOICES
]

_BLENDER_VARIANT_ITEMS: List[Tuple[str, str, str]] = [
    (v, v, "") for v in OUTFIT_VARIANTS
]


def outfit_type_label(type_id: str) -> str:
    for tid, label in OUTFIT_TYPE_CHOICES:
        if tid == type_id:
            return label
    return type_id.replace("_", " ").title()


def outfit_set_id(type_id: str, variant: str) -> str:
    v = (variant or "01").strip()
    if v.isdigit() and len(v) == 1:
        v = f"0{v}"
    if v not in OUTFIT_VARIANTS:
        v = "01"
    return f"{type_id}_{v}"


def parse_outfit_set_id(set_id: str) -> Tuple[str, str]:
    raw = (set_id or "").strip()
    if "_" not in raw:
        return raw or "casual", "01"
    type_id, variant = raw.rsplit("_", 1)
    if variant.isdigit() and len(variant) == 1:
        variant = f"0{variant}"
    return type_id, variant if variant in OUTFIT_VARIANTS else "01"
