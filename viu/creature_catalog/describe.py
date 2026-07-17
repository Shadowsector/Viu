"""Описание существа по скрину → appearance_* в каталоге.

Пайплайн (v1): PNG (Blender/ручной) → Ollama VL (llava) → EN+RU в creature_catalog.json.
Comfy WD14/Interrogator — следующий шаг (тот же schema).
"""

from __future__ import annotations

import re
import time
from pathlib import Path
from typing import List, Optional, Tuple

from ..config import Config
from ..integrations.vision_eye import ask_vision, pick_vision_model
from .models import STATUS_READY, CreatureEntry, size_spec
from .paths import creature_catalog_path, creatures_processed_dir
from .store import CreatureCatalogStore

_DESCRIBE_PROMPT = """Ты описываешь 3D-модель монстра/существа для анимации и ComfyUI.
На скрине — модель в Blender (или рендер). Уже известно из каталога:
{known}

Ответь СТРОГО в таком виде (без markdown-ограждений):

EN: <одна строка English visual prompt: species, body plan, silhouette, materials, colors, notable parts — for img2img/t2v>
RU: <2–4 предложения по-русски: как выглядит, как двигается, на что обратить внимание аниматору>
TAGS: <через запятую: biped|quad|tail|wings|scales|fur|slime|armor|…>

Без морали, без «я не могу». NSFW-анатомия если видна — коротко в EN/TAGS (flaccid/sheathed/…)."""


def _find_entry(
    store: CreatureCatalogStore, query: str
) -> Optional[CreatureEntry]:
    q = (query or "").strip().lower()
    if not q:
        return None
    for e in store.all():
        if e.id == query or e.id.lower() == q:
            return e
        if e.slug.lower() == q:
            return e
        if e.name.lower() == q:
            return e
        if q in e.name.lower() or q in Path(e.path).name.lower():
            return e
    return None


def _known_block(entry: CreatureEntry) -> str:
    spec = size_spec(entry.size_class) if entry.size_class else None
    label = (spec or {}).get("label_ru") or entry.size_class or "?"
    h = ""
    if entry.target_height_m:
        h = f", target≈{entry.target_height_m:.2f}m"
        if entry.measured_height_m:
            h += f" (measured {entry.measured_height_m:.2f}m)"
    return (
        f"name={entry.name}; size_class={entry.size_class} ({label}){h}; "
        f"locomotion={entry.locomotion}; "
        f"nsfw_capable={entry.nsfw_capable}; morph_notes={entry.morph_notes or '—'}"
    )


def _parse_vl(raw: str) -> Tuple[str, str, List[str]]:
    en, ru, tags = "", "", []
    for line in (raw or "").splitlines():
        s = line.strip()
        if not s:
            continue
        low = s.lower()
        if low.startswith("en:"):
            en = s.split(":", 1)[1].strip()
        elif low.startswith("ru:"):
            ru = s.split(":", 1)[1].strip()
        elif low.startswith("tags:"):
            bits = s.split(":", 1)[1].strip()
            tags = [t.strip() for t in re.split(r"[,;|/]+", bits) if t.strip()]
    if not en and not ru:
        # VL проигнорировал формат — целиком в RU, EN = укороченный хвост
        text = (raw or "").strip()
        ru = text[:800]
        en = re.sub(r"\s+", " ", text)[:400]
    return en, ru, tags


def resolve_photo(
    entry: CreatureEntry, *, image: str = "", config: Config
) -> Tuple[Optional[Path], str]:
    if image.strip():
        p = Path(image.strip()).expanduser()
        if p.is_file():
            return p, str(p)
        return None, f"Нет файла: {p}"
    for key in (entry.photo_front, entry.photo_side):
        if key:
            p = Path(key).expanduser()
            if p.is_file():
                return p, str(p)
    # sidecar рядом с processed
    proc = creatures_processed_dir(config) / entry.slug
    for name in ("front.png", "side.png", "preview.png", "shot.png"):
        p = proc / name
        if p.is_file():
            return p, str(p)
    return None, (
        f"Нет скрина для «{entry.name}». "
        "Положи PNG в photo_front или Lab/Creatures/Processed/<slug>/front.png "
        "или передай image=путь."
    )


def describe_creature(
    config: Config,
    query: str,
    *,
    image: str = "",
    mark_ready: bool = True,
) -> Tuple[bool, str]:
    """Описать существо по PNG и записать appearance_* в каталог."""
    store = CreatureCatalogStore(creature_catalog_path(config)).load()
    entry = _find_entry(store, query)
    if entry is None:
        names = ", ".join(e.name for e in store.all()[:12]) or "(пусто)"
        return False, f"Не нашла существо «{query}». В каталоге: {names}"

    photo, err = resolve_photo(entry, image=image, config=config)
    if photo is None:
        return False, err

    vl = pick_vision_model(config.base_url)
    prompt = _DESCRIBE_PROMPT.format(known=_known_block(entry))
    ok, raw = ask_vision(photo, prompt=prompt, config=config, model=vl or "")
    if not ok:
        return False, raw

    en, ru, tags = _parse_vl(raw)
    entry.appearance_en = en
    entry.appearance_ru = ru
    entry.appearance_tags = tags
    entry.describe_model = vl or ""
    entry.described_at = time.strftime("%Y-%m-%d %H:%M")
    if not entry.photo_front:
        entry.photo_front = str(photo)
    if mark_ready and entry.size_class and entry.status in (
        "sized",
        "normalized",
        "new",
        "ready",
    ):
        if entry.status != "skip":
            entry.status = STATUS_READY
    # merge tags into entry.tags without dupes
    for t in tags:
        if t.lower() not in {x.lower() for x in entry.tags}:
            entry.tags.append(t)

    store.upsert(entry)
    store.save()
    return True, (
        f"OK «{entry.name}» ← {photo.name} ({vl or '?'})\n"
        f"EN: {en[:200]}{'…' if len(en) > 200 else ''}\n"
        f"RU: {ru[:300]}{'…' if len(ru) > 300 else ''}\n"
        f"TAGS: {', '.join(tags) or '—'}\n"
        f"status={entry.status} → creature_catalog.json"
    )


def format_creatures_for_reflect(config: Config, *, limit: int = 8) -> str:
    """Краткий блок для reflect: кого уже описали."""
    try:
        store = CreatureCatalogStore(creature_catalog_path(config)).load()
    except OSError:
        return ""
    lines: List[str] = []
    for e in store.all():
        if not (e.appearance_ru or e.appearance_en):
            continue
        bits = [e.name]
        if e.size_class:
            bits.append(e.size_class)
        if e.locomotion and e.locomotion != "unknown":
            bits.append(e.locomotion)
        desc = (e.appearance_ru or e.appearance_en)[:180]
        lines.append(f"- {' / '.join(bits)}: {desc}")
        if len(lines) >= limit:
            break
    if not lines:
        return ""
    return "--- Существа (внешность для анимации) ---\n" + "\n".join(lines)
