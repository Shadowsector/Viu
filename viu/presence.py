"""Режим присутствия Дена: home (с вопросами) / away (автономно)."""

from __future__ import annotations

from typing import Literal

from .config import Config
from .runtime_settings import get, set_value

PresenceMode = Literal["home", "away"]

MODE_HOME = "home"
MODE_AWAY = "away"

_LABELS = {
    MODE_HOME: "Я дома — можно спрашивать",
    MODE_AWAY: "Меня нет — работай сама",
}


def get_presence(config: Config) -> PresenceMode:
    raw = str(get(config, "presence_mode", MODE_HOME) or MODE_HOME).strip().lower()
    return MODE_AWAY if raw == MODE_AWAY else MODE_HOME


def set_presence(config: Config, mode: str) -> PresenceMode:
    m = MODE_AWAY if str(mode).strip().lower() == MODE_AWAY else MODE_HOME
    set_value(config, "presence_mode", m)
    return m


def is_away(config: Config) -> bool:
    return get_presence(config) == MODE_AWAY


def is_home(config: Config) -> bool:
    return get_presence(config) == MODE_HOME


def presence_label(config: Config) -> str:
    return _LABELS[get_presence(config)]


def toggle_presence(config: Config) -> PresenceMode:
    nxt = MODE_HOME if is_away(config) else MODE_AWAY
    return set_presence(config, nxt)
