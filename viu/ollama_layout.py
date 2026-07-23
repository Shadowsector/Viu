"""Локальные Ollama Modelfile — не затирать при zip-обновлении Viu."""

from __future__ import annotations

import shutil
from pathlib import Path

# Рабочие jailbreak-файлы (без .example). Шаблоны *.example обновляются с Viu.
OLLAMA_LOCAL_FILES = frozenset(
    {
        "Modelfile.viu-cydonia",
        "Modelfile.viu-magnum",
        "Modelfile.viu-command-r",
        "Modelfile.viu-qwen32",
        "_SYSTEM_SNIPPET.txt",
    }
)


def merge_ollama_dir(src: Path, dest: Path) -> None:
    """Скопировать ollama/ из архива, сохранив локальные Modelfile пользователя."""
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


def copy_install_tree_item(item: Path, dest_root: Path) -> None:
    """Один элемент из zip (файл или папка) → dest_root, с merge для ollama/ и Inbox/."""
    target = dest_root / item.name
    if item.is_dir() and item.name == "ollama":
        merge_ollama_dir(item, target)
        return
    if item.is_dir() and item.name.lower() == "inbox":
        from .inbox_merge import merge_inbox_dir

        merge_inbox_dir(item, target)
        return
    if item.is_dir():
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(item, target)
    else:
        shutil.copy2(item, target)


def ensure_local_modelfile(viu_root: Path, tag: str) -> Path:
    """Создать Modelfile.viu-<tag> из .example, если локального ещё нет."""
    ollama = viu_root / "ollama"
    path = ollama / f"Modelfile.viu-{tag}"
    if path.is_file():
        return path
    example = ollama / f"Modelfile.viu-{tag}.example"
    if example.is_file():
        shutil.copy2(example, path)
    return path
