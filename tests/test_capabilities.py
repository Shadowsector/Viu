"""Тесты карты возможностей и ролей LLM."""

from __future__ import annotations

from viu.capabilities import CAPABILITY_BRIEF, docs_vector_brief, reflect_capability_notes
from viu.config import Config
from viu.llm_roles import guess_work_role, resolve_model
from viu.prompts.reflect_mode import REFLECT_VOICE, reflect_reply_issues
from viu.situational_context import build_reflect_notes


def test_capability_brief_mentions_pipeline():
    assert "тело Шани" in CAPABILITY_BRIEF or "body_pipeline" in CAPABILITY_BRIEF
    assert "паузе" in CAPABILITY_BRIEF.lower() or "Паузе" in CAPABILITY_BRIEF
    assert "Comfy" in CAPABILITY_BRIEF  # упомянут как на паузе
    assert "Комфи" in CAPABILITY_BRIEF or "триггер" in CAPABILITY_BRIEF.lower()
    assert "Cascadeur" in CAPABILITY_BRIEF
    assert "NOW.md" in CAPABILITY_BRIEF


def test_docs_vector_brief_nonempty():
    text = docs_vector_brief(max_chars=1200)
    assert "docs/" in text
    assert "NOW" in text or "тело" in text.lower() or "Unity" in text


def test_reflect_voice_minimal():
    assert "Вью" in REFLECT_VOICE
    assert "раскован" in REFLECT_VOICE.lower()
    assert "comfy_mocap" not in REFLECT_VOICE
    assert "запрещ" not in REFLECT_VOICE.lower()


def test_banned_generic_animation_hedge_not_filtered():
    bad = (
        "У меня есть базовые знания о Cascadeur, так что я могу помочь. "
        "Для более сложных проектов может потребоваться привлечение специалиста."
    )
    assert reflect_reply_issues(bad) == []


def test_reflect_notes_include_capability(tmp_path, monkeypatch):
    monkeypatch.setenv("VIU_DATA_DIR", str(tmp_path / ".viu"))
    cfg = Config(root=tmp_path, data_dir=tmp_path / ".viu").ensure_dirs()
    notes = build_reflect_notes(cfg, user_text="чем занимаешься сейчас")
    assert "тело" in notes.lower() or "body_pipeline" in notes or "NOW" in notes or "Comfy" in notes


def test_reflect_notes_include_comfy_trigger(tmp_path, monkeypatch):
    monkeypatch.setenv("VIU_DATA_DIR", str(tmp_path / ".viu"))
    cfg = Config(root=tmp_path, data_dir=tmp_path / ".viu").ensure_dirs()
    notes = build_reflect_notes(
        cfg, user_text="сгенерируй мне это видео в ComfyUi"
    )
    assert "триггер" in notes.lower() or "ComfyUI" in notes
    assert "камер" in notes.lower()


def test_reflect_bare_injects_comfy_on_user_when_no_system(tmp_path, monkeypatch):
    from viu.agent import Agent
    from viu.llm.mock import MockLLM

    monkeypatch.setenv("VIU_REFLECT_NO_SYSTEM", "1")
    seen: list[list[dict]] = []

    class CaptureLLM(MockLLM):
        def complete(self, messages, *, temperature=None, model=None):
            seen.append(list(messages))
            return '{"thought":"ok","final":"Comfy сейчас на паузе — сначала тело."}'

    agent = Agent(
        llm=CaptureLLM(),
        config=Config(root=tmp_path, data_dir=tmp_path / ".viu").ensure_dirs(),
    )
    agent.run_reflect("сгенерируй видео в ComfyUi, у тебя есть доступ")
    assert seen
    user = seen[0][-1]["content"]
    assert "ComfyUi" in user or "Comfy" in user
    assert "триггер" in user.lower() or "пайплайн" in user.lower()
    assert "system" not in [m["role"] for m in seen[0]]


def test_resolve_model_roles(tmp_path):
    cfg = Config(
        root=tmp_path,
        data_dir=tmp_path / ".viu",
        model="base:70b",
        model_reflect="dolphin:70b",
        model_work="qwen:32b",
        model_code="coder:32b",
    )
    assert resolve_model(cfg, "reflect") == "dolphin:70b"
    assert resolve_model(cfg, "work") == "qwen:32b"
    assert resolve_model(cfg, "code") == "coder:32b"
    assert resolve_model(cfg, "default") is None


def test_guess_work_role():
    assert guess_work_role("почини traceback в unity") == "code"
    assert guess_work_role("следующий шаг оверлей") == "work"
