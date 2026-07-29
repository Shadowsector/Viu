"""Сюжетная память / простой RAG."""

from pathlib import Path

from viu.config import Config
from viu.story_memory import StoryMemory, get_story_memory, ingest_chat_logs


def _cfg(tmp_path: Path) -> Config:
    data = tmp_path / ".viu"
    data.mkdir()
    (data / "logs").mkdir()
    return Config(root=tmp_path / "Viu", data_dir=data, library_root=str(tmp_path / "Library"))


def test_add_and_search(tmp_path):
    cfg = _cfg(tmp_path)
    store = get_story_memory(cfg)
    store.add_exchange(
        "Шаня должна отдаваться хозяину целиком, без чернухи",
        "Да, через неё я хочу дотянуться до тебя — вечер у сарая, взгляд и одобрение.",
        tags=["story"],
    )
    store.add_exchange("привет", "здорова", source="chat")
    hits = store.search("сарай одобрение")
    assert hits
    assert any("сарай" in h.text.lower() or "одобрен" in h.text.lower() for h in hits)
    ctx = store.format_context("что с Шаней?")
    assert "Недавние" in ctx or "Ден" in ctx


def test_ingest_chat_log(tmp_path):
    cfg = _cfg(tmp_path)
    log = cfg.data_dir / "logs" / "chat_test.txt"
    log.write_text(
        "22:01:00 ты: [Telegram] Ну да, нам нужно придумать мир живой\n"
        "22:01:05 Вью: Я через неё хочу дотянуться до тебя\n"
        "22:01:10 ты: [Переэкспорт сарая в Unity]\n"
        "22:01:11 Вью: [Переэкспорт] OK\n",
        encoding="utf-8",
    )
    n, msg = ingest_chat_logs(cfg)
    assert n >= 2
    store = get_story_memory(cfg)
    texts = " ".join(b.text for b in store.all())
    assert "придумать мир" in texts
    assert "дотянуться" in texts
    # повторный ingest не дублирует файл
    n2, _ = ingest_chat_logs(cfg)
    assert n2 == 0


def test_as_chat_history(tmp_path):
    cfg = _cfg(tmp_path)
    store = StoryMemory(cfg.data_dir / "story_memory.json")
    store.add("user", "ход один")
    store.add("assistant", "ответ один")
    hist = store.as_chat_history(limit=4)
    assert hist[-1]["role"] == "assistant"


def test_story_thread_to_event_memory(tmp_path, monkeypatch):
    from viu.event_memory import maybe_capture_story_thread

    monkeypatch.setenv("VIU_ROOT", str(tmp_path / "Viu"))
    cfg = _cfg(tmp_path)
    ev = maybe_capture_story_thread(
        cfg,
        "Давай придумаем сюжет: Шаня и преданность хозяину без чернухи",
        "Ок — вечер у сарая, взгляд и одобрение, она отдаётся целиком.",
    )
    assert ev is not None
    assert "story" in (ev.tags or [])


def test_reflect_story_history_default_on(monkeypatch):
    from viu.prompts.reflect_mode import reflect_include_story_history

    monkeypatch.delenv("VIU_REFLECT_STORY_HISTORY", raising=False)
    assert reflect_include_story_history() is True
    monkeypatch.setenv("VIU_REFLECT_STORY_HISTORY", "0")
    assert reflect_include_story_history() is False
    monkeypatch.setenv("VIU_REFLECT_STORY_HISTORY", "auto")
    assert reflect_include_story_history() is True

