"""Watchdog ожидания Comfy: fast-fail, auto-reset, retry policy."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from viu.integrations.comfy.client import ComfyClient, ComfyError
from viu.integrations.comfy.queue_policy import (
    comfy_auto_reset_on_hang,
    comfy_retry_on_hang,
    should_retry_after_hang,
    wait_options_for_lab,
)
from viu.config import Config


def test_prompt_ids_in_queue():
    queue = {
        "queue_running": [[1, "run-id", {}, {}, []]],
        "queue_pending": [[2, "pend-id", {}, {}, []], [3, "run-id", {}, {}, []]],
    }
    found = ComfyClient._prompt_ids_in_queue(queue)
    assert found == {"run-id": "running", "pend-id": "pending"}


def test_wait_history_gone_fast_fail_auto_reset():
    client = ComfyClient()
    states = ["pending", "gone", "gone"]

    def _state(_pid: str) -> str:
        return states.pop(0) if states else "gone"

    with (
        patch.object(client, "get_history", return_value=None),
        patch.object(client, "prompt_queue_state", side_effect=_state),
        patch.object(client, "reset_queue", return_value=(True, "cleared")) as reset,
        patch("viu.integrations.comfy.client.time.sleep"),
    ):
        with pytest.raises(ComfyError, match="пропал из очереди"):
            client.wait_history(
                "pid-x",
                timeout=30,
                gone_grace=0.05,
                poll=0.01,
                auto_reset_on_hang=True,
            )
    reset.assert_called_once()


def test_wait_history_timeout_auto_reset():
    client = ComfyClient()
    with (
        patch.object(client, "get_history", return_value=None),
        patch.object(client, "prompt_queue_state", return_value="running"),
        patch.object(client, "queue_summary", return_value="running=1 pending=0"),
        patch.object(client, "reset_queue", return_value=(True, "cleared")) as reset,
        patch("viu.integrations.comfy.client.time.time", side_effect=[0.0, 0.0, 0.0, 11.0, 11.0]),
        patch("viu.integrations.comfy.client.time.sleep"),
    ):
        with pytest.raises(ComfyError, match="Таймаут"):
            client.wait_history(
                "pid-y",
                timeout=10,
                poll=0.01,
                auto_reset_on_hang=True,
            )
    reset.assert_called_once()


def test_wait_options_for_lab(tmp_path):
    cfg = Config(
        root=tmp_path,
        data_dir=tmp_path / ".viu",
        library_root=str(tmp_path / "Library"),
    )
    opts = wait_options_for_lab(cfg)
    assert opts["auto_reset_on_hang"] is True
    assert opts["gone_grace"] == 25.0
    assert opts["stall_sec"] == 0.0


def test_should_retry_after_hang():
    assert should_retry_after_hang("Таймаут ожидания") is True
    assert should_retry_after_hang("Job пропал из очереди") is True
    assert should_retry_after_hang("LoRA missing") is False


def test_comfy_retry_on_hang_default(monkeypatch):
    monkeypatch.delenv("VIU_COMFY_RETRY_ON_HANG", raising=False)
    assert comfy_retry_on_hang() == 1


def test_comfy_auto_reset_default(monkeypatch):
    monkeypatch.delenv("VIU_COMFY_AUTO_RESET_ON_HANG", raising=False)
    assert comfy_auto_reset_on_hang() is True
