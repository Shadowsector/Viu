"""Comfy pipeline status brief for GUI."""

from pathlib import Path

from viu.config import Config
from viu.integrations.comfy.pipeline_status import comfy_pipeline_status_brief
from viu.lab.comfy_pipeline import COMFY_TOPIC
from viu.lab.session import LabSession, save_session


def _cfg(tmp_path: Path, monkeypatch) -> Config:
    monkeypatch.setenv("VIU_DATA_DIR", str(tmp_path / ".viu"))
    data = tmp_path / ".viu"
    data.mkdir(parents=True)
    return Config(root=tmp_path / "Viu", data_dir=data)


def test_brief_no_session(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path, monkeypatch)
    line = comfy_pipeline_status_brief(cfg)
    assert "Comfy" in line
    assert "lab нет" in line


def test_brief_awaiting_prompt(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path, monkeypatch)
    session = LabSession(id="t1", topic=COMFY_TOPIC)
    session.status = "awaiting_prompt"
    session.step = 3
    session.steps_total = 8
    session.meta = {"catalog_slug": "sit_down", "action": "sitting down"}
    save_session(cfg, session)
    line = comfy_pipeline_status_brief(cfg)
    assert "жду промпт" in line
    assert "sit_down" in line
