"""Сопоставление скелета модели со стандартным ригом.

На вход — список имён костей модели. На выходе — отчёт: какие стандартные
кости найдены (и под каким именем), каких обязательных не хватает, какие
кости модели не распознаны, и план переименования к стандарту.
"""

from __future__ import annotations

import difflib
from dataclasses import dataclass, field
from typing import Dict, List, Tuple

from .standard import ALIAS_MAP, BONE_BY_NAME, CANON_ORDER, REQUIRED, normalize

# Порог схожести для «нечёткого» распознавания (0..1).
_FUZZY_CUTOFF = 0.82


@dataclass
class RigReport:
    matched: Dict[str, Tuple[str, str]] = field(default_factory=dict)  # canonical -> (bone, method)
    missing_required: List[str] = field(default_factory=list)
    unmatched: List[str] = field(default_factory=list)
    rename_plan: Dict[str, str] = field(default_factory=dict)  # bone -> canonical

    @property
    def ok(self) -> bool:
        """True, если все обязательные кости найдены."""
        return not self.missing_required

    def render(self) -> str:
        lines = []
        status = "OK — все обязательные кости найдены" if self.ok else "НЕ ХВАТАЕТ обязательных костей"
        lines.append(f"Статус: {status}")

        lines.append(f"\nНайдено костей стандарта: {len(self.matched)} из {len(CANON_ORDER)}")
        for canon in CANON_ORDER:
            if canon in self.matched:
                bone, method = self.matched[canon]
                same = "" if bone == canon else f"  (модель: '{bone}', {method})"
                lines.append(f"  ✓ {canon}{same}")

        if self.missing_required:
            lines.append("\nНе хватает обязательных:")
            for c in self.missing_required:
                lines.append(f"  ✗ {c}")

        if self.unmatched:
            lines.append("\nКости модели без пары (не распознаны):")
            for b in self.unmatched:
                lines.append(f"  ? {b}")

        if self.rename_plan:
            lines.append("\nПлан переименования к стандарту:")
            for old, new in self.rename_plan.items():
                lines.append(f"  {old}  →  {new}")
        else:
            lines.append("\nПереименование не требуется (имена уже стандартные).")

        return "\n".join(lines)


def _bone_names(bones) -> List[str]:
    """Принимает список строк или список dict {'name':..}."""
    out = []
    for b in bones:
        if isinstance(b, str):
            out.append(b)
        elif isinstance(b, dict) and "name" in b:
            out.append(b["name"])
    return out


def analyze_skeleton(bones) -> RigReport:
    names = _bone_names(bones)
    report = RigReport()
    used: set = set()

    # Проход 1: точное совпадение по псевдонимам.
    for b in names:
        nb = normalize(b)
        if not nb:
            continue
        canon = ALIAS_MAP.get(nb)
        if canon and canon not in report.matched:
            report.matched[canon] = (b, "псевдоним")
            used.add(b)

    # Проход 2: нечёткое совпадение для оставшихся костей.
    remaining_canon = [c for c in CANON_ORDER if c not in report.matched]
    for b in names:
        if b in used:
            continue
        nb = normalize(b)
        if not nb:
            continue
        best_canon = None
        best_score = 0.0
        for c in remaining_canon:
            if c in report.matched:
                continue
            candidates = BONE_BY_NAME[c].aliases | {normalize(c)}
            for al in candidates:
                score = difflib.SequenceMatcher(None, nb, al).ratio()
                if score > best_score:
                    best_score = score
                    best_canon = c
        if best_canon and best_score >= _FUZZY_CUTOFF and best_canon not in report.matched:
            report.matched[best_canon] = (b, f"похоже {best_score:.2f}")
            used.add(b)

    # Итоги.
    report.unmatched = [b for b in names if b not in used]
    report.missing_required = [c for c in CANON_ORDER if c in REQUIRED and c not in report.matched]
    report.rename_plan = {
        bone: canon for canon, (bone, _method) in report.matched.items() if bone != canon
    }
    return report
