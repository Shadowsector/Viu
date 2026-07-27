"""Тесты Telegram-интеграции."""

import json
from unittest.mock import MagicMock

from viu.config import Config
from viu.integrations.telegram.client import TelegramClient
from viu.integrations.telegram.notifier import TelegramNotifier
from viu.integrations.telegram import settings as tg_settings


def _config(tmp_path, **env):
    import os

    for k, v in env.items():
        os.environ[k] = str(v)
    return Config(root=tmp_path, data_dir=tmp_path / ".viu").ensure_dirs()


def test_settings_enabled_requires_token(tmp_path, monkeypatch):
    monkeypatch.delenv("VIU_TELEGRAM_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    cfg = _config(tmp_path)
    assert not tg_settings.enabled(cfg)


def test_settings_enabled_with_token(tmp_path, monkeypatch):
    monkeypatch.setenv("VIU_TELEGRAM_TOKEN", "123:ABC")
    cfg = _config(tmp_path)
    assert tg_settings.enabled(cfg)


def test_default_owner_is_den():
    assert 103833998 in tg_settings.DEFAULT_OWNER_IDS
    assert tg_settings.owner_ids() == frozenset({103833998})


def test_owner_ids_env_override(monkeypatch):
    monkeypatch.setenv("VIU_TELEGRAM_OWNER_IDS", "111, 222")
    assert tg_settings.owner_ids() == frozenset({111, 222})


def test_chat_id_defaults_to_sole_owner(tmp_path, monkeypatch):
    monkeypatch.delenv("VIU_TELEGRAM_CHAT_ID", raising=False)
    monkeypatch.delenv("VIU_TELEGRAM_OWNER_IDS", raising=False)
    cfg = _config(tmp_path)
    assert tg_settings.chat_id(cfg) == 103833998


def test_set_chat_id_rejects_non_owner(tmp_path, monkeypatch):
    monkeypatch.delenv("VIU_TELEGRAM_OWNER_IDS", raising=False)
    cfg = _config(tmp_path)
    tg_settings.set_chat_id(cfg, 9999)
    assert tg_settings.chat_id(cfg) == 103833998


def test_client_send_message(monkeypatch):
    captured = {}

    def fake_urlopen(req, timeout=0):
        captured["url"] = req.full_url
        captured["data"] = req.data
        resp = MagicMock()
        resp.read.return_value = json.dumps(
            {"ok": True, "result": {"message_id": 1}}
        ).encode()
        resp.__enter__ = lambda s: resp
        resp.__exit__ = MagicMock(return_value=False)
        return resp

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    client = TelegramClient("123:TOKEN")
    client.send_message(999, "привет")
    assert "sendMessage" in captured["url"]
    payload = json.loads(captured["data"].decode())
    assert payload["chat_id"] == 999
    assert payload["text"] == "привет"


def test_client_get_updates_empty_list(monkeypatch):
    def fake_urlopen(req, timeout=0):
        resp = MagicMock()
        resp.read.return_value = json.dumps({"ok": True, "result": []}).encode()
        resp.__enter__ = lambda s: resp
        resp.__exit__ = MagicMock(return_value=False)
        return resp

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    client = TelegramClient("123:TOKEN")
    assert client.get_updates() == []


def test_notifier_start_binds_owner_chat(tmp_path, monkeypatch):
    monkeypatch.setenv("VIU_TELEGRAM_TOKEN", "123:TOKEN")
    monkeypatch.setenv("VIU_TELEGRAM_OWNER_IDS", "4242")
    monkeypatch.delenv("VIU_TELEGRAM_CHAT_ID", raising=False)
    cfg = _config(tmp_path)
    replies = []
    sent = []

    def fake_send(self, chat_id, text, **kwargs):
        sent.append((chat_id, text))
        return {"message_id": 1}

    monkeypatch.setattr(TelegramClient, "send_message", fake_send)

    notifier = TelegramNotifier(cfg, on_reply=replies.append, get_status=lambda: "ok")
    # Сбросим runtime, чтобы chat_id() ещё не был «сохранён», но дефолт = 4242.
    # /start при already-default идёт в «на связи»; проверим привязку через runtime.
    from viu.runtime_settings import set_value as rt_set

    rt_set(cfg, "telegram_chat_id", None)
    # После None chat_id() всё равно вернёт sole owner 4242.
    notifier._handle_update(
        {
            "update_id": 1,
            "message": {
                "chat": {"id": 4242},
                "from": {"id": 4242},
                "text": "/start",
            },
        }
    )
    assert tg_settings.chat_id(cfg) == 4242
    assert sent
    assert "Вью" in sent[0][1] or "Chat ID" in sent[0][1]


def test_notifier_ignores_stranger_start(tmp_path, monkeypatch):
    monkeypatch.setenv("VIU_TELEGRAM_TOKEN", "123:TOKEN")
    monkeypatch.delenv("VIU_TELEGRAM_OWNER_IDS", raising=False)
    cfg = _config(tmp_path)
    got = []
    sent = []

    def fake_send(self, chat_id, text, **kwargs):
        sent.append((chat_id, text))
        return {"message_id": 1}

    monkeypatch.setattr(TelegramClient, "send_message", fake_send)
    notifier = TelegramNotifier(cfg, on_reply=got.append, get_status=lambda: "ok")
    notifier._handle_update(
        {
            "update_id": 1,
            "message": {
                "chat": {"id": 9999},
                "from": {"id": 9999},
                "text": "/start",
            },
        }
    )
    assert got == []
    assert sent == []
    assert tg_settings.chat_id(cfg) == 103833998


def test_notifier_forwards_text_reply(tmp_path, monkeypatch):
    monkeypatch.setenv("VIU_TELEGRAM_TOKEN", "123:TOKEN")
    monkeypatch.setenv("VIU_TELEGRAM_OWNER_IDS", "4242")
    cfg = _config(tmp_path)
    tg_settings.set_chat_id(cfg, 4242)
    got = []
    notifier = TelegramNotifier(cfg, on_reply=got.append, get_status=lambda: "ok")
    notifier._handle_update(
        {
            "update_id": 2,
            "message": {
                "chat": {"id": 4242},
                "from": {"id": 4242},
                "text": "да, делай оверлей",
            },
        }
    )
    assert got == ["да, делай оверлей"]


def test_notifier_ignores_foreign_chat(tmp_path, monkeypatch):
    monkeypatch.setenv("VIU_TELEGRAM_TOKEN", "123:TOKEN")
    monkeypatch.setenv("VIU_TELEGRAM_OWNER_IDS", "4242")
    cfg = _config(tmp_path)
    tg_settings.set_chat_id(cfg, 4242)
    got = []
    notifier = TelegramNotifier(cfg, on_reply=got.append, get_status=lambda: "ok")
    notifier._handle_update(
        {
            "update_id": 3,
            "message": {
                "chat": {"id": 9999},
                "from": {"id": 9999},
                "text": "hack",
            },
        }
    )
    assert got == []


def test_notifier_rejects_spoofed_chat_with_foreign_from(tmp_path, monkeypatch):
    """Чат владельца, но from чужой — не принимаем."""
    monkeypatch.setenv("VIU_TELEGRAM_TOKEN", "123:TOKEN")
    monkeypatch.setenv("VIU_TELEGRAM_OWNER_IDS", "4242")
    cfg = _config(tmp_path)
    got = []
    notifier = TelegramNotifier(cfg, on_reply=got.append, get_status=lambda: "ok")
    notifier._handle_update(
        {
            "update_id": 4,
            "message": {
                "chat": {"id": 4242},
                "from": {"id": 777},
                "text": "не я",
            },
        }
    )
    # chat_id in owners → is_owner_sender True via chat_id!
    # Wait - my is_owner_sender returns True if chat_id in owners OR user_id in owners.
    # So spoofed from in owner's private chat can't happen in Telegram (from is the user).
    # In groups, chat_id is negative, not in owners; user_id must match.
    # For private chat chat_id==user_id always from Telegram's side.
    # The test case chat=4242 from=777 is impossible in real TG for private chats.
    # Tighten: require user_id in owners when user_id is present.
    assert got == []
