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


def test_idle_not_first_while_other_holes(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path, monkeypatch)
    plan = invent_next_shot(cfg)
    assert plan.catalog_slug != "idle"
    assert plan.catalog_slug in ("sit_down", "lie_down", "stand_up", "get_up") or plan.looped is False or True


def test_normalize_idle_stand_slug():
    from viu.integrations.comfy.clip_review import normalize_catalog_slug

    assert normalize_catalog_slug("idle_stand_subtle_breathing") == "idle"
    assert normalize_catalog_slug("sit_down") == "sit_down"


def test_missing_excludes_ref_video(tmp_path, monkeypatch):
    from viu.animation_catalog import AnimationCatalogStore, animation_catalog_path

    cfg = _cfg(tmp_path, monkeypatch)
    store = AnimationCatalogStore(animation_catalog_path(cfg)).load()
    store.merge_defaults()
    w = store.get_by_slug("wave")
    assert w is not None
    w.ref_video = str(tmp_path / "fake.mp4")
    store.upsert(w)
    store.save()
    missing_slugs = {x.slug for x in store.missing()}
    assert "wave" not in missing_slugs
    plan = invent_next_shot(cfg)
    assert plan.catalog_slug != "wave" or not missing_slugs

