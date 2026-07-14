"""Comfy director invents shots from catalog."""

from pathlib import Path

from viu.config import Config
from viu.lab.comfy_director import invent_next_shot, invent_next_action


def _cfg(tmp_path: Path, monkeypatch) -> Config:
    monkeypatch.setenv("VIU_DATA_DIR", str(tmp_path / ".viu"))
    monkeypatch.setenv("VIU_LIBRARY_ROOT", str(tmp_path / "Library"))
    data = tmp_path / ".viu"
    data.mkdir()
    (tmp_path / "Library").mkdir(parents=True, exist_ok=True)
    return Config(root=tmp_path / "Viu", data_dir=data, library_root=str(tmp_path / "Library"))


def test_invent_prefers_non_idle(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path, monkeypatch)
    plan = invent_next_shot(cfg)
    assert plan.action
    assert plan.catalog_slug
    # при полном каталоге missing — не обязан быть idle первым
    assert "reason" in plan.summary_ru().lower() or "Почему" in plan.summary_ru()


def test_invent_action_string(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path, monkeypatch)
    action = invent_next_action(cfg)
    assert isinstance(action, str) and len(action) > 10
