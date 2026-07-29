"""Очередь канон-рига biped."""

from __future__ import annotations

from pathlib import Path

from viu.config import Config
from viu.creature_catalog.biped_canon import (
    build_queue_items,
    format_biped_list,
    ingest_canon_fbx,
    list_bipeds,
    run_biped_canon_action,
    stage_biped_queue,
)
from viu.creature_catalog.models import CreatureEntry
from viu.creature_catalog.store import CreatureCatalogStore
from viu.creature_catalog.paths import creature_catalog_path
from viu.gui_direct import parse_direct_tool_command
from viu.tools import build_default_registry


def _cfg(tmp_path: Path) -> Config:
    return Config(root=tmp_path, data_dir=tmp_path / ".viu").ensure_dirs()


def _store_with_bipeds(tmp_path: Path) -> tuple[Config, CreatureCatalogStore]:
    cfg = _cfg(tmp_path)
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    fbx = inbox / "GoblinGirl.fbx"
    fbx.write_bytes(b"fbx")
    blend = inbox / "Wolf.blend"
    blend.write_bytes(b"blend")
    store = CreatureCatalogStore(creature_catalog_path(cfg))
    store.upsert(
        CreatureEntry(
            id="g1",
            path=str(fbx),
            name="GoblinGirl",
            slug="goblin_girl",
            locomotion="biped",
            size_class="small",
            genital_profile="vagina",
            morph_notes="tail tip",
            status="sized",
        )
    )
    store.upsert(
        CreatureEntry(
            id="w1",
            path=str(blend),
            name="Wolf",
            slug="wolf",
            locomotion="quadruped",
            size_class="quad_med",
            status="sized",
        )
    )
    store.upsert(
        CreatureEntry(
            id="b2",
            path=str(inbox / "missing.fbx"),
            name="OrcDude",
            slug="orc_dude",
            locomotion="biped",
            size_class="large",
            genital_profile="penis",
            status="sized",
        )
    )
    # create orc file
    (inbox / "missing.fbx").write_bytes(b"fbx")
    store.save()
    return cfg, store.load()


def test_list_bipeds_only(tmp_path):
    _cfg, store = _store_with_bipeds(tmp_path)
    bipeds = list_bipeds(store)
    assert {e.slug for e in bipeds} == {"goblin_girl", "orc_dude"}


def test_girls_only_filter(tmp_path):
    _cfg, store = _store_with_bipeds(tmp_path)
    girls = list_bipeds(store, girls_only=True)
    assert [e.slug for e in girls] == ["goblin_girl"]


def test_queue_and_ingest(tmp_path):
    cfg, store = _store_with_bipeds(tmp_path)
    staged, skipped, msg = stage_biped_queue(cfg, store)
    assert staged >= 2
    assert "BipedCanonQueue" in msg
    q = cfg.root  # library via anabarra — use path from msg
    from viu.creature_catalog.biped_canon import biped_canon_queue_dir

    qdir = biped_canon_queue_dir(cfg)
    assert (qdir / "README_ACCURIG.txt").is_file()
    assert (qdir / "queue_manifest.json").is_file()
    # simulate AccuRIG output
    canon = qdir / "goblin_girl_canon.fbx"
    canon.write_bytes(b"canon")
    n, imsg = ingest_canon_fbx(cfg, store)
    assert n == 1
    store2 = CreatureCatalogStore(creature_catalog_path(cfg)).load()
    g = next(e for e in store2.all() if e.slug == "goblin_girl")
    assert g.ready_fbx_path
    assert Path(g.ready_fbx_path).is_file()
    assert "canon_humanoid" in g.tags


def test_format_list_mentions_tail(tmp_path):
    _cfg, store = _store_with_bipeds(tmp_path)
    text = format_biped_list(build_queue_items(store))
    assert "goblin_girl" in text
    assert "хвост" in text.lower() or "tail" in text.lower()


def test_tool_guide_and_alias(tmp_path):
    reg = build_default_registry()
    assert "creature_biped_canon" in reg.names()
    parsed = parse_direct_tool_command("бипеды канон", reg)
    assert parsed == ("creature_biped_canon", {"action": "list"})
    ok, msg = run_biped_canon_action(_cfg(tmp_path), action="guide")
    assert ok
    assert "AccuRIG" in msg
