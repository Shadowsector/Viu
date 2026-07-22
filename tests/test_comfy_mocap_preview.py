"""Preview MoCap перед полными дублями."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from viu.config import Config
from viu.integrations.comfy.approval import parse_approval_reply
from viu.integrations.comfy.framing import PREVIEW_LENGTH, frame_spec_for_action
from viu.integrations.comfy.prompts import character_layout_hint, mocap_prompt
from viu.lab.comfy_pipeline import (
    COMFY_TOPIC,
    apply_preview_decision,
    step_generate_preview,
)
from viu.lab.session import load_session, new_session, save_session


def _cfg(tmp_path: Path) -> Config:
    data = tmp_path / ".viu"
    data.mkdir()
    return Config(
        root=tmp_path / "Viu",
        data_dir=data,
        library_root=str(tmp_path / "Library"),
        comfy_root="",
    )


def test_preview_frame_spec_shorter():
    full = frame_spec_for_action("idle stand breathing")
    prev = frame_spec_for_action("idle stand breathing", preview=True)
    assert prev.length == PREVIEW_LENGTH
    assert prev.length < full.length
    assert prev.width == full.width


def test_character_layout_single_vs_multi():
    single = character_layout_hint("idle stand")
    multi = character_layout_hint("two people walking")
    assert "single" in single.lower()
    assert "multiple" in multi.lower()
    assert "white" not in multi  # layout hint only


def test_mocap_prompt_includes_mocap_keywords():
    p = mocap_prompt("walk forward", None)
    assert "white" in p.lower()
    assert "mocap" in p.lower() or "motion capture" in p.lower()


def test_preview_approval_ok_advances_step(tmp_path):
    cfg = _cfg(tmp_path)
    session = new_session(COMFY_TOPIC)
    session.steps_total = 9
    session.step = 5
    session.status = "awaiting_preview"
    session.meta["approved"] = True
    session.meta["preview_video"] = "/tmp/preview.mp4"
    save_session(cfg, session)
    out = apply_preview_decision(cfg, load_session(cfg, COMFY_TOPIC), "approve", "idle")
    assert "3" in out or "дубл" in out.lower()
    loaded = load_session(cfg, COMFY_TOPIC)
    assert loaded.meta.get("preview_approved") is True
    assert loaded.step == 6


def test_preview_redraft_not_approved(tmp_path):
    cfg = _cfg(tmp_path)
    session = new_session(COMFY_TOPIC)
    session.steps_total = 9
    session.step = 5
    session.status = "awaiting_preview"
    session.meta["approved"] = True
    session.meta["catalog_slug"] = "sleep_idle"
    save_session(cfg, session)
    d, _ = parse_approval_reply("нет, другой кадр", current_action="sleep")
    assert d == "redraft"
    with patch("viu.lab.comfy_pipeline.send_prompt_for_approval", return_value=(True, "ok")):
        with patch("viu.lab.comfy_director.invent_redraft_shot") as inv:
            inv.return_value = type(
                "P",
                (),
                {
                    "action": "walk",
                    "catalog_slug": "walk",
                    "title_ru": "Ходьба",
                    "enters_from": [],
                    "exits_to": [],
                    "looped": True,
                    "reason": "x",
                },
            )()
            out = apply_preview_decision(cfg, load_session(cfg, COMFY_TOPIC), "redraft", "нет")
    assert "Поняла" in out or "кадр" in out.lower()
    loaded = load_session(cfg, COMFY_TOPIC)
    assert loaded.status == "awaiting_prompt"
    assert loaded.meta.get("preview_approved") is not True


def test_step_preview_away_skips(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    session = new_session(COMFY_TOPIC)
    session.steps_total = 9
    session.step = 5
    session.meta["approved"] = True
    session.meta["action"] = "wave hello"
    save_session(cfg, session)
    with patch("viu.presence.is_away", return_value=True):
        ok, msg, _ = step_generate_preview(cfg, load_session(cfg, COMFY_TOPIC))
    assert ok
    assert "пропущен" in msg.lower() or "дома" in msg.lower()
    assert load_session(cfg, COMFY_TOPIC).meta.get("preview_approved") is True
