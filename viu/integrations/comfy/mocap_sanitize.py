"""MoCap-промпты: без «кино»-шелухи, только движение для трекинга."""

from __future__ import annotations

import re
from typing import Optional

_MOCAP_FLUFF = re.compile(
    r"(?i)\b("
    r"moaning|groan|gasp|orgasm|pleasure|aroused|erotic|sensual|intimate|"
    r"sweat|sweaty|jiggle|physics|breathing heavily|panting|"
    r"facial expression|emotion|sexy|seductive|lust|herself|himself"
    r")\b"
)

_LEADING_SLUG_RE = re.compile(r"^([\w-]+)(?:\s|$)")


def has_mocap_fluff(text: str) -> bool:
    return bool(_MOCAP_FLUFF.search(text or ""))


def extract_slug_token(text: str) -> Optional[str]:
    raw = (text or "").strip()
    if not raw:
        return None
    m = _LEADING_SLUG_RE.match(raw)
    if not m:
        return None
    token = m.group(1).lower().replace("-", "_")
    if token in ("to", "the", "a", "on", "from", "ok"):
        return None
    return token


def sanitize_mocap_action(
    raw: str,
    *,
    canonical: str = "",
) -> tuple[str, str]:
    """Вернуть (action для Wan, заметка Дену)."""
    text = (raw or "").strip()
    if not text:
        return canonical or text, ""

    if canonical and (has_mocap_fluff(text) or len(text) > 100):
        return (
            canonical,
            "Для MoCap нужна **чистая поза**, не порно-сцена. "
            f"Взяла шаблон: «{canonical}». "
            "Пиши `правки: sit_down` или просто `ок` — без moaning/sweat/jiggle.",
        )

    if has_mocap_fluff(text):
        cleaned = _MOCAP_FLUFF.sub("", text)
        cleaned = re.sub(r"\s+", " ", cleaned).strip(" ,")
        if len(cleaned) >= 8:
            return cleaned, "Убрала лишние слова — MoCap = только движение тела."
    return text, ""
