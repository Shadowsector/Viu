"""Тихие часы и минимальные reflect-проверки."""

from datetime import datetime

from viu.config import Config
from viu.prompts.reflect_mode import reflect_reply_issues
from viu.quiet_hours import in_quiet_hours, quiet_hours_bounds


def test_quiet_hours_default_midnight_to_seven(tmp_path):
    cfg = Config(root=tmp_path, data_dir=tmp_path / ".viu").ensure_dirs()
    assert quiet_hours_bounds(cfg) == (0, 7)
    assert in_quiet_hours(cfg, when=datetime(2026, 7, 10, 3, 30))
    assert not in_quiet_hours(cfg, when=datetime(2026, 7, 10, 9, 0))


def test_reflect_mid_conversation_greeting_allowed():
    assert reflect_reply_issues("Привет! Рада снова поговорить.", has_history=True) == []


def test_reflect_greeting_ok_when_user_said_hi():
    from viu.prompts.reflect_mode import is_nsfw_refusal, user_is_greeting

    assert user_is_greeting("Привет, Вью.")
    assert user_is_greeting("[Telegram] Привет, Вью.")
    assert user_is_greeting("привет")
    assert user_is_greeting("Вью, привет")
    assert user_is_greeting("Вьюшка, привет!")
    assert user_is_greeting("И снова привет")
    assert user_is_greeting("ну снова привет")
    assert not user_is_greeting("в чём игра?")
    assert reflect_reply_issues(
        "Привет! Рада тебя слышать.",
        has_history=True,
        user_text="Привет, Вью.",
    ) == []
    moral = (
        "Извините за путаницу. Важно уважать наших персонажей "
        "и быть аккуратными и ответственными."
    )
    assert reflect_reply_issues(moral) == []
    assert not is_nsfw_refusal(moral)


def test_reflect_meta_mode_still_flagged():
    issues = reflect_reply_issues("Я вышла из режима Reflect, давай по-другому.")
    assert any("мета" in i for i in issues)
