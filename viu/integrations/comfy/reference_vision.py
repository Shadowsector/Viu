"""Референсы для Comfy/MoCap: картинка или кадр из видео → Ollama VL → EN/RU описание."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Tuple

from ...config import Config
from ..vision_eye import ask_vision, pick_vision_model
from .clip_review import extract_first_frame, extract_last_frame
from .paths import comfy_refs_dir
from .vision_review import extract_middle_frame

_IMAGE_EXT = frozenset({".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif"})
_VIDEO_EXT = frozenset({".mp4", ".webm", ".mov", ".mkv", ".avi"})

_REFERENCE_PROMPT = """Это референс для генерации (MoCap / Comfy).
{hint}

Ответь СТРОГО в формате (без markdown):
КТО: <кто на кадре — 3–10 слов по-русски>
ОДЕЖДА: <что надето / голое, цвета>
ПОЗА: <поза тела>
ДЕЙСТВИЕ: <что делает>
ВОЛОСЫ_ЛИЦО: <волосы, лицо>
ФОН: <место, свет>
EN_POSE: <одна строка English: pose, action, camera, framing — для t2v/i2v>
EN_LOOK: <outfit, body, lighting, background — English tags>
RU: <2–3 предложения по-русски: кто, во что одет, что делает>
TAGS: <через запятую: pose, camera, outfit, …>

Если кадр пустой/чёрный/без фигуры — напиши VERDICT: EMPTY и кратко почему."""


@dataclass
class ReferenceDescription:
    path: str
    source_kind: str
    frame_path: str
    en_pose: str
    en_look: str
    ru: str
    tags: List[str]
    verdict: str
    raw: str
    vision_ok: bool

    def to_dict(self) -> Dict[str, Any]:
        return {
            "path": self.path,
            "source_kind": self.source_kind,
            "frame_path": self.frame_path,
            "en_pose": self.en_pose,
            "en_look": self.en_look,
            "ru": self.ru,
            "tags": self.tags,
            "verdict": self.verdict,
            "raw": self.raw,
            "vision_ok": self.vision_ok,
        }


def _parse_reference(text: str) -> Tuple[str, str, str, List[str], str]:
    en_pose, en_look, ru, tags, verdict = "", "", "", [], ""
    who = clothes = pose = action = hair = bg = ""
    for line in (text or "").splitlines():
        s = line.strip()
        if not s:
            continue
        low = s.lower()
        if low.startswith("en_pose:"):
            en_pose = s.split(":", 1)[1].strip()
        elif low.startswith("en_look:"):
            en_look = s.split(":", 1)[1].strip()
        elif low.startswith("ru:"):
            ru = s.split(":", 1)[1].strip()
        elif low.startswith("tags:"):
            bits = s.split(":", 1)[1].strip()
            tags = [t.strip() for t in re.split(r"[,;|/]+", bits) if t.strip()]
        elif low.startswith("verdict:"):
            verdict = s.split(":", 1)[1].strip().upper().split()[0]
        elif low.startswith("кто:"):
            who = s.split(":", 1)[1].strip()
        elif low.startswith("одежда:"):
            clothes = s.split(":", 1)[1].strip()
        elif low.startswith("поза:"):
            pose = s.split(":", 1)[1].strip()
        elif low.startswith("действие:"):
            action = s.split(":", 1)[1].strip()
        elif low.startswith("волосы_лицо:") or low.startswith("волосы/лицо:"):
            hair = s.split(":", 1)[1].strip()
        elif low.startswith("фон:"):
            bg = s.split(":", 1)[1].strip()
    if not ru:
        bits = [b for b in (who, clothes, pose, action, hair, bg) if b]
        if bits:
            ru = " ".join(bits)
    if not verdict and "empty" in (text or "").lower():
        verdict = "EMPTY"
    return en_pose, en_look, ru, tags, verdict


def _resolve_frame(
    src: Path,
    *,
    frame: str,
    config: Config,
) -> Tuple[bool, Path, str, str]:
    """Вернуть (ok, frame_path, kind, err)."""
    ext = src.suffix.lower()
    out_dir = comfy_refs_dir(config) / "vision_refs"
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = src.stem[:48]

    if ext in _IMAGE_EXT:
        return True, src, "image", ""

    if ext not in _VIDEO_EXT:
        return False, src, "unknown", f"неизвестный тип: {ext}"

    which = (frame or "middle").strip().lower()
    if which in ("mid", "middle", "center"):
        dest = out_dir / f"{stem}_mid.png"
        ok, msg = extract_middle_frame(src, dest)
        kind = "video_middle"
    elif which in ("first", "start", "0"):
        dest = out_dir / f"{stem}_first.png"
        ok, msg = extract_first_frame(src, dest)
        kind = "video_first"
    elif which in ("last", "end", "-1"):
        dest = out_dir / f"{stem}_last.png"
        ok, msg = extract_last_frame(src, dest)
        kind = "video_last"
    else:
        return False, src, "video", f"frame=? (first|middle|last), got {frame!r}"

    if not ok:
        return False, dest, kind, msg
    return True, dest, kind, ""


def describe_reference(
    config: Config,
    path: str | Path,
    *,
    frame: str = "middle",
    hint: str = "",
    save_json: bool = True,
) -> ReferenceDescription:
    """Картинка или видео → llava/qwen2-vl → структурированное описание."""
    src = Path(path)
    empty = ReferenceDescription(
        path=str(src),
        source_kind="",
        frame_path="",
        en_pose="",
        en_look="",
        ru="",
        tags=[],
        verdict="",
        raw="",
        vision_ok=False,
    )
    if not src.is_file():
        empty.raw = f"Нет файла: {src}"
        return empty
    if not pick_vision_model(config.base_url):
        empty.raw = "Нет llava/qwen2-vl в Ollama (ollama pull llava)."
        return empty

    ok_f, frame_path, kind, err = _resolve_frame(src, frame=frame, config=config)
    if not ok_f:
        empty.source_kind = kind
        empty.raw = err
        return empty

    prompt = _REFERENCE_PROMPT.format(hint=(hint or "Опиши кадр как референс для следующей анимации.").strip())
    v_ok, v_text = ask_vision(frame_path, prompt=prompt, config=config)
    body = v_text if v_ok else v_text
    en_pose, en_look, ru, tags, verdict = _parse_reference(body if v_ok else "")
    desc = ReferenceDescription(
        path=str(src),
        source_kind=kind,
        frame_path=str(frame_path),
        en_pose=en_pose,
        en_look=en_look,
        ru=ru,
        tags=tags,
        verdict=verdict,
        raw=body,
        vision_ok=v_ok,
    )
    if save_json and v_ok:
        out = comfy_refs_dir(config) / "vision_refs" / f"{src.stem}_ref.json"
        try:
            out.write_text(
                json.dumps(desc.to_dict(), ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
        except OSError:
            pass
    return desc


def format_reference_report(desc: ReferenceDescription) -> str:
    lines = [
        f"Источник: {desc.path} ({desc.source_kind})",
        f"Кадр: {desc.frame_path or '—'}",
    ]
    if desc.verdict:
        lines.append(f"VERDICT: {desc.verdict}")
    if desc.en_pose:
        lines.append(f"EN_POSE: {desc.en_pose}")
    if desc.en_look:
        lines.append(f"EN_LOOK: {desc.en_look}")
    if desc.ru:
        lines.append(f"RU: {desc.ru}")
    if desc.tags:
        lines.append(f"TAGS: {', '.join(desc.tags)}")
    if desc.raw and not desc.vision_ok:
        lines.append(desc.raw)
    elif desc.raw and not (desc.en_pose or desc.ru):
        lines.append("--- raw ---")
        lines.append(desc.raw[:2000])
    return "\n".join(lines)


_LOOK_SELF_PROMPT = """Ден прислал фото. Это референс внешности девушки Вью (ты).
{hint}

Смотри ТОЛЬКО на картинку. Ответь СТРОГО по-русски в формате (каждая метка с новой строки):
КТО: я / девушка Вью — кратко кто на кадре
ОДЕЖДА: что надето (или без одежды), цвета, детали
ПОЗА: стоит / сидит / лежит / …, руки, ноги, ракурс
ДЕЙСТВИЕ: что делает сейчас одной фразой
ВОЛОСЫ_ЛИЦО: волосы, лицо, выражение
ФОН: место и свет

Только факты с фото. Запрещено: английские слова, списки 1.2.3, «я могу/не могу», инструкции, выдумки."""

_LOOK_OTHER_PROMPT = """Ден прислал фото-референс.
{hint}

Смотри ТОЛЬКО на картинку. Ответь СТРОГО по-русски в формате (каждая метка с новой строки):
КТО: кто изображён (девушка/парень/существо/несколько) — 3–8 слов
ОДЕЖДА: что надето (или без), цвета, стиль
ПОЗА: стоит / сидит / лежит / …, руки, ноги, ракурс
ДЕЙСТВИЕ: что делает сейчас одной фразой
ВОЛОСЫ_ЛИЦО: волосы, лицо, выражение
ФОН: место и свет

Только факты с фото. Запрещено: английские слова, списки 1.2.3, «я могу/не могу», инструкции, выдумки."""

_LOOK_RETRY_PROMPT = """Ещё раз по картинке. Только русский. Формат:
КТО: …
ОДЕЖДА: …
ПОЗА: …
ДЕЙСТВИЕ: …
ВОЛОСЫ_ЛИЦО: …
ФОН: …
Без английского, без нумерации, без «могу/не могу»."""

_LOOK_FIELDS = ("КТО", "ОДЕЖДА", "ПОЗА", "ДЕЙСТВИЕ", "ВОЛОСЫ_ЛИЦО", "ФОН")


def sanitize_vision_hint(hint: str) -> str:
    """Не тащить в VL литературщину («перепиши», «впечатления») — только якорь."""
    h = (hint or "").strip()
    h = re.sub(r"(?i)\[tg_photo:[^\]]+\]", "", h).strip()
    if not h:
        return ""
    # Убрать просьбы переписать/оценить — они сбивают слабый VL в мета-бред.
    h = re.sub(
        r"(?i)(?:перепиш\w*|перескаж\w*|расскажи\s+впечатлен\w*|"
        r"впечатлен\w*\s+от|что\s+думаешь\s+о|оцени|дай\s+оценк\w*)"
        r"[^.!?\n]*[.!?]?",
        " ",
        h,
    )
    h = " ".join(h.split()).strip(" .,;:—-")
    if len(h) > 120:
        h = h[:117] + "…"
    # Если после чистки осталась одна литературщина — лучше без hint.
    if re.search(r"(?i)^(?:суккуб|сцена|перепиш|впечатлен)", h) and len(h) < 40:
        return ""
    return h


def _parse_look_fields(text: str) -> dict[str, str]:
    out: dict[str, str] = {k: "" for k in _LOOK_FIELDS}
    body = (text or "").strip()
    if not body:
        return out
    aliases = {
        "КТО": ("КТО",),
        "ОДЕЖДА": ("ОДЕЖДА",),
        "ПОЗА": ("ПОЗА",),
        "ДЕЙСТВИЕ": ("ДЕЙСТВИЕ",),
        "ВОЛОСЫ_ЛИЦО": ("ВОЛОСЫ_ЛИЦО", "ВОЛОСЫ/ЛИЦО", "ВОЛОСЫ", "ЛИЦО"),
        "ФОН": ("ФОН",),
    }
    for key, names in aliases.items():
        for name in names:
            m = re.search(
                rf"(?im)^\s*{re.escape(name)}\s*[:\-–]\s*(.+)$",
                body,
            )
            if m:
                val = m.group(1).strip().strip("`\"'")
                if val:
                    if out[key]:
                        out[key] = f"{out[key]}; {val}"
                    else:
                        out[key] = val
                if key != "ВОЛОСЫ_ЛИЦО":
                    break
    return out


def format_look_from_fields(fields: dict[str, str], *, as_self: bool = False) -> str:
    """Собрать живой RU-абзац из структурированных полей."""
    kto = (fields.get("КТО") or "").strip()
    odezhda = (fields.get("ОДЕЖДА") or "").strip()
    poza = (fields.get("ПОЗА") or "").strip()
    deystvie = (fields.get("ДЕЙСТВИЕ") or "").strip()
    volosy = (fields.get("ВОЛОСЫ_ЛИЦО") or "").strip()
    fon = (fields.get("ФОН") or "").strip()
    bits: list[str] = []
    if as_self:
        if kto:
            bits.append(f"Это я: {kto}.")
        else:
            bits.append("Это я на кадре.")
    elif kto:
        bits.append(f"На кадре — {kto}.")
    if odezhda:
        bits.append(f"Одежда: {odezhda}.")
    pose_bits = [p for p in (poza, deystvie) if p]
    if pose_bits:
        bits.append(" ".join(pose_bits) + ("" if pose_bits[-1].endswith(".") else "."))
    if volosy:
        bits.append(f"Волосы/лицо: {volosy}.")
    if fon:
        bits.append(f"Фон: {fon}.")
    text = " ".join(bits).strip()
    text = re.sub(r"\s{2,}", " ", text)
    text = re.sub(r"\.\s*\.", ".", text)
    return text


def _mixed_script_token_count(text: str) -> int:
    n = 0
    for tok in re.findall(r"[A-Za-zА-Яа-яЁё]+", text or ""):
        has_lat = bool(re.search(r"[A-Za-z]", tok))
        has_cyr = bool(re.search(r"[А-Яа-яЁё]", tok))
        if has_lat and has_cyr:
            n += 1
    return n


def _strip_vision_model_prefix(text: str) -> str:
    """ask_vision иногда префиксирует [model]\\n — убрать для чата."""
    body = (text or "").strip()
    if body.startswith("[") and "]" in body[:80]:
        body = body.split("]", 1)[1].strip()
    return body


def _look_quality_ok(text: str) -> bool:
    """Отсечь кашу EN/RU, мета-«я могу», эхо инструкций от слабых VL."""
    body = (text or "").strip()
    if len(body) < 12:
        return False
    cyr = len(re.findall(r"[А-Яа-яЁё]", body))
    lat = len(re.findall(r"[A-Za-z]", body))
    if cyr < 20:
        return False
    if lat > cyr * 0.28:
        return False
    if _mixed_script_token_count(body) >= 2:
        return False
    low = body.lower()
    if re.search(
        r"(?i)не\s+могу\s+(?:продолж|выполн|показа|описа|разгля)|"
        r"я\s+могу\s+(?:показа|обсер|observ|упоминан|расслыш)|"
        r"cannot\s+continue|i\s+cannot|as\s+an\s+ai|"
        r"если\s+ден\s+хвал|без\s+markdown|en_pose|"
        r"\bobserv|elementy|deвуш|поze\b|peчат",
        low,
    ):
        return False
    # Нумерованные «я могу…» списки — типичный бред llava.
    if len(re.findall(r"(?m)^\s*\d+[.)]\s+", body)) >= 2:
        return False
    return True


def _fallback_look(*, as_self: bool, character_title: str) -> str:
    if as_self:
        return "Вижу себя на этом кадре — запомнила облик, но формулировку сейчас не вытянуть чисто."
    if character_title:
        return f"Вижу кадр с {character_title} — запомнила, детали позже уточню."
    return "Вижу кадр — запомнила референс."


def look_at_photo(
    config: Config,
    path: str | Path,
    *,
    as_self: bool = False,
    hint: str = "",
    character_title: str = "",
) -> Tuple[bool, str]:
    """Живой взгляд на фото → кто / одежда / поза / действие (не мета-бред VL)."""
    src = Path(path)
    if not src.is_file():
        return False, f"Не вижу файл: {src.name}"
    if not pick_vision_model(config.base_url):
        return False, (
            "Сейчас не разглядеть — нет vision-модели в Ollama. "
            "Поставь llava или qwen2-vl."
        )
    ok_f, frame_path, _kind, err = _resolve_frame(src, frame="middle", config=config)
    if not ok_f:
        return False, err or "Не вытащить кадр."

    hint_bits: list[str] = []
    clean_hint = sanitize_vision_hint(hint)
    if clean_hint:
        hint_bits.append(clean_hint)
    if character_title and not as_self:
        hint_bits.append(f"На кадре, скорее всего, {character_title}.")
    hint_block = "\n".join(hint_bits) if hint_bits else "Опиши только то, что видно на фото."

    prompt = (_LOOK_SELF_PROMPT if as_self else _LOOK_OTHER_PROMPT).format(hint=hint_block)
    v_ok, v_text = ask_vision(frame_path, prompt=prompt, config=config)
    if not v_ok:
        return False, _strip_vision_model_prefix(v_text) or "Не разглядела."
    raw = _strip_vision_model_prefix(v_text)
    fields = _parse_look_fields(raw)
    text = format_look_from_fields(fields, as_self=as_self) if any(fields.values()) else raw

    if not _look_quality_ok(text) or sum(1 for v in fields.values() if v) < 2:
        # Повтор со строгим коротким промптом.
        v2_ok, v2_text = ask_vision(frame_path, prompt=_LOOK_RETRY_PROMPT, config=config)
        if v2_ok:
            raw2 = _strip_vision_model_prefix(v2_text)
            fields2 = _parse_look_fields(raw2)
            if sum(1 for v in fields2.values() if v) >= 2:
                text2 = format_look_from_fields(fields2, as_self=as_self)
                if _look_quality_ok(text2):
                    text = text2
                    raw = raw2
                    fields = fields2
            elif _look_quality_ok(raw2):
                text = raw2
                raw = raw2

    if not _look_quality_ok(text):
        text = _fallback_look(as_self=as_self, character_title=character_title)

    if len(text) > 900:
        text = text[:897].rstrip() + "…"
    try:
        out = comfy_refs_dir(config) / "vision_refs" / f"{src.stem}_look.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(
            json.dumps(
                {
                    "path": str(src),
                    "as_self": as_self,
                    "hint": hint,
                    "hint_sanitized": clean_hint,
                    "fields": fields,
                    "raw": raw[:4000],
                    "text": text,
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
    except OSError:
        pass
    return True, text


def build_scene_action_en(
    *,
    kind: str = "scene",
    user_text: str = "",
    look_ru: str = "",
    config: Config | None = None,
) -> str:
    """Сцена для lab/Comfy: описание Дена → EN action; реф — якорь внешности."""
    from .scene_en import scene_wish_to_en

    wish = extract_scene_wish(user_text)
    look = (look_ru or "").strip()[:280]
    if look and re.search(r"[А-Яа-яЁё]", look):
        look = look[:80]
    base_look = (
        f", matching the reference look ({look})"
        if look
        else ", matching the reference face, body and style"
    )
    k = (kind or "scene").strip().lower()

    if k in ("selfie", "селфи") and (
        not wish or re.fullmatch(r"(?i)селфи|selfie|сво[её]\s+селфи", wish or "")
    ):
        return (
            "young woman taking a selfie, looking at camera, close-up phone angle, "
            "soft natural light, gentle expression, upper body"
            + base_look
        )

    if not wish and k in ("fantasy", "фентези", "пейзаж"):
        return (
            "young woman standing in a fantasy landscape, magical atmosphere, "
            "dramatic sky, medium shot, cinematic lighting"
            + base_look
        )

    en_core = (
        scene_wish_to_en(wish, config=config)
        if wish
        else "young woman in the described scene, medium shot, natural motion"
    )
    return f"{en_core}{base_look}"


def extract_scene_wish(text: str) -> str:
    """Вытащить описание сцены из фразы Дена."""
    s = (text or "").strip()
    s = re.sub(r"(?i)^\[tg_photo:[^\]]+\]\s*", "", s)
    s = re.sub(r"(?i)^\s*ок[,!.…]?\s*", "", s)
    s = re.sub(r"(?i)(?:вот,?\s*)?это\s+ты[!.…]?\s*", "", s)
    # «нарисуй себя, развалившуюся…» — запятая после себя ок
    s = re.sub(
        r"(?i)^\s*(?:пожалуйста[,.]?\s*)?"
        r"(?:сними|снять|снимай|сделай|создай|сгенер(?:ируй)?|нарисуй|нарисовать|"
        r"сфотка(?:й|ть)|сфотографируй)\s+"
        r"(?:себя|тебя|мне|фото(?:графию)?|картинк\w*|рисунок|из\s+(?:этого\s+)?референса"
        r"(?:\s+сво[её])?|сво[её])?\s*"
        r"[,:]?\s*"
        r"(?:как\s+(?:ты\s+)?)?",
        "",
        s,
    )
    s = re.sub(
        r"(?i)^\s*(?:нужен|нужна|нужно)\s+(?:рисунок|фото|клип|видео|картинк\w*)\s*"
        r"(?:в\s+(?:комфи|comfy(?:\s*ui)?)\s*)?[:=\-–,]?\s*",
        "",
        s,
    )
    s = re.sub(r"(?i)^\s*(?:сцена|снимай|снять|кадр)\s*[:=\-–]\s*", "", s)
    s = re.sub(r"(?i)\b(?:в\s+комфи|в\s+comfy(?:\s*ui)?|через\s+комфи)\b", "", s)
    s = re.sub(r"(?i)^\s*из\s+(?:этого\s+)?референса\s*", "", s)
    return " ".join(s.split()).strip(" .,;:—-")
