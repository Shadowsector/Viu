"""Telegram-бот Вью: вопросы Дену, ответы с телефона, уведомления."""

from __future__ import annotations

from typing import Callable, Optional

from ...config import Config
from .notifier import TelegramNotifier


def try_start_notifier(
    config: Config,
    *,
    on_reply: Callable[[str], None],
    get_status: Callable[[], str],
) -> Optional[TelegramNotifier]:
    """Запускает polling, если задан VIU_TELEGRAM_TOKEN."""
    notifier = TelegramNotifier(config, on_reply=on_reply, get_status=get_status)
    if not notifier.enabled:
        return None
    notifier.start()
    return notifier


__all__ = ["TelegramNotifier", "try_start_notifier"]
