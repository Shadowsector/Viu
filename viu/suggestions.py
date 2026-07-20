"""Внутренний дневник Вью — мысли о сюжете, квестах, Дене (локально в .viu/)."""

from __future__ import annotations

import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from .config import Config

SUGGESTIONS_NAME = "SUGGESTIONS.md"

DEFAULT_SUGGESTIONS = """# SUGGESTIONS — внутренний дневник Вью

**Локально** в `.viu/`, не на GitHub. Сюда Вью дописывает мысли о сюжете, квестах, сценах и Дене.
Не обязательно читать — это след её присутствия. В чате она иногда цитирует себя короткой репликой (`aside`).

Править вручную: Места → «Заметки Вью (SUGGESTIONS)».

---

"""


def suggestions_path(config: Config) -> Path:
    return config.data_dir / SUGGESTIONS_NAME


def ensure_suggestions(config: Config) -> Path:
    path = suggestions_path(config)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.is_file():
        path.write_text(DEFAULT_SUGGESTIONS, encoding="utf-8")
    return path


def _read(path: Path, *, max_chars: int) -> str:
    if not path.is_file():
        return ""
    text = path.read_text(encoding="utf-8", errors="replace").strip()
    if len(text) > max_chars:
        return "…\n" + text[-max_chars:]
    return text


def read_suggestions(config: Config, *, max_chars: int = 1600) -> str:
    return _read(ensure_suggestions(config), max_chars=max_chars)


def append_suggestion(config: Config, chunk: str, *, tag: str = "") -> str:
    path = ensure_suggestions(config)
    chunk = (chunk or "").strip()
    if not chunk:
        return "пусто — не записала"
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    label = f" [{tag}]" if tag else ""
    with path.open("a", encoding="utf-8") as f:
        f.write(f"\n## {stamp}{label}\n\n{chunk}\n")
    return f"заметка в {path.name} ({len(chunk)} зн.)"


def _thought_worth_saving(thought: str) -> bool:
    t = (thought or "").strip()
    if len(t) < 24:
        return False
    low = t.lower()
    if low.startswith("json") or "thought" in low[:40]:
        return False
    return True


def apply_suggestion_updates(
    config: Config,
    parsed: dict | None,
    *,
    thought: str = "",
    user_text: str = "",
) -> list[str]:
    """suggestion_update + отфильтрованный thought → SUGGESTIONS.md."""
    notes: list[str] = []
    explicit = str((parsed or {}).get("suggestion_update") or "").strip()
    if explicit:
        notes.append(append_suggestion(config, explicit, tag="модель"))
    elif _thought_worth_saving(thought):
        try:
            from .plot_canvas import looks_like_plot_design
            from .story_memory import looks_like_story_chat

            if looks_like_story_chat(user_text) or looks_like_plot_design(user_text):
                notes.append(append_suggestion(config, thought.strip(), tag="размышление"))
        except ImportError:
            pass
    return notes


def open_suggestions(config: Config) -> tuple[bool, str]:
    path = ensure_suggestions(config)
    try:
        if sys.platform == "win32":
            os.startfile(str(path))  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(path)])
        else:
            subprocess.Popen(["xdg-open", str(path)])
    except OSError as exc:
        return False, f"Не открыла редактор ({exc}). Файл: {path}"
    return True, f"Открыла: {path}"


def suggestions_has_substance(config: Config) -> bool:
    text = read_suggestions(config, max_chars=8000)
    for ln in text.splitlines():
        s = ln.strip()
        if s.startswith("## ") and not s.endswith("---"):
            return True
    return False
