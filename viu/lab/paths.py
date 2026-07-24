"""Пути лаборатории: journal, session, артефакты."""

from __future__ import annotations

import os
from pathlib import Path

from ..config import Config


def lab_root(config: Config) -> Path:
    root = config.data_dir / "lab"
    root.mkdir(parents=True, exist_ok=True)
    return root


def topic_dir(config: Config, topic: str) -> Path:
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in topic.strip().lower())
    p = lab_root(config) / (safe or "general")
    p.mkdir(parents=True, exist_ok=True)
    return p


def session_path(config: Config, topic: str) -> Path:
    return topic_dir(config, topic) / "session.json"


def journal_path(config: Config, topic: str) -> Path:
    return topic_dir(config, topic) / "journal.md"


def task_path(config: Config, topic: str) -> Path:
    return topic_dir(config, topic) / "TASK.md"


def artifacts_dir(config: Config, topic: str) -> Path:
    p = topic_dir(config, topic) / "artifacts"
    p.mkdir(parents=True, exist_ok=True)
    return p


def models_inbox_dir(config: Config) -> Path:
    """Единый Inbox живых существ (то же, что Creatures/Inbox)."""
    from ..creature_catalog.paths import creatures_inbox_dir

    return creatures_inbox_dir(config)


def _models_inbox_dir_legacy(config: Config) -> Path:
    """Старый путь — только если задан VIU_LAB_MODELS_INBOX."""
    import os

    from ..anabarra_layout import library_root

    env = os.environ.get("VIU_LAB_MODELS_INBOX", "").strip()
    if env:
        p = Path(env).expanduser()
        p.mkdir(parents=True, exist_ok=True)
        return p
    p = library_root(config) / "Lab" / "Models" / "Inbox"
    p.mkdir(parents=True, exist_ok=True)
    return p


def cascadeur_ready_dir(config: Config) -> Path:
    """Чистые FBX для Cascadeur (batch export из Blender)."""
    import os

    from ..anabarra_layout import library_root

    env = os.environ.get("VIU_CASCADEUR_READY", "").strip()
    if env:
        p = Path(env).expanduser()
    else:
        p = library_root(config) / "Lab" / "Models" / "CascadeurReady"
    p.mkdir(parents=True, exist_ok=True)
    readme = p / "README.txt"
    if not readme.is_file():
        readme.write_text(
            "FBX для Cascadeur — batch export из Viu (без WGT/widget, deform bones).\n"
            "Команда: blender_export_cascadeur_batch\n"
            "Import в Cascadeur: File → Import → Scene preset.\n",
            encoding="utf-8",
        )
    return p


def models_summary_md(config: Config, topic: str) -> Path:
    return artifacts_dir(config, topic) / "models_summary.md"


def models_summary_json(config: Config, topic: str) -> Path:
    return artifacts_dir(config, topic) / "models_summary.json"


def _runtime_get(config: Config, key: str, default: str) -> str:
    try:
        from ..runtime_settings import get

        val = get(config, key, None)
        if val is not None:
            return str(val)
    except Exception:
        pass
    return default


def lab_vram_gb(config: Config) -> float:
    from ..ollama_vram import ollama_vram_gb

    runtime = _runtime_get(config, "lab_vram_gb", "")
    return ollama_vram_gb(runtime_gb=runtime or None)


def lab_monitor_index(config: Config) -> int:
    """0 = первый монитор, 2 = третий (правый) — для Cascadeur."""
    raw = os.environ.get("VIU_LAB_MONITOR") or _runtime_get(config, "lab_monitor", "2")
    try:
        return max(0, int(raw))
    except (TypeError, ValueError):
        return 2


def lab_interval_min(config: Config) -> int:
    raw = os.environ.get("VIU_LAB_INTERVAL_MIN") or _runtime_get(config, "lab_interval_min", "5")
    try:
        return max(0, int(raw))
    except (TypeError, ValueError):
        return 5


def apply_lab_vram_env(config: Config) -> None:
    """Подсказка Ollama: лимит VRAM под LLM (Den: RTX 3060, ~10 GB)."""
    from ..ollama_vram import apply_ollama_vram_limit

    apply_ollama_vram_limit(config)
