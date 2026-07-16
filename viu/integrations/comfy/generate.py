"""Тройная генерация MoCap: 3 дубля в ракурсе ¾ (разный seed + вариация промпта)."""

from __future__ import annotations

import hashlib
import shutil
import time
from pathlib import Path
from typing import Any, Dict, List, Tuple

from ...config import Config
from .angles import CameraAngle, default_angles
from .client import ComfyClient, ComfyError
from .model_pref import choose_workflow_name
from .paths import comfy_out_dir, comfy_refs_dir
from .prompts import diversify_action, mocap_negative, mocap_prompt
from .workflows import (
    inject_negative_prompt,
    inject_seed,
    inject_text_prompt,
    load_workflow,
    prepare_mocap_workflow,
)


def _client(config: Config) -> ComfyClient:
    url = getattr(config, "comfy_url", None) or "http://127.0.0.1:8188"
    return ComfyClient(base_url=str(url))


def _seed_for(action: str, take_id: str, *, salt: str = "") -> int:
    h = hashlib.sha256(f"{action}|{take_id}|{salt}".encode("utf-8")).hexdigest()
    return int(h[:8], 16) % (2**31 - 1)


def run_single_angle(
    config: Config,
    *,
    action: str,
    angle: CameraAngle,
    slug: str,
    workflow_name: str | None = None,
    timeout: float = 900.0,
    seed_salt: str = "",
) -> Tuple[bool, str, List[str]]:
    prompt = mocap_prompt(action, angle)
    negative = mocap_negative()
    wf_name = workflow_name or choose_workflow_name(config, has_seed_image=False)
    try:
        wf = load_workflow(config, wf_name)
    except (FileNotFoundError, ValueError, OSError) as exc:
        return False, str(exc), []

    wf = inject_text_prompt(wf, prompt)
    wf = inject_negative_prompt(wf, negative)
    wf = inject_seed(wf, _seed_for(action, angle.id, salt=seed_salt or slug))
    wf = prepare_mocap_workflow(wf, action=action)

    client = _client(config)
    ok, ping = client.ping()
    if not ok:
        return False, ping, []

    try:
        prompt_id = client.queue_prompt(wf)
        entry = client.wait_history(prompt_id, timeout=timeout)
        files = client.collect_output_files(entry)
    except ComfyError as exc:
        return False, str(exc), []

    if not files:
        return (
            False,
            f"prompt_id={prompt_id} без outputs (угол {angle.id}). "
            "Проверь SaveVideo / VHS_VideoCombine в workflow.",
            [],
        )

    files = sorted(
        files,
        key=lambda m: (
            0 if str(m.get("filename", "")).lower().endswith(".mp4") else 1,
            0 if m.get("kind") == "videos" else 1,
            m.get("filename") or "",
        ),
    )
    if any(str(m.get("filename", "")).lower().endswith(".mp4") for m in files):
        files = [m for m in files if str(m.get("filename", "")).lower().endswith(".mp4")]

    refs = comfy_refs_dir(config)
    out_dir = comfy_out_dir(config)
    saved: List[str] = []
    for i, meta in enumerate(files):
        ext = Path(meta["filename"]).suffix or ".mp4"
        name = f"{slug}_{angle.id}_{i}{ext}"
        dest_out = out_dir / name
        try:
            client.download_view(
                meta["filename"],
                subfolder=meta.get("subfolder") or "",
                folder_type=meta.get("type") or "output",
                dest=dest_out,
            )
        except ComfyError as exc:
            return False, str(exc), saved
        dest_ref = refs / name
        try:
            shutil.copy2(dest_out, dest_ref)
        except OSError:
            dest_ref = dest_out
        saved.append(str(dest_ref))

    return True, f"{angle.id}: prompt_id={prompt_id} → {len(saved)} файл(ов)", saved


def run_triple_angles(
    config: Config,
    *,
    action: str,
    slug: str | None = None,
    timeout_each: float = 900.0,
) -> Tuple[bool, str, Dict[str, Any]]:
    """Три дубля ¾ подряд (разный seed + вариация действия)."""
    angles = default_angles()
    base_slug = (slug or "mocap").strip() or "mocap"
    stamp = time.strftime("%Y%m%d_%H%M%S")
    slug_full = f"{base_slug}_{stamp}"
    results: Dict[str, Any] = {
        "action": action,
        "slug": slug_full,
        "angles": {},
        "files": [],
        "mode": "three_quarter_takes",
    }
    lines: List[str] = [f"Comfy ×{len(angles)} дубля (¾) — «{action[:80]}»"]
    any_ok = False
    for i, angle in enumerate(angles):
        take_action = diversify_action(action, i)
        ok, msg, files = run_single_angle(
            config,
            action=take_action,
            angle=angle,
            slug=slug_full,
            timeout=timeout_each,
            seed_salt=f"{stamp}|{i}|{angle.id}",
        )
        results["angles"][angle.id] = {
            "ok": ok,
            "msg": msg,
            "files": files,
            "label": angle.label_ru,
            "action_variant": take_action,
        }
        results["files"].extend(files)
        mark = "OK" if ok else "FAIL"
        lines.append(f"  [{mark}] {angle.label_ru} ({angle.id}): {msg}")
        if files:
            lines.extend(f"      • {p}" for p in files)
        any_ok = any_ok or ok
    return any_ok, "\n".join(lines), results
