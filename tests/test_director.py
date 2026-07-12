"""Тесты режиссёра «Следующий шаг»."""

from pathlib import Path

from viu.config import Config
from viu.director import format_banner, plan_next_step
from viu.prop_catalog.models import PropEntry, prop_id_for_mesh, prop_id_for_path
from viu.prop_catalog.paths import catalog_path
from viu.prop_catalog.store import PropCatalogStore
from viu.roadmap import RoadmapStore


def _config(tmp_path: Path, *, inbox: Path | None = None, unity: Path | None = None) -> Config:
    inbox = inbox or (tmp_path / "Inbox")
    inbox.mkdir(parents=True, exist_ok=True)
    cfg = Config(
        root=tmp_path,
        data_dir=tmp_path / ".viu",
        inbox_dir=str(inbox),
        unity_project=str(unity) if unity else "",
    )
    return cfg.ensure_dirs()


def test_director_inbox_has_priority(tmp_path):
    inbox = tmp_path / "Inbox"
    inbox.mkdir()
    (inbox / "hut.blend").write_bytes(b"fake")
    config = _config(tmp_path, inbox=inbox)

    plan = plan_next_step(config)

    assert plan.tool == "prepare_unity_asset"
    assert plan.tool_args.get("open_blender") == "1"
    assert "Inbox" in plan.message


def test_director_file_level_blend_needs_rescan(tmp_path):
    inbox = tmp_path / "Inbox"
    inbox.mkdir()
    blend = tmp_path / "hut.blend"
    blend.write_bytes(b"fake")
    config = _config(tmp_path, inbox=inbox)
    store = PropCatalogStore(catalog_path(config))
    store.upsert(
        PropEntry(
            id=prop_id_for_path(blend),
            source_path=str(blend),
            display_name="hut",
            reviewed=False,
        )
    )
    store.save()

    plan = plan_next_step(config)

    assert plan.tool == "__prop_catalog__"
    assert "объект" in plan.message.lower() or "Building" in plan.message or "разложить" in plan.message.lower()


def test_director_mesh_level_opens_catalog(tmp_path):
    inbox = tmp_path / "Inbox"
    inbox.mkdir()
    blend = tmp_path / "hut.blend"
    blend.write_bytes(b"fake")
    config = _config(tmp_path, inbox=inbox)
    store = PropCatalogStore(catalog_path(config))
    store.upsert(
        PropEntry(
            id=prop_id_for_mesh(blend, "simple_chair"),
            source_path=str(blend),
            display_name="simple_chair",
            mesh_name="simple_chair",
            collection="Props",
            reviewed=False,
        )
    )
    store.save()

    plan = plan_next_step(config)

    assert plan.tool == "__prop_catalog__"
    assert "размет" in plan.message.lower()


def test_director_overlay_build_when_focus(tmp_path):
    inbox = tmp_path / "Inbox"
    inbox.mkdir()
    unity = tmp_path / "unity"
    (unity / "Assets").mkdir(parents=True)
    config = _config(tmp_path, inbox=inbox, unity=unity)
    RoadmapStore(config.data_dir / "roadmap.json").save()
    from viu.animation_catalog import AnimationCatalogStore, animation_catalog_path

    ac = AnimationCatalogStore(animation_catalog_path(config))
    for p in ac.pending_reviews():
        p.reviewed = True
        ac.upsert_pending(p)
    ac.save()

    plan = plan_next_step(config)

    assert plan.tool == "unity_overlay_validate"
    assert "оверлей" in plan.message.lower() or "overlay" in plan.message.lower() or "validate" in plan.message.lower()


def test_director_idle_when_nothing_pending(tmp_path):
    inbox = tmp_path / "Inbox"
    inbox.mkdir()
    config = _config(tmp_path, inbox=inbox)
    store = RoadmapStore(config.data_dir / "roadmap.json")
    for m in store.roadmap.milestones:
        m.status = "done"
    store.save()
    from viu.animation_catalog import AnimationCatalogStore, animation_catalog_path

    ac = AnimationCatalogStore(animation_catalog_path(config))
    for p in ac.pending_reviews():
        p.reviewed = True
        ac.upsert_pending(p)
    ac.save()

    plan = plan_next_step(config)

    assert plan.idle
    assert plan.tool == ""


def test_director_skips_inbox_when_already_prepared(tmp_path):
    inbox = tmp_path / "Inbox"
    inbox.mkdir()
    blend = inbox / "hut.blend"
    blend.write_bytes(b"fake")
    lib = tmp_path / "Library"
    prepared = lib / "Processed" / "hut" / "hut_prepared.blend"
    prepared.parent.mkdir(parents=True)
    prepared.write_bytes(b"prepared")
    import os
    import time

    os.environ["VIU_INBOX_DIR"] = str(inbox)
    os.environ["VIU_LIBRARY_ROOT"] = str(lib)
    try:
        now = time.time()
        os.utime(blend, (now - 10, now - 10))
        os.utime(prepared, (now, now))
        config = Config(
            root=tmp_path,
            data_dir=tmp_path / ".viu",
            inbox_dir=str(inbox),
            library_root=str(lib),
        ).ensure_dirs()
        plan = plan_next_step(config)
        assert plan.tool != "prepare_unity_asset"
    finally:
        os.environ.pop("VIU_INBOX_DIR", None)
        os.environ.pop("VIU_LIBRARY_ROOT", None)


def test_director_prepared_asset_suggests_export(tmp_path):
    inbox = tmp_path / "Inbox"
    inbox.mkdir()
    lib = tmp_path / "Library"
    prepared = lib / "Processed" / "Old Stables" / "Old Stables_prepared.blend"
    prepared.parent.mkdir(parents=True)
    prepared.write_bytes(b"prepared")
    import os

    os.environ["VIU_INBOX_DIR"] = str(inbox)
    os.environ["VIU_LIBRARY_ROOT"] = str(lib)
    try:
        config = Config(
            root=tmp_path,
            data_dir=tmp_path / ".viu",
            inbox_dir=str(inbox),
            library_root=str(lib),
        ).ensure_dirs()
        plan = plan_next_step(config)
        assert plan.tool == "export_unity_asset"
        assert "Old Stables" in plan.message or "экспорт" in plan.message.lower()
    finally:
        os.environ.pop("VIU_INBOX_DIR", None)
        os.environ.pop("VIU_LIBRARY_ROOT", None)


def test_format_banner_includes_human_after(tmp_path):
    config = _config(tmp_path)
    plan = plan_next_step(config)
    banner = format_banner(plan)
    assert banner.startswith("▶")
    if plan.human_after:
        assert "→" in banner
