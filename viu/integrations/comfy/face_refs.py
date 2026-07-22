"""Лица для MoCap: папка Lab/FaceRefs → I2V (до генерации) или ReActor (после)."""

from __future__ import annotations

import os
import random
import shutil
from pathlib import Path
from typing import List, Optional, Tuple

from ...config import Config
from .paths import comfy_face_refs_dir, comfy_input_dir, resolve_comfy_root

_FACE_EXTS = {".png", ".jpg", ".jpeg", ".webp"}
_PREFERRED_NAMES = (
    "default.png",
    "default.jpg",
    "shanya.png",
    "shanya.jpg",
    "face.png",
    "face.jpg",
)
_COMFY_INPUT_NAME = "viu_face_ref.png"
_README = """Lab/FaceRefs — эталонные лица для MoCap

Положи сюда PNG/JPG с одним чётким лицом (фронт или ¾).
Вью копирует выбранное фото в Comfy перед генерацией.

Приоритет выбора:
  1) VIU_COMFY_FACE_REF=полный/относительный путь
  2) default.png / shanya.png (если есть)
  3) случайный файл из этой папки

По умолчанию лицо подставляется ДО генерации (I2V start_image).
Если I2V-модели нет — fallback ReActor после VAEDecode.

Выключить подмену: VIU_COMFY_FACE_SWAP=0
Только post-ReActor: VIU_COMFY_FACE_PREGEN=0

ReActor ставится автоматически при comfy_ensure (если face_swap=1).
"""


def face_swap_enabled() -> bool:
    raw = (os.environ.get("VIU_COMFY_FACE_SWAP") or "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


def face_pregen_enabled() -> bool:
    raw = (os.environ.get("VIU_COMFY_FACE_PREGEN") or "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


def reactor_auto_install_enabled() -> bool:
    raw = (os.environ.get("VIU_COMFY_FACE_REACTOR_AUTO") or "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


def _reactor_installed(root: Path) -> bool:
    dest = root / "custom_nodes" / "ComfyUI-ReActor"
    return dest.is_dir() and (dest / "nodes.py").is_file()


def ensure_face_swap_ready(config: Config) -> Tuple[bool, str]:
    """Установить ReActor + inswapper, если face_swap включён и ноды ещё нет."""
    if not face_swap_enabled():
        return True, "face_swap off"
    root = resolve_comfy_root(config)
    if root is None:
        return False, "ComfyUI root не найден"
    if _reactor_installed(root):
        return True, "ReActor ok"
    if not reactor_auto_install_enabled():
        return False, "ReActor нет — comfy_install reactor=1"
    from .install import ensure_reactor_installed

    return ensure_reactor_installed(root)


def ensure_face_refs_dir(config: Config) -> Path:
    d = comfy_face_refs_dir(config)
    readme = d / "README.txt"
    if not readme.is_file():
        try:
            readme.write_text(_README, encoding="utf-8")
        except OSError:
            pass
    return d


def list_face_refs(config: Config) -> List[Path]:
    d = ensure_face_refs_dir(config)
    out: List[Path] = []
    try:
        for p in sorted(d.iterdir()):
            if p.is_file() and p.suffix.lower() in _FACE_EXTS:
                out.append(p)
    except OSError:
        pass
    return out


def pick_face_ref(config: Config, *, seed: str = "") -> Optional[Path]:
    """Выбрать эталон лица. seed — для стабильного random на batch."""
    env = (os.environ.get("VIU_COMFY_FACE_REF") or "").strip()
    if env:
        p = Path(env).expanduser()
        if not p.is_file():
            alt = ensure_face_refs_dir(config) / env
            if alt.is_file():
                p = alt
        if p.is_file():
            return p.resolve()

    d = ensure_face_refs_dir(config)
    for name in _PREFERRED_NAMES:
        p = d / name
        if p.is_file():
            return p.resolve()

    candidates = list_face_refs(config)
    if not candidates:
        return None
    if len(candidates) == 1:
        return candidates[0]
    rng = random.Random(seed or None)
    return rng.choice(candidates)


def stage_face_for_comfy(config: Config, face_path: Path) -> Tuple[bool, str, str]:
    """Скопировать лицо в ComfyUI/input/viu_face_ref.png. Возвращает имя для LoadImage."""
    root = resolve_comfy_root(config)
    if root is None:
        return False, "ComfyUI root не найден", ""
    if not face_path.is_file():
        return False, f"нет файла лица: {face_path}", ""

    inp_dir = comfy_input_dir(root)
    dest = inp_dir / _COMFY_INPUT_NAME
    try:
        shutil.copy2(face_path, dest)
    except OSError as exc:
        return False, f"не скопировать в Comfy input: {exc}", ""
    return True, str(dest), _COMFY_INPUT_NAME


def face_refs_status(config: Config) -> str:
    d = ensure_face_refs_dir(config)
    refs = list_face_refs(config)
    env_ref = (os.environ.get("VIU_COMFY_FACE_REF") or "").strip()
    lines = [
        f"FaceRefs: {d} ({len(refs)} фото)",
        f"face_swap: {'on' if face_swap_enabled() else 'off'}",
        f"face_pregen (I2V): {'on' if face_pregen_enabled() else 'off'}",
    ]
    if env_ref:
        lines.append(f"VIU_COMFY_FACE_REF={env_ref}")
    pick = pick_face_ref(config)
    if pick:
        lines.append(f"следующее лицо: {pick.name}")
    else:
        lines.append("лица нет — положи PNG в FaceRefs (см. README.txt)")
    root = resolve_comfy_root(config)
    if root is not None:
        installed = _reactor_installed(root)
        lines.append(
            f"ReActor: {'установлен' if installed else 'нет (auto при comfy_ensure)'}"
        )
        try:
            from .client import ComfyClient

            url = getattr(config, "comfy_url", None) or "http://127.0.0.1:8188"
            client = ComfyClient(base_url=str(url), timeout=2.0)
            ok, _ = client.ping()
            if ok:
                live = client.has_node_class("ReActorFaceSwap")
                lines.append(f"ReActor в API: {'да' if live else 'нет — перезапусти Comfy'}")
        except Exception:
            pass
        from .model_pref import probe_models

        probe = probe_models(config)
        lines.append(f"I2V для pre-gen: {'готов' if probe.ready_i2v else 'нет — comfy_install i2v=1'}")
    return "\n".join(lines)
