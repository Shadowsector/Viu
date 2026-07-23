"""Comfy MoCap vision review (llava)."""

from unittest.mock import patch

from viu.config import Config
from viu.integrations.comfy.vision_review import (
    ClipVisionReview,
    _parse_verdict,
    review_triple_results,
    vision_review_enabled,
)


def test_parse_verdict_ok():
    text = "ISSUES: нет\nVERDICT: OK\n"
    v, issues = _parse_verdict(text)
    assert v == "OK"
    assert issues == "нет"


def test_parse_verdict_black():
    text = "VERDICT: BLACK_FRAME\nISSUES: чёрный кадр\n"
    v, _ = _parse_verdict(text)
    assert v == "BLACK_FRAME"


def test_parse_verdict_heuristic_ru():
    v, _ = _parse_verdict("Похоже на пустой чёрный кадр без персонажа.")
    assert v == "BLACK_FRAME"


def test_vision_review_enabled_default(monkeypatch):
    monkeypatch.delenv("VIU_COMFY_VISION", raising=False)
    assert vision_review_enabled()


def test_vision_review_disabled(monkeypatch):
    monkeypatch.setenv("VIU_COMFY_VISION", "0")
    assert not vision_review_enabled()


def test_review_triple_auto_rejects_bad(tmp_path, monkeypatch):
    monkeypatch.setenv("VIU_DATA_DIR", str(tmp_path / ".viu"))
    monkeypatch.setenv("VIU_LIBRARY_ROOT", str(tmp_path / "Library"))
    cfg = Config(
        root=tmp_path / "Viu",
        data_dir=tmp_path / ".viu",
        library_root=str(tmp_path / "Library"),
    )
    good = tmp_path / "good.mp4"
    bad = tmp_path / "bad.mp4"
    good.write_bytes(b"x" * 100)
    bad.write_bytes(b"y" * 100)

    def fake_review(config, video, *, action="", angle=""):
        p = str(video)
        if "bad" in p:
            return ClipVisionReview(
                path=p,
                angle=angle,
                verdict="BLACK_FRAME",
                issues="чёрный",
                vision_ok=True,
                vision_text="VERDICT: BLACK_FRAME",
            )
        return ClipVisionReview(
            path=p,
            angle=angle,
            verdict="OK",
            issues="",
            vision_ok=True,
            vision_text="VERDICT: OK",
        )

    results = {
        "angles": {
            "take_a": {"files": [str(good)], "action_variant": "touch"},
            "take_b": {"files": [str(bad)], "action_variant": "touch"},
        },
        "files": [str(good), str(bad)],
    }
    with patch("viu.integrations.comfy.vision_review.review_mocap_clip", fake_review):
        out, msg = review_triple_results(cfg, results, action="touch")
    assert str(good) in out["files"]
    assert str(bad) not in out["files"]
    assert "BLACK_FRAME" in msg
