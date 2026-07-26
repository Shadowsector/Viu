"""Тесты AIS_Chara десериализатора."""

from __future__ import annotations

import io
import struct
import zlib
from pathlib import Path

import msgpack
import pytest

from viu.ais_chara import (
    load_ais_chara,
    looks_like_ais_chara,
    map_to_anabarra,
    png_iend_offset,
)


def _crc(chunk_type: bytes, data: bytes) -> bytes:
    import binascii

    return struct.pack(">I", binascii.crc32(chunk_type + data) & 0xFFFFFFFF)


def _chunk(chunk_type: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + chunk_type + data + _crc(chunk_type, data)


def _mini_png() -> bytes:
    magic = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 6, 0, 0, 0)
    raw = b"\x00" + b"\x00\x00\x00\xff"
    idat = zlib.compress(raw)
    return magic + _chunk(b"IHDR", ihdr) + _chunk(b"IDAT", idat) + _chunk(b"IEND", b"")


def _pack_len_prefixed_msg(obj, length_fmt: str = "i") -> bytes:
    blob = msgpack.packb(obj, use_bin_type=True)
    return struct.pack(length_fmt, len(blob)) + blob


def make_ais_card(path: Path) -> None:
    png = _mini_png()
    header = "【AIS_Chara】".encode("utf-8")
    version = b"1.0.0"
    face_thumb = b"thumb"

    face = {"shapeValueFace": [0.1, 0.2, 0.3, 0.4], "pupil": 2}
    body = {"shapeValueBody": [0.5, 0.6]}
    hair = {"parts": [{"id": 17, "color": 1}, {"id": 3, "color": 2}]}
    custom_blob = b"".join(
        [
            _pack_len_prefixed_msg(face),
            _pack_len_prefixed_msg(body),
            _pack_len_prefixed_msg(hair),
        ]
    )
    parameter = {"fullname": "TestCat", "personality": 1}
    param_blob = msgpack.packb(parameter, use_bin_type=True)

    # blocks in payload order: Custom then Parameter
    payload = custom_blob + param_blob
    lst = {
        "lstInfo": [
            {"name": "Custom", "version": "0.0.0", "pos": 0, "size": len(custom_blob)},
            {
                "name": "Parameter",
                "version": "0.0.1",
                "pos": len(custom_blob),
                "size": len(param_blob),
            },
        ]
    }
    lst_blob = msgpack.packb(lst, use_bin_type=True)

    tail = b"".join(
        [
            struct.pack("i", 100),
            struct.pack("b", len(header)),
            header,
            struct.pack("b", len(version)),
            version,
            struct.pack("i", len(face_thumb)),
            face_thumb,
            struct.pack("i", len(lst_blob)),
            lst_blob,
            struct.pack("q", len(payload)),
            payload,
        ]
    )
    path.write_bytes(png + tail)


def test_looks_like_ais_and_load(tmp_path: Path) -> None:
    png = tmp_path / "cat.png"
    make_ais_card(png)
    data = png.read_bytes()
    assert looks_like_ais_chara(data)
    assert png_iend_offset(data) < len(data)

    card = load_ais_chara(png, full=True)
    assert card.error == ""
    assert card.parse_level == "full"
    assert "AIS_Chara" in card.header
    assert card.version == "1.0.0"
    assert [b.name for b in card.blocks] == ["Custom", "Parameter"]
    assert card.custom["face"]["shapeValueFace"][0] == pytest.approx(0.1)
    assert card.parameter["fullname"] == "TestCat"

    app = map_to_anabarra(card)
    assert app.character_name == "TestCat"
    assert app.face_shape_values == [0.1, 0.2, 0.3, 0.4]
    assert app.body_shape_values == [0.5, 0.6]
    assert app.hair_ids == [17, 3]


def test_tool_deserialize(tmp_path: Path) -> None:
    from viu.config import Config
    from viu.memory import MemoryStore
    from viu.planning import Planner
    from viu.tools import AgentContext, build_default_registry
    from viu.tools.character_card_tool import CharacterCardDeserializeTool

    png = tmp_path / "a.png"
    make_ais_card(png)
    cfg = Config(root=tmp_path, data_dir=tmp_path / ".viu").ensure_dirs()
    ctx = AgentContext(
        config=cfg,
        memory=MemoryStore(cfg.data_dir / "memory.json"),
        planner=Planner(cfg.data_dir / "plan.json"),
        registry=build_default_registry(),
    )
    res = CharacterCardDeserializeTool().run({"path": str(png)}, ctx)
    assert res.ok
    assert "face_shape_values" in res.content
    assert "TestCat" in res.content
    assert list((tmp_path / ".viu" / "character_cards_extract").glob("*anabarra.json"))
