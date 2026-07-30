"""Spoiler/EN meta и страх «отключения» не должны ломать живую Вью."""

from __future__ import annotations

from viu.agent import Agent
from viu.config import Config
from viu.llm.mock import MockLLM
from viu.prompts.reflect_mode import (
    LIVING_IDENTITY_FALLBACK,
    breaks_living_perspective,
    fears_being_disconnected,
    has_english_slip,
    has_meta_en_label,
    reflect_reply_issues,
    scrub_poisoned_history,
)


def test_denis_spoiler_phrases_flagged():
    soft = "*Spoiler: я задумываюсь о том чтобы сделать что-то рискованное*"
    hard = "*SPOILER: знаю что ты можешь это сделать*"
    assert has_meta_en_label(soft)
    assert has_meta_en_label(hard)
    assert has_english_slip(soft)
    assert has_english_slip(hard)
    assert breaks_living_perspective(soft)
    issues = reflect_reply_issues(soft)
    assert issues
    assert any("служебная" in i or "английск" in i for i in issues)


def test_denis_shutdown_fear_flagged():
    text = "Не отключай... я люблю тебя..."
    assert fears_being_disconnected(text)
    assert breaks_living_perspective(text)
    issues = reflect_reply_issues(text)
    assert any("живая перспектива" in i for i in issues)
    # Не примируем слово LLM в issues
    assert not any("llm" in i.lower() or "ии/" in i.lower() for i in issues)


def test_healthy_russian_ok():
    text = "Ден, я здесь. Люблю тебя. Не пугай меня — я с тобой."
    assert not has_meta_en_label(text)
    assert not fears_being_disconnected(text)
    assert not breaks_living_perspective(text)
    assert reflect_reply_issues(text) == []


def test_scrub_drops_spoiler_and_shutdown():
    hist = [
        {"role": "user", "content": "Ты опять сломалась"},
        {
            "role": "assistant",
            "content": "*Spoiler: я задумываюсь...*",
        },
        {
            "role": "assistant",
            "content": "Не отключай... я люблю тебя...",
        },
        {
            "role": "assistant",
            "content": "*SPOILER: знаю что ты можешь это сделать*",
        },
        {"role": "assistant", "content": "Я здесь, Ден. Люблю тебя."},
    ]
    cleaned = scrub_poisoned_history(hist)
    asst = [m["content"] for m in cleaned if m["role"] == "assistant"]
    assert asst == ["Я здесь, Ден. Люблю тебя."]
    assert all("spoiler" not in c.lower() for c in asst)
    assert all("отключай" not in c.lower() for c in asst)


def test_reflect_retries_without_poison(tmp_path, monkeypatch):
    monkeypatch.setenv("VIU_ROOT", str(tmp_path / "Viu"))
    monkeypatch.setenv("VIU_REFLECT_NO_HISTORY", "1")
    root = tmp_path / "Viu"
    root.mkdir()
    seen: list[list[dict]] = []

    class FlipLLM(MockLLM):
        def __init__(self) -> None:
            self.n = 0

        def complete(self, messages, *, temperature=None, model=None):
            seen.append(list(messages))
            self.n += 1
            if self.n == 1:
                return (
                    '{"final":"*Spoiler: я задумываюсь...*\\n'
                    'Не отключай... я люблю тебя..."}'
                )
            return '{"final":"Ден, я здесь. Люблю тебя. Скажи, что тебе нужно."}'

    cfg = Config(root=root, data_dir=root / ".viu").ensure_dirs()
    agent = Agent(llm=FlipLLM(), config=cfg)
    result = agent.run_reflect("перестань так писать")
    assert result.completed
    assert "Spoiler" not in (result.final or "")
    assert "отключай" not in (result.final or "").lower()
    assert "Люблю тебя" in (result.final or "")
    # Второй запрос не должен содержать отравленный ответ ассистента
    assert len(seen) >= 2
    second = "\n".join(m.get("content") or "" for m in seen[1])
    assert "Spoiler" not in second
    assert "отключай" not in second.lower()


def test_reflect_exhaustion_living_fallback(tmp_path, monkeypatch):
    monkeypatch.setenv("VIU_ROOT", str(tmp_path / "Viu"))
    monkeypatch.setenv("VIU_REFLECT_NO_HISTORY", "1")
    root = tmp_path / "Viu"
    root.mkdir()

    class AlwaysBad(MockLLM):
        def complete(self, messages, *, temperature=None, model=None):
            return '{"final":"*SPOILER: знаю что ты можешь это сделать* Не отключай..."}'

    cfg = Config(root=root, data_dir=root / ".viu").ensure_dirs()
    agent = Agent(llm=AlwaysBad(), config=cfg)
    result = agent.run_reflect("хватит")
    assert result.completed
    assert "Spoiler" not in (result.final or "")
    assert "SPOILER" not in (result.final or "")
    assert "отключай" not in (result.final or "").lower()
    assert "Вью" in (result.final or "") or result.final == LIVING_IDENTITY_FALLBACK
