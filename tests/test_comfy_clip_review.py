"""Clip review store: keep/reject + parse replies."""

from pathlib import Path

from viu.config import Config
from viu.integrations.comfy.clip_review import (
    STATUS_KEPT,
    STATUS_REJECTED,
    ComfyClipStore,
    clip_review_path,
    format_candidates_message,
    keep_best_preferred_take,
    keep_clip,
    parse_clip_pick_reply,
    register_triple_batch,
    reject_batch,
)


def _cfg(tmp_path: Path, monkeypatch) -> Config:
    monkeypatch.setenv("VIU_DATA_DIR", str(tmp_path / ".viu"))
    monkeypatch.setenv("VIU_LIBRARY_ROOT", str(tmp_path / "Library"))
    data = tmp_path / ".viu"
    data.mkdir()
    (tmp_path / "Library" / "Lab" / "Refs").mkdir(parents=True)
    return Config(
        root=tmp_path / "Viu",
        data_dir=data,
        library_root=str(tmp_path / "Library"),
    )


def test_mocap_take_count():
    from viu.integrations.comfy.angles import default_angles, mocap_take_count

    assert mocap_take_count() == 5
    assert len(default_angles()) == 5


def test_is_prompt_show_request():
    from viu.integrations.comfy.prompt_edit import (
        is_comfy_short_task,
        is_prompt_show_request,
    )

    assert is_prompt_show_request("Покажи промпт")
    assert is_prompt_show_request("[Telegram] покажи wan промпт")
    assert is_prompt_show_request("что за промпт comfy")
    assert is_prompt_show_request("сделай промпт для ComfyUI под touch_self")
    assert is_comfy_short_task("накинь wan промпт для душа")
    assert not is_prompt_show_request("напиши сценарий игры на 10 страниц")


def test_parse_wan_editor():
    from viu.integrations.comfy.prompt_edit import _WAN_ACT_MARK, _WAN_NEG_MARK, _WAN_POS_MARK, parse_wan_editor_text

    raw = (
        f"{_WAN_POS_MARK}\n"
        "nude, idle, bed\n\n"
        f"{_WAN_NEG_MARK}\n"
        "blur\n\n"
        f"{_WAN_ACT_MARK}\n"
        "touch self slow\n"
    )
    p = parse_wan_editor_text(raw)
    assert "nude" in p["positive"]
    assert "blur" in p["negative"]
    assert "touch" in p["action"]


def test_parse_edited_draft():
    from viu.integrations.comfy.prompt_edit import parse_edited_draft

    raw = (
        "Действие: touch self on bed\n\n"
        "Промпт (MoCap ref, 5 дублей ¾, разный seed):\n"
        "nude young woman, idle, white background\n\n"
        "Кадр: вертикально.\n"
        "Negative:\nblur, text"
    )
    p = parse_edited_draft(raw)
    assert "touch self" in p["action"]
    assert "nude young woman" in p["positive"]
    assert "blur" in p["negative"]

    assert parse_clip_pick_reply("лучший: front")[0] == "keep"
    d, p = parse_clip_pick_reply("лучший: side 5 отлично")
    assert d == "keep"
    assert p["angle"] == "side"
    assert p["score"] == 5
    assert parse_clip_pick_reply("отклонить все")[0] == "reject_all"
    d2, p2 = parse_clip_pick_reply("лучший: front | лучший: take_a 4")
    assert d2 == "keep" and p2["angle"] == "front"


def test_keep_best_preferred_take_fallback(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path, monkeypatch)
    refs = tmp_path / "Library" / "Lab" / "Refs"
    fa = refs / "take_a.mp4"
    fc = refs / "take_c.mp4"
    fa.write_bytes(b"a")
    fc.write_bytes(b"c")
    register_triple_batch(
        cfg,
        action="touch self",
        results={
            "slug": "touch_batch",
            "angles": {
                "take_a": {"ok": True, "files": [str(fa)], "label": "дубль A"},
                "take_c": {"ok": True, "files": [str(fc)], "label": "дубль C"},
            },
        },
    )
    ok, msg, clip = keep_best_preferred_take(cfg, "touch_batch", prefer=("take_b", "take_a", "take_c"))
    assert ok and clip is not None
    assert clip.angle == "take_a"
    assert "fallback" in msg or "take_a" in msg


def test_register_and_keep(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path, monkeypatch)
    refs = tmp_path / "Library" / "Lab" / "Refs"
    f_side = refs / "batch_side_0.mp4"
    f_front = refs / "batch_front_0.mp4"
    f_side.write_bytes(b"fake")
    f_front.write_bytes(b"fake")
    results = {
        "slug": "idle_stand_20260101",
        "angles": {
            "side": {"ok": True, "files": [str(f_side)], "label": "сбоку"},
            "front": {"ok": True, "files": [str(f_front)], "label": "анфас"},
        },
    }
    clips = register_triple_batch(cfg, action="idle stand", results=results)
    assert len(clips) == 2
    msg = format_candidates_message(clips)
    assert "front" in msg

    # keep without ffmpeg — seed may fail but keep should copy
    ok, out, kept = keep_clip(cfg, clips[1].id, score=5, catalog_slug="idle", reject_siblings=True)
    assert ok and kept is not None
    assert kept.status == STATUS_KEPT
    assert Path(kept.path).is_file()
    store = ComfyClipStore(clip_review_path(cfg)).load()
    statuses = {c.angle: c.status for c in store.by_batch("idle_stand_20260101")}
    assert statuses["front"] == STATUS_KEPT
    assert statuses["side"] == STATUS_REJECTED


def test_reject_batch(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path, monkeypatch)
    refs = tmp_path / "Library" / "Lab" / "Refs"
    f = refs / "x.mp4"
    f.write_bytes(b"x")
    register_triple_batch(
        cfg,
        action="wave",
        results={"slug": "b1", "angles": {"front": {"ok": True, "files": [str(f)], "label": "анфас"}}},
    )
    ok, msg = reject_batch(cfg, "b1")
    assert ok
    store = ComfyClipStore(clip_review_path(cfg)).load()
    assert store.by_batch("b1")[0].status == STATUS_REJECTED
