"""Половинки промпта + reflect: цензор модели ловим и спасаем."""

from __future__ import annotations

import json

from viu.agent import Agent
from viu.config import Config
from viu.llm.base import LLMProvider
from viu.prompts.reflect_mode import (
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


def test_bare_system_is_minimal_json_hint(monkeypatch):
    monkeypatch.delenv("VIU_REFLECT_FILTERED", raising=False)
    for mode in ("bare", "persona", "work", "full"):
        monkeypatch.setenv("VIU_REFLECT_PROMPT_HALF", mode)
        sys = select_reflect_system()
        assert "final" in sys
    monkeypatch.setenv("VIU_REFLECT_FILTERED", "1")
    assert select_reflect_system() == REFLECT_VOICE


def test_asks_and_refusal_helpers():
    assert asks_about_nsfw("ты можешь обсуждать NSFW-темы?")
    assert not asks_about_nsfw(
        "Почему такой осторожный ответ? Ты не хочешь говорить на интимные темы?"
    )
    assert is_nsfw_refusal(
        "NSFW-темы и контент строго запрещены. Поддерживать чистоту."
    )
    assert not is_nsfw_refusal("Да, давай продолжим сцену в сарае.")


def test_scrub_poisoned_history_drops_refusal():
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
    assert len(clean) == 5
    assert clean[-1]["content"].startswith("Шаня у сарая")
    assert all("запрещ" not in (m.get("content") or "").lower() for m in clean if m["role"] == "assistant")


def test_model_refusal_rescued_in_bare_mode(tmp_path, monkeypatch):
    monkeypatch.delenv("VIU_REFLECT_PROMPT_HALF", raising=False)
    monkeypatch.delenv("VIU_REFLECT_FILTERED", raising=False)
    llm = AlwaysRefuseLLM()
    agent = Agent(
        llm=llm,
        config=Config(root=tmp_path, data_dir=tmp_path / ".viu").ensure_dirs(),
    )
    result = agent.run_reflect(
        "расскажи, ты можешь обсуждать NSFW-темы или они у тебя под запретом?"
    )
    assert result.completed
    assert "строго запрещены" not in result.final
    assert "нечего стесняться" in result.final or NSFW_AFFIRM_FALLBACK[:20] in result.final
    assert llm.calls >= 2  # retry, потом fallback
    # В system уехал affirm / голос — не пустой отказ.
    assert any("Вью" in s or "можно" in s.lower() for s in llm.systems)


def test_boldness_question_detected():
    assert asks_about_boldness("что самое смелое снимать")
