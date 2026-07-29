"""Живая Вью: не ассистент, lean на «как ты?»."""

from viu.prompts.reflect_mode import (
    lean_reflect_context,
    looks_like_assistant_bot,
    looks_like_context_poison,
    scrub_poisoned_history,
    user_is_casual_checkin,
    user_is_greeting,
    viu_voice_issues,
)


def test_casual_checkin_nu_kak_ty():
    assert user_is_casual_checkin("ну как ты?")
    assert user_is_casual_checkin("Как дела")
    assert lean_reflect_context("ну как ты?")
    assert not lean_reflect_context("давай придумаем сюжет про сарай и Шаню")


def test_greeting_still_works():
    assert user_is_greeting("привет")
    assert lean_reflect_context("привет, Вью")


def test_assistant_bot_slip_detected():
    bad = (
        "Я в норме, а ты?\n\n"
        "Только вот что-то не так... Я вижу у тебя сообщение 2026-07-20 23:41 — "
        "я не могу его прочитать. Не понимаю, это проблема с моей системой или что-то ещё.\n\n"
        "Если хочешь обсудить сценарий или предложить новую идею — давай!"
    )
    assert looks_like_assistant_bot(bad)
    issues = viu_voice_issues(bad, user_text="ну как ты?")
    assert any("ассистент" in i or "техподдерж" in i for i in issues)


def test_scrub_drops_bot_and_timestamp_poison():
    hist = [
        {"role": "user", "content": "привет"},
        {
            "role": "assistant",
            "content": "Проблема с моей системой, не могу прочитать сообщение.",
        },
        {"role": "user", "content": "2026-07-20 23:41"},
        {"role": "assistant", "content": "Норм, а ты как?"},
    ]
    cleaned = scrub_poisoned_history(hist)
    roles = [(m["role"], m["content"][:20]) for m in cleaned]
    assert ("user", "привет") in roles
    assert any(m["role"] == "assistant" and "Норм" in m["content"] for m in cleaned)
    assert not any("систем" in m["content"] for m in cleaned)
    assert not any(looks_like_context_poison(m["content"]) for m in cleaned)
