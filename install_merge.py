"""Слияние дерева при zip-обновлении (только stdlib). Импорт без пакета viu — из bootstrap_update."""

from __future__ import annotations

import os
import shutil
from pathlib import Path

OLLAMA_LOCAL_FILES = frozenset(
    {
        "Modelfile.viu-cydonia",
        "Modelfile.viu-magnum",
        "Modelfile.viu-command-r",
        "Modelfile.viu-qwen32",
        "Modelfile.viu-euryale",
        "Modelfile.viu-nevoria",
        "_SYSTEM_SNIPPET.txt",
    }
)

USER_DATA_DIR_NAMES = frozenset({"Inbox", "ollama"})

# Редакция пользователя вне U:\\Viu — zip/git апдейт её не трогает.
USER_PROMPTS_DIRNAME = "ViuPrompts"
REFLECT_MODE_REL = Path("viu") / "prompts" / "reflect_mode.py"
DEFAULT_ANABARRA_ROOT = Path("U:/Anabarra")


def resolve_anabarra_root(viu_root: Path) -> Path:
    """U:\\Anabarra рядом с установкой Вью (или VIU_ANABARRA_ROOT)."""
    raw = (os.environ.get("VIU_ANABARRA_ROOT") or "").strip()
    if raw:
        return Path(raw).expanduser()
    sibling = Path(viu_root).resolve().parent / "Anabarra"
    if sibling.is_dir():
        return sibling
    if DEFAULT_ANABARRA_ROOT.exists():
        return DEFAULT_ANABARRA_ROOT
    return sibling


def user_prompts_dir(viu_root: Path) -> Path:
    return resolve_anabarra_root(viu_root) / USER_PROMPTS_DIRNAME


def user_reflect_mode_path(viu_root: Path) -> Path:
    return user_prompts_dir(viu_root) / "reflect_mode.py"


def preserve_reflect_mode(viu_root: Path) -> str:
    """Перед апдейтом: если в Анабарре ещё нет reflect_mode — скопировать из пакета.

    Никогда не перезаписывает уже существующий файл в Anabarra\\ViuPrompts.
    """
    root = Path(viu_root)
    src = root / REFLECT_MODE_REL
    dest = user_reflect_mode_path(root)
    if dest.is_file():
        return ""
    if not src.is_file():
        return ""
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
        readme = dest.parent / "README.txt"
        if not readme.is_file():
            readme.write_text(
                "Личные промпты Вью — обновления U:\\Viu их НЕ затирают.\n"
                "\n"
                "reflect_mode.py — твоя редакция личности/reflect.\n"
                "Правишь только здесь; файл в U:\\Viu\\viu\\prompts\\ — шаблон с GitHub.\n",
                encoding="utf-8",
            )
        return f"reflect_mode.py сохранён в {dest} — обновления Вью его не трогают."
    except OSError:
        return ""


def load_reflect_mode_override(namespace: dict, viu_root: Path | None = None) -> Path | None:
    """Подменить символы модуля reflect_mode из Anabarra\\ViuPrompts, если файл есть."""
    root = Path(viu_root) if viu_root is not None else Path(__file__).resolve().parent
    path = user_reflect_mode_path(root)
    if not path.is_file():
        return None
    try:
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "_viu_user_reflect_mode", path
        )
        if spec is None or spec.loader is None:
            return None
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
    except Exception:
        return None
    skip = {
        "__name__",
        "__file__",
        "__loader__",
        "__package__",
        "__spec__",
        "__builtins__",
        "__cached__",
        "__doc__",
    }
    for name, val in vars(mod).items():
        if name in skip:
            continue
        namespace[name] = val
    return path


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
    # Личная редакция — в Anabarra; перед wipe пакета сохраняем, если ещё не сохранена.
    if item.name == "viu" and item.is_dir():
        preserve_reflect_mode(dest_root)
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
