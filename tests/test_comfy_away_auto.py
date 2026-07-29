"""Away / shoot: TG уведомляет, съёмка не стопорит Comfy."""

from pathlib import Path
from unittest.mock import patch

from viu.config import Config
from viu.lab.comfy_pipeline import (
    COMFY_TOPIC,
    step_draft_prompt,
    step_request_approval,
    step_request_lora_pick,
)
from viu.lab.session import load_session, new_session, save_session
from viu.presence import MODE_AWAY, MODE_HOME, set_presence


def _cfg(tmp_path: Path, monkeypatch) -> Config:
    monkeypatch.setenv("VIU_DATA_DIR", str(tmp_path / ".viu"))
    monkeypatch.setenv("VIU_LIBRARY_ROOT", str(tmp_path / "Library"))
    data = tmp_path / ".viu"
    data.mkdir()
    (tmp_path / "Library").mkdir(parents=True, exist_ok=True)
    (tmp_path / "Viu").mkdir(parents=True, exist_ok=True)
    return Config(
        root=tmp_path / "Viu",
        data_dir=data,
        library_root=str(tmp_path / "Library"),
    )


def test_away_without_shoot_waits_for_prompt(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path, monkeypatch)
    set_presence(cfg, MODE_AWAY)
    session = new_session(COMFY_TOPIC)
    session.steps_total = 8
    session.step = 3
    session.meta["action"] = "walking forward at a calm pace"
    session.status = "running"
    save_session(cfg, session)

    ok, msg, _ = step_draft_prompt(cfg, session)
    assert ok
    with patch(
        "viu.lab.comfy_pipeline.send_prompt_for_approval",
        return_value=(True, "Промпт ушёл в Telegram — жду ок / правки / стоп."),
    ) as send:
        ok2, msg2, _ = step_request_approval(cfg, session)
    assert ok2
    send.assert_called_once()
    loaded = load_session(cfg, COMFY_TOPIC)
    assert loaded is not None
    assert loaded.status == "awaiting_prompt"
    assert loaded.meta.get("approved") is False
    assert "телеграм" in msg2.lower() or "жду" in msg2.lower()


def test_shoot_intent_auto_approves_even_away(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path, monkeypatch)
    set_presence(cfg, MODE_AWAY)
    session = new_session(COMFY_TOPIC)
    session.step = 3
    session.meta["action"] = "lounging in an armchair"
    session.meta["shoot_intent"] = True
    session.meta["shot_reason"] = "chat: directed scene"
    session.status = "running"
    save_session(cfg, session)

    with patch(
        "viu.lab.comfy_pipeline.send_prompt_for_approval",
        return_value=(True, "sent"),
    ) as send:
        ok, msg, _ = step_request_approval(cfg, session)
    assert ok
    send.assert_called_once()
    loaded = load_session(cfg, COMFY_TOPIC)
    assert loaded is not None
    assert loaded.status == "running"
    assert loaded.meta.get("approved") is True
    assert "иду дальше" in msg.lower() or "съёмка" in msg.lower()


def test_away_without_shoot_asks_lora(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path, monkeypatch)
    set_presence(cfg, MODE_AWAY)
    session = new_session(COMFY_TOPIC)
    session.status = "running"
    session.step = 4
    session.meta["approved"] = True
    session.meta["action"] = "idle stand"
    session.meta["lora_last_pick"] = [1]
    save_session(cfg, session)

    fake_entries = [type("E", (), {"index": 1, "file": "x.safetensors"})()]

    with patch(
        "viu.integrations.comfy.lora.scan_loras",
        return_value=fake_entries,
    ), patch(
        "viu.integrations.comfy.lora.format_lora_pick_message",
        return_value="lora list",
    ), patch(
        "viu.integrations.comfy.lora.format_lora_pick_telegram",
        return_value=["1. x.safetensors"],
    ):
        ok, msg, _ = step_request_lora_pick(cfg, session)

    assert ok
    loaded = load_session(cfg, COMFY_TOPIC)
    assert loaded is not None
    assert loaded.status == "awaiting_lora_pick"
    assert not loaded.meta.get("lora_pick_done")


def test_home_lab_still_awaits_prompt(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path, monkeypatch)
    set_presence(cfg, MODE_HOME)
    session = new_session(COMFY_TOPIC)
    session.step = 3
    session.meta["action"] = "wave hello"
    session.status = "running"
    save_session(cfg, session)
    with patch(
        "viu.lab.comfy_pipeline.send_prompt_for_approval",
        return_value=(True, "sent"),
    ):
        ok, msg, _ = step_request_approval(cfg, session)
    assert ok
    assert load_session(cfg, COMFY_TOPIC).status == "awaiting_prompt"
