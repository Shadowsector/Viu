"""Маршрутизация: почти всё — reflect (думать); work — только явная команда."""

from __future__ import annotations

import re

# Только когда Ден явно просит СДЕЛАТЬ.
_EXPLICIT_WORK_RE = re.compile(
    r"(?:^|\n)\s*(?:"
    r"▶\s*следующ(?:ий|\s)*шаг|"
    r"следующ(?:ий|\s)*шаг\s*$|"
    r"(?:пожалуйста\s+)?(?:сделай|выполни|запусти|собери|встрой|продолжай)\s+(?:следующ|оверлей|сарай|inbox|unity|overlay|prepare)|"
    r"^автопилот\s*$"
    r")",
    re.IGNORECASE | re.MULTILINE,
)


def route_telegram_message(text: str, *, waiting_for_user: bool = False) -> str:
    """``reflect`` | ``work``."""
    if waiting_for_user:
        return "reflect"
    t = (text or "").strip()
    if not t or t.startswith("/"):
        return "reflect"
    if _EXPLICIT_WORK_RE.search(t):
        return "work"
    return "reflect"


def route_user_message(text: str, *, waiting_for_user: bool = False) -> str:
    return route_telegram_message(text, waiting_for_user=waiting_for_user)
