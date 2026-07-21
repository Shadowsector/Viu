"""Лаборатория совместных анимаций — MVP-скелет шагов.

Полная реализация — по docs/INTERACTION_PIPELINE.md.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, List, Optional, Tuple

from ..config import Config
from ..interaction_catalog import (
    InteractionCatalogStore,
    InteractionWish,
    interaction_catalog_path,
    interaction_scene_dir,
)
from .notify import notify_lab_step
from .paths import task_path
from .session import LabSession, append_journal, load_session, save_session

INTERACTION_TOPIC = "interaction"

StepResult = Tuple[bool, str, Optional[str]]

STEP_LABELS = [
    "Спека каталога",
    "Blocking Blender",
    "Master draft Comfy",
    "Одобрение master",
    "Per-actor isolated ref",
    "MoCap / Control Pose",
    "Blender assembly",
    "Verify + отчёт",
]


def ensure_task_file(config: Config, *, catalog_slug: str = "") -> Path:
    path = task_path(config, INTERACTION_TOPIC)
    slug = catalog_slug.strip()
    if not slug:
        store = InteractionCatalogStore(interaction_catalog_path(config)).load()
        holes = store.holes_for_wave(wave=1)
        if holes:
            slug = holes[0].slug
    body = (
        "# Lab Interaction — совместные анимации\n\n"
        "См. docs/INTERACTION_PIPELINE.md\n\n"
        f"## catalog_slug\n\n{slug or '(укажи slug)'}\n\n"
        "## pipeline\n\n"
        "master ref → per-actor isolated → mocap/CP → blender assembly → verify\n"
    )
    if not path.is_file() or slug:
        path.write_text(body, encoding="utf-8")
    return path


def read_slug_from_task(config: Config) -> str:
    path = task_path(config, INTERACTION_TOPIC)
    if not path.is_file():
        return ""
    text = path.read_text(encoding="utf-8")
    for header in ("## catalog_slug", "## Catalog_slug"):
        if header.lower() in text.lower():
            parts = text.split(header, 1)
            if len(parts) < 2:
                continue
            for ln in parts[1].splitlines():
                s = ln.strip()
                if s and not s.startswith("#"):
                    return s
    return ""


def load_wish(config: Config, slug: str = "") -> Optional[InteractionWish]:
    store = InteractionCatalogStore(interaction_catalog_path(config)).load()
    key = slug.strip() or read_slug_from_task(config)
    if not key:
        holes = store.holes_for_wave(wave=1)
        if holes:
            key = holes[0].slug
    if not key:
        return None
    return store.get_by_slug(key)


def _scene_paths(config: Config, wish: InteractionWish) -> dict[str, Path]:
    root = interaction_scene_dir(config, wish.slug)
    return {
        "root": root,
        "blocking": root / "blocking",
        "master": root / "master",
        "actors": root / "actors",
        "assembly": root / "assembly",
        "exports": root / "exports",
        "rejected": root / "rejected",
    }


def _ensure_dirs(paths: dict[str, Path]) -> None:
    for key in ("blocking", "master", "actors", "assembly", "exports", "rejected"):
        paths[key].mkdir(parents=True, exist_ok=True)


def step_spec(config: Config, session: LabSession) -> StepResult:
    slug = session.meta.get("catalog_slug") or read_slug_from_task(config)
    wish = load_wish(config, slug)
    if wish is None:
        return False, "Нет interaction в каталоге. Укажи catalog_slug в TASK.md.", None
    session.meta["catalog_slug"] = wish.slug
    paths = _scene_paths(config, wish)
    _ensure_dirs(paths)
    actors = ", ".join(f"{a.role}:{a.creature_slug}" for a in wish.actors)
    ch = wish.choreography
    msg = (
        f"Спека `{wish.slug}`: {wish.title_ru}\n"
        f"Актёры: {actors}\n"
        f"Хореография: {ch.duration_frames}f @ {ch.fps}fps\n"
        f"Папка: {paths['root']}"
    )
    append_journal(config, INTERACTION_TOPIC, f"spec ok: {wish.slug}")
    return True, msg, None


def step_blocking(config: Config, session: LabSession) -> StepResult:
    from ..interaction_catalog.blocking import run_interaction_blocking

    wish = load_wish(config, str(session.meta.get("catalog_slug", "")))
    if wish is None:
        return False, "Нет wish для blocking.", None
    paths = _scene_paths(config, wish)
    _ensure_dirs(paths)
    blend = paths["blocking"] / "blocking.blend"

    ok, msg = run_interaction_blocking(config, wish, open_result=False)
    if not ok:
        append_journal(config, INTERACTION_TOPIC, f"blocking fail: {msg[:200]}")
        return False, msg, None

    append_journal(config, INTERACTION_TOPIC, f"blocking ok: {blend}")
    markers = ", ".join(f"@{m.frame}:{m.event}" for m in wish.sync_markers)
    return True, f"{msg}\nМаркеры: {markers}", None


def step_master_draft(config: Config, session: LabSession) -> StepResult:
    from ..interaction_catalog.master_comfy import run_interaction_master_draft

    wish = load_wish(config, str(session.meta.get("catalog_slug", "")))
    if wish is None:
        return False, "Нет wish для master draft.", None

    ok, msg = run_interaction_master_draft(config, wish)
    if not ok:
        append_journal(config, INTERACTION_TOPIC, f"master_draft fail: {msg[:300]}")
        return False, msg, None

    append_journal(config, INTERACTION_TOPIC, "master_draft ok")
    return True, msg, None


def step_master_approve(config: Config, session: LabSession) -> StepResult:
    wish = load_wish(config, str(session.meta.get("catalog_slug", "")))
    if wish is None:
        return False, "Нет wish.", None
    paths = _scene_paths(config, wish)
    approved = paths["master"] / "master_approved.mp4"
    msg = (
        "MVP: одобрение master — Telegram/GUI (как comfy clip pick).\n"
        f"После одобрения: {approved}"
    )
    append_journal(config, INTERACTION_TOPIC, "master_approve: scaffold")
    return True, msg, None


def step_isolated_refs(config: Config, session: LabSession) -> StepResult:
    wish = load_wish(config, str(session.meta.get("catalog_slug", "")))
    if wish is None:
        return False, "Нет wish.", None
    lines = ["MVP: per-actor isolated ref — scaffold."]
    for a in wish.actors:
        adir = interaction_scene_dir(config, wish.slug) / "actors" / a.role
        adir.mkdir(parents=True, exist_ok=True)
        target = adir / "isolated_ref.mp4"
        lines.append(
            f"  {a.role} ({a.creature_slug}): {target} — реген Comfy I2V, не кроп master."
        )
    append_journal(config, INTERACTION_TOPIC, "isolated: scaffold")
    return True, "\n".join(lines), None


def step_animate_actors(config: Config, session: LabSession) -> StepResult:
    wish = load_wish(config, str(session.meta.get("catalog_slug", "")))
    if wish is None:
        return False, "Нет wish.", None
    lines = ["MVP: MoCap / Control Pose — scaffold."]
    for a in wish.actors:
        path = "mocap" if a.motion_path == "mocap" else "control_pose"
        lines.append(
            f"  {a.role}: {path} → actors/{a.role}/mocap.fbx ({a.rig_kind})"
        )
    append_journal(config, INTERACTION_TOPIC, "animate: scaffold")
    return True, "\n".join(lines), None


def step_assembly(config: Config, session: LabSession) -> StepResult:
    wish = load_wish(config, str(session.meta.get("catalog_slug", "")))
    if wish is None:
        return False, "Нет wish.", None
    paths = _scene_paths(config, wish)
    blend = paths["assembly"] / "assembly.blend"
    msg = (
        f"MVP: Blender assembly — scaffold.\n"
        f"Цель: {blend} + exports/*.fbx с общим frame_start.\n"
        f"Constraints на sync_markers: "
        f"{', '.join(m.event for m in wish.sync_markers)}"
    )
    append_journal(config, INTERACTION_TOPIC, "assembly: scaffold")
    return True, msg, None


def step_verify(config: Config, session: LabSession) -> StepResult:
    wish = load_wish(config, str(session.meta.get("catalog_slug", "")))
    if wish is None:
        return False, "Нет wish.", None
    msg = (
        "MVP: verify — marker drift, ground contact, penetration, длина FBX.\n"
        "Unity smoke — позже. См. docs/INTERACTION_PIPELINE.md § фаза 6."
    )
    append_journal(config, INTERACTION_TOPIC, "verify: scaffold")
    return True, msg, None


STEP_RUNNERS: List[Callable[[Config, LabSession], StepResult]] = [
    step_spec,
    step_blocking,
    step_master_draft,
    step_master_approve,
    step_isolated_refs,
    step_animate_actors,
    step_assembly,
    step_verify,
]


def run_one_step(config: Config, session: LabSession) -> Tuple[bool, str]:
    if session.status == "awaiting_prompt":
        return True, "Жду одобрение master ref (Telegram/GUI — позже)."
    if session.status == "awaiting_rating":
        return True, "Жду оценку — «Оценить лабораторию»."
    if session.status not in ("running", "paused"):
        return True, f"Сессия: {session.status}"

    if session.status == "paused":
        session.status = "running"
        session.pause_reason = ""

    if session.step >= len(STEP_RUNNERS):
        session.status = "completed"
        save_session(config, session)
        return True, "Все шаги interaction выполнены (MVP scaffold)."

    fn = STEP_RUNNERS[session.step]
    step_idx = session.step + 1
    label = STEP_LABELS[session.step]
    ok, msg, _hint = fn(config, session)

    if not ok:
        session.last_fail_step = session.step
        session.last_fail_msg = msg[:2000]
        key = str(session.step)
        session.step_fail_counts[key] = session.step_fail_counts.get(key, 0) + 1
        save_session(config, session)
        return False, msg

    session.last_fail_step = -1
    session.step += 1
    session.steps_total = len(STEP_RUNNERS)
    notify_lab_step(config, step_idx, label, msg)
    if session.step >= len(STEP_RUNNERS):
        session.status = "completed"
    else:
        session.status = "running"
    save_session(config, session)
    return ok, msg


def run_until_done(
    config: Config,
    session: LabSession,
    *,
    max_steps: int = 16,
) -> Tuple[bool, str]:
    lines: list[str] = []
    steps_run = 0
    ok_all = True
    while steps_run < max_steps:
        session = load_session(config, INTERACTION_TOPIC) or session
        if session.status in ("completed", "awaiting_prompt", "awaiting_rating"):
            break
        ok, msg = run_one_step(config, session)
        lines.append(msg)
        steps_run += 1
        if not ok:
            ok_all = False
            break
        session = load_session(config, INTERACTION_TOPIC) or session
        if session.status == "completed":
            break
    return ok_all, "\n\n".join(lines)
