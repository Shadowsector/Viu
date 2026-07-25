"""Авто-перерисовка эталона HS2 → натуральное тело через Comfy img2img (SD checkpoint)."""

from __future__ import annotations

import json
import random
import shutil
from pathlib import Path
from typing import List, Optional, Tuple

from ...config import Config
from .client import ComfyClient, ComfyError
from .paths import comfy_input_dir, resolve_comfy_root

_IN_NAME = "viu_seed_refine_in.png"
_TEMPLATE = "seed_refine_img2img.json"

# Предпочитаем реалистичные чекпоинты, если лежат в models/checkpoints.
_CKPT_PREFER = (
    "juggernaut",
    "epicrealism",
    "realistic",
    "realvis",
    "photon",
    "absolutereality",
    "dreamshaper",
    "sdxl",
    "v1-5",
    "sd15",
)

REFINE_POSITIVE = (
    "natural realistic body proportions, soft skin, photorealistic young woman figure, "
    "full body visible, white seamless studio background, detailed anatomy, "
    "keep exact pose and camera angle, not anime, not doll, not plastic"
)

REFINE_NEGATIVE = (
    "anime, cartoon, cel shade, doll face, plastic skin, oversmoothed, "
    "deformed limbs, extra fingers, missing limbs, cropped head, face closeup, "
    "text, watermark, lowres, blurry"
)


def list_checkpoints(config: Config) -> List[str]:
    root = resolve_comfy_root(config)
    if root is None:
        return []
    folder = root / "models" / "checkpoints"
    if not folder.is_dir():
        return []
    names = [
        p.name
        for p in folder.iterdir()
        if p.is_file() and p.suffix.lower() in (".safetensors", ".ckpt", ".pt")
    ]
    return sorted(names, key=str.lower)


def pick_checkpoint(config: Config, *, preferred: str = "") -> str:
    names = list_checkpoints(config)
    if not names:
        return ""
    if preferred and preferred in names:
        return preferred
    low_map = {n.lower(): n for n in names}
    for needle in _CKPT_PREFER:
        for low, orig in low_map.items():
            if needle in low:
                return orig
    return names[0]


def refine_ready(config: Config) -> Tuple[bool, str]:
    """Можно ли гонять авто-доработку. ok → (True, ckpt_name)."""
    root = resolve_comfy_root(config)
    if root is None:
        return False, "ComfyUI не найден (U:\\Viu\\ComfyUI)."
    ckpt = pick_checkpoint(config)
    if not ckpt:
        return False, (
            "Нет SD-чекпоинта в ComfyUI\\models\\checkpoints\\.\n"
            "Положи туда realistic / Juggernaut / EpicRealism (.safetensors) — "
            "Wan video для перерисовки кадра не подходит.\n"
            "Потом «Поднять ComfyUI» и снова «Авто-доработать»."
        )
    return True, ckpt


def _comfy_url(config: Config) -> str:
    import os

    raw = (
        os.environ.get("VIU_COMFY_URL")
        or getattr(config, "comfy_url", "")
        or "http://127.0.0.1:8188"
    )
    return str(raw).rstrip("/")


def _load_refine_template() -> dict:
    path = Path(__file__).resolve().parent / "templates" / _TEMPLATE
    return json.loads(path.read_text(encoding="utf-8"))


def build_refine_workflow(
    *,
    ckpt_name: str,
    image_name: str,
    positive: str,
    negative: str,
    denoise: float = 0.48,
    seed: int = 0,
) -> dict:
    wf = _load_refine_template()
    wf["4"]["inputs"]["ckpt_name"] = ckpt_name
    wf["10"]["inputs"]["image"] = image_name
    wf["6"]["inputs"]["text"] = positive
    wf["7"]["inputs"]["text"] = negative
    wf["3"]["inputs"]["denoise"] = float(denoise)
    wf["3"]["inputs"]["seed"] = int(seed) if seed else random.randint(1, 2**31 - 1)
    return wf


def stage_refine_input(config: Config, source: Path) -> Tuple[bool, str, str]:
    root = resolve_comfy_root(config)
    if root is None:
        return False, "ComfyUI root не найден", ""
    if not source.is_file():
        return False, f"нет файла: {source}", ""
    dest = comfy_input_dir(root) / _IN_NAME
    try:
        shutil.copy2(source, dest)
    except OSError as exc:
        return False, f"не скопировать в Comfy input: {exc}", ""
    return True, str(dest), _IN_NAME


def run_seed_refine(
    config: Config,
    source: Path,
    *,
    en_pose: str = "",
    denoise: float = 0.48,
    timeout: float = 300.0,
    ckpt_name: str = "",
) -> Tuple[bool, str, Optional[Path]]:
    """Прогнать img2img → PNG во временный файл рядом с seeds."""
    ok_r, ready_msg = refine_ready(config)
    if not ok_r:
        return False, ready_msg, None
    ckpt = ckpt_name or ready_msg
    if ckpt_name and ckpt_name not in list_checkpoints(config):
        return False, f"Чекпоинт не найден: {ckpt_name}", None

    ok_s, msg_s, in_name = stage_refine_input(config, source)
    if not ok_s:
        return False, msg_s, None

    positive = REFINE_POSITIVE
    if (en_pose or "").strip():
        positive = f"{en_pose.strip()}, {REFINE_POSITIVE}"

    client = ComfyClient(_comfy_url(config))
    ok_ping, ping = client.ping()
    if not ok_ping:
        return False, ping + "\nСначала «Поднять ComfyUI».", None

    wf = build_refine_workflow(
        ckpt_name=ckpt,
        image_name=in_name,
        positive=positive,
        negative=REFINE_NEGATIVE,
        denoise=denoise,
    )
    try:
        prompt_id = client.queue_prompt(wf)
        entry = client.wait_history(prompt_id, timeout=timeout)
        files = client.collect_output_files(entry)
    except ComfyError as exc:
        return False, str(exc), None

    images = [
        m
        for m in files
        if str(m.get("filename", "")).lower().endswith((".png", ".jpg", ".jpeg", ".webp"))
    ]
    if not images:
        return False, f"prompt_id={prompt_id} без картинки в outputs (ckpt={ckpt}).", None

    meta = images[0]
    from .seed_library import seeds_root

    dest = seeds_root(config) / "raw" / f"refine_out_{prompt_id[:8]}.png"
    try:
        client.download_view(
            meta["filename"],
            subfolder=meta.get("subfolder") or "",
            folder_type=meta.get("type") or "output",
            dest=dest,
        )
    except ComfyError as exc:
        return False, str(exc), None

    return True, f"img2img OK (ckpt={ckpt}, denoise={denoise})", dest


def auto_refine_seed(
    config: Config,
    seed_id: str,
    *,
    denoise: float = 0.48,
    activate: bool = False,
    timeout: float = 300.0,
) -> Tuple[bool, str]:
    """Vision-бриф + Comfy img2img + принять доработанный эталон."""
    from .seed_library import (
        accept_refined,
        get_entry,
        prepare_refine,
        upsert_entry,
    )

    entry = get_entry(config, seed_id)
    if entry is None:
        return False, f"Нет эталона id={seed_id}"

    # Бриф / en_pose (не падаем, если vision нет).
    prepare_refine(config, seed_id)
    entry = get_entry(config, seed_id) or entry
    entry.status = "refining"
    upsert_entry(config, entry)

    src = Path(entry.raw_path) if entry.raw_path else entry.resolve_path()
    if src is None or not src.is_file():
        entry.status = "needs_refine"
        upsert_entry(config, entry)
        return False, "Нет исходного файла для img2img."

    ok, msg, out = run_seed_refine(
        config,
        src,
        en_pose=entry.en_pose,
        denoise=denoise,
        timeout=timeout,
    )
    if not ok or out is None:
        entry.status = "needs_refine"
        entry.notes = ((entry.notes or "") + f"\n\nАвто-img2img fail: {msg}").strip()
        upsert_entry(config, entry)
        return False, msg

    ok2, msg2 = accept_refined(config, seed_id, out, activate=activate)
    if not ok2:
        return False, msg2
    return True, f"{msg}\n{msg2}"
