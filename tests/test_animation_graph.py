"""Transition graph edges on default catalog wishes."""

from pathlib import Path

from viu.animation_catalog.models import DEFAULT_WISHES
from viu.animation_catalog.store import AnimationCatalogStore


def test_wave1_core_has_graph_edges():
    by_slug = {w.slug: w for w in DEFAULT_WISHES}
    for slug in ("idle", "walk", "sit_down", "stand_up", "lie_down", "sit_idle", "sleep_idle", "get_up"):
        w = by_slug[slug]
        assert w.enters_from or w.exits_to, slug


def test_all_wishes_have_graph_edges():
    missing = [w.slug for w in DEFAULT_WISHES if not (w.enters_from or w.exits_to)]
    assert missing == [], f"без рёбер: {missing}"


def test_sit_chain():
    by_slug = {w.slug: w for w in DEFAULT_WISHES}
    assert "idle" in by_slug["sit_down"].enters_from
    assert "sit_idle" in by_slug["sit_down"].exits_to
    assert "stand_up" in by_slug["sit_idle"].exits_to
    assert "idle" in by_slug["stand_up"].exits_to


def test_merge_fills_empty_graph(tmp_path: Path):
    path = tmp_path / "animation_catalog.json"
    store = AnimationCatalogStore(path).load()
    idle = store.get_by_slug("idle")
    assert idle is not None
    idle.enters_from = []
    idle.exits_to = []
    store.save()
    store2 = AnimationCatalogStore(path).load()
    idle2 = store2.get_by_slug("idle")
    assert idle2 is not None
    assert idle2.enters_from
    assert idle2.exits_to


def test_graph_brief_lists_holes(tmp_path: Path):
    path = tmp_path / "animation_catalog.json"
    store = AnimationCatalogStore(path).load()
    text = store.graph_brief(max_holes=5)
    assert "Граф анимаций" in text
    assert "sit_down" in text or "дыр" in text.lower()
    assert "→" in text
