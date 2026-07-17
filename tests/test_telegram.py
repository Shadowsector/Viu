"""Тесты Telegram-интеграции."""

import json
from unittest.mock import MagicMock

import pytest

from viu.config import Config
from viu.integrations.telegram.client import TelegramClient, TelegramError
from viu.integrations.telegram.notifier import TelegramNotifier
from viu.integrations.telegram import settings as tg_settings


def _config(tmp_path, **env):
    import os

    for k, v in env.items():
        os.environ[k] = v
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


def test_client_send_message(monkeypatch):
    captured = {}

    def fake_urlopen(req, timeout=0):
        captured["url"] = req.full_url
        captured["data"] = req.data
        resp = MagicMock()
        resp.read.return_value = json.dumps({"ok": True, "result": {"message_id": 1}}).encode()
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


def test_notifier_start_binds_chat_on_start(tmp_path, monkeypatch):
    monkeypatch.setenv("VIU_TELEGRAM_TOKEN", "123:TOKEN")
    cfg = _config(tmp_path)
    replies = []

    def fake_get_updates(self, *, offset=0, timeout=25):
        if offset == 0:
            return [
                {
                    "update_id": 1,
                    "message": {
                        "chat": {"id": 4242},
                        "text": "/start",
                    },
                }
            ]
        return []

    sent = []

    def fake_send(self, chat_id, text, **kwargs):
        sent.append((chat_id, text))
        return {"message_id": 1}

    monkeypatch.setattr(TelegramClient, "get_updates", fake_get_updates)
    monkeypatch.setattr(TelegramClient, "send_message", fake_send)

    notifier = TelegramNotifier(cfg, on_reply=replies.append, get_status=lambda: "ok")
    notifier._poll_loop_once = lambda: None  # type: ignore[method-assign]
    notifier._handle_update(
        {
            "update_id": 1,
            "message": {"chat": {"id": 4242}, "text": "/start"},
        }
    )
    assert tg_settings.chat_id(cfg) == 4242
    assert sent
    assert "Chat ID" in sent[0][1]


def test_notifier_forwards_text_reply(tmp_path, monkeypatch):
    monkeypatch.setenv("VIU_TELEGRAM_TOKEN", "123:TOKEN")
    cfg = _config(tmp_path)
    tg_settings.set_chat_id(cfg, 4242)
    got = []
    notifier = TelegramNotifier(cfg, on_reply=got.append, get_status=lambda: "ok")
    notifier._handle_update(
        {
            "update_id": 2,
            "message": {"chat": {"id": 4242}, "text": "да, делай оверлей"},
        }
    )
    assert got == ["да, делай оверлей"]


def test_notifier_ignores_foreign_chat(tmp_path, monkeypatch):
    monkeypatch.setenv("VIU_TELEGRAM_TOKEN", "123:TOKEN")
    cfg = _config(tmp_path)
    tg_settings.set_chat_id(cfg, 4242)
    got = []
    notifier = TelegramNotifier(cfg, on_reply=got.append, get_status=lambda: "ok")
    notifier._handle_update(
        {
            "update_id": 3,
            "message": {"chat": {"id": 9999}, "text": "hack"},
        }
    )
    assert got == []
