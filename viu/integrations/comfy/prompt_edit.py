"""Просмотр и применение черновика Comfy MoCap (чат, tool, GUI)."""

from __future__ import annotations

import re
from typing import Any, Dict, Optional, Tuple

from ...config import Config
from ...lab.comfy_pipeline import COMFY_TOPIC, apply_prompt_decision, read_action_from_task
from ...lab.session import append_journal, load_session, save_session
from .prompts import draft_bundle, mocap_take_count

_SHOW_RE = re.compile(
    r"^\s*(?:comfy_prompt|промпт\s*comfy|покажи\s+промпт|промпт\s*mocap|wan\s*промпт)\s*[.!…]?\s*$",
    re.IGNORECASE,
)
_APPLY_PREFIX_RE = re.compile(
    r"^\s*(?:промпт\+|comfy_prompt_apply|применить\s+промпт)\s*[:\-–]\s*",
    re.IGNORECASE,
)


def current_action(config: Config) -> str:
    session = load_session(config, COMFY_TOPIC)
    if session is not None:
        for key in ("approved_action", "action"):
            val = str((session.meta or {}).get(key) or "").strip()
            if val:
                return val
    return read_action_from_task(config).strip() or "idle stand"


def prompt_draft_text(config: Config) -> str:
    session = load_session(config, COMFY_TOPIC)
    if session is not None:
        draft = str((session.meta or {}).get("draft") or "").strip()
        if draft:
            return draft
        action = str((session.meta or {}).get("action") or "").strip()
        if action:
            return draft_bundle(action)
    return draft_bundle(current_action(config))


def parse_edited_draft(text: str) -> Dict[str, str]:
    """Разобрать отредактированный bundle (Действие / Промпт / Negative)."""
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
    parsed = parse_edited_draft(text)
    action = parsed.get("action") or str(session.meta.get("action") or "").strip()
    positive = parsed.get("positive") or ""
    negative = parsed.get("negative") or ""

    if action:
        session.meta["action"] = action
    if positive:
        session.meta["wan_positive"] = positive
    else:
        session.meta.pop("wan_positive", None)
    if negative:
        session.meta["wan_negative"] = negative
    else:
        session.meta.pop("wan_negative", None)

    if rebuild_draft:
        base_action = action or current_action(config)
        session.meta["draft"] = draft_bundle(base_action)
        if positive or negative:
            session.meta["draft"] = (text or "").strip() or session.meta["draft"]

    save_session(config, session)
    append_journal(config, COMFY_TOPIC, f"### Промпт (редактирование)\n\n{session.meta.get('draft', '')[:4000]}")
    lines = [
        "Черновик сохранён.",
        f"Действие: {(action or session.meta.get('action') or '')[:100]}",
    ]
    if positive:
        lines.append(f"Wan positive (override): {positive[:160]}…" if len(positive) > 160 else f"Wan positive: {positive}")
    if negative:
        lines.append("Negative: переопределён.")
    lines.append(
        f"Дальше: «ок» / comfy_prompt approve=1 — съёмка · {mocap_take_count()} дублей ¾."
    )
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
    return ok, msg + "\n\nПромпт в сессии — при следующей генерации подхвачу override."


def prompt_help_footer() -> str:
    n = mocap_take_count()
    return (
        f"\n\n---\n"
        f"Редактировать:\n"
        f"• GUI — «Промпт MoCap»\n"
        f"• `comfy_prompt apply=1` + текст в `text=` (или `промпт+: …` в чате)\n"
        f"• коротко: `правки: sit_down` на шаге одобрения\n"
        f"• `comfy_prompt approve=1` — сохранить и снять ({n} дублей ¾)\n"
        f"• `comfy_prompt show=1` — снова показать"
    )


def try_handle_comfy_prompt_chat(config: Config, text: str) -> Tuple[bool, str]:
    raw = (text or "").strip()
    if not raw:
        return False, ""
    if _SHOW_RE.match(raw):
        return True, prompt_draft_text(config) + prompt_help_footer()
    if _APPLY_PREFIX_RE.match(raw):
        body = _APPLY_PREFIX_RE.sub("", raw).strip()
        if not body:
            return True, "После «промпт+:» вставь текст черновика или одну строку действия."
        _, msg = apply_draft_text(config, body, approve=False)
        return True, msg
    return False, ""
