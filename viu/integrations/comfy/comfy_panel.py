"""Панель управления Comfy до генерации: сцена + LoRA, ждём «Снять»."""

from __future__ import annotations

from typing import List, Tuple

from ...config import Config
from ...lab.session import LabSession, save_session
from ..telegram import settings as tg_settings
from ..telegram.client import TelegramClient, TelegramError
from .prompts import mocap_take_count
from .tg_buttons import control_panel_keyboard, lora_pick_keyboard


def _lora_summary(session: LabSession) -> str:
    meta = session.meta or {}
    if "setup_lora_indices" in meta:
        idxs = [int(x) for x in (meta.get("setup_lora_indices") or [])]
        if not idxs:
            return "без LoRA (чистый Wan)"
        return "№ " + ",".join(str(i) for i in idxs)
    selected = meta.get("selected_loras") or []
    if selected:
        names = []
        for item in selected[:4]:
            if isinstance(item, dict):
                names.append(str(item.get("file") or "?"))
            else:
                names.append(str(item))
        return ", ".join(names) if names else "без LoRA"
    last = [int(x) for x in (meta.get("lora_last_pick") or []) if str(x).isdigit()]
    if last:
        return "прошлый № " + ",".join(str(i) for i in last) + " (по умолчанию)"
    return "без LoRA (по умолчанию)"


def format_control_panel(session: LabSession) -> str:
    action = str(session.meta.get("approved_action") or session.meta.get("action") or "—")
    if len(action) > 160:
        action = action[:157] + "…"
    slug = str(session.meta.get("catalog_slug") or "").strip()
    wan = str(session.meta.get("wan_positive") or "").strip()
    draft = str(session.meta.get("draft") or "").strip()
    lines = [
        "🎬 Comfy — панель съёмки",
        "",
        f"Сцена: {action}",
    ]
    if slug:
        lines.append(f"Slug: `{slug}`")
    lines.append(f"LoRA: {_lora_summary(session)}")
    preview = wan or draft
    if preview:
        # Короткий кусок промпта — полный через «Промпт»
        snippet = preview.replace("\n", " ")
        if len(snippet) > 220:
            snippet = snippet[:217] + "…"
        lines.extend(["", f"Промпт: {snippet}"])
    lines.extend(
        [
            "",
            f"Дублей: {mocap_take_count()} × ¾",
            "",
            "① LoRA / Промпт — настрой",
            "② «Снять» — только тогда очередь Comfy",
        ]
    )
    return "\n".join(lines)


def send_control_panel(config: Config, session: LabSession) -> Tuple[bool, str]:
    body = format_control_panel(session)
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


def send_lora_menu(config: Config, session: LabSession) -> Tuple[bool, str]:
    from .lora import format_lora_pick_message, format_lora_pick_telegram, scan_loras

    entries = scan_loras(config)
    if not entries:
        return True, "LoRA на диске нет — будет чистый Wan. Жми «Снять»."
    last = [int(x) for x in (session.meta.get("lora_last_pick") or []) if str(x).isdigit()]
    if not tg_settings.enabled(config):
        return True, format_lora_pick_message(entries)
    token = tg_settings.token(config)
    chat_id = tg_settings.chat_id(config)
    if not token or chat_id is None:
        return False, "Telegram не привязан."
    try:
        client = TelegramClient(token)
        parts = format_lora_pick_telegram(entries)
        idxs = [e.index for e in entries[:12]]
        kb = lora_pick_keyboard(indices=idxs, last=last or None)
        for i, part in enumerate(parts):
            head = "🎛 LoRA — выбери номер (генерация ещё не стартует)"
            if len(parts) > 1:
                head += f" ({i + 1}/{len(parts)})"
            markup = kb if i == len(parts) - 1 else None
            client.send_message(chat_id, head + "\n\n" + part, reply_markup=markup)
        return True, "Выбери LoRA, потом «Назад» / «Снять»."
    except TelegramError as exc:
        return False, f"Telegram ошибка: {exc}"


def set_setup_lora_indices(session: LabSession, indices: List[int]) -> None:
    session.meta["setup_lora_indices"] = [int(i) for i in indices]
    session.meta.pop("lora_pick_done", None)


def apply_setup_and_start(
    config: Config,
    session: LabSession,
    *,
    jump_to_generate: bool = True,
) -> str:
    """«Снять»: зафиксировать LoRA + approve и пойти в генерацию.

    jump_to_generate=True — снаружи (кнопка TG/чат): сразу шаг generate.
    False — изнутри step_request_approval (away auto): step +=1 в pipeline
    пройдёт LoRA no-op → generate.
    """
    from .lora import scan_loras, spec_to_dict, specs_from_indices

    action = str(session.meta.get("action") or session.meta.get("approved_action") or "")
    if "setup_lora_indices" in (session.meta or {}):
        indices = [int(x) for x in session.meta.get("setup_lora_indices") or []]
    else:
        indices = [
            int(x) for x in (session.meta.get("lora_last_pick") or []) if str(x).isdigit()
        ]

    scan_loras(config)
    specs = specs_from_indices(config, indices) if indices else []
    session.meta["selected_loras"] = [spec_to_dict(s) for s in specs]
    session.meta["lora_last_pick"] = list(indices)
    session.meta["lora_pick_done"] = True
    session.meta["approved"] = True
    session.meta["approved_action"] = action
    session.meta.pop("shoot_intent", None)
    session.meta["auto_approved_shoot"] = True
    session.status = "running"
    if jump_to_generate and session.step < 5:
        session.step = 5
    save_session(config, session)

    if not specs:
        lora_msg = "Без LoRA — чистый Wan."
    else:
        names = ", ".join(f"{s.file}@{s.strength}" for s in specs)
        lora_msg = f"LoRA: {names}."
    return (
        f"Снимаю («{action[:80]}»).\n{lora_msg}\n"
        f"Ставлю {mocap_take_count()} дублей в очередь Comfy…"
    )
