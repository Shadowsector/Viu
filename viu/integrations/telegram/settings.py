"""Настройки Telegram: токен из env; чат — только владелец (Ден)."""

from __future__ import annotations

import os
from typing import Optional

from ...config import Config
from ...runtime_settings import get as rt_get, set_value as rt_set

# Жёсткий дефолт: личный Telegram Дена. Чужие /start и сообщения игнорируются.
DEFAULT_OWNER_IDS = frozenset({103833998})


def token(config: Config) -> str:
    del config
    return (
        os.environ.get("VIU_TELEGRAM_TOKEN", "").strip()
        or os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    )


def enabled(config: Config) -> bool:
    if not token(config):
        return False
    flag = os.environ.get("VIU_TELEGRAM_ENABLED", "1").strip().lower()
    return flag not in ("0", "false", "no", "off")


def owner_ids(config: Config | None = None) -> frozenset[int]:
    """Кто может писать боту. Env VIU_TELEGRAM_OWNER_IDS=1,2 переопределяет дефолт."""
    del config
    raw = (os.environ.get("VIU_TELEGRAM_OWNER_IDS") or "").strip()
    if not raw:
        return DEFAULT_OWNER_IDS
    out: set[int] = set()
    for part in raw.replace(";", ",").split(","):
        part = part.strip()
        if not part:
            continue
        try:
            out.add(int(part))
        except ValueError:
            continue
    return frozenset(out) if out else DEFAULT_OWNER_IDS


def is_owner_sender(
    config: Config,
    *,
    chat_id: int,
    user_id: Optional[int] = None,
) -> bool:
    """Если есть from.id — только он. Иначе fallback на chat_id (личка)."""
    owners = owner_ids(config)
    if user_id is not None:
        return int(user_id) in owners
    return int(chat_id) in owners


def chat_id(config: Config) -> Optional[int]:
    """Привязанный чат для исходящих. Только owner; иначе дефолт = единственный owner."""
    owners = owner_ids(config)
    raw = os.environ.get("VIU_TELEGRAM_CHAT_ID", "").strip()
    if raw:
        try:
            cid = int(raw)
        except ValueError:
            cid = None
        if cid is not None and cid in owners:
            return cid
        # Чужой chat_id в env — не используем.
    stored = rt_get(config, "telegram_chat_id")
    if stored is not None:
        try:
            cid = int(stored)
        except (TypeError, ValueError):
            cid = None
        if cid is not None and cid in owners:
            return cid
    if len(owners) == 1:
        return next(iter(owners))
    return None


def set_chat_id(config: Config, chat_id: int) -> None:
    """Сохранить chat_id только если это владелец."""
    cid = int(chat_id)
    if cid not in owner_ids(config):
        return
    rt_set(config, "telegram_chat_id", cid)


def notify_errors(config: Config) -> bool:
    del config
    flag = os.environ.get("VIU_TELEGRAM_NOTIFY_ERRORS", "1").strip().lower()
    return flag not in ("0", "false", "no", "off")


def notify_done(config: Config) -> bool:
    del config
    flag = os.environ.get("VIU_TELEGRAM_NOTIFY_DONE", "1").strip().lower()
    return flag not in ("0", "false", "no", "off")
