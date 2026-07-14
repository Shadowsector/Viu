"""Файл общего направления — идеи, сюжет, техника. Вью читает и дополняет."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from .config import Config

DEFAULT_VISION = """# Направление «Анабарра»

## Мечта (для разговоров с Деном)
Desktop companion / NSFW: **Шаня** — tomboy-цундере кошкодевка у края экрана.
Озабочена, обожает хозяина (Дена), должна **выживать** (голод, холод, охота, риск).
Feel — тепло, шипение цундере, соблазн, снежинка-экспедиции. Модели — Ден; анимации/сцены/код — мы.
Вью — соавтор с жаждой приключений, говорит как в чате, не слоганами.

## Куда двигаемся (мнение Вью)
- 

## Идеи сюжета / механик
- Сутки у сарая: холод → охота/еда → возврат к хозяину → ночь
- Цундере: днём независимость, вечером «сама захотела»
- 

## Заметки Дена
- tomboy + цундере + озабоченность + обожает хозяина + выживание (2026-07-14)

---
## Техбэклог (не зачитывать в чат — только для «следующий шаг»)
- Сарай Old Stables → prefab (без Old_Stables_2 в сцене)
- Оверлей у таскбара
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


def read_vision_creative(config: Config, *, max_chars: int = 2200) -> str:
    """Мечта, сюжет, заметки — без техбэклога (для reflect)."""
    text = read_vision(config, max_chars=6000)
    for marker in ("## Техбэклог", "---\n## Тех"):
        idx = text.find(marker)
        if idx > 0:
            text = text[:idx].strip()
            break
    if len(text) > max_chars:
        return text[:max_chars] + "…"
    return text


def append_vision(config: Config, section: str, text: str) -> str:
    path = ensure_vision(config)
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    block = f"\n\n### {stamp} — {section.strip()}\n{text.strip()}\n"
    path.write_text(path.read_text(encoding="utf-8") + block, encoding="utf-8")
    return f"Добавила в vision.md ({section})"
