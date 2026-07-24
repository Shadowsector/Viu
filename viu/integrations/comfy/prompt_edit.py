"""Просмотр и применение черновика Comfy MoCap (чат, tool, GUI)."""

from __future__ import annotations

import re
from typing import Any, Dict, Tuple

from ...config import Config
from ...lab.comfy_pipeline import COMFY_TOPIC, apply_prompt_decision, read_action_from_task
from ...lab.session import append_journal, load_session, save_session
from .angles import THREE_QUARTER
from .prompts import draft_bundle, mocap_negative, mocap_prompt, mocap_take_count

_TELEGRAM_PREFIX_RE = re.compile(r"^\s*\[telegram\]\s*", re.IGNORECASE)

_SHOW_STRICT_RE = re.compile(
    r"^\s*(?:comfy_prompt|промпт\s*comfy|покажи\s+промпт|промпт\s*mocap|wan\s*промпт)\s*[.!…]?\s*$",
    re.IGNORECASE,
)
_SHOW_LOOSE_RE = re.compile(
    r"^\s*(?:покажи|show|что\s+за|какой)\s+(?:wan\s+|comfy\s+|mocap\s+)?промпт",
    re.IGNORECASE,
)
_APPLY_PREFIX_RE = re.compile(
    r"^\s*(?:промпт\+|comfy_prompt_apply|применить\s+промпт|отправь\s+промпт)\s*[:\-–]\s*",
    re.IGNORECASE,
)

_WAN_POS_MARK = "--- POSITIVE (в ComfyUI / Wan) ---"
_WAN_NEG_MARK = "--- NEGATIVE ---"
_WAN_ACT_MARK = "--- ДЕЙСТВИЕ (EN) ---"


def _normalize_user_text(text: str) -> str:
    raw = (text or "").strip()
    raw = _TELEGRAM_PREFIX_RE.sub("", raw).strip()
    return raw


def current_action(config: Config) -> str:
    session = load_session(config, COMFY_TOPIC)
    if session is not None:
        for key in ("approved_action", "action"):
            val = str((session.meta or {}).get(key) or "").strip()
            if val:
                return val
    return read_action_from_task(config).strip() or "idle stand"


def resolved_wan_lines(config: Config) -> Tuple[str, str, str]:
    """То, что реально уходит в Wan (positive для ¾ + negative + EN action)."""
    session = load_session(config, COMFY_TOPIC)
    action = current_action(config)
    pos_ov = ""
    neg_ov = ""
    if session is not None:
        pos_ov = str((session.meta or {}).get("wan_positive") or "").strip()
        neg_ov = str((session.meta or {}).get("wan_negative") or "").strip()
    angle = THREE_QUARTER
    from .angles import MOCAP_TAKES

    sample_angle = MOCAP_TAKES[0]
    positive = pos_ov or mocap_prompt(action, sample_angle)
    negative = neg_ov or mocap_negative()
    return action, positive, negative


def format_wan_editor_text(config: Config) -> str:
    """Редактируемый текст: только строки Wan, без «сценария режиссёра»."""
    action, positive, negative = resolved_wan_lines(config)
    session = load_session(config, COMFY_TOPIC)
    slug = ""
    st = ""
    if session is not None:
        slug = str(session.meta.get("catalog_slug") or "").strip()
        st = str(session.status or "")
    head = "Это текст для ComfyUI (Wan), не описание сцены из каталога.\n"
    if slug or st:
        head += f"(lab: {slug or '—'}, статус: {st or '—'})\n"
    return (
        f"{head}\n"
        f"{_WAN_POS_MARK}\n"
        f"{positive}\n\n"
        f"{_WAN_NEG_MARK}\n"
        f"{negative}\n\n"
        f"{_WAN_ACT_MARK}\n"
        f"{action}\n"
    )


def prompt_draft_text(config: Config) -> str:
    """Полный bundle (Telegram-черновик) — для совместимости."""
    session = load_session(config, COMFY_TOPIC)
    if session is not None:
        draft = str((session.meta or {}).get("draft") or "").strip()
        if draft and _WAN_POS_MARK not in draft:
            return draft
        action = str((session.meta or {}).get("action") or "").strip()
        if action and not draft:
            return draft_bundle(action)
    return draft_bundle(current_action(config))


def show_prompt_message(config: Config, *, for_telegram: bool = False) -> str:
    body = format_wan_editor_text(config)
    if for_telegram:
        return (
            body
            + "\n\nПравка: ответь блоком с теми же --- POSITIVE --- / NEGATIVE / ДЕЙСТВИЕ "
            "или «промпт+:» + текст. GUI: кнопка «Промпт Wan → Comfy»."
        )
    return body + prompt_help_footer()


def parse_wan_editor_text(text: str) -> Dict[str, str]:
    raw = (text or "").strip()
    out: Dict[str, str] = {"action": "", "positive": "", "negative": "", "raw": raw}
    if _WAN_POS_MARK in raw:
        m_pos = re.search(
            re.escape(_WAN_POS_MARK) + r"\s*\n(.+?)(?=\n--- NEGATIVE ---|\Z)",
            raw,
            re.DOTALL,
        )
        if m_pos:
            out["positive"] = m_pos.group(1).strip()
        m_neg = re.search(
            re.escape(_WAN_NEG_MARK) + r"\s*\n(.+?)(?=\n--- ДЕЙСТВИЕ|\Z)",
            raw,
            re.DOTALL,
        )
        if m_neg:
            out["negative"] = m_neg.group(1).strip()
        m_act = re.search(
            re.escape(_WAN_ACT_MARK) + r"\s*\n(.+?)(?:\n\n|\Z)",
            raw,
            re.DOTALL,
        )
        if m_act:
            out["action"] = m_act.group(1).strip().split("\n")[0].strip()
        return out
    return parse_edited_draft(raw)


def parse_edited_draft(text: str) -> Dict[str, str]:
    """Разобрать старый bundle (Действие / Промпт / Negative)."""
    raw = (text or "").strip()
    out: Dict[str, str] = {"action": "", "positive": "", "negative": "", "raw": raw}
    if not raw:
        return out

    m_action = re.search(r"^Действие:\s*(.+)$", raw, re.MULTILINE | re.IGNORECASE)
    if m_action:
        out["action"] = m_action.group(1).strip()

    m_pos = re.search(
        r"Промпт\s*\([^)]*\)\s*:\s*\n(.+?)(?:\n\nКадр:|\n\nНе добавляй:|\n\nNegative:|\Z)",
        raw,
        re.DOTALL | re.IGNORECASE,
    )
    if m_pos:
        out["positive"] = m_pos.group(1).strip().replace("\n", " ")

    m_neg = re.search(r"^Negative:\s*\n?(.+?)(?:\n\n|\Z)", raw, re.DOTALL | re.IGNORECASE | re.MULTILINE)
    if m_neg:
        out["negative"] = m_neg.group(1).strip().replace("\n", " ")

    if not out["action"] and not out["positive"] and "\n" not in raw and len(raw) < 120:
        out["action"] = raw
    elif not out["action"] and not out["positive"]:
        out["positive"] = raw.replace("\n", " ").strip()

    return out


def apply_draft_to_session(
    config: Config,
    session: Any,
    text: str,
    *,
    rebuild_draft: bool = True,
) -> Tuple[bool, str]:
    parsed = parse_wan_editor_text(text)
    action = parsed.get("action") or str(session.meta.get("action") or "").strip()
    positive = parsed.get("positive") or ""
    negative = parsed.get("negative") or ""

    if action:
        session.meta["action"] = action
        session.meta["approved_action"] = action
    if positive:
        session.meta["wan_positive"] = positive
    else:
        session.meta.pop("wan_positive", None)
    if negative:
        session.meta["wan_negative"] = negative
    else:
        session.meta.pop("wan_negative", None)

    session.meta["draft"] = (text or "").strip() or draft_bundle(action or current_action(config))
    if rebuild_draft and _WAN_POS_MARK not in (text or ""):
        base_action = action or current_action(config)
        session.meta["draft"] = draft_bundle(base_action)

    save_session(config, session)
    append_journal(
        config,
        COMFY_TOPIC,
        f"### Промпт Wan (редактирование)\n\n{session.meta.get('draft', '')[:4000]}",
    )
    _, pos_show, _ = resolved_wan_lines(config)
    lines = [
        "Промпт для Comfy сохранён — подхвачу на следующей генерации (и при текущей, если ещё не сняли).",
        f"Действие: {(action or session.meta.get('action') or '')[:100]}",
        f"Positive: {pos_show[:200]}{'…' if len(pos_show) > 200 else ''}",
    ]
    if negative:
        lines.append("Negative: обновлён.")
    lines.append(f"Дублей ¾: {mocap_take_count()}.")
    return True, "\n".join(lines)


def apply_draft_text(
    config: Config,
    text: str,
    *,
    approve: bool = False,
) -> Tuple[bool, str]:
    session = load_session(config, COMFY_TOPIC)
    if session is None:
        from ...lab.session import new_session

        session = new_session(COMFY_TOPIC)
        session.meta["action"] = current_action(config)
        save_session(config, session)

    ok, msg = apply_draft_to_session(config, session, text)
    if not approve:
        return ok, msg

    session = load_session(config, COMFY_TOPIC) or session
    if session.status == "awaiting_prompt":
        tail = apply_prompt_decision(
            config,
            session,
            "approve",
            str(session.meta.get("approved_action") or session.meta.get("action") or ""),
        )
        return True, msg + "\n\n" + tail
    return ok, msg


def prompt_help_footer() -> str:
    n = mocap_take_count()
    return (
        f"\n\n---\n"
        f"GUI: «Промпт Wan → Comfy» — правка и «Отправить в Comfy».\n"
        f"Telegram/чат: `промпт+: …` или блок с --- POSITIVE ---.\n"
        f"`comfy_prompt approve=1` — сохранить и начать съёмку ({n} дублей ¾)."
    )


def is_prompt_show_request(text: str) -> bool:
    raw = _normalize_user_text(text)
    if not raw:
        return False
    if _SHOW_STRICT_RE.match(raw):
        return True
    if _SHOW_LOOSE_RE.match(raw):
        return True
    low = raw.lower()
    if "промпт" in low and any(w in low for w in ("покажи", "show", "что за", "какой", "wan", "comfy")):
        if "сценари" not in low and "граф" not in low:
            return True
    return False


def try_handle_comfy_prompt_chat(
    config: Config, text: str, *, for_telegram: bool = False
) -> Tuple[bool, str]:
    raw = _normalize_user_text(text)
    if not raw:
        return False, ""
    if is_prompt_show_request(raw):
        return True, show_prompt_message(config, for_telegram=for_telegram)
    if _APPLY_PREFIX_RE.match(raw):
        body = _APPLY_PREFIX_RE.sub("", raw).strip()
        if not body:
            return True, "После «промпт+:» вставь блок --- POSITIVE --- или строку действия."
        _, msg = apply_draft_text(config, body, approve=False)
        return True, msg
    if _WAN_POS_MARK in raw or _WAN_NEG_MARK in raw:
        _, msg = apply_draft_text(config, raw, approve=False)
        return True, msg
    return False, ""
