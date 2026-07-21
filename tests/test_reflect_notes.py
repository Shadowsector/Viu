"""Reflect notes tiering + meta NSFW questions."""

from viu.prompts.reflect_mode import asks_about_nsfw, is_meta_nsfw_boundary_question
from viu.situational_context import _needs_full_work_notes, build_reflect_notes


def test_meta_intimacy_not_nsfw_policy_question():
    q = "Почему такой осторожный ответ? Ты не хочешь говорить на интимные темы?"
    assert is_meta_nsfw_boundary_question(q)
    assert not asks_about_nsfw(q)


def test_can_we_nsfw_still_light_prompt():
    assert asks_about_nsfw("можно ли у нас NSFW в игре?")


def test_chat_notes_slimmer_than_work(tmp_path, monkeypatch):
    from viu.config import Config

    monkeypatch.setenv("VIU_DATA_DIR", str(tmp_path / ".viu"))
    data = tmp_path / ".viu"
    data.mkdir(parents=True)
    cfg = Config(data_dir=data)
    chat = build_reflect_notes(cfg, user_text="давай сцену в сарае, она озорная")
    work = build_reflect_notes(cfg, user_text="чем занимаешься, что делаешь сейчас")
    assert _needs_full_work_notes("чем занимаешься")
    assert not _needs_full_work_notes("давай сцену в сарае")
    if work:
        assert len(work) >= len(chat) or "CAPABILITY" in work or "PLOT" in work
