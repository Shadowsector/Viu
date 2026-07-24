"""Локальные Ollama Modelfile — не затирать при zip-обновлении Viu."""

from __future__ import annotations

import shutil
from pathlib import Path

from install_merge import (
    OLLAMA_LOCAL_FILES,
    copy_install_tree_item,
    merge_inbox_dir,
    merge_ollama_dir,
    merge_preserving_user_dir,
)

__all__ = [
    "OLLAMA_LOCAL_FILES",
    "copy_install_tree_item",
    "merge_inbox_dir",
    "merge_ollama_dir",
    "merge_preserving_user_dir",
    "ensure_local_modelfile",
]


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
