"""Очередь канон-рига для всех biped: AccuRIG пачкой + хвосты отдельно.

Вью не запускает AccuRIG (внешний GUI). Здесь: список biped из каталога,
папка очереди с копиями мешей, README, ingest канон-FBX обратно в Processed.
"""

from __future__ import annotations

import json
import shutil
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple

from ..anabarra_layout import library_root
from ..config import Config
from .models import STATUS_SKIP, CreatureEntry
from .paths import (
    creature_catalog_path,
    creature_ready_fbx_path,
    creatures_processed_dir,
)
from .store import CreatureCatalogStore

QUEUE_DIRNAME = "BipedCanonQueue"
MANIFEST_NAME = "queue_manifest.json"
README_NAME = "README_ACCURIG.txt"


@dataclass
class BipedQueueItem:
    id: str
    slug: str
    name: str
    size_class: str
    status: str
    source_path: str
    staged_name: str = ""
    ready: bool = False  # есть файл для AccuRIG
    needs_export: bool = False  # только .blend — сначала студия/FBX
    notes: str = ""
    tags: List[str] = field(default_factory=list)


def biped_canon_queue_dir(config: Config) -> Path:
    p = library_root(config) / "Lab" / "Creatures" / QUEUE_DIRNAME
    p.mkdir(parents=True, exist_ok=True)
    return p


def list_bipeds(
    store: CreatureCatalogStore,
    *,
    include_skip: bool = False,
    girls_only: bool = False,
) -> List[CreatureEntry]:
    out: List[CreatureEntry] = []
    for e in store.all():
        if e.locomotion != "biped":
            continue
        if not include_skip and e.status == STATUS_SKIP:
            continue
        if girls_only:
            g = (e.genital_profile or "").lower()
            name_l = (e.name or "").lower()
            girlish = g in ("vagina", "futa") or any(
                x in name_l
                for x in (
                    "girl",
                    "woman",
                    "female",
                    "lady",
                    "shanya",
                    "шаня",
                    "erisa",
                    "lilia",
                )
            )
            if not girlish:
                continue
        out.append(e)
    out.sort(key=lambda x: (x.size_class or "", x.slug or x.name.lower()))
    return out


def _pick_source_mesh(entry: CreatureEntry) -> Tuple[Optional[Path], str]:
    """Лучший файл для AccuRIG: ready FBX → inbox FBX → prepared/inbox blend."""
    candidates: List[Tuple[Path, str]] = []
    if entry.ready_fbx_path:
        candidates.append((Path(entry.ready_fbx_path), "ready_fbx"))
    if entry.path:
        candidates.append((Path(entry.path), "inbox"))
    if entry.prepared_path:
        candidates.append((Path(entry.prepared_path), "prepared"))
    for path, kind in candidates:
        try:
            if path.is_file():
                suf = path.suffix.lower()
                if suf == ".fbx":
                    return path, kind
                if suf in (".blend", ".glb", ".gltf", ".obj"):
                    return path, kind
        except OSError:
            continue
    return None, ""


def build_queue_items(
    store: CreatureCatalogStore,
    *,
    girls_only: bool = False,
) -> List[BipedQueueItem]:
    items: List[BipedQueueItem] = []
    for e in list_bipeds(store, girls_only=girls_only):
        src, kind = _pick_source_mesh(e)
        tags = list(e.tags or [])
        morph = (e.morph_notes or "").lower()
        if "tail" in morph or "хвост" in morph:
            tags.append("has_tail_note")
        if e.preserve_morphs:
            tags.append("preserve_morphs")
        if src is None:
            items.append(
                BipedQueueItem(
                    id=e.id,
                    slug=e.slug,
                    name=e.name,
                    size_class=e.size_class or "?",
                    status=e.status,
                    source_path="",
                    needs_export=True,
                    notes="нет файла модели в каталоге",
                    tags=tags,
                )
            )
            continue
        suf = src.suffix.lower()
        needs = suf != ".fbx"
        items.append(
            BipedQueueItem(
                id=e.id,
                slug=e.slug or e.id,
                name=e.name,
                size_class=e.size_class or "?",
                status=e.status,
                source_path=str(src),
                staged_name=f"{e.slug or e.id}{suf if needs else '.fbx'}",
                ready=not needs,
                needs_export=needs,
                notes=f"источник: {kind}",
                tags=tags,
            )
        )
    return items


def format_biped_list(items: List[BipedQueueItem]) -> str:
    if not items:
        return (
            "Biped в каталоге нет (locomotion=biped).\n"
            "Сначала: creature_catalog_scan → «Разметить существ» (locomotion=biped)."
        )
    lines = [
        f"=== Biped канон-очередь: {len(items)} ===",
        "AccuRIG Вью не запускает — папка очереди + README.",
        "",
    ]
    ready_n = sum(1 for i in items if i.ready)
    need_n = sum(1 for i in items if i.needs_export)
    lines.append(f"Готовы FBX под AccuRIG: {ready_n}")
    lines.append(f"Нужен экспорт из .blend: {need_n}")
    lines.append("")
    for i in items:
        mark = "FBX✓" if i.ready else ("BLEND→FBX" if i.needs_export else "?")
        tail = " · хвост?" if "has_tail_note" in i.tags else ""
        lines.append(
            f"  [{mark}] {i.slug}  {i.size_class}  {i.name}{tail}"
        )
        if i.source_path:
            lines.append(f"         {i.source_path}")
    lines.append("")
    lines.append(
        "Дальше: creature_biped_canon action=queue — скопировать в "
        f"Lab/Creatures/{QUEUE_DIRNAME}/"
    )
    return "\n".join(lines)


def _accurig_readme() -> str:
    return f"""Перериг biped — простыми словами
===============================

Полная памятка: docs/BIPED_RERIG_SIMPLE.md

1) Открой AccuRIG 2 (бесплатная программа Reallusion — не Вью).
2) Для каждого .fbx в ЭТОЙ папке:
   - Rig Body, проверь позу (руки в стороны или A-pose)
   - Export FBX, цель Unity
   - Имя файла:  ИМЯ_МОДЕЛИ_canon.fbx
     пример: goblin_girl.fbx → goblin_girl_canon.fbx
   - Сохрани СЮДА ЖЕ
3) В чате Вью напиши:  ingest biped

Хвост / грудь-jiggle: после перерига, отдельные кости + физика в Unity.
Не часть «человеческого» скелета.

Органы (penis): всем biped, в покое scale кости ≈ 0 (спрятан в теле).
В каталоге: creature_biped_canon action=mark_genital

Создано: {time.strftime("%Y-%m-%d %H:%M")}
"""


def stage_biped_queue(
    config: Config,
    store: CreatureCatalogStore,
    *,
    girls_only: bool = False,
    copy_blend: bool = True,
) -> Tuple[int, int, str]:
    """Скопировать biped-меши в Lab/Creatures/BipedCanonQueue/."""
    qdir = biped_canon_queue_dir(config)
    items = build_queue_items(store, girls_only=girls_only)
    staged = 0
    skipped = 0
    manifest_items = []
    for it in items:
        if not it.source_path:
            skipped += 1
            manifest_items.append(asdict(it))
            continue
        src = Path(it.source_path)
        if not src.is_file():
            skipped += 1
            it.notes = "файл пропал"
            manifest_items.append(asdict(it))
            continue
        if it.needs_export and not copy_blend:
            skipped += 1
            manifest_items.append(asdict(it))
            continue
        dest_name = it.staged_name or f"{it.slug}{src.suffix.lower()}"
        dest = qdir / dest_name
        try:
            shutil.copy2(src, dest)
            staged += 1
            it.staged_name = dest_name
            it.notes = (it.notes + f"; staged→{dest_name}").strip("; ")
        except OSError as exc:
            skipped += 1
            it.notes = f"copy fail: {exc}"
        manifest_items.append(asdict(it))

    manifest = {
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "queue_dir": str(qdir),
        "count": len(manifest_items),
        "staged": staged,
        "skipped": skipped,
        "items": manifest_items,
    }
    (qdir / MANIFEST_NAME).write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (qdir / README_NAME).write_text(_accurig_readme(), encoding="utf-8")

    msg = (
        f"Очередь: {qdir}\n"
        f"Скопировано: {staged}, пропущено: {skipped}\n"
        f"Манифест: {MANIFEST_NAME}\n"
        f"Инструкция: {README_NAME}\n\n"
        "1) AccuRIG по каждому FBX → сохрани <slug>_canon.fbx сюда же\n"
        "2) creature_biped_canon action=ingest\n"
        "3) Хвосты/jiggle — после бинда, secondary (см. README)"
    )
    if any(i.needs_export for i in items):
        msg += (
            "\n\nУ части только .blend — открой «Студия существ» → эталон FBX, "
            "потом queue ещё раз (или положи FBX в Inbox)."
        )
    return staged, skipped, msg


def ingest_canon_fbx(config: Config, store: CreatureCatalogStore) -> Tuple[int, str]:
    """Забрать *_canon.fbx из очереди → Processed/<slug>/<slug>_ready.fbx."""
    qdir = biped_canon_queue_dir(config)
    if not qdir.is_dir():
        return 0, f"Нет папки очереди: {qdir}"
    found = sorted(qdir.glob("*_canon.fbx")) + sorted(qdir.glob("*_canon.FBX"))
    # также plain AccuRIG exports named <slug>.fbx in done/ subfolder
    done = qdir / "done"
    if done.is_dir():
        found.extend(sorted(done.glob("*_canon.fbx")))
    if not found:
        return (
            0,
            f"В {qdir} нет *_canon.fbx.\n"
            "После AccuRIG сохрани экспорт как slug_canon.fbx и повтори ingest.",
        )

    by_slug = {e.slug: e for e in store.all() if e.slug}
    n = 0
    lines: List[str] = []
    for src in found:
        stem = src.stem
        slug = stem[: -len("_canon")] if stem.lower().endswith("_canon") else stem
        dest = creature_ready_fbx_path(config, slug)
        try:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)
        except OSError as exc:
            lines.append(f"FAIL {slug}: {exc}")
            continue
        e = by_slug.get(slug)
        if e is not None:
            e.ready_fbx_path = str(dest)
            note = "[biped_canon] AccuRIG → ready_fbx"
            if note not in (e.notes or ""):
                e.notes = ((e.notes or "").rstrip() + "\n" + note).strip()
            # tag
            if "canon_humanoid" not in (e.tags or []):
                e.tags = list(e.tags or []) + ["canon_humanoid"]
        n += 1
        lines.append(f"OK {slug} → {dest}")

    if n:
        store.save()
    head = f"Ingest: {n} канон-FBX → {creatures_processed_dir(config)}\n"
    return n, head + "\n".join(lines[:40])


def guide_text() -> str:
    return (
        "=== Biped пачкой через Вью ===\n"
        "1. creature_catalog_scan + разметка locomotion=biped\n"
        "2. creature_biped_canon action=list\n"
        "3. Эталон FBX в студии (если только .blend)\n"
        "4. creature_biped_canon action=queue → Lab/Creatures/BipedCanonQueue/\n"
        "5. AccuRIG вручную: каждый FBX → <slug>_canon.fbx\n"
        "6. creature_biped_canon action=ingest\n"
        "7. Unity Humanoid Apply; клипы Mixamo/ActorCore на общий скелет\n"
        "8. Хвост/jiggle: кости Tail_* вне Humanoid + spring in Unity\n"
        "\n"
        "Cascadeur — только полировка уже играющих клипов.\n"
        "См. docs/ANIMATION_CANON.md"
    )


def mark_biped_genital(
    store: CreatureCatalogStore,
    *,
    girls_only: bool = False,
) -> Tuple[int, str]:
    """Всем biped: penis (или futa если уже vagina), genital_rig=pending, flaccid.

    Меш не трогаем — только каталог. Прикрутка prefab + scale-hide — в студии.
    """
    n = 0
    lines: List[str] = []
    for e in list_bipeds(store, girls_only=girls_only):
        old_g = (e.genital_profile or "none").strip().lower() or "none"
        if old_g in ("vagina", "futa"):
            new_g = "futa"
        elif old_g == "penis":
            new_g = "penis"
        else:
            new_g = "penis"
        e.genital_profile = new_g
        e.nsfw_capable = True
        e.flaccid_default = True
        if (e.genital_rig or "").strip().lower() in ("", "none"):
            e.genital_rig = "pending"
        note = (
            "[genital] hidden penis (scale~0 на кости); "
            f"profile={new_g}; rig={e.genital_rig}"
        )
        if note.split(";")[0] not in (e.notes or ""):
            e.notes = ((e.notes or "").rstrip() + "\n" + note).strip()
        if "hidden_penis" not in (e.tags or []):
            e.tags = list(e.tags or []) + ["hidden_penis"]
        n += 1
        lines.append(f"  {e.slug}: {old_g} → {new_g}, genital_rig={e.genital_rig}")
    if n:
        store.save()
    head = (
        f"Помечено biped: {n}.\n"
        "В каталоге: penis/futa, flaccid_default, genital_rig=pending.\n"
        "Дальше в Blender/Wardrobe: прикрутить эталон penis к тазу, "
        "покой = scale кости ≈ 0; показ = scale вверх.\n"
        "См. docs/BIPED_RERIG_SIMPLE.md\n"
    )
    return n, head + "\n".join(lines[:50])


def run_biped_canon_action(
    config: Config,
    *,
    action: str = "list",
    girls_only: bool = False,
) -> Tuple[bool, str]:
    store = CreatureCatalogStore(creature_catalog_path(config)).load()
    act = (action or "list").strip().lower()
    if act in ("guide", "help", "how", "lamer", "просто"):
        from pathlib import Path as _P

        simple = _P(__file__).resolve().parents[2] / "docs" / "BIPED_RERIG_SIMPLE.md"
        if simple.is_file():
            return True, simple.read_text(encoding="utf-8")
        return True, guide_text()
    if act in ("list", "show", "bipeds"):
        items = build_queue_items(store, girls_only=girls_only)
        return True, format_biped_list(items)
    if act in ("queue", "stage", "prepare"):
        _s, _k, msg = stage_biped_queue(
            config, store, girls_only=girls_only, copy_blend=True
        )
        return True, msg
    if act in ("ingest", "import", "land"):
        n, msg = ingest_canon_fbx(config, store)
        return n > 0, msg
    if act in ("mark_genital", "genital", "organs", "penis_all"):
        n, msg = mark_biped_genital(store, girls_only=girls_only)
        return n > 0, msg
    return (
        False,
        f"Неизвестное action={action}. list | queue | ingest | mark_genital | guide",
    )
