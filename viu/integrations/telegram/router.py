"""Маршрутизация сообщений из Telegram: болтовня vs команда."""

from __future__ import annotations

import re

# Явные команды — полный агент с инструментами.
_WORK_HINTS = (
    "следующ",
    "шаг",
    "запуст",
    "открой",
    "unity",
    "блендер",
    "blender",
    "сарай",
    "inbox",
    "оверлей",
    "overlay",
    "prepare",
    "собер",
    "размет",
    "каталог",
    "prop",
    "встрой",
    "принять",
    "asset",
    "обнов",
    "fix",
    "почини",
    "сделай",
    "давай",
    "продолж",
    "автопилот",
    "двига",
    "проект",
    "статус",
    "project",
    "roadmap",
    "rig",
    "экспорт",
    "fbx",
    "play",
    "шан",
)

# Только приветствие / small talk — без Unity и batch.
_GREETING_ONLY = re.compile(
    r"^(?:\s*(?:"
    r"привет|здравств|добр(?:ый|ое|ая|ой|ого|ую)|"
    r"hi|hello|hey|хай|салют|"
    r"спасибо|thanks|thx|пока|бб|bb|"
    r"ok|ок+|окей|okay|ага|понял|ясно|класс|супер|норм|"
    r"как дела|что нового|ты тут|на связи|доброй"
    r")[\s,!.\-—]*(?:вью|viu)?[\s,!.\-—]*)+$",
    re.IGNORECASE,
)


def route_telegram_message(text: str, *, waiting_for_user: bool = False) -> str:
    """Вернёт ``chat`` (только ответ) или ``work`` (агент с инструментами)."""
    if waiting_for_user:
        return "work"
    t = (text or "").strip()
    if not t or t.startswith("/"):
        return "chat"
    if _GREETING_ONLY.match(t):
        return "chat"
    low = t.lower()
    if any(h in low for h in _WORK_HINTS):
        return "work"
    # Короткая реплика без глаголов работы — скорее болтовня.
    if len(t) < 60 and "?" not in t:
        words = [w for w in re.split(r"\s+", low) if w]
        if len(words) <= 7:
            return "chat"
    return "work"


def route_user_message(text: str, *, waiting_for_user: bool = False) -> str:
    """Та же логика для чата в окне Viu."""
    return route_telegram_message(text, waiting_for_user=waiting_for_user)
