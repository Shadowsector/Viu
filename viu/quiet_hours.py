"""Тихие часы — не будить Дена ночью (heartbeat, проактивные пуши)."""

from __future__ import annotations

import os
from datetime import datetime
from typing import Tuple

from .config import Config
from .runtime_settings import get_quiet_hours


def _parse_hours(raw: str) -> Tuple[int, int]:
    """``0-7`` → (0, 7): с start включительно до end исключительно."""
    raw = (raw or "0-7").strip()
    if "-" in raw:
        a, b = raw.split("-", 1)
        try:
            return int(a.strip()) % 24, int(b.strip()) % 24
        except ValueError:
            pass
    return 0, 7


def quiet_hours_bounds(config: Config) -> Tuple[int, int]:
    stored = get_quiet_hours(config)
    if stored:
        return _parse_hours(stored)
    return _parse_hours(os.environ.get("VIU_QUIET_HOURS", "0-7"))


def in_quiet_hours(config: Config, when: datetime | None = None) -> bool:
    """True если сейчас тихие часы (локальное время ПК)."""
    start, end = quiet_hours_bounds(config)
    if start == end:
        return False
    now = when or datetime.now()
    hour = now.hour
    if start < end:
        return start <= hour < end
    # через полночь, напр. 22–7
    return hour >= start or hour < end
