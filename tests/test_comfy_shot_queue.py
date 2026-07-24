"""Очередь MoCap-анимаций: план съёмки и peek/take."""

from pathlib import Path

from viu.config import Config
from viu.integrations.comfy.shot_queue import (
    count_pending,
    load_items,
    peek_next_pending,
    rebuild_queue,
    take_next_pending,
    update_item,
)
from viu.lab.comfy_director import invent_next_shot


def _cfg(tmp_path: Path, monkeypatch) -> Config:
    monkeypatch.setenv("VIU_DATA_DIR", str(tmp_path / ".viu"))
    monkeypatch.setenv("VIU_LIBRARY_ROOT", str(tmp_path / "Library"))
    data = tmp_path / ".viu"
    data.mkdir()
    (tmp_path / "Library").mkdir(parents=True, exist_ok=True)
    return Config(
        root=tmp_path,
        data_dir=data,
        library_root=str(tmp_path / "Library"),
    ).ensure_dirs()


def test_rebuild_and_take_queue(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path, monkeypatch)

    class FakePlan:
        action = "sit down from stand onto bed"
        catalog_slug = "sit_down"
        reason = "hole"
        enters_from = ["idle"]
        exits_to = ["sit_idle"]
        title_ru = "Сесть"
        looped = False

    monkeypatch.setattr(
        "viu.lab.comfy_director.invent_shot_choices",
        lambda _c, limit=8: [FakePlan()],
    )
    items = rebuild_queue(cfg, limit=5)
    assert len(items) == 1
    assert items[0].catalog_slug == "sit_down"
    assert "sit" in items[0].wan_positive.lower() or items[0].wan_positive
    assert count_pending(cfg) == 1

    peeked = peek_next_pending(cfg)
    assert peeked is not None
    assert count_pending(cfg) == 1

    taken = take_next_pending(cfg)
    assert taken is not None
    assert taken.catalog_slug == "sit_down"
    assert count_pending(cfg) == 0


def test_invent_peek_does_not_consume(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path, monkeypatch)

    class FakePlan:
        action = "walk forward"
        catalog_slug = "walk"
        reason = "hole"
        enters_from = ["idle"]
        exits_to = ["idle"]
        title_ru = "Ходьба"
        looped = True

    monkeypatch.setattr(
        "viu.lab.comfy_director.invent_shot_choices",
        lambda _c, limit=8: [FakePlan()],
    )
    rebuild_queue(cfg, limit=3)
    plan = invent_next_shot(cfg, consume_queue=False)
    assert plan.from_queue
    assert plan.catalog_slug == "walk"
    assert count_pending(cfg) == 1

    plan2 = invent_next_shot(cfg, consume_queue=True)
    assert plan2.from_queue
    assert count_pending(cfg) == 0


def test_update_prompt_keeps_pending(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path, monkeypatch)

    class FakePlan:
        action = "wave hello"
        catalog_slug = "wave"
        reason = "hole"
        enters_from = ["idle"]
        exits_to = ["idle"]
        title_ru = "Машет"
        looped = False

    monkeypatch.setattr(
        "viu.lab.comfy_director.invent_shot_choices",
        lambda _c, limit=8: [FakePlan()],
    )
    items = rebuild_queue(cfg, limit=2)
    updated = update_item(
        cfg,
        items[0].id,
        wan_positive="custom positive for wave",
        notes="не делай face closeup",
    )
    assert updated is not None
    loaded = load_items(cfg)
    assert loaded[0].wan_positive == "custom positive for wave"
    assert "face" in loaded[0].notes
