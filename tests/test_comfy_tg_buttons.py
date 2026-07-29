"""Telegram inline-кнопки Comfy — панель до генерации."""

from viu.integrations.comfy.tg_buttons import (
    CB_OK,
    CB_PROMPT,
    CB_SHOOT,
    callback_to_chat_text,
    clip_pick_keyboard,
    control_panel_keyboard,
    lora_pick_keyboard,
    prompt_approval_keyboard,
)


def test_control_panel_keyboard_shape():
    kb = control_panel_keyboard()
    rows = kb["inline_keyboard"]
    assert len(rows) == 2
    labels = [b["text"] for row in rows for b in row]
    assert any("Снять" in t for t in labels)
    assert any("Промпт" in t for t in labels)
    assert any("LoRA" in t for t in labels)
    assert all(len(b["callback_data"].encode("utf-8")) <= 64 for row in rows for b in row)
    # alias
    assert prompt_approval_keyboard() == kb
    assert CB_OK == CB_SHOOT


def test_lora_keyboard_and_callbacks():
    kb = lora_pick_keyboard(indices=[1, 2, 3, 5], last=[2])
    flat = [b for row in kb["inline_keyboard"] for b in row]
    assert any(b["callback_data"] == "c:lora:1" for b in flat)
    assert any(b["callback_data"] == "c:lora:none" for b in flat)
    assert any(b["callback_data"] == "c:panel" for b in flat)
    assert callback_to_chat_text(CB_SHOOT) == "ок"
    assert callback_to_chat_text(CB_PROMPT) == "промпт comfy"
    assert callback_to_chat_text("c:lora_menu") == "lora: меню"
    assert callback_to_chat_text("c:panel") == "панель comfy"
    assert callback_to_chat_text("c:lora:3") == "lora: 3"
    assert callback_to_chat_text("c:lora:none") == "lora: none"
    assert callback_to_chat_text("c:lora:last", last_lora=[2, 5]) == "lora: 2,5"
    assert callback_to_chat_text("c:unknown") is None


def test_clip_keyboard():
    kb = clip_pick_keyboard(["take_a", "take_b", "take_c"])
    flat = [b for row in kb["inline_keyboard"] for b in row]
    assert any("c:clip:take_b" == b["callback_data"] for b in flat)
    assert callback_to_chat_text("c:clip:take_b") == "лучший: take_b"
    assert callback_to_chat_text("c:clip:reject") == "отклонить все"


def test_send_control_panel_attaches_keyboard(monkeypatch):
    from viu.config import Config
    from viu.integrations.comfy import comfy_panel
    from viu.lab.session import new_session

    calls = {}

    class FakeClient:
        def __init__(self, token):
            calls["token"] = token

        def send_message(self, chat_id, text, *, reply_markup=None, **kw):
            calls["chat_id"] = chat_id
            calls["text"] = text
            calls["reply_markup"] = reply_markup
            return {}

    monkeypatch.setattr(comfy_panel.tg_settings, "enabled", lambda cfg: True)
    monkeypatch.setattr(comfy_panel.tg_settings, "token", lambda cfg: "tok")
    monkeypatch.setattr(comfy_panel.tg_settings, "chat_id", lambda cfg: 103833998)
    monkeypatch.setattr(comfy_panel, "TelegramClient", FakeClient)

    cfg = Config(root="/tmp/viu", data_dir="/tmp/viu-data")
    session = new_session("comfy")
    session.meta["action"] = "idle stand"
    session.meta["draft"] = "POSITIVE: a woman stands idle"
    ok, msg = comfy_panel.send_control_panel(cfg, session)
    assert ok
    assert calls["reply_markup"] is not None
    assert "inline_keyboard" in calls["reply_markup"]
    assert "Снять" in calls["text"] or "панель" in calls["text"].lower()
    assert "панель" in msg.lower() or "Снять" in msg
