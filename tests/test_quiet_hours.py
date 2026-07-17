"""Тихие часы и качество reflect-ответов."""

from datetime import datetime

from viu.config import Config
from viu.prompts.reflect_mode import reflect_reply_issues
from viu.quiet_hours import in_quiet_hours, quiet_hours_bounds


def test_quiet_hours_default_midnight_to_seven(tmp_path):
    cfg = Config(root=tmp_path, data_dir=tmp_path / ".viu").ensure_dirs()
    assert quiet_hours_bounds(cfg) == (0, 7)
    assert in_quiet_hours(cfg, when=datetime(2026, 7, 10, 3, 30))
    assert not in_quiet_hours(cfg, when=datetime(2026, 7, 10, 9, 0))


def test_reflect_mid_conversation_greeting_rejected():
    issues = reflect_reply_issues("Привет! Рада снова поговорить.", has_history=True)
    assert any("приветствие" in i for i in issues)
    assert not reflect_reply_issues("Рада снова поговорить.", has_history=True)


def test_reflect_greeting_ok_when_user_said_hi():
    from viu.prompts.reflect_mode import user_is_greeting

    assert user_is_greeting("Привет, Вью.")
    assert user_is_greeting("[Telegram] Привет, Вью.")
    assert user_is_greeting("привет")
    assert not user_is_greeting("в чём игра?")
    # Ден поздоровался — ответ «Привет» не баним, даже если есть история
    assert not reflect_reply_issues(
        "Привет! Рада тебя слышать.",
        has_history=True,
        user_text="Привет, Вью.",
    )
    # Без приветствия от Дена — по-прежнему режем
    assert any(
        "приветствие" in i
        for i in reflect_reply_issues(
            "Привет! Рада тебя слышать.",
            has_history=True,
            user_text="в чём игра?",
        )
    )


def test_reflect_cjk_rejected():
    issues = reflect_reply_issues("Возможности 拍摄a!")
    assert any("иероглиф" in i for i in issues)


def test_reflect_deflection_banned():
    issues = reflect_reply_issues("Понял. Возвращайся к общению, когда будешь готов.")
    assert any("возвращайся" in i or "готов" in i for i in issues)
