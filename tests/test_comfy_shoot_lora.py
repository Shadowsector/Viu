"""Shoot intent: всё равно ждём LoRA в Telegram; lab не стопорит зря на awaiting_prompt без ответа."""

from pathlib import Path
from unittest.mock import patch

from viu.config import Config
from viu.lab.comfy_pipeline import COMFY_TOPIC, step_request_lora_pick
from viu.lab.prepare import run_lab_prepared
from viu.lab.session import load_session, new_session, save_session


def _cfg(tmp_path: Path, monkeypatch) -> Config:
    monkeypatch.setenv("VIU_DATA_DIR", str(tmp_path / ".viu"))
    monkeypatch.setenv("VIU_LIBRARY_ROOT", str(tmp_path / "Library"))
    data = tmp_path / ".viu"
    data.mkdir()
    (tmp_path / "Library").mkdir(parents=True, exist_ok=True)
    return Config(
        root=tmp_path,
        data_dir=data,
        library_root=str(tmp_path / "Library"),
    )


def test_shoot_intent_still_awaits_lora(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path, monkeypatch)
    session = new_session(COMFY_TOPIC)
    session.status = "running"
    session.step = 4
    session.meta["auto_approved_shoot"] = True
    session.meta["action"] = "sit up on a bed"
    save_session(cfg, session)

    fake_entries = [type("E", (), {"index": 1, "file": "x.safetensors"})()]

    with patch(
        "viu.integrations.comfy.lora.scan_loras",
        return_value=fake_entries,
    ), patch(
        "viu.integrations.comfy.lora.format_lora_pick_message",
        return_value="Выбери LoRA",
    ), patch(
        "viu.integrations.comfy.lora.format_lora_pick_telegram",
        return_value=["1. x"],
    ):
        ok, msg, _ = step_request_lora_pick(cfg, session)

    assert ok
    loaded = load_session(cfg, COMFY_TOPIC)
    assert loaded is not None
    assert loaded.status == "awaiting_lora_pick"
    assert not loaded.meta.get("lora_pick_done")
    assert "lora" in msg.lower() or "LoRA" in msg


def test_shoot_intent_flag_also_awaits_lora(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path, monkeypatch)
    session = new_session(COMFY_TOPIC)
    session.status = "running"
    session.step = 4
    session.meta["shoot_intent"] = True
    session.meta["action"] = "from standing to sit on a bed"
    save_session(cfg, session)

    with patch(
        "viu.integrations.comfy.lora.scan_loras",
        return_value=[type("E", (), {"index": 1, "file": "a.safetensors"})()],
    ), patch(
        "viu.integrations.comfy.lora.format_lora_pick_message",
        return_value="list",
    ), patch(
        "viu.integrations.comfy.lora.format_lora_pick_telegram",
        return_value=["1. a"],
    ):
        ok, msg, _ = step_request_lora_pick(cfg, session)

    assert ok
    assert session.status == "awaiting_lora_pick"
    assert not session.meta.get("lora_pick_done")
    assert "shoot_intent" not in session.meta


def test_awaiting_prompt_with_shoot_still_waits(tmp_path, monkeypatch):
    """lab_start shoot=1 при awaiting_prompt не авто-одобряет — ждём Telegram."""
    cfg = _cfg(tmp_path, monkeypatch)
    session = new_session(COMFY_TOPIC)
    session.status = "awaiting_prompt"
    session.step = 3
    session.meta["action"] = "sit on a bed"
    session.meta["wan_positive"] = "nude young woman sits on a bed"
    session.meta["prompt_user_edited"] = True
    save_session(cfg, session)

    with patch("viu.lab.comfy_pipeline.run_until_done") as run_done, patch(
        "viu.lab.comfy_pipeline.ensure_task_file"
    ), patch("viu.lab.comfy_pipeline.run_one_step", return_value=(True, "ok")):
        ok, msg, loaded = run_lab_prepared(
            cfg,
            COMFY_TOPIC,
            force_reset=False,
            run_all=True,
            action="sit on a bed",
            meta_extra={"shoot_intent": True},
        )

    assert ok
    run_done.assert_not_called()
    assert "жду" in msg.lower() or "telegram" in msg.lower() or "промпт" in msg.lower()
    assert loaded is not None
    assert loaded.status == "awaiting_prompt"
    assert loaded.meta.get("shoot_intent") is True
