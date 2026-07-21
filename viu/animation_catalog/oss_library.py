"""Локальная OSS-библиотека анимаций (Mesh2Motion / ручные FBX) → Inbox → каталог."""

from __future__ import annotations

import json
import shutil
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ..anabarra_layout import inbox_dir
from ..config import Config
from .models import DEFAULT_WISHES, AnimationWish
from .paths import animation_catalog_path, oss_animations_dir

_REGISTRY_REV = 1
_REGISTRY_NAME = "oss_animations.json"
_TEMPLATES = Path(__file__).resolve().parent / "templates"
_MESH2MOTION_WEB = "https://mesh2motion.org/"


def oss_export_dir(config: Config) -> Path:
    """Готовые копии с именами Mixamo для ручного переноса в Inbox."""
    p = oss_animations_dir(config) / "_export"
    p.mkdir(parents=True, exist_ok=True)
    return p


def registry_path(config: Config) -> Path:
    return config.data_dir / _REGISTRY_NAME


def _empty_registry() -> Dict[str, Any]:
    return {"_viu_rev": _REGISTRY_REV, "bootstrap": {}, "by_slug": {}}


def _wave1_defaults() -> Dict[str, Dict[str, str]]:
    out: Dict[str, Dict[str, str]] = {}
    for w in DEFAULT_WISHES:
        if w.wave > 1:
            continue
        hint = (w.mixamo_hints or [w.slug.replace("_", " ").title()])[0]
        inbox = hint if hint.lower().endswith(".fbx") else f"{hint}.fbx"
        out[w.slug] = {
            "inbox_name": inbox,
            "file": f"{w.slug}.fbx",
            "url": "",
            "source": "mesh2motion",
            "note": "Экспорт из mesh2motion.org или положи FBX вручную",
        }
    return out


def ensure_registry(config: Config) -> Dict[str, Any]:
    path = registry_path(config)
    if path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            data = _empty_registry()
    else:
        tpl = _TEMPLATES / _REGISTRY_NAME
        if tpl.is_file():
            try:
                data = json.loads(tpl.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                data = _empty_registry()
        else:
            data = _empty_registry()

    defaults = _wave1_defaults()
    by_slug = dict(data.get("by_slug") or {})
    for slug, row in defaults.items():
        if slug not in by_slug:
            by_slug[slug] = row
        else:
            cur = by_slug[slug]
            for key in ("inbox_name", "file", "source", "note"):
                if not str(cur.get(key) or "").strip():
                    cur[key] = row.get(key, "")
    data["by_slug"] = by_slug
    if not data.get("bootstrap"):
        tpl = _TEMPLATES / _REGISTRY_NAME
        if tpl.is_file():
            try:
                boot = json.loads(tpl.read_text(encoding="utf-8")).get("bootstrap") or {}
                data["bootstrap"] = boot
            except (OSError, json.JSONDecodeError):
                data["bootstrap"] = {}
    data["_viu_rev"] = _REGISTRY_REV
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return data


def _slug_row(registry: Dict[str, Any], slug: str) -> Optional[Dict[str, str]]:
    row = (registry.get("by_slug") or {}).get(slug)
    return row if isinstance(row, dict) else None


def local_oss_path(config: Config, slug: str, registry: Optional[Dict[str, Any]] = None) -> Optional[Path]:
    reg = registry or ensure_registry(config)
    row = _slug_row(reg, slug)
    if not row:
        return None
    fname = str(row.get("file") or f"{slug}.fbx").strip()
    if not fname:
        return None
    p = oss_animations_dir(config) / fname
    return p if p.is_file() else None


def _download(url: str, dest: Path, *, timeout: float = 120.0) -> Tuple[bool, str]:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.is_file() and dest.stat().st_size > 0:
        return True, f"уже есть: {dest.name}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Viu/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = resp.read()
        dest.write_bytes(data)
        return True, f"скачано {dest.name} ({len(data) // 1024} KB)"
    except (OSError, urllib.error.URLError) as exc:
        return False, f"не скачалось {dest.name}: {exc}"


def bootstrap_sources(config: Config) -> Tuple[int, List[str]]:
    """Скачать GLB/Blend пакеты Mesh2Motion в OSS/_mesh2motion и OSS/_sources."""
    reg = ensure_registry(config)
    root = oss_animations_dir(config)
    lines: List[str] = []
    ok_n = 0
    for _key, spec in (reg.get("bootstrap") or {}).items():
        if not isinstance(spec, dict):
            continue
        url = str(spec.get("url") or "").strip()
        dest_rel = str(spec.get("dest") or "").strip()
        if not url or not dest_rel:
            continue
        dest = root / dest_rel
        ok, msg = _download(url, dest)
        lines.append(msg)
        if ok:
            ok_n += 1
    lines.append(
        f"Папка OSS: {root}\n"
        f"Дальше: mesh2motion.org → экспорт FBX как {{slug}}.fbx в эту папку "
        f"или animation_oss_prepare wave=1"
    )
    return ok_n, lines


def download_slug(config: Config, slug: str) -> Tuple[bool, str]:
    reg = ensure_registry(config)
    row = _slug_row(reg, slug)
    if not row:
        return False, f"Нет slug={slug} в реестре OSS"
    url = str(row.get("url") or "").strip()
    if not url:
        return False, f"Для {slug} нет url — положи {row.get('file')} в {oss_animations_dir(config)}"
    dest = oss_animations_dir(config) / str(row.get("file") or f"{slug}.fbx")
    ok, msg = _download(url, dest)
    return ok, msg


def _copy_to_inbox(src: Path, inbox_name: str, config: Config) -> Path:
    inbox = inbox_dir(config)
    inbox.mkdir(parents=True, exist_ok=True)
    dest = inbox / inbox_name
    if dest.exists():
        stem, suffix = dest.stem, dest.suffix
        n = 2
        while dest.exists():
            dest = inbox / f"{stem}_{n}{suffix}"
            n += 1
    shutil.copy2(src, dest)
    return dest


def fetch_to_inbox(
    config: Config,
    slug: str,
    *,
    accept: bool = False,
) -> Tuple[bool, str]:
    """Скопировать OSS FBX в Inbox (имя как Mixamo для matcher)."""
    reg = ensure_registry(config)
    row = _slug_row(reg, slug)
    if not row:
        return False, f"Неизвестный slug: {slug}"

    src = local_oss_path(config, slug, reg)
    if src is None:
        dl_ok, dl_msg = download_slug(config, slug)
        if dl_ok:
            src = local_oss_path(config, slug, reg)
        if src is None:
            return False, (
                f"Нет файла для `{slug}`.\n"
                f"  {dl_msg}\n"
                f"  Положи `{row.get('file')}` в {oss_animations_dir(config)}\n"
                f"  или экспортируй с {_MESH2MOTION_WEB}"
            )

    inbox_name = str(row.get("inbox_name") or src.name).strip()
    dest = _copy_to_inbox(src, inbox_name, config)
    lines = [f"→ Inbox: {dest.name}", f"  из {src}"]

    if accept:
        from ..drop_router import accept_single_animation

        report = accept_single_animation(config, copy_to_unity=True, remove_from_inbox=True)
        lines.append(report.format())
        return report.ok, "\n".join(lines)

    lines.append("Дальше: «Принять анимацию (Inbox)» или animation_oss_fetch accept=1")
    return True, "\n".join(lines)


def prepare_exports(
    config: Config,
    *,
    wave: int = 1,
) -> Tuple[int, List[str]]:
    """Скопировать доступные OSS FBX в OSS/_export с именами Mixamo."""
    reg = ensure_registry(config)
    out_dir = oss_export_dir(config)
    lines: List[str] = []
    n = 0
    for w in DEFAULT_WISHES:
        if w.wave > wave:
            continue
        src = local_oss_path(config, w.slug, reg)
        if src is None:
            continue
        row = _slug_row(reg, w.slug) or {}
        name = str(row.get("inbox_name") or src.name)
        dest = out_dir / name
        shutil.copy2(src, dest)
        n += 1
        lines.append(f"  • {w.slug} → _export/{name}")
    if not lines:
        lines.append(
            f"Нет FBX в {oss_animations_dir(config)}. "
            f"Сначала animation_oss_bootstrap, потом экспорт с Mesh2Motion."
        )
    else:
        lines.insert(0, f"Готово в {out_dir}:")
    return n, lines


def _wish_needs_clip(wish: AnimationWish) -> bool:
    return wish.status == "wished" and not (wish.ref_video or wish.clip_file)


def pick_next_slug(store: "AnimationCatalogStore", config: Config) -> Optional[str]:
    reg = ensure_registry(config)
    for wish in store.ordered_holes():
        if local_oss_path(config, wish.slug, reg):
            return wish.slug
    return None


def status_text(config: Config) -> str:
    from .store import AnimationCatalogStore

    reg = ensure_registry(config)
    store = AnimationCatalogStore(animation_catalog_path(config)).load()
    oss_dir = oss_animations_dir(config)
    holes = [w for w in store.ordered_holes() if _wish_needs_clip(w)]
    have: List[str] = []
    need: List[str] = []
    for w in holes[:24]:
        if local_oss_path(config, w.slug, reg):
            have.append(w.slug)
        else:
            need.append(w.slug)
    lines = [
        "OSS-анимации (Mesh2Motion / локальные FBX)",
        f"Папка: {oss_dir}",
        f"Реестр: {registry_path(config)}",
        f"Дыры wave≤1 с OSS-файлом: {len(have)}",
        f"Дыры без файла: {len(need)}",
    ]
    if have:
        lines.append("Можно подтянуть: " + ", ".join(have[:16]))
    if need:
        lines.append("Нет FBX: " + ", ".join(need[:16]))
    lines.append(
        f"\nКоманды:\n"
        f"  animation_oss_bootstrap — скачать GLB/Blend Mesh2Motion\n"
        f"  animation_oss_fetch slug=walk [accept=1]\n"
        f"  animation_oss_fetch auto=1 — первая дыра с файлом → Inbox\n"
        f"  animation_oss_prepare wave=1 — копии в _export/\n"
        f"  Веб: {_MESH2MOTION_WEB}"
    )
    return "\n".join(lines)


def fetch_auto(
    config: Config,
    *,
    accept: bool = False,
) -> Tuple[bool, str]:
    from .store import AnimationCatalogStore

    store = AnimationCatalogStore(animation_catalog_path(config)).load()
    slug = pick_next_slug(store, config)
    if not slug:
        return False, (
            "Нет дыр каталога с готовым OSS-файлом.\n"
            + status_text(config).split("\n", 3)[-1]
        )
    ok, msg = fetch_to_inbox(config, slug, accept=accept)
    wish = store.get_by_slug(slug)
    title = wish.title_ru if wish else slug
    return ok, f"[{slug}] {title}\n{msg}"
