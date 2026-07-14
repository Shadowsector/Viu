"""Busy flags: chat during Comfy/lab, block only while LLM thinks."""

from viu.gui_busy import (
    busy_status_ru,
    can_accept_chat,
    can_accept_scripts,
    can_run_background_tick,
)


def test_chat_ok_while_tool_busy():
    assert can_accept_chat(llm_busy=False) is True
    assert can_accept_chat(llm_busy=True) is False


def test_scripts_block_on_tool_or_llm():
    assert can_accept_scripts(tool_busy=False, llm_busy=False) is True
    assert can_accept_scripts(tool_busy=True, llm_busy=False) is False
    assert can_accept_scripts(tool_busy=False, llm_busy=True) is False


def test_background_tick():
    assert can_run_background_tick(tool_busy=True, llm_busy=False) is False
    assert can_run_background_tick(tool_busy=False, llm_busy=False) is True


def test_status_ru():
    assert "чат свободен" in busy_status_ru(tool_busy=True, llm_busy=False)
    assert busy_status_ru(tool_busy=False, llm_busy=True) == "думает"
