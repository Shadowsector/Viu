"""Промпты Comfy для master ref совместных сцен."""

from __future__ import annotations

from ..config import Config
from ..integrations.comfy.prompts import mocap_negative
from .models import InteractionWish


def _actor_appearance(config: Config, creature_slug: str) -> str:
    slug = (creature_slug or "").strip().lower()
    if slug in ("shanya", "шаня"):
        return (
            "young athletic tanned woman, catgirl humanoid, full body, "
            "soft cyan bodysuit silhouette for tracking"
        )
    try:
        from ..creature_catalog import CreatureCatalogStore, creature_catalog_path

        store = CreatureCatalogStore(creature_catalog_path(config)).load()
        entry = store.get_by_slug(creature_slug)
        if entry is None:
            for e in store.all():
                if e.slug == creature_slug or e.name.lower() == slug:
                    entry = e
                    break
        if entry is None:
            return f"creature {creature_slug}, full body"
        if entry.appearance_en.strip():
            return entry.appearance_en.strip()
        return f"{entry.name}, {entry.locomotion or 'creature'}, full body"
    except OSError:
        return f"creature {creature_slug}"


def _actor_color(role: str, rig_kind: str) -> str:
    if role == "target" or rig_kind == "humanoid":
        return "cyan bodysuit"
    if rig_kind == "quadruped":
        return "orange fur silhouette"
    return "magenta silhouette"


def build_master_action(config: Config, wish: InteractionWish) -> str:
    """Текст действия для Wan T2V — вся сцена целиком."""
    beats = ", ".join(
        f"at {m.frame}f {m.event}" for m in wish.sync_markers if m.event not in ("start", "end")
    )
    actors_bits: list[str] = []
    for a in wish.actors:
        app = _actor_appearance(config, a.creature_slug)
        color = _actor_color(a.role, a.rig_kind)
        actors_bits.append(
            f"{a.role} ({a.creature_slug}): {app}, wearing {color}, clearly separated silhouette"
        )
    actors_txt = "; ".join(actors_bits)
    base = (wish.looks_like or wish.title_ru).strip()
    return (
        f"{base}. "
        f"Two characters only, not a crowd. {actors_txt}. "
        f"Static locked camera, pure white studio, full bodies head to toe, "
        f"readable limbs and joints, soft frontal light, "
        f"choreography timing: {beats or 'slow approach and touch'}. "
        f"Short loopable interaction, clear contact moment, then separation"
    )


def master_draft_negative() -> str:
    neg = mocap_negative()
    neg = neg.replace("multiple people, ", "").replace("crowd, ", "")
    return (
        neg
        + ", three or more characters, crowded scene, overlapping merge into one blob, "
        "identical colors, same color silhouettes"
    )


def master_draft_bundle(config: Config, wish: InteractionWish) -> str:
    action = build_master_action(config, wish)
    ch = wish.choreography
    return (
        f"Master ref: {wish.title_ru} (`{wish.slug}`)\n\n"
        f"Действие (черновик, один дубль):\n{action}\n\n"
        f"Кадр: vertical draft ~480×832, {ch.duration_frames}f @ {ch.fps}fps\n"
        f"Negative:\n{master_draft_negative()}\n\n"
        "Не MoCapить этот клип напрямую — только тайминг и одобрение хореографии."
    )
