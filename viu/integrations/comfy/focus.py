"""Фокус Comfy MoCap: сарай (быт) vs NSFW vs всё."""

from __future__ import annotations

import os
from typing import List

from ...config import Config
from ...lab.comfy_director import BARN_SHED_CYCLE
from .scene_choice import ComfySceneState

# Быт сарая — по умолчанию раньше; Mixamo для wave-1 закрываем вручную.
BARN_FOCUS_SLUGS: tuple[str, ...] = BARN_SHED_CYCLE

# NSFW solo — Comfy MoCap; остальное (sit, walk…) — стандартные клипы.
NSFW_FOCUS_SLUGS: tuple[str, ...] = (
    "touch_self",
    "shower",
    "bath",
)

_FOCUS_ALIASES = {
    "nsfw": NSFW_FOCUS_SLUGS,
    "private": NSFW_FOCUS_SLUGS,
    "приват": NSFW_FOCUS_SLUGS,
    "barn": BARN_FOCUS_SLUGS,
    "сарай": BARN_FOCUS_SLUGS,
    "дом": BARN_FOCUS_SLUGS,
    "all": (),
}


def focus_mode_from_env(config: Config | None = None) -> str:
    raw = ""
    if config is not None:
        raw = str(getattr(config, "comfy_focus", "") or "").strip()
    if not raw:
        raw = os.environ.get("VIU_COMFY_FOCUS", "").strip()
    return raw.lower()


def slugs_for_mode(mode: str) -> List[str]:
    key = (mode or "").strip().lower()
    if key in _FOCUS_ALIASES:
        return list(_FOCUS_ALIASES[key])
    return list(BARN_FOCUS_SLUGS)


def _default_focus_slugs(config: Config) -> List[str]:
    mode = focus_mode_from_env(config)
    if mode in _FOCUS_ALIASES:
        return slugs_for_mode(mode)
    return list(BARN_FOCUS_SLUGS)


def resolve_focus_slugs(config: Config) -> List[str]:
    """Активный фокус из scene_state (или дефолт из env)."""
    from .scene_choice import scene_state_path
    import json

    path = scene_state_path(config)
    if path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            slugs = [str(x) for x in (data.get("focus_slugs") or []) if str(x).strip()]
            if slugs:
                return slugs
        except (OSError, json.JSONDecodeError):
            pass
    return _default_focus_slugs(config)


def focus_mode_label(config: Config) -> str:
    slugs = resolve_focus_slugs(config)
    if set(slugs) <= set(NSFW_FOCUS_SLUGS) and slugs:
        return "NSFW"
    if set(slugs) >= set(BARN_FOCUS_SLUGS):
        return "сарай"
    if not slugs:
        return "всё"
    return "+".join(slugs[:3]) + ("…" if len(slugs) > 3 else "")


def set_comfy_focus(config: Config, mode: str) -> tuple[bool, str]:
    """Записать фокус в .viu/comfy_scene_state.json."""
    from .scene_choice import load_scene_state, save_scene_state

    key = (mode or "").strip().lower()
    if key not in _FOCUS_ALIASES and key not in ("", "default"):
        return False, (
            f"Не знаю фокус «{mode}». Варианты: nsfw | barn | all\n"
            "nsfw — touch_self, shower, bath (остальное из Mixamo).\n"
            "barn — цикл сарая (sit, lie, walk…)."
        )
    if key in ("", "default"):
        key = focus_mode_from_env(config) or "barn"
    slugs = slugs_for_mode(key)
    st = load_scene_state(config)
    st.focus_slugs = slugs
    st.awaiting_choice = False
    save_scene_state(config, st)
    label = focus_mode_label(config)
    if key in ("nsfw", "private", "приват"):
        hint = (
            "Дальше lab предложит только NSFW-slug (touch_self…). "
            "Бытовые sit/walk/lie — из Mixamo, не Comfy."
        )
    else:
        hint = "Цикл сарая как раньше."
    return True, f"Фокус Comfy: **{label}** ({', '.join(slugs) or 'все дыры'}).\n{hint}"


def maybe_migrate_focus_from_env(config: Config) -> None:
    """Если в .env VIU_COMFY_FOCUS=nsfw, а на диске ещё дефолтный сарай — переключить."""
    mode = focus_mode_from_env(config)
    if mode not in ("nsfw", "private", "приват"):
        return
    from .scene_choice import scene_state_path, save_scene_state

    path = scene_state_path(config)
    if not path.is_file():
        return
    try:
        import json

        data = json.loads(path.read_text(encoding="utf-8"))
        slugs = [str(x) for x in (data.get("focus_slugs") or [])]
        if slugs != list(BARN_FOCUS_SLUGS):
            return
        st = ComfySceneState.from_dict(data)
        st.focus_slugs = list(NSFW_FOCUS_SLUGS)
        save_scene_state(config, st)
    except (OSError, json.JSONDecodeError):
        pass
