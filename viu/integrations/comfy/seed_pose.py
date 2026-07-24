"""Эталонный кадр позы → Wan I2V + чеклист LoRA под MoCap."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import List, Optional, Tuple

from ...config import Config
from .model_pref import probe_models
from .paths import comfy_input_dir, comfy_seed_frames_dir, resolve_comfy_root

_COMFY_SEED_NAME = "viu_pose_seed.png"
_SEED_STATE = "comfy_i2v_seed.json"

MOCAP_LORA_CHECKLIST = """\
Чеклист LoRA под MoCap (не NSFW-кино):
• Бери: Wan 2.1 video / motion / pose / walk·sit·lie·quad gait
• Не бери: beauty, face closeup, cinematic camera, «best NSFW furry checkpoint»
• 1–2 LoRA на пул; если ломает конечности — none / чистый Wan
• Character LoRA — осторожно (пропорции); лучше ReActor FaceRefs
• LyCORIS/DoRA — только если Comfy грузит как обычный LoRA
• VAE/embeddings не крути: родной wan_2.1_vae + UMT5
• Эталонный кадр (I2V) сильнее десяти «красивых» LoRA
"""


def seed_state_path(config: Config) -> Path:
    return Path(config.data_dir) / _SEED_STATE


def load_seed_state(config: Config) -> dict:
    path = seed_state_path(config)
    if not path.is_file():
        return {"enabled": False, "path": "", "comfy_name": ""}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"enabled": False, "path": "", "comfy_name": ""}
    if not isinstance(data, dict):
        return {"enabled": False, "path": "", "comfy_name": ""}
    return {
        "enabled": bool(data.get("enabled")),
        "path": str(data.get("path") or ""),
        "comfy_name": str(data.get("comfy_name") or _COMFY_SEED_NAME),
    }


def save_seed_state(config: Config, *, enabled: bool, path: str = "", comfy_name: str = "") -> None:
    config.ensure_dirs()
    payload = {
        "enabled": bool(enabled),
        "path": str(path or ""),
        "comfy_name": str(comfy_name or _COMFY_SEED_NAME),
    }
    p = seed_state_path(config)
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(p)


def list_seed_frames(config: Config) -> List[Path]:
    root = comfy_seed_frames_dir(config)
    out: List[Path] = []
    for p in sorted(root.iterdir(), key=lambda x: x.stat().st_mtime if x.is_file() else 0, reverse=True):
        if p.is_file() and p.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp"):
            out.append(p)
    return out


def stage_seed_for_comfy(config: Config, seed_path: Path) -> Tuple[bool, str, str]:
    """Скопировать эталон в ComfyUI/input/viu_pose_seed.png."""
    root = resolve_comfy_root(config)
    if root is None:
        return False, "ComfyUI root не найден", ""
    if not seed_path.is_file():
        return False, f"нет файла эталона: {seed_path}", ""
    dest = comfy_input_dir(root) / _COMFY_SEED_NAME
    try:
        shutil.copy2(seed_path, dest)
    except OSError as exc:
        return False, f"не скопировать в Comfy input: {exc}", ""
    return True, str(dest), _COMFY_SEED_NAME


def set_pose_seed(
    config: Config,
    source: Path,
    *,
    slug: str = "",
) -> Tuple[bool, str]:
    """Принять PNG/JPG как эталон позы: Lab/Refs/seeds + Comfy input + state."""
    src = Path(source)
    if not src.is_file():
        return False, f"Файл не найден: {src}"
    if src.suffix.lower() not in (".png", ".jpg", ".jpeg", ".webp"):
        return False, "Нужен PNG/JPG/WebP (полный рост, белый фон, ¾)."

    seeds = comfy_seed_frames_dir(config)
    stem = (slug or src.stem or "pose").strip().replace(" ", "_")[:60] or "pose"
    dest = seeds / f"{stem}{src.suffix.lower()}"
    try:
        shutil.copy2(src, dest)
    except OSError as exc:
        return False, f"Не сохранить в Lab/Refs/seeds: {exc}"

    ok, msg, comfy_name = stage_seed_for_comfy(config, dest)
    if not ok:
        return False, msg

    save_seed_state(config, enabled=True, path=str(dest), comfy_name=comfy_name)

    from ...lab.comfy_pipeline import COMFY_TOPIC
    from ...lab.session import load_session, new_session, save_session

    session = load_session(config, COMFY_TOPIC) or new_session(COMFY_TOPIC)
    session.meta["i2v_seed_enabled"] = True
    session.meta["i2v_seed_path"] = str(dest)
    session.meta["i2v_seed_comfy"] = comfy_name
    save_session(config, session)

    probe = probe_models(config)
    ready = "I2V готов" if probe.ready_i2v else "I2V модели нет — пока T2V (comfy_install i2v=1)"
    return True, (
        f"Эталон позы: {dest.name}\n"
        f"Comfy input: {comfy_name}\n"
        f"{ready}\n"
        "Следующая съёмка пойдёт через I2V от этого кадра (если модели на месте)."
    )


def clear_pose_seed(config: Config) -> str:
    save_seed_state(config, enabled=False, path="", comfy_name="")
    from ...lab.comfy_pipeline import COMFY_TOPIC
    from ...lab.session import load_session, save_session

    session = load_session(config, COMFY_TOPIC)
    if session is not None:
        session.meta.pop("i2v_seed_enabled", None)
        session.meta.pop("i2v_seed_path", None)
        session.meta.pop("i2v_seed_comfy", None)
        save_session(config, session)
    return "Эталон I2V сброшен — следующая съёмка снова T2V."


def resolve_active_seed(config: Config) -> Tuple[Optional[Path], str, bool]:
    """(lab_path, comfy_input_name, enabled)."""
    from ...lab.comfy_pipeline import COMFY_TOPIC
    from ...lab.session import load_session

    session = load_session(config, COMFY_TOPIC)
    if session is not None and session.meta.get("i2v_seed_enabled"):
        p = Path(str(session.meta.get("i2v_seed_path") or ""))
        name = str(session.meta.get("i2v_seed_comfy") or _COMFY_SEED_NAME)
        if p.is_file():
            return p, name, True
    st = load_seed_state(config)
    if st.get("enabled") and st.get("path"):
        p = Path(str(st["path"]))
        if p.is_file():
            return p, str(st.get("comfy_name") or _COMFY_SEED_NAME), True
    return None, "", False


def i2v_status_line(config: Config) -> str:
    probe = probe_models(config)
    path, name, enabled = resolve_active_seed(config)
    if not enabled or path is None:
        return "I2V эталон: нет — съёмка T2V. Студия → «Эталон → I2V»."
    if probe.ready_i2v:
        return f"I2V эталон: {path.name} → {name} (модели OK)"
    return (
        f"I2V эталон: {path.name}, но нет I2V 14B/clip_vision — будет T2V. "
        "comfy_install i2v=1"
    )


def mocap_lora_checklist_text() -> str:
    return MOCAP_LORA_CHECKLIST.strip()
