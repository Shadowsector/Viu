"""Доставка reflect-ответов частями — несколько коротких сообщений вместо одного обрезанного."""

from __future__ import annotations

import os
import re
from typing import TYPE_CHECKING, List, Optional, Sequence

if TYPE_CHECKING:
    from .config import Config

_COUNT_WORDS = {
    "один": 1,
    "одна": 1,
    "одно": 1,
    "два": 2,
    "две": 2,
    "три": 3,
    "четыре": 4,
    "пять": 5,
    "шесть": 6,
    "семь": 7,
    "восемь": 8,
    "девять": 9,
    "десять": 10,
}


def word_count(text: str) -> int:
    return len(re.findall(r"\S+", (text or "").strip()))


def reflect_max_words_per_part(config: Config | None = None) -> int:
    raw = (os.environ.get("VIU_REFLECT_MAX_WORDS") or "").strip()
    if not raw and config is not None:
        raw = str(getattr(config, "reflect_max_words", "") or "").strip()
    try:
        return max(80, min(400, int(raw or "220")))
    except ValueError:
        return 220


def reflect_max_parts(config: Config | None = None, *, user_text: str = "") -> int:
    raw = (os.environ.get("VIU_REFLECT_MAX_PARTS") or "").strip()
    if not raw and config is not None:
        raw = str(getattr(config, "reflect_max_parts", "") or "").strip()
    try:
        base = max(1, min(8, int(raw or "5")))
    except ValueError:
        base = 5
    asked = requested_item_count(user_text)
    if asked > 1:
        return max(base, min(asked, 8))
    return base


def requested_item_count(user_text: str) -> int:
    """Сколько пунктов просит Ден: «пять событий», «3 сцены»."""
    t = (user_text or "").lower()
    m = re.search(r"\b(\d{1,2})\s*(?:событ|сцен|пункт|иде|истор|кадр|шаг)", t)
    if m:
        return min(8, int(m.group(1)))
    m = re.search(
        r"\b(один|одна|одно|два|две|три|четыре|пять|шесть|семь|восемь|девять|десять)\s+"
        r"(?:событ|сцен|пункт|иде|истор|кадр|шаг)",
        t,
    )
    if m:
        return min(8, _COUNT_WORDS.get(m.group(1), 0))
    return 0


_MORE_MARKERS = (
    "(продолжу",
    "(ещё",
    "(еще",
    "продолжу в следующ",
    "дальше —",
    "во второй части",
)


def looks_incomplete_ending(text: str) -> bool:
    t = (text or "").strip()
    if not t:
        return False
    low = t.lower()
    if any(m in low[-120:] for m in _MORE_MARKERS):
        return True
    if t.endswith("…") or t.endswith("..."):
        return True
    if t[-1] not in ".!?»\"')":
        return True
    return False


def wants_more_parts(parsed: Optional[dict]) -> bool:
    if not parsed:
        return False
    for key in ("more", "continue", "continued", "has_more"):
        val = parsed.get(key)
        if val in (True, 1, "1", "true", "yes"):
            return True
    part = parsed.get("part")
    total = parsed.get("parts") or parsed.get("total_parts")
    try:
        if part is not None and total is not None and int(part) < int(total):
            return True
    except (TypeError, ValueError):
        pass
    return False


def should_fetch_more_parts(
    text: str,
    *,
    parsed: Optional[dict] = None,
    truncated: bool = False,
    config: Config | None = None,
    user_text: str = "",
) -> bool:
    if truncated:
        return True
    if wants_more_parts(parsed):
        return True
    low = (text or "").lower()
    if any(m in low for m in _MORE_MARKERS):
        return True
    limit = reflect_max_words_per_part(config)
    wc = word_count(text)
    # Не дёргать продолжение только из‑за длины — иначе второй пузырь
    # перефразирует то же самое («два процесса»).
    if wc >= int(limit * 0.9) and looks_incomplete_ending(text):
        return True
    if wc >= limit - 15 and looks_incomplete_ending(text):
        return True
    asked = requested_item_count(user_text)
    if asked > 1 and parsed:
        fps = parsed.get("final_parts")
        if isinstance(fps, list) and len(fps) < asked:
            return True
    return False


def list_delivery_hint(user_text: str) -> str:
    n = requested_item_count(user_text)
    if n < 2:
        return scene_delivery_hint(user_text)
    return (
        f"\n\n--- Формат для {n} пунктов ---\n"
        f'Верни JSON с массивом final_parts из {n} коротких сообщений '
        f'(каждое 1–3 предложения, отдельный пузырь в чате). '
        f'Пример: {{"thought":"…","final_parts":["пункт 1…","пункт 2…",…]}}. '
        f"Поле final можно опустить или оставить пустым."
    )


def scene_delivery_hint(user_text: str) -> str:
    """Для сцен/ERP — мягко просим 2–3 пузыря без требования «N событий»."""
    low = (user_text or "").lower()
    if not re.search(
        r"представь|твои\s+действия|сцен|ролев|nsfw|эротик|секс|интим|"
        r"что\s+делаешь|продолж|дальше|ещё",
        low,
    ):
        return ""
    return (
        "\n\n--- Сцена: несколько пузырей ---\n"
        "Лучше final_parts из 2–3 коротких сообщений "
        "(завязка / тело и действие / ощущение). "
        'Можно {"thought":"…","final_parts":["…","…"],'
        '"event_update":{"title":"…","what":"…","senses":"…"}}.'
    )


def continuation_user_prompt(
    *,
    user_text: str,
    prior_parts: Sequence[str],
    part_index: int,
    max_parts: int,
    max_words: int,
) -> str:
    last = prior_parts[-1] if prior_parts else ""
    return (
        f"Часть {part_index} из ≤{max_parts} уже ушла Дену:\n"
        f"---\n{last}\n---\n"
        f"Исходный вопрос Дена: {user_text[:500]}\n\n"
        f"Продолжай с того места, **не повторяй** начало. "
        f'Только JSON: {{"thought":"коротко","final":"часть {part_index + 1}…"}} — '
        f"до ~{max_words} слов. "
        "Если мысль закончена — заверши предложение и точку."
    )


def truncate_retry_hint(*, attempt: int, max_words: int) -> str:
    base = (
        "Ответ оборвался — модель не влезает в один JSON. "
        f'Верни ОДИН JSON: {{"thought":"…","final":"…"}} без текста снаружи. '
        f"Сейчас только **часть 1**: до ~{max_words} слов. "
        "Длинное — Вью дошлёт части 2–3 отдельными сообщениями сама. "
    )
    if attempt >= 1:
        base += f"Ещё короче — до ~{max(80, max_words - 40)} слов, но цельная мысль. "
    return base


def collect_final_parts(
    text: str,
    parsed: Optional[dict],
) -> List[str]:
    parts: List[str] = []
    if parsed:
        fps = parsed.get("final_parts")
        if isinstance(fps, list):
            parts = [str(p).strip() for p in fps if str(p).strip()]
    if not parts and text.strip():
        parts = [text.strip()]
    return parts
