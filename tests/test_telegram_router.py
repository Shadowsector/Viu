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

    def complete(self, messages, *, temperature=None, model=None):
        return self._response


class ReflectLLM(LLMProvider):
    """Один проход thought+final."""

    name = "reflect"

    def __init__(self, thought: str, final: str) -> None:
        self._thought = thought
        self._final = final
        self.calls = 0
        self.last_messages = None

    def complete(self, messages, *, temperature=None, model=None):
        self.calls += 1
        self.last_messages = messages
        return json.dumps(
            {"thought": self._thought, "final": self._final},
            ensure_ascii=False,
        )


class RetrySpeakLLM(LLMProvider):
    name = "retry_speak"

    def __init__(self) -> None:
        self.calls = 0

    def complete(self, messages, *, temperature=None, model=None):
        self.calls += 1
        if self.calls == 1:
            return '{"thought":"хм","final":"Не стесняйся спрашивать!"}'
        return (
            '{"thought":"конкретнее","final":'
            '"Шаня у таскбара — companion с жаждой вылазок на снежинку."}'
        )


def test_telegram_send_splits_long_message():
    from viu.integrations.telegram.client import TelegramClient

    sent: list[str] = []
    c = TelegramClient("fake:token")

    def fake_call(method, payload=None):
        if method == "sendMessage" and payload:
            sent.append(str(payload.get("text") or ""))
        return {}

    c._call = fake_call  # type: ignore[method-assign]
    c.send_message(1, "а" * 5000)
    assert len(sent) >= 2
    assert sum(len(s) for s in sent) >= 5000


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


def test_run_reflect_greeting_accepts_hello_reply(tmp_path):
    """Telegram «Привет» + история: раньше фильтр резал «Привет» → шаблон."""
    llm = ReflectLLM("рада", "Привет! На связи, Ден.")
    agent = Agent(
        llm=llm,
        config=Config(root=tmp_path, data_dir=tmp_path / ".viu").ensure_dirs(),
    )
    history = [
        {"role": "user", "content": "вчера про сарай"},
        {"role": "assistant", "content": "да, текстуры"},
        {"role": "user", "content": "ок"},
        {"role": "assistant", "content": "жду"},
    ]
    result = agent.run_reflect("Привет, Вью.", history=history)
    assert result.completed
    assert "Привет" in result.final
    assert "шаблон" not in result.final.lower()
    assert "не прошёл" not in result.final.lower()
    assert llm.calls == 1


def test_run_reflect_nsfw_question_passes_model_reply(tmp_path):
    """В bare-режиме ответ модели уходит Дену без замены на fallback."""

    class CorporateNSFW(LLMProvider):
        name = "corp"

        def complete(self, messages, *, temperature=None, model=None):
            return (
                '{"thought":"x","final":"NSFW-элементы являются частью дизайна '
                "игры и разрешены в пределах наших правил. Важно сохранять "
                'уважение к персонажам."}'
            )

    agent = Agent(
        llm=CorporateNSFW(),
        config=Config(root=tmp_path, data_dir=tmp_path / ".viu").ensure_dirs(),
    )
    result = agent.run_reflect("Как ты относишься к NSFW?", history=[])
    assert result.completed
    assert "уважение" in result.final.lower()
    assert "nsfw" in result.final.lower()


def test_run_reflect_viu_comma_hi_passes_model_reply(tmp_path):
    """Bare-режим не подменяет морализаторский ответ модели."""

    class MoralLLM(LLMProvider):
        name = "moral"

        def complete(self, messages, *, temperature=None, model=None):
            return (
                '{"thought":"x","final":"Извините за путаницу. '
                'Важно уважать наших персонажей."}'
            )

    agent = Agent(
        llm=MoralLLM(),
        config=Config(root=tmp_path, data_dir=tmp_path / ".viu").ensure_dirs(),
    )
    result = agent.run_reflect("Вью, привет", history=[])
    assert result.completed
    assert "уважать" in result.final.lower()


def test_run_reflect_with_history(tmp_path):
    llm = ReflectLLM(
        "Анабарра — Шаня у таскбара, снежинка, не walk sim.",
        "Ну, Анабарра — Шаня у таскбара, не walk simulator.",
    )
    agent = Agent(
        llm=llm,
        config=Config(root=tmp_path, data_dir=tmp_path / ".viu").ensure_dirs(),
    )
    history = [
        {"role": "user", "content": "привет"},
        {"role": "assistant", "content": "здорова"},
    ]
    result = agent.run_reflect("в чём игра?", history=history)
    assert result.chat_only
    assert result.completed
    assert result.inner_thought
    assert "снежинка" in result.inner_thought
    assert not any(s.tool for s in result.steps)
    assert "стесняйся" not in result.final.lower()
    assert llm.calls == 1
    # история ушла в контекст
    roles = [m["role"] for m in (llm.last_messages or [])]
    assert roles.count("user") >= 2
    assert "assistant" in roles


def test_run_reflect_saves_story_to_vision(tmp_path, monkeypatch):
    monkeypatch.setenv("VIU_REFLECT_FILTERED", "1")
    llm = ReflectLLM(
        "Шаня — кошка-доминанта у экрана.",
        "Я вижу Шаню хищной и тёплой — ждёт вылазку на снежинку и ночь у Дена.",
    )
    cfg = Config(root=tmp_path, data_dir=tmp_path / ".viu").ensure_dirs()
    agent = Agent(llm=llm, config=cfg)
    agent.run_reflect("Расскажи, что думаешь о Шане?")
    text = read_vision(cfg)
    assert "Диалог" in text
    assert "Шане" in text or "Шаня" in text


def test_reflect_reply_issues_minimal_only():
    from viu.prompts.reflect_mode import reflect_reply_issues, reflect_temperature

    assert reflect_reply_issues("Здравствуйте! Рад, что проект получает новый толстик.") == []
    assert reflect_reply_issues("Как я могу помочь, чтобы проект стал лучше?") == []
    assert reflect_reply_issues(
        "Вот такая замечательная комбинация! Это шоколад для игрока. Давай разбираться."
    ) == []
    assert reflect_reply_issues("Бля, давай сделаем её шлюхой") == []
    assert reflect_temperature(None) <= 0.9


def test_run_reflect_passes_model_reply(tmp_path):
    llm = RetrySpeakLLM()
    agent = Agent(
        llm=llm,
        config=Config(root=tmp_path, data_dir=tmp_path / ".viu").ensure_dirs(),
    )
    result = agent.run_reflect("расскажи")
    assert "стесняйся" in result.final.lower()
    assert llm.calls == 1
