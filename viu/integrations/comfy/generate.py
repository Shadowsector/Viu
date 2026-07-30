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
    prompt_override: str = "",
    negative_override: str = "",
    seed_image_name: str = "",
    render_profile: str = "mocap",
    show_style: str = "realism",
) -> Tuple[bool, str, List[str]]:
    from .show_profile import (
        PROFILE_SHOW,
        find_show_unet,
        normalize_profile,
        show_negative,
        show_positive,
    )

    show = normalize_profile(render_profile) == PROFILE_SHOW
    from ...lab.comfy_pipeline import COMFY_TOPIC
    from ...lab.session import load_session
    from .shoot_settings import (
        DEFAULT_MOCAP_FRAMES,
        length_from_meta,
        resolve_workflow_for_shoot,
        unet_from_meta,
    )
    from .show_profile import SHOW_LENGTH

    sess = load_session(config, COMFY_TOPIC)
    meta = sess.meta if sess is not None and isinstance(sess.meta, dict) else {}
    unet_name = unet_from_meta(meta)
    unet_note = ""
    if unet_name:
        unet_note = f"чекпоинт: {unet_name}"
    elif show:
        unet_name, unet_note = find_show_unet(config)

    if show:
        if (prompt_override or "").strip():
            prompt = prompt_override.strip()
        else:
            prompt = show_positive(
                action, style=show_style, has_smoothmix=bool(unet_name)
            )
        negative = (
            negative_override.strip()
            if (negative_override or "").strip()
            else show_negative(style=show_style)
        )
    else:
        prompt = mocap_prompt(action, angle, positive_override=prompt_override)
        negative = mocap_negative(negative_override=negative_override)
    from .lora import append_trigger_words, ensure_lora_files

    loras = list(lora_specs or [])
    loras_ok, lora_notes = ensure_lora_files(config, loras, auto_fetch=False)
    if loras and not loras_ok:
        return False, "LoRA: " + "; ".join(lora_notes), []
    prompt = append_trigger_words(prompt, loras)

    from .naming import comfy_filename_prefix, display_video_stem, normalize_slug_for_name

    base_slug = normalize_slug_for_name(catalog_slug or slug)
    if show and base_slug in ("", "mocap", "chat_scene"):
        base_slug = "show"
    display_stem = display_video_stem(
        catalog_slug=base_slug,
        enters_from=enters_from,
        looped=looped,
        take_id=angle.id,
        seq=seq,
    )
    file_prefix = comfy_filename_prefix(display_stem)
    if show:
        if "show" not in file_prefix.lower() and not file_prefix.lower().startswith("girl"):
            file_prefix = f"viu_show_{base_slug}_{angle.id}"
    elif file_prefix == "viu_mocap" or not file_prefix.lower().startswith("girl"):
        file_prefix = comfy_filename_prefix(
            display_video_stem(
                catalog_slug=base_slug or "mocap",
                enters_from=enters_from,
                looped=looped,
                take_id=angle.id,
                seq=seq,
            )
        )

    has_seed = bool((seed_image_name or "").strip())
    wf_name, mode_note = resolve_workflow_for_shoot(
        config, meta, has_seed=has_seed, is_show=show
    )
    if workflow_name:
        wf_name = workflow_name
    use_i2v = has_seed and wf_name == "i2v"
    try:
        wf = load_workflow(config, wf_name)
    except (FileNotFoundError, ValueError, OSError) as exc:
        return False, str(exc), []

    wf = inject_text_prompt(wf, prompt)
    wf = inject_negative_prompt(wf, negative)
    wf = inject_seed(wf, _seed_for(action, angle.id, salt=seed_salt or slug))

    client = _client(config)
    ok, ping = client.ping()
    if not ok:
        return False, ping, []

    lora_note = ""
    use_loras = list(loras or [])
    if use_loras:
        from .lora import resolve_specs_for_comfy

        resolved, notes, errors = resolve_specs_for_comfy(client, list(use_loras))
        if errors:
            detail = "\n".join(f"  • {e}" for e in errors[:6])
            return (
                False,
                (
                    "LoRA не из списка Comfy — /prompt получит 400 value_not_in_list.\n"
                    f"{detail}\n"
                    "Сделай comfy_lora_scan, выбери LoRA заново (lora: N) или lora: none.\n"
                    "Если файл на диске есть, а в списке Comfy нет — перезапусти Comfy "
                    "(comfy_ensure restart=1)."
                ),
                [],
            )
        use_loras = resolved
        if notes:
            lora_note = "; ".join(notes[:4])

    from .lora import fetch_comfy_lora_names

    comfy_names = fetch_comfy_lora_names(client) if use_loras else []
    wf = inject_loras(wf, use_loras, comfy_lora_names=comfy_names)
    if use_i2v and wf_name == "i2v":
        from .workflows import inject_end_seed_image, inject_seed_image

        wf = inject_seed_image(wf, seed_image_name.strip())
        # Конечный эталон — если нода/шаблон умеет end_image.
        end_name = str(meta.get("i2v_end_seed_comfy") or "").strip()
        if end_name:
            wf = inject_end_seed_image(wf, end_name)

    length_frames = length_from_meta(
        meta, default=SHOW_LENGTH if show else DEFAULT_MOCAP_FRAMES
    )
    if show:
        from .workflows import prepare_show_workflow

        wf = prepare_show_workflow(
            wf,
            filename_prefix=file_prefix,
            unet_name=unet_name or "",
            length=length_frames,
        )
    else:
        wf = prepare_mocap_workflow(
            wf,
            action=action,
            filename_prefix=file_prefix,
            length=length_frames,
            unet_name=unet_name or "",
        )
    from .workflows import inject_filename_prefix

    # Повторно вшить префикс: импортированные графы иногда оставляют viu_mocap.
    wf = inject_filename_prefix(wf, file_prefix)

    face_note = ""
    i2v_note = mode_note
    if use_i2v and wf_name == "i2v":
        i2v_note = ((i2v_note + "; ") if i2v_note else "") + f"I2V seed={seed_image_name.strip()}"
    elif has_seed and wf_name != "i2v":
        i2v_note = ((i2v_note + "; ") if i2v_note else "") + "эталон есть, но I2V не готов — T2V"
    if show and unet_note:
        i2v_note = ((i2v_note + "; ") if i2v_note else "") + f"шоу: {unet_note}"
    i2v_note = ((i2v_note + "; ") if i2v_note else "") + f"length={length_frames}"

    from .face_refs import (
        face_swap_enabled,
        inswapper_model_path,
        pick_face_ref,
        reactor_face_swap_class,
        stage_face_for_comfy,
    )

    if face_swap_enabled():
        face = pick_face_ref(config, seed=f"{slug}|{catalog_slug or base_slug}")
        if face is not None:
            ok_face, stage_msg, input_name = stage_face_for_comfy(config, face)
            reactor_cls = reactor_face_swap_class(client)
            inswap = inswapper_model_path(config)
            if ok_face and reactor_cls and inswap:
                wf = inject_face_swap(
                    wf, face_image=input_name, reactor_class=reactor_cls
                )
                face_note = f"лицо: {face.name} (ReActor {reactor_cls})"
            elif ok_face and reactor_cls and not inswap:
                face_note = (
                    f"лицо {face.name}, ReActor есть, но нет inswapper_128.onnx — "
                    "comfy_install reactor=1"
                )
            elif ok_face and not reactor_cls:
                face_note = (
                    f"лицо {face.name} в input, но ReActor не в Comfy — "
                    "comfy_ensure (перезапуск) или comfy_install reactor=1"
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

        from .video_health import reactor_black_frame_hint, validate_mocap_mp4

        v_ok, v_msg = validate_mocap_mp4(dest_ref)
        if not v_ok:
            hint = reactor_black_frame_hint() if face_note else ""
            return (
                False,
                f"битый mp4 угол {angle.id}: {v_msg}. {hint}".strip(),
                saved,
            )

        saved.append(str(dest_ref))

    note = f"{angle.id}: → Lab/Refs ({len(saved)} файл(ов))"
    if i2v_note:
        note += f" [{i2v_note}]"
    if face_note:
        note += f" [{face_note}]"
    if lora_note:
        note += f" [{lora_note}]"
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
    prompt_override: str = "",
    negative_override: str = "",
    seed_image_name: str = "",
) -> Tuple[bool, str, Dict[str, Any]]:
    """Пять дублей ¾ (MoCap) или 1 шоу-дубль."""
    from .naming import next_kept_seq, normalize_slug_for_name
    from .queue_manage import prepare_queue_for_slug
    from .seed_pose import resolve_active_seed, stage_seed_for_comfy
    from .show_profile import (
        is_show_profile,
        show_angles,
        show_style_from_meta,
        show_take_count,
    )
    from ...lab.comfy_pipeline import COMFY_TOPIC
    from ...lab.session import load_session

    sess = load_session(config, COMFY_TOPIC)
    meta = sess.meta if sess is not None and isinstance(sess.meta, dict) else {}
    show = is_show_profile(meta)
    style = show_style_from_meta(meta)
    angles = show_angles() if show else default_angles()
    base_slug = normalize_slug_for_name(catalog_slug or slug or ("show" if show else "mocap"))
    client = _client(config)
    queue_note = prepare_queue_for_slug(client, base_slug)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    slug_full = f"{base_slug}_{stamp}"
    seq = next_kept_seq(config, base_slug)

    seed_name = (seed_image_name or "").strip()
    seed_path, seed_comfy, seed_on = resolve_active_seed(config)
    from .shoot_settings import MODE_T2V, mode_needs_seed, shoot_mode_from_meta

    mode = shoot_mode_from_meta(meta)
    # Правило эталона:
    # - i2v/i2i → всегда, если есть
    # - mocap + t2v (дефолт) → как раньше: подхватить эталон если есть (I2V когда готов)
    # - шоу + t2v → без эталона; шоу + i2v → с эталоном
    use_seed = False
    if mode_needs_seed(mode):
        use_seed = True
    elif not show and mode == MODE_T2V:
        use_seed = True  # совместимость mocap: seed → I2V
    if use_seed and not seed_name and seed_on and seed_path is not None:
        ok_s, _msg_s, staged = stage_seed_for_comfy(config, seed_path)
        if ok_s:
            seed_name = staged or seed_comfy
    if not use_seed:
        seed_name = ""

    results: Dict[str, Any] = {
        "action": action,
        "slug": slug_full,
        "catalog_slug": base_slug,
        "enters_from": list(enters_from or []),
        "looped": looped,
        "seq": seq,
        "angles": {},
        "files": [],
        "mode": "show_double" if show else "three_quarter_takes",
        "render_profile": "show" if show else "mocap",
        "shoot_mode": mode,
        "i2v_seed": seed_name,
    }
    n = show_take_count() if show else len(angles)
    lines: List[str] = [
        f"Comfy ×{n} "
        + ("шоу-дубль" if show else "дубля (¾)")
        + f" — «{action[:80]}»"
    ]
    if show:
        lines.append(f"Профиль: ШОУ ({style})")
    lines.append(f"Режим: {mode}")
    if seed_name:
        lines.append(f"Эталон I2V: {seed_name}")
    if queue_note:
        lines.insert(0, queue_note)
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
            prompt_override=prompt_override,
            negative_override=negative_override,
            seed_image_name=seed_name,
            render_profile="show" if show else "mocap",
            show_style=style,
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

    from .vision_review import review_triple_results, vision_review_enabled

    if vision_review_enabled() and any_ok:
        results, vision_msg = review_triple_results(config, results, action=action)
        if vision_msg:
            lines.append(vision_msg)
        if not (results.get("files") or []):
            any_ok = False
            lines.append("⏸ Vision отклонила все дубли — переснять или VIU_COMFY_VISION=0.")

    return any_ok, "\n".join(lines), results
