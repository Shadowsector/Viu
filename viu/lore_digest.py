"""Короткий лор Анабарры для reflect — не раздувает REFLECT_VOICE.

Файл: .viu/LORE_DIGEST.md (Ден правит сам; переживает апдейт).
"""

from __future__ import annotations

from pathlib import Path

from .config import Config

LORE_DIGEST_NAME = "LORE_DIGEST.md"

DEFAULT_LORE_DIGEST = """# Лор Анабарры (кратко)

Править свободно. Вью читает кусок в чате — не весь учебник.

## Мир
- Анабарра — страна Шаньки; дома ей тепло, без тоски по «другому миру».
- Биомы (допиши): леса, сарай/старые конюшни у границы, …

## Существа
- **Шанька** — табакси (уши, хвост, томбой, азарт, странная логика).
- Другие (допиши имена, вид, нрав):

## Тон NSFW в лоре
- Тёплый, от чувств; без чернухи «для всех».
- Вью сочиняет приключения; удачные биты помнит как **события** и может смешивать.

## Не путать
- Вью — девушка у экрана, соавтор.
- Шаня — проекция в игре.
"""


def lore_digest_path(config: Config) -> Path:
    return Path(config.data_dir) / LORE_DIGEST_NAME


def ensure_lore_digest(config: Config) -> Path:
    config.ensure_dirs()
    path = lore_digest_path(config)
    if not path.is_file():
        path.write_text(DEFAULT_LORE_DIGEST, encoding="utf-8")
    return path


def format_lore_digest(config: Config, *, max_chars: int = 1200) -> str:
    path = ensure_lore_digest(config)
    try:
        text = path.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return ""
    if not text:
        return ""
    # убрать заголовок-инструкцию первой строки если длинно
    if len(text) > max_chars:
        text = text[:max_chars].rstrip() + "\n…"
    return "--- Лор Анабарры (опирайся; не зачитывай списком) ---\n" + text
