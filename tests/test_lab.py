"""Тесты лаборатории Вью."""

from pathlib import Path

from viu.config import Config
from viu.lab.cascadeur_pipeline import CASCADEUR_TOPIC, ensure_task_file, run_one_step
from viu.lab.controller import lab_controller
from viu.lab.ratings import average_score, validate_ratings
from viu.lab.session import LabSession, load_session, new_session, save_session


def _cfg(tmp_path: Path) -> Config:
    import os

    os.environ["VIU_DATA_DIR"] = str(tmp_path / ".viu")
    return Config(root=tmp_path, data_dir=tmp_path / ".viu").ensure_dirs()


def test_lab_session_roundtrip(tmp_path):
    cfg = _cfg(tmp_path)
    s = new_session(CASCADEUR_TOPIC)
    s.step = 2
    save_session(cfg, s)
    loaded = load_session(cfg, CASCADEUR_TOPIC)
    assert loaded is not None
    assert loaded.step == 2
    assert loaded.status == "running"


def test_ratings_validate():
    vals = {
        "technique": 4,
        "creativity": 3,
        "effort": 5,
        "usefulness": 4,
        "clarity": 4,
    }
    ok, _ = validate_ratings(vals)
    assert ok
    assert 3.0 < average_score(vals) < 5.0


def test_lab_controller_pause():
    lab_controller.clear_operator_priority()
    lab_controller.request_operator_priority("test")
    assert lab_controller.is_paused()
    assert lab_controller.should_abort_step()
    lab_controller.acknowledge_abort()
    lab_controller.clear_operator_priority()
    assert not lab_controller.is_paused()


def test_cascadeur_task_file(tmp_path):
    cfg = _cfg(tmp_path)
    path = ensure_task_file(cfg)
    assert path.is_file()
    assert "Cascadeur" in path.read_text(encoding="utf-8")


def test_run_one_step_status(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    monkeypatch.setattr(
        "viu.lab.cascadeur_pipeline.cascadeur_status",
        lambda _c: (True, "mock status"),
    )
    s = new_session(CASCADEUR_TOPIC)
    save_session(cfg, s)
    ok, msg = run_one_step(cfg, s)
    assert ok
    assert "mock" in msg.lower() or "status" in msg.lower()
    loaded = load_session(cfg, CASCADEUR_TOPIC)
    assert loaded is not None
    assert loaded.step == 1
