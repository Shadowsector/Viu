"""Снимок «что вокруг» — для размышления, не для слепого автопилота."""

from __future__ import annotations

import re

from .config import Config


def build_situational_context(config: Config, *, recent_chat: str = "") -> str:
    parts: list[str] = []

    try:
        from .integrations.unity.process import unity_process_running

        if unity_process_running():
            parts.append(
                "Unity Editor **открыт** на машине. Ден может быть не у ПК — "
                "не проси нажать Play; при необходимости закрой unity_close."
            )
        else:
            parts.append("Unity Editor закрыт.")
    except OSError:
        pass

    try:
        from .director import format_banner, plan_next_step

        plan = plan_next_step(config)
        parts.append(
            "Подсказка режиссёра (не выполнять автоматически):\n"
            + format_banner(plan)
        )
    except OSError:
        pass

    try:
        from .vision import read_vision

        parts.append("--- vision.md ---\n" + read_vision(config, max_chars=2500))
    except OSError:
        pass

    if recent_chat.strip():
        parts.append("--- Недавний чат ---\n" + recent_chat.strip()[-2000:])

    return "\n\n".join(parts)


def build_reflect_notes(config: Config, *, user_text: str = "") -> str:
    """Фон для reflect: в бытовом чате — коротко; в work/GDD — полный снимок."""
    if _needs_full_work_notes(user_text):
        return _build_reflect_notes_full(config)
    if _needs_story_digest(user_text) and not _user_sent_scene_brief(user_text):
        return _build_reflect_notes_story(config)
    return _build_reflect_notes_chat(config)


def _user_sent_scene_brief(user_text: str) -> bool:
    """Ден уже прислал раскадровку — не заливать канву/квесты и не отвечать GDD-зеркалом."""
    t = user_text or ""
    if t.count("###") >= 1 or t.count("**") >= 6:
        return True
    if re.search(r"(?i)motion\s+capture|frames\)|камера\s*:", t):
        return True
    return False


def _needs_story_digest(user_text: str) -> bool:
    try:
        from .plot_canvas import looks_like_plot_design
        from .story_memory import looks_like_story_chat

        return looks_like_story_chat(user_text) or looks_like_plot_design(user_text)
    except ImportError:
        return False


def _build_reflect_notes_story(config: Config) -> str:
    """Сюжетный чат: канва/квесты кратко + последние заметки Вью."""
    parts: list[str] = [_build_reflect_notes_chat(config)]
    try:
        from .plot_canvas import canvas_has_substance, read_plot_canvas, read_quests

        canvas = read_plot_canvas(config, max_chars=900).strip()
        if canvas and canvas_has_substance(canvas):
            parts.append(
                "--- Канва (кратко; не зачитывать) ---\n" + canvas
            )
        quests = read_quests(config, max_chars=700).strip()
        if quests and "шаблон" not in quests[:200].lower():
            parts.append("--- Квесты (кратко) ---\n" + quests)
    except OSError:
        pass
    try:
        from .suggestions import read_suggestions, suggestions_has_substance

        if suggestions_has_substance(config):
            tail = read_suggestions(config, max_chars=800).strip()
            if tail:
                parts.append(
                    "--- Мои недавние заметки (SUGGESTIONS; не зачитывать) ---\n"
                    + tail
                )
    except OSError:
        pass
    parts.append(
        "--- Стиль ответа ---\n"
        "Заметки выше — фон. В final только живая речь: 2–6 предложений, без GDD-разметки."
    )
    return "\n\n".join(p for p in parts if p)


def _needs_full_work_notes(user_text: str) -> bool:
    low = (user_text or "").lower()
    if not low.strip():
        return False
    # Только операционные запросы — не «обсуждаем сцену» с mocap/comfy в тексте.
    return bool(
        re.search(
            r"следующ\w+\s+шаг|"
            r"(?:запусти|выполни)\s+(?:lab|comfy)|"
            r"lab\s+topic|"
            r"comfy_(?:mocap|triple|ensure)\s|"
            r"cascadeur_(?:status|import|export)|"
            r"animation_catalog_show|"
            r"чем\s+занимаешься|что\s+делаешь\s+сейчас|"
            r"дыр\w*\s+граф|граф\s+анима.*(?:покаж|дыр)",
            low,
        )
    )


def _read_viu_self_brief(*, max_chars: int = 1400) -> str:
    try:
        from pathlib import Path

        path = Path(__file__).resolve().parent.parent / "docs" / "VIU_SELF.md"
        if not path.is_file():
            return ""
        text = path.read_text(encoding="utf-8", errors="replace").strip()
        if len(text) > max_chars:
            text = text[:max_chars] + "…"
        return "--- VIU_SELF (процессы внутри Вью; не зачитывать списком) ---\n" + text
    except OSError:
        return ""


def _build_reflect_notes_chat(config: Config) -> str:
    """Минимум: кто я в системе + граф + следующий кадр — без простыни GDD."""
    parts: list[str] = []
    brief = _read_viu_self_brief()
    if brief:
        parts.append(brief)
    try:
        from .animation_catalog import AnimationCatalogStore, animation_catalog_path

        store = AnimationCatalogStore(animation_catalog_path(config)).load()
        brief_graph = store.graph_brief(max_holes=4).strip()
        if brief_graph:
            parts.append(
                "--- Граф анимаций (кратко) ---\n" + brief_graph
            )
    except OSError:
        pass
    try:
        from .lab.comfy_director import invent_next_shot

        plan = invent_next_shot(config)
        parts.append("--- Следующий кадр ---\n" + plan.summary_ru())
    except Exception:
        pass
    return "\n\n".join(parts) if parts else ""


def _build_reflect_notes_full(config: Config) -> str:
    """Полный снимок — для work, пайплайна, квестов."""
    parts: list[str] = []

    try:
        from .capabilities import CAPABILITY_BRIEF, docs_vector_brief

        parts.append(CAPABILITY_BRIEF)
        docs = docs_vector_brief(max_chars=1600)
        if docs:
            parts.append(docs)
    except OSError:
        pass

    try:
        from .integrations.unity.process import unity_process_running

        if unity_process_running():
            parts.append("(Unity открыт — Play может быть некому.)")
    except OSError:
        pass

    try:
        from .memory import MemoryStore

        recent = MemoryStore(config.data_dir / "memory.json").recent(limit=2)
        if recent:
            parts.append("Память: " + "; ".join(r.text[:120] for r in recent))
    except OSError:
        pass

    try:
        from .story_memory import get_story_memory

        # краткий хвост — полный RAG собирает run_reflect
        tail = get_story_memory(config).recent(limit=4)
        if tail:
            bits = []
            for b in tail:
                who = "Ден" if b.role == "user" else "Вью"
                bits.append(f"{who}: {b.text[:80]}")
            parts.append("Сюжет (хвост): " + " | ".join(bits))
    except OSError:
        pass

    try:
        from .vision import read_vision_creative

        creative = read_vision_creative(config, max_chars=1800).strip()
        if creative:
            parts.append("--- vision (сюжет/мечта, не зачитывать списком) ---\n" + creative)
    except OSError:
        pass

    try:
        from .characters_vision import read_characters_vision

        chars = read_characters_vision(config, max_chars=2800).strip()
        # подключать только если Ден уже что-то дописал после двоеточий
        filled = any(
            ("**" in ln and ":" in ln and len(ln.split(":", 1)[-1].strip()) > 0)
            for ln in chars.splitlines()
        )
        if filled:
            parts.append(
                "--- CHARACTERS_VISION (локально, не зачитывать списком) ---\n" + chars
            )
    except OSError:
        pass

    try:
        from .plot_canvas import (
            canvas_has_substance,
            ensure_plot_canvas,
            ensure_quests,
            read_plot_canvas,
            read_quests,
        )

        ensure_plot_canvas(config)
        ensure_quests(config)
        canvas = read_plot_canvas(config, max_chars=4000).strip()
        if canvas_has_substance(canvas):
            parts.append(
                "--- PLOT_CANVAS (канон сюжета — сверяйся при квестах; не зачитывать списком) ---\n"
                + canvas
            )
        else:
            parts.append(
                "--- PLOT_CANVAS: пока пусто. Перед новым квестом предложи биты канвы "
                "и запиши через plot_update. ---"
            )
        quests = read_quests(config, max_chars=3000).strip()
        if canvas_has_substance(quests):
            parts.append(
                "--- QUESTS (сверяйся с канвой; не зачитывать списком) ---\n" + quests
            )
    except OSError:
        pass

    try:
        from .creature_catalog.describe import format_creatures_for_reflect

        creatures = format_creatures_for_reflect(config)
        if creatures:
            parts.append(creatures)
    except OSError:
        pass

    try:
        from .animation_catalog import AnimationCatalogStore, animation_catalog_path

        store = AnimationCatalogStore(animation_catalog_path(config)).load()
        brief = store.graph_brief(max_holes=6).strip()
        if brief:
            parts.append(
                "--- Граф анимаций (не зачитывать списком; предлагай закрывать цепочки) ---\n"
                + brief
            )
    except OSError:
        pass

    try:
        from .interaction_catalog.format_reflect import format_interactions_for_reflect

        interactions = format_interactions_for_reflect(config, max_holes=4)
        if interactions:
            parts.append(interactions)
    except OSError:
        pass

    try:
        from .lab.comfy_director import invent_next_shot

        plan = invent_next_shot(config)
        parts.append(
            "--- Следующий кадр (предложи Дена, спроси одобрение) ---\n"
            + plan.summary_ru()
        )
    except Exception:
        pass

    try:
        from pathlib import Path

        direction = Path(__file__).resolve().parent.parent / "docs" / "VIU_DIRECTION.md"
        if direction.is_file():
            text = direction.read_text(encoding="utf-8", errors="replace")
            if len(text) > 1200:
                text = text[:1200] + "…"
            parts.append("--- Направление работ ---\n" + text)
    except OSError:
        pass

    return "\n\n".join(parts) if parts else ""
