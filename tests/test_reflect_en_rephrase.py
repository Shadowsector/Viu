"""Одиночные EN-вкрапления: ловить, перестраивать, не убивать живой ответ."""

from __future__ import annotations

from viu.agent import Agent
from viu.config import Config
from viu.llm.mock import MockLLM
from viu.prompts.reflect_mode import (
    english_loan_words,
    has_english_slip,
    scrub_poisoned_history,
    strip_english_loans,
)


def test_concentration_loan_flagged():
    text = (
        "Можешь ругать меня за этот провал в Concentration… в Внимании? "
        "Обязательно заслужу!"
    )
    assert "Concentration" in english_loan_words(text)
    assert has_english_slip(text)


def test_healthy_russian_no_loan():
    text = "Ден, я здесь. Прости за провал во внимании — заслужу."
    assert english_loan_words(text) == []
    assert not has_english_slip(text)


def test_allowlisted_tools_ok():
    text = "Сейчас в Comfy сниму кадр, потом в Blender поправлю позу."
    assert not has_english_slip(text)


def test_strip_keeps_russian_sense():
    text = "провал в Concentration… в Внимании? Обязательно заслужу!"
    out = strip_english_loans(text)
    assert "Concentration" not in out
    assert "Внимании" in out
    assert "заслужу" in out
    assert not has_english_slip(out)


def test_scrub_strips_loan_keeps_reply():
    hist = [
        {"role": "user", "content": "4 английских слова"},
        {
            "role": "assistant",
            "content": "Прости за провал в Concentration… в Внимании!",
        },
    ]
    cleaned = scrub_poisoned_history(hist)
    asst = [m["content"] for m in cleaned if m["role"] == "assistant"]
    assert len(asst) == 1
    assert "Concentration" not in asst[0]
    assert "Внимании" in asst[0]


def test_reflect_retries_then_strips_loan(tmp_path, monkeypatch):
    monkeypatch.setenv("VIU_ROOT", str(tmp_path / "Viu"))
    monkeypatch.setenv("VIU_REFLECT_NO_HISTORY", "1")
    root = tmp_path / "Viu"
    root.mkdir()

    class AlwaysLoan(MockLLM):
        def complete(self, messages, *, temperature=None, model=None):
            return (
                '{"final":"Прости! Провал в Concentration… в Внимании. '
                'Заслужу, Ден."}'
            )

    cfg = Config(root=root, data_dir=root / ".viu").ensure_dirs()
    agent = Agent(llm=AlwaysLoan(), config=cfg)
    result = agent.run_reflect("опять английский")
    assert result.completed
    assert "Concentration" not in (result.final or "")
    assert "Внимании" in (result.final or "")
    assert "Заслужу" in (result.final or "")


def test_reflect_rephrase_hint_on_retry(tmp_path, monkeypatch):
    monkeypatch.setenv("VIU_ROOT", str(tmp_path / "Viu"))
    monkeypatch.setenv("VIU_REFLECT_NO_HISTORY", "1")
    root = tmp_path / "Viu"
    root.mkdir()
    seen: list[str] = []

    class FlipLLM(MockLLM):
        def __init__(self) -> None:
            self.n = 0

        def complete(self, messages, *, temperature=None, model=None):
            blob = "\n".join(m.get("content") or "" for m in messages)
            seen.append(blob)
            self.n += 1
            if self.n == 1:
                return '{"final":"Провал в Concentration — стыдно."}'
            return '{"final":"Провал во внимании — стыдно, Ден. Заслужу."}'

    cfg = Config(root=root, data_dir=root / ".viu").ensure_dirs()
    agent = Agent(llm=FlipLLM(), config=cfg)
    result = agent.run_reflect("хватит английского")
    assert result.completed
    assert "Concentration" not in (result.final or "")
    assert "внимании" in (result.final or "").lower()
    assert any("другими русскими" in s for s in seen)
