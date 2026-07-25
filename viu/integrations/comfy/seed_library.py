"""Библиотека эталонов позы (I2V) в Anabarra — не затирается обновлением Вью.

U:\\Anabarra\\Library\\Lab\\Refs\\seeds\\
  index.json          — каталог эталонов
  slug_seeds.json     — привязка start/end к catalog_slug
  <id>.png            — файлы
  raw\\                — исходники HS2 до доработки
"""

from __future__ import annotations

import json
import re
import shutil
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ...config import Config
from .paths import comfy_seed_frames_dir

_INDEX = "index.json"
_SLUG_MAP = "slug_seeds.json"
_IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp"}

NATURAL_BODY_HINT = (
    "Перерисуй / используй как эталон реалистичное тело: натуральные пропорции, "
    "мягкая кожа, без аниме-глаз и кукольной пластики HS2. Полный рост, белый фон, ¾."
)

NATURAL_BODY_PROMPT_ADD = (
    "natural realistic body proportions, soft skin, photorealistic figure, "
    "not anime, not doll face, full body, white studio background"
)


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def seeds_root(config: Config) -> Path:
    root = comfy_seed_frames_dir(config)
    (root / "raw").mkdir(parents=True, exist_ok=True)
    return root


def index_path(config: Config) -> Path:
    return seeds_root(config) / _INDEX


def slug_map_path(config: Config) -> Path:
    return seeds_root(config) / _SLUG_MAP


@dataclass
class SeedEntry:
    id: str
    path: str
    title: str = ""
    slug: str = ""  # основная анимация (подсказка)
    source: str = "import"  # hs2 | import | last_frame | refined
    notes: str = ""
    en_pose: str = ""
    status: str = "ready"  # ready | needs_refine | refining
    raw_path: str = ""
    refined_path: str = ""
    created_at: str = ""
    tags: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "SeedEntry":
        tags = [str(x) for x in (d.get("tags") or []) if str(x).strip()]
        return cls(
            id=str(d.get("id") or uuid.uuid4().hex[:10]),
            path=str(d.get("path") or ""),
            title=str(d.get("title") or ""),
            slug=str(d.get("slug") or "").strip(),
            source=str(d.get("source") or "import"),
            notes=str(d.get("notes") or ""),
            en_pose=str(d.get("en_pose") or ""),
            status=str(d.get("status") or "ready"),
            raw_path=str(d.get("raw_path") or ""),
            refined_path=str(d.get("refined_path") or ""),
            created_at=str(d.get("created_at") or ""),
            tags=tags,
        )

    def resolve_path(self) -> Optional[Path]:
        """Актуальный файл: refined → path."""
        for cand in (self.refined_path, self.path):
            p = Path(cand) if cand else None
            if p is not None and p.is_file():
                return p
        return None

    def label(self) -> str:
        mark = {"ready": "·", "needs_refine": "✎", "refining": "…"}.get(self.status, "?")
        title = self.title or Path(self.path).stem or self.id
        slug = f" [{self.slug}]" if self.slug else ""
        return f"{mark} {title}{slug}"


def _read_json(path: Path, default: Any) -> Any:
    if not path.is_file():
        return default
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return default
    return data


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def load_library(config: Config) -> List[SeedEntry]:
    raw = _read_json(index_path(config), {"version": 1, "items": []})
    items = raw.get("items") if isinstance(raw, dict) else []
    out: List[SeedEntry] = []
    if isinstance(items, list):
        for x in items:
            if isinstance(x, dict):
                out.append(SeedEntry.from_dict(x))
    # Подхватить файлы без записи в index (старые last-frame).
    known = {Path(e.path).resolve() for e in out if e.path}
    known |= {Path(e.refined_path).resolve() for e in out if e.refined_path}
    root = seeds_root(config)
    for p in sorted(root.iterdir(), key=lambda x: x.stat().st_mtime if x.is_file() else 0, reverse=True):
        if not p.is_file() or p.suffix.lower() not in _IMAGE_EXT:
            continue
        if p.name in (_INDEX, _SLUG_MAP) or p.name.endswith(".tmp"):
            continue
        try:
            if p.resolve() in known:
                continue
        except OSError:
            continue
        out.append(
            SeedEntry(
                id=uuid.uuid4().hex[:10],
                path=str(p),
                title=p.stem,
                source="last_frame" if "_last" in p.stem else "import",
                created_at=_now(),
            )
        )
    return out


def save_library(config: Config, entries: List[SeedEntry]) -> None:
    _write_json(
        index_path(config),
        {"version": 1, "items": [e.to_dict() for e in entries]},
    )


def get_entry(config: Config, seed_id: str) -> Optional[SeedEntry]:
    sid = (seed_id or "").strip()
    if not sid:
        return None
    for e in load_library(config):
        if e.id == sid:
            return e
    return None


def upsert_entry(config: Config, entry: SeedEntry) -> SeedEntry:
    items = load_library(config)
    for i, e in enumerate(items):
        if e.id == entry.id:
            items[i] = entry
            save_library(config, items)
            return entry
    items.insert(0, entry)
    save_library(config, items)
    return entry


def _safe_stem(name: str) -> str:
    s = re.sub(r"[^\w.\-]+", "_", (name or "pose").strip(), flags=re.UNICODE)
    return (s[:60] or "pose").strip("._") or "pose"


def import_seed(
    config: Config,
    source: Path,
    *,
    title: str = "",
    slug: str = "",
    from_hs2: bool = False,
    activate: bool = False,
) -> Tuple[bool, str, Optional[SeedEntry]]:
    """Положить скрин в библиотеку эталонов (Anabarra)."""
    src = Path(source)
    if not src.is_file():
        return False, f"Файл не найден: {src}", None
    if src.suffix.lower() not in _IMAGE_EXT:
        return False, "Нужен PNG/JPG/WebP.", None

    root = seeds_root(config)
    sid = uuid.uuid4().hex[:10]
    stem = _safe_stem(title or slug or src.stem)
    dest = root / f"{sid}_{stem}{src.suffix.lower()}"
    try:
        shutil.copy2(src, dest)
    except OSError as exc:
        return False, f"Не скопировать: {exc}", None

    entry = SeedEntry(
        id=sid,
        path=str(dest),
        title=title or stem,
        slug=(slug or "").strip(),
        source="hs2" if from_hs2 else "import",
        status="needs_refine" if from_hs2 else "ready",
        created_at=_now(),
        tags=["hs2"] if from_hs2 else [],
    )
    if from_hs2:
        raw_dest = root / "raw" / dest.name
        try:
            shutil.copy2(src, raw_dest)
            entry.raw_path = str(raw_dest)
        except OSError:
            pass
        entry.notes = NATURAL_BODY_HINT

    upsert_entry(config, entry)
    msg = f"Эталон в библиотеке: {entry.label()}\n{dest}"
    if from_hs2:
        msg += "\nПомечен как HS2 — жми «Доработать» (описание позы + замена на натуральный кадр)."
    if activate:
        ok2, msg2 = activate_seed(config, entry.id)
        msg += "\n" + msg2
        if not ok2:
            return False, msg, entry
    return True, msg, entry


def activate_seed(config: Config, seed_id: str, *, role: str = "start") -> Tuple[bool, str]:
    """Сделать эталон активным start (или stage end) для следующей съёмки."""
    from .seed_pose import (
        _COMFY_SEED_NAME,
        save_seed_state,
        stage_seed_for_comfy,
    )

    entry = get_entry(config, seed_id)
    if entry is None:
        return False, f"Нет эталона id={seed_id}"
    path = entry.resolve_path()
    if path is None:
        return False, f"Файл эталона пропал: {entry.path}"

    role = (role or "start").strip().lower()
    if role == "end":
        return stage_end_seed(config, path)

    ok, msg, comfy_name = stage_seed_for_comfy(config, path)
    if not ok:
        return False, msg
    save_seed_state(config, enabled=True, path=str(path), comfy_name=comfy_name)

    from ...lab.comfy_pipeline import COMFY_TOPIC
    from ...lab.session import load_session, new_session, save_session

    session = load_session(config, COMFY_TOPIC) or new_session(COMFY_TOPIC)
    session.meta["i2v_seed_enabled"] = True
    session.meta["i2v_seed_path"] = str(path)
    session.meta["i2v_seed_comfy"] = comfy_name
    session.meta["i2v_seed_id"] = entry.id
    if entry.en_pose:
        session.meta["i2v_seed_en_pose"] = entry.en_pose
    if entry.source in ("hs2",) or entry.status == "needs_refine":
        session.meta["i2v_seed_natural_hint"] = NATURAL_BODY_PROMPT_ADD
    save_session(config, session)
    return True, f"Старт I2V: {entry.label()} → {comfy_name or _COMFY_SEED_NAME}"


_COMFY_END_NAME = "viu_pose_seed_end.png"


def stage_end_seed(config: Config, seed_path: Path) -> Tuple[bool, str]:
    from .paths import comfy_input_dir, resolve_comfy_root
    from .seed_pose import save_seed_state, load_seed_state

    root = resolve_comfy_root(config)
    if root is None:
        return False, "ComfyUI root не найден"
    if not seed_path.is_file():
        return False, f"нет файла: {seed_path}"
    dest = comfy_input_dir(root) / _COMFY_END_NAME
    try:
        shutil.copy2(seed_path, dest)
    except OSError as exc:
        return False, f"не скопировать end seed: {exc}"

    from ...lab.comfy_pipeline import COMFY_TOPIC
    from ...lab.session import load_session, new_session, save_session

    session = load_session(config, COMFY_TOPIC) or new_session(COMFY_TOPIC)
    session.meta["i2v_end_seed_path"] = str(seed_path)
    session.meta["i2v_end_seed_comfy"] = _COMFY_END_NAME
    save_session(config, session)
    # Не сбрасываем start; только дополняем.
    st = load_seed_state(config)
    save_seed_state(
        config,
        enabled=bool(st.get("enabled")),
        path=str(st.get("path") or ""),
        comfy_name=str(st.get("comfy_name") or ""),
    )
    return True, f"Конец I2V (если нода умеет end_image): {_COMFY_END_NAME}"


def load_slug_seeds(config: Config) -> Dict[str, Dict[str, str]]:
    raw = _read_json(slug_map_path(config), {})
    if not isinstance(raw, dict):
        return {}
    out: Dict[str, Dict[str, str]] = {}
    for slug, val in raw.items():
        if slug in ("version",):
            continue
        if isinstance(val, dict):
            out[str(slug)] = {
                "start": str(val.get("start") or ""),
                "end": str(val.get("end") or ""),
            }
    return out


def save_slug_seeds(config: Config, mapping: Dict[str, Dict[str, str]]) -> None:
    payload = {"version": 1, **mapping}
    _write_json(slug_map_path(config), payload)


def bind_seed_to_slug(
    config: Config,
    slug: str,
    seed_id: str,
    *,
    role: str = "start",
) -> Tuple[bool, str]:
    slug = (slug or "").strip()
    if not slug:
        return False, "Нужен catalog_slug анимации."
    entry = get_entry(config, seed_id)
    if entry is None:
        return False, f"Нет эталона id={seed_id}"
    role = (role or "start").strip().lower()
    if role not in ("start", "end"):
        return False, "role = start | end"
    mapping = load_slug_seeds(config)
    slot = mapping.setdefault(slug, {"start": "", "end": ""})
    slot[role] = entry.id
    if not entry.slug:
        entry.slug = slug
        upsert_entry(config, entry)
    save_slug_seeds(config, mapping)
    return True, f"`{slug}` ← {role}: {entry.label()}"


def seeds_for_slug(config: Config, slug: str) -> Dict[str, Optional[SeedEntry]]:
    mapping = load_slug_seeds(config)
    slot = mapping.get((slug or "").strip()) or {}
    return {
        "start": get_entry(config, slot.get("start") or ""),
        "end": get_entry(config, slot.get("end") or ""),
    }


def activate_for_slug(config: Config, slug: str) -> str:
    """Перед съёмкой slug — активировать привязанные start/end."""
    bound = seeds_for_slug(config, slug)
    lines: List[str] = []
    start = bound.get("start")
    end = bound.get("end")
    if start is not None:
        ok, msg = activate_seed(config, start.id, role="start")
        lines.append(msg if ok else f"start: {msg}")
    if end is not None:
        ok, msg = activate_seed(config, end.id, role="end")
        lines.append(msg if ok else f"end: {msg}")
    return "\n".join(lines)


def prepare_refine(config: Config, seed_id: str) -> Tuple[bool, str]:
    """Доработка эталона: vision-описание позы + чеклист «натуральное тело».

    Сам пиксельный img2img (HS2→realistic) — следующий шаг: положи доработанный PNG
    через accept_refined, либо прогони кадр в Comfy вручную.
    """
    entry = get_entry(config, seed_id)
    if entry is None:
        return False, f"Нет эталона id={seed_id}"
    path = Path(entry.raw_path) if entry.raw_path else entry.resolve_path()
    if path is None or not path.is_file():
        return False, "Нет файла для доработки."

    entry.status = "refining"
    upsert_entry(config, entry)

    en_pose = ""
    ru = ""
    vision_note = ""
    try:
        from .reference_vision import describe_reference

        desc = describe_reference(
            config,
            path,
            hint=NATURAL_BODY_HINT,
            save_json=True,
        )
        if desc.vision_ok:
            en_pose = desc.en_pose or ""
            ru = desc.ru or ""
            vision_note = f"Vision: {ru or en_pose}"
        else:
            vision_note = f"Vision недоступен: {(desc.raw or '')[:200]}"
    except Exception as exc:  # noqa: BLE001
        vision_note = f"Vision ошибка: {exc}"

    entry.en_pose = en_pose or entry.en_pose
    entry.notes = (
        f"{NATURAL_BODY_HINT}\n\n"
        f"{vision_note}\n\n"
        "Дальше: доработай кадр (Comfy img2img / внешний инструмент) → "
        "«Принять доработанный» в библиотеке эталонов."
    ).strip()
    entry.status = "needs_refine"
    if "hs2" not in entry.tags:
        entry.tags = list(entry.tags) + ["hs2"]
    upsert_entry(config, entry)
    return True, (
        f"Эталон `{entry.title}` готов к доработке.\n"
        f"{vision_note}\n"
        f"Исходник: {path}\n"
        "После правки: «Принять доработанный…» — станет start для I2V."
    )


def accept_refined(
    config: Config,
    seed_id: str,
    refined_source: Path,
    *,
    activate: bool = False,
) -> Tuple[bool, str]:
    """Заменить эталон доработанным (натуральное тело) PNG."""
    entry = get_entry(config, seed_id)
    if entry is None:
        return False, f"Нет эталона id={seed_id}"
    src = Path(refined_source)
    if not src.is_file() or src.suffix.lower() not in _IMAGE_EXT:
        return False, "Нужен файл PNG/JPG доработанного эталона."

    root = seeds_root(config)
    dest = root / f"{entry.id}_refined{src.suffix.lower()}"
    try:
        shutil.copy2(src, dest)
    except OSError as exc:
        return False, f"Не сохранить: {exc}"

    if not entry.raw_path and entry.path:
        # сохранить оригинал в raw
        try:
            raw_dest = root / "raw" / Path(entry.path).name
            if Path(entry.path).is_file() and not raw_dest.is_file():
                shutil.copy2(entry.path, raw_dest)
                entry.raw_path = str(raw_dest)
        except OSError:
            pass

    entry.refined_path = str(dest)
    entry.path = str(dest)
    entry.status = "ready"
    entry.source = "refined"
    if "natural" not in entry.tags:
        entry.tags = list(entry.tags) + ["natural"]
    upsert_entry(config, entry)
    msg = f"Доработанный эталон принят: {dest.name}"
    if activate:
        ok2, msg2 = activate_seed(config, entry.id)
        msg += "\n" + msg2
        if not ok2:
            return False, msg
    return True, msg


def format_library_brief(config: Config) -> str:
    items = load_library(config)
    if not items:
        return "Библиотека эталонов пуста — импортируй скрин из HS2 / Inbox."
    lines = [f"Эталоны I2V: {len(items)}"]
    for e in items[:12]:
        lines.append(f"  {e.label()}  ({e.status})")
    if len(items) > 12:
        lines.append(f"  … ещё {len(items) - 12}")
    mapping = load_slug_seeds(config)
    if mapping:
        lines.append("Привязки к анимациям:")
        for slug, slot in list(mapping.items())[:8]:
            if slug == "version":
                continue
            s = slot.get("start") or "—"
            e = slot.get("end") or "—"
            lines.append(f"  `{slug}`: start={s[:8]} end={e[:8]}")
    return "\n".join(lines)
