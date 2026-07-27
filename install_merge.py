"""Слияние дерева при zip-обновлении (только stdlib). Импорт без пакета viu — из bootstrap_update."""

from __future__ import annotations

import ast
import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

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

# Только голос/промпт-строки. Функции, флаги env и фильтры — всегда из пакета.
# Иначе старый полный снимок в Anabarra после апдейта затирает фиксы (#85/#86/#90).
REFLECT_OVERRIDE_ALLOWLIST = frozenset(
    {
        "REFLECT_VOICE",
        "REFLECT_BARE",
        "REFLECT_PERSONA",
        "REFLECT_SYSTEM",
        "REFLECT_WORK",
        "REFLECT_RESCUE_SYSTEM",
        "REFLECT_THINK",
        "REFLECT_SPEAK",
        "REFLECT_BARE_MINIMAL",
        "NSFW_AFFIRM_FALLBACK",
        "BOLD_MOCAP_FALLBACK",
        "SCENE_RP_FALLBACK",
        "SCENE_RP_SYSTEM_HINT",
        "HEARTBEAT_SYSTEM",
        "HEARTBEAT_TASK",
        "AWAY_PING_SYSTEM",
        "AWAY_PING_TASK",
    }
)

REFLECT_VOICE_ALIASES = (
    "REFLECT_BARE",
    "REFLECT_PERSONA",
    "REFLECT_SYSTEM",
    "REFLECT_WORK",
    "REFLECT_RESCUE_SYSTEM",
    "REFLECT_THINK",
    "REFLECT_SPEAK",
)

_STALE_FULL_COPY_MARKERS = (
    "def reflect_no_system",
    "def reflect_use_filters",
    "def viu_voice_issues",
    "def reflect_reply_issues",
    "def _apply_anabarra_override",
)

REFLECT_OVERRIDE_FORMAT = 1


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


def _format_py_str(value: str) -> str:
    if '"""' not in value:
        return f'"""{value}"""'
    if "'''" not in value:
        return f"'''{value}'''"
    return repr(value)


def _is_stale_full_reflect_override(text: str) -> bool:
    if "REFLECT_OVERRIDE_FORMAT" in text and "def reflect_" not in text:
        return False
    return any(marker in text for marker in _STALE_FULL_COPY_MARKERS)


def extract_reflect_voice_values(path: Path) -> dict[str, str]:
    """Достать allowlisted строковые константы из .py (AST, без exec)."""
    raw = path.read_text(encoding="utf-8")
    try:
        tree = ast.parse(raw)
    except SyntaxError:
        return {}

    literals: dict[str, str] = {}
    aliases: dict[str, str] = {}

    for node in tree.body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if not isinstance(target, ast.Name):
            continue
        name = target.id
        if name not in REFLECT_OVERRIDE_ALLOWLIST:
            continue
        value = node.value
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            literals[name] = value.value
        elif isinstance(value, ast.Name) and value.id in REFLECT_OVERRIDE_ALLOWLIST:
            aliases[name] = value.id

    for name, src in aliases.items():
        if name not in literals and src in literals:
            literals[name] = literals[src]
    return literals


def format_voice_only_reflect(values: dict[str, str]) -> str:
    """Минимальный личный файл: только голос, без plumbing."""
    voice = values.get("REFLECT_VOICE", "")
    lines = [
        '"""Личный голос Вью (Anabarra). Обновления U:\\\\Viu этот файл НЕ затирают.',
        "",
        "Правишь только строки ниже. Флаги/функции (NO_SYSTEM, фильтры, memory digest)",
        "всегда из пакета viu/prompts/reflect_mode.py — полный снимок сюда больше не кладём.",
        '"""',
        "",
        f"REFLECT_OVERRIDE_FORMAT = {REFLECT_OVERRIDE_FORMAT}",
        "",
        f"REFLECT_VOICE = {_format_py_str(voice)}",
        "",
    ]
    for alias in REFLECT_VOICE_ALIASES:
        other = values.get(alias)
        if other is not None and other != voice:
            lines.append(f"{alias} = {_format_py_str(other)}")
        else:
            lines.append(f"{alias} = REFLECT_VOICE")
    lines.append("")

    extras = (
        "REFLECT_BARE_MINIMAL",
        "NSFW_AFFIRM_FALLBACK",
        "BOLD_MOCAP_FALLBACK",
        "SCENE_RP_FALLBACK",
        "SCENE_RP_SYSTEM_HINT",
        "HEARTBEAT_SYSTEM",
        "HEARTBEAT_TASK",
        "AWAY_PING_SYSTEM",
        "AWAY_PING_TASK",
    )
    for name in extras:
        if name not in values:
            continue
        lines.append(f"{name} = {_format_py_str(values[name])}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _write_viu_prompts_readme(prompts_dir: Path) -> None:
    readme = prompts_dir / "README.txt"
    text = (
        "Личные промпты Вью — обновления U:\\Viu их НЕ затирают.\n"
        "\n"
        "reflect_mode.py — только голос/промпт-строки (REFLECT_VOICE и друзья).\n"
        "Функции и флаги (NO_SYSTEM, фильтры, memory) всегда из пакета:\n"
        "  U:\\Viu\\viu\\prompts\\reflect_mode.py\n"
        "\n"
        "Если здесь лежит старый полный снимок модуля — Вью сама вырежет голос\n"
        "и сохранит .bak-full; plumbing после апдейта больше не откатывается.\n"
    )
    try:
        if not readme.is_file() or "только голос" not in readme.read_text(
            encoding="utf-8", errors="ignore"
        ):
            readme.write_text(text, encoding="utf-8")
    except OSError:
        pass


def migrate_stale_reflect_override(viu_root: Path) -> str:
    """Старый полный снимок → backup + voice-only. Иначе пустая строка."""
    root = Path(viu_root)
    path = user_reflect_mode_path(root)
    if not path.is_file():
        return ""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return ""
    if not _is_stale_full_reflect_override(text):
        return ""

    values = extract_reflect_voice_values(path)
    if not values.get("REFLECT_VOICE"):
        # Fallback: seed from package so reflect still has a voice.
        pkg = root / REFLECT_MODE_REL
        if pkg.is_file():
            values = extract_reflect_voice_values(pkg)
    if not values.get("REFLECT_VOICE"):
        return ""

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = path.with_name(f"reflect_mode.py.bak-full-{stamp}")
    try:
        shutil.copy2(path, backup)
        path.write_text(format_voice_only_reflect(values), encoding="utf-8")
        _write_viu_prompts_readme(path.parent)
    except OSError:
        return ""
    return (
        f"reflect_mode в Anabarra был полным снимком (ломал фиксы после апдейта) — "
        f"оставлен только голос; backup: {backup.name}"
    )


def preserve_reflect_mode(viu_root: Path) -> str:
    """Перед апдейтом: seed voice-only в Анабарру, если файла ещё нет.

    Существующий файл никогда не перезаписываем содержимым zip — только мигрируем
    устаревший полный снимок в voice-only (с .bak-full).
    """
    root = Path(viu_root)
    src = root / REFLECT_MODE_REL
    dest = user_reflect_mode_path(root)
    if dest.is_file():
        return migrate_stale_reflect_override(root)
    if not src.is_file():
        return ""
    try:
        values = extract_reflect_voice_values(src)
        if not values.get("REFLECT_VOICE"):
            # Крайний случай: скопировать как есть, migrate починит при load.
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)
            _write_viu_prompts_readme(dest.parent)
            migrate_stale_reflect_override(root)
            return f"reflect_mode.py сохранён в {dest} — обновления Вью его не трогают."
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(format_voice_only_reflect(values), encoding="utf-8")
        _write_viu_prompts_readme(dest.parent)
        return (
            f"reflect_mode.py (только голос) сохранён в {dest} — "
            "обновления Вью его не трогают."
        )
    except OSError:
        return ""


def _sync_voice_aliases(namespace: dict[str, Any], applied: set[str]) -> None:
    if "REFLECT_VOICE" not in applied:
        return
    voice = namespace.get("REFLECT_VOICE")
    if not isinstance(voice, str):
        return
    for alias in REFLECT_VOICE_ALIASES:
        if alias not in applied:
            namespace[alias] = voice


def load_reflect_mode_override(
    namespace: dict, viu_root: Path | None = None
) -> Path | None:
    """Подменить только голос из Anabarra\\ViuPrompts; plumbing пакета не трогать."""
    root = Path(viu_root) if viu_root is not None else Path(__file__).resolve().parent
    migrate_stale_reflect_override(root)
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
        "REFLECT_OVERRIDE_FORMAT",
    }
    applied: set[str] = set()
    for name, val in vars(mod).items():
        if name in skip:
            continue
        if name not in REFLECT_OVERRIDE_ALLOWLIST:
            continue
        namespace[name] = val
        applied.add(name)
    _sync_voice_aliases(namespace, applied)
    return path if applied else None


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
