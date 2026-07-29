"""Чат-оркестратор Comfy: взгляд на фото, рефы, LoRA, видео — без имён тулов."""

from __future__ import annotations

import json
import re
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple

from ...config import Config
from .character_refs import (
    assign_character_ref,
    character_image_path,
    format_character_refs_status,
    resolve_character_id,
)
from .intent import looks_like_comfy_job_request, mentions_comfy
from .paths import comfy_refs_dir

_TG_PHOTO_RE = re.compile(
    r"^\[tg_photo:(?P<path>[^\]]+)\]\s*(?P<caption>.*)$",
    re.DOTALL,
)

_ASSIGN_RE = re.compile(
    r"(?i)(?:"
    r"(?:это|вот,?\s*это|вот\s+это|смотри)\s+(?P<a>ты|тебя|вью|вьюшка|шаня|шанька|минотавр|мино|бык)\b|"
    r"так\s+выгляд(?:ишь|ит)\s+(?P<b>ты|вью|шаня|минотавр)\b|"
    r"(?P<c>ты|вью|шаня|минотавр)\s*[—\-–:,]\s*(?:вот|так|реф)|"
    r"реф(?:еренс)?\s+(?:для\s+)?(?P<d>тебя|вью|шани|минотавра)\b|"
    r"вот\s+референс.{0,40}(?P<e>ты|вью|шаня|минотавр)\b"
    r")"
)

_LOOK_RE = re.compile(
    r"(?i)(?:"
    r"посмотри|глянь|взглян|посмотри\s+на\s+(?:себя|это|фото|картинк)|"
    r"какая\s+ты|какой\s+ты|как\s+ты\s+выгляд|"
    r"красив|мило\s+выгляд|нравишься"
    r")"
)

_ANALYZE_RE = re.compile(
    r"(?i)(?:разбер|анализ|проанализ|что\s+на\s+(?:этой\s+)?(?:картинк|фото|реф)|"
    r"опиши\s+(?:реф|картинк|фото|себя)|разбор\s+реф)"
)

_PROCESS_RE = re.compile(
    r"(?i)(?:обработай|обработать|создай\s+из\s+референс|прогони\s+реф|"
    r"подготовь\s+(?:реф|картинк|фото)|сделай\s+обработан)"
)

_SELFIE_RE = re.compile(
    r"(?i)(?:\bселфи\b|\bselfie\b|"
    r"сво[её]\s+селфи|"
    r"сфотка(?:й|ть)\s+себя)"
)

_FANTASY_RE = re.compile(
    r"(?i)(?:фентез|фэнтез|fantasy|"
    r"магическ(?:ом|ий)\s+пейзаж|"
    r"фентезийном\s+пейзаж|"
    r"фэнтезийном\s+пейзаж)"
)

# Ден говорит, ЧТО сделать из рефа / в Комфи.
_DIRECTED_SHOOT_RE = re.compile(
    r"(?i)(?:"
    r"(?:сними|снять|снимай|сделай|создай|сгенер(?:ируй)?|нарисуй|нарисовать|"
    r"сфотка(?:й|ть)|сфотографируй)\s+"
    r"(?:себя|тебя|из\s+(?:этого\s+)?реф|клип|видео|сцен|фото|картинк|рисунок)|"
    r"(?:сними|снять|снимай|сделай|нарисуй)\s+(?:в|на|у|под|возле|среди)\b|"
    r"(?:сделай|создай)\s+фото|"
    r"(?:нужен|нужна|нужно)\s+(?:рисунок|фото|клип|видео|картинк)|"
    r"(?:сцена|снимай|снять|кадр)\s*[:=\-–]|"
    r"хочу\s+(?:чтобы\s+)?ты\s+(?:была|сняла|снялась|стояла|шла|сидела|лежала)|"
    r"из\s+(?:этого\s+)?референса|"
    r"\bселфи\b|\bselfie\b"
    r")"
)

_LORA_RE = re.compile(
    r"(?i)(?:подгруз|загруз|включи|выбер|постав).{0,24}(?:лор[ауы]?|lora)|"
    r"(?:лор[ауы]?|lora).{0,24}(?:подгруз|загруз|включи|выбер|список|какие)|"
    r"^\s*(?:лор[ауы]?|lora)\s*$"
)

_VIDEO_RE = re.compile(
    r"(?i)(?:сделай|сними|создай|сгенер|запусти).{0,40}(?:видео|клип|ролик)|"
    r"(?:видео|клип).{0,40}(?:comfy|комфи)|"
    r"(?:comfy|комфи).{0,40}(?:видео|клип|сними|снять|сгенер)|"
    r"сними\s+себя|снять\s+себя"
)

_STATUS_RE = re.compile(
    r"(?i)(?:какие\s+реф|референсы\s+персонаж|кто\s+на\s+реф|"
    r"покажи\s+реф(?:ы|еренсы)?\s+персонаж|статус\s+реф)"
)

_LAB_SHORT_RE = re.compile(
    r"(?is)^\s*(?:"
    r"(?:ок|ok|да|yes|approve|нет|no|стоп|stop|отмена)\s*[.!…]?\s*$|"
    r"(?:lora|лора)\s*:|"
    r"лучший\s*:|"
    r"правк"
    r")",
)

_TITLES = {"viu": "Вью", "shanya": "Шаня", "minotaur": "Минотавр"}


@dataclass
class ChatFlowOutcome:
    handled: bool
    message: str = ""
    start_shoot: bool = False
    shoot_action: str = ""
    media_to_send: List[Tuple[str, str]] = field(default_factory=list)
    # ("photo"|"video", path)


def _pending_path(config: Config) -> Path:
    return Path(config.data_dir) / "comfy_chat_pending.json"


def _read_pending(config: Config) -> dict:
    path = _pending_path(config)
    if not path.is_file():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def set_pending_ref(
    config: Config,
    path: str | Path,
    *,
    caption: str = "",
    look_text: str = "",
    pending_character: str = "",
) -> None:
    prev = _read_pending(config)
    payload = {
        "path": str(Path(path).resolve()),
        "caption": (caption or "").strip()[:500],
        "look_text": (look_text or prev.get("look_text") or "")[:1500],
        "pending_character": (
            (pending_character or prev.get("pending_character") or "").strip().lower()
        ),
        "at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    dest = _pending_path(config)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def set_pending_character(config: Config, character: str, *, note: str = "") -> None:
    """«Это ты» пришло текстом до фото — ждать картинку."""
    prev = _read_pending(config)
    payload = {
        "path": str(prev.get("path") or ""),
        "caption": note.strip()[:500],
        "look_text": str(prev.get("look_text") or ""),
        "pending_character": (character or "").strip().lower(),
        "at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    dest = _pending_path(config)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def get_pending_character(config: Config) -> Optional[str]:
    cid = str(_read_pending(config).get("pending_character") or "").strip().lower()
    return cid if cid in ("viu", "shanya", "minotaur") else None


def clear_pending_character(config: Config) -> None:
    raw = _read_pending(config)
    if not raw:
        return
    raw["pending_character"] = ""
    dest = _pending_path(config)
    try:
        dest.write_text(json.dumps(raw, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except OSError:
        pass


def get_pending_ref(config: Config) -> Optional[Path]:
    raw = _read_pending(config)
    p = Path(str(raw.get("path") or ""))
    return p if p.is_file() else None


def get_pending_look(config: Config) -> str:
    return str(_read_pending(config).get("look_text") or "").strip()


def clear_pending_ref(config: Config) -> None:
    path = _pending_path(config)
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass


def parse_tg_photo_payload(text: str) -> Tuple[Optional[Path], str]:
    m = _TG_PHOTO_RE.match((text or "").strip())
    if not m:
        return None, (text or "").strip()
    p = Path(m.group("path").strip())
    return p, (m.group("caption") or "").strip()


def _resolve_assign_character(text: str) -> Optional[str]:
    m = _ASSIGN_RE.search(text or "")
    if not m:
        if re.search(r"(?i)\b(?:это|вот|реф|выгляд)", text or ""):
            return resolve_character_id(text or "")
        return None
    token = next((g for g in m.groups() if g), None) or ""
    return resolve_character_id(token) or resolve_character_id(text or "")


def _wants_look(text: str) -> bool:
    return bool(_LOOK_RE.search(text or "") or _ANALYZE_RE.search(text or ""))


def _wants_analyze(text: str) -> bool:
    return bool(_ANALYZE_RE.search(text or ""))


def _wants_process(text: str) -> bool:
    return bool(_PROCESS_RE.search(text or ""))


def _wants_selfie(text: str) -> bool:
    return bool(_SELFIE_RE.search(text or ""))


def _wants_fantasy(text: str) -> bool:
    return bool(_FANTASY_RE.search(text or ""))


def _wants_lora(text: str) -> bool:
    return bool(_LORA_RE.search(text or ""))


def _wants_directed_shoot(text: str, config: Config) -> bool:
    """Ден описал сцену / сказал сделать фото-рисунок из рефа."""
    t = text or ""
    if _wants_selfie(t) or _wants_fantasy(t):
        return True
    if looks_like_comfy_job_request(t):
        return True
    has_ref = get_pending_ref(config) is not None or character_image_path(config, "viu") is not None
    if _DIRECTED_SHOOT_RE.search(t):
        if has_ref:
            return True
        if mentions_comfy(t):
            return True
        if re.search(
            r"(?i)\bсебя\b|референс|(?:сцена|снимай|снять|кадр)\s*[:=\-–]|"
            r"нарисуй|рисунок|сделай\s+фото",
            t,
        ):
            return True
    if has_ref and len(t.strip()) >= 18:
        if _LOOK_RE.search(t) or _ASSIGN_RE.search(t) or _LORA_RE.search(t):
            return False
        if re.search(
            r"(?i)^(?:в|на|у|под|возле|среди|сто[ия]шь|ид[её]шь|сидишь|лежишь|"
            r"ты\s+просто)\b",
            t.strip(),
        ):
            return True
    if not _VIDEO_RE.search(t) and not re.search(
        r"(?i)нарисуй|рисунок|сделай\s+фото|сфотка", t
    ):
        return False
    if mentions_comfy(t) or has_ref or re.search(r"(?i)референс|из\s+реф", t):
        return True
    return False


def _look(
    config: Config,
    image: Path,
    *,
    as_self: bool,
    hint: str = "",
    character: Optional[str] = None,
) -> str:
    from .reference_vision import look_at_photo

    title = _TITLES.get(character or "", "")
    ok, text = look_at_photo(
        config,
        image,
        as_self=as_self,
        hint=hint,
        character_title=title,
    )
    return text if ok else f"(не разглядела: {text})"


def _analyze_ref(config: Config, image: Path, *, hint: str = "") -> str:
    try:
        from .reference_vision import describe_reference, format_reference_report

        desc = describe_reference(config, image, hint=hint or "Референс из чата с Деном.")
        return format_reference_report(desc)
    except Exception as exc:  # noqa: BLE001
        return f"Разбор не вышел: {exc}"


def _process_ref(
    config: Config, image: Path, *, character: Optional[str] = None
) -> Tuple[str, Optional[Path]]:
    out_dir = comfy_refs_dir(config) / "processed"
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    dest = out_dir / f"proc_{stamp}{image.suffix.lower() or '.png'}"
    try:
        shutil.copy2(image, dest)
    except OSError as exc:
        return f"Не скопировать кадр: {exc}", None

    bits = [f"Кадр для съёмки готов: {dest.name}"]
    if character:
        ok, msg = assign_character_ref(config, character, dest)
        bits.append(msg if ok else f"(привязка: {msg})")
    else:
        try:
            from .face_refs import stage_face_for_comfy

            ok_f, msg_f, _name = stage_face_for_comfy(config, dest)
            bits.append("Лицо подставила." if ok_f else msg_f)
        except Exception as exc:  # noqa: BLE001
            bits.append(str(exc))
    return "\n".join(bits), dest


def _scene_kind(text: str) -> str:
    if _wants_selfie(text):
        return "selfie"
    if _wants_fantasy(text):
        return "fantasy"
    return "scene"


def _shoot_action_for(config: Config, text: str, *, look_ru: str = "") -> str:
    from .reference_vision import build_scene_action_en

    look = look_ru or get_pending_look(config)
    return build_scene_action_en(
        kind=_scene_kind(text),
        user_text=text,
        look_ru=look,
        config=config,
    )


def _lora_list_message(config: Config) -> str:
    from .lora import format_lora_pick_message, scan_loras

    entries = scan_loras(config)
    if not entries:
        return "LoRA на диске не вижу. Кинь файлы в ComfyUI/models/loras — скажу номера."
    try:
        return format_lora_pick_message(entries)
    except Exception:
        lines = ["Какие LoRA? Напиши: лора: 1 или лора: none"]
        for e in entries[:40]:
            lines.append(f"{e.index}. {e.file}")
        return "\n".join(lines)


def _arm_lora_pick(config: Config) -> str:
    from ...lab.comfy_pipeline import COMFY_TOPIC
    from ...lab.session import load_session, save_session
    from .lora import scan_loras

    msg = _lora_list_message(config)
    session = load_session(config, COMFY_TOPIC)
    entries = scan_loras(config)
    if session is not None and entries:
        session.status = "awaiting_lora_pick"
        session.meta["lora_pick_offered"] = True
        save_session(config, session)
        return msg + "\nЖду номер — подхвачу в съёмку."
    return msg


def _maybe_look_and_store(
    config: Config,
    image: Path,
    *,
    body: str,
    cid: Optional[str],
) -> str:
    as_self = cid == "viu"
    if cid in ("shanya", "minotaur"):
        as_self = False
    elif cid is None and re.search(r"(?i)\b(?:ты|тебя|вью|себя)\b", body or ""):
        as_self = True
    text = _look(config, image, as_self=as_self, hint=body, character=cid)
    set_pending_ref(
        config,
        image,
        caption=body,
        look_text=text,
        pending_character=cid or get_pending_character(config) or "",
    )
    return text


def _shoot_confirm_message(text: str) -> str:
    from .reference_vision import extract_scene_wish

    wish = extract_scene_wish(text)
    if wish and len(wish) >= 6:
        preview = wish if len(wish) <= 120 else wish[:117] + "…"
        return f"Ок — делаю из рефа: {preview}\nПришлю, когда будет готово."
    return "Ок — делаю из рефа, как сказал. Пришлю, когда будет готово."


def try_handle_comfy_chat(config: Config, text: str) -> ChatFlowOutcome:
    """NL: посмотреть фото, запомнить целиком, сделать кадр по описанию."""
    raw = (text or "").strip()
    if not raw:
        return ChatFlowOutcome(False)

    if _LAB_SHORT_RE.match(raw) and not _TG_PHOTO_RE.match(raw):
        return ChatFlowOutcome(False)

    photo, caption = parse_tg_photo_payload(raw)
    body = caption if photo is not None else raw
    new_photo = photo is not None and photo.is_file()
    if new_photo:
        set_pending_ref(
            config,
            photo,
            caption=caption,
            pending_character=get_pending_character(config) or "",
        )

    pending = get_pending_ref(config)
    fresh = (photo if new_photo else None) or pending
    # Сохранённый реф — только для «сделай/нарисуй», не для голого «это ты».
    image = fresh
    if image is None and body and _wants_directed_shoot(body, config):
        image = character_image_path(config, "viu")

    if _STATUS_RE.search(body) and not new_photo:
        return ChatFlowOutcome(True, format_character_refs_status(config))

    cid = _resolve_assign_character(body) if body else None
    if not cid and new_photo:
        cid = get_pending_character(config)
    if cid and new_photo:
        clear_pending_character(config)

    directed = bool(body) and _wants_directed_shoot(body, config)

    # Текст «это ты / посмотри» без нового фото — ждать картинку (не reflect).
    if not new_photo and fresh is None and not directed:
        if cid or _wants_look(body):
            if cid:
                set_pending_character(config, cid, note=body)
                who = _TITLES.get(cid, "тебя")
                return ChatFlowOutcome(
                    True,
                    f"Кидай фото — посмотрю и запомню {who.lower()} целиком.",
                )
            return ChatFlowOutcome(True, "Кидай фото — посмотрю.")

    # --- Есть картинка (новая / pending / сохранённый реф для съёмки) ---
    if image is not None and image.is_file() and (new_photo or body):
        bits: List[str] = []
        media: List[Tuple[str, str]] = []
        look_text = ""

        if new_photo or _wants_look(body) or _wants_analyze(body) or cid:
            look_text = _maybe_look_and_store(config, image, body=body, cid=cid)
            if look_text:
                bits.append(look_text)

        if cid:
            _ok, msg = assign_character_ref(config, cid, image, notes=body[:200])
            bits.append(msg)

        if _wants_analyze(body) and not new_photo:
            bits.append(_analyze_ref(config, image, hint=body))

        if _wants_process(body) or directed:
            pmsg, pout = _process_ref(
                config,
                image,
                character=cid or ("viu" if directed else None),
            )
            # Не дублировать «запомнила», если уже assign выше
            if not cid:
                bits.append(pmsg)
            elif pout is not None:
                bits.append(f"Кадр для съёмки готов: {pout.name}")
            if pout is not None:
                media.append(("photo", str(pout)))

        start = False
        shoot_action = ""
        if directed:
            start = True
            shoot_action = _shoot_action_for(
                config, body, look_ru=look_text or get_pending_look(config)
            )
            bits.append(_shoot_confirm_message(body))

        if _wants_lora(body):
            bits.append(_arm_lora_pick(config))

        if new_photo and not cid and not (
            directed or _wants_lora(body) or _wants_process(body)
        ):
            bits.append("Если это я — скажи «это ты», запомню целиком.")

        if bits:
            return ChatFlowOutcome(
                True,
                "\n\n".join(bits),
                start_shoot=start,
                shoot_action=shoot_action,
                media_to_send=media,
            )

    if image is not None and image.is_file():
        if cid:
            look = _look(config, image, as_self=cid == "viu", hint=body, character=cid)
            set_pending_ref(config, image, caption=body, look_text=look)
            _ok, msg = assign_character_ref(config, cid, image, notes=body[:200])
            return ChatFlowOutcome(True, f"{look}\n\n{msg}" if look else msg)

        if _wants_look(body) or _wants_analyze(body):
            look = _look(
                config,
                image,
                as_self=bool(re.search(r"(?i)\b(?:ты|себя|вью)\b", body)),
                hint=body,
            )
            set_pending_ref(config, image, caption=body, look_text=look)
            return ChatFlowOutcome(True, look)

        if _wants_process(body):
            cid2 = resolve_character_id(body)
            pmsg, pout = _process_ref(config, image, character=cid2)
            media = [("photo", str(pout))] if pout else []
            return ChatFlowOutcome(True, pmsg, media_to_send=media)

        if directed:
            _process_ref(config, image, character="viu")
            action = _shoot_action_for(config, body)
            return ChatFlowOutcome(
                True,
                _shoot_confirm_message(body),
                start_shoot=True,
                shoot_action=action,
            )

    if _wants_lora(body):
        return ChatFlowOutcome(True, _arm_lora_pick(config))

    if directed:
        action = _shoot_action_for(config, body)
        return ChatFlowOutcome(
            True,
            _shoot_confirm_message(body),
            start_shoot=True,
            shoot_action=action,
        )

    # Comfy без явной сцены — коротко, по-человечески
    if mentions_comfy(body):
        return ChatFlowOutcome(
            True,
            "Скажи кадр своими словами — например «нарисуй себя в кресле» "
            "или кинь реф и «это ты». Я сделаю из рефа и пришлю.",
        )

    return ChatFlowOutcome(False)


def send_media_to_telegram(
    config: Config, kind: str, path: str | Path, *, caption: str = ""
) -> bool:
    """Отправить фото/видео владельцу (без GUI)."""
    from ..telegram import settings as tg_settings
    from ..telegram.client import TelegramClient, TelegramError

    if not tg_settings.enabled(config):
        return False
    token = tg_settings.token(config)
    chat_id = tg_settings.chat_id(config)
    if not token or chat_id is None:
        return False
    try:
        client = TelegramClient(token)
        if kind == "video":
            client.send_video(chat_id, path, caption=caption)
        else:
            client.send_photo(chat_id, path, caption=caption)
        return True
    except TelegramError:
        return False
