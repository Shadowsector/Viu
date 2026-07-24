"""Shoot intent must not stall on LoRA pick with empty Comfy queue."""

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


def test_shoot_intent_auto_picks_lora(tmp_path, monkeypatch):
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
        "viu.integrations.comfy.lora.specs_from_indices",
        return_value=[],
    ):
        ok, msg, _ = step_request_lora_pick(cfg, session)

    assert ok
    assert "очередь" in msg.lower() or "LoRA" in msg
    loaded = load_session(cfg, COMFY_TOPIC)
    assert loaded is not None
    assert loaded.meta.get("lora_pick_done") is True
    assert loaded.status != "awaiting_lora_pick"


def test_shoot_intent_flag_also_auto_picks(tmp_path, monkeypatch):
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
        "viu.integrations.comfy.lora.specs_from_indices",
        return_value=[],
    ):
        ok, msg, _ = step_request_lora_pick(cfg, session)

    assert ok
    assert session.meta.get("lora_pick_done") is True
    assert "shoot_intent" not in session.meta


def test_awaiting_prompt_with_shoot_does_not_early_return(tmp_path, monkeypatch):
    """lab_start shoot=1 while awaiting_prompt must continue, not stop at Telegram wait."""
    cfg = _cfg(tmp_path, monkeypatch)
    session = new_session(COMFY_TOPIC)
    session.status = "awaiting_prompt"
    session.step = 4
    session.meta["action"] = "sit on a bed"
    session.meta["wan_positive"] = "nude young woman sits on a bed"
    session.meta["prompt_user_edited"] = True
    save_session(cfg, session)

    calls = {"n": 0}

    def fake_run_until_done(config, sess):
        calls["n"] += 1
        sess.status = "running"
        save_session(config, sess)
        return True, "queued"

    with patch("viu.lab.comfy_pipeline.run_until_done", fake_run_until_done), patch(
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
    assert calls["n"] == 1
    assert "queued" in msg
    assert loaded is not None
    assert loaded.meta.get("shoot_intent") is True
