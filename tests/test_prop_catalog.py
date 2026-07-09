"""Тесты каталога предметов."""

from pathlib import Path

from viu.prop_catalog.models import (
    PropEntry,
    prop_id_for_mesh,
    prop_id_for_path,
    suggest_can_lift,
    suggest_category_for_role,
    suggest_role,
)
from viu.prop_catalog.organizer import plan_inbox_sort
from viu.prop_catalog.scanner import scan_blend_file, scan_folder
from viu.prop_catalog.store import PropCatalogStore


def test_prop_id_stable():
    p = Path("/tmp/chair.fbx")
    assert prop_id_for_path(p) == prop_id_for_path(p)


def test_prop_id_mesh_differs_from_file():
    p = Path("/tmp/hut.blend")
    assert prop_id_for_mesh(p, "Interactive_Chair") != prop_id_for_path(p)


def test_suggest_role_from_name():
    assert suggest_role("Shell_WallFront") == "shell"
    assert suggest_role("Interactive_Bed") == "interactive"
    assert suggest_role("Decor_Lamp") == "decor"
    assert suggest_category_for_role("shell") == "building"


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


def test_scan_blend_with_collections(tmp_path):
    blend = tmp_path / "hut.blend"
    blend.write_bytes(b"fake")
    store = PropCatalogStore(tmp_path / "catalog.json")

    def fake_reader(path: Path, _exe: str):
        return [
            {"name": "simple_chair", "collection": "Props"},
            {"name": "poor_stables_door", "collection": "Building"},
        ]

    n, _ = scan_blend_file(blend, store, mesh_reader=fake_reader)
    assert n == 2
    chair = next(e for e in store.pending() if e.mesh_name == "simple_chair")
    assert chair.collection == "Props"
    assert chair.role == "interactive"
    assert "Props" in chair.list_label()


def test_scan_blend_creates_per_mesh(tmp_path):
    blend = tmp_path / "hut.blend"
    blend.write_bytes(b"fake")
    store = PropCatalogStore(tmp_path / "catalog.json")

    def fake_reader(path: Path, _exe: str):
        return ["Shell_Floor", "Interactive_Bed"]

    n, seen = scan_blend_file(blend, store, mesh_reader=fake_reader)
    assert n == 2
    assert seen == 0
    pending = store.pending()
    assert {e.mesh_name for e in pending} == {"Shell_Floor", "Interactive_Bed"}
    bed = next(e for e in pending if e.mesh_name == "Interactive_Bed")
    assert bed.role == "interactive"
    assert bed.category == "furniture"


def test_scan_blend_replaces_stale_file_entry(tmp_path):
    blend = tmp_path / "hut.blend"
    blend.write_bytes(b"fake")
    store = PropCatalogStore(tmp_path / "catalog.json")
    store.upsert(
        PropEntry(
            id=prop_id_for_path(blend),
            source_path=str(blend),
            display_name="hut",
            reviewed=False,
        )
    )

    def fake_reader(path: Path, _exe: str):
        return ["Shell_Wall"]

    scan_blend_file(blend, store, mesh_reader=fake_reader)
    assert store.get(prop_id_for_path(blend)) is None
    assert store.get(prop_id_for_mesh(blend, "Shell_Wall")) is not None


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
        mesh_name="Interactive_Chair",
        role="interactive",
    )
    d = e.to_affordance_dict()
    assert "sit_surface" in str(d["sockets"])
    assert d["can_lift"] is True
    assert d["mesh_name"] == "Interactive_Chair"
    assert d["role"] == "interactive"


def test_suggest_can_lift():
    assert suggest_can_lift(10.0, 35.0) is True
    assert suggest_can_lift(40.0, 35.0) is False


def test_inbox_plan_blend_with_textures(tmp_path):
    inbox = tmp_path / "Inbox"
    inbox.mkdir()
    lib = tmp_path / "Library"
    (inbox / "Old Stables.blend").write_bytes(b"")
    tex = inbox / "textures"
    tex.mkdir()
    (tex / "wood.png").write_bytes(b"")
    plans = plan_inbox_sort(inbox, lib)
    assert any("Blender/Old Stables/Old Stables.blend" in str(p.dest).replace("\\", "/") for p in plans)
    assert any(p.dest.name == "textures" and "Old Stables" in str(p.dest) for p in plans)


def test_inbox_plan_files_and_folders(tmp_path):
    inbox = tmp_path / "Inbox"
    inbox.mkdir()
    lib = tmp_path / "Library"
    (inbox / "tree.fbx").write_bytes(b"")
    (inbox / "photo.png").write_bytes(b"")
    pack = inbox / "HutPack"
    pack.mkdir()
    (pack / "hut.blend").write_bytes(b"")
    (pack / "Textures").mkdir()
    plans = plan_inbox_sort(inbox, lib)
    assert len(plans) == 3
    assert any(p.kind == "folder" and p.src.name == "HutPack" for p in plans)
    assert any("Props/fbx" in str(p.dest) for p in plans)
    assert any("Blender/HutPack" in str(p.dest) for p in plans)


def test_sidecar_notes_in_scan(tmp_path):
    pack = tmp_path / "pack"
    pack.mkdir()
    blend = pack / "hut.blend"
    blend.write_bytes(b"x")
    (pack / "notes.txt").write_text("домик шани", encoding="utf-8")
    store = PropCatalogStore(tmp_path / "catalog.json")

    def fake_reader(path: Path, _exe: str):
        return ["Shell_Floor"]

    n, _ = scan_blend_file(blend, store, mesh_reader=fake_reader)
    assert n == 1
    assert "домик" in store.pending()[0].notes


def test_apply_auto_review_building_collection():
    from viu.prop_catalog.models import apply_auto_review

    blend = Path("/tmp/hut.blend")
    entry = PropEntry(
        id=prop_id_for_mesh(blend, "poor_stables_door"),
        source_path=str(blend),
        display_name="door",
        mesh_name="poor_stables_door",
        collection="Building",
    )
    out = apply_auto_review(entry)
    assert out.reviewed
    assert out.role == "shell"


def test_apply_auto_review_great_brome_is_shell_climbable():
    from viu.prop_catalog.models import apply_auto_review

    blend = Path("/tmp/hut.blend")
    entry = PropEntry(
        id=prop_id_for_mesh(blend, "Great Brome.003"),
        source_path=str(blend),
        display_name="Great Brome.003",
        mesh_name="Great Brome.003",
        collection="Landscape",
    )
    out = apply_auto_review(entry)
    assert out.reviewed
    assert out.role == "shell"
    assert out.can_climb is True
    assert "stand_on" in out.interactions


def test_apply_auto_review_fog_is_atmosphere():
    from viu.prop_catalog.models import apply_auto_review

    blend = Path("/tmp/hut.blend")
    entry = PropEntry(
        id=prop_id_for_mesh(blend, "Fog"),
        source_path=str(blend),
        display_name="Fog",
        mesh_name="Fog",
        collection="Landscape",
    )
    out = apply_auto_review(entry)
    assert out.role == "atmosphere"
    assert out.reviewed


def test_normalize_interactions_legacy():
    from viu.prop_catalog.interactions import normalize_interactions

    assert normalize_interactions(["push", "pull", "open", "close"]) == ["move", "open"]


def test_apply_auto_review_props_stays_pending():
    from viu.prop_catalog.models import apply_auto_review

    blend = Path("/tmp/hut.blend")
    entry = PropEntry(
        id=prop_id_for_mesh(blend, "simple_chair"),
        source_path=str(blend),
        display_name="chair",
        mesh_name="simple_chair",
        collection="Props",
    )
    out = apply_auto_review(entry)
    assert not out.reviewed
    assert out.role == "interactive"
