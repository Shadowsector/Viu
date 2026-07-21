"""Локальная канва сюжета и квесты — не в GitHub, не в support-zip.

PLOT_CANVAS.md  — общая канва (арки, темы, табу, биты).
QUESTS.md       — отдельные квесты; каждый сверяется с канвой.

Вью читает оба в reflect-заметках. Обновляет через plot_update / quest_update
в JSON-ответе (см. reflect_mode) или правкой файла (Места → Канва / Квесты).
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

from .config import Config

PLOT_CANVAS_NAME = "PLOT_CANVAS.md"
QUESTS_NAME = "QUESTS.md"

# Только каркас — без сюжетных деталей Дена.
DEFAULT_PLOT_CANVAS = """# PLOT_CANVAS.md

**Важно:** файл внутренний (`.viu/`), не на GitHub, не уезжает с «Обновить Вью».
Общая канва сюжета Анабарры. Квесты и сцены **сверяй с этим файлом** — не выдумывай параллельную арку.

Править: Места → «Канва сюжета», или попроси Вью зафиксировать бит (она допишет сюда).

---

## Логлайн

(одно-два предложения — о чём игра)

## Тон и жанр

- 
- NSFW / эротика в сюжете: 

## Главные арки

1. 
2. 
3. 

## Текущий фокус (что в работе сейчас)

- 

## Открытые крючки / тайны

- 

## Табу и границы (не ломать)

- 

## Связь с персонажами / существами

- (ссылайся на CHARACTERS_VISION и каталог существ, не копируй всё сюда)

## Заметки Дена

- 
"""

DEFAULT_QUESTS = """# QUESTS.md

**Важно:** локально в `.viu/`. Каждый квест должен **не противоречить** PLOT_CANVAS.md.

Шаблон — копируй блок «Квест» ниже.

---

### Квест: (название)
**Статус:** черновик | в работе | готов | отложен  
**Связь с канвой:** (какая арка / бит)  
**Цель:**  
**Старт / триггер:**  
**Шаги:**  
1.  
2.  
**Выборы (A/B):**  
**Награда / последствия:**  
**NSFW-бит (если есть):**  
**Заметки:**  

"""


def plot_canvas_path(config: Config) -> Path:
    return config.data_dir / PLOT_CANVAS_NAME


def quests_path(config: Config) -> Path:
    return config.data_dir / QUESTS_NAME


def ensure_plot_canvas(config: Config) -> Path:
    config.ensure_dirs()
    path = plot_canvas_path(config)
    if not path.is_file():
        path.write_text(DEFAULT_PLOT_CANVAS, encoding="utf-8")
    return path


def ensure_quests(config: Config) -> Path:
    config.ensure_dirs()
    path = quests_path(config)
    if not path.is_file():
        path.write_text(DEFAULT_QUESTS, encoding="utf-8")
    return path


def _read(path: Path, *, max_chars: int) -> str:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return ""
    if len(text) > max_chars:
        return text[:max_chars] + "\n…"
    return text


def canvas_has_substance(text: str) -> bool:
    """Есть ли заполненные строки кроме заголовков каркаса."""
    skip_substrings = (
        "файл внутренний",
        "не на github",
        "общая канва",
        "квесты и сцены",
        "править:",
        "места →",
        "одно-два предложения",
        "ссылайся на characters",
        "копируй блок",
        "каждый квест",
        "шаблон —",
    )
    for ln in text.splitlines():
        s = ln.strip()
        if not s:
            continue
        if s.startswith("#") or s.startswith("**Важно") or s == "---":
            continue
        if s.startswith("## ") or s.startswith("### "):
            continue
        if s in ("-", "1.", "2.", "3."):
            continue
        low = s.lower()
        if any(x in low for x in skip_substrings):
            continue
        if s.endswith(":") and len(s) < 48:
            continue
        body = re.sub(r"^[\-\d\.\)\*]+\s*", "", s).strip()
        if body.startswith("(") or body.endswith(")"):
            continue
        if len(body) >= 12:
            return True
    return False


def read_plot_canvas(config: Config, *, max_chars: int = 4500) -> str:
    path = ensure_plot_canvas(config)
    return _read(path, max_chars=max_chars)


def read_quests(config: Config, *, max_chars: int = 3500) -> str:
    path = ensure_quests(config)
    return _read(path, max_chars=max_chars)


def append_plot_canvas(config: Config, chunk: str) -> str:
    """Дописать фрагмент в конец канвы (с разделителем)."""
    path = ensure_plot_canvas(config)
    chunk = (chunk or "").strip()
    if not chunk:
        return "пусто — не записала"
    with path.open("a", encoding="utf-8") as f:
        f.write("\n\n## Обновление\n\n")
        f.write(chunk)
        f.write("\n")
    return f"канва дополнена ({len(chunk)} зн.) → {path.name}"


def append_quests(config: Config, chunk: str) -> str:
    path = ensure_quests(config)
    chunk = (chunk or "").strip()
    if not chunk:
        return "пусто — не записала"
    with path.open("a", encoding="utf-8") as f:
        f.write("\n\n")
        f.write(chunk)
        f.write("\n")
    return f"квесты дополнены ({len(chunk)} зн.) → {path.name}"


def apply_reflect_updates(config: Config, parsed: dict) -> list[str]:
    """Из JSON reflect: plot_update / quest_update → файлы."""
    notes: list[str] = []
    plot_u = str(parsed.get("plot_update") or "").strip()
    quest_u = str(parsed.get("quest_update") or "").strip()
    if plot_u:
        notes.append(append_plot_canvas(config, plot_u))
    if quest_u:
        notes.append(append_quests(config, quest_u))
    return notes


def open_plot_canvas(config: Config) -> tuple[bool, str]:
    path = ensure_plot_canvas(config)
    return _open_file(path)


def open_quests(config: Config) -> tuple[bool, str]:
    path = ensure_quests(config)
    return _open_file(path)


def _open_file(path: Path) -> tuple[bool, str]:
    try:
        if sys.platform == "win32":
            os.startfile(str(path))  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(path)])
        else:
            subprocess.Popen(["xdg-open", str(path)])
    except OSError as exc:
        return False, f"Не открыла редактор ({exc}). Файл: {path}"
    return True, f"Открыла для правки: {path}\nСохрани (Ctrl+S) — Вью подхватит в следующем чате."


def looks_like_plot_design(user_text: str) -> bool:
    low = (user_text or "").lower()
    return bool(
        re.search(
            r"(сюжет|квест|арк[аиу]|канв|гдд|gdd|логлайн|ветк[аи]|диалогов|"
            r"сценари|геймдизайн|крючок|твист|финал\b|завязк)",
            low,
        )
    )
