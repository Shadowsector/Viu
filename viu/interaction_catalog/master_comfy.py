"""Comfy → master_draft.mp4 для interaction-сцен."""

from __future__ import annotations

import hashlib
import shutil
from pathlib import Path
from typing import List, Tuple

from ..config import Config
from ..integrations.comfy.angles import LEGACY_ANGLES
from ..integrations.comfy.client import ComfyClient, ComfyError
from ..integrations.comfy.generate import _client
from ..integrations.comfy.model_pref import choose_workflow_name, probe_models
from ..integrations.comfy.naming import comfy_filename_prefix, display_video_stem
from ..integrations.comfy.process import ensure_comfy_running
from ..integrations.comfy.workflows import (
    ensure_mp4_output,
    ensure_workflow_templates,
    inject_filename_prefix,
    inject_negative_prompt,
    inject_seed,
    inject_text_prompt,
    inject_vertical_frame,
    load_workflow,
)
from .models import STATUS_MASTER_DRAFT, InteractionWish
from .paths import interaction_scene_dir
from .prompts import build_master_action, master_draft_negative

# Черновик — чуть меньше полного MoCap, экономия VRAM
DRAFT_SIZE = (480, 832)


def snap_wan_length(frames: int) -> int:
    """Wan T2V: длина кратна 4 + 1."""
    if frames < 9:
        return 49
    n = max(1, round((int(frames) - 1) / 4))
    return 4 * n + 1


def _seed_for(slug: str, salt: str = "master") -> int:
    h = hashlib.sha256(f"{slug}|{salt}|interaction_master".encode("utf-8")).hexdigest()
    return int(h[:8], 16) % (2**31 - 1)


def _prepare_workflow(config: Config, wish: InteractionWish, action: str) -> dict:
    wf_name = choose_workflow_name(config, has_seed_image=False)
    wf = load_workflow(config, wf_name)
    length = snap_wan_length(wish.choreography.duration_frames)
    wf = inject_vertical_frame(
        wf,
        width=DRAFT_SIZE[0],
        height=DRAFT_SIZE[1],
        length=length,
    )
    stem = display_video_stem(catalog_slug=wish.slug)
    prefix = comfy_filename_prefix(stem)
    wf = ensure_mp4_output(wf, fps=float(wish.choreography.fps), filename_prefix=prefix)
    wf = inject_filename_prefix(wf, prefix)
    wf = inject_text_prompt(wf, action)
    wf = inject_negative_prompt(wf, master_draft_negative())
    wf = inject_seed(wf, _seed_for(wish.slug))
    return wf


def _pick_mp4(files: List[dict]) -> List[dict]:
    mp4 = [m for m in files if str(m.get("filename", "")).lower().endswith(".mp4")]
    return mp4 or files


def run_master_draft_comfy(
    config: Config,
    wish: InteractionWish,
    *,
    timeout: float = 1200.0,
) -> Tuple[bool, str, Path]:
    """Один черновой MP4 → master/master_draft.mp4."""
    master_dir = interaction_scene_dir(config, wish.slug) / "master"
    master_dir.mkdir(parents=True, exist_ok=True)
    dest = master_dir / "master_draft.mp4"

    ok_run, run_msg = ensure_comfy_running(config)
    if not ok_run:
        return False, f"Comfy не запущен: {run_msg}", Path()

    probe = probe_models(config)
    if not probe.ready_t2v:
        return (
            False,
            "Модели Wan T2V не готовы. Запусти comfy_install / lab topic=comfy.\n"
            + "\n".join(probe.notes[:8]),
            Path(),
        )

    ensure_workflow_templates(config)

    action = build_master_action(config, wish)
    front = next((a for a in LEGACY_ANGLES if a.id == "front"), LEGACY_ANGLES[2])
    prompt = f"{action}, {front.prompt_en}"

    wf = _prepare_workflow(config, wish, prompt)
    client: ComfyClient = _client(config)
    ok, ping = client.ping()
    if not ok:
        return False, ping, Path()

    try:
        prompt_id = client.queue_prompt(wf)
        entry = client.wait_history(prompt_id, timeout=timeout)
        files = _pick_mp4(client.collect_output_files(entry))
    except ComfyError as exc:
        return False, str(exc), Path()

    if not files:
        return False, f"prompt_id={prompt_id}: нет MP4 в output", Path()

    meta = files[0]
    try:
        client.download_view(
            meta["filename"],
            subfolder=meta.get("subfolder") or "",
            folder_type=meta.get("type") or "output",
            dest=dest,
        )
    except ComfyError as exc:
        return False, str(exc), Path()

    if not dest.is_file():
        from ..integrations.comfy.paths import resolve_comfy_root

        root = resolve_comfy_root(config)
        native = str(meta.get("filename") or "")
        if root and native:
            cand = root / "output" / native
            if cand.is_file():
                shutil.copy2(cand, dest)
        if not dest.is_file():
            return False, f"MP4 не сохранён: {dest}", Path()

    length = snap_wan_length(wish.choreography.duration_frames)
    msg = (
        f"Master draft: {dest.name}\n"
        f"Промпт: {action[:200]}…\n"
        f"Кадр: {DRAFT_SIZE[0]}×{DRAFT_SIZE[1]}, {length}f @ {wish.choreography.fps}fps"
    )
    return True, msg, dest


def _update_catalog_master_draft(config: Config, wish: InteractionWish, video: Path) -> None:
    from .paths import interaction_catalog_path
    from .store import InteractionCatalogStore

    store = InteractionCatalogStore(interaction_catalog_path(config)).load()
    cur = store.get_by_slug(wish.slug)
    if cur is None:
        return
    cur.master_ref_draft = str(video)
    if cur.status in ("wished", "blocking_done"):
        cur.status = STATUS_MASTER_DRAFT
    store.upsert(cur)
    store.save()


def run_interaction_master_draft(
    config: Config,
    wish: InteractionWish,
    *,
    timeout: float = 1200.0,
) -> Tuple[bool, str]:
    blocking_blend = Path(wish.blocking_blend) if wish.blocking_blend else None
    if blocking_blend is None or not blocking_blend.is_file():
        blend_guess = interaction_scene_dir(config, wish.slug) / "blocking" / "blocking.blend"
        if not blend_guess.is_file():
            return (
                False,
                "Сначала blocking (`interaction_blocking`). Нужен blocking.blend.",
            )

    ok, msg, video = run_master_draft_comfy(config, wish, timeout=timeout)
    if not ok:
        return False, msg
    _update_catalog_master_draft(config, wish, video)
    return True, msg + f"\nФайл: {video}"
