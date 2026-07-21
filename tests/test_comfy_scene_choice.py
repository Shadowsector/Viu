"""Выбор сцены после 10 kept."""

from pathlib import Path

from viu.config import Config
from viu.integrations.comfy.scene_choice import (
    ComfySceneState,
    SceneProposal,
    apply_scene_choice,
    on_action_quota_reached,
    parse_scene_choice_reply,
    save_scene_state,
    scene_state_path,
)


def _cfg(tmp_path: Path, monkeypatch) -> Config:
    monkeypatch.setenv("VIU_DATA_DIR", str(tmp_path / ".viu"))
    monkeypatch.setenv("VIU_LIBRARY_ROOT", str(tmp_path / "Library"))
    data = tmp_path / ".viu"
    data.mkdir()
    return Config(root=tmp_path / "Viu", data_dir=data, library_root=str(tmp_path / "Library"))


def test_parse_scene_choice_number():
    d, p = parse_scene_choice_reply("2")
    assert d == "pick" and p["index"] == 2
    d2, p2 = parse_scene_choice_reply("2 только без drink")
    assert d2 == "pick" and p2["index"] == 2 and "без drink" in p2["notes"]


def test_apply_scene_choice_pick(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path, monkeypatch)
    st = ComfySceneState(
        awaiting_choice=True,
        completed_slug="walk",
        proposals=[
            SceneProposal("A", "desc a", ["sit_down"]),
            SceneProposal("B", "desc b", ["lie_down"]),
        ],
    )
    save_scene_state(cfg, st)
    msg = apply_scene_choice(cfg, "pick", {"index": 2, "notes": ""})
    assert "лечь" in msg.lower() or "lie" in msg.lower() or "B" in msg
    st2 = __import__("viu.integrations.comfy.scene_choice", fromlist=["load_scene_state"]).load_scene_state(cfg)
    assert not st2.awaiting_choice
    assert "lie_down" in st2.focus_slugs


def test_quota_triggers_pause(tmp_path, monkeypatch):
    monkeypatch.setenv("VIU_COMFY_MAX_PER_ACTION", "1")
    from viu.integrations.comfy.clip_review import ComfyClip, ComfyClipStore, STATUS_KEPT, clip_review_path

    cfg = _cfg(tmp_path, monkeypatch)
    store = ComfyClipStore(clip_review_path(cfg)).load()
    store.clips.append(
        ComfyClip(
            id="c1",
            batch_id="b",
            action="walk",
            angle="take_b",
            angle_label="b",
            path=str(tmp_path / "w.mp4"),
            status=STATUS_KEPT,
            catalog_slug="walk",
        )
    )
    store.save()
    msg = on_action_quota_reached(cfg, "walk", title_ru="Идёт")
    assert msg is not None
    assert scene_state_path(cfg).is_file()
