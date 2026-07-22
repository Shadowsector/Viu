"""Политика очереди Comfy перед lab «3 дубля»."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from viu.config import Config
from viu.integrations.comfy.queue_policy import (
    comfy_lab_autoclear_queue,
    comfy_max_pending_for_lab,
    comfy_timeout_each,
    prepare_queue_for_triple,
    should_stop_triple_after_fail,
)


def _cfg(tmp_path) -> Config:
    data = tmp_path / ".viu"
    data.mkdir()
    return Config(
        root=tmp_path,
        data_dir=data,
        library_root=str(tmp_path / "Library"),
        comfy_url="http://127.0.0.1:8188",
    )


def test_comfy_timeout_each_default(monkeypatch):
    monkeypatch.delenv("VIU_COMFY_TIMEOUT_EACH", raising=False)
    assert comfy_timeout_each() == 2400.0


def test_comfy_timeout_each_env(monkeypatch):
    monkeypatch.setenv("VIU_COMFY_TIMEOUT_EACH", "3600")
    assert comfy_timeout_each() == 3600.0


def test_comfy_timeout_each_clamped(monkeypatch):
    monkeypatch.setenv("VIU_COMFY_TIMEOUT_EACH", "100")
    assert comfy_timeout_each() == 300.0
    monkeypatch.setenv("VIU_COMFY_TIMEOUT_EACH", "99999")
    assert comfy_timeout_each() == 7200.0


def test_comfy_lab_autoclear_queue(monkeypatch):
    monkeypatch.delenv("VIU_COMFY_LAB_CLEAR_QUEUE", raising=False)
    assert comfy_lab_autoclear_queue() is True
    monkeypatch.setenv("VIU_COMFY_LAB_CLEAR_QUEUE", "0")
    assert comfy_lab_autoclear_queue() is False


def test_comfy_max_pending_for_lab(monkeypatch):
    monkeypatch.delenv("VIU_COMFY_MAX_PENDING", raising=False)
    assert comfy_max_pending_for_lab() == 0
    monkeypatch.setenv("VIU_COMFY_MAX_PENDING", "3")
    assert comfy_max_pending_for_lab() == 3


def test_prepare_queue_empty(tmp_path):
    client = MagicMock()
    client.queue_counts.return_value = (0, 0)
    ok, msg = prepare_queue_for_triple(_cfg(tmp_path), client)
    assert ok is True
    assert msg == ""
    client.reset_queue.assert_not_called()


def test_prepare_queue_autoclear(tmp_path, monkeypatch):
    monkeypatch.setenv("VIU_COMFY_LAB_CLEAR_QUEUE", "1")
    client = MagicMock()
    client.queue_counts.return_value = (1, 5)
    client.reset_queue.return_value = (True, "ok")
    ok, msg = prepare_queue_for_triple(_cfg(tmp_path), client)
    assert ok is True
    assert "сброшена" in msg
    client.reset_queue.assert_called_once()


def test_prepare_queue_blocked_when_no_autoclear(tmp_path, monkeypatch):
    monkeypatch.setenv("VIU_COMFY_LAB_CLEAR_QUEUE", "0")
    monkeypatch.setenv("VIU_COMFY_MAX_PENDING", "0")
    client = MagicMock()
    client.queue_counts.return_value = (0, 2)
    ok, msg = prepare_queue_for_triple(_cfg(tmp_path), client)
    assert ok is False
    assert "pending=2" in msg
    client.reset_queue.assert_not_called()


def test_should_stop_triple_after_fail():
    assert should_stop_triple_after_fail("Таймаут 900s") is True
    assert should_stop_triple_after_fail("connection timeout") is True
    assert should_stop_triple_after_fail("пропал из очереди") is True
    assert should_stop_triple_after_fail("ComfyError: node failed") is False
