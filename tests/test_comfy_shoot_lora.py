"""Directed shoot: LoRA/промпт ждут панель; «Снять» стартует генерацию."""

from pathlib import Path
from unittest.mock import MagicMock, patch

from viu.config import Config
from viu.integrations.comfy.comfy_panel import apply_setup_and_start, set_setup_lora_indices
from viu.lab.comfy_pipeline import COMFY_TOPIC, apply_lora_pick_decision, step_request_lora_pick
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


def test_shoot_intent_lora_step_returns_to_panel(tmp_path, monkeypatch):
    """Без lora_pick_done — не стартуем gen, возвращаем на панель."""
    cfg = _cfg(tmp_path, monkeypatch)
    session = new_session(COMFY_TOPIC)
    session.status = "running"
    session.step = 4
    session.meta["auto_approved_shoot"] = True
    session.meta["shoot_intent"] = True
    session.meta["action"] = "sit up on a bed"
    session.meta["lora_last_pick"] = [1]
    save_session(cfg, session)

    with patch(
        "viu.integrations.comfy.lora.scan_loras",
        return_value=[type("E", (), {"index": 1, "file": "x.safetensors"})()],
    ), patch(
        "viu.integrations.comfy.comfy_panel.send_lora_menu",
        return_value=(True, "menu"),
    ), patch(
        "viu.integrations.comfy.comfy_panel.send_control_panel",
        return_value=(True, "Панель в Telegram — жду «Снять»."),
    ):
        ok, msg, _ = step_request_lora_pick(cfg, session)

    assert ok
    loaded = load_session(cfg, COMFY_TOPIC)
    assert loaded is not None
    assert loaded.status == "awaiting_prompt"
    assert not loaded.meta.get("lora_pick_done")
    assert "Снять" in msg or "панель" in msg.lower()


def test_lora_pick_stores_without_starting(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path, monkeypatch)
    session = new_session(COMFY_TOPIC)
    session.status = "awaiting_lora_pick"
    session.step = 4
    session.meta["action"] = "from standing to sit on a bed"
    save_session(cfg, session)

    fake_spec = MagicMock(file="a.safetensors", strength=0.75)
    with patch(
        "viu.integrations.comfy.lora.scan_loras",
        return_value=[type("E", (), {"index": 1, "file": "a.safetensors"})()],
    ), patch(
        "viu.integrations.comfy.lora.specs_from_indices",
        return_value=[fake_spec],
    ), patch(
        "viu.integrations.comfy.lora.spec_to_dict",
        return_value={"file": "a.safetensors", "strength": 0.75},
    ), patch(
        "viu.integrations.comfy.comfy_panel.send_control_panel",
        return_value=(True, "Панель"),
    ):
        msg = apply_lora_pick_decision(cfg, session, [1])

    loaded = load_session(cfg, COMFY_TOPIC)
    assert loaded is not None
    assert loaded.status == "awaiting_prompt"
    assert loaded.meta.get("setup_lora_indices") == [1]
    assert not loaded.meta.get("lora_pick_done")
    assert "Снять" in msg


def test_awaiting_prompt_lab_start_waits(tmp_path, monkeypatch):
    """lab_start при awaiting_prompt без явного Shoot — не форсирует очередь."""
    cfg = _cfg(tmp_path, monkeypatch)
    session = new_session(COMFY_TOPIC)
    session.status = "awaiting_prompt"
    session.step = 4
    session.meta["action"] = "sit on a bed"
    session.meta["wan_positive"] = "nude young woman sits on a bed"
    session.meta["prompt_user_edited"] = True
    save_session(cfg, session)

    with patch("viu.lab.comfy_pipeline.ensure_task_file"), patch(
        "viu.lab.comfy_pipeline.run_until_done"
    ) as run_all, patch("viu.lab.comfy_pipeline.run_one_step", return_value=(True, "ok")):
        ok, msg, loaded = run_lab_prepared(
            cfg,
            COMFY_TOPIC,
            force_reset=False,
            run_all=True,
            action="sit on a bed",
            meta_extra={"shoot_intent": True},
        )

    assert ok
    run_all.assert_not_called()
    assert "панель" in msg.lower() or "Жду" in msg
    assert loaded is not None
    assert loaded.status == "awaiting_prompt"
    assert loaded.meta.get("approved") is not True


def test_apply_setup_starts_generate(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path, monkeypatch)
    session = new_session(COMFY_TOPIC)
    session.status = "awaiting_prompt"
    session.step = 4
    session.meta["action"] = "wave hello"
    set_setup_lora_indices(session, [])
    save_session(cfg, session)

    with patch("viu.integrations.comfy.lora.scan_loras", return_value=[]), patch(
        "viu.integrations.comfy.lora.specs_from_indices",
        return_value=[],
    ), patch(
        "viu.integrations.comfy.lora.spec_to_dict",
        return_value={},
    ):
        msg = apply_setup_and_start(cfg, session)

    loaded = load_session(cfg, COMFY_TOPIC)
    assert loaded is not None
    assert loaded.status == "running"
    assert loaded.meta.get("approved") is True
    assert loaded.meta.get("lora_pick_done") is True
    assert loaded.step == 5
    assert "Снимаю" in msg
