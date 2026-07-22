"""Тесты многочастной доставки reflect-ответов."""

from __future__ import annotations

import json

from viu.agent import Agent
from viu.config import Config
from viu.llm.base import LLMProvider
from viu.reflect_delivery import (
    continuation_user_prompt,
    reflect_max_parts,
    reflect_max_words_per_part,
    should_fetch_more_parts,
    truncate_retry_hint,
    word_count,
)


def test_word_count_basic():
    assert word_count("один два три") == 3
    assert word_count("") == 0


def test_should_fetch_more_parts_on_truncated():
    assert should_fetch_more_parts("коротко", truncated=True)


def test_should_fetch_more_parts_on_long_text():
    text = " ".join(f"w{i}" for i in range(250))
    assert should_fetch_more_parts(text)


def test_should_fetch_more_parts_on_marker():
    assert should_fetch_more_parts("Всё ясно (продолжу)")


def test_truncate_retry_hint_mentions_parts():
    hint = truncate_retry_hint(attempt=0, max_words=220)
    assert "часть 1" in hint
    assert "220" in hint


def test_continuation_prompt_includes_prior():
    prompt = continuation_user_prompt(
        user_text="расскажи сцену",
        prior_parts=["часть один"],
        part_index=1,
        max_parts=3,
        max_words=220,
    )
    assert "часть один" in prompt
    assert "часть 2" in prompt.lower() or "2" in prompt


class MultiPartLLM(LLMProvider):
    name = "multi"

    def __init__(self) -> None:
        self.calls = 0

    def complete(self, messages, *, temperature=None, model=None):
        self.calls += 1
        if self.calls == 1:
            body = " ".join(f"слово{i}" for i in range(230))
            return json.dumps(
                {"thought": "длинно", "final": body + " (продолжу)"},
                ensure_ascii=False,
            )
        return json.dumps(
            {"thought": "ещё", "final": "Вторая часть — коротко и тепло."},
            ensure_ascii=False,
        )


def test_agent_reflect_fetches_second_part(tmp_path, monkeypatch):
    monkeypatch.setenv("VIU_DATA_DIR", str(tmp_path / ".viu"))
    monkeypatch.setenv("VIU_REFLECT_MAX_WORDS", "220")
    monkeypatch.setenv("VIU_REFLECT_MAX_PARTS", "3")
    cfg = Config().ensure_dirs()
    agent = Agent(config=cfg, llm=MultiPartLLM())
    result = agent.run_reflect("напиши длинную сцену")
    assert result.completed
    assert len(result.final_parts) >= 2
    assert "Вторая часть" in result.final
    assert reflect_max_words_per_part(cfg) == 220
    assert reflect_max_parts(cfg) == 3
