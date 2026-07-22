"""Доставка reflect-ответов частями — короткие сообщения вместо одного долгого JSON."""

from __future__ import annotations

import os
import re
from typing import TYPE_CHECKING, List, Optional, Sequence

if TYPE_CHECKING:
    from .config import Config


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


def reflect_max_parts(config: Config | None = None) -> int:
    raw = (os.environ.get("VIU_REFLECT_MAX_PARTS") or "").strip()
    if not raw and config is not None:
        raw = str(getattr(config, "reflect_max_parts", "") or "").strip()
    try:
        return max(1, min(5, int(raw or "3")))
    except ValueError:
        return 3


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
    if wc >= int(limit * 0.9):
        return True
    if wc >= limit - 15 and looks_incomplete_ending(text):
        return True
    return False


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
        f"Только JSON: {{\"thought\":\"коротко\",\"final\":\"часть {part_index + 1}…\"}} — "
        f"до ~{max_words} слов. "
        "Если мысль закончена — заверши предложение и точку. "
        "Если ещё осталось — можно намекнуть «(продолжу)»."
    )


def truncate_retry_hint(*, attempt: int, max_words: int) -> str:
    base = (
        "Ответ оборвался — модель не влезает в один JSON (~300 слов). "
        "Дену нельзя слать сырой JSON или ```json. "
        f'Верни ОДИН JSON: {{"thought":"…","final":"…"}} без текста снаружи. '
        f"Сейчас только **часть 1**: до ~{max_words} слов, законченный кусок. "
        "Длинное — Вью дошлёт части 2–3 отдельными сообщениями сама. "
    )
    if attempt >= 1:
        base += f"Ещё короче — до ~{max(80, max_words - 40)} слов, но цельная мысль. "
    else:
        base += "Не пытайся влезть всё — лучше коротко и тепло. "
    return base


def delivery_parts(full_text: str, *, config: Config | None = None) -> List[str]:
    """Разбить уже готовый текст на пузыри для GUI/Telegram (запасной путь)."""
    text = (full_text or "").strip()
    if not text:
        return []
    limit = reflect_max_words_per_part(config)
    words = text.split()
    if len(words) <= limit:
        return [text]
    parts: List[str] = []
    i = 0
    while i < len(words) and len(parts) < reflect_max_parts(config):
        chunk = words[i : i + limit]
        i += limit
        parts.append(" ".join(chunk).strip())
    if i < len(words) and parts:
        parts[-1] = parts[-1] + " " + " ".join(words[i:])
    return parts or [text]
