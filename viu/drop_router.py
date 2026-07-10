"""Единый Inbox: Viu сама раскладывает blend, анимации, props, картинки."""

from __future__ import annotations

import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from .anabarra_layout import inbox_dir, library_root, unity_project_path
from .animation_catalog import (
    AnimationCatalogStore,
    animation_catalog_path,
    animation_staging_dir,
    match_fbx_to_wish,
    suggest_rename_for_wish,
)
from .config import Config
from .integrations.unity.animation_scan import ANIMATIONS_REL
from .integrations.unity.paths import resolve_in_unity_project

# Признаки FBX-анимации (Mixamo и т.п.), не prop/домик.
_ANIM_FBX = re.compile(
    r"idle|walk|run|sit|sleep|stretch|jump|yawn|throw|climb|fall|"
    r"attack|dance|eat|drink|mixamo|x bot@|@female|@male",
    re.I,
)

# FBX окружения / здания — не анимация персонажа.
_ENV_FBX = re.compile(
    r"stable|stables|barn|hut|house|environment|building|prop_|wall_",
    re.I,
)


@dataclass
class RoutedItem:
    src: Path
    dest: Path
    kind: str
    detail: str = ""


@dataclass
class InboxRouteReport:
    ok: bool = True
    items: List[RoutedItem] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    animation_matches: List[str] = field(default_factory=list)

    def format(self) -> str:
        lines = ["Разбор Inbox — готово."]
        if not self.items:
            lines.append("Inbox пуст или нечего переносить.")
        for it in self.items:
            lines.append(f"  • {it.kind}: {it.src.name}")
            lines.append(f"    → {it.dest}")
            if it.detail:
                lines.append(f"    ({it.detail})")
        for m in self.animation_matches:
            lines.append(f"  🎬 {m}")
        for err in self.errors:
            lines.append(f"  ⚠ {err}")
        lines.append("")
        lines.append(
            "Blend → дальше «Следующий шаг» (prepare).\n"
            "Анимации → Unity Sync или «Обновить аниматор».\n"
            "Каталог: .viu/animation_catalog.json"
        )
        return "\n".join(lines)


def is_character_animation_fbx(path: Path) -> bool:
    """FBX с клипом Шани, не меш домика."""
    if path.suffix.lower() != ".fbx":
        return False
    name = path.name
    if _ENV_FBX.search(name):
        return False
    if _ANIM_FBX.search(name):
        return True
    # Папка Animations в Inbox
    if "animation" in str(path.parent).lower():
        return True
    return False


def _unique_dest(dest: Path) -> Path:
    if not dest.exists():
        return dest
    stem, suffix = dest.stem, dest.suffix
    n = 2
    while dest.exists():
        dest = dest.with_name(f"{stem}_{n}{suffix}")
        n += 1
    return dest


def route_inbox(
    config: Config,
    *,
    copy_to_unity: bool = True,
    remove_from_inbox: bool = True,
) -> InboxRouteReport:
    """Разобрать верхний уровень Inbox по типам файлов."""
    report = InboxRouteReport()
    inbox = inbox_dir(config)
    if not inbox.is_dir():
        report.ok = False
        report.errors.append(f"Inbox не найден: {inbox}")
        return report

    store = AnimationCatalogStore(animation_catalog_path(config)).load()
    staging = animation_staging_dir(config)
    staging.mkdir(parents=True, exist_ok=True)
    lib = library_root(config)
    unity_anim = resolve_in_unity_project(unity_project_path(config), ANIMATIONS_REL)

    entries = sorted(
        p for p in inbox.iterdir() if p.name not in (".", "..") and not p.name.startswith(".")
    )
    if not entries:
        return report

    for entry in entries:
        try:
            if entry.is_file() and entry.suffix.lower() == ".blend":
                dest = _unique_dest(lib / "Blender" / entry.name)
                dest.parent.mkdir(parents=True, exist_ok=True)
                _move_or_copy(entry, dest, remove_from_inbox)
                report.items.append(
                    RoutedItem(entry, dest, "blend", "prepare через «Следующий шаг»")
                )
                continue

            if entry.is_file() and entry.suffix.lower() == ".fbx":
                if is_character_animation_fbx(entry):
                    wish, score, reason = match_fbx_to_wish(entry, store)
                    target_name = entry.name
                    detail = reason
                    if wish and score >= 0.65:
                        target_name = suggest_rename_for_wish(wish, entry.name)
                        wish.clip_file = target_name
                        wish.status = "imported"
                        store.upsert(wish)
                        detail = f"{wish.title_ru} ({wish.slug}) — {reason}"
                        report.animation_matches.append(
                            f"{entry.name} → «{wish.title_ru}» [{wish.category}]"
                        )

                    dest_staging = _unique_dest(staging / target_name)
                    _move_or_copy(entry, dest_staging, remove_from_inbox)
                    report.items.append(RoutedItem(entry, dest_staging, "animation", detail))

                    if copy_to_unity:
                        unity_anim.mkdir(parents=True, exist_ok=True)
                        dest_unity = _unique_dest(unity_anim / target_name)
                        shutil.copy2(dest_staging, dest_unity)
                        report.items.append(
                            RoutedItem(
                                dest_staging,
                                dest_unity,
                                "animation→Unity",
                                "Sync Animations",
                            )
                        )
                else:
                    dest = _unique_dest(lib / "Props" / "fbx" / entry.name)
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    _move_or_copy(entry, dest, remove_from_inbox)
                    report.items.append(RoutedItem(entry, dest, "prop fbx"))
                continue

            if entry.is_file() and entry.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp"):
                dest = _unique_dest(lib / "References" / "images" / entry.name)
                dest.parent.mkdir(parents=True, exist_ok=True)
                _move_or_copy(entry, dest, remove_from_inbox)
                report.items.append(RoutedItem(entry, dest, "image"))
                continue

            if entry.is_dir():
                # Пак с blend или textures — оставить для prepare (не трогаем)
                blends = list(entry.glob("*.blend"))
                if blends:
                    report.items.append(
                        RoutedItem(
                            entry,
                            entry,
                            "pack (blend)",
                            "не трогала — «Следующий шаг» сделает prepare",
                        )
                    )
                    continue
                anim_fbx = [p for p in entry.glob("*.fbx") if is_character_animation_fbx(p)]
                if anim_fbx:
                    for fbx in anim_fbx:
                        wish, score, reason = match_fbx_to_wish(fbx, store)
                        target_name = fbx.name
                        if wish and score >= 0.65:
                            target_name = suggest_rename_for_wish(wish, fbx.name)
                            wish.clip_file = target_name
                            wish.status = "imported"
                            store.upsert(wish)
                            report.animation_matches.append(
                                f"{fbx.name} → «{wish.title_ru}»"
                            )
                        dest_staging = _unique_dest(staging / target_name)
                        _move_or_copy(fbx, dest_staging, remove_from_inbox)
                        report.items.append(
                            RoutedItem(fbx, dest_staging, "animation", reason)
                        )
                        if copy_to_unity:
                            unity_anim.mkdir(parents=True, exist_ok=True)
                            dest_unity = _unique_dest(unity_anim / target_name)
                            shutil.copy2(dest_staging, dest_unity)
                    continue

                dest = _unique_dest(lib / "unsorted" / entry.name)
                dest.parent.mkdir(parents=True, exist_ok=True)
                if remove_from_inbox:
                    shutil.move(str(entry), str(dest))
                else:
                    shutil.copytree(entry, dest, dirs_exist_ok=True)
                report.items.append(RoutedItem(entry, dest, "folder→unsorted"))
                continue

            dest = _unique_dest(lib / "unsorted" / entry.name)
            dest.parent.mkdir(parents=True, exist_ok=True)
            _move_or_copy(entry, dest, remove_from_inbox)
            report.items.append(RoutedItem(entry, dest, "unsorted"))

        except OSError as exc:
            report.errors.append(f"{entry.name}: {exc}")

    store.save()
    return report


def _move_or_copy(src: Path, dest: Path, move: bool) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if move:
        shutil.move(str(src), str(dest))
    else:
        shutil.copy2(src, dest)
