"""Reflect/work filter: chat notes vs full; history scrub without speech bans."""

from viu.prompts.reflect_mode import (
    looks_like_log_artifact,
    scrub_poisoned_history,
    user_is_greeting,
)
from viu.situational_context import _needs_full_work_notes, build_reflect_notes
from viu.config import Config


def test_nu_kak_ty_is_chat_not_full_work_notes():
    assert not _needs_full_work_notes("ну как ты?")
    assert not _needs_full_work_notes("как дела")
    assert _needs_full_work_notes("следующий шаг")
    assert _needs_full_work_notes("дырка в графе анимаций")


def test_build_reflect_notes_chat_is_brief(tmp_path, monkeypatch):
    monkeypatch.setenv("VIU_ROOT", str(tmp_path / "Viu"))
    root = tmp_path / "Viu"
    root.mkdir()
    cfg = Config(root=root, data_dir=root / ".viu").ensure_dirs()
    notes = build_reflect_notes(cfg, user_text="ну как ты?")
    assert "Шанька" in notes or "Вью" in notes
    # Не work-дамп пайплайна
    assert "Подсказка режиссёра" not in notes
    assert "Unity Editor" not in notes


def test_scrub_drops_log_artifacts_only():
    hist = [
        {"role": "user", "content": "привет"},
        {"role": "assistant", "content": "Привет, Ден!"},
        {"role": "user", "content": "2026-07-20 23:41"},
        {"role": "user", "content": "система: что-то"},
    ]
    cleaned = scrub_poisoned_history(hist)
    assert len(cleaned) == 2
    assert cleaned[0]["content"] == "привет"
    assert looks_like_log_artifact("2026-07-20 23:41")
    assert not user_is_greeting("ну как ты?")  # это не «привет», а обычный reflect-чат
