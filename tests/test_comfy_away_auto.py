"""Away invent — авто; directed shoot — живая панель до «Снять»."""

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


def test_away_without_shoot_auto_starts(tmp_path, monkeypatch):
    """Тихий away invent — без панели, сразу approve+LoRA."""
    cfg = _cfg(tmp_path, monkeypatch)
    set_presence(cfg, MODE_AWAY)
    session = new_session(COMFY_TOPIC)
    session.steps_total = 8
    session.step = 3
    session.meta["action"] = "walking forward at a calm pace"
    session.meta["lora_last_pick"] = [1]
    session.status = "running"
    save_session(cfg, session)

    ok, msg, _ = step_draft_prompt(cfg, session)
    assert ok
    with patch(
        "viu.integrations.comfy.lora.scan_loras",
        return_value=[type("E", (), {"index": 1, "file": "x.safetensors"})()],
    ), patch(
        "viu.integrations.comfy.lora.specs_from_indices",
        return_value=[type("S", (), {"file": "x.safetensors", "strength": 0.8})()],
    ), patch(
        "viu.integrations.comfy.lora.spec_to_dict",
        return_value={"file": "x.safetensors", "strength": 0.8},
    ):
        ok2, msg2, _ = step_request_approval(cfg, session)
    assert ok2
    loaded = load_session(cfg, COMFY_TOPIC)
    assert loaded is not None
    assert loaded.status == "running"
    assert loaded.meta.get("approved") is True
    assert loaded.meta.get("lora_pick_done") is True
    assert "Снимаю" in msg2 or "очередь" in msg2.lower()


def test_shoot_intent_waits_for_panel_even_away(tmp_path, monkeypatch):
    """Съёмка из чата/кнопки — панель живая, даже если Нет дома."""
    cfg = _cfg(tmp_path, monkeypatch)
    set_presence(cfg, MODE_AWAY)
    session = new_session(COMFY_TOPIC)
    session.step = 3
    session.meta["action"] = "lounging in an armchair"
    session.meta["shoot_intent"] = True
    session.meta["shot_reason"] = "chat: directed scene"
    session.status = "running"
    save_session(cfg, session)

    ok, msg, _ = step_request_approval(cfg, session)
    assert ok
    loaded = load_session(cfg, COMFY_TOPIC)
    assert loaded is not None
    assert loaded.status == "awaiting_prompt"
    assert loaded.meta.get("approved") is False
    assert "панель" in msg.lower() or "жду" in msg.lower() or "снять" in msg.lower()


def test_away_lora_step_noop_after_auto(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path, monkeypatch)
    set_presence(cfg, MODE_AWAY)
    session = new_session(COMFY_TOPIC)
    session.status = "running"
    session.step = 4
    session.meta["approved"] = True
    session.meta["lora_pick_done"] = True
    session.meta["selected_loras"] = [{"file": "x.safetensors", "strength": 0.8}]
    session.meta["action"] = "idle stand"
    save_session(cfg, session)

    ok, msg, _ = step_request_lora_pick(cfg, session)
    assert ok
    assert "LoRA" in msg
    assert session.status != "awaiting_lora_pick"


def test_invent_auto_from_shoot_panel_skips_awaiting(tmp_path, monkeypatch):
    """chat: invent auto + from_shoot_panel → сразу генерация, не панель."""
    cfg = _cfg(tmp_path, monkeypatch)
    set_presence(cfg, MODE_HOME)
    session = new_session(COMFY_TOPIC)
    session.step = 3
    session.meta["action"] = "sitting in an armchair, full body"
    session.meta["wan_positive"] = (
        "a fit girl with a big fake breast and perfect body is sitting in an armchair"
    )
    session.meta["from_shoot_panel"] = True
    session.meta["auto_invent_shoot"] = True
    session.meta["shot_reason"] = "chat: invent auto"
    session.meta["setup_lora_indices"] = []
    session.meta["shoot_mode"] = "i2i"
    session.status = "running"
    save_session(cfg, session)

    seen = {}

    def _fake_start(config, sess, jump_to_generate=False):
        del config
        seen["jump"] = jump_to_generate
        save_session(cfg, sess)
        return "Делаю PNG (i2i)."

    with patch(
        "viu.integrations.comfy.comfy_panel.apply_setup_and_start",
        side_effect=_fake_start,
    ) as start:
        ok, msg, _ = step_request_approval(cfg, session)
    assert ok
    assert start.called
    assert seen.get("jump") is False  # не пропускать generate
    assert "from_shoot_panel" not in (session.meta or {})
    assert "PNG" in msg or "Снимаю" in msg
    loaded = load_session(cfg, COMFY_TOPIC)
    assert loaded is not None
    assert "from_shoot_panel" not in (loaded.meta or {})
    assert loaded.status != "awaiting_prompt"

