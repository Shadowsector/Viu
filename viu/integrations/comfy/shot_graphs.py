"""Именованные графы анимаций для каталожного вида очереди MoCap."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple


@dataclass(frozen=True)
class ShotGraph:
    id: str
    title_ru: str
    slugs: Tuple[str, ...]
    hint: str = ""

    def contains(self, slug: str) -> bool:
        return (slug or "").strip() in self.slugs


# Порядок = приоритет при определении графа для slug (первый матч).
SHOT_GRAPHS: Tuple[ShotGraph, ...] = (
    ShotGraph(
        "sleep",
        "Лечь спать",
        ("lie_down", "sleep_idle", "get_up"),
        "кровать / коврик: лечь → спать → встать",
    ),
    ShotGraph(
        "sit",
        "Сесть",
        ("sit_down", "sit_idle", "stand_up"),
        "стул / край: сесть → сидеть → встать",
    ),
    ShotGraph(
        "floor",
        "Пол / колени",
        ("kneel", "all_fours"),
        "колени → четвереньки; Blender holds kneel/all_fours",
    ),
    ShotGraph(
        "climb",
        "Залезть",
        ("climb_up",),
        "дерево / забор / сарай — полный цикл взбирания",
    ),
    ShotGraph(
        "locomotion",
        "Ходьба",
        ("idle", "walk", "walk_back", "run", "sneak", "walk_proud"),
        "стойка и перемещение",
    ),
    ShotGraph(
        "barn_look",
        "Осмотр сарая",
        ("lean", "look_around", "look_window"),
        "опереться, оглядеться, в окно",
    ),
    ShotGraph(
        "props",
        "Взять / есть / пить",
        ("take", "pickup", "eat", "drink"),
        "предметы и еда",
    ),
    ShotGraph(
        "intimate",
        "Интим",
        ("touch_self",),
        "touch_self и смежные",
    ),
    ShotGraph(
        "greet",
        "Жесты",
        ("wave", "yawn", "stretch"),
        "помахать, потянуться",
    ),
    ShotGraph(
        "adventure",
        "Прыжок / падение",
        ("jump", "fall", "hide_peek"),
        "adventure-клипы",
    ),
)

OTHER_GRAPH = ShotGraph("other", "Прочее", (), "не попало в именованный цикл")


def _slug_to_graph() -> Dict[str, ShotGraph]:
    out: Dict[str, ShotGraph] = {}
    for g in SHOT_GRAPHS:
        for slug in g.slugs:
            out.setdefault(slug, g)
    return out


_SLUG_GRAPH = _slug_to_graph()


def graph_for_slug(slug: str) -> ShotGraph:
    return _SLUG_GRAPH.get((slug or "").strip(), OTHER_GRAPH)


def graph_path_label(
    slug: str,
    *,
    enters_from: Optional[Sequence[str]] = None,
    exits_to: Optional[Sequence[str]] = None,
) -> str:
    """Короткая строка «из → slug → в» + имя графа."""
    g = graph_for_slug(slug)
    left = " | ".join(enters_from or []) or "—"
    right = " | ".join(exits_to or []) or "—"
    s = (slug or "").strip() or "?"
    return f"{g.title_ru}: {left} → `{s}` → {right}"


def group_items_by_graph(items: Sequence[object]) -> List[Tuple[ShotGraph, List[object]]]:
    """Сгруппировать объекты с атрибутом catalog_slug по графам (порядок SHOT_GRAPHS)."""
    buckets: Dict[str, List[object]] = {g.id: [] for g in SHOT_GRAPHS}
    buckets[OTHER_GRAPH.id] = []
    for it in items:
        slug = str(getattr(it, "catalog_slug", "") or "").strip()
        g = graph_for_slug(slug)
        buckets.setdefault(g.id, []).append(it)
    out: List[Tuple[ShotGraph, List[object]]] = []
    for g in SHOT_GRAPHS:
        chunk = buckets.get(g.id) or []
        if chunk:
            out.append((g, chunk))
    other = buckets.get(OTHER_GRAPH.id) or []
    if other:
        out.append((OTHER_GRAPH, other))
    return out
