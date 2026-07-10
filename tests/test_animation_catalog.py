"""Тесты каталога анимаций и drop_router."""

from pathlib import Path

from viu.animation_catalog import (
    AnimationCatalogStore,
    animation_catalog_path,
    match_fbx_to_wish,
)
from viu.animation_catalog.models import DEFAULT_WISHES
from viu.config import Config
from viu.drop_router import is_character_animation_fbx, route_inbox


def test_default_wishes_seeded():
    assert len(DEFAULT_WISHES) >= 20
    slugs = {w.slug for w in DEFAULT_WISHES}
    assert "climb_up" in slugs
    assert "sit_down" in slugs


def test_store_seed_and_summary(tmp_path):
    path = tmp_path / ".viu" / "animation_catalog.json"
    store = AnimationCatalogStore(path).load()
    assert len(store.all_wishes()) >= 20
    text = store.summary_text()
    assert "wave 1" in text.lower() or "Не хватает" in text


def test_match_climbing_fbx(tmp_path):
    store = AnimationCatalogStore(tmp_path / "cat.json").load()
    fbx = tmp_path / "X Bot@Female Climbing.fbx"
    fbx.write_bytes(b"x")
    wish, score, _ = match_fbx_to_wish(fbx, store)
    assert wish is not None
    assert wish.slug == "climb_up"
    assert score >= 0.65


def test_match_sitting_down(tmp_path):
    store = AnimationCatalogStore(tmp_path / "cat.json").load()
    fbx = tmp_path / "Sitting Down.fbx"
    fbx.write_bytes(b"x")
    wish, score, _ = match_fbx_to_wish(fbx, store)
    assert wish is not None
    assert wish.slug in ("sit_down", "sit_idle")


def test_is_animation_not_barn():
    assert is_character_animation_fbx(Path("Idle.fbx"))
    assert not is_character_animation_fbx(Path("Old_Stables.fbx"))


def test_route_inbox_animation(tmp_path, monkeypatch):
    inbox = tmp_path / "Inbox"
    inbox.mkdir()
    staging = tmp_path / "Animations"
    unity = tmp_path / "Unity" / "Anabarra" / "Assets"
    unity.mkdir(parents=True)
    lib = tmp_path / "Library"
    (inbox / "Yawn.fbx").write_bytes(b"fbx")

    import os

    os.environ["VIU_INBOX_DIR"] = str(inbox)
    os.environ["VIU_LIBRARY_ROOT"] = str(lib)
    os.environ["VIU_ANIM_STAGING"] = str(staging)
    os.environ["VIU_UNITY_PROJECT"] = str(unity.parent.parent)
    try:
        cfg = Config(
            root=tmp_path / "Viu",
            data_dir=tmp_path / "Viu" / ".viu",
            inbox_dir=str(inbox),
            library_root=str(lib),
            unity_project=str(unity.parent.parent),
            unity_anim_staging=str(staging),
        ).ensure_dirs()
        report = route_inbox(cfg, copy_to_unity=True)
        assert any("yawn" in m.lower() or "Yawn" in m for m in report.animation_matches) or report.items
        assert not (inbox / "Yawn.fbx").exists()
        assert list(staging.glob("*.fbx"))
    finally:
        for k in ("VIU_INBOX_DIR", "VIU_LIBRARY_ROOT", "VIU_ANIM_STAGING", "VIU_UNITY_PROJECT"):
            os.environ.pop(k, None)
