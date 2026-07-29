"""Telegram inline-кнопки Comfy."""

from viu.integrations.comfy.tg_buttons import (
    CB_OK,
    CB_PROMPT,
    callback_to_chat_text,
    lora_pick_keyboard,
    prompt_approval_keyboard,
)


def test_prompt_keyboard_shape():
    kb = prompt_approval_keyboard()
    rows = kb["inline_keyboard"]
    assert len(rows) == 2
    labels = [b["text"] for row in rows for b in row]
    assert any("Снимать" in t for t in labels)
    assert any("Промпт" in t for t in labels)
    assert all(len(b["callback_data"].encode("utf-8")) <= 64 for row in rows for b in row)


def test_lora_keyboard_and_callbacks():
    kb = lora_pick_keyboard(indices=[1, 2, 3, 5], last=[2])
    flat = [b for row in kb["inline_keyboard"] for b in row]
    assert any(b["callback_data"] == "c:lora:1" for b in flat)
    assert any(b["callback_data"] == "c:lora:none" for b in flat)
    assert callback_to_chat_text(CB_OK) == "ок"
    assert callback_to_chat_text(CB_PROMPT) == "промпт comfy"
    assert callback_to_chat_text("c:lora:3") == "lora: 3"
    assert callback_to_chat_text("c:lora:none") == "lora: none"
    assert callback_to_chat_text("c:lora:last", last_lora=[2, 5]) == "lora: 2,5"
    assert callback_to_chat_text("c:unknown") is None


def test_send_prompt_attaches_keyboard(monkeypatch):
    from viu.config import Config
    from viu.integrations.comfy import approval

    calls = {}

    class FakeClient:
        def __init__(self, token):
            calls["token"] = token

        def send_message(self, chat_id, text, *, reply_markup=None, **kw):
            calls["chat_id"] = chat_id
            calls["text"] = text
            calls["reply_markup"] = reply_markup
            return {}

    monkeypatch.setattr(approval.tg_settings, "enabled", lambda cfg: True)
    monkeypatch.setattr(approval.tg_settings, "token", lambda cfg: "tok")
    monkeypatch.setattr(approval.tg_settings, "chat_id", lambda cfg: 103833998)
    monkeypatch.setattr(approval, "TelegramClient", FakeClient)

    cfg = Config(root="/tmp/viu", data_dir="/tmp/viu-data")
    ok, msg = approval.send_prompt_for_approval(cfg, "idle stand", "draft line")
    assert ok
    assert calls["reply_markup"] is not None
    assert "inline_keyboard" in calls["reply_markup"]
    assert "кнопк" in msg.lower() or "Снимать" in msg or "Telegram" in msg
