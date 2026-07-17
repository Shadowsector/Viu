"""Настройки Telegram: токен из env, chat_id — env или runtime.json."""

from __future__ import annotations

import os
from typing import Optional

from ...config import Config
from ...runtime_settings import get as rt_get, set_value as rt_set


def token(config: Config) -> str:
    return (
        os.environ.get("VIU_TELEGRAM_TOKEN", "").strip()
        or os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    )


def enabled(config: Config) -> bool:
    if not token(config):
        return False
    flag = os.environ.get("VIU_TELEGRAM_ENABLED", "1").strip().lower()
    return flag not in ("0", "false", "no", "off")


def chat_id(config: Config) -> Optional[int]:
    raw = os.environ.get("VIU_TELEGRAM_CHAT_ID", "").strip()
    if raw:
        try:
            return int(raw)
        except ValueError:
            return None
    stored = rt_get(config, "telegram_chat_id")
    if stored is None:
        return None
    try:
        return int(stored)
    except (TypeError, ValueError):
        return None


def set_chat_id(config: Config, chat_id: int) -> None:
    rt_set(config, "telegram_chat_id", int(chat_id))


def notify_errors(config: Config) -> bool:
    flag = os.environ.get("VIU_TELEGRAM_NOTIFY_ERRORS", "1").strip().lower()
    return flag not in ("0", "false", "no", "off")


def notify_done(config: Config) -> bool:
    flag = os.environ.get("VIU_TELEGRAM_NOTIFY_DONE", "1").strip().lower()
    return flag not in ("0", "false", "no", "off")
