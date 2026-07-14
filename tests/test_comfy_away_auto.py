"""Away auto-approve for Comfy lab."""

from pathlib import Path
from unittest.mock import patch

from viu.config import Config
from viu.lab.comfy_pipeline import COMFY_TOPIC, step_draft_prompt, step_request_approval
from viu.lab.session import load_session, new_session, save_session
from viu.presence import MODE_AWAY, set_presence


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


def test_away_auto_approves_comfy(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path, monkeypatch)
    set_presence(cfg, MODE_AWAY)
    session = new_session(COMFY_TOPIC)
    session.steps_total = 7
    session.step = 3
    session.meta["action"] = "walking forward at a calm pace"
    session.status = "running"
    save_session(cfg, session)

    ok, msg, _ = step_draft_prompt(cfg, session)
    assert ok
    with patch("viu.lab.comfy_pipeline.send_prompt_for_approval") as send:
        ok2, msg2, _ = step_request_approval(cfg, session)
    assert ok2
    send.assert_not_called()
    loaded = load_session(cfg, COMFY_TOPIC)
    assert loaded is not None
    assert loaded.meta.get("approved") is True
    assert loaded.status == "running"
    assert "сама одобрила" in msg2.lower() or "away" in msg2.lower() or "Нет дома" in msg2
