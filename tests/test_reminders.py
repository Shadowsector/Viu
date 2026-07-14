"""Отложенные напоминания после N сообщений пользователя."""

from __future__ import annotations

from pathlib import Path

from viu.config import Config
from viu.reminders import list_pending, on_user_message, schedule


def _cfg(tmp_path: Path) -> Config:
    data = tmp_path / ".viu"
    data.mkdir()
    return Config(root=tmp_path, data_dir=data)


def test_schedule_and_fire(tmp_path):
    cfg = _cfg(tmp_path)
    ok, msg = schedule(cfg, "проверь сарай", after_user_messages=3, tag="anim_barn")
    assert ok
    assert "3" in msg or "сообщен" in msg.lower()
    pending = list_pending(cfg)
    assert len(pending) == 1
    assert pending[0]["tag"] == "anim_barn"

    assert on_user_message(cfg) == []
    assert on_user_message(cfg) == []
    fired = on_user_message(cfg)
    assert fired == ["проверь сарай"]
    assert list_pending(cfg) == []


def test_same_tag_updates(tmp_path):
    cfg = _cfg(tmp_path)
    schedule(cfg, "раз", after_user_messages=10, tag="anim_barn")
    ok, msg = schedule(cfg, "два", after_user_messages=5, tag="anim_barn")
    assert ok
    assert "Обновила" in msg or "два" in (list_pending(cfg)[0]["text"])
    assert list_pending(cfg)[0]["text"] == "два"
    assert list_pending(cfg)[0]["after_n"] == 5
