"""Каноническая структура папок на диске U: — три зоны для Вью.

U:\\Viu\\              — программа Вью и данные (.viu). Zip-апдейт трогает только это.
U:\\Anabarra\\         — игра + Inbox (Unity, Library, Animations, Inbox, ViuPrompts)
U:\\Desktop Mascot\\   — архив сотен файлов (Вью НЕ сканирует сама)
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import List, Tuple

from .config import Config

LIBRARY_SUBDIRS: tuple[str, ...] = (
    "Blender",
    "Lab/Models/Inbox",
    "Lab/Models/CascadeurReady",
    "Lab/Refs",
    "Lab/FaceRefs",
    "Lab/Interactions",
    "Lab/ComfyOut",
    "Props/fbx",
    "Props/obj",
    "Props/glb",
    "Archives",
    "References/images",
    "Processed",
    "unsorted",
)

DEFAULT_ANABARRA_ROOT = Path("U:/Anabarra")
DEFAULT_VIU_ROOT = Path("U:/Viu")
DEFAULT_UNITY_PROJECT = DEFAULT_ANABARRA_ROOT / "Unity" / "Anabarra"
DEFAULT_MASCOT_ARCHIVE = Path("U:/Desktop Mascot")
INBOX_FOLDER_NAME = "Inbox"


def _env(name: str) -> str:
    value = os.environ.get(name)
    return value if value not in (None, "") else ""


def viu_install_root(config: Config) -> Path:
    """Где установлена Вью (U:\\Viu)."""
    raw = _env("VIU_ROOT") or ""
    if raw:
        p = Path(raw).expanduser().resolve()
        if p.name.lower() == "viu" or (p / "viu").is_dir():
            return p if p.name.lower() == "viu" else p
    if config.root.name.lower() == "viu":
        return config.root.resolve()
    if DEFAULT_VIU_ROOT.is_dir():
        return DEFAULT_VIU_ROOT.resolve()
    return config.root.resolve()


def anabarra_root(config: Config) -> Path:
    """Корень игры — U:\\Anabarra."""
    raw = _env("VIU_ANABARRA_ROOT") or getattr(config, "anabarra_root", "") or ""
    if raw:
        return Path(raw).expanduser().resolve()

    unity_raw = (config.unity_project or _env("VIU_UNITY_PROJECT") or "").strip()
    if unity_raw:
        unity = Path(unity_raw).expanduser().resolve()
        if unity.name.lower() == "anabarra" and unity.parent.name.lower() == "unity":
            return unity.parent.parent
        if (unity / "Assets").is_dir():
            return unity
        return unity.parent

    viu_root = viu_install_root(config)
    if viu_root.parent.exists():
        sibling = viu_root.parent / "Anabarra"
        if sibling.is_dir():
            return sibling.resolve()

    if DEFAULT_ANABARRA_ROOT.exists():
        return DEFAULT_ANABARRA_ROOT.resolve()
    return DEFAULT_ANABARRA_ROOT


def unity_project_path(config: Config) -> Path:
    raw = (config.unity_project or _env("VIU_UNITY_PROJECT") or "").strip()
    if raw:
        return Path(raw).expanduser().resolve()
    candidate = anabarra_root(config) / "Unity" / "Anabarra"
    if candidate.is_dir():
        return candidate.resolve()
    return DEFAULT_UNITY_PROJECT


def library_root(config: Config) -> Path:
    raw = _env("VIU_LIBRARY_ROOT") or getattr(config, "library_root", "") or ""
    if raw:
        return Path(raw).expanduser().resolve()
    return anabarra_root(config) / "Library"


def user_prompts_dir(config: Config) -> Path:
    """Личные промпты вне zip: U:\\Anabarra\\ViuPrompts."""
    from install_merge import USER_PROMPTS_DIRNAME

    return anabarra_root(config) / USER_PROMPTS_DIRNAME


def user_reflect_mode_path(config: Config) -> Path:
    return user_prompts_dir(config) / "reflect_mode.py"


def preserve_user_reflect_mode(config: Config | None = None) -> str:
    """Сохранить текущий reflect_mode в Анабарру (если там ещё нет). До апдейта."""
    from install_merge import preserve_reflect_mode

    if config is not None:
        return preserve_reflect_mode(viu_install_root(config))
    # U:\\Viu — родитель пакета viu/
    return preserve_reflect_mode(Path(__file__).resolve().parent.parent)


def legacy_viu_inbox_dir(config: Config) -> Path:
    """Старый путь U:\\Viu\\Inbox — больше не канон (zip апдейт мог его трогать)."""
    return viu_install_root(config) / INBOX_FOLDER_NAME


def inbox_dir(config: Config) -> Path:
    """Вход: один пак / референсы / анимации. По умолчанию U:\\Anabarra\\Inbox (вне zip)."""
    for key in ("VIU_INBOX_DIR", "VIU_DOWNLOADS_DIR"):
        raw = _env(key)
        if raw:
            return Path(raw).expanduser().resolve()
    cfg_raw = getattr(config, "inbox_dir", "") or getattr(config, "downloads_dir", "") or ""
    if cfg_raw:
        return Path(cfg_raw).expanduser().resolve()
    return anabarra_root(config) / INBOX_FOLDER_NAME


def downloads_dir(config: Config) -> Path:
    """Обратная совместимость — то же, что inbox_dir."""
    return inbox_dir(config)


def _dir_has_user_files(path: Path) -> bool:
    if not path.is_dir():
        return False
    for p in path.rglob("*"):
        if not p.is_file():
            continue
        if p.name.lower() in ("readme.txt", "readme.md", ".gitkeep"):
            continue
        return True
    return False


def migrate_inbox_to_anabarra(config: Config) -> Tuple[bool, str]:
    """Перенести содержимое U:\\Viu\\Inbox → U:\\Anabarra\\Inbox (один раз при старте)."""
    old = legacy_viu_inbox_dir(config)
    new = inbox_dir(config)
    try:
        if old.resolve() == new.resolve():
            return False, ""
    except OSError:
        return False, ""
    if not old.is_dir() or not _dir_has_user_files(old):
        return False, ""
    new.mkdir(parents=True, exist_ok=True)
    moved = 0
    skipped = 0
    for src in old.rglob("*"):
        if not src.is_file():
            continue
        rel = src.relative_to(old)
        dest = new / rel
        if dest.exists():
            skipped += 1
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        try:
            shutil.move(str(src), str(dest))
            moved += 1
        except OSError:
            try:
                shutil.copy2(src, dest)
                moved += 1
            except OSError:
                skipped += 1
    # Убрать пустые каталоги в старом Inbox (README можно оставить-указатель)
    try:
        marker = old / "README.txt"
        marker.write_text(
            "Inbox переехал в U:\\Anabarra\\Inbox — клади файлы туда.\n"
            "Папка U:\\Viu\\Inbox больше не используется (обновления Вью её не трогают).\n",
            encoding="utf-8",
        )
    except OSError:
        pass
    if moved == 0 and skipped == 0:
        return False, ""
    msg = f"Inbox перенесён в {new}: файлов {moved}"
    if skipped:
        msg += f", пропущено (уже есть) {skipped}"
    return True, msg


def mascot_archive_dir(config: Config) -> Path:
    """Архив Desktop Mascot — только для ручного выбора, без автоскана."""
    raw = _env("VIU_MASCOT_DIR") or getattr(config, "mascot_dir", "") or ""
    if raw:
        return Path(raw).expanduser().resolve()
    return DEFAULT_MASCOT_ARCHIVE


def project_data_dir(config: Config) -> Path:
    explicit = _env("VIU_DATA_DIR")
    if explicit:
        return Path(explicit).expanduser().resolve()
    if config.data_dir:
        return config.data_dir.resolve()
    return viu_install_root(config) / ".viu"


def ensure_layout(config: Config) -> List[Path]:
    """Создаёт Inbox (Anabarra), .viu и Library; переносит старый U:\\Viu\\Inbox."""
    from .inbox_layout import ensure_inbox_readme

    migrate_inbox_to_anabarra(config)
    roots: List[Path] = []
    for path in (config.data_dir.resolve(), inbox_dir(config), library_root(config)):
        path.mkdir(parents=True, exist_ok=True)
        roots.append(path)
    ensure_inbox_readme(config)
    lib = library_root(config)
    for sub in LIBRARY_SUBDIRS:
        (lib / sub).mkdir(parents=True, exist_ok=True)
    return roots


def describe_layout(config: Config) -> str:
    viu = viu_install_root(config)
    mascot = mascot_archive_dir(config)
    lines = [
        "Три папки на U: (Вью не лезет на C: без явной настройки):",
        "",
        f"  1. U:\\Viu\\          программа:     {viu}",
        f"     Данные (.viu):     {config.data_dir}",
        "     (обновления с GitHub трогают только эту папку)",
        "",
        f"  2. U:\\Anabarra\\      игра:          {anabarra_root(config)}",
        f"     Inbox (разбор):    {inbox_dir(config)}",
        f"     Unity:             {unity_project_path(config)}",
        f"     Library (склад):   {library_root(config)}",
        "",
        f"  3. Desktop Mascot   архив:         {mascot}",
        "     (сотни файлов — Вью НЕ сканирует сама; бери оттуда один пак → Inbox)",
        "",
        "Workflow: пак → U:\\Anabarra\\Inbox → «Разобрать Inbox» → «Разметить предметы».",
        "Подробнее: docs/ANABARRA_FOLDERS.md",
    ]
    return "\n".join(lines)
