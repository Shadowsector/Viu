"""Единый Inbox: Viu сама раскладывает blend, анимации, props, картинки."""

from __future__ import annotations

import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from .anabarra_layout import inbox_dir, library_root, unity_project_path
from .inbox_layout import inbox_animations_dir, inbox_references_dir, ensure_inbox_readme
from .animation_catalog import (
    AnimationCatalogStore,
    animation_catalog_path,
    animation_staging_dir,
    match_fbx_to_wish,
    suggest_rename_for_wish,
)
from .animation_catalog.models import AnimationImportReview, DEFAULT_SCOPE
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
    open_animation_review: bool = False

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
        if self.open_animation_review:
            lines.append("→ Откроется окно описания анимации.")
        else:
            lines.append(
                "Blend → «Следующий шаг». Анимация → «Принять анимацию (Inbox)» — по одной.\n"
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


def _find_inbox_animation_fbx(inbox: Path, config: Config) -> List[Path]:
    found: List[Path] = []
    roots = [inbox]
    try:
        anim_inbox = inbox_animations_dir(config)
        if anim_inbox.is_dir() and anim_inbox not in roots:
            roots.append(anim_inbox)
    except OSError:
        pass
    for root in roots:
        if not root.is_dir():
            continue
        for p in sorted(root.iterdir()):
            if p.is_file() and p.suffix.lower() == ".fbx" and is_character_animation_fbx(p):
                found.append(p)
    return found


def _import_one_animation(
    entry: Path,
    store: AnimationCatalogStore,
    staging: Path,
    unity_anim: Path,
    *,
    copy_to_unity: bool,
    remove_from_inbox: bool,
) -> tuple[RoutedItem, RoutedItem | None, AnimationImportReview, str]:
    wish, score, reason = match_fbx_to_wish(entry, store)
    target_name = entry.name
    if wish and score >= 0.65:
        target_name = suggest_rename_for_wish(wish, entry.name)

    dest_staging = _unique_dest(staging / target_name)
    _move_or_copy(entry, dest_staging, remove_from_inbox)

    dest_unity: Path | None = None
    if copy_to_unity:
        unity_anim.mkdir(parents=True, exist_ok=True)
        dest_unity = _unique_dest(unity_anim / target_name)
        shutil.copy2(dest_staging, dest_unity)

    review = AnimationImportReview(
        original_name=entry.name,
        clip_file=str(dest_unity or dest_staging),
        suggested_slug=wish.slug if wish else _normalize_slug(entry.stem),
        suggested_title=wish.title_ru if wish else entry.stem,
        category=wish.category if wish else "locomotion",
        when_used=wish.when_used if wish else "",
        looks_like=wish.looks_like if wish else "",
        purpose=wish.purpose if wish else "",
        animator_state=wish.animator_state if wish else "",
        scope=DEFAULT_SCOPE,
    )
    store.upsert_pending(review)

    detail = f"ожидает описания — {reason}"
    if wish:
        detail = f"предположение: «{wish.title_ru}» ({wish.slug}) — {reason}"

    return (
        RoutedItem(entry, dest_staging, "animation", detail),
        RoutedItem(dest_staging, dest_unity, "animation→Unity", "после review") if dest_unity else None,
        review,
        detail,
    )


def _normalize_slug(stem: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", stem.lower()).strip("_")
    return s or "clip"


def accept_single_animation(
    config: Config,
    *,
    copy_to_unity: bool = True,
    remove_from_inbox: bool = True,
) -> InboxRouteReport:
    """Ровно один FBX-анимация в Inbox → staging + Unity + очередь review."""
    report = InboxRouteReport()
    inbox = inbox_dir(config)
    if not inbox.is_dir():
        report.ok = False
        report.errors.append(f"Inbox не найден: {inbox}")
        return report

    anim_files = _find_inbox_animation_fbx(inbox, config)
    if not anim_files:
        report.ok = False
        report.errors.append(
            "В Inbox нет FBX-анимации (Mixamo).\n"
            "Положи один файл, напр. Fast Run.fbx"
        )
        return report
    if len(anim_files) > 1:
        report.ok = False
        report.errors.append(
            f"В Inbox {len(anim_files)} анимаций — клади **по одной**.\n"
            + ", ".join(p.name for p in anim_files)
        )
        return report

    store = AnimationCatalogStore(animation_catalog_path(config)).load()
    staging = animation_staging_dir(config)
    staging.mkdir(parents=True, exist_ok=True)
    unity_anim = resolve_in_unity_project(unity_project_path(config), ANIMATIONS_REL)

    try:
        item, unity_item, review, _ = _import_one_animation(
            anim_files[0],
            store,
            staging,
            unity_anim,
            copy_to_unity=copy_to_unity,
            remove_from_inbox=remove_from_inbox,
        )
        report.items.append(item)
        if unity_item:
            report.items.append(unity_item)
        report.animation_matches.append(
            f"{review.original_name} → окно описания (slug: {review.suggested_slug})"
        )
        report.open_animation_review = True
        store.save()
    except OSError as exc:
        report.ok = False
        report.errors.append(str(exc))

    return report


def route_inbox(
    config: Config,
    *,
    copy_to_unity: bool = True,
    remove_from_inbox: bool = True,
) -> InboxRouteReport:
    """Разобрать Inbox: blend, props, картинки. Анимации — через accept_single_animation."""
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

    ensure_inbox_readme(config)
    refs_inbox = inbox_references_dir(config)

    entries = sorted(
        p
        for p in inbox.iterdir()
        if p.name not in (".", "..")
        and not p.name.startswith(".")
        and p.name not in ("creatures", "animations", "references", "cascadeur")
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
                    report.items.append(
                        RoutedItem(
                            entry,
                            entry,
                            "animation (пропуск)",
                            "используй «Принять анимацию (Inbox)» — по одной + описание",
                        )
                    )
                    continue
                dest = _unique_dest(lib / "Props" / "fbx" / entry.name)
                dest.parent.mkdir(parents=True, exist_ok=True)
                _move_or_copy(entry, dest, remove_from_inbox)
                report.items.append(RoutedItem(entry, dest, "prop fbx"))
                continue

            if entry.is_file() and entry.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp"):
                dest = _unique_dest(refs_inbox / entry.name)
                dest.parent.mkdir(parents=True, exist_ok=True)
                _move_or_copy(entry, dest, remove_from_inbox)
                report.items.append(
                    RoutedItem(entry, dest, "reference", "Inbox/references → каталог референсов")
                )
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
                    report.items.append(
                        RoutedItem(
                            entry,
                            entry,
                            "animation folder",
                            f"{len(anim_fbx)} FBX — вынь по одному в Inbox → «Принять анимацию»",
                        )
                    )
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
