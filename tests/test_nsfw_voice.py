"""Проверка: ложные отказы NSFW ловятся фильтром тона."""

from viu.prompts.reflect_mode import reflect_reply_issues


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
