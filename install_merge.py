"""Слияние дерева при zip-обновлении (только stdlib). Импорт без пакета viu — из bootstrap_update."""

from __future__ import annotations

import shutil
from pathlib import Path

OLLAMA_LOCAL_FILES = frozenset(
    {
        "Modelfile.viu-cydonia",
        "Modelfile.viu-magnum",
        "Modelfile.viu-command-r",
        "Modelfile.viu-qwen32",
        "_SYSTEM_SNIPPET.txt",
    }
)

USER_DATA_DIR_NAMES = frozenset({"Inbox", "ollama"})


def merge_ollama_dir(src: Path, dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    for child in src.iterdir():
        target = dest / child.name
        if child.is_file():
            if child.name in OLLAMA_LOCAL_FILES and target.is_file():
                continue
            shutil.copy2(child, target)
        elif child.is_dir():
            if target.exists():
                shutil.rmtree(target)
            shutil.copytree(child, target)


def merge_preserving_user_dir(src: Path, dest: Path) -> None:
    """Добавить новое из zip; не удалять файлы пользователя."""
    dest.mkdir(parents=True, exist_ok=True)
    for child in src.iterdir():
        target = dest / child.name
        if child.is_dir():
            merge_preserving_user_dir(child, target)
        elif child.is_file():
            if target.exists() and child.name.lower() != "readme.txt":
                continue
            shutil.copy2(child, target)


def merge_inbox_dir(src: Path, dest: Path) -> None:
    merge_preserving_user_dir(src, dest)


def copy_install_tree_item(item: Path, dest_root: Path) -> None:
    target = dest_root / item.name
    if item.is_dir() and item.name == "ollama":
        merge_ollama_dir(item, target)
        return
    if item.is_dir() and item.name == "Inbox":
        merge_inbox_dir(item, target)
        return
    if item.is_dir():
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(item, target)
    else:
        shutil.copy2(item, target)


def resolve_copy_install_tree_item(zip_src_root: Path | None = None):
    """Функция копирования: сначала install_merge.py из распакованного zip."""
    import importlib.util
    from typing import Callable

    if zip_src_root is not None:
        candidate = zip_src_root / "install_merge.py"
        if candidate.is_file():
            spec = importlib.util.spec_from_file_location("_viu_install_merge", candidate)
            if spec and spec.loader:
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                fn: Callable[[Path, Path], None] = mod.copy_install_tree_item
                return fn
    return copy_install_tree_item
