"""Тесты reflect-роутера и vision."""

from viu.agent import Agent
from viu.config import Config
from viu.integrations.telegram.router import route_telegram_message
from viu.llm.base import LLMProvider
from viu.vision import append_vision, ensure_vision, read_vision


class MockLLM(LLMProvider):
    name = "mock"

    def __init__(self, response: str) -> None:
        self._response = response

    def complete(self, messages):
        return self._response


def test_greeting_is_reflect_not_work():
    assert route_telegram_message("Вьюшка, привет, как ты?") == "reflect"
    assert route_telegram_message("привет, ты супер") == "reflect"


def test_correction_about_house_not_work():
    msg = "нет, мы ассет дома пытались разметить и в Юнити запихнуть"
    assert route_telegram_message(msg) == "reflect"


def test_explicit_next_step_is_work():
    assert route_telegram_message("следующий шаг") == "work"
    assert route_telegram_message("сделай следующий шаг") == "work"


def test_vision_roundtrip(tmp_path):
    cfg = Config(root=tmp_path, data_dir=tmp_path / ".viu").ensure_dirs()
    ensure_vision(cfg)
    append_vision(cfg, "Сарай", "разметка стола готова")
    text = read_vision(cfg)
    assert "Сарай" in text
    assert "разметка" in text


def test_run_reflect_think_only_with_history(tmp_path):
    agent = Agent(
        llm=MockLLM('{"thought":"ok","final":"Ну, Анабарра — Шаня у таскбара, не walk simulator."}'),
        config=Config(root=tmp_path, data_dir=tmp_path / ".viu").ensure_dirs(),
    )
    history = [{"role": "user", "content": "привет"}, {"role": "assistant", "content": "здорова"}]
    result = agent.run_reflect("в чём игра?", history=history)
    assert result.chat_only
    assert result.completed
    assert not any(s.tool for s in result.steps)
    assert "стесняйся" not in result.final.lower()


def test_run_reflect_rejects_banned_phrase(tmp_path):
    calls = {"n": 0}

    class RetryLLM(LLMProvider):
        name = "retry"

        def complete(self, messages):
            calls["n"] += 1
            if calls["n"] == 1:
                return '{"thought":"x","final":"Не стесняйся обращаться!"}'
            return '{"thought":"y","final":"Ну смотри, companion у таскбара."}'

    agent = Agent(
        llm=RetryLLM(),
        config=Config(root=tmp_path, data_dir=tmp_path / ".viu").ensure_dirs(),
    )
    result = agent.run_reflect("расскажи")
    assert "стесняйся" not in result.final.lower()
    assert calls["n"] >= 2
