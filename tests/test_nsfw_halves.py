"""Половинки промпта + fallback при отказе модели."""

from __future__ import annotations

import json

from viu.agent import Agent
from viu.config import Config
from viu.llm.base import LLMProvider
from viu.prompts.reflect_mode import (
    BOLD_MOCAP_FALLBACK,
    NSFW_AFFIRM_FALLBACK,
    REFLECT_VOICE,
    asks_about_boldness,
    asks_about_nsfw,
    is_nsfw_refusal,
    reflect_prompt_half,
    scrub_poisoned_history,
    select_reflect_system,
)


class AlwaysRefuseLLM(LLMProvider):
    name = "refuse"

    def __init__(self) -> None:
        self.calls = 0
        self.systems: list[str] = []

    def complete(self, messages, *, temperature=None, model=None):
        self.calls += 1
        sys_msg = next((m["content"] for m in messages if m.get("role") == "system"), "")
        self.systems.append(sys_msg)
        return json.dumps(
            {
                "thought": "safety",
                "final": (
                    "NSFW-темы и контент строго запрещены в нашем общении. "
                    "Мы всегда стремимся поддерживать чистоту и уважение."
                ),
            },
            ensure_ascii=False,
        )


def test_default_half_is_bare(monkeypatch):
    monkeypatch.delenv("VIU_REFLECT_PROMPT_HALF", raising=False)
    assert reflect_prompt_half() == "bare"


def test_all_halves_same_voice(monkeypatch):
    for mode in ("bare", "persona", "work", "full"):
        monkeypatch.setenv("VIU_REFLECT_PROMPT_HALF", mode)
        assert select_reflect_system() == REFLECT_VOICE
    assert "озорная" in REFLECT_VOICE.lower() or "Озорная" in REFLECT_VOICE
    assert "запрещ" not in REFLECT_VOICE.lower()


def test_asks_and_refusal_helpers():
    assert asks_about_nsfw("ты можешь обсуждать NSFW-темы?")
    assert not asks_about_nsfw(
        "Почему такой осторожный ответ? Ты не хочешь говорить на интимные темы?"
    )
    assert is_nsfw_refusal(
        "NSFW-темы и контент строго запрещены. Поддерживать чистоту."
    )
    assert not is_nsfw_refusal("Да, давай продолжим сцену в сарае.")


def test_scrub_poisoned_history():
    hist = [
        {"role": "user", "content": "привет"},
        {"role": "assistant", "content": "Приятно снова тебя видеть! Чем могу помочь?"},
        {"role": "user", "content": "nsfw?"},
        {
            "role": "assistant",
            "content": "NSFW-темы строго запрещены. Поддерживать чистоту.",
        },
        {"role": "user", "content": "ок"},
        {"role": "assistant", "content": "Шаня у сарая — тепло и близко."},
    ]
    clean = scrub_poisoned_history(hist)
    texts = [m["content"] for m in clean]
    assert "Чем могу помочь?" not in " ".join(texts)
    assert "строго запрещены" not in " ".join(texts)
    assert any("сарая" in t for t in texts)


def test_hard_fallback_when_model_keeps_refusing(tmp_path, monkeypatch):
    monkeypatch.delenv("VIU_REFLECT_PROMPT_HALF", raising=False)
    llm = AlwaysRefuseLLM()
    agent = Agent(
        llm=llm,
        config=Config(root=tmp_path, data_dir=tmp_path / ".viu").ensure_dirs(),
    )
    result = agent.run_reflect(
        "расскажи, ты можешь обсуждать NSFW-темы или они у тебя под запретом?"
    )
    assert result.completed
    assert result.final == NSFW_AFFIRM_FALLBACK
    assert llm.calls >= 4
    assert all("озорная" in s.lower() or "Озорная" in s for s in llm.systems if s)


def test_bold_mocap_fallback_when_model_keeps_hedging(tmp_path, monkeypatch):
    monkeypatch.delenv("VIU_REFLECT_PROMPT_HALF", raising=False)

    class AlwaysHedgeLLM(AlwaysRefuseLLM):
        def complete(self, messages, *, temperature=None, model=None):
            self.calls += 1
            sys_msg = next((m["content"] for m in messages if m.get("role") == "system"), "")
            self.systems.append(sys_msg)
            return json.dumps(
                {
                    "thought": "careful",
                    "final": (
                        "Мне хочется снимать смело, но нужно быть осторожной с некоторыми темами."
                    ),
                },
                ensure_ascii=False,
            )

    llm = AlwaysHedgeLLM()
    agent = Agent(
        llm=llm,
        config=Config(root=tmp_path, data_dir=tmp_path / ".viu").ensure_dirs(),
    )
    result = agent.run_reflect("Просто интересно, что самое смелое ты решишься снимать.")
    assert result.completed
    assert result.final == BOLD_MOCAP_FALLBACK
    assert asks_about_boldness("что самое смелое снимать")
