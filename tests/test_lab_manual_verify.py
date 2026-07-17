"""Тесты проверки ручного import."""

from viu.config import Config
from viu.lab.cascadeur_pipeline import CASCADEUR_TOPIC
from viu.lab.manual_verify import CAPTURE_STEP, resume_for_manual_verify
from viu.lab.session import load_session, new_session, save_session
from viu.tools import AgentContext, build_default_registry
from viu.tools.lab_tool import LabStartTool


def _cfg(tmp_path):
    import os

    os.environ["VIU_DATA_DIR"] = str(tmp_path / ".viu")
    return Config(root=tmp_path, data_dir=tmp_path / ".viu").ensure_dirs()


def _ctx(cfg):
    from viu.memory import MemoryStore
    from viu.planning import Planner

    return AgentContext(
        config=cfg,
        memory=MemoryStore(cfg.data_dir / "memory.json"),
        planner=Planner(cfg.data_dir / "plan.json"),
        registry=build_default_registry(),
    )


def test_resume_for_manual_verify_rewinds_to_capture(tmp_path):
    cfg = _cfg(tmp_path)
    s = new_session(CASCADEUR_TOPIC)
    s.status = "awaiting_rating"
    s.step = 9
    save_session(cfg, s)
    resume_for_manual_verify(cfg, s)
    loaded = load_session(cfg, CASCADEUR_TOPIC)
    assert loaded is not None
    assert loaded.status == "running"
    assert loaded.step == CAPTURE_STEP
    assert loaded.launch_ok is True


def test_lab_start_run_all_after_awaiting_rating_verifies(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    s = new_session(CASCADEUR_TOPIC)
    s.status = "awaiting_rating"
    s.step = 9
    save_session(cfg, s)

    monkeypatch.setattr(
        "viu.lab.cascadeur_pipeline.run_until_done",
        lambda _c, _s: (True, "mock capture+report"),
    )

    tool = LabStartTool()
    result = tool.run({"topic": CASCADEUR_TOPIC, "run_all": "1"}, _ctx(cfg))
    assert result.ok
    text = result.content.lower()
    assert "ручной import" in text or "viewport" in text
    loaded = load_session(cfg, CASCADEUR_TOPIC)
    assert loaded is not None
    assert loaded.step == CAPTURE_STEP
    assert loaded.status == "running"
