"""Уроки Дена по промптам и LoRA — self-improving слой для invent.

Чат: фото/текст → Вью пишет промпт+LoRA → Ден хвалит или правит →
урок в `.viu/comfy_teach_lessons.json`, следующий invent его учитывает.
"""

from __future__ import annotations

import json
import re
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, List, Optional, Sequence

from ...config import Config

_LESSONS_NAME = "comfy_teach_lessons.json"
_DRAFT_NAME = "comfy_teach_draft.json"
_REV = 1

# Встроенные уроки Дена (подмешиваются при первом создании файла).
_SEED_PROMPT_RULES = [
    {
        "when_kinds": ["realism"],
        "ban_positive": ["not anime", "not anime style"],
        "add_negative": ["Anime", "anime style"],
        "add_positive": [],
        "note_ru": "Anime — в Negative, не «not anime» в Positive",
        "score": 5,
        "from": "den-seed",
    }
]
_SEED_LORA_RULES = [
    {
        "when_modes": ["t2i", "i2i"],
        "avoid_name_substrings": ["i2v", "t2v", "video"],
        "prefer_name_substrings": [],
        "avoid_tags": ["i2v", "t2v", "video"],
        "note_ru": "На still PNG не брать i2v/video LoRA",
        "score": 5,
        "from": "den-seed",
    }
]


@dataclass
class TeachDraft:
    """Последний черновик invent — к нему цепляется хвала/ругань."""

    wish: str = ""
    edit_kind: str = ""
    process: str = ""
    positive: str = ""
    negative: str = ""
    show_style: str = "realism"
    shoot_mode: str = "t2i"
    lora_names: List[str] = field(default_factory=list)
    lora_indices: List[int] = field(default_factory=list)
    look_ru: str = ""
    teach_only: bool = False
    ts: float = 0.0

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "TeachDraft":
        return cls(
            wish=str(d.get("wish") or ""),
            edit_kind=str(d.get("edit_kind") or ""),
            process=str(d.get("process") or ""),
            positive=str(d.get("positive") or ""),
            negative=str(d.get("negative") or ""),
            show_style=str(d.get("show_style") or "realism"),
            shoot_mode=str(d.get("shoot_mode") or "t2i"),
            lora_names=[str(x) for x in (d.get("lora_names") or [])],
            lora_indices=[
                int(x)
                for x in (d.get("lora_indices") or [])
                if str(x).isdigit() or isinstance(x, int)
            ],
            look_ru=str(d.get("look_ru") or ""),
            teach_only=bool(d.get("teach_only")),
            ts=float(d.get("ts") or 0),
        )


def lessons_path(config: Config) -> Path:
    return Path(config.data_dir) / _LESSONS_NAME


def draft_path(config: Config) -> Path:
    return Path(config.data_dir) / _DRAFT_NAME


def _new_id() -> str:
    return uuid.uuid4().hex[:10]


def load_lessons(config: Config) -> dict:
    path = lessons_path(config)
    if not path.is_file():
        data = {
            "rev": _REV,
            "prompt_rules": [
                {**r, "id": _new_id(), "created": time.time()}
                for r in _SEED_PROMPT_RULES
            ],
            "lora_rules": [
                {**r, "id": _new_id(), "created": time.time()}
                for r in _SEED_LORA_RULES
            ],
            "praised": [],
            "notes": [],
        }
        save_lessons(config, data)
        return data
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {
            "rev": _REV,
            "prompt_rules": [],
            "lora_rules": [],
            "praised": [],
            "notes": [],
        }
    if not isinstance(raw, dict):
        return {
            "rev": _REV,
            "prompt_rules": [],
            "lora_rules": [],
            "praised": [],
            "notes": [],
        }
    raw.setdefault("prompt_rules", [])
    raw.setdefault("lora_rules", [])
    raw.setdefault("praised", [])
    raw.setdefault("notes", [])
    return raw


def save_lessons(config: Config, data: dict) -> None:
    config.ensure_dirs()
    path = lessons_path(config)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    tmp.replace(path)


def save_draft(config: Config, draft: TeachDraft) -> None:
    config.ensure_dirs()
    draft.ts = time.time()
    path = draft_path(config)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(
        json.dumps(draft.to_dict(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    tmp.replace(path)


def load_draft(config: Config) -> Optional[TeachDraft]:
    path = draft_path(config)
    if not path.is_file():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    if not isinstance(raw, dict):
        return None
    return TeachDraft.from_dict(raw)


def clear_draft(config: Config) -> None:
    path = draft_path(config)
    try:
        if path.is_file():
            path.unlink()
    except OSError:
        pass


def format_draft_for_chat(draft: TeachDraft, *, teach_only: bool = False) -> str:
    lines = [
        "Черновик на разбор:" if teach_only or draft.teach_only else "Собрала так:",
        f"Режим: {draft.shoot_mode} · правка: {draft.edit_kind or '?'}",
        f"--- POSITIVE ---\n{draft.positive}",
        f"--- NEGATIVE ---\n{draft.negative}",
    ]
    if draft.lora_names:
        lines.append("LoRA: " + ", ".join(draft.lora_names))
    else:
        lines.append("LoRA: чистый Wan")
    if teach_only or draft.teach_only:
        lines.append(
            "Скажи «хорошо» / «плохо» / подсказку "
            "(напр. «Anime в negative», «на фото без i2v LoRA») — запомню."
        )
    else:
        lines.append(
            "Если мимо — поправь в чате («Anime в negative», «не бери i2v»), "
            "или «хорошо» — закреплю."
        )
    return "\n".join(lines)


def format_lessons_status(config: Config) -> str:
    data = load_lessons(config)
    pr = data.get("prompt_rules") or []
    lr = data.get("lora_rules") or []
    praised = data.get("praised") or []
    notes = data.get("notes") or []
    lines = [
        f"Уроки Comfy: промпт {len(pr)}, LoRA {len(lr)}, "
        f"похвалы {len(praised)}, заметки {len(notes)}."
    ]
    for r in pr[-5:]:
        lines.append(f"· промпт: {r.get('note_ru') or r.get('id')}")
    for r in lr[-5:]:
        lines.append(f"· LoRA: {r.get('note_ru') or r.get('id')}")
    return "\n".join(lines)


_TEACH_INTENT_RE = re.compile(
    r"(?i)(?:"
    r"учим\s+промпт|учить\s+промпт|трениру\w*\s+промпт|"
    r"разбер\w*\s+промпт|урок\s+(?:по\s+)?(?:промпт|lora|лор)|"
    r"трениру\w*\s+лор|учим\s+лор|"
    r"давай\s+учить(?:ся)?|режим\s+обучен|"
    r"покажи\s+промпт\s+как\s+бы|собери\s+промпт\s+без\s+генер|"
    r"какие\s+уроки\s+(?:по\s+)?(?:промпт|comfy|лор)"
    r")"
)

_PRAISE_RE = re.compile(
    r"(?i)^\s*(?:"
    r"хорошо|отлично|молодец|правильно|так\s+и\s+надо|так\s+оставь|"
    r"закрепи|запомни\s+так|ок\s+так|норм(?:ально)?|"
    r"praise|good\s+job|keep\s+it"
    r")\s*[.!]?\s*$"
)

_CRITIQUE_START_RE = re.compile(
    r"(?i)^\s*(?:"
    r"плохо|мимо|не\s+так|ошибк|исправ|лучше|"
    r"убери|добавь|перенес|не\s+бери|не\s+ставь|запомни|"
    r"правило|урок\s*:|negative|positive|lora|лор"
    r")"
)


def is_teach_intent(text: str) -> bool:
    return bool(_TEACH_INTENT_RE.search(text or ""))


def is_lessons_status_ask(text: str) -> bool:
    return bool(
        re.search(r"(?i)какие\s+уроки\s+(?:по\s+)?(?:промпт|comfy|лор)", text or "")
    )


def is_praise(text: str) -> bool:
    return bool(_PRAISE_RE.match((text or "").strip()))


def looks_like_teach_feedback(text: str) -> bool:
    t = (text or "").strip()
    if not t or len(t) > 400:
        return False
    if is_praise(t):
        return True
    if _CRITIQUE_START_RE.search(t):
        return True
    if re.search(r"(?i)(?:negative|positive|лора|lora|anime|i2v)", t) and len(t) < 200:
        return True
    return False


def extract_wish_from_teach(text: str) -> str:
    t = _TEACH_INTENT_RE.sub(" ", text or "")
    t = re.sub(r"(?i)^\s*(?:пожалуйста|плиз|давай|ок)[,:\s]*", "", t)
    return re.sub(r"\s+", " ", t).strip(" .,!—-")


def apply_prompt_lessons(
    config: Config,
    *,
    edit_kind: str,
    process: str,
    positive: str,
    negative: str,
) -> tuple[str, str, str, List[str]]:
    """Вернуть (process, positive, negative, applied_notes)."""
    data = load_lessons(config)
    notes: List[str] = []
    proc = process or ""
    pos = positive or ""
    neg = negative or ""
    kind = (edit_kind or "").strip().lower()

    for rule in data.get("prompt_rules") or []:
        when = [str(x).lower() for x in (rule.get("when_kinds") or [])]
        if when and "*" not in when and kind not in when:
            continue
        for ban in rule.get("ban_positive") or []:
            ban_s = str(ban).strip()
            if not ban_s:
                continue
            pat = re.compile(re.escape(ban_s), re.IGNORECASE)
            if pat.search(proc) or pat.search(pos):
                proc = pat.sub("", proc)
                pos = pat.sub("", pos)
                notes.append(rule.get("note_ru") or f"убрала «{ban_s}» из positive")
        for add in rule.get("add_negative") or []:
            add_s = str(add).strip()
            if not add_s:
                continue
            if add_s.lower() not in neg.lower():
                neg = f"{neg}, {add_s}" if neg else add_s
                notes.append(rule.get("note_ru") or f"+negative: {add_s}")
        for add in rule.get("add_positive") or []:
            add_s = str(add).strip()
            if not add_s:
                continue
            if add_s.lower() not in proc.lower():
                proc = f"{proc}, {add_s}" if proc else add_s
                notes.append(rule.get("note_ru") or f"+positive: {add_s}")

    proc = re.sub(r"\s*,\s*,+", ", ", proc).strip(" ,")
    pos = re.sub(r"\s*,\s*,+", ", ", pos).strip(" ,")
    neg = re.sub(r"\s*,\s*,+", ", ", neg).strip(" ,")
    return proc, pos, neg, notes


def filter_lora_entries_by_lessons(
    config: Config,
    entries: Sequence[Any],
    *,
    shoot_mode: str = "",
) -> List[Any]:
    data = load_lessons(config)
    mode = (shoot_mode or "").strip().lower()
    out: List[Any] = []
    for e in entries:
        name = str(getattr(e, "file", "") or "").lower()
        tags = {str(t).lower() for t in (getattr(e, "tags", None) or [])}
        tags.update(re.findall(r"[a-z0-9]+", name))
        drop = False
        for rule in data.get("lora_rules") or []:
            when = [str(x).lower() for x in (rule.get("when_modes") or [])]
            if when and "*" not in when and mode not in when:
                continue
            for sub in rule.get("avoid_name_substrings") or []:
                if str(sub).lower() in name:
                    drop = True
                    break
            if drop:
                break
            for tag in rule.get("avoid_tags") or []:
                tl = str(tag).lower()
                if tl in tags or tl in name:
                    drop = True
                    break
            if drop:
                break
        if not drop:
            out.append(e)
    return out


def boost_lora_score_by_lessons(
    config: Config,
    entry: Any,
    base_score: int,
    *,
    shoot_mode: str = "",
) -> int:
    data = load_lessons(config)
    mode = (shoot_mode or "").strip().lower()
    name = str(getattr(entry, "file", "") or "").lower()
    score = int(base_score)
    for rule in data.get("lora_rules") or []:
        when = [str(x).lower() for x in (rule.get("when_modes") or [])]
        if when and "*" not in when and mode not in when:
            continue
        for sub in rule.get("prefer_name_substrings") or []:
            if str(sub).lower() in name:
                score += max(1, int(rule.get("score") or 1))
    return score


def record_praise(config: Config, draft: TeachDraft) -> str:
    data = load_lessons(config)
    data["praised"] = list(data.get("praised") or [])
    data["praised"].append(
        {
            "id": _new_id(),
            "wish": draft.wish[:200],
            "edit_kind": draft.edit_kind,
            "process": draft.process[:240],
            "negative": draft.negative[:200],
            "lora_names": list(draft.lora_names)[:4],
            "shoot_mode": draft.shoot_mode,
            "created": time.time(),
        }
    )
    data["praised"] = data["praised"][-40:]
    save_lessons(config, data)
    return "Закрепила — в следующий раз на похожее буду опираться."


def parse_and_record_critique(
    config: Config, text: str, draft: Optional[TeachDraft]
) -> str:
    t = (text or "").strip()
    data = load_lessons(config)
    bits: List[str] = []
    kind = (draft.edit_kind if draft else "") or "generic"
    mode = (draft.shoot_mode if draft else "") or "t2i"

    if re.search(
        r"(?i)(?:anime|аниме).{0,40}negative|negative.{0,40}(?:anime|аниме)|"
        r"(?:anime|аниме)\s+в\s+neg",
        t,
    ):
        data["prompt_rules"] = list(data.get("prompt_rules") or []) + [
            {
                "id": _new_id(),
                "when_kinds": [kind, "realism"] if kind != "realism" else ["realism"],
                "ban_positive": ["not anime", "not anime style"],
                "add_negative": ["Anime", "anime style"],
                "add_positive": [],
                "note_ru": "Anime в Negative (урок Дена)",
                "score": 4,
                "from": "den",
                "created": time.time(),
            }
        ]
        bits.append("поняла: Anime → Negative, не «not anime» в Positive")

    if re.search(
        r"(?i)убер\w*.{0,20}not\s*anime|not\s*anime.{0,20}(?:убер|из\s+pos)", t
    ):
        data["prompt_rules"] = list(data.get("prompt_rules") or []) + [
            {
                "id": _new_id(),
                "when_kinds": [kind, "realism"],
                "ban_positive": ["not anime", "not anime style"],
                "add_negative": [],
                "add_positive": [],
                "note_ru": "не писать not anime в Positive",
                "score": 3,
                "from": "den",
                "created": time.time(),
            }
        ]
        bits.append("убрала «not anime» из Positive")

    if re.search(
        r"(?i)(?:"
        r"не\s+бер\w*.{0,30}(?:i2v|t2v|video)|"
        r"(?:i2v|video).{0,30}(?:не\s+бер|на\s+фото|на\s+still|на\s+картин)|"
        r"(?:фото|still|картин|png).{0,30}(?:без|не).{0,20}(?:i2v|video|лор)"
        r")",
        t,
    ):
        data["lora_rules"] = list(data.get("lora_rules") or []) + [
            {
                "id": _new_id(),
                "when_modes": ["t2i", "i2i"],
                "avoid_name_substrings": ["i2v", "t2v", "video"],
                "prefer_name_substrings": [],
                "avoid_tags": ["i2v", "t2v", "video"],
                "note_ru": "still ≠ i2v/video LoRA (урок Дена)",
                "score": 5,
                "from": "den",
                "created": time.time(),
            }
        ]
        bits.append("на still больше не беру i2v/video LoRA")

    m_neg = re.search(
        r"(?i)(?:добав\w*|впиши|пиши)\s+(?:в\s+)?(?:negative|негатив)\s*[:=]?\s*(.+)$",
        t,
    )
    if m_neg:
        phrase = m_neg.group(1).strip(" .,\"'«»")
        if phrase and len(phrase) < 80:
            data["prompt_rules"] = list(data.get("prompt_rules") or []) + [
                {
                    "id": _new_id(),
                    "when_kinds": [kind] if kind else ["*"],
                    "ban_positive": [],
                    "add_negative": [phrase],
                    "add_positive": [],
                    "note_ru": f"+Negative: {phrase}",
                    "score": 2,
                    "from": "den",
                    "created": time.time(),
                }
            ]
            bits.append(f"в Negative добавлю «{phrase}»")

    m_note = re.search(r"(?i)(?:запомни|правило|урок)\s*[:=]\s*(.+)$", t)
    if m_note:
        note = m_note.group(1).strip()[:300]
        if note:
            data["notes"] = list(data.get("notes") or [])
            data["notes"].append(
                {
                    "id": _new_id(),
                    "text": note,
                    "edit_kind": kind,
                    "shoot_mode": mode,
                    "created": time.time(),
                }
            )
            data["notes"] = data["notes"][-50:]
            bits.append(f"записала: {note}")

    if not bits:
        data["notes"] = list(data.get("notes") or [])
        data["notes"].append(
            {
                "id": _new_id(),
                "text": t[:300],
                "edit_kind": kind,
                "shoot_mode": mode,
                "created": time.time(),
                "raw": True,
            }
        )
        data["notes"] = data["notes"][-50:]
        bits.append("записала замечание — буду осторожнее на похожих")

    for key in ("prompt_rules", "lora_rules"):
        seen = set()
        uniq = []
        for r in data.get(key) or []:
            marker = (
                str(r.get("note_ru") or ""),
                tuple(r.get("when_kinds") or r.get("when_modes") or []),
            )
            if marker in seen and r.get("from") != "den-seed":
                continue
            seen.add(marker)
            uniq.append(r)
        data[key] = uniq[-30:]

    save_lessons(config, data)
    return "Урок: " + "; ".join(bits) + ".\n" + format_lessons_status(config)
