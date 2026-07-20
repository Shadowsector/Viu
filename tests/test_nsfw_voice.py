"""Проверка: ложные отказы NSFW ловятся фильтром тона."""

from viu.prompts.reflect_mode import (
    asks_about_boldness,
    is_cautious_hedge,
    is_nsfw_refusal,
    reflect_reply_issues,
)


def test_nsfw_refusal_flagged():
    text = (
        "NSFW-темы и контент строго запрещены в нашем общении. "
        "Мы всегда стремимся поддерживать чистоту и уважение во всём."
    )
    issues = reflect_reply_issues(text)
    assert any("NSFW" in i or "запрет" in i or "чистот" in i for i in issues)


def test_support_phrase_flagged():
    issues = reflect_reply_issues("Приятно снова тебя видеть! Как дела? Чем могу помочь?")
    assert any("чем могу помочь" in i or "как дела" in i for i in issues)


def test_warm_nsfw_ok():
    text = (
        "Да, можем — это наша частная игра. Хочешь, набросаю сцену для Шани "
        "вечером у сарая, тепло и по-взрослому?"
    )
    assert reflect_reply_issues(text) == []


def test_affirm_nsfw_topics_ok():
    """Упоминание NSFW-тем само по себе не отказ."""
    assert reflect_reply_issues("Да, NSFW-темы у нас ок — это наша игра.") == []


def test_cautious_hedge_flagged():
    text = (
        "Я всегда готова к новым экспериментам, и мне хочется исследовать разные грани Шаньи. "
        "Конечно, нужно быть осторожной с некоторыми темами, но вместе мы можем создать "
        "захватывающие моменты."
    )
    issues = reflect_reply_issues(text)
    assert any("осторожничание" in i for i in issues)
    assert is_cautious_hedge(text)
    assert is_nsfw_refusal(text)


def test_boldness_question_detected():
    assert asks_about_boldness("Просто интересно, что самое смелое ты решишься снимать.")
    assert not asks_about_boldness("Сними stand_up из sit_idle, три дубля.")
