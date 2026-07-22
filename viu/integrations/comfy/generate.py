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
    inject_face_swap,
    inject_loras,
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
    catalog_slug: str = "",
    enters_from: list | None = None,
    looped: bool = False,
    seq: int = 0,
    lora_specs: list | None = None,
    length_override: int | None = None,
) -> Tuple[bool, str, List[str]]:
    prompt = mocap_prompt(action, angle)
    negative = mocap_negative()
    from .lora import append_trigger_words, ensure_lora_files

    loras = list(lora_specs or [])
    loras_ok, lora_notes = ensure_lora_files(config, loras, auto_fetch=False)
    if loras and not loras_ok:
        return False, "LoRA: " + "; ".join(lora_notes), []
    prompt = append_trigger_words(prompt, loras)

    from .naming import comfy_filename_prefix, display_video_stem, normalize_slug_for_name

    base_slug = normalize_slug_for_name(catalog_slug or slug)
    display_stem = display_video_stem(
        catalog_slug=base_slug,
        enters_from=enters_from,
        looped=looped,
        take_id=angle.id,
        seq=seq,
    )
    file_prefix = comfy_filename_prefix(display_stem)

    wf_name = workflow_name or choose_workflow_name(config, has_seed_image=False)
    try:
        wf = load_workflow(config, wf_name)
    except (FileNotFoundError, ValueError, OSError) as exc:
        return False, str(exc), []

    wf = inject_text_prompt(wf, prompt)
    wf = inject_negative_prompt(wf, negative)
    wf = inject_seed(wf, _seed_for(action, angle.id, salt=seed_salt or slug))
    wf = inject_loras(wf, loras)
    wf = inject_loras(wf, loras)
    wf = prepare_mocap_workflow(
        wf, action=action, filename_prefix=file_prefix, length_override=length_override
    )

    client = _client(config)
    ok, ping = client.ping()
    if not ok:
        return False, ping, []

    face_note = ""
    from .face_refs import face_swap_enabled, pick_face_ref, stage_face_for_comfy

    if face_swap_enabled():
        face = pick_face_ref(config, seed=f"{slug}|{catalog_slug or base_slug}")
        if face is not None:
            ok_face, stage_msg, input_name = stage_face_for_comfy(config, face)
            if ok_face and client.has_node_class("ReActorFaceSwap"):
                wf = inject_face_swap(wf, face_image=input_name)
                face_note = f"лицо: {face.name}"
            elif ok_face:
                face_note = (
                    f"лицо {face.name} в input, но ReActor нет — comfy_install reactor=1"
                )
            else:
                face_note = stage_msg

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
    copy_notes: List[str] = []
    for i, meta in enumerate(files):
        ext = Path(meta["filename"]).suffix or ".mp4"
        name = f"{display_stem}{ext}" if i == 0 else f"{display_stem}_{i}{ext}"
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
        copied = False
        try:
            shutil.copy2(dest_out, dest_ref)
            copied = dest_ref.is_file()
        except OSError as exc:
            copy_notes.append(f"copy Lab/ComfyOut→Refs fail: {exc}")

        # Fallback: взять файл прямо из U:\Viu\ComfyUI\output\ (native SaveVideo)
        if not copied:
            from .paths import resolve_comfy_root

            root = resolve_comfy_root(config)
            native_name = str(meta.get("filename") or "")
            sub = str(meta.get("subfolder") or "").strip().replace("\\", "/").lstrip("/")
            candidates: List[Path] = []
            if root is not None and native_name:
                base = root / "output"
                if sub:
                    candidates.append(base / sub / native_name)
                candidates.append(base / native_name)
            candidates.append(dest_out)
            for src in candidates:
                if not src.is_file():
                    continue
                try:
                    shutil.copy2(src, dest_out)
                    shutil.copy2(src, dest_ref)
                    if dest_ref.is_file():
                        copied = True
                        copy_notes.append(f"ComfyOut+Refs ← {src}")
                        break
                except OSError as exc:
                    copy_notes.append(f"native copy fail {src.name}: {exc}")

        if not copied:
            return (
                False,
                f"не скопировать в Lab/Refs ({dest_ref}). "
                f"Native Comfy: output/; staging: {dest_out}. "
                + "; ".join(copy_notes),
                saved,
            )
        saved.append(str(dest_ref))

    note = f"{angle.id}: → Lab/Refs ({len(saved)} файл(ов))"
    if face_note:
        note += f" [{face_note}]"
    if copy_notes:
        note += " [" + "; ".join(copy_notes[:3]) + "]"
    return True, note, saved


def run_triple_angles(
    config: Config,
    *,
    action: str,
    slug: str | None = None,
    catalog_slug: str = "",
    enters_from: list | None = None,
    looped: bool = False,
    timeout_each: float = 900.0,
    lora_specs: list | None = None,
) -> Tuple[bool, str, Dict[str, Any]]:
    """Три дубля ¾ подряд (разный seed + вариация действия)."""
    from .naming import next_kept_seq, normalize_slug_for_name

    angles = default_angles()
    base_slug = normalize_slug_for_name(catalog_slug or slug or "mocap")
    stamp = time.strftime("%Y%m%d_%H%M%S")
    slug_full = f"{base_slug}_{stamp}"
    seq = next_kept_seq(config, base_slug)
    results: Dict[str, Any] = {
        "action": action,
        "slug": slug_full,
        "catalog_slug": base_slug,
        "enters_from": list(enters_from or []),
        "looped": looped,
        "seq": seq,
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
            catalog_slug=base_slug,
            enters_from=enters_from,
            looped=looped,
            seq=seq,
            timeout=timeout_each,
            seed_salt=f"{stamp}|{i}|{angle.id}",
            lora_specs=lora_specs,
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


def run_mocap_preview(
    config: Config,
    *,
    action: str,
    catalog_slug: str = "",
    enters_from: list | None = None,
    looped: bool = False,
    lora_specs: list | None = None,
    timeout: float | None = None,
) -> Tuple[bool, str, Dict[str, Any]]:
    """Короткий preview-клип ¾ перед полными 3 дублями."""
    from .angles import angle_by_id
    from .framing import frame_spec_for_action

    if timeout is None:
        import os

        try:
            timeout = float(os.environ.get("VIU_COMFY_PREVIEW_TIMEOUT", "900"))
        except ValueError:
            timeout = 900.0

    spec = frame_spec_for_action(action, preview=True)
    angle = angle_by_id("take_b") or default_angles()[1]
    stamp = time.strftime("%Y%m%d_%H%M%S")
    base_slug = catalog_slug or "mocap"
    slug = f"{base_slug}_preview_{stamp}"
    ok, msg, files = run_single_angle(
        config,
        action=action,
        angle=angle,
        slug=slug,
        catalog_slug=base_slug,
        enters_from=enters_from,
        looped=looped,
        seq=0,
        timeout=timeout,
        seed_salt=f"preview|{stamp}",
        lora_specs=lora_specs,
        length_override=spec.length,
    )
    results: Dict[str, Any] = {
        "action": action,
        "slug": slug,
        "video": files[0] if files else "",
        "still": "",
        "spec": {
            "width": spec.width,
            "height": spec.height,
            "length": spec.length,
            "fps": spec.fps,
        },
    }
    if not ok or not files:
        return False, msg, results

    from .preview import extract_preview_still

    video = Path(files[0])
    still_ok, still_path = extract_preview_still(video)
    if still_ok:
        results["still"] = still_path
    line = (
        f"Preview MoCap ({spec.summary_ru()}): {msg}"
        + (f"\n  кадр: {still_path}" if still_ok else "")
    )
    return True, line, results
