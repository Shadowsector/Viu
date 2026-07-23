"""Проверка MoCap mp4 после Comfy — отсечь битые 4 KB «видео»."""

from __future__ import annotations

from pathlib import Path

# Рабочие клипы Wan ~80+ KB; ReActor+NSFW-filter иногда даёт один чёрный кадр ~4.6 KB.
MIN_MOCAP_MP4_BYTES = 12_000


def validate_mocap_mp4(path: Path, *, min_bytes: int = MIN_MOCAP_MP4_BYTES) -> tuple[bool, str]:
    """(ok, reason). Битый файл — слишком мал или не mp4."""
    p = Path(path)
    if not p.is_file():
        return False, f"нет файла: {p}"
    if p.suffix.lower() != ".mp4":
        return False, f"не mp4: {p.name}"
    size = p.stat().st_size
    if size < min_bytes:
        return (
            False,
            f"{p.name}: {size} байт (< {min_bytes}) — пустой/битый экспорт",
        )
    try:
        head = p.read_bytes()[:12]
    except OSError as exc:
        return False, f"не читается: {exc}"
    if len(head) < 8 or head[4:8] != b"ftyp":
        return False, f"{p.name}: не похоже на mp4 (нет ftyp)"
    return True, f"ok ({size // 1024} KB)"


def reactor_black_frame_hint() -> str:
    return (
        "ReActor вырезал все кадры (NSFW-filter) → чёрный 512×512 mp4. "
        "Вью: полная замена reactor_sfw.py + рестарт Comfy (comfy_reactor_fix). "
        "Повтор без лица — автоматически; или VIU_COMFY_FACE_SWAP=0."
    )
