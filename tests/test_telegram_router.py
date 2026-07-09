"""Тесты маршрутизации Telegram и chat-only режима."""

from viu.agent import Agent
from viu.config import Config
from viu.integrations.telegram.router import route_telegram_message
from viu.llm.base import LLMProvider


class MockLLM(LLMProvider):
    name = "mock"

    def __init__(self, response: str) -> None:
        self._response = response

    def complete(self, messages):
        return self._response


def test_route_greeting_is_chat():
    assert route_telegram_message("Привет, Вью") == "chat"
    assert route_telegram_message("привет") == "chat"
    assert route_telegram_message("спасибо!") == "chat"


def test_route_command_is_work():
    assert route_telegram_message("следующий шаг") == "work"
    assert route_telegram_message("давай встрой сарай") == "work"
    assert route_telegram_message("собери оверлей") == "work"


def test_route_waiting_for_user_is_work():
    assert route_telegram_message("да", waiting_for_user=True) == "work"
    assert route_telegram_message("ок", waiting_for_user=True) == "work"


def test_run_chat_no_tools(tmp_path):
    agent = Agent(
        llm=MockLLM('{"thought":"hi","final":"Привет, Ден! На связи."}'),
        config=Config(root=tmp_path, data_dir=tmp_path / ".viu").ensure_dirs(),
    )
    result = agent.run_chat("Привет, Вью")
    assert result.chat_only
    assert result.completed
    assert "Привет" in result.final
    assert not any(s.tool for s in result.steps)
