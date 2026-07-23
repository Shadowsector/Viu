"""comfy_status brevity, focus cycle, stale prompt, ReActor reload."""

from pathlib import Path

from viu.config import Config
from viu.integrations.comfy.focus import action_is_stale, focus_cycle_status
from viu.integrations.comfy.lora import list_registry_status_brief
from viu.integrations.comfy.pipeline_status import comfy_pipeline_status
from viu.lab.comfy_pipeline import COMFY_TOPIC
from viu.lab.session import LabSession, save_session


def _cfg(tmp_path: Path, monkeypatch) -> Config:
    monkeypatch.setenv("VIU_DATA_DIR", str(tmp_path / ".viu"))
    monkeypatch.setenv("VIU_LIBRARY_ROOT", str(tmp_path / "Library"))
    monkeypatch.setenv("VIU_COMFY_FOCUS", "nsfw")
    data = tmp_path / ".viu"
    data.mkdir(parents=True)
    (tmp_path / "Library").mkdir(parents=True, exist_ok=True)
    return Config(root=tmp_path / "Viu", data_dir=data, library_root=str(tmp_path / "Library"))


def test_action_is_stale_touch_self():
    cfg = Config(root=Path("/x"), data_dir=Path("/x/.viu"))
    old = "private solo moment, seated or lying, slow self-touch, intimate breathing"
    assert action_is_stale(cfg, "touch_self", old)


def test_focus_cycle_nsfw_only_three_slugs(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path, monkeypatch)
    text = focus_cycle_status(cfg)
    assert "touch_self" in text
    assert "walk" not in text
    assert "NSFW" in text


def test_lora_brief_not_enumerating_all(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path, monkeypatch)
    from viu.integrations.comfy.lora import ensure_registry, scan_loras

    ensure_registry(cfg)
    text = list_registry_status_brief(cfg)
    assert "comfy_lora_list" in text
    assert "Список (номера" not in text


def test_pipeline_resyncs_stale_prompt(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path, monkeypatch)
    session = LabSession(id="t1", topic=COMFY_TOPIC)
    session.status = "running"
    session.step = 5
    session.meta = {
        "catalog_slug": "touch_self",
        "approved_action": "private solo moment, intimate breathing, shy closed eyes",
        "approved": True,
    }
    save_session(cfg, session)
    text = comfy_pipeline_status(cfg)
    assert "обновлён" in text or "touch self" in text.lower()
    assert "intimate breathing" not in text
