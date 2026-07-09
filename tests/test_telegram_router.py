"""Тесты reflect-роутера и vision."""

import json

from viu.agent import Agent, extract_inner_json
from viu.config import Config
from viu.integrations.telegram.router import route_telegram_message
from viu.llm.base import LLMProvider
from viu.vision import append_vision, ensure_vision, read_vision


class MockLLM(LLMProvider):
    name = "mock"

    def __init__(self, response: str) -> None:
        self._response = response

    def complete(self, messages, *, temperature=None):
        return self._response


class TwoPhaseLLM(LLMProvider):
    """Think → speak: по системному промпту."""

    name = "two_phase"

    def __init__(self, inner: str, final: str) -> None:
        self._inner = inner
        self._final = final
        self.calls = 0

    def complete(self, messages, *, temperature=None):
        self.calls += 1
        sys = messages[0]["content"] if messages else ""
        if "внутренний монолог" in sys:
            return json.dumps({"inner": self._inner}, ensure_ascii=False)
        return json.dumps({"final": self._final}, ensure_ascii=False)


class RetrySpeakLLM(LLMProvider):
    name = "retry_speak"

    def __init__(self) -> None:
        self.calls = 0

    def complete(self, messages, *, temperature=None):
        self.calls += 1
        sys = messages[0]["content"] if messages else ""
        if "внутренний монолог" in sys:
            return '{"inner":"Думаю про companion и снежинку."}'
        if self.calls == 2:
            return '{"final":"Не стесняйся обращаться!"}'
        return '{"final":"Ну смотри, companion у таскбара."}'


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


def test_extract_inner_json():
    assert extract_inner_json('{"inner":"хм…"}') == {"inner": "хм…"}
    assert extract_inner_json('```json\n{"inner":"ok"}\n```') == {"inner": "ok"}


def test_run_reflect_two_phase_with_history(tmp_path):
    llm = TwoPhaseLLM(
        "Анабарра — Шаня у таскбара, снежинка, не walk sim.",
        "Ну, Анабарра — Шаня у таскбара, не walk simulator.",
    )
    agent = Agent(
        llm=llm,
        config=Config(root=tmp_path, data_dir=tmp_path / ".viu").ensure_dirs(),
    )
    history = [{"role": "user", "content": "привет"}, {"role": "assistant", "content": "здорова"}]
    result = agent.run_reflect("в чём игра?", history=history)
    assert result.chat_only
    assert result.completed
    assert result.inner_thought
    assert "снежинка" in result.inner_thought
    assert not any(s.tool for s in result.steps)
    assert "стесняйся" not in result.final.lower()
    assert llm.calls >= 2


def test_run_reflect_rejects_banned_phrase(tmp_path):
    llm = RetrySpeakLLM()
    agent = Agent(
        llm=llm,
        config=Config(root=tmp_path, data_dir=tmp_path / ".viu").ensure_dirs(),
    )
    result = agent.run_reflect("расскажи")
    assert "стесняйся" not in result.final.lower()
    assert llm.calls >= 3
