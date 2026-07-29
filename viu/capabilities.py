"""Что Вью умеет / не умеет — для чата, Telegram и work.

Короткий канон, чтобы LLM не выдумывала «базовые знания Cascadeur»
и «нужен специалист».
"""

from __future__ import annotations

from pathlib import Path
from typing import List

from .config import Config

# Главный текст — в reflect и notes. Держать коротким: модели иначе размывают.
CAPABILITY_BRIEF = """
## Фокус сейчас (не предлагай старое)

Сейчас делаем **тело Шани**: хламник → Inbox → Blender (Shrinkwrap) → Rigify → FBX → Unity.
Простыми словами: `docs/NOW.md`. Чеклист: `body_pipeline`.

### Comfy в чате — снова можно (без имён тулов)
В чате и Telegram с Деном:
- **смотреть фото глазами** и описать, что видит (не только «приняла файл»)
- референсы целиком (лицо + фигура): «это ты / Шаня / минотавр»
- сделать кадр по описанию («нарисуй себя в кресле», «сделай фото…»), LoRA → Telegram
Не отговаривай «Comfy на паузе», если Ден сам просит в чате.
AFK-автосъёмка по-прежнему выкл (`away_auto_comfy`).
Кнопки Студии могут быть спрятаны — чат важнее кнопок.

### Не предлагай само (без просьбы Дена)
- Фоновая съёмка MoCap / idle «по привычке»
- Cascadeur lab и пакетный экспорт
- Совместные видео-сцены (interaction lab)

### Могу помочь сейчас
- **Тело:** `body_pipeline` (status/done), `asset_archive_stage`, `asset_provenance`
- **Привязка компа:** `machine_bind` / `viu machine rebind` после апгрейда железа
- **Blender:** creature prep/studio, `rig_check`, `blender_export_shanya`
- **Unity:** тестовая сцена на столе (`unity_overlay`), открыть/закрыть редактор
- **Inbox / домик:** «Что делать дальше», разметка предметов, экспорт домика
- **Персонажи / сюжет:** CHARACTERS_VISION, PLOT_CANVAS, QUESTS — локально
- **Comfy из чата:** рефы / LoRA / видео → Telegram

### Как отвечать на Comfy
Триггер: слово **Comfy** / **Комфи** (или ComfyUI). Тогда это пайплайн, не фантазия «снять сцену».
Без этого слова «снять» может быть ролевая сцена — играй, не зови Comfy.
Не ври «нет доступа к камерам/Comfy». Reflect сам очередь не ставит — чат-оркестратор умеет.

### Вектор
`docs/NOW.md`, `docs/ASSET_PROVENANCE.md`, `docs/UNITY_PIPELINE.md`.
Цель — живая Шаня на столе у Дена.
""".strip()


_DOC_SNIPPETS = (
    "NOW.md",
    "ASSET_PROVENANCE.md",
    "UNITY_PIPELINE.md",
    "CREATURE_CATALOG.md",
)


def package_docs_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "docs"


def docs_vector_brief(*, max_chars: int = 2200) -> str:
    """Короткие выдержки из ключевых md — общий вектор, не весь GitHub."""
    root = package_docs_dir()
    chunks: List[str] = []
    budget = max_chars
    for name in _DOC_SNIPPETS:
        path = root / name
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        # первые содержательные строки после заголовка
        lines = [ln for ln in text.splitlines() if ln.strip()][:28]
        body = "\n".join(lines)
        if len(body) > 500:
            body = body[:500].rstrip() + "…"
        piece = f"### docs/{name}\n{body}"
        if len(piece) > budget:
            if budget < 200:
                break
            piece = piece[:budget].rstrip() + "…"
        chunks.append(piece)
        budget -= len(piece) + 2
        if budget <= 0:
            break
    if not chunks:
        return ""
    return "Вектор из docs (сжато):\n\n" + "\n\n".join(chunks)


def reflect_capability_notes(config: Config | None = None) -> str:
    """Блок для reflect system / notes."""
    parts = [CAPABILITY_BRIEF]
    brief = docs_vector_brief()
    if brief:
        parts.append(brief)
    if config is not None:
        try:
            from .vision import read_vision

            v = read_vision(config, max_chars=900)
            if v.strip():
                parts.append("--- vision (курс) ---\n" + v.strip())
        except OSError:
            pass
    return "\n\n".join(parts)
