"""Файл общего направления — идеи, сюжет, техника. Вью читает и дополняет."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from .config import Config

DEFAULT_VISION = """# Направление «Анабарра»

Файл для Вью и Дена: куда идём, идеи, не только roadmap.

## Сейчас в фокусе
- Сарай Old Stables: разметка props, потом prefab в Unity
- Оверлей: Шаня у панели задач

## Идеи (Вью дополняет)
- 

## Заметки Дена
- 

## Отложено
- 
"""


def vision_path(config: Config) -> Path:
    return config.data_dir / "vision.md"


def ensure_vision(config: Config) -> Path:
    config.ensure_dirs()
    path = vision_path(config)
    if not path.is_file():
        path.write_text(DEFAULT_VISION, encoding="utf-8")
    return path


def read_vision(config: Config, *, max_chars: int = 4000) -> str:
    path = ensure_vision(config)
    text = path.read_text(encoding="utf-8")
    if len(text) > max_chars:
        return "…\n" + text[-max_chars:]
    return text


def append_vision(config: Config, section: str, text: str) -> str:
    path = ensure_vision(config)
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    block = f"\n\n### {stamp} — {section.strip()}\n{text.strip()}\n"
    path.write_text(path.read_text(encoding="utf-8") + block, encoding="utf-8")
    return f"Добавила в vision.md ({section})"
