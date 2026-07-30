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
    # «Нет, другой промпт» — коротко. «Нет, солнце, придумай тварей…» — разговор.
    if _REJECT_PREFIX_RE.match(raw) and not _REJECT_RE.match(raw):
        if len(raw) > 72:
            return False
        return True
    return False


def send_prompt_for_approval(config: Config, action: str, draft_text: str) -> Tuple[bool, str]:
    """Отправить Дена в Telegram панель съёмки (Снять / Промпт / LoRA)."""
    from .tg_buttons import control_panel_keyboard

    draft = (draft_text or "").strip()
    if len(draft) > 2200:
        draft = draft[:2197] + "…"
    scene = (action or "").strip()
    if len(scene) > 160:
        scene = scene[:157] + "…"
    body = (
        "🎬 Comfy — панель съёмки\n\n"
        f"Сцена: {scene or '—'}\n"
        f"Дублей: {mocap_take_count()} × ¾\n\n"
        f"{draft}\n\n"
        "① Промпт / LoRA — настрой\n"
        "② «Снять» — только тогда очередь"
    )
    if not tg_settings.enabled(config):
        return False, "Telegram выключен — в чате: ок (=снять) / стоп / lora: …"
    token = tg_settings.token(config)
    chat_id = tg_settings.chat_id(config)
    if not token or chat_id is None:
        return False, "Telegram не привязан — в чате: ок / стоп."
    try:
        TelegramClient(token).send_message(
            chat_id,
            body,
            reply_markup=control_panel_keyboard(),
        )
        return True, "Панель в Telegram — жду «Снять»."
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
    """Панель съёмки / клип / сцена — ответ Дена из Telegram или чата."""
    from .prompt_edit import try_handle_comfy_prompt_chat

    raw = (text or "").strip()

    # Сначала спецкоманды панели (до prompt_edit, чтобы «промпт comfy» из кнопки ок).
    from ...lab.comfy_pipeline import (
        COMFY_TOPIC,
        apply_clip_pick_decision,
        apply_prompt_decision,
    )
    from ...lab.session import load_session, save_session
    from .clip_review import parse_clip_pick_reply
    from .comfy_panel import (
        send_control_panel,
        send_lora_menu,
        set_setup_lora_indices,
    )
    from .lora import load_index, parse_lora_pick_reply
    from .scene_choice import apply_scene_choice, is_paused_for_scene_choice, parse_scene_choice_reply

    session = load_session(config, COMFY_TOPIC)

    if session is not None and session.status == "awaiting_prompt":
        low = raw.lower()
        if low in ("lora: меню", "лора: меню", "lora menu"):
            ok, msg = send_lora_menu(config, session)
            return True, msg
        if low in ("панель comfy", "панель", "comfy panel"):
            _ok, msg = send_control_panel(config, session)
            return True, msg
        # LoRA с панели: только запомнить выбор, не стартовать
        entries = load_index(config)
        max_idx = max((e.index for e in entries), default=0)
        indices = parse_lora_pick_reply(raw, max_index=max_idx)
        if indices is not None and (
            low.startswith("lora:") or low.startswith("лора:") or re.match(r"^\s*\d", raw)
        ):
            set_setup_lora_indices(session, indices)
            save_session(config, session)
            _ok, panel = send_control_panel(config, session)
            label = "без LoRA" if not indices else "№ " + ",".join(str(i) for i in indices)
            return True, f"LoRA: {label}. Жми «Снять», когда готово.\n{panel}"

    handled, out = try_handle_comfy_prompt_chat(config, text, for_telegram=for_telegram)
    if handled:
        # После показа/правки Wan — вернуть панель, если ещё ждём
        session = load_session(config, COMFY_TOPIC)
        if session is not None and session.status == "awaiting_prompt":
            _ok, panel = send_control_panel(config, session)
            return True, out + "\n\n" + panel
        return True, out

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
                "Напиши: лучший: take_b | или жми кнопку под сообщением."
            )
        decision, payload = parsed
        return True, apply_clip_pick_decision(config, session, decision, payload)

    if session.status == "awaiting_lora_pick":
        entries = load_index(config)
        max_idx = max((e.index for e in entries), default=0)
        indices = parse_lora_pick_reply(text, max_index=max_idx)
        if indices is None:
            return True, "Не поняла LoRA. Жми номер на панели или: lora: 1 | lora: none"
        # Перевести в единую панель
        set_setup_lora_indices(session, indices)
        session.status = "awaiting_prompt"
        save_session(config, session)
        _ok, panel = send_control_panel(config, session)
        return True, f"LoRA записала. Жми «Снять».\n{panel}"

    if session.status != "awaiting_prompt":
        return False, ""
    action = str((session.meta or {}).get("action") or "").strip()
    decision, payload = parse_approval_reply(text, current_action=action)
    if decision == "unknown":
        # Не глотать разговор — пусть reflect / чат решат.
        return False, ""
    return True, apply_prompt_decision(config, session, decision, payload)
