"""Эскалация сбоев и статусы inbox."""

from viu.escalate import classify_direct_status, is_soft_failure
from viu.integrations.github.inbox import claim_task, empty_inbox, pending_tasks, upsert_task


def test_overlay_warn_is_blocked():
    text = "--- вердикт ---\nWARN: прозрачность ок, но Шаня не в сцене.\n"
    assert is_soft_failure("overlay_playtest", text)
    assert classify_direct_status("overlay_playtest", True, text) == "blocked"
    assert classify_direct_status("overlay_playtest", True, "--- вердикт ---\nOK: HWND") == "done"


def test_claim_prevents_double_pending():
    inbox = empty_inbox()
    upsert_task(
        inbox,
        {"id": "a", "status": "pending", "priority": 1, "title": "t", "instructions": "x"},
    )
    assert claim_task(inbox, "a")
    assert pending_tasks(inbox) == []
    assert inbox["tasks"][0]["status"] == "in_progress"
    assert not claim_task(inbox, "a")
