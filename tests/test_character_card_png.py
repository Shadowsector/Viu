"""Тесты разбора PNG character cards (stdlib only)."""

from __future__ import annotations

import json
import struct
import zlib
from pathlib import Path

from viu.character_card_png import (
    dump_json_payloads,
    format_probe_report,
    probe_directory,
    probe_png,
)
from viu.tools.character_card_tool import CharacterCardProbeTool
from viu.tools.base import AgentContext
from viu.config import Config


def _crc(chunk_type: bytes, data: bytes) -> bytes:
    import binascii

    return struct.pack(">I", binascii.crc32(chunk_type + data) & 0xFFFFFFFF)


def _chunk(chunk_type: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + chunk_type + data + _crc(chunk_type, data)


def make_png_with_text(
    path: Path,
    *,
    keyword: str,
    text: str,
    trailing: bytes = b"",
    compress_text: bool = False,
) -> None:
    magic = b"\x89PNG\r\n\x1a\n"
    # IHDR 1x1 RGBA
    ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 6, 0, 0, 0)
    # minimal IDAT: one filtered scanline for RGBA
    raw = b"\x00" + b"\x00\x00\x00\xff"
    idat = zlib.compress(raw)
    if compress_text:
        zt = keyword.encode("latin-1") + b"\x00\x00" + zlib.compress(text.encode("utf-8"))
        text_chunk = _chunk(b"zTXt", zt)
    else:
        te = keyword.encode("latin-1") + b"\x00" + text.encode("utf-8")
        text_chunk = _chunk(b"tEXt", te)
    blob = (
        magic
        + _chunk(b"IHDR", ihdr)
        + text_chunk
        + _chunk(b"IDAT", idat)
        + _chunk(b"IEND", b"")
        + trailing
    )
    path.write_bytes(blob)


def test_probe_text_json(tmp_path: Path) -> None:
    payload = {
        "faceSliders": {"nose": 0.42, "jaw": -0.1},
        "hairId": "hair_07",
        "eyes": {"color": "#884422"},
    }
    png = tmp_path / "hero.png"
    make_png_with_text(png, keyword="character", text=json.dumps(payload))
    r = probe_png(png)
    assert r.ok
    assert r.width == 1 and r.height == 1
    assert any(p.kind == "json" for p in r.payloads)
    data = next(p.data for p in r.payloads if p.kind == "json")
    assert data["hairId"] == "hair_07"
    assert "faceSliders.nose" in r.summary_keys


def test_probe_base64_chara(tmp_path: Path) -> None:
    import base64

    inner = {"name": "Shanya", "hair": 3, "sliders": [0.1, 0.2, 0.9]}
    b64 = base64.b64encode(json.dumps(inner).encode("utf-8")).decode("ascii")
    png = tmp_path / "card.png"
    make_png_with_text(png, keyword="chara", text=b64)
    r = probe_png(png)
    assert r.ok
    kinds = {p.kind for p in r.payloads}
    assert "base64_json" in kinds
    data = next(p.data for p in r.payloads if p.kind == "base64_json")
    assert data["name"] == "Shanya"


def test_probe_after_iend(tmp_path: Path) -> None:
    payload = {"hairId": 12, "face": {"cheek": 0.5}}
    png = tmp_path / "tail.png"
    make_png_with_text(
        png,
        keyword="Title",
        text="portrait",
        trailing=json.dumps(payload).encode("utf-8"),
    )
    r = probe_png(png)
    assert r.ok
    assert r.after_iend_bytes > 0
    json_payloads = [p for p in r.payloads if p.kind == "json"]
    assert any(p.data.get("hairId") == 12 for p in json_payloads if isinstance(p.data, dict))


def test_probe_ztxt(tmp_path: Path) -> None:
    payload = {"sliders": {"brow": 0.33}}
    png = tmp_path / "z.png"
    make_png_with_text(
        png,
        keyword="viu_card",
        text=json.dumps(payload),
        compress_text=True,
    )
    r = probe_png(png)
    assert r.ok
    assert any(tc["type"] == "zTXt" for tc in r.text_chunks)
    assert any(p.kind == "json" for p in r.payloads)


def test_probe_directory_and_dump(tmp_path: Path) -> None:
    a = {"a": 1}
    b = {"b": 2}
    make_png_with_text(tmp_path / "a.png", keyword="c", text=json.dumps(a))
    make_png_with_text(tmp_path / "b.png", keyword="c", text=json.dumps(b))
    results = probe_directory(tmp_path)
    assert len(results) == 2
    out = tmp_path / "out"
    written = dump_json_payloads(results, out)
    assert len(written) == 2
    report = format_probe_report(results)
    assert "PNG character-card probe" in report
    assert "a.png" in report


def test_tool_runs(tmp_path: Path) -> None:
    from viu.memory import MemoryStore
    from viu.planning import Planner
    from viu.tools import build_default_registry

    payload = {"hairId": "x", "faceSliders": {"x": 1}}
    make_png_with_text(tmp_path / "t.png", keyword="card", text=json.dumps(payload))
    cfg = Config(root=tmp_path, data_dir=tmp_path / ".viu").ensure_dirs()
    ctx = AgentContext(
        config=cfg,
        memory=MemoryStore(cfg.data_dir / "memory.json"),
        planner=Planner(cfg.data_dir / "plan.json"),
        registry=build_default_registry(),
    )
    tool = CharacterCardProbeTool()
    res = tool.run({"path": str(tmp_path), "limit": 10}, ctx)
    assert res.ok
    assert "summary_json" in res.content
    assert "hairId" in res.content
    dumped = list((tmp_path / ".viu" / "character_cards_extract").glob("*.json"))
    assert dumped
