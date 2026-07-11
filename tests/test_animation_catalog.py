"""Тесты каталога анимаций и drop_router."""

from pathlib import Path

from viu.animation_catalog import (
    AnimationCatalogStore,
    animation_catalog_path,
    match_fbx_to_wish,
)
from viu.animation_catalog.models import DEFAULT_SCOPE, DEFAULT_WISHES, applies_to_shanya, normalize_scope
from viu.config import Config
from viu.drop_router import accept_single_animation, is_character_animation_fbx, route_inbox


def test_default_wishes_seeded():
    assert len(DEFAULT_WISHES) >= 20
    slugs = {w.slug for w in DEFAULT_WISHES}
    assert "climb_up" in slugs


def test_match_fast_run_to_run(tmp_path):
    store = AnimationCatalogStore(tmp_path / "cat.json").load()
    fbx = tmp_path / "Fast Run.fbx"
    fbx.write_bytes(b"x")
    wish, score, _ = match_fbx_to_wish(fbx, store)
    assert wish is not None
    assert wish.slug == "run"
    assert score >= 0.65


def test_accept_single_animation_opens_review(tmp_path, monkeypatch):
    inbox = tmp_path / "Inbox"
    inbox.mkdir()
    (inbox / "Fast Run.fbx").write_bytes(b"fbx")
    staging = tmp_path / "Animations"
    unity = tmp_path / "Unity" / "Anabarra"
    (unity / "Assets").mkdir(parents=True)
    lib = tmp_path / "Library"

    import os

    os.environ["VIU_INBOX_DIR"] = str(inbox)
    os.environ["VIU_LIBRARY_ROOT"] = str(lib)
    os.environ["VIU_ANIM_STAGING"] = str(staging)
    os.environ["VIU_UNITY_PROJECT"] = str(unity)
    os.environ["VIU_DATA_DIR"] = str(tmp_path / "Viu" / ".viu")
    try:
        cfg = Config(
            root=tmp_path / "Viu",
            data_dir=tmp_path / "Viu" / ".viu",
            inbox_dir=str(inbox),
            library_root=str(lib),
            unity_project=str(unity),
            unity_anim_staging=str(staging),
        ).ensure_dirs()
        report = accept_single_animation(cfg)
        assert report.ok
        assert report.open_animation_review
        assert not (inbox / "Fast Run.fbx").exists()
        store = AnimationCatalogStore(animation_catalog_path(cfg)).load()
        assert len(store.pending_reviews()) == 1
        pending = store.pending_reviews()[0]
        assert pending.suggested_slug == "run"
        assert pending.scope == DEFAULT_SCOPE
    finally:
        for k in ("VIU_INBOX_DIR", "VIU_LIBRARY_ROOT", "VIU_ANIM_STAGING", "VIU_UNITY_PROJECT", "VIU_DATA_DIR"):
            os.environ.pop(k, None)


def test_route_inbox_skips_animation(tmp_path, monkeypatch):
    inbox = tmp_path / "Inbox"
    inbox.mkdir()
    (inbox / "Fast Run.fbx").write_bytes(b"fbx")
    lib = tmp_path / "Library"
    import os

    os.environ["VIU_INBOX_DIR"] = str(inbox)
    os.environ["VIU_LIBRARY_ROOT"] = str(lib)
    os.environ["VIU_UNITY_PROJECT"] = str(tmp_path / "Unity" / "Anabarra")
    try:
        cfg = Config(
            root=tmp_path / "Viu",
            data_dir=tmp_path / "Viu" / ".viu",
            inbox_dir=str(inbox),
            library_root=str(lib),
        ).ensure_dirs()
        report = route_inbox(cfg)
        assert (inbox / "Fast Run.fbx").exists()
        assert any("пропуск" in it.kind or "animation" in it.kind for it in report.items)
    finally:
        os.environ.pop("VIU_INBOX_DIR", None)
        os.environ.pop("VIU_LIBRARY_ROOT", None)
        os.environ.pop("VIU_UNITY_PROJECT", None)


def test_scope_female_includes_shanya():
    assert normalize_scope("humanoid_female") == "female_humanoid"
    assert applies_to_shanya("female_humanoid")
    assert applies_to_shanya("shanya_only")
    assert not applies_to_shanya("humanoid_npc_female")
    assert not applies_to_shanya("humanoid_any")


def test_default_scope_is_female_humanoid():
    assert DEFAULT_SCOPE == "female_humanoid"
    assert is_character_animation_fbx(Path("Fast Run.fbx"))
    assert not is_character_animation_fbx(Path("Old_Stables.fbx"))
