"""ComfyUI queue: slug parsing, stale detection, clear."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from viu.integrations.comfy.client import ComfyClient
from viu.integrations.comfy.queue_manage import (
    clear_comfy_queue,
    prepare_queue_for_slug,
    queue_stale_for_slug,
    slug_from_output_prefix,
)


def test_slug_from_output_prefix():
    assert slug_from_output_prefix("Girl_Idle_to_Lie_down_take_b") == "lie_down"
    assert slug_from_output_prefix("Girl_Touch_self_take_a_01") == "touch_self"
    assert slug_from_output_prefix("Girl_Walk_loop_02") == "walk"


def test_clear_queue_posts():
    client = ComfyClient("http://127.0.0.1:8188")
    with patch.object(client, "_post") as post:
        client.clear_queue()
    post.assert_called_once_with("/queue", {"clear": True})


def test_queue_stale_for_slug():
    client = MagicMock()
    workflow_lie = {
        "9": {
            "class_type": "SaveVideo",
            "inputs": {"filename_prefix": "Girl_Idle_to_Lie_down_take_b"},
        }
    }
    workflow_touch = {
        "9": {
            "class_type": "SaveVideo",
            "inputs": {"filename_prefix": "Girl_Touch_self_take_a"},
        }
    }
    client.get_queue.return_value = {
        "queue_running": [[1, "p1", workflow_lie, {}, []]],
        "queue_pending": [[2, "p2", workflow_touch, {}, []]],
    }
    stale, prefixes = queue_stale_for_slug(client, "touch_self")
    assert stale is True
    assert "Girl_Idle_to_Lie_down_take_b" in prefixes


def test_prepare_queue_clears_stale():
    client = MagicMock()
    workflow_lie = {
        "9": {
            "class_type": "SaveVideo",
            "inputs": {"filename_prefix": "Girl_Idle_to_Lie_down_take_b"},
        }
    }
    client.get_queue.return_value = {
        "queue_running": [[1, "p1", workflow_lie, {}, []]],
        "queue_pending": [],
    }
    with patch(
        "viu.integrations.comfy.queue_manage.clear_comfy_queue",
        return_value="cleared",
    ) as clear:
        msg = prepare_queue_for_slug(client, "touch_self")
    assert "touch_self" in msg
    clear.assert_called_once()


def test_prepare_queue_skips_matching():
    client = MagicMock()
    workflow_touch = {
        "9": {
            "class_type": "SaveVideo",
            "inputs": {"filename_prefix": "Girl_Touch_self_take_a"},
        }
    }
    client.get_queue.return_value = {
        "queue_running": [],
        "queue_pending": [[2, "p2", workflow_touch, {}, []]],
    }
    msg = prepare_queue_for_slug(client, "touch_self")
    assert msg == ""


def test_clear_comfy_queue_interrupt_and_clear():
    client = MagicMock()
    client.get_queue.return_value = {
        "queue_running": [[1, "p1", {}, {}, []]],
        "queue_pending": [[2, "p2", {}, {}, []]],
    }
    msg = clear_comfy_queue(client)
    client.interrupt.assert_called_once()
    client.clear_queue.assert_called_once()
    assert "interrupt" in msg
    assert "clear" in msg
