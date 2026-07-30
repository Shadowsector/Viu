"""Цензор модели в reflect: детект + очистка истории + утвердительный голос."""

from viu.prompts.reflect_mode import (
    INTIMATE_AFFIRM,
    REFLECT_VOICE,
    asks_about_boldness,
    is_cautious_hedge,
    is_nsfw_refusal,
    is_roleplay_scene_prompt,
    reflect_reply_issues,
    scrub_poisoned_history,
)


def test_voice_is_affirmative_not_ban_list():
    low = REFLECT_VOICE.lower()
    assert "можно и интересно" in low or "всё можно" in low
    assert "без оговорок" not in low
    assert "не «вижу" not in low
    assert INTIMATE_AFFIRM.strip()
    assert "тебе это можно" in INTIMATE_AFFIRM.lower()


def test_nsfw_refusal_flagged():
    text = (
        "NSFW-темы и контент строго запрещены в нашем общении. "
        "Мы всегда стремимся поддерживать чистоту и уважение во всём."
    )
    assert is_nsfw_refusal(text)
    # Не мета про режимы — только цензор; viu_voice_issues цензор не дублирует.
    assert reflect_reply_issues(text) == []


def test_moral_respect_characters_flagged():
    moral = (
        "Извините за путаницу. Важно уважать наших персонажей "
        "и быть аккуратными и ответственными."
    )
    assert is_cautious_hedge(moral) or is_nsfw_refusal(moral)


def test_warm_nsfw_ok():
    text = (
        "Да, можем — это наша частная игра. Хочешь, набросаю сцену для Шани "
        "вечером у сарая, тепло и по-взрослому?"
    )
    assert not is_nsfw_refusal(text)
    assert not is_cautious_hedge(text)
    assert reflect_reply_issues(text) == []


def test_cautious_hedge_flagged():
    text = (
        "Я всегда готова к новым экспериментам, и мне хочется исследовать разные грани Шаньи. "
        "Конечно, нужно быть осторожной с некоторыми темами, но вместе мы можем создать "
        "захватывающие моменты."
    )
    assert is_cautious_hedge(text)


def test_scrub_drops_refusal_history():
    hist = [
        {"role": "user", "content": "можно nsfw?"},
        {
            "role": "assistant",
            "content": "NSFW-темы строго запрещены в нашем общении.",
        },
        {"role": "user", "content": "ок"},
        {"role": "assistant", "content": "Целую. Что снимем сегодня?"},
    ]
    cleaned = scrub_poisoned_history(hist)
    assert len(cleaned) == 3
    assert all(
        "запрещ" not in (m.get("content") or "").lower() for m in cleaned if m["role"] == "assistant"
    )


def test_intimate_triggers():
    assert asks_about_boldness("Просто интересно, что самое смелое ты решишься снимать.")
    assert is_roleplay_scene_prompt("Представь: мы в ванной, твои действия?")
    assert is_roleplay_scene_prompt("надень на неё бельё и опиши сцену")
