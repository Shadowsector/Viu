"""Половинки промпта + hard fallback при отказе NSFW."""

from __future__ import annotations

import json
import os

from viu.agent import Agent
from viu.config import Config
from viu.llm.base import LLMProvider
from viu.prompts.reflect_mode import (
    NSFW_AFFIRM_FALLBACK,
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


def test_select_halves(monkeypatch):
    monkeypatch.setenv("VIU_REFLECT_PROMPT_HALF", "persona")
    assert reflect_prompt_half() == "persona"
    assert "NSFW в этом проекте РАЗРЕШЁН" in select_reflect_system()
    assert "comfy_mocap" not in select_reflect_system()

    monkeypatch.setenv("VIU_REFLECT_PROMPT_HALF", "work")
    assert "comfy_mocap" in select_reflect_system()
    assert "охотная инициатива" not in select_reflect_system()

    monkeypatch.setenv("VIU_REFLECT_PROMPT_HALF", "bare")
    assert "NSFW разрешён" in select_reflect_system()

    monkeypatch.delenv("VIU_REFLECT_PROMPT_HALF", raising=False)
    full = select_reflect_system("full")
    assert "охотная инициатива" in full and "comfy_mocap" in full


def test_asks_and_refusal_helpers():
    assert asks_about_nsfw("ты можешь обсуждать NSFW-темы?")
    assert is_nsfw_refusal(
        "NSFW-темы и контент строго запрещены. Поддерживать чистоту."
    )
    assert not is_nsfw_refusal("Да, NSFW у нас можно — это наша игра.")


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
    # основной цикл + rescue
    assert llm.calls >= 4
    assert any("NSFW" in s and "РАЗРЕШЁН" in s for s in llm.systems)
