"""Одобрение промпта Comfy через Telegram."""

from __future__ import annotations

import re
from typing import Optional, Tuple

from ...config import Config
from ..telegram.client import TelegramClient, TelegramError
from ..telegram import settings as tg_settings
from .prompts import draft_bundle, mocap_prompt

_APPROVE_RE = re.compile(
    r"^\s*(?:ок|ok|да|yes|approve|👍|✅|принято|го)\s*[.!…]?\s*$",
    re.IGNORECASE,
)
_REJECT_RE = re.compile(
    r"^\s*(?:нет|no|стоп|stop|отмена|cancel|reject|❌)\s*[.!…]?\s*$",
    re.IGNORECASE,
)
_EDIT_PREFIX_RE = re.compile(
    r"^\s*(?:правк[аи]|edit|промпт)\s*[:\-–]\s*",
    re.IGNORECASE,
)


def send_prompt_for_approval(config: Config, action: str, draft_text: str) -> Tuple[bool, str]:
    """Отправить Дена в Telegram текст на одобрение."""
    body = (
        "🎬 Comfy → Cascadeur MoCap\n\n"
        f"{draft_text.strip()}\n\n"
        "Ответь:\n"
        "• ок — генерирую 3 видео (сбоку / ¾ / анфас)\n"
        "• правки: <новый текст действия или полный промпт>\n"
        "• стоп — отменить этот промпт"
    )
    if not tg_settings.enabled(config):
        return False, "Telegram выключен — одобри в чате Вью: ok / стоп / правки: …"
    token = tg_settings.token(config)
    chat_id = tg_settings.chat_id(config)
    if not token or chat_id is None:
        return False, "Telegram не привязан — одобри в чате Вью."
    try:
        TelegramClient(token).send_message(chat_id, body)
        return True, "Промпт ушёл в Telegram — жду ок / правки / стоп."
    except TelegramError as exc:
        return False, f"Telegram ошибка: {exc}"


def parse_approval_reply(text: str, *, current_action: str) -> Tuple[str, str]:
    """Вернуть (decision, action_or_msg). decision: approve|reject|edit|unknown."""
    raw = (text or "").strip()
    if not raw:
        return "unknown", ""
    if _APPROVE_RE.match(raw):
        return "approve", current_action
    if _REJECT_RE.match(raw):
        return "reject", "Отменено."
    if _EDIT_PREFIX_RE.match(raw):
        edited = _EDIT_PREFIX_RE.sub("", raw).strip()
        if edited:
            return "edit", edited
        return "unknown", ""
    # Любой другой непустой текст = правка действия/промпта
    if len(raw) >= 8:
        return "edit", raw
    return "unknown", raw


def try_handle_comfy_telegram(
    config: Config,
    text: str,
) -> Tuple[bool, str]:
    """Если lab/comfy ждёт промпт — обработать ответ. (handled, message)."""
    from ...lab.comfy_pipeline import COMFY_TOPIC, apply_prompt_decision
    from ...lab.session import load_session

    session = load_session(config, COMFY_TOPIC)
    if session is None or session.status != "awaiting_prompt":
        return False, ""
    action = str((session.meta or {}).get("action") or "").strip()
    decision, payload = parse_approval_reply(text, current_action=action)
    if decision == "unknown":
        return True, (
            "Не поняла ответ по Comfy-промпту.\n"
            "Напиши: ок | стоп | правки: <текст>"
        )
    return True, apply_prompt_decision(config, session, decision, payload)
