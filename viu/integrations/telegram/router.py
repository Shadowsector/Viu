"""Маршрутизация: reflect (простой разговор) vs work (работа инструментами).

По умолчанию — reflect. Work только при явной команде действовать.
Голое «Попробуешь?» больше не уводит чат в tools — нужен глагол/цель рядом.
"""

from __future__ import annotations

import re

# Явная команда «следующий шаг» / кнопка.
_EXPLICIT_WORK_RE = re.compile(
    r"(?:^|\n)\s*(?:"
    r"▶\s*следующ(?:ий|\s)*шаг|"
    r"следующ(?:ий|\s)*шаг\s*$|"
    r"^автопилот\s*$"
    r")",
    re.IGNORECASE | re.MULTILINE,
)

# «Сделай X» — конкретное действие.
_DO_WORK_RE = re.compile(
    r"(?:^|\n)\s*(?:"
    r"(?:пожалуйста\s+)?(?:сделай|выполни|запусти|собери|встрой|продолжай)\s+"
    r"(?:следующ|оверлей|сарай|inbox|unity|overlay|prepare|это|работу|handoff|github)"
    r")",
    re.IGNORECASE | re.MULTILINE,
)

# «Попробуй/ешь …» только с действием — иначе это обычный чат.
_TRY_WITH_ACTION_RE = re.compile(
    r"попробу(?:й|ешь|йте)\b.{0,60}(?:"
    r"сдела|выполн|запуст|собер|встрой|вылож|отправ|опублик|откры|"
    r"провер|напиш|прогна|скан|"
    r"github|гитхаб|handoff|cursor|курсор|unity|overlay|оверлей|comfy|inbox|шаг"
    r")",
    re.IGNORECASE | re.DOTALL,
)

# Старт / handoff / GitHub+Cursor — Ден просит не болтать, а делать.
_ACTION_INTENT_RE = re.compile(
    r"(?:"
    r"начни(?:ть|те)?\b|"
    r"стартуй|"
    r"приступай|"
    r"(?:вылож|запиши|отправ|опублику)(?:\w*\s+){0,8}(?:на\s+)?github|"
    r"github.{0,80}(?:cursor|курсор|handoff|размысл|лог)|"
    r"(?:cursor|курсор).{0,60}(?:github|канал|handoff|вылож|прочт|прочит)|"
    r"cursor_handoff|"
    r"handoff"
    r")",
    re.IGNORECASE,
)

# Проверка токена / diagnose — сразу инструмент, не болтовня.
_GITHUB_DIAGNOSE_RE = re.compile(
    r"(?:"
    r"github_diagnose|"
    r"диагност(?:ика|ировать).{0,40}github|"
    r"провер(?:ь|ите|ить).{0,50}(?:github|гитхаб).{0,50}(?:токен|token|доступ|scope|права)|"
    r"провер(?:ь|ите|ить).{0,50}(?:токен|token).{0,50}(?:github|гитхаб)|"
    r"(?:github|гитхаб).{0,50}(?:токен|token).{0,50}провер|"
    r"статус.{0,40}(?:github|гитхаб).{0,40}(?:токен|token)"
    r")",
    re.IGNORECASE,
)


def route_telegram_message(text: str, *, waiting_for_user: bool = False) -> str:
    """``reflect`` (чат) | ``work`` (инструменты). По умолчанию — reflect."""
    if waiting_for_user:
        return "reflect"
    t = (text or "").strip()
    if not t or t.startswith("/"):
        return "reflect"
    if _EXPLICIT_WORK_RE.search(t):
        return "work"
    if _DO_WORK_RE.search(t):
        return "work"
    if _TRY_WITH_ACTION_RE.search(t):
        return "work"
    if _ACTION_INTENT_RE.search(t):
        return "work"
    if _GITHUB_DIAGNOSE_RE.search(t):
        return "work"
    return "reflect"


def route_user_message(text: str, *, waiting_for_user: bool = False) -> str:
    return route_telegram_message(text, waiting_for_user=waiting_for_user)
