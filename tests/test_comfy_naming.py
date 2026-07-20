"""Имена и лимиты Comfy MoCap."""

from pathlib import Path

from viu.config import Config
from viu.integrations.comfy.naming import (
    display_video_stem,
    max_clips_per_action,
    slug_at_quota,
)
from viu.integrations.comfy.clip_review import (
    ComfyClip,
    ComfyClipStore,
    STATUS_KEPT,
    clip_review_path,
    keep_clip,
)


def _cfg(tmp_path: Path, monkeypatch) -> Config:
    monkeypatch.setenv("VIU_DATA_DIR", str(tmp_path / ".viu"))
    monkeypatch.setenv("VIU_LIBRARY_ROOT", str(tmp_path / "Library"))
    data = tmp_path / ".viu"
    data.mkdir()
    (tmp_path / "Library").mkdir(parents=True, exist_ok=True)
    return Config(root=tmp_path / "Viu", data_dir=data, library_root=str(tmp_path / "Library"))


def test_display_video_stem_transition():
    stem = display_video_stem(catalog_slug="sit_down", enters_from=["idle"], take_id="take_b", seq=3)
    assert stem == "Girl_Idle_to_Sit_down_take_b_03"


def test_display_video_stem_loop():
    stem = display_video_stem(catalog_slug="walk", looped=True, seq=2)
    assert stem == "Girl_Walk_loop_02"


def test_slug_at_quota(monkeypatch, tmp_path):
    monkeypatch.setenv("VIU_COMFY_MAX_PER_ACTION", "2")
    cfg = _cfg(tmp_path, monkeypatch)
    store = ComfyClipStore(clip_review_path(cfg)).load()
    for i in range(2):
        store.clips.append(
            ComfyClip(
                id=f"c{i}",
                batch_id="b1",
                action="walk",
                angle="take_a",
                angle_label="a",
                path=str(tmp_path / f"w{i}.mp4"),
                status=STATUS_KEPT,
                catalog_slug="walk",
            )
        )
    store.save()
    assert slug_at_quota(cfg, "walk")
    assert not slug_at_quota(cfg, "sit_down")
    assert max_clips_per_action() == 2


def test_keep_clip_uses_display_name(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path, monkeypatch)
    src = tmp_path / "raw.mp4"
    src.write_bytes(b"mp4")
    store = ComfyClipStore(clip_review_path(cfg)).load()
    clip = ComfyClip(
        id="c1",
        batch_id="batch1",
        action="sit down",
        angle="take_b",
        angle_label="b",
        path=str(src),
        catalog_slug="sit_down",
        enters_from=["idle"],
    )
    store.clips.append(clip)
    store.save()
    ok, msg, kept = keep_clip(cfg, "c1", catalog_slug="sit_down", enters_from=["idle"])
    assert ok and kept is not None
    assert "Girl_Idle_to_Sit_down" in kept.path
