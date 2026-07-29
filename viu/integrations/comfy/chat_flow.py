"""Чат-оркестратор Comfy: рефы, разбор, LoRA, видео — без имён тулов."""

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
    r"(?:это|вот\s+это|смотри)\s+(?P<a>ты|тебя|вью|вьюшка|шаня|шанька|минотавр|мино|бык)\b|"
    r"так\s+выгляд(?:ишь|ит)\s+(?P<b>ты|вью|шаня|минотавр)\b|"
    r"(?P<c>ты|вью|шаня|минотавр)\s*[—\-–:,]\s*(?:вот|так|реф)|"
    r"реф(?:еренс)?\s+(?:для\s+)?(?P<d>тебя|вью|шани|минотавра)\b|"
    r"вот\s+референс.{0,40}(?P<e>ты|вью|шаня|минотавр)\b"
    r")"
)

_ANALYZE_RE = re.compile(
    r"(?i)(?:разбер|анализ|проанализ|что\s+на\s+(?:этой\s+)?(?:картинк|фото|реф)|"
    r"опиши\s+(?:реф|картинк|фото)|разбор\s+реф)"
)

_PROCESS_RE = re.compile(
    r"(?i)(?:обработай|обработать|создай\s+из\s+референс|прогони\s+реф|"
    r"подготовь\s+(?:реф|картинк|фото)|сделай\s+обработан)"
)

_LORA_RE = re.compile(
    r"(?i)(?:подгруз|загруз|включи|выбер|постав).{0,24}(?:лор[ауы]?|lora)|"
    r"(?:лор[ауы]?|lora).{0,24}(?:подгруз|загруз|включи|выбер|список|какие)|"
    r"^\s*(?:лор[ауы]?|lora)\s*$"
)

_VIDEO_RE = re.compile(
    r"(?i)(?:сделай|сними|создай|сгенер|запусти).{0,40}(?:видео|клип|ролик)|"
    r"(?:видео|клип).{0,40}(?:comfy|комфи)|"
    r"(?:comfy|комфи).{0,40}(?:видео|клип|сними|снять|сгенер)"
)

_STATUS_RE = re.compile(
    r"(?i)(?:какие\s+реф|референсы\s+персонаж|кто\s+на\s+реф|"
    r"покажи\s+реф(?:ы|еренсы)?\s+персонаж|статус\s+реф)"
)

_LAB_SHORT_RE = re.compile(
    r"^\s*(?:ок|ok|да|yes|approve|нет|no|стоп|stop|отмена|"
    r"lora\s*:|лора\s*:|лучший\s*:|правк)",
    re.IGNORECASE,
)


@dataclass
class ChatFlowOutcome:
    handled: bool
    message: str = ""
    start_shoot: bool = False
    media_to_send: List[Tuple[str, str]] = field(default_factory=list)
    # ("photo"|"video", path)


def _pending_path(config: Config) -> Path:
    return Path(config.data_dir) / "comfy_chat_pending.json"


def set_pending_ref(config: Config, path: str | Path, *, caption: str = "") -> None:
    payload = {
        "path": str(Path(path).resolve()),
        "caption": (caption or "").strip()[:500],
        "at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    dest = _pending_path(config)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def get_pending_ref(config: Config) -> Optional[Path]:
    path = _pending_path(config)
    if not path.is_file():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    p = Path(str((raw or {}).get("path") or ""))
    return p if p.is_file() else None


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
        # fallback: resolve_character_id на фразах вида «это Шаня»
        if re.search(r"(?i)\b(?:это|вот|реф|выгляд)", text or ""):
            return resolve_character_id(text or "")
        return None
    token = next((g for g in m.groups() if g), None) or ""
    return resolve_character_id(token) or resolve_character_id(text or "")


def _wants_analyze(text: str) -> bool:
    return bool(_ANALYZE_RE.search(text or ""))


def _wants_process(text: str) -> bool:
    return bool(_PROCESS_RE.search(text or ""))


def _wants_lora(text: str) -> bool:
    return bool(_LORA_RE.search(text or ""))


def _wants_video(text: str, config: Config) -> bool:
    if looks_like_comfy_job_request(text or ""):
        return True
    if not _VIDEO_RE.search(text or ""):
        return False
    if mentions_comfy(text or ""):
        return True
    if get_pending_ref(config) is not None:
        return True
    if re.search(r"(?i)референс|из\s+реф", text or ""):
        return True
    return False


def _analyze_ref(config: Config, image: Path, *, hint: str = "") -> str:
    try:
        from .reference_vision import describe_reference, format_reference_report

        desc = describe_reference(config, image, hint=hint or "Референс из чата с Деном.")
        return format_reference_report(desc)
    except Exception as exc:  # noqa: BLE001
        return f"Разбор не вышел: {exc}"


def _process_ref(config: Config, image: Path, *, character: Optional[str] = None) -> Tuple[str, Optional[Path]]:
    """Скопировать в Lab/Refs/processed и при нужде в FaceRefs."""
    out_dir = comfy_refs_dir(config) / "processed"
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    dest = out_dir / f"proc_{stamp}{image.suffix.lower() or '.png'}"
    try:
        shutil.copy2(image, dest)
    except OSError as exc:
        return f"Не скопировать обработанный кадр: {exc}", None

    bits = [f"Готово — обработанный кадр лежит у меня: {dest.name}"]
    if character:
        ok, msg = assign_character_ref(config, character, dest)
        bits.append(msg if ok else f"(привязка: {msg})")
    else:
        try:
            from .face_refs import stage_face_for_comfy

            ok_f, msg_f, _name = stage_face_for_comfy(config, dest)
            if ok_f:
                bits.append("Лицо подставила для съёмки.")
            else:
                bits.append(msg_f)
        except Exception as exc:  # noqa: BLE001
            bits.append(f"FaceRefs: {exc}")
    return "\n".join(bits), dest


def _lora_list_message(config: Config) -> str:
    from .lora import format_lora_pick_message, scan_loras

    entries = scan_loras(config)
    if not entries:
        return (
            "LoRA на диске не вижу (ComfyUI/models/loras).\n"
            "Кинь файлы туда — скажу номера, что подгрузить."
        )
    try:
        return format_lora_pick_message(entries)
    except Exception:
        lines = ["Какие LoRA подгрузить? Напиши: лора: 1 или лора: 1,3 или лора: none"]
        for e in entries[:40]:
            lines.append(f"{e.index}. {e.file}" + (f" [{e.subfolder}]" if e.subfolder else ""))
        return "\n".join(lines)


def _arm_lora_pick(config: Config) -> str:
    """Если lab-сессия жива — перевести в awaiting_lora_pick; иначе просто список."""
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
        return msg + "\nЖду номер — подхвачу в текущую съёмку."
    return msg


def try_handle_comfy_chat(config: Config, text: str) -> ChatFlowOutcome:
    """NL-вход для рефов / разбора / LoRA / видео. Без имён тулов в ответах."""
    raw = (text or "").strip()
    if not raw:
        return ChatFlowOutcome(False)

    # Не перехватывать короткие ответы lab (ок / лора: 1 / лучший: …).
    if _LAB_SHORT_RE.match(raw) and not _TG_PHOTO_RE.match(raw):
        return ChatFlowOutcome(False)

    photo, caption = parse_tg_photo_payload(raw)
    body = caption if photo is not None else raw
    if photo is not None and photo.is_file():
        set_pending_ref(config, photo, caption=caption)

    pending = get_pending_ref(config)
    image = photo if (photo is not None and photo.is_file()) else pending

    # Статус рефов
    if _STATUS_RE.search(body) and photo is None:
        return ChatFlowOutcome(True, format_character_refs_status(config))

    # Привязка персонажа
    cid = _resolve_assign_character(body) if body else None
    if cid and image is not None and image.is_file():
        ok, msg = assign_character_ref(config, cid, image, notes=body[:200])
        bits = [msg]
        media: List[Tuple[str, str]] = [("photo", str(image))]
        if _wants_analyze(body) or (photo is not None and not _wants_process(body) and not _wants_video(body, config)):
            # при новой фотке с подписью «это ты» — короткий разбор по желанию
            if _wants_analyze(body):
                bits.append(_analyze_ref(config, image, hint=body))
        if _wants_process(body):
            pmsg, pout = _process_ref(config, image, character=cid)
            bits.append(pmsg)
            if pout is not None:
                media.append(("photo", str(pout)))
        start = _wants_video(body, config)
        if start:
            bits.append("Ок, запускаю съёмку — клип пришлю сюда, когда будет.")
        if ok:
            # оставляем pending — удобно для «теперь видео»
            pass
        return ChatFlowOutcome(
            True,
            "\n".join(bits),
            start_shoot=start,
            media_to_send=media if photo is not None else [],
        )

    # Новое фото без явной привязки
    if photo is not None and photo.is_file():
        bits = [
            "Фото приняла.",
            "Скажи, кто это: ты (Вью), Шаня или минотавр — запомню.",
        ]
        if _wants_analyze(body) or not body:
            # лёгкий разбор, если просят или просто кинули
            if _wants_analyze(body):
                bits.append(_analyze_ref(config, photo, hint=body))
        if cid is None and body and resolve_character_id(body) and _ASSIGN_RE.search(body):
            pass  # уже выше
        if _wants_process(body):
            pmsg, pout = _process_ref(config, photo)
            bits.append(pmsg)
            media = [("photo", str(pout))] if pout else []
            return ChatFlowOutcome(True, "\n".join(bits), media_to_send=media)
        if _wants_video(body, config):
            bits.append("Запускаю съёмку с этим кадром — пришлю клип.")
            return ChatFlowOutcome(True, "\n".join(bits), start_shoot=True)
        if _wants_lora(body):
            bits.append(_arm_lora_pick(config))
            return ChatFlowOutcome(True, "\n".join(bits))
        # просто фото — спросить кого
        if not body or len(body) < 80:
            return ChatFlowOutcome(True, "\n".join(bits))
        # длинная подпись без assign — не перехватывать весь reflect
        if not (_wants_analyze(body) or _wants_process(body) or _wants_lora(body) or _wants_video(body, config)):
            return ChatFlowOutcome(True, "\n".join(bits))

    # Текст без нового фото
    if image is not None and image.is_file() and cid and _resolve_assign_character(body):
        ok, msg = assign_character_ref(config, cid, image, notes=body[:200])
        return ChatFlowOutcome(True, msg)

    if image is not None and image.is_file() and _wants_analyze(body):
        return ChatFlowOutcome(True, _analyze_ref(config, image, hint=body))

    if image is not None and image.is_file() and _wants_process(body):
        cid2 = resolve_character_id(body)
        pmsg, pout = _process_ref(config, image, character=cid2)
        media = [("photo", str(pout))] if pout else []
        return ChatFlowOutcome(True, pmsg, media_to_send=media)

    if _wants_lora(body):
        return ChatFlowOutcome(True, _arm_lora_pick(config))

    if _wants_video(body, config):
        extra = ""
        if image is not None and image.is_file():
            extra = "\nРеф на месте — снимаю от него."
        return ChatFlowOutcome(
            True,
            "Ок, кручу съёмку. Клип пришлю в Telegram, когда будет готов." + extra,
            start_shoot=True,
        )

    # Явный Comfy без job — подсказать, что можно в чате
    if mentions_comfy(body) and not looks_like_comfy_job_request(body):
        return ChatFlowOutcome(
            True,
            "Могу в чате: разобрать реф, запомнить «это я / Шаня / минотавр», "
            "подгрузить LoRA, снять видео и прислать тебе.\n"
            "Кинь фото или скажи, что сделать.",
        )

    return ChatFlowOutcome(False)


def send_media_to_telegram(config: Config, kind: str, path: str | Path, *, caption: str = "") -> bool:
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
