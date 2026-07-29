"""Одобрение промпта Comfy через Telegram и чат Вью."""

from __future__ import annotations

import re
from typing import Tuple

from ...config import Config
from ..telegram.client import TelegramClient, TelegramError
from ..telegram import settings as tg_settings
from .prompts import mocap_take_count

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
_REDRAFT_COMPLAINT_RE = re.compile(
    r"(?:"
    r"другой\s+промпт?|"
    r"не\s+тот\s+промпт?|"
    r"не\s+это(?:т)?\s+промпт?|"
    r"не\s+то|"
    r"не\s+хотел|"
    r"wrong\s+prompt|"
    r"another\s+prompt|"
    r"not\s+this\s+one|"
    r"переснять|"
    r"другой\s+кадр|"
    r"смени(?:ть)?\s+промпт|"
    r"другой\s+shot"
    r")",
    re.IGNORECASE,
)
_REJECT_PREFIX_RE = re.compile(r"^\s*нет\b", re.IGNORECASE)
_SLUG_ONLY_RE = re.compile(r"^[\w-]+$")


def _looks_like_mocap_action(text: str) -> bool:
    """Текст похож на EN-описание движения или slug — не на «нет, не тот промпт»."""
    raw = (text or "").strip()
    if len(raw) < 8:
        return False
    if _REDRAFT_COMPLAINT_RE.search(raw) or _REJECT_PREFIX_RE.match(raw):
        return False
    latin = len(re.findall(r"[A-Za-z]", raw))
    if latin >= 18:
        return True
    slug = raw.lower().replace("-", "_")
    if _SLUG_ONLY_RE.match(raw) and "_" in slug:
        return True
    return False


def _is_redraft_request(text: str) -> bool:
    raw = (text or "").strip()
    if not raw:
        return False
    if _REDRAFT_COMPLAINT_RE.search(raw):
        return True
    if _REJECT_PREFIX_RE.match(raw) and not _REJECT_RE.match(raw):
        return True
    return False


def send_prompt_for_approval(config: Config, action: str, draft_text: str) -> Tuple[bool, str]:
    """Отправить Дена в Telegram текст на одобрение."""
    body = (
        "🎬 Comfy → Cascadeur MoCap\n\n"
        f"{draft_text.strip()}\n\n"
        "Ответь:\n"
        f"• ок — дальше выбор LoRA, потом {mocap_take_count()} дублей ¾\n"
        "• нет / другой кадр — предложу следующий по графу\n"
        "• правки: sit_down — slug или короткий EN (без moaning/sweat/jiggle)\n"
        "• промпт comfy — показать Wan POSITIVE/NEGATIVE и поправить\n"
        "• промпт+: … или вставь блок --- POSITIVE --- / NEGATIVE / ДЕЙСТВИЕ\n"
        "• стоп — отменить этот промпт"
    )
    if not tg_settings.enabled(config):
        return False, "Telegram выключен — одобри в чате Вью: ок / стоп / правки: …"
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
    """Вернуть (decision, action_or_msg).

    decision: approve | reject | edit | redraft | unknown
    """
    raw = (text or "").strip()
    if not raw:
        return "unknown", ""
    if _APPROVE_RE.match(raw):
        return "approve", current_action
    if _REJECT_RE.match(raw):
        return "reject", "Отменено."
    if _EDIT_PREFIX_RE.match(raw):
        edited = _EDIT_PREFIX_RE.sub("", raw).strip()
        if not edited:
            return "unknown", ""
        if _is_redraft_request(edited):
            return "redraft", edited
        return "edit", edited
    if _is_redraft_request(raw):
        return "redraft", raw
    if _looks_like_mocap_action(raw):
        return "edit", raw
    return "unknown", raw


def try_handle_comfy_telegram(
    config: Config,
    text: str,
    *,
    for_telegram: bool = False,
) -> Tuple[bool, str]:
    """Если lab/comfy ждёт промпт, выбор клипа или сцены — обработать ответ."""
    from .prompt_edit import try_handle_comfy_prompt_chat

    handled, out = try_handle_comfy_prompt_chat(config, text, for_telegram=for_telegram)
    if handled:
        return True, out

    from ...lab.comfy_pipeline import (
        COMFY_TOPIC,
        apply_clip_pick_decision,
        apply_lora_pick_decision,
        apply_prompt_decision,
    )
    from ...lab.session import load_session
    from .clip_review import parse_clip_pick_reply
    from .lora import load_index, parse_lora_pick_reply
    from .scene_choice import apply_scene_choice, is_paused_for_scene_choice, parse_scene_choice_reply

    if is_paused_for_scene_choice(config):
        decision, payload = parse_scene_choice_reply(text)
        if decision == "unknown":
            return True, apply_scene_choice(config, "unknown", {})
        return True, apply_scene_choice(config, decision, payload)

    session = load_session(config, COMFY_TOPIC)
    if session is None:
        return False, ""

    if session.status == "awaiting_clip_pick":
        parsed = parse_clip_pick_reply(text)
        if parsed is None:
            return True, (
                "Не поняла выбор клипа.\n"
                "Напиши: лучший: front | лучший: side 5 | отклонить все"
            )
        decision, payload = parsed
        return True, apply_clip_pick_decision(config, session, decision, payload)

    if session.status == "awaiting_lora_pick":
        entries = load_index(config)
        max_idx = max((e.index for e in entries), default=0)
        indices = parse_lora_pick_reply(text, max_index=max_idx)
        if indices is None:
            return True, (
                "Не поняла выбор LoRA.\n"
                "Напиши: lora: 1 | lora: 1,3 | lora: all | lora: none"
            )
        return True, apply_lora_pick_decision(config, session, indices)

    if session.status != "awaiting_prompt":
        return False, ""
    action = str((session.meta or {}).get("action") or "").strip()
    decision, payload = parse_approval_reply(text, current_action=action)
    if decision == "unknown":
        return True, (
            "Не поняла ответ по Comfy-промпту.\n"
            "Напиши: ок | нет / другой кадр | правки: sit_down | стоп"
        )
    return True, apply_prompt_decision(config, session, decision, payload)
