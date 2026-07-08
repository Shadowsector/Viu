"""Тесты каталога предметов."""

from pathlib import Path

from viu.prop_catalog.models import PropEntry, suggest_can_lift, prop_id_for_path
from viu.prop_catalog.organizer import plan_downloads_sort
from viu.prop_catalog.scanner import scan_folder
from viu.prop_catalog.store import PropCatalogStore


def test_prop_id_stable():
    p = Path("/tmp/chair.fbx")
    assert prop_id_for_path(p) == prop_id_for_path(p)


def test_scan_folder_adds_entries(tmp_path):
    assets = tmp_path / "in"
    assets.mkdir()
    (assets / "chair.fbx").write_bytes(b"x")
    (assets / "readme.txt").write_text("nope", encoding="utf-8")
    store = PropCatalogStore(tmp_path / "catalog.json")
    n, seen = scan_folder(assets, store, recursive=False)
    assert n == 1
    assert seen == 0
    assert len(store.pending()) == 1
    e = store.pending()[0]
    assert "chair" in e.source_path


def test_affordance_export():
    e = PropEntry(
        id="abc",
        source_path="/x/chair.fbx",
        display_name="Стул",
        category="furniture",
        weight_kg=8.0,
        can_lift=True,
        interactions=["sit", "lean_on"],
        reviewed=True,
    )
    d = e.to_affordance_dict()
    assert "sit_surface" in str(d["sockets"])
    assert d["can_lift"] is True


def test_suggest_can_lift():
    assert suggest_can_lift(10.0, 35.0) is True
    assert suggest_can_lift(40.0, 35.0) is False


def test_downloads_plan(tmp_path):
    dl = tmp_path / "Downloads"
    dl.mkdir()
    lib = tmp_path / "Library"
    (dl / "tree.fbx").write_bytes(b"")
    (dl / "photo.png").write_bytes(b"")
    plans = plan_downloads_sort(dl, lib)
    assert len(plans) == 2
    assert any("Props/incoming/fbx" in str(p.dest) for p in plans)
