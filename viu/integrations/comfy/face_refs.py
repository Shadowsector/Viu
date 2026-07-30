"""Лица для MoCap: папка Lab/FaceRefs → ReActor в Comfy.

Подпапки = группы персонажей: FaceRefs/Ru/, FaceRefs/Oli/, …
В панели «Съёмка» выбираешь группу/фото — ★ видно, generate подхватит.
"""

from __future__ import annotations

import json
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
_FACE_STATE = "comfy_face_ref.json"
_README = """Lab/FaceRefs — эталонные лица для MoCap (ReActor)

Положи PNG/JPG с одним чётким лицом (фронт или ¾).

Группы персонажей — подпапки:
  FaceRefs/Ru/….png
  FaceRefs/Oli/….png
В панели «Съёмка» выбираешь группу/файл — ★ ← ВЫБРАН.

Приоритет выбора:
  1) выбор в панели Съёмка / VIU_COMFY_FACE_REF
  2) default.png / shanya.png (если есть)
  3) случайный файл

Выключить подмену: VIU_COMFY_FACE_SWAP=0
После первой установки: comfy_install.bat reactor=1
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


def _face_state_path(config: Config) -> Path:
    return Path(config.data_dir) / _FACE_STATE


def load_face_state(config: Config) -> dict:
    path = _face_state_path(config)
    if not path.is_file():
        return {"path": "", "group": ""}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"path": "", "group": ""}
    if not isinstance(data, dict):
        return {"path": "", "group": ""}
    return {
        "path": str(data.get("path") or ""),
        "group": str(data.get("group") or ""),
    }


def save_face_state(config: Config, *, path: str = "", group: str = "") -> None:
    config.ensure_dirs()
    p = _face_state_path(config)
    tmp = p.with_suffix(".json.tmp")
    payload = {"path": str(path or ""), "group": str(group or "")}
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(p)


def list_face_refs(config: Config) -> List[Path]:
    """Плоский список всех лиц (корень + подпапки)."""
    return [p for _g, p in list_face_ref_entries(config)]


def list_face_ref_entries(config: Config) -> List[Tuple[str, Path]]:
    """[(метка «Ru/face.png», path), …] — корень и подпапки-группы."""
    d = ensure_face_refs_dir(config)
    out: List[Tuple[str, Path]] = []
    try:
        for p in sorted(d.iterdir()):
            if p.is_file() and p.suffix.lower() in _FACE_EXTS:
                out.append((p.name, p.resolve()))
            elif p.is_dir() and not p.name.startswith("."):
                group = p.name
                for f in sorted(p.iterdir()):
                    if f.is_file() and f.suffix.lower() in _FACE_EXTS:
                        out.append((f"{group}/{f.name}", f.resolve()))
    except OSError:
        pass
    return out


def list_face_groups(config: Config) -> List[str]:
    """Имена подпапок (Ru, Oli, …) + '' для корня если там есть файлы."""
    d = ensure_face_refs_dir(config)
    groups: List[str] = []
    try:
        root_has = any(
            p.is_file() and p.suffix.lower() in _FACE_EXTS for p in d.iterdir()
        )
        if root_has:
            groups.append("")
        for p in sorted(d.iterdir()):
            if p.is_dir() and not p.name.startswith("."):
                if any(
                    f.is_file() and f.suffix.lower() in _FACE_EXTS for f in p.iterdir()
                ):
                    groups.append(p.name)
    except OSError:
        pass
    return groups


def set_active_face_ref(config: Config, face_path: Path | str) -> Tuple[bool, str]:
    """Запомнить лицо для следующей съёмки (ReActor)."""
    p = Path(face_path)
    if not p.is_file():
        return False, f"Нет файла лица: {p}"
    if p.suffix.lower() not in _FACE_EXTS:
        return False, "Нужен PNG/JPG/WebP"
    group = ""
    root = ensure_face_refs_dir(config)
    try:
        rel = p.resolve().relative_to(root.resolve())
        if len(rel.parts) >= 2:
            group = rel.parts[0]
    except ValueError:
        group = ""
    save_face_state(config, path=str(p.resolve()), group=group)

    from ...lab.comfy_pipeline import COMFY_TOPIC
    from ...lab.session import load_session, new_session, save_session

    session = load_session(config, COMFY_TOPIC) or new_session(COMFY_TOPIC)
    session.meta["reactor_face_ref"] = str(p.resolve())
    session.meta["reactor_face_group"] = group
    save_session(config, session)
    label = f"{group}/{p.name}" if group else p.name
    return True, f"ReActor лицо: {label}\nСкопирую в Comfy на следующей съёмке."


def clear_active_face_ref(config: Config) -> str:
    save_face_state(config, path="", group="")
    from ...lab.comfy_pipeline import COMFY_TOPIC
    from ...lab.session import load_session, save_session

    session = load_session(config, COMFY_TOPIC)
    if session is not None:
        session.meta.pop("reactor_face_ref", None)
        session.meta.pop("reactor_face_group", None)
        save_session(config, session)
    return "Выбор лица сброшен — снова default / случайный из FaceRefs."


def resolve_active_face_ref(config: Config) -> Optional[Path]:
    from ...lab.comfy_pipeline import COMFY_TOPIC
    from ...lab.session import load_session

    session = load_session(config, COMFY_TOPIC)
    if session is not None:
        raw = str(session.meta.get("reactor_face_ref") or "").strip()
        if raw:
            p = Path(raw)
            if p.is_file():
                return p.resolve()
    st = load_face_state(config)
    if st.get("path"):
        p = Path(str(st["path"]))
        if p.is_file():
            return p.resolve()
    return None


def pick_face_ref(config: Config, *, seed: str = "") -> Optional[Path]:
    """Выбрать эталон лица. seed — для стабильного random на batch."""
    active = resolve_active_face_ref(config)
    if active is not None:
        return active

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


def face_list_labels(config: Config) -> List[str]:
    """Подписи для Listbox: ★ у активного."""
    active = resolve_active_face_ref(config)
    active_res = active.resolve() if active is not None else None
    out: List[str] = []
    for label, path in list_face_ref_entries(config):
        if active_res is not None and path.resolve() == active_res:
            out.append(f"★ {label}  ← ВЫБРАН")
        else:
            out.append(f"  {label}")
    return out


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
    from .reactor_diag import list_reactor_node_classes

    found = list_reactor_node_classes(client)
    for name in found:
        if "faceswap" in name.lower():
            return name
    return found[0] if found else None


def inswapper_model_path(config: Config) -> Path | None:
    from .paths import resolve_comfy_root

    root = resolve_comfy_root(config)
    if root is None:
        return None
    p = root / "models" / "insightface" / "inswapper_128.onnx"
    return p if p.is_file() else None


def reactor_needs_reload(config: Config, client) -> bool:
    """Папка ReActor есть, но Comfy запущен до установки — нужен рестарт."""
    if not face_swap_enabled():
        return False
    root = resolve_comfy_root(config)
    if root is None:
        return False
    if not (root / "custom_nodes" / "ComfyUI-ReActor").is_dir():
        return False
    return reactor_face_swap_class(client) is None


def face_swap_status_line(config: Config, *, client=None) -> str:
    """Одна строка: ReActor готов или что сделать."""
    if not face_swap_enabled():
        return "face_swap: off"
    if client is None:
        return "face_swap: on (проверка ReActor — нужен онлайн Comfy)"
    cls = reactor_face_swap_class(client)
    if cls:
        pick = pick_face_ref(config)
        face = pick.name if pick else "нет FaceRef"
        return f"face_swap: **OK** (ReActor {cls}, лицо: {face})"
    from .reactor_diag import probe_reactor_deps

    root = resolve_comfy_root(config)
    ok_imp, _, _ = probe_reactor_deps(config, timeout=30.0)
    if root and (root / "custom_nodes" / "ComfyUI-ReActor").is_dir():
        if not ok_imp:
            return "face_swap: **нет** — import ReActor падает → comfy_reactor_fix"
        return "face_swap: **нет** — import OK, но нод нет в API → comfy_ensure restart=1"
    return "face_swap: **нет** — comfy_install reactor=1"


def face_refs_status(config: Config, *, client=None) -> str:
    from .reactor_diag import probe_reactor_deps, reactor_errors_in_launch_log

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
            ok_imp, imp_tail, _ = probe_reactor_deps(config, timeout=30.0)
            if ok_imp:
                lines.append(
                    "ReActor: import OK, но нода не в API — перезапусти Comfy (comfy_ensure restart=1)"
                )
            else:
                lines.append("ReActor: **import FAIL** — comfy_reactor_fix")
                for ln in (imp_tail or "").splitlines()[-4:]:
                    if ln.strip():
                        lines.append(f"  {ln.strip()[:200]}")
                log_bit = reactor_errors_in_launch_log(config)
                if log_bit:
                    for ln in log_bit.splitlines()[-3:]:
                        lines.append(f"  log: {ln.strip()[:200]}")
        else:
            lines.append("ReActor: нет — comfy_install reactor=1")
    inswap = inswapper_model_path(config)
    if inswap:
        lines.append(f"inswapper: {inswap.name}")
    elif root is not None:
        lines.append("inswapper: нет models/insightface/inswapper_128.onnx")
    if face_swap_enabled() and pick and not reactor_cls:
        if not probe_reactor_deps(config, timeout=20.0)[0]:
            lines.append("⚠ comfy_reactor_fix — доустановить зависимости ReActor")
        else:
            lines.append("⚠ comfy_ensure restart=1 — import OK, нужен рестарт Comfy")
    lines.append(face_swap_status_line(config, client=client))
    return "\n".join(lines)
