"""Единый Inbox U:\\Viu\\Inbox — подпапки рядом друг с другом."""

from __future__ import annotations

from pathlib import Path

from .anabarra_layout import inbox_dir
from .config import Config

# Подпапки в U:\Viu\Inbox (рядом, не разбросаны по Anabarra).
INBOX_SUBDIRS: dict[str, str] = {
    "creatures": "Модели существ (.blend / .fbx / .glb)",
    "animations": "Анимации FBX — по одной, Mixamo/Cascadeur export",
    "references": "Референсы: картинки и видео для MoCap / идей",
    "cascadeur": "Очередь Cascadeur (.fbx / .blend)",
}


def _subdir(config: Config, key: str) -> Path:
    root = inbox_dir(config)
    p = root / key
    p.mkdir(parents=True, exist_ok=True)
    return p


def inbox_creatures_dir(config: Config) -> Path:
    return _subdir(config, "creatures")


def inbox_animations_dir(config: Config) -> Path:
    return _subdir(config, "animations")


def inbox_references_dir(config: Config) -> Path:
    return _subdir(config, "references")


def inbox_cascadeur_dir(config: Config) -> Path:
    return _subdir(config, "cascadeur")


def ensure_inbox_readme(config: Config) -> None:
    root = inbox_dir(config)
    root.mkdir(parents=True, exist_ok=True)
    readme = root / "README.txt"
    lines = [
        "Inbox Вью — все входы в одном месте (U:\\Viu\\Inbox).",
        "",
        "  (корень)     — паки домиков / blend для «Что делать дальше»",
    ]
    for key, hint in INBOX_SUBDIRS.items():
        lines.append(f"  {key}/       — {hint}")
    lines.extend(
        [
            "",
            "Референсы → references/ → «Референсы — окно» в ComfyUI.",
            "Существа → creatures/ → Blender — существа (шаги 1–3).",
            "Анимации → animations/ → «Описать новые FBX».",
        ]
    )
    text = "\n".join(lines) + "\n"
    if not readme.is_file() or readme.read_text(encoding="utf-8") != text:
        readme.write_text(text, encoding="utf-8")
    for key in INBOX_SUBDIRS:
        sub = root / key
        sub.mkdir(parents=True, exist_ok=True)
        sub_readme = sub / "README.txt"
        if not sub_readme.is_file():
            sub_readme.write_text(f"{INBOX_SUBDIRS[key]}\n", encoding="utf-8")


def describe_inbox(config: Config) -> str:
    root = inbox_dir(config)
    lines = [f"Inbox: {root}"]
    for key, hint in INBOX_SUBDIRS.items():
        lines.append(f"  {key}/ — {hint}")
    return "\n".join(lines)
