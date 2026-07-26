"""Десериализация карточек Illusion/AI ★ Girl: PNG + MessagePack после IEND.

Формат (подтверждено логом Вью по U:\\TempUnityCard):

1. Обычный PNG (превью 252×352)
2. После IEND:
   - ``product_no`` (int32)
   - header ``【AIS_Chara】`` (length-prefixed byte)
   - version ``1.0.0``
   - face thumbnail (length-prefixed int32)
   - lstInfo (MessagePack) + payload блоков
3. Блоки: Custom (face/body/hair), Coordinate, Parameter, Status, KKEx, …

Для полного разбора нужен пакет ``msgpack`` (опциональная зависимость).
Без него читаем только заголовок и список блоков.
"""

from __future__ import annotations

import io
import json
import struct
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, BinaryIO, Optional

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
AIS_MARKER = "AIS_Chara"
KNOWN_HEADERS = (
    "【AIS_Chara】",
    "【KoiKatuChara】",
    "【KoiKatuCharaS】",
    "【EroMakeLove】",
    "【HoneyComeChara】",
)


@dataclass
class AisBlockInfo:
    name: str
    version: str
    pos: int
    size: int


@dataclass
class AnabarraAppearance:
    """Упрощённая структура под игру Анабарра (из Custom + Parameter)."""

    source_path: str = ""
    card_header: str = ""
    card_version: str = ""
    product_no: int = 0
    character_name: str = ""
    face_shape_values: list[float] = field(default_factory=list)
    body_shape_values: list[float] = field(default_factory=list)
    hair_ids: list[int] = field(default_factory=list)
    hair_parts: list[dict[str, Any]] = field(default_factory=list)
    face_detail: dict[str, Any] = field(default_factory=dict)
    raw_parameter: dict[str, Any] = field(default_factory=dict)
    blocks: list[str] = field(default_factory=list)
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class AisCharaCard:
    path: str = ""
    product_no: int = 0
    header: str = ""
    version: str = ""
    face_image_size: int = 0
    png_size: int = 0
    blocks: list[AisBlockInfo] = field(default_factory=list)
    custom: dict[str, Any] = field(default_factory=dict)
    parameter: dict[str, Any] = field(default_factory=dict)
    status: dict[str, Any] = field(default_factory=dict)
    coordinate_summary: Any = None
    kkex_keys: list[str] = field(default_factory=list)
    parse_level: str = "header"  # header | blocks | full
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "product_no": self.product_no,
            "header": self.header,
            "version": self.version,
            "face_image_size": self.face_image_size,
            "png_size": self.png_size,
            "blocks": [asdict(b) for b in self.blocks],
            "custom_keys": list(self.custom.keys()),
            "parameter": _jsonable(self.parameter),
            "status_keys": list(self.status.keys()) if isinstance(self.status, dict) else [],
            "kkex_keys": self.kkex_keys,
            "parse_level": self.parse_level,
            "error": self.error,
            "appearance": self.to_appearance().to_dict(),
        }

    def to_appearance(self) -> AnabarraAppearance:
        return map_to_anabarra(self)


def _jsonable(obj: Any, *, depth: int = 0) -> Any:
    if depth > 8:
        return "<max-depth>"
    if isinstance(obj, (str, int, float, bool)) or obj is None:
        return obj
    if isinstance(obj, bytes):
        return f"<bytes:{len(obj)}>"
    if isinstance(obj, dict):
        return {str(k): _jsonable(v, depth=depth + 1) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        if len(obj) > 80 and all(isinstance(x, (int, float)) for x in obj[:8]):
            return list(obj)  # shape arrays — целиком
        return [_jsonable(x, depth=depth + 1) for x in obj[:200]]
    return str(obj)


def _load_type(stream: BinaryIO, fmt: str) -> Any:
    size = struct.calcsize(fmt)
    raw = stream.read(size)
    if len(raw) < size:
        raise ValueError(f"unexpected EOF reading {fmt}")
    return struct.unpack(fmt, raw)[0]


def _load_length(stream: BinaryIO, fmt: str) -> bytes:
    n = _load_type(stream, fmt)
    if n < 0 or n > 200_000_000:
        raise ValueError(f"suspicious length {n}")
    data = stream.read(n)
    if len(data) < n:
        raise ValueError("unexpected EOF in length-prefixed blob")
    return data


def png_iend_offset(data: bytes) -> int:
    if not data.startswith(PNG_MAGIC):
        raise ValueError("not a PNG")
    pos = 8
    while pos + 8 <= len(data):
        length = struct.unpack(">I", data[pos : pos + 4])[0]
        ctype = data[pos + 4 : pos + 8]
        pos += 8 + length + 4
        if ctype == b"IEND":
            return pos
    raise ValueError("IEND not found")


def looks_like_ais_chara(data: bytes) -> bool:
    try:
        off = png_iend_offset(data)
    except ValueError:
        return AIS_MARKER.encode("ascii") in data[:4096]
    tail = data[off : off + 256]
    return AIS_MARKER.encode("ascii") in tail or "AIS_Chara".encode("utf-8") in tail


def _msg_unpack(data: bytes) -> Any:
    try:
        import msgpack
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "Нужен пакет msgpack: pip install msgpack"
        ) from exc
    return msgpack.unpackb(data, raw=False, strict_map_key=False)


def _has_msgpack() -> bool:
    try:
        import msgpack  # noqa: F401

        return True
    except ImportError:
        return False


def _decode_header_str(raw: bytes) -> str:
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("utf-8", errors="replace")


def load_ais_chara(path: Path | str, *, full: bool = True) -> AisCharaCard:
    path = Path(path)
    card = AisCharaCard(path=str(path))
    try:
        data = path.read_bytes()
    except OSError as exc:
        card.error = str(exc)
        return card

    try:
        png_end = png_iend_offset(data)
    except ValueError as exc:
        card.error = str(exc)
        return card

    card.png_size = png_end
    stream = io.BytesIO(data[png_end:])

    try:
        card.product_no = int(_load_type(stream, "i"))
        card.header = _decode_header_str(_load_length(stream, "b"))
        card.version = _decode_header_str(_load_length(stream, "b"))
        face = _load_length(stream, "i")
        card.face_image_size = len(face)
        card.parse_level = "header"
    except ValueError as exc:
        card.error = f"header: {exc}"
        return card

    if AIS_MARKER not in card.header and "Chara" not in card.header:
        card.error = f"unknown header {card.header!r}"
        return card

    if not full:
        return card

    if not _has_msgpack():
        card.error = "msgpack not installed — header only"
        return card

    try:
        lst_raw = _load_length(stream, "i")
        lst = _msg_unpack(lst_raw)
        payload = _load_length(stream, "q")
        entries = lst.get("lstInfo") if isinstance(lst, dict) else None
        if not isinstance(entries, list):
            raise ValueError("lstInfo missing")
        for e in entries:
            if not isinstance(e, dict):
                continue
            info = AisBlockInfo(
                name=str(e.get("name") or ""),
                version=str(e.get("version") or ""),
                pos=int(e.get("pos") or 0),
                size=int(e.get("size") or 0),
            )
            card.blocks.append(info)
        card.parse_level = "blocks"

        by_name = {b.name: b for b in card.blocks}
        if "Custom" in by_name:
            card.custom = _parse_custom(payload, by_name["Custom"])
        if "Parameter" in by_name:
            card.parameter = _parse_single_msgpack(payload, by_name["Parameter"])
        if "Status" in by_name:
            card.status = _parse_single_msgpack(payload, by_name["Status"])
        if "KKEx" in by_name:
            kk = _parse_single_msgpack(payload, by_name["KKEx"])
            if isinstance(kk, dict):
                card.kkex_keys = [str(k) for k in kk.keys()]
        if "Coordinate" in by_name:
            card.coordinate_summary = _summarize_coordinate(
                payload, by_name["Coordinate"]
            )
        card.parse_level = "full"
    except Exception as exc:  # noqa: BLE001
        card.error = f"blocks: {exc}"
    return card


def _slice(payload: bytes, info: AisBlockInfo) -> bytes:
    return payload[info.pos : info.pos + info.size]


def _parse_single_msgpack(payload: bytes, info: AisBlockInfo) -> dict[str, Any]:
    raw = _slice(payload, info)
    obj = _msg_unpack(raw)
    return obj if isinstance(obj, dict) else {"_value": obj}


def _parse_custom(payload: bytes, info: AisBlockInfo) -> dict[str, Any]:
    """Custom = face + body + hair, каждый length-prefixed MessagePack."""
    raw = _slice(payload, info)
    stream = io.BytesIO(raw)
    out: dict[str, Any] = {}
    for field_name in ("face", "body", "hair"):
        try:
            chunk = _load_length(stream, "i")
            out[field_name] = _msg_unpack(chunk)
        except Exception as exc:  # noqa: BLE001
            out[field_name] = {"_error": str(exc)}
            break
    return out


def _summarize_coordinate(payload: bytes, info: AisBlockInfo) -> Any:
    raw = _slice(payload, info)
    try:
        if info.version == "0.0.0":
            coords = _msg_unpack(raw)
            if isinstance(coords, list):
                return {"outfits": len(coords), "version": info.version}
        obj = _msg_unpack(raw)
        if isinstance(obj, dict):
            return {"keys": list(obj.keys())[:20], "version": info.version}
        return {"type": type(obj).__name__, "version": info.version}
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc), "version": info.version}


def _as_float_list(value: Any) -> list[float]:
    if not isinstance(value, (list, tuple)):
        return []
    out: list[float] = []
    for x in value:
        try:
            out.append(float(x))
        except (TypeError, ValueError):
            continue
    return out


def _extract_hair_parts(hair: Any) -> tuple[list[int], list[dict[str, Any]]]:
    ids: list[int] = []
    parts: list[dict[str, Any]] = []
    if not isinstance(hair, dict):
        return ids, parts
    # типичные ключи KK/AI: parts / hairId / kind
    candidates = hair.get("parts") or hair.get("hairParts") or hair.get("hair")
    if isinstance(candidates, list):
        for i, p in enumerate(candidates):
            if not isinstance(p, dict):
                continue
            hid = p.get("id", p.get("hairId", p.get("kind")))
            try:
                hid_i = int(hid)
            except (TypeError, ValueError):
                hid_i = -1
            ids.append(hid_i)
            parts.append(
                {
                    "index": i,
                    "id": hid_i,
                    "keys": sorted(str(k) for k in p.keys())[:30],
                }
            )
    else:
        for key in ("hairId", "id", "kind"):
            if key in hair:
                try:
                    ids.append(int(hair[key]))
                except (TypeError, ValueError):
                    pass
    return ids, parts


def map_to_anabarra(card: AisCharaCard) -> AnabarraAppearance:
    face = card.custom.get("face") if isinstance(card.custom, dict) else {}
    body = card.custom.get("body") if isinstance(card.custom, dict) else {}
    hair = card.custom.get("hair") if isinstance(card.custom, dict) else {}
    if not isinstance(face, dict):
        face = {}
    if not isinstance(body, dict):
        body = {}

    shape_face = _as_float_list(
        face.get("shapeValueFace")
        or face.get("shapeValue")
        or face.get("shape")
    )
    shape_body = _as_float_list(
        body.get("shapeValueBody")
        or body.get("shapeValue")
        or body.get("shape")
    )
    hair_ids, hair_parts = _extract_hair_parts(hair)

    name = ""
    param = card.parameter if isinstance(card.parameter, dict) else {}
    for key in ("fullname", "nickname", "firstname", "lastname", "name"):
        if param.get(key):
            name = str(param.get(key)).strip()
            if name:
                break
    if not name and param.get("lastname") or param.get("firstname"):
        name = f"{param.get('lastname', '')} {param.get('firstname', '')}".strip()

    face_detail = {
        k: _jsonable(v)
        for k, v in face.items()
        if k
        not in (
            "shapeValueFace",
            "shapeValue",
            "shape",
        )
        and not isinstance(v, (bytes, bytearray))
    }
    # ограничим размер
    face_detail = dict(list(face_detail.items())[:40])

    return AnabarraAppearance(
        source_path=card.path,
        card_header=card.header,
        card_version=card.version,
        product_no=card.product_no,
        character_name=name,
        face_shape_values=shape_face,
        body_shape_values=shape_body,
        hair_ids=hair_ids,
        hair_parts=hair_parts,
        face_detail=face_detail,
        raw_parameter=_jsonable(param) if isinstance(param, dict) else {},
        blocks=[b.name for b in card.blocks],
        notes=(
            f"parse_level={card.parse_level}"
            + (f"; error={card.error}" if card.error else "")
        ),
    )


def dump_appearance_json(card: AisCharaCard, out_path: Path | str) -> Path:
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(card.to_appearance().to_dict(), ensure_ascii=False, indent=2)
        + "\n",
        encoding="utf-8",
    )
    return out


def format_card_report(card: AisCharaCard) -> str:
    app = card.to_appearance()
    lines = [
        f"AIS card: {card.path}",
        f"  header={card.header!r} version={card.version} product={card.product_no}",
        f"  png_size={card.png_size} face_thumb={card.face_image_size} "
        f"parse={card.parse_level} err={card.error!r}",
        f"  blocks: {', '.join(b.name for b in card.blocks) or '(none)'}",
        f"  name: {app.character_name or '(n/a)'}",
        f"  face_shape_values: {len(app.face_shape_values)}",
        f"  body_shape_values: {len(app.body_shape_values)}",
        f"  hair_ids: {app.hair_ids[:20]}",
    ]
    if app.face_shape_values:
        preview = ", ".join(f"{v:.3f}" for v in app.face_shape_values[:12])
        lines.append(f"  face_sliders[0:12]: {preview}")
    if card.kkex_keys:
        lines.append(f"  kkex_mods: {', '.join(card.kkex_keys[:15])}")
    return "\n".join(lines)
