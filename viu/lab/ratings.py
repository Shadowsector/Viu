"""Критерии оценки работы лаборатории."""

from __future__ import annotations

from typing import Dict, List, Tuple

# id, короткое имя, подсказка
LAB_CRITERIA: List[Tuple[str, str, str]] = [
    ("technique", "Техника", "Корректность, аккуратность, без грубых ошибок"),
    ("creativity", "Изобретательность", "Свои идеи, не только шаблон из доков"),
    ("effort", "Старание", "Копала глубже минимума, виден след работы"),
    ("usefulness", "Полезность", "Можно взять в Anabarra / Cascadeur pipeline"),
    ("clarity", "Ясность", "Понятный отчёт: что сделала, что не вышло"),
]


def criteria_labels() -> Dict[str, str]:
    return {cid: title for cid, title, _hint in LAB_CRITERIA}


def validate_ratings(values: Dict[str, int]) -> tuple[bool, str]:
    for cid, _title, _hint in LAB_CRITERIA:
        v = values.get(cid)
        if v is None:
            return False, f"Нет оценки: {cid}"
        if not isinstance(v, int) or v < 1 or v > 5:
            return False, f"Оценка {cid} должна быть 1–5"
    return True, ""


def average_score(values: Dict[str, int]) -> float:
    if not values:
        return 0.0
    nums = [int(values[cid]) for cid, _, _ in LAB_CRITERIA if cid in values]
    return sum(nums) / len(nums) if nums else 0.0
