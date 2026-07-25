"""Тесты архива Desktop Mascot + provenance (пилот Shanya/Erisa)."""

from pathlib import Path

import pytest

from viu.asset_archive.inventory import (
    inventory_archive_top,
    inventory_pack,
    stage_pack_to_inbox,
)
from viu.asset_archive.layout import (
    MASCOT_TOP_CATEGORIES,
    classify_mascot_category,
    expected_mascot_layout,
    inbox_subdir_for_category,
    missing_mascot_categories,
)
from viu.asset_archive.provenance import (
    PILOT_SHANYA_ERISA,
    ProvenanceEntry,
    license_allows_derivatives,
    license_ok_for_anabarra_build,
    normalize_license,
    seed_pilot_entries,
)
from viu.asset_archive.store import ProvenanceStore, provenance_path
from viu.config import Config
from viu.tools import build_default_registry


def _cfg(tmp_path: Path, monkeypatch, mascot: Path | None = None) -> Config:
    monkeypatch.delenv("VIU_INBOX_DIR", raising=False)
    monkeypatch.delenv("VIU_MASCOT_DIR", raising=False)
    viu = tmp_path / "Viu"
    ana = tmp_path / "Anabarra"
    viu.mkdir()
    ana.mkdir()
    monkeypatch.setenv("VIU_ANABARRA_ROOT", str(ana))
    if mascot is not None:
        monkeypatch.setenv("VIU_MASCOT_DIR", str(mascot))
    return Config(root=viu, data_dir=viu / ".viu")


def test_mascot_has_eight_canonical_categories():
    assert len(MASCOT_TOP_CATEGORIES) == 8
    assert "Women" in MASCOT_TOP_CATEGORIES
    assert "NS Animations" in MASCOT_TOP_CATEGORIES


def test_classify_mascot_category_aliases():
    assert classify_mascot_category("Women") == "Women"
    assert classify_mascot_category("nsfw animations") == "NS Animations"
    assert classify_mascot_category("clothing") == "Clothes"
    assert classify_mascot_category("random_junk") is None


def test_inbox_routing_from_mascot_category():
    assert inbox_subdir_for_category("Women") == "creatures"
    assert inbox_subdir_for_category("Animations") == "animations"
    assert inbox_subdir_for_category("Props") == ""
    assert inbox_subdir_for_category("NoSuch") is None


def test_inventory_top_level_no_deep_scan(tmp_path, monkeypatch):
    mascot = tmp_path / "Desktop Mascot"
    deep = mascot / "Women" / "nested" / "deep"
    deep.mkdir(parents=True)
    (deep / "secret.blend").write_bytes(b"x")
    (mascot / "Clothes").mkdir()
    (mascot / "rig_tools.zip").write_bytes(b"z")
    cfg = _cfg(tmp_path, monkeypatch, mascot)
    inv = inventory_archive_top(cfg)
    assert inv["auto_scan"] is False
    assert inv["exists"] is True
    assert "Women" in inv["present_categories"]
    assert "Clothes" in inv["present_categories"]
    assert "Animations" in inv["missing_categories"]
    # Не должен перечислять deep secret.blend
    blob = str(inv)
    assert "secret.blend" not in blob


def test_missing_categories_when_archive_absent(tmp_path, monkeypatch):
    missing = tmp_path / "no_mascot"
    cfg = _cfg(tmp_path, monkeypatch, missing)
    assert missing_mascot_categories(missing) == list(MASCOT_TOP_CATEGORIES)
    inv = inventory_archive_top(cfg)
    assert inv["exists"] is False


def test_expected_layout_paths(tmp_path):
    root = tmp_path / "Mascot"
    layout = expected_mascot_layout(root)
    assert layout["Women"] == root / "Women"
    assert set(layout) == set(MASCOT_TOP_CATEGORIES)


def test_inventory_one_pack_counts_assets(tmp_path):
    pack = tmp_path / "ErisaBody"
    (pack / "textures").mkdir(parents=True)
    (pack / "body.blend").write_bytes(b"b")
    (pack / "textures" / "skin.png").write_bytes(b"p")
    (pack / "readme.txt").write_text("hi", encoding="utf-8")
    inv = inventory_pack(pack)
    assert inv["exists"]
    assert inv["asset_count"] == 2
    assert inv["by_suffix"][".blend"] == 1
    assert inv["by_suffix"][".png"] == 1


def test_stage_pack_women_to_creatures_inbox(tmp_path, monkeypatch):
    mascot = tmp_path / "Desktop Mascot" / "Women" / "Erisa"
    mascot.mkdir(parents=True)
    (mascot / "body.blend").write_bytes(b"mesh")
    cfg = _cfg(tmp_path, monkeypatch, tmp_path / "Desktop Mascot")
    ok, msg, dest = stage_pack_to_inbox(cfg, mascot, category="Women")
    assert ok, msg
    assert dest.name == "Erisa"
    assert "creatures" in str(dest)
    assert (dest / "body.blend").read_bytes() == b"mesh"
    # Оригинал на месте
    assert (mascot / "body.blend").is_file()


def test_normalize_and_nd_license():
    assert normalize_license("CC BY-ND 4.0") == "cc-by-nd-4.0"
    assert normalize_license("CC0") == "cc0"
    assert normalize_license("mine") == "mine"
    assert license_allows_derivatives("CC BY-ND 4.0") is False
    assert license_allows_derivatives("CC BY 4.0") is True
    assert license_allows_derivatives("CC0") is True


def test_license_ok_personal_nd_vs_public():
    ok_p, msg_p = license_ok_for_anabarra_build(
        "CC BY-ND 4.0", personal_only=True, will_modify=True
    )
    assert ok_p is True
    assert "ND" in msg_p
    ok_pub, msg_pub = license_ok_for_anabarra_build(
        "CC BY-ND 4.0", personal_only=False, will_modify=True
    )
    assert ok_pub is False
    assert "ND" in msg_pub


def test_pilot_shanya_erisa_card():
    p = PILOT_SHANYA_ERISA
    assert p.id == "shanya_erisa_redeyes"
    assert p.source == "smutbase"
    assert "ND" in p.license.upper() or "nd" in normalize_license(p.license)
    assert "smutba.se" in p.url
    assert p.mascot_category == "Women"
    assert p.local_path.lower().endswith("women") or "Desktop Mascot" in p.local_path
    ok, _ = license_ok_for_anabarra_build(p.license, personal_only=True, will_modify=True)
    assert ok
    assert len(seed_pilot_entries()) >= 1


def test_provenance_store_persists(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path, monkeypatch)
    path = provenance_path(cfg)
    store = ProvenanceStore(path)
    n = store.ensure_pilots()
    assert n >= 1
    assert path.is_file()
    again = ProvenanceStore(path)
    assert again.get("shanya_erisa_redeyes") is not None
    assert "Erisa" in again.render_summary() or "erisa" in again.render_summary().lower()


def test_provenance_entry_roundtrip():
    raw = PILOT_SHANYA_ERISA.to_dict()
    back = ProvenanceEntry.from_dict(raw)
    assert back.id == PILOT_SHANYA_ERISA.id
    assert back.credits == PILOT_SHANYA_ERISA.credits


def test_tools_registered():
    reg = build_default_registry()
    names = set(reg.names())
    assert "asset_archive_inventory" in names
    assert "asset_archive_stage" in names
    assert "asset_provenance" in names


def test_asset_provenance_tool_ensure(tmp_path, monkeypatch):
    from viu.memory import MemoryStore
    from viu.planning import Planner
    from viu.tools.asset_archive_tool import AssetProvenanceTool
    from viu.tools.base import AgentContext

    cfg = _cfg(tmp_path, monkeypatch)
    cfg.ensure_dirs()
    reg = build_default_registry()
    ctx = AgentContext(
        config=cfg,
        memory=MemoryStore(cfg.data_dir / "memory.json"),
        planner=Planner(cfg.data_dir / "plan.json"),
        registry=reg,
    )
    result = AssetProvenanceTool().run({"action": "ensure_pilots"}, ctx)
    assert result.ok
    assert "shanya_erisa" in result.content.lower() or "Erisa" in result.content
