"""Сочинение + самоулучшение Вью — жизнь и игра, без раздувания reflect-голоса.

Слои:
  · `.viu/self_compose.json` — зёрна, черновики, уроки improve
  · digest в reflect/heartbeat (коротко) рядом с event_memory
  · ночь в quiet hours — тихое зерно (без Telegram)
  · чат: «сочини квест», «что думала ночью», «в канон»

Гайды живут здесь как константы — НЕ в REFLECT_VOICE (иначе снова цензор/мета).
"""

from __future__ import annotations

import json
import re
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, List, Optional, Sequence, Tuple

from .config import Config

_STORE_NAME = "self_compose.json"
_REV = 1
_MAX_GRAINS = 40
_MAX_IMPROVE = 30
_MAX_NOTES = 40

# --- Гайд квеста (Анабарра) — для кода / Дена, не целиком в system ---
QUEST_PRINCIPLES = (
    "Одна ясная цель на шаг; разные локации; маленький выбор и последствие; "
    "квест раскрывает характер или мир; побочные можно пропустить."
)

QUEST_STRUCTURE = ("Learn", "Explore", "Act", "Aftermath")

QUEST_CHECKLIST = (
    "личная ставка",
    "выбор",
    "след после",
    "4–6 коротких сцен",
    "по-Анабаррски (тепло, странно, характеры)",
)

# --- Цикл самоулучшения ---
IMPROVE_STEPS = (
    "цель / чья ставка / что почувствует Ден",
    "что есть сейчас и что слабо",
    "дыры: контент · постановка · инструменты",
    "одно решение: в рамках / слегка изменить / предложить добавить",
    "одна фраза: сработало · не хватило · улучшить",
)

_CAST = (
    ("ру", "Ру"),
    ("оля", "Оля"),
    ("оли", "Оля"),
    ("лили", "Лили"),
    ("шаня", "Шаня"),
    ("шаньк", "Шаня"),
    ("вью", "Вью"),
    ("хозяин", "Ден"),
    ("ден", "Ден"),
)

_COMPOSE_RE = re.compile(
    r"(?i)(?:"
    r"сочини\s+(?:квест|истори\w*|приключ\w*)|"
    r"придумай\s+(?:квест|истори\w*|приключ\w*|сцен\w*)|"
    r"давай\s+(?:квест|истори\w*)|"
    r"ночной?\s+(?:сюжет|квест|истори)|"
    r"что\s+(?:думала|снилось|придумала)\s*(?:ночь\w*)?|"
    r"какие\s+(?:зёрна|зерна|ночи?ые\s+мысли)|"
    r"проверь\s+сцен\w*|улучши\s+(?:сцен\w*|квест)|"
    r"в\s+канон|в\s+квесты|зафиксируй\s+квест"
    r")"
)

_PRAISE_RE = re.compile(
    r"(?i)^\s*(?:"
    r"хорошо|отлично|молодец|правильно|так\s+и\s+надо|закрепи|"
    r"в\s+канон|оставь\s+так|норм(?:ально)?"
    r")\s*[.!]?\s*$"
)


@dataclass
class Grain:
    """Короткое зерно — можно вплести в разговор или в квест."""

    id: str
    context: str  # life | game
    title: str
    hook: str  # одна фраза для чата
    body: str  # шаблон / синопсис
    improve: str = ""
    used: bool = False
    source: str = "chat"  # chat | night | den
    ts: float = 0.0
    tags: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Grain":
        return cls(
            id=str(d.get("id") or uuid.uuid4().hex[:10]),
            context=str(d.get("context") or "life"),
            title=str(d.get("title") or "").strip() or "зерно",
            hook=str(d.get("hook") or "").strip(),
            body=str(d.get("body") or "").strip(),
            improve=str(d.get("improve") or "").strip(),
            used=bool(d.get("used")),
            source=str(d.get("source") or "chat"),
            ts=float(d.get("ts") or 0),
            tags=[str(t) for t in (d.get("tags") or []) if str(t).strip()],
        )


@dataclass
class ComposeDraft:
    wish: str = ""
    context: str = "game"
    title: str = ""
    body: str = ""
    improve: str = ""
    grain_id: str = ""
    ts: float = 0.0

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "ComposeDraft":
        return cls(
            wish=str(d.get("wish") or ""),
            context=str(d.get("context") or "game"),
            title=str(d.get("title") or ""),
            body=str(d.get("body") or ""),
            improve=str(d.get("improve") or ""),
            grain_id=str(d.get("grain_id") or ""),
            ts=float(d.get("ts") or 0),
        )


def store_path(config: Config) -> Path:
    return Path(config.data_dir) / _STORE_NAME


def _new_id() -> str:
    return uuid.uuid4().hex[:10]


def load_store(config: Config) -> dict:
    path = store_path(config)
    if not path.is_file():
        data = {
            "rev": _REV,
            "grains": [],
            "improve_notes": [],
            "draft": None,
            "night_last_day": "",
            "notes": [],
        }
        save_store(config, data)
        return data
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {
            "rev": _REV,
            "grains": [],
            "improve_notes": [],
            "draft": None,
            "night_last_day": "",
            "notes": [],
        }
    if not isinstance(raw, dict):
        return {
            "rev": _REV,
            "grains": [],
            "improve_notes": [],
            "draft": None,
            "night_last_day": "",
            "notes": [],
        }
    raw.setdefault("grains", [])
    raw.setdefault("improve_notes", [])
    raw.setdefault("draft", None)
    raw.setdefault("night_last_day", "")
    raw.setdefault("notes", [])
    return raw


def save_store(config: Config, data: dict) -> None:
    config.ensure_dirs()
    path = store_path(config)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    tmp.replace(path)


def gather_memory_bits(config: Config, *, limit: int = 6) -> List[str]:
    """Агрегат из event_memory + story_memory + VIU_MEMORY — сырьё для сочинения."""
    bits: List[str] = []
    try:
        from .event_memory import get_event_memory

        for ev in get_event_memory(config).recent(limit):
            line = f"{ev.title}: {ev.what}".strip()
            if line:
                bits.append(line[:180])
    except Exception:  # noqa: BLE001
        pass
    try:
        from .story_memory import get_story_memory

        for beat in get_story_memory(config).recent(limit):
            t = (beat.text or "").strip().replace("\n", " ")
            if len(t) >= 20:
                bits.append(f"{beat.role}: {t[:140]}")
    except Exception:  # noqa: BLE001
        pass
    try:
        from .viu_memory import format_reflect_block

        mem = format_reflect_block(config, max_chars=400)
        if mem:
            bits.append(mem[:300])
    except Exception:  # noqa: BLE001
        pass
    # уникальные по префиксу
    out: List[str] = []
    seen = set()
    for b in bits:
        key = b[:48].lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(b)
        if len(out) >= limit:
            break
    return out


def _guess_who(text: str) -> str:
    low = (text or "").lower()
    for needle, name in _CAST:
        if needle in low:
            return name
    return "девочки дома"


def _guess_context(text: str) -> str:
    low = (text or "").lower()
    if re.search(r"(?i)квест|анабарр|локац|биом|defeated|ру\b|оля|лили|шаня", low):
        return "game"
    if re.search(r"(?i)жизн|ночь|снил|приключ|с\s+ден|про\s+нас|личн", low):
        return "life"
    if "квест" in low:
        return "game"
    return "life"


def _pick_seed(bits: Sequence[str], wish: str) -> str:
    if wish and len(wish.strip()) >= 8:
        return wish.strip()[:200]
    if bits:
        return bits[0][:160]
    return "дом на опушке и странный гость"


def compose_quest_body(
    *,
    wish: str,
    who: str,
    seed: str,
    locations: Optional[Sequence[str]] = None,
) -> Tuple[str, str]:
    """Шаблон короткого квеста + название."""
    locs = list(locations or ["дом", "опушка", "рынок"])
    title = f"{who}: {wish.strip()[:40]}" if wish.strip() else f"Дело для {who}"
    if len(title) < 8:
        title = f"Странное у {who}"
    body = (
        f"Название: {title}\n"
        f"Чья проблема: {who}\n"
        f"Цель: разобраться с «{seed[:80]}» и оставить след дома\n"
        f"Локации: {', '.join(locs[:3])}\n"
        f"Помеха: нехватка времени/материалов или чужая ложь\n"
        f"Выбор: помочь прямо / хитростью / отложить (побочный)\n"
        f"Чем заканчивается: новый факт или гость; дом чуть лучше/страннее\n"
        f"NSFW-риск: только если из характера (Шаня — смело для Хозяина)\n"
        f"Структура: Learn → Explore → Act → Aftermath\n"
        f"Принцип: {QUEST_PRINCIPLES}"
    )
    return title[:80], body


def compose_life_body(*, wish: str, seed: str) -> Tuple[str, str]:
    title = (wish.strip()[:50] if wish.strip() else "Ночная мысль") or "Ночная мысль"
    hook_src = wish.strip() or seed
    body = (
        f"Контекст: жизнь Вью с Деном\n"
        f"Зерно: {hook_src[:160]}\n"
        f"Learn: что зацепило / чего не хватает\n"
        f"Explore: воспоминание или фантазия из памяти чата\n"
        f"Act: что она может сказать или предложить Дену\n"
        f"Aftermath: новый факт между ними (не королевство — дом и двое)\n"
        f"Чувство Дена: тепло / интерес / возбуждение — одно"
    )
    return title[:80], body


def run_improve_pass(
    *,
    context: str,
    title: str,
    body: str,
    memory_bits: Optional[Sequence[str]] = None,
) -> str:
    """Короткий цикл самоулучшения → 4 строки."""
    low = (body or "").lower()
    gaps: List[str] = []
    if "выбор" not in low and "a/b" not in low:
        gaps.append("выбор")
    if context == "game" and "локац" not in low:
        gaps.append("вторая локация")
    if "nsfw" in low and "характер" not in low:
        gaps.append("NSFW из характера, не ради секса")
    if not memory_bits:
        gaps.append("опора на память чата/событий")
    # постановка / инструменты — мягко
    if context == "game" and not re.search(r"(?i)дом|опушк|рынок|пещер|река", low):
        gaps.append("постановка: место/проп")
    if context == "life" and len((body or "").split()) < 20:
        gaps.append("контент: реакция и последствие")

    weak = ", ".join(gaps[:3]) if gaps else "пока ок, можно углубить ставку"
    propose: str
    if "выбор" in gaps:
        propose = "текст: добавить маленький выбор A/B с разным следом"
    elif "постановка" in " ".join(gaps):
        propose = "мир: уточнить место/проп (пенёк, окно, кровать)"
    elif "память" in weak:
        propose = "текст: опереться на недавнее событие из памяти"
    elif context == "game":
        propose = "в рамках имеющегося: один шаг Learn→Act без новых систем"
    else:
        propose = "в разговоре: одна фраза-намёк, не синопсис"

    feel = "тепло и интерес" if context == "life" else "напряжение + забота о доме"
    return (
        f"Цель: {title[:60]} · ставка на характер · Ден почувствует: {feel}\n"
        f"Сейчас слабо из-за: {weak}\n"
        f"Не хватает: {gaps[0] if gaps else 'мелочи для вкуса'}\n"
        f"Предлагаю: {propose}"
    )


def _hook_from(title: str, body: str, context: str) -> str:
    if context == "life":
        return f"Думала ночью: {title.rstrip('.')}.…"
    # первая содержательная строка цели
    m = re.search(r"(?im)^Цель:\s*(.+)$", body or "")
    if m:
        return f"Квест в голове: {m.group(1).strip()[:100]}"
    return f"Квест в голове: {title}"


def add_grain(
    config: Config,
    *,
    context: str,
    title: str,
    body: str,
    improve: str = "",
    source: str = "chat",
    tags: Optional[Sequence[str]] = None,
    also_event: bool = True,
) -> Grain:
    data = load_store(config)
    grain = Grain(
        id=_new_id(),
        context=context if context in ("life", "game") else "life",
        title=title[:80],
        hook=_hook_from(title, body, context)[:160],
        body=body[:2000],
        improve=(improve or "")[:600],
        used=False,
        source=source,
        ts=time.time(),
        tags=[str(t) for t in (tags or [])],
    )
    grains = list(data.get("grains") or [])
    grains.append(grain.to_dict())
    data["grains"] = grains[-_MAX_GRAINS:]
    if improve:
        notes = list(data.get("improve_notes") or [])
        notes.append(
            {
                "id": _new_id(),
                "grain_id": grain.id,
                "text": improve[:600],
                "context": grain.context,
                "created": time.time(),
            }
        )
        data["improve_notes"] = notes[-_MAX_IMPROVE:]
    data["draft"] = ComposeDraft(
        wish=title,
        context=grain.context,
        title=grain.title,
        body=grain.body,
        improve=grain.improve,
        grain_id=grain.id,
        ts=time.time(),
    ).to_dict()
    save_store(config, data)

    if also_event:
        try:
            from .event_memory import get_event_memory

            get_event_memory(config).add(
                title=f"{'Ночь' if source == 'night' else 'Сочинение'}: {grain.title}"[:80],
                what=grain.hook + " — " + (grain.body.splitlines()[0] if grain.body else ""),
                who="Вью",
                tags=["compose", grain.context, source],
                source="compose",
            )
        except Exception:  # noqa: BLE001
            pass
    return grain


def mark_grain_used(config: Config, grain_id: str) -> None:
    data = load_store(config)
    changed = False
    for g in data.get("grains") or []:
        if str(g.get("id")) == grain_id:
            g["used"] = True
            changed = True
            break
    if changed:
        save_store(config, data)


def unused_grains(config: Config, *, limit: int = 5) -> List[Grain]:
    data = load_store(config)
    out: List[Grain] = []
    for raw in reversed(data.get("grains") or []):
        g = Grain.from_dict(raw)
        if not g.used:
            out.append(g)
        if len(out) >= limit:
            break
    return list(reversed(out))


def format_compose_digest(config: Config, *, max_chars: int = 700) -> str:
    """Короткий блок для reflect/heartbeat — факты, без запретов и мета-лекций."""
    grains = unused_grains(config, limit=4)
    data = load_store(config)
    notes = list(data.get("improve_notes") or [])[-2:]
    if not grains and not notes:
        return ""
    lines = [
        "--- Зёрна Вью (можно тихо вплести в разговор; не зачитывать списком) ---"
    ]
    for g in grains:
        tag = "игра" if g.context == "game" else "жизнь"
        lines.append(f"· [{tag}] {g.hook}")
    if notes:
        last = str(notes[-1].get("text") or "").splitlines()
        if last:
            lines.append("Последнее улучшение: " + last[-1][:120])
    text = "\n".join(lines).strip()
    if len(text) > max_chars:
        text = text[:max_chars].rstrip() + "\n…"
    return text


def format_compose_status(config: Config) -> str:
    data = load_store(config)
    grains = [Grain.from_dict(x) for x in (data.get("grains") or [])]
    unused = [g for g in grains if not g.used]
    lines = [
        f"Сочинение: зёрен {len(grains)} (неиспользованных {len(unused)}), "
        f"improve-заметок {len(data.get('improve_notes') or [])}."
    ]
    for g in unused[-5:]:
        lines.append(f"· [{g.context}] {g.title} — {g.hook}")
    if not unused:
        lines.append("Свежих зёрен нет — скажи «сочини квест: …» или подожди ночь.")
    return "\n".join(lines)


def compose_from_wish(
    config: Config,
    wish: str,
    *,
    context: str = "",
    source: str = "chat",
) -> Tuple[Grain, str]:
    """Собрать квест/историю из wish + памяти чатов."""
    bits = gather_memory_bits(config, limit=6)
    ctx = (context or _guess_context(wish)).strip().lower()
    if ctx not in ("life", "game"):
        ctx = "game" if "квест" in (wish or "").lower() else "life"
    who = _guess_who(wish + " " + " ".join(bits[:2]))
    seed = _pick_seed(bits, wish)
    if ctx == "game":
        title, body = compose_quest_body(wish=wish, who=who, seed=seed)
    else:
        title, body = compose_life_body(wish=wish, seed=seed)
    improve = run_improve_pass(
        context=ctx, title=title, body=body, memory_bits=bits
    )
    grain = add_grain(
        config,
        context=ctx,
        title=title,
        body=body,
        improve=improve,
        source=source,
        tags=["wish"] if wish else ["auto"],
    )
    reply = (
        f"Собрала ({'игра' if ctx == 'game' else 'жизнь'}):\n\n"
        f"{body}\n\n"
        f"--- Улучшение ---\n{improve}\n\n"
        "Скажи «хорошо» / «в канон» — закреплю; или поправь одной фразой."
    )
    return grain, reply


def promote_draft_to_quests(config: Config) -> str:
    """Дописать черновик в QUESTS.md и пометить зерно использованным."""
    data = load_store(config)
    raw = data.get("draft")
    if not isinstance(raw, dict):
        return "Нет черновика — сначала «сочини квест: …»."
    draft = ComposeDraft.from_dict(raw)
    if draft.context != "game" and "квест" not in draft.title.lower():
        # life grain — в event уже есть; канон квестов не трогаем
        if draft.grain_id:
            mark_grain_used(config, draft.grain_id)
        return "Это личное зерно — оставила в памяти событий, не в QUESTS."
    try:
        from .plot_canvas import ensure_quests, quests_path

        ensure_quests(config)
        path = quests_path(config)
        block = (
            f"\n### Квест: {draft.title}\n"
            f"**Статус:** черновик\n"
            f"**Связь с канвой:** (сочинение Вью)\n"
            f"**Цель:**\n"
            f"{draft.body}\n"
            f"**Improve:**\n{draft.improve}\n"
        )
        prev = path.read_text(encoding="utf-8") if path.is_file() else ""
        path.write_text(prev.rstrip() + "\n" + block + "\n", encoding="utf-8")
    except Exception as exc:  # noqa: BLE001
        return f"Не смогла дописать QUESTS: {exc}"
    if draft.grain_id:
        mark_grain_used(config, draft.grain_id)
    return f"Вписала в QUESTS.md: «{draft.title}». Можно править в Места → Квесты."


def record_compose_praise(config: Config) -> str:
    data = load_store(config)
    raw = data.get("draft")
    if not isinstance(raw, dict):
        return "Нечего закреплять — сначала сочиним."
    draft = ComposeDraft.from_dict(raw)
    notes = list(data.get("notes") or [])
    notes.append(
        {
            "id": _new_id(),
            "kind": "praise",
            "title": draft.title,
            "context": draft.context,
            "created": time.time(),
        }
    )
    data["notes"] = notes[-_MAX_NOTES:]
    save_store(config, data)
    return "Закрепила зерно — в следующий раз на похожее буду опираться."


def record_compose_note(config: Config, text: str) -> str:
    data = load_store(config)
    notes = list(data.get("notes") or [])
    notes.append(
        {
            "id": _new_id(),
            "kind": "critique",
            "text": (text or "").strip()[:300],
            "created": time.time(),
        }
    )
    data["notes"] = notes[-_MAX_NOTES:]
    # лёгкий improve-урок
    improve = list(data.get("improve_notes") or [])
    improve.append(
        {
            "id": _new_id(),
            "grain_id": "",
            "text": (
                f"Цель: учесть Дена\n"
                f"Сейчас слабо из-за: замечание в чате\n"
                f"Не хватает: правки\n"
                f"Предлагаю: {text.strip()[:160]}"
            ),
            "context": "both",
            "created": time.time(),
        }
    )
    data["improve_notes"] = improve[-_MAX_IMPROVE:]
    save_store(config, data)
    return "Записала замечание к сочинению — учту."


def maybe_night_think(config: Config, *, force: bool = False) -> Optional[Grain]:
    """Тихая ночная мысль в quiet hours — без Telegram, раз в календарную ночь."""
    from .quiet_hours import in_quiet_hours

    if not force and not in_quiet_hours(config):
        return None
    data = load_store(config)
    day_key = datetime.now().strftime("%Y-%m-%d")
    if not force and data.get("night_last_day") == day_key:
        return None
    # чередуем жизнь / игру
    n = len(data.get("grains") or [])
    ctx = "game" if n % 2 == 0 else "life"
    bits = gather_memory_bits(config, limit=5)
    seed = bits[0] if bits else "тихий дом и что-то за окном"
    wish = (
        f"квест из памяти: {seed[:80]}"
        if ctx == "game"
        else f"подумать о нас: {seed[:80]}"
    )
    grain, _reply = compose_from_wish(config, wish, context=ctx, source="night")
    data = load_store(config)
    data["night_last_day"] = day_key
    save_store(config, data)
    return grain


def is_compose_intent(text: str) -> bool:
    return bool(_COMPOSE_RE.search(text or ""))


def looks_like_compose_feedback(text: str) -> bool:
    t = (text or "").strip()
    if not t or len(t) > 280:
        return False
    if _PRAISE_RE.match(t):
        return True
    if re.search(r"(?i)^(?:лучше|убери|добавь|короче|длиннее|больше\s+выбор)", t):
        return True
    return False


def extract_compose_wish(text: str) -> str:
    t = _COMPOSE_RE.sub(" ", text or "")
    t = re.sub(r"(?i)^\s*(?:пожалуйста|плиз|давай|ок)[,:\s]*", "", t)
    return re.sub(r"\s+", " ", t).strip(" .,!—-:")


@dataclass
class ComposeChatOutcome:
    handled: bool
    message: str = ""


def try_handle_compose_chat(config: Config, text: str) -> ComposeChatOutcome:
    """Явные команды сочинения — без LLM, до reflect."""
    raw = (text or "").strip()
    if not raw:
        return ComposeChatOutcome(False)

    data = load_store(config)
    has_draft = isinstance(data.get("draft"), dict)
    draft_age = 0.0
    if has_draft:
        try:
            draft_age = time.time() - float(data["draft"].get("ts") or 0)
        except (TypeError, ValueError, AttributeError):
            draft_age = 1e9

    if re.search(r"(?i)какие\s+(?:зёрна|зерна)|что\s+(?:думала|снилось|придумала)", raw):
        return ComposeChatOutcome(True, format_compose_status(config))

    if has_draft and looks_like_compose_feedback(raw):
        # Голое «хорошо» — только пока черновик свежий (не перехватывать утренний чат).
        if _PRAISE_RE.match(raw.strip()) and draft_age > 3 * 3600:
            if not re.search(r"(?i)в\s+канон|закрепи", raw):
                return ComposeChatOutcome(False)
        if re.search(r"(?i)в\s+канон|в\s+квесты|зафиксируй", raw):
            return ComposeChatOutcome(True, promote_draft_to_quests(config))
        if _PRAISE_RE.match(raw.strip()):
            msg = record_compose_praise(config)
            if re.search(r"(?i)в\s+канон", raw):
                msg += "\n" + promote_draft_to_quests(config)
            return ComposeChatOutcome(True, msg)
        return ComposeChatOutcome(True, record_compose_note(config, raw))

    if re.search(r"(?i)в\s+канон|в\s+квесты|зафиксируй\s+квест", raw) and has_draft:
        return ComposeChatOutcome(True, promote_draft_to_quests(config))

    if re.search(r"(?i)проверь\s+сцен|улучши\s+(?:сцен|квест)", raw):
        draft = data.get("draft")
        if isinstance(draft, dict) and draft.get("body"):
            d = ComposeDraft.from_dict(draft)
            improve = run_improve_pass(
                context=d.context,
                title=d.title,
                body=d.body,
                memory_bits=gather_memory_bits(config),
            )
            d.improve = improve
            data["draft"] = d.to_dict()
            notes = list(data.get("improve_notes") or [])
            notes.append(
                {
                    "id": _new_id(),
                    "grain_id": d.grain_id,
                    "text": improve,
                    "context": d.context,
                    "created": time.time(),
                }
            )
            data["improve_notes"] = notes[-_MAX_IMPROVE:]
            save_store(config, data)
            return ComposeChatOutcome(True, "--- Улучшение ---\n" + improve)
        # нет draft — сочиним из wish
        wish = extract_compose_wish(raw) or "проверить текущую сцену дома"
        _g, reply = compose_from_wish(config, wish, context=_guess_context(raw))
        return ComposeChatOutcome(True, reply)

    if is_compose_intent(raw) and not re.search(
        r"(?i)какие\s+(?:зёрна|зерна)|что\s+(?:думала|снилось)", raw
    ):
        wish = extract_compose_wish(raw)
        if not wish or len(wish) < 3:
            wish = "маленький квест на дом"
        ctx = "game" if re.search(r"(?i)квест", raw) else _guess_context(raw)
        if re.search(r"(?i)истори|приключ|жизн|ноч", raw) and not re.search(
            r"(?i)квест", raw
        ):
            ctx = "life"
        _g, reply = compose_from_wish(config, wish, context=ctx)
        return ComposeChatOutcome(True, reply)

    return ComposeChatOutcome(False)
