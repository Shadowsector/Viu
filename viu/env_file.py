"""Загрузка .env в os.environ (без сторонних пакетов)."""

from __future__ import annotations

import os
from pathlib import Path


def load_env_file(*roots: Path) -> None:
    """Читает KEY=VALUE из .env; не перезаписывает уже заданные переменные."""
    seen: set[Path] = set()
    for root in roots:
        if root is None:
            continue
        path = Path(root).expanduser().resolve() / ".env"
        if path in seen or not path.is_file():
            continue
        seen.add(path)
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value
