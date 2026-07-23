"""Лица для MoCap: папка Lab/FaceRefs → ReActor в Comfy."""

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
_README = """Lab/FaceRefs — эталонные лица для MoCap (ReActor)

Положи сюда PNG/JPG с одним чётким лицом (фронт или ¾).
Вью копирует выбранное фото в Comfy перед генерацией.

Приоритет выбора:
  1) VIU_COMFY_FACE_REF=полный/относительный путь
  2) default.png / shanya.png (если есть)
  3) случайный файл из этой папки

Выключить подмену: VIU_COMFY_FACE_SWAP=0

После первой установки: comfy_install.bat reactor=1
Пересборка не нужна — только положи фото и снимай.
"""


def face_swap_enabled() -> bool:
    raw = (os.environ.get("VIU_COMFY_FACE_SWAP") or "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


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


def reactor_face_swap_class(client) -> str | None:
    """Класс ReActor в запущенном Comfy (папка ≠ загруженная нода)."""
    from .client import ComfyClient

    if not isinstance(client, ComfyClient):
        return None
    for cand in ("ReActorFaceSwap", "ReActorFaceSwapOpt"):
        if client.has_node_class(cand):
            return cand
    return client.find_node_class("reactor", "faceswap")


def inswapper_model_path(config: Config) -> Path | None:
    from .paths import resolve_comfy_root

    root = resolve_comfy_root(config)
    if root is None:
        return None
    p = root / "models" / "insightface" / "inswapper_128.onnx"
    return p if p.is_file() else None


def face_refs_status(config: Config, *, client=None) -> str:
    d = ensure_face_refs_dir(config)
    refs = list_face_refs(config)
    env_ref = (os.environ.get("VIU_COMFY_FACE_REF") or "").strip()
    lines = [
        f"FaceRefs: {d} ({len(refs)} фото)",
        f"face_swap: {'on' if face_swap_enabled() else 'off'}",
    ]
    if env_ref:
        lines.append(f"VIU_COMFY_FACE_REF={env_ref}")
    pick = pick_face_ref(config)
    if pick:
        lines.append(f"следующее лицо: {pick.name}")
    else:
        lines.append("лица нет — положи PNG в FaceRefs (см. README.txt)")
    root = resolve_comfy_root(config)
    reactor_cls = None
    if client is not None:
        reactor_cls = reactor_face_swap_class(client)
    if reactor_cls:
        lines.append(f"ReActor: нода **{reactor_cls}** в Comfy :8188")
    elif root is not None:
        reactor_dir = root / "custom_nodes" / "ComfyUI-ReActor"
        if reactor_dir.is_dir():
            lines.append(
                "ReActor: папка есть, но нода не в Comfy — перезапусти Comfy (comfy_ensure)"
            )
        else:
            lines.append("ReActor: нет — comfy_install reactor=1")
    inswap = inswapper_model_path(config)
    if inswap:
        lines.append(f"inswapper: {inswap.name}")
    elif root is not None:
        lines.append("inswapper: нет models/insightface/inswapper_128.onnx")
    if face_swap_enabled() and pick and not reactor_cls:
        lines.append("⚠ face_swap on, но ReActor не загружен — подмены не будет")
    return "\n".join(lines)
