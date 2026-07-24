"""Comfy MoCap focus: NSFW vs barn cycle."""

from pathlib import Path

from viu.config import Config
from viu.integrations.comfy.focus import (
    NSFW_FOCUS_SLUGS,
    focus_mode_label,
    set_comfy_focus,
    slugs_for_mode,
)
from viu.integrations.comfy.scene_choice import load_scene_state
from viu.lab.comfy_director import invent_next_shot


def _cfg(tmp_path: Path, monkeypatch) -> Config:
    monkeypatch.setenv("VIU_DATA_DIR", str(tmp_path / ".viu"))
    data = tmp_path / ".viu"
    data.mkdir(parents=True)
    (tmp_path / "Library").mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("VIU_LIBRARY_ROOT", str(tmp_path / "Library"))
    return Config(root=tmp_path / "Viu", data_dir=data, library_root=str(tmp_path / "Library"))


def test_set_nsfw_focus(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path, monkeypatch)
    ok, msg = set_comfy_focus(cfg, "nsfw")
    assert ok
    assert "NSFW" in msg or "touch_self" in msg
    st = load_scene_state(cfg)
    assert "touch_self" in st.focus_slugs


def test_invent_next_respects_nsfw_focus(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path, monkeypatch)
    set_comfy_focus(cfg, "nsfw")
    plan = invent_next_shot(cfg)
    assert plan.catalog_slug in NSFW_FOCUS_SLUGS or plan.catalog_slug == ""


def test_env_migrate_nsfw(tmp_path, monkeypatch):
    monkeypatch.setenv("VIU_COMFY_FOCUS", "nsfw")
    cfg = _cfg(tmp_path, monkeypatch)
    from viu.integrations.comfy.focus import maybe_migrate_focus_from_env

    maybe_migrate_focus_from_env(cfg)
    assert focus_mode_label(cfg) == "NSFW"
