"""Тесты карты возможностей и ролей LLM."""

from __future__ import annotations

from pathlib import Path

from viu.capabilities import CAPABILITY_BRIEF, docs_vector_brief, reflect_capability_notes
from viu.config import Config
from viu.llm_roles import guess_work_role, resolve_model
from viu.prompts.reflect_mode import REFLECT_SYSTEM, reflect_reply_issues
from viu.situational_context import build_reflect_notes


def test_capability_brief_mentions_pipeline():
    assert "Comfy" in CAPABILITY_BRIEF
    assert "Cascadeur" in CAPABILITY_BRIEF
    assert "специалист" in CAPABILITY_BRIEF or "базовые знания" in CAPABILITY_BRIEF
    assert "cascadeur_import_reference" in CAPABILITY_BRIEF


def test_docs_vector_brief_nonempty():
    text = docs_vector_brief(max_chars=1200)
    assert "docs/" in text
    assert "COMFY" in text or "Cascadeur" in text or "CASCADEUR" in text


def test_reflect_system_has_capability():
    assert "Cascadeur MoCap" in REFLECT_SYSTEM or "comfy_mocap" in REFLECT_SYSTEM
    assert "специалист" in REFLECT_SYSTEM


def test_banned_generic_animation_hedge():
    bad = (
        "У меня есть базовые знания о Cascadeur, так что я могу помочь. "
        "Для более сложных проектов может потребоваться привлечение специалиста."
    )
    issues = reflect_reply_issues(bad)
    assert issues, "должны ловить шаблонный отказ"


def test_reflect_notes_include_capability(tmp_path, monkeypatch):
    monkeypatch.setenv("VIU_DATA_DIR", str(tmp_path / ".viu"))
    cfg = Config(root=tmp_path, data_dir=tmp_path / ".viu").ensure_dirs()
    notes = build_reflect_notes(cfg)
    assert "Comfy" in notes
    assert "Cascadeur" in notes


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
