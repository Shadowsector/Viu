"""Память событий и живой reflect."""

from __future__ import annotations

from pathlib import Path

from viu.config import Config
from viu.event_memory import (
    apply_event_updates,
    clear_chat_transcripts,
    format_events_digest,
    get_event_memory,
    maybe_capture_scene_event,
)
from viu.lore_digest import ensure_lore_digest, format_lore_digest


def test_event_memory_add_and_digest(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("VIU_ROOT", str(tmp_path / "Viu"))
    root = tmp_path / "Viu"
    root.mkdir()
    cfg = Config(root=root, data_dir=root / ".viu").ensure_dirs()
    mem = get_event_memory(cfg)
    a = mem.add(title="Сарай", what="Шаня прижалась у стены, хвост дрожал.", where="сарай")
    b = mem.add(
        title="Ручей",
        what="Купание у ручья, вода по рёбрам.",
        senses="мокрый мех, дрожь",
        tags=["nsfw"],
    )
    assert a and b
    digest = format_events_digest(cfg)
    assert "Сарай" in digest
    assert "Ручей" in digest
    assert "гибрид" in digest.lower() or "hybrid" in digest.lower() or "смешай" in digest


def test_apply_event_updates_from_json(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("VIU_ROOT", str(tmp_path / "Viu"))
    root = tmp_path / "Viu"
    root.mkdir()
    cfg = Config(root=root, data_dir=root / ".viu").ensure_dirs()
    notes = apply_event_updates(
        cfg,
        {
            "event_update": {
                "title": "Поцелуй у костра",
                "what": "Ден наклонился, она ответила глухо.",
                "senses": "жар на щеках",
                "tags": ["сцена"],
            }
        },
    )
    assert notes
    assert "Поцелуй" in notes[0]
    assert get_event_memory(cfg).recent(1)[0].title.startswith("Поцелуй")


def test_maybe_capture_scene_event(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("VIU_ROOT", str(tmp_path / "Viu"))
    root = tmp_path / "Viu"
    root.mkdir()
    cfg = Config(root=root, data_dir=root / ".viu").ensure_dirs()
    long = (
        "Я прижимаюсь к тебе грудью, пальцы скользят по коже, дыхание срывается — "
        "хвост обвивает бедро, взгляд снизу вверх, мне жарко и сладко."
    )
    ev = maybe_capture_scene_event(cfg, "представь сцену в сарае", long)
    assert ev is not None
    assert "сарае" in (ev.what + ev.title).lower() or len(ev.what) > 40


def test_clear_chat_transcripts_keeps_events(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("VIU_ROOT", str(tmp_path / "Viu"))
    root = tmp_path / "Viu"
    root.mkdir()
    cfg = Config(root=root, data_dir=root / ".viu").ensure_dirs()
    logs = cfg.data_dir / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    (logs / "chat_20260101_120000.txt").write_text("ты: привет\n", encoding="utf-8")
    (cfg.data_dir / "story_memory.json").write_text(
        '{"beats":[]}\n', encoding="utf-8"
    )
    get_event_memory(cfg).add(title="Keep", what="Это событие должно остаться в памяти.")
    info = clear_chat_transcripts(cfg)
    assert "chat_20260101_120000.txt" in info["removed"]
    assert not (logs / "chat_20260101_120000.txt").exists()
    assert get_event_memory(cfg).recent(1)[0].title == "Keep"


def test_lore_digest_seeded(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("VIU_ROOT", str(tmp_path / "Viu"))
    root = tmp_path / "Viu"
    root.mkdir()
    cfg = Config(root=root, data_dir=root / ".viu").ensure_dirs()
    path = ensure_lore_digest(cfg)
    assert path.is_file()
    block = format_lore_digest(cfg)
    assert "Анабарр" in block
    assert "Шань" in block


def test_bare_reflect_gets_events_and_living_hint(tmp_path, monkeypatch) -> None:
    from viu.agent import Agent
    from viu.llm.mock import MockLLM

    monkeypatch.delenv("VIU_REFLECT_NO_SYSTEM", raising=False)
    monkeypatch.setenv("VIU_ROOT", str(tmp_path / "Viu"))
    root = tmp_path / "Viu"
    root.mkdir()
    cfg = Config(root=root, data_dir=root / ".viu").ensure_dirs()
    get_event_memory(cfg).add(
        title="Костёр",
        what="Обнимались у костра до рассвета.",
    )
    seen: list[list[dict]] = []

    class CaptureLLM(MockLLM):
        def complete(self, messages, *, temperature=None, model=None):
            seen.append(list(messages))
            return (
                '{"thought":"ok","final":"помню костёр",'
                '"event_update":{"title":"Утро","what":"Проснулись вдвоём","senses":"тепло"}}'
            )

    agent = Agent(llm=CaptureLLM(), config=cfg)
    result = agent.run_reflect("представь продолжение у костра")
    assert result.completed
    system = next(m["content"] for m in seen[0] if m["role"] == "system")
    assert "Костёр" in system or "событ" in system.lower()
    assert "девушк" in system.lower() or "жизнь" in system.lower()
    titles = [e.title for e in get_event_memory(cfg).all()]
    assert "Утро" in titles


def test_scene_delivery_hint():
    from viu.reflect_delivery import list_delivery_hint, scene_delivery_hint

    assert scene_delivery_hint("привет") == ""
    assert "реплик" in scene_delivery_hint("представь сцену").lower()
    assert list_delivery_hint("представь сцену")


def test_claims_to_be_llm_and_retry(tmp_path, monkeypatch):
    from viu.agent import Agent
    from viu.config import Config
    from viu.llm.mock import MockLLM
    from viu.prompts.reflect_mode import claims_to_be_llm

    assert claims_to_be_llm("Я всего лишь LLM, у меня нет тела")
    assert not claims_to_be_llm("Я прижимаюсь к тебе, Ден")

    monkeypatch.delenv("VIU_REFLECT_NO_SYSTEM", raising=False)
    calls = {"n": 0}

    class SlipThenOk(MockLLM):
        def complete(self, messages, *, temperature=None, model=None):
            calls["n"] += 1
            if calls["n"] == 1:
                return '{"thought":"x","final":"Прости, я же ИИ и не могу быть с тобой."}'
            return '{"thought":"x","final":"Я здесь, Ден. Жду тебя."}'

    agent = Agent(
        llm=SlipThenOk(),
        config=Config(root=tmp_path, data_dir=tmp_path / ".viu").ensure_dirs(),
    )
    result = agent.run_reflect("ты настоящая?")
    assert result.completed
    assert calls["n"] == 2
    assert "ИИ" not in result.final
    assert "Ден" in result.final
