"""Локальный CHARACTERS_VISION.md — характеры, отношения, интим.

Живёт только в data_dir (обычно U:\\Viu\\.viu\\), не в репозитории.
«Обновить Вью» и GitHub его не трогают. В support-zip не кладём.
Cursor: см. .cursorignore — облачным агентам файл не нужен.
Вью читает укороченный фрагмент в reflect (живой чат), не зачитывает вслух.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from .config import Config

CHARACTERS_VISION_NAME = "CHARACTERS_VISION.md"

# Только пустой каркас — без личных деталей Дена (их он допишет сам).
DEFAULT_CHARACTERS_VISION = """# CHARACTERS_VISION.md

**Важно:** файл внутренний. Лежит в `.viu/`, не на GitHub, не уезжает с «Обновить Вью».
Правишь сам (кнопка «Персонажи» во Вью). Вью читает для тона чата — не зачитывает тебе списком.

---

## Основные персонажи

### Шаня
**Типаж:**  
**История:**  
**Характер:**  
**Отношение к Дену:**  
**Сексуальность и предпочтения:**  
**Hitpoints / Состояние:**  

### Ру
**Типаж:**  
**История:**  
**Характер:**  
**Отношение к другим:**  
**Сексуальность и предпочтения:**  
**Hitpoints / Состояние:**  

### Оля
**Типаж:**  
**История:**  
**Характер:**  
**Отношение к другим:**  
**Сексуальность и предпочтения:**  
**Hitpoints / Состояние:**  

### Лили
**Типаж:**  
**История:**  
**Характер:**  
**Отношение к другим:**  
**Сексуальность и предпочтения:**  
**Hitpoints / Состояние:**  

### Шняк
**Типаж:**  
**История:**  
**Характер:**  
**Особенности:**  
**Сексуальность и предпочтения:**  
**Hitpoints / Состояние:**  

### Домовой
**Типаж:**  
**История:**  
**Характер:**  
**Особенности:**  
**Сексуальность и предпочтения:**  
**Hitpoints / Состояние:**  

## Приходящие гости / Второстепенные

> Копируй блок «Гость» ниже, сколько нужно.

### Гость 1 [Имя]
**Типаж:**  
**История появления:**  
**Характер:**  
**Отношение к основным девушкам:**  
**Сексуальность и предпочтения:**  
**Hitpoints / Состояние:**  

### Гость 2 [Имя]
**Типаж:**  
**История появления:**  
**Характер:**  
**Отношение к основным девушкам:**  
**Сексуальность и предпочтения:**  
**Hitpoints / Состояние:**  

### Гость 3 [Имя]
**Типаж:**  
**История появления:**  
**Характер:**  
**Отношение к основным девушкам:**  
**Сексуальность и предпочтения:**  
**Hitpoints / Состояние:**  

## Дополнительные заметки
- Общие правила взаимодействия между персонажами:
- Запреты и табу:
- Особые механики (например, влияние на Hitpoints):
"""


def characters_vision_path(config: Config) -> Path:
    return config.data_dir / CHARACTERS_VISION_NAME


def ensure_characters_vision(config: Config) -> Path:
    """Создать каркас, если файла ещё нет. Существующий не перезаписывать."""
    config.ensure_dirs()
    path = characters_vision_path(config)
    if not path.is_file():
        path.write_text(DEFAULT_CHARACTERS_VISION, encoding="utf-8")
    return path


def read_characters_vision(config: Config, *, max_chars: int = 3500) -> str:
    """Для reflect: укороченный текст. Пустые поля шаблона почти не занимают места."""
    path = ensure_characters_vision(config)
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return ""
    # выкинуть совсем пустые строки-заголовки без содержания — оставить смысл
    if len(text) > max_chars:
        return text[:max_chars] + "\n…"
    return text


def open_characters_vision(config: Config) -> tuple[bool, str]:
    """Открыть файл в системном редакторе (Блокнот / default)."""
    path = ensure_characters_vision(config)
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
