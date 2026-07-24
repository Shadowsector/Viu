"""Оценка и хранение Comfy-клипов: keep/reject, last-frame seed, связи каталога."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from ...config import Config
from .framing import detect_orientation, frame_spec_for_action
from .paths import comfy_refs_dir, comfy_seed_frames_dir, comfy_out_dir

STATUS_CANDIDATE = "candidate"
STATUS_KEPT = "kept"
STATUS_REJECTED = "rejected"

_CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0


def clip_review_path(config: Config) -> Path:
    return config.data_dir / "comfy_clips.json"


def comfy_kept_dir(config: Config) -> Path:
    p = comfy_refs_dir(config) / "kept"
    p.mkdir(parents=True, exist_ok=True)
    return p


def comfy_rejected_dir(config: Config) -> Path:
    p = comfy_refs_dir(config) / "rejected"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _clip_id(batch_id: str, angle: str, path: str) -> str:
    raw = f"{batch_id}|{angle}|{path}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:16]


@dataclass
class ComfyClip:
    id: str
    batch_id: str
    action: str
    angle: str
    angle_label: str
    path: str
    status: str = STATUS_CANDIDATE
    score: int = 0
    notes: str = ""
    orientation: str = "vertical"
    width: int = 0
    height: int = 0
    length: int = 0
    fps: float = 24.0
    seed_frame: str = ""
    catalog_slug: str = ""
    enters_from: List[str] = field(default_factory=list)
    exits_to: List[str] = field(default_factory=list)
    created_at: str = ""
    kept_at: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "ComfyClip":
        return ComfyClip(
            id=str(d.get("id") or ""),
            batch_id=str(d.get("batch_id") or ""),
            action=str(d.get("action") or ""),
            angle=str(d.get("angle") or ""),
            angle_label=str(d.get("angle_label") or ""),
            path=str(d.get("path") or ""),
            status=str(d.get("status") or STATUS_CANDIDATE),
            score=int(d.get("score") or 0),
            notes=str(d.get("notes") or ""),
            orientation=str(d.get("orientation") or "vertical"),
            width=int(d.get("width") or 0),
            height=int(d.get("height") or 0),
            length=int(d.get("length") or 0),
            fps=float(d.get("fps") or 24.0),
            seed_frame=str(d.get("seed_frame") or ""),
            catalog_slug=str(d.get("catalog_slug") or ""),
            enters_from=list(d.get("enters_from") or []),
            exits_to=list(d.get("exits_to") or []),
            created_at=str(d.get("created_at") or ""),
            kept_at=str(d.get("kept_at") or ""),
        )


@dataclass
class ClipChainLink:
    """Связь: из какого клипа/позы → в какую (через seed last-frame)."""

    from_slug: str
    to_slug: str
    via_clip_id: str
    seed_frame: str
    created_at: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "ClipChainLink":
        return ClipChainLink(
            from_slug=str(d.get("from_slug") or ""),
            to_slug=str(d.get("to_slug") or ""),
            via_clip_id=str(d.get("via_clip_id") or ""),
            seed_frame=str(d.get("seed_frame") or ""),
            created_at=str(d.get("created_at") or ""),
        )


class ComfyClipStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.clips: List[ComfyClip] = []
        self.chains: List[ClipChainLink] = []

    def load(self) -> "ComfyClipStore":
        if not self.path.is_file():
            return self
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return self
        self.clips = [ComfyClip.from_dict(x) for x in (data.get("clips") or []) if isinstance(x, dict)]
        self.chains = [
            ClipChainLink.from_dict(x) for x in (data.get("chains") or []) if isinstance(x, dict)
        ]
        return self

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": 1,
            "comment": "Comfy MoCap clips: candidate/kept/rejected + last-frame chains",
            "clips": [c.to_dict() for c in self.clips],
            "chains": [c.to_dict() for c in self.chains],
        }
        self.path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    def get(self, clip_id: str) -> Optional[ComfyClip]:
        for c in self.clips:
            if c.id == clip_id:
                return c
        return None

    def by_batch(self, batch_id: str) -> List[ComfyClip]:
        return [c for c in self.clips if c.batch_id == batch_id]

    def pending_candidates(self) -> List[ComfyClip]:
        return [c for c in self.clips if c.status == STATUS_CANDIDATE]

    def kept(self) -> List[ComfyClip]:
        return [c for c in self.clips if c.status == STATUS_KEPT]


def register_triple_batch(
    config: Config,
    *,
    action: str,
    results: Dict[str, Any],
    catalog_slug: str = "",
    enters_from: Optional[List[str]] = None,
    exits_to: Optional[List[str]] = None,
) -> List[ComfyClip]:
    """Зарегистрировать 3 дубля после генерации."""
    store = ComfyClipStore(clip_review_path(config)).load()
    batch_id = str(results.get("slug") or f"batch_{int(time.time())}")
    spec = frame_spec_for_action(action)
    stamp = time.strftime("%Y-%m-%dT%H:%M:%S")
    created: List[ComfyClip] = []
    angles = results.get("angles") or {}
    slug = (catalog_slug or "").strip()
    for angle_id, info in angles.items():
        if not isinstance(info, dict):
            continue
        files = list(info.get("files") or [])
        if not files:
            continue
        path = str(files[0])
        v_note = str(info.get("vision_verdict") or "").strip()
        clip = ComfyClip(
            id=_clip_id(batch_id, str(angle_id), path),
            batch_id=batch_id,
            action=str(info.get("action_variant") or action),
            angle=str(angle_id),
            angle_label=str(info.get("label") or angle_id),
            path=path,
            status=STATUS_CANDIDATE,
            notes=f"vision:{v_note}" if v_note else "",
            orientation=spec.orientation,
            width=spec.width,
            height=spec.height,
            length=spec.length,
            fps=spec.fps,
            created_at=stamp,
            catalog_slug=slug,
            enters_from=list(enters_from or []),
            exits_to=list(exits_to or []),
        )
        # заменить если тот же id
        store.clips = [c for c in store.clips if c.id != clip.id]
        store.clips.append(clip)
        created.append(clip)
    store.save()
    return created


def extract_last_frame(video: Path, dest: Path) -> Tuple[bool, str]:
    """Последний кадр mp4 → PNG (ffmpeg / imageio / cv2)."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    if not video.is_file():
        return False, f"нет файла: {video}"

    # 1) ffmpeg
    for bin_name in ("ffmpeg", "ffmpeg.exe"):
        try:
            proc = subprocess.run(  # noqa: S603
                [
                    bin_name,
                    "-y",
                    "-sseof",
                    "-0.05",
                    "-i",
                    str(video),
                    "-frames:v",
                    "1",
                    str(dest),
                ],
                capture_output=True,
                text=True,
                timeout=120,
                creationflags=_CREATE_NO_WINDOW,
            )
            if proc.returncode == 0 and dest.is_file() and dest.stat().st_size > 0:
                return True, str(dest)
        except (OSError, subprocess.TimeoutExpired, FileNotFoundError):
            continue

    # 2) imageio
    try:
        import imageio.v3 as iio  # type: ignore

        frames = iio.imread(video)
        if getattr(frames, "ndim", 0) >= 3:
            last = frames[-1] if frames.ndim == 4 else frames
            iio.imwrite(dest, last)
            if dest.is_file():
                return True, str(dest)
    except Exception:
        pass

    # 3) cv2
    try:
        import cv2  # type: ignore

        cap = cv2.VideoCapture(str(video))
        if not cap.isOpened():
            return False, "cv2 не открыл видео"
        last = None
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            last = frame
        cap.release()
        if last is None:
            return False, "пустое видео"
        ok = cv2.imwrite(str(dest), last)
        if ok and dest.is_file():
            return True, str(dest)
    except Exception as exc:
        return False, f"last-frame: {exc}"

    return False, "нужен ffmpeg в PATH (или imageio/cv2) для last-frame"


def _slugify(text: str) -> str:
    s = re.sub(r"[^a-z0-9_\-]+", "_", (text or "").lower().strip())
    s = re.sub(r"_+", "_", s).strip("_")
    return (s or "clip")[:48]


# EN-action / ошибочные имена файлов → канонический slug каталога
_CATALOG_SLUG_ALIASES = {
    "idle_stand": "idle",
    "idle_standing": "idle",
    "standing_idle": "idle",
    "breathing_idle": "idle",
}


def normalize_catalog_slug(slug: str) -> str:
    """idle_stand_* / slugify(EN action) → idle; иначе slugify."""
    s = _slugify(slug)
    if s in _CATALOG_SLUG_ALIASES:
        return _CATALOG_SLUG_ALIASES[s]
    if s.startswith("idle_stand"):
        return "idle"
    return s


def keep_clip(
    config: Config,
    clip_id: str,
    *,
    score: int = 4,
    notes: str = "",
    catalog_slug: str = "",
    enters_from: Optional[List[str]] = None,
    exits_to: Optional[List[str]] = None,
    reject_siblings: bool = True,
) -> Tuple[bool, str, Optional[ComfyClip]]:
    """Оставить лучший клип: kept/, last-frame seed, связи каталога."""
    store = ComfyClipStore(clip_review_path(config)).load()
    clip = store.get(clip_id)
    if clip is None:
        return False, f"клип {clip_id} не найден", None

    src = Path(clip.path)
    if not src.is_file():
        return False, f"файл пропал: {src}", None

    slug = normalize_catalog_slug(catalog_slug or clip.catalog_slug or clip.action)
    # если передали короткий catalog_slug (sit_idle) — не перетирать длинным action
    if catalog_slug.strip():
        slug = normalize_catalog_slug(catalog_slug)
    elif clip.catalog_slug.strip():
        slug = normalize_catalog_slug(clip.catalog_slug)
    ef = enters_from if enters_from is not None else list(clip.enters_from)
    from .naming import display_video_stem, next_kept_seq

    kept_stem = display_video_stem(
        catalog_slug=slug,
        enters_from=ef or clip.enters_from,
        looped="idle" in slug or slug.endswith("_idle"),
        seq=next_kept_seq(config, slug),
    )
    kept_name = f"{kept_stem}.mp4"
    kept_path = comfy_kept_dir(config) / kept_name
    # дубликат в ComfyOut для удобного просмотра
    from .paths import comfy_out_dir

    try:
        shutil.copy2(src, comfy_out_dir(config) / kept_name)
    except OSError:
        pass
    try:
        shutil.copy2(src, kept_path)
    except OSError as exc:
        return False, f"не скопировать в kept: {exc}", None

    seed_name = f"{slug}_{clip.angle}_last.png"
    seed_path = comfy_seed_frames_dir(config) / seed_name
    ok_f, frame_msg = extract_last_frame(src, seed_path)

    clip.status = STATUS_KEPT
    clip.score = max(1, min(5, int(score or 4)))
    clip.notes = (notes or "").strip()
    clip.catalog_slug = slug
    et = exits_to if exits_to is not None else list(clip.exits_to)
    clip.enters_from = [_slugify(x) for x in ef if str(x).strip()]
    clip.exits_to = [_slugify(x) for x in et if str(x).strip()]
    clip.path = str(kept_path)
    clip.seed_frame = str(seed_path) if ok_f else ""
    clip.kept_at = time.strftime("%Y-%m-%dT%H:%M:%S")

    if reject_siblings:
        for sib in store.by_batch(clip.batch_id):
            if sib.id == clip.id or sib.status != STATUS_CANDIDATE:
                continue
            _reject_one(config, store, sib)

    # chain links: каждый enters_from → this; this → каждый exits_to
    stamp = clip.kept_at
    for src_slug in clip.enters_from:
        store.chains.append(
            ClipChainLink(
                from_slug=src_slug,
                to_slug=slug,
                via_clip_id=clip.id,
                seed_frame=clip.seed_frame,
                created_at=stamp,
            )
        )
    for dst in clip.exits_to:
        store.chains.append(
            ClipChainLink(
                from_slug=slug,
                to_slug=dst,
                via_clip_id=clip.id,
                seed_frame=clip.seed_frame,
                created_at=stamp,
            )
        )

    store.save()
    _sync_catalog_wish(config, clip)

    pause_msg = None
    try:
        from .scene_choice import on_action_quota_reached

        pause_msg = on_action_quota_reached(config, slug, title_ru=slug.replace("_", " "))
    except Exception:
        pass

    lines = [
        f"Оставила «{clip.angle_label}» ({clip.angle}) score={clip.score}/5",
        f"kept: {kept_path}",
    ]
    if ok_f:
        lines.append(f"seed (last frame): {seed_path}")
    else:
        lines.append(f"seed: не извлекла — {frame_msg}")
    if clip.enters_from or clip.exits_to:
        lines.append(
            f"граф: enters_from={clip.enters_from or '—'} → `{slug}` → exits_to={clip.exits_to or '—'}"
        )
    if pause_msg:
        lines.append(pause_msg)
    return True, "\n".join(lines), clip


def _reject_one(config: Config, store: ComfyClipStore, clip: ComfyClip) -> None:
    src = Path(clip.path)
    if src.is_file():
        dest = comfy_rejected_dir(config) / src.name
        try:
            if not dest.exists():
                shutil.move(str(src), str(dest))
            clip.path = str(dest)
        except OSError:
            try:
                shutil.copy2(src, dest)
                clip.path = str(dest)
            except OSError:
                pass
    clip.status = STATUS_REJECTED


def reject_clip(config: Config, clip_id: str) -> Tuple[bool, str]:
    store = ComfyClipStore(clip_review_path(config)).load()
    clip = store.get(clip_id)
    if clip is None:
        return False, f"клип {clip_id} не найден"
    _reject_one(config, store, clip)
    store.save()
    return True, f"Отклонила {clip.angle_label}: {clip.path}"


def reject_batch(config: Config, batch_id: str) -> Tuple[bool, str]:
    store = ComfyClipStore(clip_review_path(config)).load()
    n = 0
    for clip in store.by_batch(batch_id):
        if clip.status == STATUS_CANDIDATE:
            _reject_one(config, store, clip)
            n += 1
    store.save()
    return True, f"Отклонила {n} кандидат(ов) batch={batch_id}"


PICK_ANGLE_ALIASES: Dict[str, str] = {
    "сбоку": "side",
    "side": "side",
    "три": "three_quarter",
    "3/4": "three_quarter",
    "¾": "three_quarter",
    "three_quarter": "three_quarter",
    "quarter": "three_quarter",
    "анфас": "front",
    "front": "front",
    "фронт": "front",
    "a": "take_a",
    "b": "take_b",
    "c": "take_c",
    "take_a": "take_a",
    "take_b": "take_b",
    "take_c": "take_c",
    "take_d": "take_d",
    "take_e": "take_e",
    "d": "take_d",
    "e": "take_e",
    "дубль_a": "take_a",
    "дубль_b": "take_b",
    "дубль_c": "take_c",
}


def normalize_pick_angle(angle: str) -> str:
    return PICK_ANGLE_ALIASES.get((angle or "").strip().lower(), (angle or "").strip().lower())


def keep_best_by_angle(
    config: Config,
    batch_id: str,
    angle: str,
    *,
    score: int = 4,
    notes: str = "",
    catalog_slug: str = "",
    enters_from: Optional[List[str]] = None,
    exits_to: Optional[List[str]] = None,
) -> Tuple[bool, str, Optional[ComfyClip]]:
    store = ComfyClipStore(clip_review_path(config)).load()
    angle_id = normalize_pick_angle(angle)
    for clip in store.by_batch(batch_id):
        if clip.angle == angle_id and clip.status == STATUS_CANDIDATE:
            return keep_clip(
                config,
                clip.id,
                score=score,
                notes=notes,
                catalog_slug=catalog_slug,
                enters_from=enters_from,
                exits_to=exits_to,
                reject_siblings=True,
            )
    return False, f"в batch {batch_id} нет кандидата angle={angle_id}", None


# Порядок для away / авто-выбора: take_b часто срезает vision — тогда a или c.
MOCAP_TAKE_PICK_ORDER: tuple[str, ...] = ("take_b", "take_a", "take_c", "take_d", "take_e")


def keep_best_preferred_take(
    config: Config,
    batch_id: str,
    *,
    score: int = 4,
    notes: str = "",
    catalog_slug: str = "",
    enters_from: Optional[List[str]] = None,
    exits_to: Optional[List[str]] = None,
    prefer: Optional[Sequence[str]] = None,
) -> Tuple[bool, str, Optional[ComfyClip]]:
    """Выбрать лучший доступный дубль (не только take_b)."""
    order = tuple(prefer or MOCAP_TAKE_PICK_ORDER)
    tried: list[str] = []
    for angle_id in order:
        ok, msg, clip = keep_best_by_angle(
            config,
            batch_id,
            angle_id,
            score=score,
            notes=notes,
            catalog_slug=catalog_slug,
            enters_from=enters_from,
            exits_to=exits_to,
        )
        if ok and clip is not None:
            if angle_id != order[0]:
                msg = f"{msg} (fallback: {angle_id}, нет {order[0]})"
            return True, msg, clip
        tried.append(angle_id)
    store = ComfyClipStore(clip_review_path(config)).load()
    have = [c.angle for c in store.by_batch(batch_id) if c.status == STATUS_CANDIDATE]
    return (
        False,
        f"в batch {batch_id} нет кандидатов для {tried}; есть: {have or '—'}",
        None,
    )


def keep_best_take(
    config: Config,
    batch_id: str,
    angle: str,
    *,
    score: int = 4,
    notes: str = "",
    catalog_slug: str = "",
    enters_from: Optional[List[str]] = None,
    exits_to: Optional[List[str]] = None,
) -> Tuple[bool, str, Optional[ComfyClip]]:
    """Выбор дубля: сначала запрошенный take, иначе fallback по MOCAP_TAKE_PICK_ORDER."""
    angle_id = normalize_pick_angle(angle)
    prefer: tuple[str, ...] = (angle_id,) + tuple(
        x for x in MOCAP_TAKE_PICK_ORDER if x != angle_id
    )
    return keep_best_preferred_take(
        config,
        batch_id,
        score=score,
        notes=notes,
        catalog_slug=catalog_slug,
        enters_from=enters_from,
        exits_to=exits_to,
        prefer=prefer,
    )


def _parse_clip_pick_line(raw: str) -> Optional[Tuple[str, Dict[str, Any]]]:
    low = raw.lower()
    if low in ("отклонить все", "reject all", "все плохо", "заново"):
        return "reject_all", {}
    m = re.match(
        r"^(?:лучший|best|keep|оставить)\s*[:\-]?\s*(\S+)(?:\s+(\d))?(?:\s+(.+))?$",
        raw,
        re.I,
    )
    if not m:
        return None
    angle = m.group(1)
    score = int(m.group(2) or 4)
    notes = (m.group(3) or "").strip()
    return "keep", {"angle": angle, "score": score, "notes": notes}


def parse_clip_pick_reply(text: str) -> Optional[Tuple[str, Dict[str, Any]]]:
    """Telegram/чат: 'лучший: take_b', 'лучший: a 5', 'отклонить все', несколько через |."""
    raw = (text or "").strip()
    if not raw:
        return None
    parts = [p.strip() for p in raw.split("|") if p.strip()]
    for part in parts:
        parsed = _parse_clip_pick_line(part)
        if parsed is not None:
            return parsed
    return None


def _sync_catalog_wish(config: Config, clip: ComfyClip) -> None:
    """Записать ref_video / seed / enters_from / exits_to в animation_catalog."""
    try:
        from ...animation_catalog import AnimationCatalogStore, animation_catalog_path
        from ...animation_catalog.models import AnimationWish, STATUS_WISHED
    except Exception:
        return
    store = AnimationCatalogStore(animation_catalog_path(config)).load()
    slug = normalize_catalog_slug(clip.catalog_slug or clip.action)
    wish = store.get_by_slug(slug)
    if wish is None:
        wish = AnimationWish(
            slug=slug,
            category="rest" if slug in ("idle", "sit_idle", "sleep_idle") else "special",
            title_ru=slug.replace("_", " "),
            when_used="Comfy MoCap reference",
            looks_like=clip.action,
            purpose="Видео-референс для Cascadeur MoCap",
            status=STATUS_WISHED,
            notes="auto from comfy clip keep",
        )
    wish.ref_video = clip.path
    wish.seed_frame = clip.seed_frame
    if clip.enters_from:
        wish.enters_from = list(clip.enters_from)
    if clip.exits_to:
        wish.exits_to = list(clip.exits_to)
    wish.comfy_score = clip.score
    # ref закрывает дыру для режиссёра (missing() смотрит на ref_video)
    extra = f"ref={Path(clip.path).name}; seed={Path(clip.seed_frame).name if clip.seed_frame else '—'}"
    if extra not in (wish.notes or ""):
        wish.notes = ((wish.notes or "") + f"\n{extra}").strip()
    store.upsert(wish)
    store.save()


def format_candidates_message(clips: List[ComfyClip]) -> str:
    if not clips:
        return "Нет кандидатов на оценку."
    batch = clips[0].batch_id
    angles = sorted({c.angle for c in clips})

    from .angles import mocap_take_count

    expected = mocap_take_count()
    lines = [
        f"Выбери лучший дубль ¾ (batch `{batch}`):",
        f"В batch сейчас: {', '.join(angles)} ({len(clips)}/{expected} дублей).",
        "Файлы: Lab/ComfyOut + Lab/Refs (не только ComfyUI/output).",
        "Дома: окно «Выбрать лучший клип» (ComfyUI) или чат/Telegram:",
        "`лучший: take_b` / `лучший: a` / `лучший: c 5` / `отклонить все`",
    ]
    if len(clips) < expected:
        lines.append(
            "⚠ Не все дубли дошли (vision/FAIL) — away возьмёт лучший из тех, что есть."
        )
    lines.append("")
    for c in clips:
        extra = f" [{c.notes}]" if c.notes else ""
        lines.append(f"  • {c.angle} ({c.angle_label}): {Path(c.path).name}{extra}")
    return "\n".join(lines)


def harvest_comfy_native_output(
    config: Config, *, limit: int = 40
) -> Tuple[int, str]:
    """Скопировать свежие mp4 из U:\\Viu\\ComfyUI\\output\\ → Lab/Refs.

    Native Comfy всегда пишет туда; без копирования оценка клипов «пустая».
    """
    from .paths import resolve_comfy_root

    root = resolve_comfy_root(config)
    if root is None:
        return 0, "ComfyUI root не найден — нечего собирать."
    src_dir = root / "output"
    if not src_dir.is_dir():
        return 0, f"Нет папки {src_dir}"
    refs = comfy_refs_dir(config)
    out_dir = comfy_out_dir(config)
    mp4s = sorted(
        src_dir.rglob("*.mp4"),
        key=lambda p: p.stat().st_mtime if p.is_file() else 0,
        reverse=True,
    )[:limit]
    n = 0
    lines = [f"Сбор из {src_dir} → ComfyOut + Refs:"]
    for src in mp4s:
        dest_ref = refs / src.name
        dest_out = out_dir / src.name
        if dest_ref.is_file() and dest_ref.stat().st_size == src.stat().st_size:
            if dest_out.is_file():
                continue
        try:
            shutil.copy2(src, dest_out)
            shutil.copy2(src, dest_ref)
            n += 1
            lines.append(f"  + {src.name}")
        except OSError as exc:
            lines.append(f"  ✗ {src.name}: {exc}")
    if n == 0:
        lines.append("  (новых нет — уже в Refs или output пуст)")
    return n, "\n".join(lines)
