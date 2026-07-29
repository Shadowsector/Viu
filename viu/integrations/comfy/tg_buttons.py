"""Единая панель Comfy в Telegram: Снять / Промпт / LoRA — кнопки живые, пока ждём."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Tuple

# callback_data ≤ 64 байт
CB_SHOOT = "c:ok"
CB_OK = CB_SHOOT  # alias
CB_STOP = "c:stop"
CB_REDRAFT = "c:redraft"
CB_PROMPT = "c:prompt"
CB_LORA_MENU = "c:lora_menu"
CB_PANEL = "c:panel"
CB_LORA_NONE = "c:lora:none"
CB_LORA_LAST = "c:lora:last"
CB_LORA_N = "c:lora:{n}"
CB_CLIP = "c:clip:{angle}"


def _btn(text: str, data: str) -> Dict[str, str]:
    return {"text": text, "callback_data": data[:64]}


def inline_keyboard(rows: Sequence[Sequence[Tuple[str, str]]]) -> Dict[str, Any]:
    return {
        "inline_keyboard": [
            [_btn(label, data) for label, data in row] for row in rows if row
        ]
    }


def control_panel_keyboard() -> Dict[str, Any]:
    """Главная панель до генерации."""
    return inline_keyboard(
        [
            [("✅ Снять", CB_SHOOT), ("✏️ Промпт", CB_PROMPT)],
            [("🎛 LoRA", CB_LORA_MENU), ("⏹ Стоп", CB_STOP)],
        ]
    )


def prompt_approval_keyboard() -> Dict[str, Any]:
    """Alias для старых вызовов."""
    return control_panel_keyboard()


def lora_pick_keyboard(
    *,
    indices: Optional[List[int]] = None,
    last: Optional[List[int]] = None,
    max_buttons: int = 8,
) -> Dict[str, Any]:
    rows: List[List[Tuple[str, str]]] = []
    idxs = [int(i) for i in (indices or []) if int(i) > 0][:max_buttons]
    row: List[Tuple[str, str]] = []
    for n in idxs:
        row.append((str(n), CB_LORA_N.format(n=n)))
        if len(row) >= 4:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    tail: List[Tuple[str, str]] = [("🚫 Без LoRA", CB_LORA_NONE)]
    if last:
        label = "↩ Прошлый (" + ",".join(str(i) for i in last[:4]) + ")"
        if len(label) > 28:
            label = "↩ Прошлый"
        tail.append((label, CB_LORA_LAST))
    rows.append(tail)
    rows.append([("◀️ Назад", CB_PANEL)])
    return inline_keyboard(rows)


def clip_pick_keyboard(angles: Sequence[str]) -> Dict[str, Any]:
    row: List[Tuple[str, str]] = []
    rows: List[List[Tuple[str, str]]] = []
    for a in angles:
        label = str(a).replace("take_", "").upper()
        row.append((f"▶ {label}", CB_CLIP.format(angle=a)))
        if len(row) >= 3:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([("🗑 Отклонить все", "c:clip:reject")])
    return inline_keyboard(rows)


def callback_to_chat_text(
    data: str,
    *,
    last_lora: Optional[List[int]] = None,
) -> Optional[str]:
    """callback_data → текст для обработчиков Comfy."""
    raw = (data or "").strip()
    if not raw:
        return None
    if raw in (CB_SHOOT, "c:ok"):
        return "ок"
    if raw == CB_STOP:
        return "стоп"
    if raw == CB_REDRAFT:
        return "другой кадр"
    if raw == CB_PROMPT:
        return "промпт comfy"
    if raw == CB_LORA_MENU:
        return "lora: меню"
    if raw == CB_PANEL:
        return "панель comfy"
    if raw == CB_LORA_NONE:
        return "lora: none"
    if raw == CB_LORA_LAST:
        if last_lora:
            return "lora: " + ",".join(str(i) for i in last_lora)
        return "lora: none"
    if raw.startswith("c:lora:"):
        rest = raw.split(":", 2)[-1].strip()
        if rest.isdigit():
            return f"lora: {rest}"
    if raw == "c:clip:reject":
        return "отклонить все"
    if raw.startswith("c:clip:"):
        angle = raw.split(":", 2)[-1].strip()
        if angle:
            return f"лучший: {angle}"
    return None
