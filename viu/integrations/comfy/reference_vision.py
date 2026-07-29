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

_REFERENCE_PROMPT = """Это референс для генерации MoCap-анимации персонажа (табакси Шаня / humanoid).
{hint}

Ответь СТРОГО в формате (без markdown):
EN_POSE: <одна строка English: pose, action, camera angle, framing — для t2v/i2v>
EN_LOOK: <outfit, body, lighting, background — English tags>
RU: <2–4 предложения по-русски: что на кадре, настроение, для чего референс>
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


_LOOK_SELF_PROMPT = """Ден прислал фото и говорит, что это ты — девушка Вью.
{hint}

Посмотри на картинку и ответь коротко по-русски от первого лица (я, мне, у меня).
2–4 живых предложения: поза, фигура, одежда, лицо, волосы, фон, свет.
Только русский. Без английских слов, без списков, без служебных пометок."""

_LOOK_OTHER_PROMPT = """Ден прислал фото в чат.
{hint}

Посмотри и ответь коротко по-русски: кто на кадре, поза, одежда, фон, свет, настроение.
2–4 предложения. Только русский. Без английских слов, без списков."""


def _strip_vision_model_prefix(text: str) -> str:
    """ask_vision иногда префиксирует [model]\\n — убрать для чата."""
    body = (text or "").strip()
    if body.startswith("[") and "]" in body[:80]:
        body = body.split("]", 1)[1].strip()
    return body


def _look_quality_ok(text: str) -> bool:
    """Отсечь кашу EN/RU и эхо инструкций от слабых VL-моделей."""
    body = (text or "").strip()
    if len(body) < 12:
        return False
    cyr = len(re.findall(r"[А-Яа-яЁё]", body))
    lat = len(re.findall(r"[A-Za-z]", body))
    if cyr < 20:
        return False
    if lat > cyr * 0.45:
        return False
    low = body.lower()
    if re.search(
        r"(?i)не\s+могу\s+(?:продолж|выполн)|cannot\s+continue|i\s+cannot|"
        r"если\s+ден\s+хвал|без\s+markdown|en_pose|as\s+an\s+ai",
        low,
    ):
        return False
    return True


def look_at_photo(
    config: Config,
    path: str | Path,
    *,
    as_self: bool = False,
    hint: str = "",
    character_title: str = "",
) -> Tuple[bool, str]:
    """Живой взгляд на фото → короткое RU-описание (не технический MoCap-отчёт)."""
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

    hint_bits = []
    h = (hint or "").strip()
    # Не тащить в VL длинные служебные куски — только тёплый контекст Дена.
    if h:
        h = re.sub(r"(?i)\[tg_photo:[^\]]+\]", "", h).strip()
        if len(h) > 180:
            h = h[:177] + "…"
        if h:
            hint_bits.append(h)
    if character_title and not as_self:
        hint_bits.append(f"На кадре, скорее всего, {character_title}.")
    hint_block = "\n".join(hint_bits) if hint_bits else ""

    prompt = (_LOOK_SELF_PROMPT if as_self else _LOOK_OTHER_PROMPT).format(
        hint=hint_block or "Просто опиши, что видишь."
    )
    v_ok, v_text = ask_vision(frame_path, prompt=prompt, config=config)
    if not v_ok:
        return False, _strip_vision_model_prefix(v_text) or "Не разглядела."
    text = _strip_vision_model_prefix(v_text)
    if not _look_quality_ok(text):
        # Мягкий fallback — без каши и без отказов.
        if as_self:
            text = "Вижу себя на этом кадре — запомнила, как выгляжу."
        elif character_title:
            text = f"Вижу кадр с {character_title} — запомнила."
        else:
            text = "Вижу кадр — запомнила."
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
