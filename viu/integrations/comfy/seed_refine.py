"""Авто-перерисовка эталона HS2 → натуральное тело через Comfy img2img (SDXL).

Канон: Juggernaut XL (RunDiffusion) в ComfyUI/models/checkpoints/.
"""

from __future__ import annotations

import json
import os
import random
import shutil
from pathlib import Path
from typing import Callable, List, Optional, Tuple

from ...config import Config
from .client import ComfyClient, ComfyError
from .paths import comfy_input_dir, resolve_comfy_root

_IN_NAME = "viu_seed_refine_in.png"
_TEMPLATE = "seed_refine_img2img.json"

# Канонический файл + зеркало с HuggingFace (single-file для Comfy).
JUGGERNAUT_XL_FILENAME = "Juggernaut-XL_v9_RunDiffusionPhoto_v2.safetensors"
JUGGERNAUT_XL_URL = (
    "https://huggingface.co/RunDiffusion/Juggernaut-XL-v9/resolve/main/"
    "Juggernaut-XL_v9_RunDiffusionPhoto_v2.safetensors"
)

# Предпочитаем Juggernaut XL, потом прочий realistic SDXL.
_CKPT_PREFER = (
    "juggernaut-xl",
    "juggernaut_xl",
    "juggernautxl",
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

ProgressCb = Optional[Callable[[str], None]]

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


def checkpoints_dir(config: Config) -> Optional[Path]:
    root = resolve_comfy_root(config)
    if root is None:
        return None
    folder = root / "models" / "checkpoints"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def list_checkpoints(config: Config) -> List[str]:
    folder = checkpoints_dir(config)
    if folder is None or not folder.is_dir():
        return []
    names = [
        p.name
        for p in folder.iterdir()
        if p.is_file() and p.suffix.lower() in (".safetensors", ".ckpt", ".pt")
    ]
    return sorted(names, key=str.lower)


def _score_ckpt(name: str) -> int:
    low = name.lower()
    score = 0
    if "juggernaut" in low and ("xl" in low or "xi" in low):
        score += 100
    elif "juggernaut" in low:
        score += 80
    for i, needle in enumerate(_CKPT_PREFER):
        if needle in low:
            score += 50 - i
            break
    if "xl" in low or "sdxl" in low:
        score += 10
    return score


def pick_checkpoint(config: Config, *, preferred: str = "") -> str:
    names = list_checkpoints(config)
    if not names:
        return ""
    env = (os.environ.get("VIU_SEED_REFINE_CKPT") or "").strip()
    if preferred and preferred in names:
        return preferred
    if env and env in names:
        return env
    # Точное каноническое имя, если уже скачали.
    if JUGGERNAUT_XL_FILENAME in names:
        return JUGGERNAUT_XL_FILENAME
    ranked = sorted(names, key=lambda n: (-_score_ckpt(n), n.lower()))
    return ranked[0] if ranked else ""


def find_external_juggernaut(config: Config) -> Optional[Path]:
    """Ищем уже скачанный Juggernaut XL вне Comfy (A1111 / Forge / ручная папка)."""
    candidates: List[Path] = []
    env_dir = (os.environ.get("VIU_SDXL_CKPT_DIR") or "").strip()
    if env_dir:
        candidates.append(Path(env_dir))
    viu = resolve_comfy_root(config)
    parents: List[Path] = []
    if viu is not None:
        parents.extend([viu.parent, viu.parent.parent])
    for base in parents:
        candidates.extend(
            [
                base / "stable-diffusion-webui" / "models" / "Stable-diffusion",
                base / "webui" / "models" / "Stable-diffusion",
                base / "forge" / "models" / "Stable-diffusion",
                base / "SDXL" / "models" / "Stable-diffusion",
                base / "Models" / "Stable-diffusion",
                base / "Models" / "checkpoints",
            ]
        )
    # Типичные диски Windows
    for drive in ("U:/", "D:/", "C:/"):
        candidates.extend(
            [
                Path(drive) / "stable-diffusion-webui" / "models" / "Stable-diffusion",
                Path(drive) / "sd" / "models" / "Stable-diffusion",
                Path(drive) / "AI" / "models" / "Stable-diffusion",
            ]
        )
    seen: set[Path] = set()
    hits: List[Path] = []
    for folder in candidates:
        try:
            folder = folder.expanduser()
        except OSError:
            continue
        if folder in seen or not folder.is_dir():
            continue
        seen.add(folder)
        for p in folder.iterdir():
            if not p.is_file():
                continue
            if p.suffix.lower() != ".safetensors":
                continue
            low = p.name.lower()
            if "juggernaut" in low and ("xl" in low or "xi" in low):
                hits.append(p)
    if not hits:
        return None
    hits.sort(key=lambda p: (-_score_ckpt(p.name), -p.stat().st_size))
    return hits[0]


def ensure_juggernaut_xl(
    config: Config,
    *,
    download: bool = True,
    progress: ProgressCb = None,
) -> Tuple[bool, str]:
    """Гарантировать Juggernaut XL в Comfy checkpoints (локальная копия или HF)."""
    folder = checkpoints_dir(config)
    if folder is None:
        return False, "ComfyUI не найден — некуда класть Juggernaut XL."

    existing = pick_checkpoint(config)
    if existing and "juggernaut" in existing.lower():
        return True, f"Juggernaut уже в Comfy: {existing}"

    dest = folder / JUGGERNAUT_XL_FILENAME
    if dest.is_file() and dest.stat().st_size > 1_000_000_000:
        return True, f"уже есть: {dest.name}"

    ext = find_external_juggernaut(config)
    if ext is not None and ext.is_file():
        if progress:
            progress(f"Копирую локальный {ext.name} → Comfy checkpoints…")
        try:
            # Если имя уже каноническое — копируем как есть; иначе сохраняем имя файла.
            target = folder / ext.name
            if not target.is_file():
                shutil.copy2(ext, target)
            return True, f"взяла локальный Juggernaut: {target.name}"
        except OSError as exc:
            if progress:
                progress(f"копия не вышла ({exc}), пробую скачать…")

    if not download:
        return False, (
            f"Нет Juggernaut XL в {folder}.\n"
            "Положи .safetensors туда или задай VIU_SDXL_CKPT_DIR=папка_с_моделью."
        )

    if progress:
        progress(f"Качаю Juggernaut XL v9 (~7 GB) → {dest}…")
    from .install import _download

    ok, msg = _download(JUGGERNAUT_XL_URL, dest, progress=progress)
    if not ok:
        return False, (
            f"Не скачать Juggernaut XL: {msg}\n"
            "Скачай вручную с HuggingFace RunDiffusion/Juggernaut-XL-v9 "
            f"и положи в {folder}"
        )
    return True, msg


def refine_ready(config: Config) -> Tuple[bool, str]:
    """Можно ли гонять авто-доработку. ok → (True, ckpt_name)."""
    root = resolve_comfy_root(config)
    if root is None:
        return False, "ComfyUI не найден (U:\\Viu\\ComfyUI)."
    ckpt = pick_checkpoint(config)
    if ckpt:
        return True, ckpt
    return False, (
        "Нет SDXL-чекпоинта в ComfyUI\\models\\checkpoints\\.\n"
        "Жми «Поставить Juggernaut XL» (или comfy_install juggernaut=1) — "
        "возьму локальный или скачаю v9 с HuggingFace (~7 GB).\n"
        "Wan video для перерисовки кадра не подходит."
    )


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
    denoise: float = 0.45,
    seed: int = 0,
) -> dict:
    wf = _load_refine_template()
    wf["4"]["inputs"]["ckpt_name"] = ckpt_name
    wf["10"]["inputs"]["image"] = image_name
    wf["6"]["inputs"]["text"] = positive
    wf["7"]["inputs"]["text"] = negative
    wf["3"]["inputs"]["denoise"] = float(denoise)
    wf["3"]["inputs"]["seed"] = int(seed) if seed else random.randint(1, 2**31 - 1)
    # SDXL-friendly defaults (Juggernaut XL)
    low = ckpt_name.lower()
    if "xl" in low or "sdxl" in low or "juggernaut" in low:
        wf["3"]["inputs"]["steps"] = 32
        wf["3"]["inputs"]["cfg"] = 5.0
        wf["3"]["inputs"]["sampler_name"] = "dpmpp_2m"
        wf["3"]["inputs"]["scheduler"] = "karras"
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
    denoise: float = 0.45,
    timeout: float = 420.0,
    ckpt_name: str = "",
    ensure_ckpt: bool = True,
) -> Tuple[bool, str, Optional[Path]]:
    """Прогнать img2img → PNG во временный файл рядом с seeds."""
    ensure_note = ""
    if ensure_ckpt and not pick_checkpoint(config):
        ok_e, msg_e = ensure_juggernaut_xl(config, download=True)
        ensure_note = msg_e
        if not ok_e:
            return False, msg_e, None
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

    note = f"img2img OK (ckpt={ckpt}, denoise={denoise})"
    if ensure_note:
        note = ensure_note + "\n" + note
    return True, note, dest


def auto_refine_seed(
    config: Config,
    seed_id: str,
    *,
    denoise: float = 0.45,
    activate: bool = False,
    timeout: float = 420.0,
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
