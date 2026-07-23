"""Inbox при zip-обновлении — не затирать файлы пользователя."""

from __future__ import annotations

import shutil
from pathlib import Path

# Подпапки Inbox — создаём из архива, содержимое пользователя не трогаем.
INBOX_SUBDIR_NAMES = frozenset({"creatures", "animations", "references", "cascadeur"})


def _copy_if_missing(src: Path, dest: Path) -> None:
    if dest.exists():
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest)


def merge_inbox_dir(src: Path, dest: Path) -> None:
    """Скопировать Inbox из архива: README и пустые подпапки; файлы пользователя сохранить."""
    dest.mkdir(parents=True, exist_ok=True)
    for child in src.iterdir():
        target = dest / child.name
        if child.is_file():
            if child.name.upper() == "README.TXT":
                _copy_if_missing(child, target)
            else:
                _copy_if_missing(child, target)
            continue
        if not child.is_dir():
            continue
        target.mkdir(parents=True, exist_ok=True)
        if child.name in INBOX_SUBDIR_NAMES:
            for sub in child.iterdir():
                sub_target = target / sub.name
                if sub.is_file():
                    if sub.name.upper() == "README.TXT":
                        _copy_if_missing(sub, sub_target)
                    else:
                        _copy_if_missing(sub, sub_target)
        else:
            # Неизвестная подпапка из архива — только добавить отсутствующее.
            for sub in child.rglob("*"):
                if not sub.is_file():
                    continue
                rel = sub.relative_to(child)
                sub_target = target / rel
                _copy_if_missing(sub, sub_target)
