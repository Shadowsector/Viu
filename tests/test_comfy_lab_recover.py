"""Comfy lab: recover при offline, не слепой повтор."""

from pathlib import Path
from unittest.mock import patch

from viu.config import Config
from viu.lab.comfy_pipeline import COMFY_TOPIC, step_generate_triple
from viu.lab.prepare import prepare_lab_session, run_lab_prepared
from viu.lab.session import LabSession, new_session, save_session


def _cfg(tmp_path: Path) -> Config:
    data = tmp_path / ".viu"
    data.mkdir(parents=True, exist_ok=True)
    return Config(root=tmp_path / "Viu", data_dir=data, comfy_url="http://127.0.0.1:8188")


def test_comfy_recover_mode_after_two_fails(tmp_path):
    cfg = _cfg(tmp_path)
    s = new_session(COMFY_TOPIC)
    s.status = "running"
    s.step = 4
    s.last_fail_step = 4
    s.step_fail_counts = {"4": 2}
    s.last_fail_msg = "ComfyUI недоступен"
    s.viu_build_stamp = "test"
    save_session(cfg, s)

    with patch("viu.lab.prepare.viu_build_stamp", return_value="test"):
        with patch("viu.lab.prepare.build_changed_since_last_run", return_value=False):
            session, mode, note = prepare_lab_session(cfg, COMFY_TOPIC)
    assert mode == "recover"
    assert "recover" in note.lower() or "Застряла" in note


def test_generate_pauses_when_comfy_down(tmp_path):
    cfg = _cfg(tmp_path)
    s = new_session(COMFY_TOPIC)
    s.status = "running"
    s.step = 4
    s.meta["approved"] = True
    s.meta["approved_action"] = "wave hello"
    s.meta["catalog_slug"] = "wave"

    class FakeClient:
        def __init__(self, *a, **k):
            pass

        def ping(self):
            return False, "connection refused"

    with patch("viu.integrations.comfy.client.ComfyClient", FakeClient):
        with patch(
            "viu.lab.comfy_pipeline.ensure_comfy_running",
            return_value=(False, "не смогла поднять"),
        ):
            ok, msg, _ = step_generate_triple(cfg, s)
    assert ok is False
    assert s.status == "paused"
    assert s.pause_reason == "comfy_offline"
    assert "паузе" in msg.lower() or "недоступен" in msg.lower()


def test_run_lab_prepared_calls_comfy_recover(tmp_path):
    cfg = _cfg(tmp_path)
    s = new_session(COMFY_TOPIC)
    s.status = "paused"
    s.pause_reason = "comfy_offline"
    s.step = 4
    s.last_fail_step = 4
    s.step_fail_counts = {"4": 5}
    s.last_fail_msg = "10061"
    s.viu_build_stamp = "test"
    save_session(cfg, s)

    with patch("viu.lab.prepare.viu_build_stamp", return_value="test"):
        with patch("viu.lab.prepare.build_changed_since_last_run", return_value=False):
            with patch(
                "viu.lab.prepare.recover_stuck_step",
                return_value=(False, "RECOVER: comfy offline"),
            ) as rec:
                ok, msg, _sess = run_lab_prepared(cfg, COMFY_TOPIC, run_all=False)
    assert rec.called
    assert "RECOVER" in msg
    assert ok is False
