"""Снимок «что вокруг» — для размышления, не для слепого автопилота."""

from __future__ import annotations

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


def build_reflect_notes(config: Config) -> str:
    """Минимум фона — без roadmap (он делает робота)."""
    parts: list[str] = []

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

    return "\n\n".join(parts) if parts else ""
