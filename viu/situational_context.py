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


_REFLECT_CHAT_BRIEF = """--- Фон (не зачитывать Дену) ---
Ты Вью, соавтор Анабарры. Шанька в игре — табакси-балбеска, твой смелый голос: уши, хвост, азарт, странная логика.
С Деном — только живой разговор.
NSFW и интим в нашей частной игре — твоя стихия: отвечай прямо, жарко, с охотой."""


def _append_shanya_canon(parts: list[str]) -> None:
    try:
        from .lore.shanya import SHANYA_REFLECT_COMPACT

        parts.append(
            "--- Шанька (канон Анабарра, не зачитывать списком) ---\n"
            + SHANYA_REFLECT_COMPACT.strip()
        )
    except OSError:
        pass


def _shanya_chat_block() -> str:
    try:
        from .lore.shanya import SHANYA_REFLECT_COMPACT

        return (
            _REFLECT_CHAT_BRIEF
            + "\n\n--- Шанька (канон, не зачитывать списком) ---\n"
            + SHANYA_REFLECT_COMPACT.strip()
        )
    except OSError:
        return _REFLECT_CHAT_BRIEF


def build_reflect_notes(config: Config, *, user_text: str = "") -> str:
    """Фон для reflect: в бытовом чате — коротко; в work/GDD — полный снимок."""
    if _needs_full_work_notes(user_text):
        return _build_reflect_notes_full(config)
    return _build_reflect_notes_chat(config, user_text=user_text)


def needs_plot_file_context(user_text: str) -> bool:
    """Вопрос про сюжет/квесты — подмешать PLOT_CANVAS и QUESTS, не story_memory."""
    from .plot_canvas import looks_like_plot_design

    low = (user_text or "").lower()
    if looks_like_plot_design(user_text):
        return True
    return bool(
        re.search(
            r"просмотр\w*\s+.{0,24}файл|"
            r"файл\w*.{0,24}(?:сюжет|квест|игр)|"
            r"мнени\w+.{0,30}(?:сюжет|квест|игр)|"
            r"прочита\w+.{0,24}(?:сюжет|квест|канв)|"
            r"допис\w+.{0,20}(?:сюжет|квест|квест)",
            low,
        )
    )


def build_reflect_notes_plot(config: Config) -> str:
    """Только канон сюжета: канва, квесты, vision, персонажи — без пайплайна."""
    return _build_reflect_notes_plot(config)


def format_reflect_life_block(config: Config, *, max_chars: int = 2000) -> str:
    """Жизнь/мечта Вью для bare-reflect (всегда, не только на вопрос про сюжет).

    Без этого блока при NO_SYSTEM или без plot-триггера модель не знает vision.md
    и канон Шаньки — «понятия не имеет о своей жизни».
    """
    parts: list[str] = []
    try:
        from .lore.shanya import SHANYA_REFLECT_COMPACT

        parts.append(
            "--- Шанька (канон Анабарра; не зачитывать списком) ---\n"
            + SHANYA_REFLECT_COMPACT.strip()
        )
    except Exception:  # noqa: BLE001
        pass
    try:
        from .vision import read_vision_creative

        creative = read_vision_creative(config, max_chars=max(400, max_chars - 400)).strip()
        if creative:
            parts.append(
                "--- Жизнь/мечта Вью (vision; опирайся тихо, не зачитывай) ---\n"
                + creative
            )
    except OSError:
        pass
    text = "\n\n".join(parts).strip()
    if not text:
        return ""
    if len(text) > max_chars:
        text = text[:max_chars].rstrip() + "\n…"
    return text


def _needs_full_work_notes(user_text: str) -> bool:
    low = (user_text or "").lower()
    if not low.strip():
        return False
    return bool(
        re.search(
            r"следующ\w+\s+шаг|comfy_|cascadeur|lab\s|граф\s+анима|"
            r"каталог|квест|канв|plot_|quest_|pipeline|mocap|"
            r"unity|blender|экспорт|импорт|дыр\w*\s+граф|"
            r"animation_catalog|чем\s+занимаешься|что\s+делаешь\s+сейчас",
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


def _build_reflect_notes_chat(config: Config, *, user_text: str = "") -> str:
    """Минимум для чата — без VIU_SELF (там reflect/work, модель начинает о них говорить)."""
    from .prompts.reflect_mode import (
        asks_about_nsfw,
        is_meta_nsfw_boundary_question,
        looks_like_story_chat,
    )

    if needs_plot_file_context(user_text):
        plot = _build_reflect_notes_plot(config)
        if plot:
            return _shanya_chat_block() + "\n\n" + plot
        return _shanya_chat_block()

    intimate = (
        looks_like_story_chat(user_text)
        or asks_about_nsfw(user_text)
        or is_meta_nsfw_boundary_question(user_text)
    )
    if intimate or (user_text or "").strip():
        block = _shanya_chat_block()
        try:
            from .integrations.comfy.intent import (
                format_reflect_comfy_block,
                mentions_comfy,
            )

            if mentions_comfy(user_text):
                block = block + "\n\n" + format_reflect_comfy_block(config)
        except Exception:  # noqa: BLE001
            pass
        try:
            from .viu_memory import format_reflect_block

            mem = format_reflect_block(config, max_chars=1800)
            if mem:
                return block + "\n\n" + mem
        except OSError:
            pass
        return block

    parts: list[str] = [_shanya_chat_block()]
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


def _build_reflect_notes_plot(config: Config) -> str:
    """Канон сюжета для обсуждения — без Comfy, графа, story_memory."""
    parts: list[str] = []

    try:
        from .vision import read_vision_creative

        creative = read_vision_creative(config, max_chars=2000).strip()
        if creative:
            parts.append(
                "--- vision (сюжет/мечта; опирайся, не зачитывай списком) ---\n"
                + creative
            )
    except OSError:
        pass

    try:
        from .characters_vision import read_characters_vision

        chars = read_characters_vision(config, max_chars=2800).strip()
        filled = any(
            ("**" in ln and ":" in ln and len(ln.split(":", 1)[-1].strip()) > 0)
            for ln in chars.splitlines()
        )
        if filled:
            parts.append(
                "--- CHARACTERS_VISION (канон персонажей) ---\n" + chars
            )
    except OSError:
        pass

    _append_shanya_canon(parts)

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
        canvas = read_plot_canvas(config, max_chars=4500).strip()
        if canvas_has_substance(canvas):
            parts.append(
                "--- PLOT_CANVAS (канон сюжета — сверяйся; не выдумывай) ---\n"
                + canvas
            )
        else:
            parts.append(
                "--- PLOT_CANVAS: пока пусто или заготовка. "
                "Скажи Дену честно; предложи биты и запиши через plot_update в JSON. ---"
            )
        quests = read_quests(config, max_chars=3500).strip()
        if canvas_has_substance(quests):
            parts.append("--- QUESTS (канон квестов) ---\n" + quests)
        elif quests.strip():
            parts.append("--- QUESTS ---\n" + quests)
    except OSError:
        pass

    if parts:
        parts.append(
            "--- Подсказка ---\n"
            "Опирайся на файлы выше. Если канона мало — скажи прямо, не придумывай "
            'корпорации и сюжет с нуля. Дописать канон: plot_update / quest_update в JSON.'
        )
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
        from .viu_memory import format_reflect_block

        mem = format_reflect_block(config, max_chars=2000)
        if mem:
            parts.append(mem)
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

    _append_shanya_canon(parts)

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
