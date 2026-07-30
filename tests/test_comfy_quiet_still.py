"""Invent auto: не пропускать generate; короткий quiet notify."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from viu.config import Config
from viu.integrations.comfy.comfy_panel import apply_setup_and_start
from viu.integrations.comfy.shoot_settings import MODE_I2I, apply_shoot_settings
from viu.lab.comfy_pipeline import COMFY_TOPIC, step_request_approval, step_report
from viu.lab.notify import notify_lab_step
from viu.lab.session import load_session, new_session, save_session
from viu.presence import MODE_AWAY, set_presence


def _cfg(tmp_path: Path) -> Config:
    return Config(root=tmp_path, data_dir=tmp_path / ".viu").ensure_dirs()


def test_apply_setup_still_message(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    session = new_session(COMFY_TOPIC)
    session.step = 3
    session.meta["action"] = "standing with papers"
    apply_shoot_settings(session.meta, mode=MODE_I2I)
    session.meta["setup_lora_indices"] = []
    msg = apply_setup_and_start(cfg, session, jump_to_generate=False)
    assert "PNG" in msg
    assert "дубл" not in msg.lower()
    assert session.step == 3  # не прыгать на 5 изнутри approval


def test_quiet_notify_for_invent_still(tmp_path: Path, monkeypatch) -> None:
    cfg = _cfg(tmp_path)
    set_presence(cfg, MODE_AWAY)
    session = new_session(COMFY_TOPIC)
    apply_shoot_settings(session.meta, mode=MODE_I2I)
    session.meta["auto_invent_shoot"] = True
    save_session(cfg, session)
    sent = []

    monkeypatch.setattr(
        "viu.lab.notify._send", lambda config, text: sent.append(text) or True
    )
    assert notify_lab_step(cfg, 1, "Comfy online", "long spam") is False
    assert sent == []


def test_still_report_short(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    session = new_session(COMFY_TOPIC)
    apply_shoot_settings(session.meta, mode=MODE_I2I)
    session.meta["auto_invent_shoot"] = True
    session.meta["action"] = "papers"
    session.meta["clip_kept_id"] = "still_auto"
    session.meta["still_sent"] = 1
    session.append_artifact("/tmp/x.png")
    ok, msg, _ = step_report(cfg, session)
    assert ok
    assert "PNG" in msg
    assert "Cascadeur" not in msg
    assert len(msg) < 200
