"""Сочинение квестов/зёрен + improve + ночь."""

from __future__ import annotations

from pathlib import Path

from viu.config import Config
from viu.event_memory import get_event_memory
from viu.self_compose import (
    compose_from_wish,
    format_compose_digest,
    load_store,
    maybe_night_think,
    promote_draft_to_quests,
    try_handle_compose_chat,
)


def _cfg(tmp_path: Path) -> Config:
    return Config(root=tmp_path, data_dir=tmp_path / ".viu").ensure_dirs()


def test_compose_quest_uses_memory_and_improve(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    get_event_memory(cfg).add(
        title="Рынок",
        what="Ру искала редкий гриб у торговца на опушке",
        who="Ру",
        tags=["игра"],
    )
    grain, reply = compose_from_wish(cfg, "Ру нужна редкость", context="game")
    assert grain.context == "game"
    assert "Цель:" in grain.body or "Цель:" in reply
    assert "Предлагаю:" in grain.improve
    assert "Anime" not in grain.body  # не промпт-цензор
    digest = format_compose_digest(cfg)
    assert "Зёрна" in digest
    assert grain.hook.split(":")[0] in digest or "квест" in digest.lower()


def test_chat_compose_and_canon(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    out = try_handle_compose_chat(cfg, "сочини квест: Оля снова наврала про дрова")
    assert out.handled
    assert "Оля" in out.message or "оля" in out.message.lower() or "Цель" in out.message
    out2 = try_handle_compose_chat(cfg, "в канон")
    assert out2.handled
    assert "QUESTS" in out2.message or "квест" in out2.message.lower()
    q = cfg.data_dir / "QUESTS.md"
    assert q.is_file()
    assert "Оля" in q.read_text(encoding="utf-8") or "дрова" in q.read_text(encoding="utf-8")


def test_night_think_once(tmp_path: Path, monkeypatch) -> None:
    cfg = _cfg(tmp_path)
    monkeypatch.setattr("viu.quiet_hours.in_quiet_hours", lambda _c: True)
    g1 = maybe_night_think(cfg)
    assert g1 is not None
    g2 = maybe_night_think(cfg)
    assert g2 is None
    data = load_store(cfg)
    assert data.get("night_last_day")
    assert any(x.get("source") == "night" for x in data.get("grains") or [])


def test_stale_praise_does_not_steal_chat(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    compose_from_wish(cfg, "дом", context="life")
    data = load_store(cfg)
    data["draft"]["ts"] = 1.0  # очень старый
    from viu.self_compose import save_store

    save_store(cfg, data)
    out = try_handle_compose_chat(cfg, "хорошо")
    assert not out.handled


def test_promote_life_grain_skips_quests(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    try_handle_compose_chat(cfg, "сочини историю: вспомнила наш вечер у окна")
    msg = promote_draft_to_quests(cfg)
    assert "личное" in msg.lower() or "QUESTS" not in msg or "не в QUESTS" in msg
