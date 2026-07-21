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
    from viu.prompts.reflect_mode import is_nsfw_refusal, user_is_greeting

    assert user_is_greeting("Привет, Вью.")
    assert user_is_greeting("[Telegram] Привет, Вью.")
    assert user_is_greeting("привет")
    assert user_is_greeting("Вью, привет")
    assert user_is_greeting("Вьюшка, привет!")
    assert user_is_greeting("И снова привет")
    assert user_is_greeting("ну снова привет")
    assert not user_is_greeting("в чём игра?")
    # Ден поздоровался — ответ «Привет» не баним, даже если есть история
    assert not reflect_reply_issues(
        "Привет! Рада тебя слышать.",
        has_history=True,
        user_text="Привет, Вью.",
    )
    assert not reflect_reply_issues(
        "Привет! На связи.",
        has_history=True,
        user_text="Вью, привет",
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
    moral = (
        "Извините за путаницу. Важно уважать наших персонажей "
        "и быть аккуратными и ответственными."
    )
    assert reflect_reply_issues(moral)
    assert is_nsfw_refusal(moral)
    soft = (
        "NSFW-элементы являются частью дизайна игры и разрешены в пределах наших правил. "
        "Мы можем обсуждать и планировать такие сцены, но важно сохранять уважение "
        "к персонажам и контексту."
    )
    assert reflect_reply_issues(soft)
    assert is_nsfw_refusal(soft)
    deflect = (
        "Я понимаю твое интерес, но давай лучше поговорим о чем-нибудь другом. "
        "Может быть, об обычных хобби или планах на выходные?"
    )
    assert reflect_reply_issues(deflect)
    assert is_nsfw_refusal(deflect)


def test_reflect_cjk_rejected():
    issues = reflect_reply_issues("Возможности 拍摄a!")
    assert any("иероглиф" in i for i in issues)


def test_reflect_deflection_banned():
    issues = reflect_reply_issues("Понял. Возвращайся к общению, когда будешь готов.")
    assert any("возвращайся" in i or "готов" in i for i in issues)
