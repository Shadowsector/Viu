"""Тесты многочастной доставки reflect-ответов."""

from __future__ import annotations

import json

from viu.agent import Agent
from viu.config import Config
from viu.llm.base import LLMProvider
from viu.reflect_delivery import (
    collect_final_parts,
    continuation_user_prompt,
    list_delivery_hint,
    reflect_max_parts,
    requested_item_count,
    should_fetch_more_parts,
    truncate_retry_hint,
    word_count,
)


def test_word_count_basic():
    assert word_count("один два три") == 3


def test_requested_item_count_russian():
    assert requested_item_count("опиши пять событий") == 5
    assert requested_item_count("3 сцены") == 3


def test_collect_final_parts_array():
    parts = collect_final_parts(
        "",
        {"final_parts": ["один", "два", "три"]},
    )
    assert parts == ["один", "два", "три"]


def test_list_delivery_hint_for_five():
    hint = list_delivery_hint("расскажи пять событий")
    assert "final_parts" in hint
    assert "5" in hint


def test_should_fetch_more_parts_on_truncated():
    assert should_fetch_more_parts("коротко", truncated=True)


def test_should_fetch_more_parts_not_on_length_alone():
    # Длинный, но законченный ответ — не тянуть вторую часть (дубли).
    long_ok = "А. " * 100 + "Всё."
    assert not should_fetch_more_parts(long_ok, truncated=False)


class MultiPartLLM(LLMProvider):
    name = "multi"

    def __init__(self) -> None:
        self.calls = 0

    def complete(self, messages, *, temperature=None, model=None):
        self.calls += 1
        if self.calls == 1:
            return json.dumps(
                {
                    "thought": "список",
                    "final_parts": ["Событие 1.", "Событие 2.", "Событие 3."],
                },
                ensure_ascii=False,
            )
        return json.dumps({"thought": "x", "final": "лишнее"}, ensure_ascii=False)


def test_agent_reflect_final_parts(tmp_path, monkeypatch):
    monkeypatch.setenv("VIU_DATA_DIR", str(tmp_path / ".viu"))
    monkeypatch.setenv("VIU_REFLECT_FILTERED", "0")
    cfg = Config().ensure_dirs()
    agent = Agent(config=cfg, llm=MultiPartLLM())
    result = agent.run_reflect("опиши три события")
    assert result.completed
    assert len(result.final_parts) == 3
    assert "Событие 2" in result.final_parts[1]
