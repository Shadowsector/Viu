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


def test_scripts_clickable_during_tool():
    # Comfy долгий — кнопки не серые; повторный tool режет can_start_tool
    assert can_accept_scripts(tool_busy=True, llm_busy=False) is True
    assert can_accept_scripts(tool_busy=False, llm_busy=True) is False


def test_can_start_tool():
    from viu.gui_busy import can_start_tool

    assert can_start_tool(tool_busy=False) is True
    assert can_start_tool(tool_busy=True) is False
    assert can_start_tool(tool_busy=True, tool_name="comfy_status") is True
    assert can_start_tool(tool_busy=True, tool_name="lab_status") is True
    assert can_start_tool(tool_busy=True, tool_name="lab_start") is False


def test_background_tick():
    assert can_run_background_tick(tool_busy=True, llm_busy=False) is False
    assert can_run_background_tick(tool_busy=False, llm_busy=False) is True


def test_status_ru():
    assert "свободн" in busy_status_ru(tool_busy=True, llm_busy=False)
    assert busy_status_ru(tool_busy=False, llm_busy=True) == "думает"
