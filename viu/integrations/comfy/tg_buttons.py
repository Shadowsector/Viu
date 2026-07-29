"""Inline-кнопки Telegram для Comfy (промпт / LoRA) — без длинных команд."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Tuple

# callback_data ≤ 64 байт
CB_OK = "c:ok"
CB_STOP = "c:stop"
CB_REDRAFT = "c:redraft"
CB_PROMPT = "c:prompt"
CB_LORA_NONE = "c:lora:none"
CB_LORA_LAST = "c:lora:last"
CB_LORA_N = "c:lora:{n}"  # format


def _btn(text: str, data: str) -> Dict[str, str]:
    return {"text": text, "callback_data": data[:64]}


def inline_keyboard(rows: Sequence[Sequence[Tuple[str, str]]]) -> Dict[str, Any]:
    return {
        "inline_keyboard": [
            [_btn(label, data) for label, data in row] for row in rows if row
        ]
    }


def prompt_approval_keyboard() -> Dict[str, Any]:
    return inline_keyboard(
        [
            [("✅ Снимать", CB_OK), ("✏️ Промпт", CB_PROMPT)],
            [("🔄 Другой кадр", CB_REDRAFT), ("⏹ Стоп", CB_STOP)],
        ]
    )


def lora_pick_keyboard(
    *,
    indices: Optional[List[int]] = None,
    last: Optional[List[int]] = None,
    max_buttons: int = 8,
) -> Dict[str, Any]:
    """Кнопки LoRA: номера + none + прошлый выбор."""
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
    return inline_keyboard(rows)


def callback_to_chat_text(
    data: str,
    *,
    last_lora: Optional[List[int]] = None,
) -> Optional[str]:
    """callback_data → текст, который уже понимает try_handle_comfy_telegram."""
    raw = (data or "").strip()
    if not raw:
        return None
    if raw == CB_OK:
        return "ок"
    if raw == CB_STOP:
        return "стоп"
    if raw == CB_REDRAFT:
        return "другой кадр"
    if raw == CB_PROMPT:
        return "промпт comfy"
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
    return None
