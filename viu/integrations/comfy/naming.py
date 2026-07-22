"""Имена MoCap-видео: Girl_Idle_to_Sit_down_take_b_03.mp4."""

from __future__ import annotations

import os
import re
from typing import Optional, Sequence

_DEFAULT_SUBJECT = "Girl"


def _cap_part(slug: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9_]+", "_", (slug or "").strip())
    parts = [p for p in s.split("_") if p]
    if not parts:
        return "Motion"
    if len(parts) == 1:
        p = parts[0]
        return p[:1].upper() + p[1:].lower()
    head = parts[0][:1].upper() + parts[0][1:].lower()
    tail = "_".join(p.lower() for p in parts[1:])
    return f"{head}_{tail}"


def normalize_slug_for_name(slug: str) -> str:
    from .clip_review import normalize_catalog_slug

    return normalize_catalog_slug(slug)


def comfy_filename_prefix(stem: str, *, max_len: int = 100) -> str:
    """Префикс для Comfy SaveVideo — без пробелов и лишней длины."""
    s = re.sub(r"[^a-zA-Z0-9_]+", "_", (stem or "").strip())
    s = re.sub(r"_+", "_", s).strip("_")
    if not s:
        return "viu_mocap"
    if len(s) > max_len:
        s = s[:max_len].rstrip("_")
    return s or "viu_mocap"


def max_clips_per_action() -> int:
    try:
        return max(1, int(os.environ.get("VIU_COMFY_MAX_PER_ACTION", "10")))
    except ValueError:
        return 10


def display_video_stem(
    *,
    subject: str = _DEFAULT_SUBJECT,
    catalog_slug: str,
    enters_from: Optional[Sequence[str]] = None,
    looped: bool = False,
    take_id: str = "",
    seq: int = 0,
) -> str:
    """Читаемое имя: Girl_Idle_to_Sit_down, Girl_Walk_loop_02, …"""
    slug = normalize_slug_for_name(catalog_slug)
    parts = [_cap_part(subject) or "Girl"]
    src = [normalize_slug_for_name(x) for x in (enters_from or []) if str(x).strip()]
    if src:
        parts.append(_cap_part(src[0]))
        parts.append("to")
        parts.append(_cap_part(slug))
    else:
        parts.append(_cap_part(slug))
        if looped:
            parts.append("loop")
    if take_id:
        parts.append(take_id.strip().lower())
    if seq > 0:
        parts.append(f"{seq:02d}")
    return "_".join(parts)


def kept_count_for_slug(config, catalog_slug: str) -> int:
    from .clip_review import ComfyClipStore, STATUS_KEPT, clip_review_path, normalize_catalog_slug

    slug = normalize_catalog_slug(catalog_slug)
    store = ComfyClipStore(clip_review_path(config)).load()
    return sum(
        1
        for c in store.clips
        if c.status == STATUS_KEPT and normalize_catalog_slug(c.catalog_slug) == slug
    )


def next_kept_seq(config, catalog_slug: str) -> int:
    return kept_count_for_slug(config, catalog_slug) + 1


def comfy_filename_prefix(display_stem: str) -> str:
    """Безопасный filename_prefix для SaveVideo в Comfy."""
    stem = re.sub(r"[^a-zA-Z0-9_]+", "_", (display_stem or "viu_mocap").strip())
    return stem[:120] or "viu_mocap"


def slug_at_quota(config, catalog_slug: str) -> bool:
    return kept_count_for_slug(config, catalog_slug) >= max_clips_per_action()
