"""Матчинг ассетов под AnabarraAppearance JSON."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

from viu.ais_asset_match import (
    ensure_ais_inbox_layout,
    inbox_ais_assets_dir,
    inbox_ais_cards_dir,
    match_appearance_to_assets,
    needs_from_appearance,
    score_asset,
)
from viu.config import Config


def test_needs_and_score(tmp_path: Path) -> None:
    app = {
        "character_name": "Mira Fox",
        "hair_ids": [17, 3],
        "kkex_mods": ["KKABMPlugin.ABMData"],
        "face_detail": {"pupilId": 42},
        "raw_parameter": {},
    }
    need = needs_from_appearance(app)
    assert 17 in need.hair_ids
    assert "mira" in need.name_tokens or "fox" in need.name_tokens

    assets = tmp_path / "assets"
    assets.mkdir()
    hair = assets / "hair_017_long.fbx"
    hair.write_bytes(b"x")
    noise = assets / "rock_prop.fbx"
    noise.write_bytes(b"y")
    pack = assets / "Mira_pack.zip"
    with zipfile.ZipFile(pack, "w") as zf:
        zf.writestr("hair/ha_17.unity3d", b"z")

    hit = score_asset(hair, need)
    assert hit is not None and hit.score >= 8
    assert hit.kind == "hair"

    assert score_asset(noise, need) is None or score_asset(noise, need).score < 3

    card = tmp_path / "hero__anabarra.json"
    card.write_text(json.dumps(app), encoding="utf-8")
    report = match_appearance_to_assets(card, assets)
    assert report.scanned_files >= 2
    assert any("hair" in h.path.lower() or h.kind == "hair" for h in report.hits)
    assert report.hits[0].score >= report.hits[-1].score


def test_setup_dirs(tmp_path: Path) -> None:
    cfg = Config(root=tmp_path / "Viu", data_dir=tmp_path / "Viu" / ".viu")
    cfg.ensure_dirs()
    # force inbox under tmp
    import os

    os.environ["VIU_INBOX_DIR"] = str(tmp_path / "Inbox")
    cfg = Config(root=tmp_path / "Viu", data_dir=tmp_path / "Viu" / ".viu", inbox_dir=str(tmp_path / "Inbox"))
    paths = ensure_ais_inbox_layout(cfg)
    assert inbox_ais_cards_dir(cfg).is_dir()
    assert inbox_ais_assets_dir(cfg).is_dir()
    assert (inbox_ais_assets_dir(cfg) / "README.txt").is_file()
    assert len(paths) == 3


def test_match_tool(tmp_path: Path) -> None:
    from viu.memory import MemoryStore
    from viu.planning import Planner
    from viu.tools import AgentContext, build_default_registry
    from viu.tools.character_card_tool import CharacterCardMatchTool, CharacterCardSetupTool

    inbox = tmp_path / "Inbox"
    cfg = Config(
        root=tmp_path / "Viu",
        data_dir=tmp_path / "Viu" / ".viu",
        inbox_dir=str(inbox),
    ).ensure_dirs()
    ctx = AgentContext(
        config=cfg,
        memory=MemoryStore(cfg.data_dir / "memory.json"),
        planner=Planner(cfg.data_dir / "plan.json"),
        registry=build_default_registry(),
    )
    setup = CharacterCardSetupTool().run({"open": "0"}, ctx)
    assert setup.ok

    assets = inbox_ais_assets_dir(cfg)
    (assets / "hair_03.fbx").write_bytes(b"1")
    extract = cfg.data_dir / "character_cards_extract"
    extract.mkdir(parents=True, exist_ok=True)
    card = extract / "AI_test__anabarra.json"
    card.write_text(
        json.dumps({"character_name": "Test", "hair_ids": [3], "face_shape_values": [0.1]}),
        encoding="utf-8",
    )
    res = CharacterCardMatchTool().run({"json": str(card)}, ctx)
    assert res.ok
    assert "hair_03" in res.content or "hits=" in res.content
