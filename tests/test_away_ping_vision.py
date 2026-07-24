"""Away ping interval and vision first+last frame."""

from unittest.mock import patch

from viu.config import Config
from viu.integrations.comfy.vision_review import (
    ClipVisionReview,
    FrameVisionReview,
    _parse_verdict,
    _worst_verdict,
    review_triple_results,
)
from viu.runtime_settings import away_ping_interval_min, get_away_ping_per_day


def test_parse_verdict_ok():
    text = "ISSUES: нет\nVERDICT: OK\n"
    v, issues = _parse_verdict(text)
    assert v == "OK"
    assert issues == "нет"


def test_worst_verdict_picks_black_over_ok():
    assert _worst_verdict(["OK", "BLACK_FRAME"]) == "BLACK_FRAME"
    assert _worst_verdict(["OK", "OK"]) == "OK"


def test_away_ping_per_day_default(monkeypatch, tmp_path):
    monkeypatch.delenv("VIU_AWAY_PING_PER_DAY", raising=False)
    cfg = Config(
        root=tmp_path / "Viu",
        data_dir=tmp_path / ".viu",
        library_root=str(tmp_path / "Library"),
    )
    assert get_away_ping_per_day(cfg) == 3
    assert away_ping_interval_min(cfg) == 480


def test_away_ping_per_day_env(monkeypatch, tmp_path):
    monkeypatch.setenv("VIU_AWAY_PING_PER_DAY", "2")
    cfg = Config(
        root=tmp_path / "Viu",
        data_dir=tmp_path / ".viu",
        library_root=str(tmp_path / "Library"),
    )
    assert get_away_ping_per_day(cfg) == 2
    assert away_ping_interval_min(cfg) == 720


def test_review_triple_reports_frame_verdicts(tmp_path, monkeypatch):
    monkeypatch.setenv("VIU_DATA_DIR", str(tmp_path / ".viu"))
    monkeypatch.setenv("VIU_LIBRARY_ROOT", str(tmp_path / "Library"))
    cfg = Config(
        root=tmp_path / "Viu",
        data_dir=tmp_path / ".viu",
        library_root=str(tmp_path / "Library"),
    )
    good = tmp_path / "good.mp4"
    good.write_bytes(b"x" * 100)

    def fake_review(config, video, *, action="", angle=""):
        return ClipVisionReview(
            path=str(video),
            angle=angle,
            verdict="OK",
            issues="",
            vision_ok=True,
            vision_text="VERDICT: OK",
            frames=[
                FrameVisionReview("первый", "OK", "", True, "ok"),
                FrameVisionReview("последний", "OK", "", True, "ok"),
            ],
        )

    results = {
        "angles": {"take_a": {"files": [str(good)], "action_variant": "touch"}},
        "files": [str(good)],
    }
    with patch("viu.integrations.comfy.vision_review.review_mocap_clip", fake_review):
        out, msg = review_triple_results(cfg, results, action="touch")
    assert str(good) in out["files"]
    assert "первый=OK" in msg
