"""После 10 kept на действие — пауза и выбор следующей сцены в Telegram."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ...config import Config
from ...lab.comfy_director import BARN_SHED_CYCLE
from ..telegram import settings as tg_settings
from ..telegram.client import TelegramClient, TelegramError
from .naming import kept_count_for_slug, max_clips_per_action, slug_at_quota

_SCENE_PRESETS: List[Dict[str, Any]] = [
    {
        "id": "sit_chair",
        "title": "Стул и посадка",
        "desc": "сесть, сидеть, встать — стул/ящик у сарая",
        "slugs": ["sit_down", "sit_idle", "stand_up"],
    },
    {
        "id": "sleep_bed",
        "title": "Кровать и сон",
        "desc": "лечь, спать, встать с коврика/кровати",
        "slugs": ["lie_down", "sleep_idle", "get_up"],
    },
    {
        "id": "explore_props",
        "title": "Осмотр и предметы",
        "desc": "оглядеться, окно, поднять предмет, облокотиться",
        "slugs": ["look_around", "look_window", "take", "lean"],
    },
    {
        "id": "walk_floor",
        "title": "Ходьба по полу",
        "desc": "шаг, отступление, базовый idle-loop",
        "slugs": ["walk", "walk_back", "idle"],
    },
    {
        "id": "table_food",
        "title": "Стол: еда и питьё",
        "desc": "есть стоя/сидя, пить из кружки",
        "slugs": ["eat", "drink"],
    },
    {
        "id": "private_shed",
        "title": "Приват в сарае",
        "desc": "одиночная интимная сцена (Instance)",
        "slugs": ["touch_self"],
    },
]


@dataclass
class SceneProposal:
    title: str
    description: str
    slugs: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return {"title": self.title, "description": self.description, "slugs": list(self.slugs)}

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "SceneProposal":
        return SceneProposal(
            title=str(d.get("title") or ""),
            description=str(d.get("description") or ""),
            slugs=[str(x) for x in (d.get("slugs") or [])],
        )


@dataclass
class ComfySceneState:
    awaiting_choice: bool = False
    completed_slug: str = ""
    completed_title: str = ""
    proposals: List[SceneProposal] = field(default_factory=list)
    focus_slugs: List[str] = field(default_factory=list)
    custom_notes: str = ""
    last_notified_slug: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "awaiting_choice": self.awaiting_choice,
            "completed_slug": self.completed_slug,
            "completed_title": self.completed_title,
            "proposals": [p.to_dict() for p in self.proposals],
            "focus_slugs": list(self.focus_slugs),
            "custom_notes": self.custom_notes,
            "last_notified_slug": self.last_notified_slug,
        }

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "ComfySceneState":
        return ComfySceneState(
            awaiting_choice=bool(d.get("awaiting_choice")),
            completed_slug=str(d.get("completed_slug") or ""),
            completed_title=str(d.get("completed_title") or ""),
            proposals=[SceneProposal.from_dict(x) for x in (d.get("proposals") or []) if isinstance(x, dict)],
            focus_slugs=[str(x) for x in (d.get("focus_slugs") or [])],
            custom_notes=str(d.get("custom_notes") or ""),
            last_notified_slug=str(d.get("last_notified_slug") or ""),
        )


def scene_state_path(config: Config) -> Path:
    return config.data_dir / "comfy_scene_state.json"


def load_scene_state(config: Config) -> ComfySceneState:
    from .focus import _default_focus_slugs, maybe_migrate_focus_from_env

    maybe_migrate_focus_from_env(config)
    path = scene_state_path(config)
    if not path.is_file():
        st = ComfySceneState(focus_slugs=_default_focus_slugs(config))
        save_scene_state(config, st)
        return st
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        st = ComfySceneState.from_dict(data)
        if not st.focus_slugs:
            st.focus_slugs = _default_focus_slugs(config)
        return st
    except (OSError, json.JSONDecodeError):
        return ComfySceneState(focus_slugs=_default_focus_slugs(config))


def save_scene_state(config: Config, state: ComfySceneState) -> None:
    path = scene_state_path(config)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state.to_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def is_paused_for_scene_choice(config: Config) -> bool:
    return load_scene_state(config).awaiting_choice


def get_focus_slugs(config: Config) -> List[str]:
    from .focus import resolve_focus_slugs

    return resolve_focus_slugs(config)


def _slug_title(slug: str) -> str:
    return slug.replace("_", " ")


def _pick_proposals(config: Config, completed_slug: str, *, limit: int = 3) -> List[SceneProposal]:
    """Три сцены, где ещё есть дыры по лимиту."""
    out: List[SceneProposal] = []
    for preset in _SCENE_PRESETS:
        slugs = [s for s in preset["slugs"] if not slug_at_quota(config, s)]
        if not slugs:
            continue
        if completed_slug and completed_slug in slugs and len(slugs) == 1:
            continue
        out.append(
            SceneProposal(
                title=str(preset["title"]),
                description=str(preset["desc"]),
                slugs=slugs,
            )
        )
    if len(out) >= limit:
        return out[:limit]
    # добор: одиночные действия из цикла сарая
    for slug in BARN_SHED_CYCLE:
        if slug_at_quota(config, slug) or slug == completed_slug:
            continue
        if any(slug in p.slugs for p in out):
            continue
        out.append(
            SceneProposal(
                title=_slug_title(slug),
                description=f"добить движение `{slug}` до {max_clips_per_action()} kept",
                slugs=[slug],
            )
        )
        if len(out) >= limit:
            break
    return out[:limit]


def format_scene_choice_message(state: ComfySceneState) -> str:
    title = state.completed_title or _slug_title(state.completed_slug)
    lines = [
        f"✅ Закончила цикл «{title}» ({max_clips_per_action()} kept-клипов).",
        "",
        "Что снимать дальше? Ответь цифрой или своим текстом:",
    ]
    for i, p in enumerate(state.proposals[:3], start=1):
        slugs = ", ".join(p.slugs)
        lines.append(f"{i}. {p.title} — {p.description} [{slugs}]")
    lines.extend(
        [
            "",
            "Примеры ответа:",
            "• `2` — вариант 2",
            "• `2 только без drink` — вариант 2 с уточнением",
            "• `давай lean и look_window, покороче` — свой вариант",
            "",
            "Пока не ответишь — новые генерации на паузе.",
        ]
    )
    return "\n".join(lines)


def send_scene_choice_telegram(config: Config, state: ComfySceneState) -> Tuple[bool, str]:
    body = format_scene_choice_message(state)
    if not tg_settings.enabled(config):
        return False, body
    token = tg_settings.token(config)
    chat_id = tg_settings.chat_id(config)
    if not token or chat_id is None:
        return False, body
    try:
        TelegramClient(token).send_message(chat_id, body)
        return True, "Вопрос о следующей сцене ушёл в Telegram."
    except TelegramError as exc:
        return False, f"Telegram: {exc}\n\n{body}"


def on_action_quota_reached(config: Config, slug: str, *, title_ru: str = "") -> Optional[str]:
    """Вызвать когда kept по slug достиг лимита. Возвращает сообщение для чата."""
    if not slug_at_quota(config, slug):
        return None
    state = load_scene_state(config)
    if state.awaiting_choice or state.last_notified_slug == slug:
        return None
    proposals = _pick_proposals(config, slug)
    if not proposals:
        state.last_notified_slug = slug
        save_scene_state(config, state)
        return f"«{slug}» набрал {max_clips_per_action()} kept — других сцен с дырами не осталось."
    state.awaiting_choice = True
    state.completed_slug = slug
    state.completed_title = title_ru or _slug_title(slug)
    state.proposals = proposals[:3]
    state.last_notified_slug = slug
    save_scene_state(config, state)
    sent, msg = send_scene_choice_telegram(config, state)
    preview = format_scene_choice_message(state)
    if sent:
        return f"⏸ Пауза после «{state.completed_title}». {msg}"
    return f"⏸ Пауза после «{state.completed_title}».\n{preview}"


_CHOICE_NUM_RE = re.compile(r"^\s*(\d)\s*(?:[.\):\-–]\s*)?(.*)$", re.S)


def parse_scene_choice_reply(text: str) -> Tuple[str, Dict[str, Any]]:
    """decision: pick|custom|unknown."""
    raw = (text or "").strip()
    if not raw:
        return "unknown", {}
    m = _CHOICE_NUM_RE.match(raw)
    if m:
        idx = int(m.group(1))
        notes = (m.group(2) or "").strip()
        if 1 <= idx <= 3:
            return "pick", {"index": idx, "notes": notes}
    if len(raw) >= 4:
        return "custom", {"text": raw}
    return "unknown", {}


def apply_scene_choice(
    config: Config,
    decision: str,
    payload: Dict[str, Any],
) -> str:
    state = load_scene_state(config)
    if not state.awaiting_choice:
        return "Сейчас выбор сцены не ждётся."

    if decision == "pick":
        idx = int(payload.get("index") or 0) - 1
        notes = str(payload.get("notes") or "").strip()
        if idx < 0 or idx >= len(state.proposals):
            return f"Нет варианта {idx + 1}. Ответь 1–{len(state.proposals)}."
        pick = state.proposals[idx]
        state.focus_slugs = list(pick.slugs)
        state.custom_notes = notes
        state.awaiting_choice = False
        state.completed_slug = ""
        save_scene_state(config, state)
        slugs = ", ".join(pick.slugs)
        extra = f" Уточнение: {notes}" if notes else ""
        return f"Ок, снимаю дальше: {pick.title} ({slugs}).{extra}"

    if decision == "custom":
        text = str(payload.get("text") or "").strip()
        slugs = _slugs_from_free_text(text)
        state.focus_slugs = slugs or list(BARN_SHED_CYCLE)
        state.custom_notes = text
        state.awaiting_choice = False
        state.completed_slug = ""
        save_scene_state(config, state)
        return f"Приняла свой вариант. Фокус: {', '.join(state.focus_slugs)}."

    return "Не поняла. Ответь `1`, `2`, `3` или опиши сцену своими словами."


def _slugs_from_free_text(text: str) -> List[str]:
    low = text.lower()
    found: List[str] = []
    for slug in BARN_SHED_CYCLE:
        if slug.replace("_", " ") in low or slug in low:
            found.append(slug)
    # ключевые слова
    keys = {
        "стул": "sit_down",
        "сид": "sit_idle",
        "сон": "sleep_idle",
        "спать": "sleep_idle",
        "леч": "lie_down",
        "окно": "look_window",
        "огляд": "look_around",
        "ходьб": "walk",
        "шаг": "walk",
        "стол": "eat",
        "ест": "eat",
        "пь": "drink",
        "lean": "lean",
        "облокот": "lean",
        "предмет": "take",
        "поднять": "take",
        "приват": "touch_self",
    }
    for k, slug in keys.items():
        if k in low and slug not in found:
            found.append(slug)
    return found


def scene_choice_status_line(config: Config) -> str:
    st = load_scene_state(config)
    if st.awaiting_choice:
        return (
            f"⏸ Жду выбор сцены в Telegram (после «{st.completed_title or st.completed_slug}»). "
            "Ответь 1/2/3 или свой текст."
        )
    focus = ", ".join(st.focus_slugs[:6])
    if len(st.focus_slugs) > 6:
        focus += "…"
    return f"Фокус съёмки: {focus or 'цикл сарая'}"
