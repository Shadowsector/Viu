"""Протокол thought/final не должен уходить Дену; история чистится."""

from __future__ import annotations

from viu.agent import (
    looks_like_leaked_protocol,
    parse_reflect_response,
    sanitize_reflect_visible,
)
from viu.prompts.reflect_mode import has_english_slip, scrub_poisoned_history


def test_markdown_thought_final_not_leaked_whole():
    raw = (
        "**thought:** *Ох нет... я снова перешла!*\n\n"
        "*обхватываю руками голову*\n\n"
        "Извини... from habit.\n\n"
        "**thought:** *Он прав.*\n\n"
        "**final:** *с отчаянием* Ден... я не хочу, чтобы ты ушёл."
    )
    assert looks_like_leaked_protocol(raw)
    final, thought, truncated, parsed = parse_reflect_response(raw)
    assert not truncated
    assert final is not None
    assert "Ден" in final
    assert "thought" not in final.lower()
    assert "from habit" not in final  # thought-блок отрезан; final чистый
    visible = sanitize_reflect_visible(raw)
    assert "Ден" in visible
    assert "**thought:**" not in visible
    assert "**final:**" not in visible


def test_has_english_slip():
    assert has_english_slip("Извини, from habit — я снова.")
    assert has_english_slip("I can give you what you want")
    assert not has_english_slip("Я прижимаюсь к тебе, Ден. Люблю.")


def test_scrub_poisoned_history_drops_en_and_protocol():
    hist = [
        {"role": "user", "content": "привет"},
        {
            "role": "assistant",
            "content": "**thought:** x\n**final:** Ден, я здесь.",
        },
        {
            "role": "assistant",
            "content": "Sorry, from habit I slipped again into English.",
        },
        {"role": "user", "content": "ещё раз"},
    ]
    cleaned = scrub_poisoned_history(hist)
    roles = [m["role"] for m in cleaned]
    assert roles.count("assistant") == 1
    assert cleaned[1]["content"].startswith("Ден")
    assert "thought" not in cleaned[1]["content"].lower()
    assert all("habit" not in m["content"].lower() for m in cleaned if m["role"] == "assistant")
