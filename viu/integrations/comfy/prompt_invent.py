"""Изобретатель промптов: фото + пожелание Дена → Wan positive / negative / process.

Целевой UX (Telegram):
  фото + «эту девушку сидящей в кресле» /
        «из анимешной — реалистичной» /
        «надень на неё …»
→ Вью сама пишет промпт, подбирает LoRA, снимает, болтает, присылает результат.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional

from ...config import Config
from .prompts import SUBJECT_PREFIX, clean_process_for_wan, mocap_negative
from .scene_en import map_scene_heuristics, scene_wish_to_en

# Виды правок — влияют на хвост промпта и теги LoRA.
EDIT_POSE = "pose"
EDIT_REALISM = "realism"
EDIT_ANIME = "anime"
EDIT_OUTFIT = "outfit"
EDIT_GENERIC = "generic"

_REALISM_RE = re.compile(
    r"(?i)(?:"
    r"реалист|realistic|photoreal|"
    r"из\s+аниме|из\s+анимешн|анимешн\w*\s*(?:в|→|->|—|-)\s*реал|"
    r"не\s+аниме|убери\s+аниме|сделай\s+живой"
    r")"
)
_ANIME_RE = re.compile(
    r"(?i)(?:"
    r"\bаниме\b|\banime\b|в\s+аниме|анимешн|"
    r"из\s+реал\w*\s*(?:в|→|->|—|-)\s*аниме|"
    r"сделай\s+аниме"
    r")"
)
_OUTFIT_RE = re.compile(
    r"(?i)(?:"
    r"надень|одень|переодень|в\s+одежд|куртк|плать|юбк|костюм|"
    r"swimsuit|bikini|lingerie|футболк|джинс|на\s+ней\s+"
    r")"
)
_POSE_HINT_RE = re.compile(
    r"(?i)(?:"
    r"сид\w*|сто\w*|леж\w*|кресл|диван|окн|селфи|игр|танц|"
    r"нарисуй|сделай|сними|поза|позу"
    r")"
)


@dataclass
class InventedPrompt:
    """Готовый пакет для съёмки / редактора."""

    edit_kind: str
    process: str  # хвост после SUBJECT_PREFIX
    positive: str
    negative: str
    lora_query_tags: List[str]
    summary_ru: str
    show_style: str  # realism | anime


def classify_edit_kind(wish: str) -> str:
    w = (wish or "").strip()
    if not w:
        return EDIT_GENERIC
    if _REALISM_RE.search(w) and not _ANIME_RE.search(w):
        return EDIT_REALISM
    if _ANIME_RE.search(w) and not _REALISM_RE.search(w):
        return EDIT_ANIME
    # «из аниме в реализм» — оба слова; приоритет реализму если есть «реал»
    if _REALISM_RE.search(w) and _ANIME_RE.search(w):
        if re.search(r"(?i)аниме.{0,20}реал|реал.{0,20}аниме", w):
            if re.search(r"(?i)(?:в|→|->|—|-)\s*реал|реал\w*$", w):
                return EDIT_REALISM
            if re.search(r"(?i)(?:в|→|->|—|-)\s*аниме", w):
                return EDIT_ANIME
        return EDIT_REALISM
    if _OUTFIT_RE.search(w):
        return EDIT_OUTFIT
    if _POSE_HINT_RE.search(w) or map_scene_heuristics(w):
        return EDIT_POSE
    return EDIT_GENERIC


def _outfit_en_bits(wish: str) -> str:
    """Грубый EN хвост одежды из RU (без LLM)."""
    w = (wish or "").lower()
    bits: List[str] = []
    mapping = (
        (r"плать", "wearing an elegant dress"),
        (r"юбк", "wearing a skirt"),
        (r"джинс", "wearing jeans"),
        (r"футболк", "wearing a t-shirt"),
        (r"куртк", "wearing a jacket"),
        (r"костюм", "wearing a suit"),
        (r"bikini|бикини", "wearing a bikini"),
        (r"купальник|swimsuit", "wearing a swimsuit"),
        (r"lingerie|белье|бельё", "wearing lingerie"),
    )
    for pat, en in mapping:
        if re.search(pat, w):
            bits.append(en)
    if not bits:
        bits.append("wearing the described outfit, clear clothing details")
    return ", ".join(bits)


def invent_process_line(
    config: Config,
    wish: str,
    *,
    look_ru: str = "",
    edit_kind: str = "",
) -> str:
    """Короткий EN process после «… body is»."""
    kind = edit_kind or classify_edit_kind(wish)
    base = ""

    # look_ru пока не вшиваем в Wan (лицо через ReActor/реф); hint для EN-сцены.
    _ = look_ru
    if kind == EDIT_POSE or kind == EDIT_GENERIC:
        base = map_scene_heuristics(wish) or scene_wish_to_en(wish, config=config)
        if not base:
            base = "posing in soft light, full body"
    elif kind == EDIT_REALISM:
        pose = map_scene_heuristics(wish) or scene_wish_to_en(wish, config=config)
        pose = pose or "standing relaxed, full body"
        base = (
            f"{pose}, photorealistic skin, natural lighting, detailed fabric, "
            "realistic proportions, not anime"
        )
    elif kind == EDIT_ANIME:
        pose = map_scene_heuristics(wish) or scene_wish_to_en(wish, config=config)
        pose = pose or "standing relaxed, full body"
        base = (
            f"{pose}, anime style, clean lineart, vibrant colors, stylized face"
        )
    elif kind == EDIT_OUTFIT:
        pose = map_scene_heuristics(wish) or "standing relaxed, full body"
        base = f"{pose}, {_outfit_en_bits(wish)}"
    else:
        base = "posing in soft light, full body"

    return clean_process_for_wan(base)


def invent_prompt_package(
    config: Config,
    wish: str,
    *,
    look_ru: str = "",
    style_hint: str = "",
) -> InventedPrompt:
    """Полный пакет: kind, positive, negative, теги для LoRA, краткое RU."""
    kind = classify_edit_kind(wish)
    show_style = "anime" if kind == EDIT_ANIME else "realism"
    if (style_hint or "").strip().lower() in ("anime", "аниме"):
        show_style = "anime"
        if kind == EDIT_GENERIC:
            kind = EDIT_ANIME

    process = invent_process_line(config, wish, look_ru=look_ru, edit_kind=kind)
    if show_style == "anime" and "anime" not in process.lower():
        process = f"{process}, anime style, vibrant colors"
    elif show_style == "realism" and kind == EDIT_REALISM:
        if "photorealistic" not in process.lower():
            process = f"{process}, photorealistic, detailed skin"

    positive = f"{SUBJECT_PREFIX} {process}".strip()
    negative = mocap_negative()

    tags: List[str] = []
    if kind == EDIT_ANIME or show_style == "anime":
        tags.extend(["anime", "wan", "style"])
    if kind == EDIT_REALISM:
        tags.extend(["realism", "realistic", "photo"])
    if kind == EDIT_OUTFIT:
        tags.extend(["outfit", "clothing", "dress", "fashion"])
    if kind == EDIT_POSE:
        tags.extend(["pose", "motion", "wan"])
    # слова из wish как слабые теги
    for tok in re.findall(r"[A-Za-zА-Яа-яЁё]{4,}", wish or ""):
        tags.append(tok.lower())

    kind_ru = {
        EDIT_POSE: "поза/сцена",
        EDIT_REALISM: "аниме → реализм",
        EDIT_ANIME: "стиль аниме",
        EDIT_OUTFIT: "одежда",
        EDIT_GENERIC: "сцена",
    }.get(kind, kind)
    summary = (
        f"Правка: {kind_ru}.\n"
        f"Промпт: {positive[:220]}{'…' if len(positive) > 220 else ''}"
    )
    return InventedPrompt(
        edit_kind=kind,
        process=process,
        positive=positive,
        negative=negative,
        lora_query_tags=tags,
        summary_ru=summary,
        show_style=show_style,
    )


def format_invent_brief(pkg: InventedPrompt, *, lora_names: Optional[List[str]] = None) -> str:
    lines = [
        "Ок, сама соберу — без панели.",
        pkg.summary_ru,
        f"Negative: {pkg.negative}",
    ]
    if lora_names:
        lines.append("LoRA: " + ", ".join(lora_names))
    else:
        lines.append("LoRA: чистый Wan (подходящих не нашла / нет на диске).")
    lines.append("Болтаем дальше — когда будет готово, пришлю.")
    return "\n".join(lines)
