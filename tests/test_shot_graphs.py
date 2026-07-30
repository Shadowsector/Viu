"""Каталог графов MoCap и LoRA на кадре очереди."""

from pathlib import Path

from viu.config import Config
from viu.integrations.comfy.shot_graphs import (
    graph_for_slug,
    graph_path_label,
    group_items_by_graph,
)
from viu.integrations.comfy.shot_queue import (
    ShotQueueItem,
    load_items,
    rebuild_queue,
    update_item,
)


def test_graph_for_sleep_and_climb():
    assert graph_for_slug("sleep_idle").id == "sleep"
    assert graph_for_slug("lie_down").title_ru == "Лечь спать"
    assert graph_for_slug("climb_up").id == "climb"
    assert graph_for_slug("kneel").id == "floor"
    assert graph_for_slug("all_fours").id == "floor"
    assert graph_for_slug("unknown_slug").id == "other"


def test_group_items_by_graph_order():
    items = [
        ShotQueueItem(id="1", catalog_slug="climb_up", action="climb"),
        ShotQueueItem(id="2", catalog_slug="sleep_idle", action="sleep"),
        ShotQueueItem(id="3", catalog_slug="lie_down", action="lie"),
        ShotQueueItem(id="4", catalog_slug="custom_x", action="x"),
    ]
    groups = group_items_by_graph(items)
    ids = [g.id for g, _ in groups]
    assert ids[0] == "sleep"
    assert ids[1] == "climb"
    assert ids[-1] == "other"
    sleep_chunk = groups[0][1]
    assert [i.catalog_slug for i in sleep_chunk] == ["sleep_idle", "lie_down"]


def test_graph_path_label():
    label = graph_path_label(
        "sleep_idle", enters_from=["lie_down"], exits_to=["get_up"]
    )
    assert "Лечь спать" in label
    assert "lie_down" in label
    assert "get_up" in label


def test_queue_lora_fields_persist(tmp_path, monkeypatch):
    monkeypatch.setenv("VIU_DATA_DIR", str(tmp_path / ".viu"))
    monkeypatch.setenv("VIU_LIBRARY_ROOT", str(tmp_path / "Library"))
    data = tmp_path / ".viu"
    data.mkdir()
    (tmp_path / "Library").mkdir(parents=True, exist_ok=True)
    cfg = Config(
        root=tmp_path,
        data_dir=data,
        library_root=str(tmp_path / "Library"),
    ).ensure_dirs()

    class FakePlan:
        action = "lie down"
        catalog_slug = "lie_down"
        reason = "hole"
        enters_from = ["idle"]
        exits_to = ["sleep_idle"]
        title_ru = "Лечь"
        looped = False

    monkeypatch.setattr(
        "viu.lab.comfy_director.invent_shot_choices",
        lambda _c, limit=8: [FakePlan()],
    )
    items = rebuild_queue(cfg, limit=2)
    update_item(
        cfg,
        items[0].id,
        lora_mode="pick",
        lora_indices=[1, 3],
        wan_positive="custom sleep pos",
    )
    loaded = load_items(cfg)
    assert loaded[0].lora_mode == "pick"
    assert loaded[0].lora_indices == [1, 3]
    assert loaded[0].wan_positive == "custom sleep pos"

    # rebuild keep_edits сохраняет LoRA
    rebuild_queue(cfg, limit=2, keep_edits=True)
    again = load_items(cfg)
    assert again[0].lora_mode == "pick"
    assert again[0].lora_indices == [1, 3]
