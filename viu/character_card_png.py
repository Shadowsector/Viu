"""Извлечение JSON/конфига кастомизации из PNG «карточек» персонажей.

Старые ассеты могли хранить настройки (слайдеры лица, ID причёсок и т.п.)
внутри PNG несколькими способами:

1. Текстовые чанки PNG: ``tEXt`` / ``zTXt`` / ``iTXt`` (в т.ч. base64)
2. Данные после маркера ``IEND`` (appended payload)
3. JSON/base64-строки, встречающиеся в сырых байтах файла

Только стандартная библиотека Python 3.10+.
"""

from __future__ import annotations

import base64
import json
import struct
import zlib
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable, Optional

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
IEND = b"IEND"


@dataclass
class ExtractedPayload:
    """Один найденный кусок данных внутри PNG."""

    source: str  # chunk:KEYWORD | after_iend | raw_scan
    kind: str  # json | text | bytes | base64_json
    preview: str = ""
    data: Any = None
    byte_length: int = 0
    notes: str = ""


@dataclass
class PngProbeResult:
    path: str
    ok: bool
    error: str = ""
    size: int = 0
    width: Optional[int] = None
    height: Optional[int] = None
    bit_depth: Optional[int] = None
    color_type: Optional[int] = None
    chunk_types: list[str] = field(default_factory=list)
    text_chunks: list[dict[str, str]] = field(default_factory=list)
    payloads: list[ExtractedPayload] = field(default_factory=list)
    after_iend_bytes: int = 0
    summary_keys: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        return d


def _safe_decode(data: bytes) -> str:
    for enc in ("utf-8", "utf-16", "latin-1"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def _try_json(text: str) -> Any:
    text = text.strip()
    if not text:
        return None
    if text[0] not in "{[":
        # иногда JSON обёрнут в кавычки или с префиксом
        start_obj = text.find("{")
        start_arr = text.find("[")
        starts = [i for i in (start_obj, start_arr) if i >= 0]
        if not starts:
            return None
        text = text[min(starts) :]
    try:
        return json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return None


def _try_base64_json(text: str) -> Any:
    raw = "".join(text.split())
    if len(raw) < 8:
        return None
    # padding
    pad = (-len(raw)) % 4
    if pad:
        raw += "=" * pad
    try:
        decoded = base64.b64decode(raw, validate=False)
    except Exception:  # noqa: BLE001
        try:
            decoded = base64.b64decode(raw)
        except Exception:  # noqa: BLE001
            return None
    as_text = _safe_decode(decoded)
    return _try_json(as_text)


def _collect_keys(obj: Any, *, limit: int = 80) -> list[str]:
    keys: list[str] = []

    def walk(node: Any, prefix: str = "") -> None:
        if len(keys) >= limit:
            return
        if isinstance(node, dict):
            for k, v in node.items():
                path = f"{prefix}.{k}" if prefix else str(k)
                keys.append(path)
                if len(keys) >= limit:
                    return
                if isinstance(v, (dict, list)):
                    walk(v, path)
        elif isinstance(node, list) and node:
            walk(node[0], f"{prefix}[]" if prefix else "[]")

    walk(obj)
    return keys


def _parse_text_chunk(chunk_type: bytes, data: bytes) -> tuple[str, str]:
    """Вернуть (keyword, text)."""
    if chunk_type == b"tEXt":
        if b"\x00" not in data:
            return "", _safe_decode(data)
        key, _, rest = data.partition(b"\x00")
        return _safe_decode(key), _safe_decode(rest)
    if chunk_type == b"zTXt":
        if b"\x00" not in data:
            return "", ""
        key, _, rest = data.partition(b"\x00")
        if not rest:
            return _safe_decode(key), ""
        # rest[0] = compression method (0 = zlib)
        comp = rest[1:] if rest[0:1] == b"\x00" else rest[1:]
        try:
            text = zlib.decompress(comp).decode("utf-8", errors="replace")
        except zlib.error:
            text = _safe_decode(comp)
        return _safe_decode(key), text
    if chunk_type == b"iTXt":
        # keyword\0 compression_flag\0 compression_method\0 language\0 translated\0 text
        parts = data.split(b"\x00", 5)
        if len(parts) < 6:
            return "", _safe_decode(data)
        key = _safe_decode(parts[0])
        comp_flag = parts[1][:1] if parts[1] else b"\x00"
        text_bytes = parts[5]
        if comp_flag == b"\x01":
            try:
                text = zlib.decompress(text_bytes).decode("utf-8", errors="replace")
            except zlib.error:
                text = _safe_decode(text_bytes)
        else:
            text = _safe_decode(text_bytes)
        return key, text
    return "", ""


def _payload_from_text(source: str, text: str) -> list[ExtractedPayload]:
    out: list[ExtractedPayload] = []
    if not text:
        return out
    parsed = _try_json(text)
    if parsed is not None:
        out.append(
            ExtractedPayload(
                source=source,
                kind="json",
                preview=json.dumps(parsed, ensure_ascii=False)[:500],
                data=parsed,
                byte_length=len(text.encode("utf-8", errors="replace")),
            )
        )
        return out
    b64 = _try_base64_json(text)
    if b64 is not None:
        out.append(
            ExtractedPayload(
                source=source,
                kind="base64_json",
                preview=json.dumps(b64, ensure_ascii=False)[:500],
                data=b64,
                byte_length=len(text.encode("utf-8", errors="replace")),
                notes="decoded from base64 text",
            )
        )
        return out
    # длинный текст без JSON — всё равно зафиксировать
    if len(text) >= 8:
        out.append(
            ExtractedPayload(
                source=source,
                kind="text",
                preview=text[:500],
                data=text if len(text) <= 4000 else text[:4000],
                byte_length=len(text.encode("utf-8", errors="replace")),
            )
        )
    return out


def _payload_from_bytes(source: str, raw: bytes) -> list[ExtractedPayload]:
    out: list[ExtractedPayload] = []
    if not raw:
        return out
    text = _safe_decode(raw)
    from_text = _payload_from_text(source, text)
    if from_text and from_text[0].kind in ("json", "base64_json"):
        return from_text
    # zlib-обёртка после IEND
    for offset in (0, 1, 2, 4):
        if len(raw) <= offset:
            break
        try:
            inflated = zlib.decompress(raw[offset:])
        except zlib.error:
            continue
        nested = _payload_from_bytes(f"{source}+zlib@{offset}", inflated)
        if nested:
            return nested
    out.extend(from_text)
    if not out:
        out.append(
            ExtractedPayload(
                source=source,
                kind="bytes",
                preview=raw[:64].hex(),
                byte_length=len(raw),
                notes="no utf/json decoded",
            )
        )
    return out


def _scan_raw_for_json(blob: bytes, *, max_hits: int = 5) -> list[ExtractedPayload]:
    """Грубый поиск JSON-объектов в сырых байтах (на случай стегано/мусора)."""
    out: list[ExtractedPayload] = []
    text = blob.decode("latin-1", errors="ignore")
    idx = 0
    while len(out) < max_hits:
        start = text.find("{", idx)
        if start < 0:
            break
        # ограничим окно
        window = text[start : start + 2_000_000]
        depth = 0
        end = -1
        for i, ch in enumerate(window):
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    end = i
                    break
        if end < 0:
            idx = start + 1
            continue
        candidate = window[: end + 1]
        parsed = _try_json(candidate)
        idx = start + end + 1
        if parsed is None:
            continue
        # отсечь крошечный шум
        if isinstance(parsed, dict) and len(parsed) == 0:
            continue
        out.append(
            ExtractedPayload(
                source=f"raw_scan@{start}",
                kind="json",
                preview=json.dumps(parsed, ensure_ascii=False)[:500],
                data=parsed,
                byte_length=len(candidate.encode("utf-8", errors="replace")),
                notes="found by brace-scan in file bytes",
            )
        )
    return out


def iter_png_chunks(data: bytes) -> Iterable[tuple[bytes, bytes, int]]:
    """Yield (type, data, offset). Stops at IEND (inclusive) or truncated stream."""
    if not data.startswith(PNG_MAGIC):
        raise ValueError("not a PNG (bad magic)")
    pos = 8
    while pos + 8 <= len(data):
        length = struct.unpack(">I", data[pos : pos + 4])[0]
        ctype = data[pos + 4 : pos + 8]
        start = pos
        pos += 8
        chunk_data = data[pos : pos + length]
        pos += length
        # CRC
        pos += 4
        yield ctype, chunk_data, start
        if ctype == IEND:
            return


def probe_png(path: Path | str, *, deep_scan: bool = True) -> PngProbeResult:
    path = Path(path)
    result = PngProbeResult(path=str(path), ok=False)
    try:
        data = path.read_bytes()
    except OSError as exc:
        result.error = str(exc)
        return result
    result.size = len(data)
    if not data.startswith(PNG_MAGIC):
        result.error = "not a PNG (magic mismatch)"
        # всё равно попробуем как «фейковый png» с JSON внутри
        payloads = _payload_from_bytes("whole_file", data)
        if deep_scan:
            payloads.extend(_scan_raw_for_json(data))
        result.payloads = payloads
        for p in payloads:
            if p.kind in ("json", "base64_json") and p.data is not None:
                result.summary_keys.extend(_collect_keys(p.data))
        result.ok = bool(payloads)
        return result

    iend_end = None
    try:
        for ctype, cdata, _offset in iter_png_chunks(data):
            result.chunk_types.append(ctype.decode("ascii", errors="replace"))
            if ctype == b"IHDR" and len(cdata) >= 13:
                result.width = struct.unpack(">I", cdata[0:4])[0]
                result.height = struct.unpack(">I", cdata[4:8])[0]
                result.bit_depth = cdata[8]
                result.color_type = cdata[9]
            if ctype in (b"tEXt", b"zTXt", b"iTXt"):
                key, text = _parse_text_chunk(ctype, cdata)
                result.text_chunks.append(
                    {
                        "type": ctype.decode("ascii"),
                        "keyword": key,
                        "length": str(len(text)),
                        "preview": text[:200],
                    }
                )
                result.payloads.extend(
                    _payload_from_text(f"chunk:{ctype.decode()}:{key or '?'}", text)
                )
            if ctype == IEND:
                # pos after reading this chunk: find absolute end
                # re-scan to get exact end offset
                break
        # найти конец IEND точно
        pos = 8
        while pos + 8 <= len(data):
            length = struct.unpack(">I", data[pos : pos + 4])[0]
            ctype = data[pos + 4 : pos + 8]
            pos += 8 + length + 4
            if ctype == IEND:
                iend_end = pos
                break
    except ValueError as exc:
        result.error = str(exc)
        return result

    if iend_end is not None and iend_end < len(data):
        trailing = data[iend_end:]
        result.after_iend_bytes = len(trailing)
        result.payloads.extend(_payload_from_bytes("after_iend", trailing))

    if deep_scan and not any(p.kind in ("json", "base64_json") for p in result.payloads):
        # только если JSON ещё не нашли — дорогой scan
        result.payloads.extend(_scan_raw_for_json(data, max_hits=3))

    keys: list[str] = []
    for p in result.payloads:
        if p.kind in ("json", "base64_json") and p.data is not None:
            keys.extend(_collect_keys(p.data))
    # unique preserve order
    seen: set[str] = set()
    for k in keys:
        if k not in seen:
            seen.add(k)
            result.summary_keys.append(k)

    result.ok = True
    return result


def probe_directory(
    directory: Path | str,
    *,
    glob_pat: str = "*.png",
    deep_scan: bool = True,
    limit: int = 50,
) -> list[PngProbeResult]:
    root = Path(directory)
    if not root.is_dir():
        return [
            PngProbeResult(
                path=str(root),
                ok=False,
                error=f"directory not found: {root}",
            )
        ]
    files = sorted(root.glob(glob_pat))[:limit]
    # также без учёта регистра на Windows уже ок; на linux добавим *.PNG
    if not files:
        files = sorted(set(root.glob("*.png")) | set(root.glob("*.PNG")))[:limit]
    return [probe_png(p, deep_scan=deep_scan) for p in files]


def format_probe_report(results: list[PngProbeResult], *, max_preview: int = 1200) -> str:
    lines: list[str] = []
    lines.append(f"PNG character-card probe: {len(results)} file(s)")
    for r in results:
        lines.append("")
        lines.append("=" * 60)
        lines.append(f"FILE: {r.path}")
        lines.append(f"ok={r.ok} size={r.size} {r.width}x{r.height} err={r.error!r}")
        lines.append(f"chunks: {', '.join(r.chunk_types) if r.chunk_types else '(none)'}")
        lines.append(f"after_iend_bytes={r.after_iend_bytes}")
        if r.text_chunks:
            lines.append("text_chunks:")
            for tc in r.text_chunks:
                lines.append(
                    f"  - {tc.get('type')} keyword={tc.get('keyword')!r} "
                    f"len={tc.get('length')} preview={tc.get('preview')!r}"
                )
        if r.summary_keys:
            lines.append("json_keys (sample):")
            lines.append("  " + ", ".join(r.summary_keys[:60]))
        if r.payloads:
            lines.append(f"payloads: {len(r.payloads)}")
            for i, p in enumerate(r.payloads):
                lines.append(
                    f"  [{i}] source={p.source} kind={p.kind} "
                    f"bytes={p.byte_length} notes={p.notes!r}"
                )
                prev = (p.preview or "")[:max_preview]
                if prev:
                    lines.append("      preview:")
                    for pl in prev.splitlines()[:40]:
                        lines.append(f"      {pl}")
        else:
            lines.append("payloads: (none)")
    return "\n".join(lines)


def dump_json_payloads(
    results: list[PngProbeResult],
    out_dir: Path | str,
) -> list[Path]:
    """Сохранить каждый найденный JSON рядом в out_dir/<stem>__<i>.json."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for r in results:
        stem = Path(r.path).stem
        n = 0
        for p in r.payloads:
            if p.kind not in ("json", "base64_json") or p.data is None:
                continue
            target = out / f"{stem}__{n}.json"
            target.write_text(
                json.dumps(p.data, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            written.append(target)
            n += 1
    return written
