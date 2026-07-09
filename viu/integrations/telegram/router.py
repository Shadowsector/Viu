"""Маршрутизация сообщений: болтовня / статус / команда."""

from __future__ import annotations

import re

# Вопрос о плане — ответ словами, без Unity.
_STATUS_RE = re.compile(
    r"(?:"
    r"что\s+(?:у\s+(?:нас|на)|дальше|след|теперь|по\s+плану|нового|там)|"
    r"куда\s+(?:дальше|идём|идем)|"
    r"как\s+(?:дела|идёт|идет|прогресс|нам|у\s+нас)|"
    r"где\s+мы|"
    r"какой\s+(?:план|шаг|статус)|"
    r"расскаж(?:и|ите)\s+(?:про\s+)?(?:план|статус|проект)|"
    r"что\s+по\s+проект"
    r")",
    re.IGNORECASE,
)

# Явная команда «делай» — полный агент с инструментами.
_WORK_RE = re.compile(
    r"(?:"
    r"следующ(?:ий|\s)*шаг|"
    r"запуст(?:и|ить)|открой|"
    r"unity|блендер|blender|"
    r"встрой|прин(?:ять|им)|prepare|"
    r"собер(?:и|ить)|оверлей|overlay|"
    r"размет|каталог|"
    r"продолж(?:ай|и)|автопилот|"
    r"inbox|prepare_unity|"
    r"почини|fix|"
    r"сделай|выполни|"
    r"давай\s+(?:встрой|собер|запуст|сдел|продолж|встроим)|"
    r"unity_prepare|unity_overlay|rig_check|"
    r"экспорт|fbx|"
    r"▶\s*следующий"
    r")",
    re.IGNORECASE,
)

# Только приветствие / благодарность — без инструментов.
_SMALLTALK_RE = re.compile(
    r"^(?:\s*(?:"
    r"привет|здравств|добр(?:ый|ое|ая|ой|ого|ую)|"
    r"hi|hello|hey|хай|салют|"
    r"спасибо|thanks|thx|благодар|"
    r"пока|бб|bb|"
    r"ok|ок+|окей|okay|ага|понял|ясно|класс|супер|норм|круто|"
    r"как дела|что нового|ты тут|на связи|доброй|"
    r"ты\s+(?:супер|класс|лучш|молодец|умнич)"
    r")[\s,!.\-—\)]*)+$",
    re.IGNORECASE,
)


def route_telegram_message(text: str, *, waiting_for_user: bool = False) -> str:
    """``chat`` | ``status`` | ``work``."""
    if waiting_for_user:
        return "work"
    t = (text or "").strip()
    if not t or t.startswith("/"):
        return "chat"
    low = t.lower()
    if _SMALLTALK_RE.match(t):
        return "chat"
    if _STATUS_RE.search(low):
        return "status"
    if _WORK_RE.search(low):
        return "work"
    # Вопрос без явной команды — статус, не Unity.
    if "?" in t:
        return "status"
    # Короткое сообщение без глагола «сделай» — болтовня.
    if len(t) < 100:
        return "chat"
    return "work"


def route_user_message(text: str, *, waiting_for_user: bool = False) -> str:
    return route_telegram_message(text, waiting_for_user=waiting_for_user)
