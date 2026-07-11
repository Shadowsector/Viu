"""Тесты Cursor → Viu inbox."""

from viu.integrations.github.inbox import (
    empty_inbox,
    format_task_prompt,
    mark_task,
    pending_tasks,
    upsert_task,
)
from viu.tools import build_default_registry


def test_pending_and_mark():
    inbox = empty_inbox()
    upsert_task(
        inbox,
        {
            "id": "t1",
            "status": "pending",
            "priority": 2,
            "title": "Test",
            "instructions": "Do thing",
        },
    )
    upsert_task(
        inbox,
        {
            "id": "t0",
            "status": "pending",
            "priority": 1,
            "title": "First",
            "instructions": "First thing",
        },
    )
    pending = pending_tasks(inbox)
    assert pending[0]["id"] == "t0"
    assert mark_task(inbox, "t0", status="done", result="ok")
    assert pending_tasks(inbox)[0]["id"] == "t1"
    prompt = format_task_prompt(pending[0])
    assert "Cursor → Viu" in prompt or "task" in prompt


def test_registry_has_inbox_and_playtest():
    reg = build_default_registry()
    assert reg.get("cursor_inbox_pull") is not None
    assert reg.get("cursor_inbox_complete") is not None
    assert reg.get("overlay_playtest") is not None
