"""Comfy kept MP4 → Cascadeur Reference / MoCap assist → Export FBX.

Cascadeur не даёт надёжного публичного API для кнопки MoCap — поэтому:
1) кладём pending JSON + Commands (открыть Import Reference / Export);
2) чеклист для Дена (MoCap на таймлайне);
3) после Export — регистрация в animation_catalog.
"""

from __future__ import annotations

import json
import re
import shutil
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ...config import Config
from ..comfy.clip_review import (
    STATUS_KEPT,
    ComfyClip,
    ComfyClipStore,
    clip_review_path,
    comfy_kept_dir,
)
from .import_fbx import (
    cascadeur_scripts_dir,
    discover_commands_dirs,
    scripts_status_text,
)
from .paths import cascadeur_export

REF_COMMAND_FILENAME = "viu_import_reference.py"
EXPORT_COMMAND_FILENAME = "viu_export_clip.py"
PENDING_REF_FILENAME = "viu_mocap_pending.json"
CONSOLE_REF_FILENAME = "viu_import_reference_console.py"
CONSOLE_EXPORT_FILENAME = "viu_export_clip_console.py"

IMPORT_REF_COMMAND_SOURCE = '''"""Viu — Import Reference video из viu_mocap_pending.json.

Commands → Viu → ImportReference
Открывает диалог Reference video (если action найден) и пишет путь в Event log.
"""
import json
import os

import csc


def command_name():
    return "Viu.ImportReference"


def _load_pending():
    pending = os.path.join(os.path.dirname(__file__), "viu_mocap_pending.json")
    if not os.path.isfile(pending):
        return None, pending
    with open(pending, "r", encoding="utf-8") as fh:
        return json.load(fh), pending


def run(scene):
    data, pending = _load_pending()
    if data is None:
        scene.error("Нет viu_mocap_pending.json — сначала cascadeur_import_reference в Вью.")
        return
    video = (data.get("video") or "").strip().replace("\\\\", "/")
    if not video:
        scene.error("В pending нет пути video.")
        return
    if not os.path.isfile(video):
        scene.error("Видео не найдено: " + video)
        return

    app = csc.app.get_application()
    am = app.get_action_manager()
    tried = []
    opened = False
    for name in (
        "File.Import Reference video",
        "Import.Reference video",
        "File.Reference video",
        "Application.Import Reference video",
        "File.Import.Reference video",
    ):
        try:
            am.call_action(name)
            opened = True
            scene.info("Action OK: " + name)
            break
        except Exception as exc:
            tried.append(name + ": " + str(exc))

    frames = (data.get("frames_dir") or "").strip()
    scene.info("Viu Reference video: " + video)
    if frames:
        scene.info("Frames path (рекомендуется): " + frames)
    if not opened:
        scene.error(
            "Не открыла Import Reference автоматически. "
            "Сделай: File → Import → Reference video → выбери файл из Event log."
        )
        if tried:
            scene.info("Tried: " + " | ".join(tried[:5]))
    else:
        scene.info("В диалоге Choose… выбери видео выше (H.264 mp4).")
'''

EXPORT_CLIP_COMMAND_SOURCE = '''"""Viu — Export FBX клипа из viu_mocap_pending.json.

Commands → Viu → ExportClip
"""
import json
import os

import csc


def command_name():
    return "Viu.ExportClip"


def run(scene):
    pending = os.path.join(os.path.dirname(__file__), "viu_mocap_pending.json")
    if not os.path.isfile(pending):
        scene.error("Нет viu_mocap_pending.json — сначала cascadeur_import_reference / export в Вью.")
        return
    with open(pending, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    out = (data.get("export_fbx") or "").strip().replace("\\\\", "/")
    if not out:
        scene.error("В pending нет export_fbx.")
        return
    parent = os.path.dirname(out)
    if parent and not os.path.isdir(parent):
        try:
            os.makedirs(parent, exist_ok=True)
        except OSError as exc:
            scene.error("Не создать папку Export: " + str(exc))
            return

    app = csc.app.get_application()
    current = app.get_scene_manager().current_scene()
    if current is None:
        scene.error("Нет активной сцены.")
        return
    loader = app.get_tools_manager().get_tool("FbxSceneLoader").get_fbx_loader(current)
    loader.export_all_objects(out)
    marker = out + ".viu_done"
    try:
        with open(marker, "w", encoding="utf-8") as fh:
            fh.write(json.dumps({"export_fbx": out, "slug": data.get("slug") or ""}, ensure_ascii=False))
    except OSError:
        pass
    scene.info("Exported: " + out)
'''

CONSOLE_REF_TEMPLATE = '''"""Viu — подсказка Import Reference (Python Console)."""
import csc

VIDEO = r"{video_path}"
FRAMES = r"{frames_dir}"

app = csc.app.get_application()
am = app.get_action_manager()
for name in (
    "File.Import Reference video",
    "Import.Reference video",
    "File.Reference video",
):
    try:
        am.call_action(name)
        print("Opened:", name)
        break
    except Exception as exc:
        print(name, exc)
print("VIDEO:", VIDEO)
print("FRAMES:", FRAMES)
print("UI: File → Import → Reference video → Choose VIDEO → Frames path → Import")
print("Потом: выдели кадры на Timeline → кнопка Mocap")
'''

CONSOLE_EXPORT_TEMPLATE = '''"""Viu — Export FBX клипа (Python Console)."""
import csc
import os

OUT = r"{export_fbx}"

app = csc.app.get_application()
scene_tab = app.get_scene_manager().current_scene()
if scene_tab is None:
    raise RuntimeError("No scene")
parent = os.path.dirname(OUT)
if parent and not os.path.isdir(parent):
    os.makedirs(parent, exist_ok=True)
loader = app.get_tools_manager().get_tool("FbxSceneLoader").get_fbx_loader(scene_tab)
loader.export_all_objects(OUT.replace("\\\\", "/"))
print("Exported:", OUT)
'''


def _slugify(text: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9_\-]+", "_", (text or "").strip().lower())
    s = re.sub(r"_+", "_", s).strip("_")
    return (s or "clip")[:48]


def mocap_refs_staging_dir(config: Config) -> Path:
    """Стабильная копия kept mp4 для Cascadeur."""
    from ...anabarra_layout import library_root

    p = library_root(config) / "Lab" / "Cascadeur" / "Refs"
    p.mkdir(parents=True, exist_ok=True)
    return p


def mocap_frames_dir(config: Config, slug: str) -> Path:
    p = mocap_refs_staging_dir(config).parent / "Frames" / _slugify(slug)
    p.mkdir(parents=True, exist_ok=True)
    return p


def pending_mocap_path(config: Config) -> Path:
    p = config.data_dir / "lab" / "mocap" / "pending_mocap.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def mocap_queue_path(config: Config) -> Path:
    return config.data_dir / "lab" / "mocap" / "queue.json"


def load_pending_mocap(config: Config) -> Dict[str, Any]:
    path = pending_mocap_path(config)
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def resolve_kept_clip(
    config: Config,
    *,
    clip_id: str = "",
    path: str = "",
) -> Tuple[Optional[ComfyClip], Optional[Path], str]:
    """Найти kept-клип: явный path / clip_id / последний kept / файл в kept/."""
    store = ComfyClipStore(clip_review_path(config)).load()
    if path:
        p = Path(path).expanduser()
        if not p.is_file():
            return None, None, f"Нет файла: {p}"
        for c in store.kept():
            if Path(c.path).resolve() == p.resolve():
                return c, p, ""
        return None, p, ""

    if clip_id:
        c = store.get(clip_id)
        if c is None:
            return None, None, f"clip_id не найден: {clip_id}"
        p = Path(c.path)
        if not p.is_file():
            return c, None, f"Клип есть в store, файла нет: {p}"
        return c, p, ""

    kept = store.kept()
    if kept:
        kept_sorted = sorted(kept, key=lambda c: c.kept_at or c.created_at, reverse=True)
        c = kept_sorted[0]
        p = Path(c.path)
        if p.is_file():
            return c, p, ""

    kept_dir = comfy_kept_dir(config)
    mp4s = sorted(kept_dir.glob("*.mp4"), key=lambda x: x.stat().st_mtime, reverse=True)
    if mp4s:
        return None, mp4s[0], ""
    return None, None, (
        "Нет kept-клипов. Сначала comfy_mocap → выбери ракурс "
        "(«лучший: front») или положи mp4 в Lab/Refs/kept/."
    )


def stage_reference_video(config: Config, src: Path, slug: str) -> Path:
    dest_dir = mocap_refs_staging_dir(config)
    dest = dest_dir / f"{_slugify(slug)}{src.suffix.lower() or '.mp4'}"
    if src.resolve() != dest.resolve():
        shutil.copy2(src, dest)
    return dest


def build_pending_payload(
    config: Config,
    *,
    video: Path,
    slug: str,
    action: str = "",
    clip_id: str = "",
    enters_from: Optional[List[str]] = None,
    exits_to: Optional[List[str]] = None,
) -> Dict[str, Any]:
    safe = _slugify(slug)
    export_dir = cascadeur_export(config)
    export_fbx = export_dir / f"shanya_{safe}.fbx"
    frames = mocap_frames_dir(config, safe)
    return {
        "video": str(video.resolve()),
        "frames_dir": str(frames.resolve()),
        "export_fbx": str(export_fbx.resolve()),
        "slug": safe,
        "action": action or safe,
        "clip_id": clip_id,
        "enters_from": list(enters_from or []),
        "exits_to": list(exits_to or []),
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "status": "reference_ready",
    }


def write_pending_mocap(config: Config, payload: Dict[str, Any]) -> Tuple[bool, str]:
    text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    written: List[str] = []
    lab = pending_mocap_path(config)
    try:
        lab.write_text(text, encoding="utf-8")
        written.append(str(lab))
    except OSError as exc:
        return False, str(exc)

    for scripts in discover_commands_dirs(config):
        if scripts.name != "commands" and "commands" not in scripts.as_posix().lower():
            continue
        target = scripts / PENDING_REF_FILENAME
        try:
            scripts.mkdir(parents=True, exist_ok=True)
            target.write_text(text, encoding="utf-8")
            written.append(str(target))
        except OSError:
            pass
    return True, "pending:\n" + "\n".join(f"  • {p}" for p in written)


def deploy_mocap_commands(config: Config) -> Tuple[bool, str]:
    primary = cascadeur_scripts_dir(config)
    targets = discover_commands_dirs(config)
    if primary not in targets:
        targets = [primary] + list(targets)
    written: List[str] = []
    errors: List[str] = []
    for scripts in targets:
        if scripts.name != "commands" and "commands" not in scripts.as_posix().lower():
            continue
        try:
            scripts.mkdir(parents=True, exist_ok=True)
            for name, body in (
                (REF_COMMAND_FILENAME, IMPORT_REF_COMMAND_SOURCE),
                (EXPORT_COMMAND_FILENAME, EXPORT_CLIP_COMMAND_SOURCE),
            ):
                path = scripts / name
                path.write_text(body, encoding="utf-8")
                written.append(str(path))
        except OSError as exc:
            errors.append(f"{scripts}: {exc}")
    if not written:
        try:
            primary.mkdir(parents=True, exist_ok=True)
            (primary / REF_COMMAND_FILENAME).write_text(IMPORT_REF_COMMAND_SOURCE, encoding="utf-8")
            (primary / EXPORT_COMMAND_FILENAME).write_text(EXPORT_CLIP_COMMAND_SOURCE, encoding="utf-8")
            written.extend(
                [
                    str(primary / REF_COMMAND_FILENAME),
                    str(primary / EXPORT_COMMAND_FILENAME),
                ]
            )
        except OSError as exc:
            return False, f"Не удалось записать команды: {exc}"
    msg = "Команды Cascadeur:\n" + "\n".join(f"  • {p}" for p in written)
    if errors:
        msg += "\nОшибки:\n" + "\n".join(errors)
    return True, msg


def write_console_scripts(config: Config, payload: Dict[str, Any]) -> Tuple[bool, str]:
    art = config.data_dir / "lab" / "mocap" / "artifacts"
    art.mkdir(parents=True, exist_ok=True)
    ref = art / CONSOLE_REF_FILENAME
    exp = art / CONSOLE_EXPORT_FILENAME
    try:
        ref.write_text(
            CONSOLE_REF_TEMPLATE.format(
                video_path=payload.get("video") or "",
                frames_dir=payload.get("frames_dir") or "",
            ),
            encoding="utf-8",
        )
        exp.write_text(
            CONSOLE_EXPORT_TEMPLATE.format(export_fbx=payload.get("export_fbx") or ""),
            encoding="utf-8",
        )
    except OSError as exc:
        return False, str(exc)
    return True, f"Console scripts:\n  • {ref}\n  • {exp}"


def mocap_checklist(payload: Dict[str, Any]) -> str:
    video = payload.get("video") or "?"
    frames = payload.get("frames_dir") or "?"
    export = payload.get("export_fbx") or "?"
    slug = payload.get("slug") or "?"
    return (
        f"### MoCap checklist (`{slug}`)\n"
        "1. В Cascadeur: **эталон Шани** уже в сцене (New scene → import character FBX).\n"
        "2. **Commands → Reload scripts** → **Viu → ImportReference**\n"
        "   (или File → Import → **Reference video**).\n"
        f"3. Video: `{video}`\n"
        f"4. Frames path: `{frames}` (H.264 mp4).\n"
        "5. Import → plane с видео.\n"
        "6. На Timeline выдели диапазон ≈ длине клипа.\n"
        "7. Toolbar → **Mocap** (первый раз скачает mocap.pt ~700MB).\n"
        "8. Поправь контакты/стопы если нужно.\n"
        "9. **Commands → Viu → ExportClip** (или cascadeur_export_clip в Вью после Export).\n"
        f"10. Цель FBX: `{export}` → потом «Обновить аниматор» в Unity.\n"
    )


def prepare_import_reference(
    config: Config,
    *,
    clip_id: str = "",
    path: str = "",
    slug: str = "",
) -> Tuple[bool, str, Dict[str, Any]]:
    """Подготовить pending + deploy команд для Reference video."""
    clip, video, err = resolve_kept_clip(config, clip_id=clip_id, path=path)
    if err and video is None:
        return False, err, {}
    assert video is not None

    use_slug = slug or (clip.catalog_slug if clip else "") or video.stem
    use_slug = _slugify(use_slug)
    staged = stage_reference_video(config, video, use_slug)
    payload = build_pending_payload(
        config,
        video=staged,
        slug=use_slug,
        action=(clip.action if clip else use_slug),
        clip_id=(clip.id if clip else ""),
        enters_from=(clip.enters_from if clip else None),
        exits_to=(clip.exits_to if clip else None),
    )

    ok_dep, dep_msg = deploy_mocap_commands(config)
    if not ok_dep:
        return False, dep_msg, payload

    ok_pend, pend_msg = write_pending_mocap(config, payload)
    if not ok_pend:
        return False, pend_msg, payload

    ok_con, con_msg = write_console_scripts(config, payload)
    checklist = mocap_checklist(payload)
    try:
        journal = config.data_dir / "lab" / "mocap" / "journal.md"
        journal.parent.mkdir(parents=True, exist_ok=True)
        with journal.open("a", encoding="utf-8") as fh:
            fh.write(f"\n## {payload['created_at']} import_reference\n\n{checklist}\n")
    except OSError:
        pass

    # очередь
    try:
        qpath = mocap_queue_path(config)
        queue = []
        if qpath.is_file():
            raw = json.loads(qpath.read_text(encoding="utf-8"))
            if isinstance(raw, list):
                queue = raw
        queue = [x for x in queue if isinstance(x, dict) and x.get("slug") != use_slug]
        queue.append(payload)
        qpath.write_text(json.dumps(queue, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except (OSError, json.JSONDecodeError):
        pass

    lines = [
        f"Reference готов: `{staged.name}` → Cascadeur",
        f"slug: `{use_slug}`",
        dep_msg,
        pend_msg,
    ]
    if ok_con:
        lines.append(con_msg)
    lines.append(scripts_status_text(config))
    lines.append("")
    lines.append(checklist)
    lines.append(
        "После MoCap: в чате **cascadeur_export_clip** "
        "(или Commands → Viu → ExportClip, потом снова export_clip для каталога)."
    )
    return True, "\n".join(lines), payload


def register_exported_clip(config: Config, payload: Dict[str, Any], fbx: Path) -> str:
    """Отметить FBX в animation_catalog."""
    slug = str(payload.get("slug") or fbx.stem)
    notes: List[str] = []
    try:
        from ...animation_catalog import AnimationCatalogStore, animation_catalog_path
        from ...animation_catalog.models import AnimationWish, STATUS_IMPORTED, STATUS_WISHED

        store = AnimationCatalogStore(animation_catalog_path(config)).load()
        wish = store.get_by_slug(slug)
        if wish is None:
            wish = AnimationWish(
                slug=slug,
                category="special",
                title_ru=slug.replace("_", " "),
                when_used="Cascadeur MoCap export",
                looks_like=str(payload.get("action") or slug),
                purpose="Клип из Comfy → Cascadeur MoCap",
                status=STATUS_WISHED,
            )
        wish.clip_file = str(fbx)
        wish.status = STATUS_IMPORTED
        wish.ref_video = str(payload.get("video") or wish.ref_video)
        if payload.get("enters_from"):
            wish.enters_from = list(payload.get("enters_from") or [])
        if payload.get("exits_to"):
            wish.exits_to = list(payload.get("exits_to") or [])
        store.upsert(wish)
        store.save()
        notes.append(f"catalog: `{slug}` → {fbx.name} (imported)")
    except Exception as exc:  # noqa: BLE001
        notes.append(f"catalog: не обновлён ({exc})")

    payload = dict(payload)
    payload["status"] = "exported"
    payload["exported_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    payload["export_fbx"] = str(fbx.resolve())
    try:
        write_pending_mocap(config, payload)
    except Exception:
        pass
    return "; ".join(notes) if notes else "ok"


def finalize_export_clip(
    config: Config,
    *,
    slug: str = "",
    fbx_path: str = "",
) -> Tuple[bool, str]:
    """Проверить/зафиксировать Export FBX после MoCap."""
    payload = load_pending_mocap(config)
    if not payload and not fbx_path:
        return False, "Нет pending_mocap — сначала cascadeur_import_reference."

    candidates: List[Path] = []
    if fbx_path:
        candidates.append(Path(fbx_path).expanduser())
    if payload.get("export_fbx"):
        candidates.append(Path(str(payload["export_fbx"])))
    use_slug = _slugify(slug or str(payload.get("slug") or "clip"))
    export_dir = cascadeur_export(config)
    candidates.append(export_dir / f"shanya_{use_slug}.fbx")

    fbx: Optional[Path] = None
    for c in candidates:
        if c.is_file() and c.stat().st_size > 0:
            fbx = c
            break

    if fbx is None:
        # Deploy export command + checklist — Ден ещё не экспортировал
        ok_dep, dep_msg = deploy_mocap_commands(config)
        if payload:
            write_pending_mocap(config, payload)
            write_console_scripts(config, payload)
        target = candidates[0] if candidates else export_dir / f"shanya_{use_slug}.fbx"
        return False, (
            f"FBX ещё нет: `{target}`\n"
            f"{dep_msg}\n\n"
            "В Cascadeur после MoCap:\n"
            "  Commands → Reload scripts → **Viu → ExportClip**\n"
            "или Python Console → Load "
            f"`.viu/lab/mocap/artifacts/{CONSOLE_EXPORT_FILENAME}` → Execute.\n"
            "Потом снова **cascadeur_export_clip**."
        )

    note = register_exported_clip(config, payload or {"slug": use_slug}, fbx)
    done = Path(str(fbx) + ".viu_done")
    if done.is_file():
        try:
            done.unlink()
        except OSError:
            pass
    return True, (
        f"Export OK: `{fbx}`\n{note}\n"
        "Дальше: Unity закрыт → «Обновить аниматор» / unity_sync_animations."
    )


def mocap_status_text(config: Config) -> str:
    lines = ["Cascadeur MoCap (Comfy → Reference → Export)"]
    kept_dir = comfy_kept_dir(config)
    mp4s = sorted(kept_dir.glob("*.mp4"), key=lambda p: p.stat().st_mtime, reverse=True) if kept_dir.is_dir() else []
    store = ComfyClipStore(clip_review_path(config)).load()
    lines.append(f"• kept mp4: {len(mp4s)} в {kept_dir}")
    if mp4s:
        lines.append(f"  последний: {mp4s[0].name}")
    lines.append(f"• store kept: {len(store.kept())}")
    pending = load_pending_mocap(config)
    if pending:
        lines.append(
            f"• pending: slug=`{pending.get('slug')}` status=`{pending.get('status')}`"
        )
        lines.append(f"  video: {pending.get('video')}")
        lines.append(f"  export: {pending.get('export_fbx')}")
    else:
        lines.append("• pending: нет — cascadeur_import_reference")
    lines.append(f"• staging: {mocap_refs_staging_dir(config)}")
    lines.append(f"• Animations: {cascadeur_export(config)}")
    return "\n".join(lines)
