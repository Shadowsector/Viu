"""Загрузка API-workflow JSON для ComfyUI."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Union

from .paths import comfy_workflows_dir

_TEMPLATES = Path(__file__).resolve().parent / "templates"

# Дефолты (перекрываются framing.frame_spec_for_action при генерации).
MOCAP_WIDTH = 576
MOCAP_HEIGHT = 1024
MOCAP_LENGTH = 81
MOCAP_FPS = 24.0
_TEMPLATE_REV = 4

_LATENT_SIZE_NODES = (
    "EmptyHunyuanLatentVideo",
    "WanImageToVideo",
    "EmptyLatentImage",
    "EmptyLatentAudio",
)
_OLD_SAVERS = (
    "SaveAnimatedWEBP",
    "SaveAnimatedPNG",
    "SaveAnimatedGIF",
    "VHS_VideoCombine",
)


def list_workflows(config) -> list[Path]:
    d = comfy_workflows_dir(config)
    return sorted(d.glob("*.json"))


def load_workflow(config, name: str = "default") -> Dict[str, Any]:
    """Загрузить workflow. name без .json или полный путь."""
    ensure_workflow_templates(config)
    raw = (name or "default").strip()
    path = Path(raw)
    if path.is_file():
        data = json.loads(path.read_text(encoding="utf-8"))
    else:
        stem = raw[:-5] if raw.lower().endswith(".json") else raw
        path = comfy_workflows_dir(config) / f"{stem}.json"
        if not path.is_file() and stem != "default":
            # fallback chain: requested → default → t2v
            for alt in ("default", "t2v"):
                alt_path = comfy_workflows_dir(config) / f"{alt}.json"
                if alt_path.is_file():
                    path = alt_path
                    break
        if not path.is_file():
            raise FileNotFoundError(
                f"Нет workflow {path}.\n"
                "Вью ждёт API Format JSON в:\n"
                f"  {comfy_workflows_dir(config)}\n"
                "Имена: t2v.json (Wan T2V), i2v.json (Wan I2V), default.json."
            )
        data = json.loads(path.read_text(encoding="utf-8"))
    return _unwrap_api_export(data)


def _unwrap_api_export(data: Any) -> Dict[str, Any]:
    """Comfy иногда сохраняет {\"prompt\": {...}} или плоский graph."""
    if not isinstance(data, dict):
        raise ValueError("workflow JSON должен быть объектом")
    if data.get("_viu_stub") is True:
        raise ValueError(
            "Это заглушка workflow (_viu_stub). "
            "Запусти comfy_install — Вью скачает Wan JSON сама."
        )
    if "prompt" in data and isinstance(data["prompt"], dict):
        return {k: v for k, v in data["prompt"].items() if not str(k).startswith("_")}
    if "nodes" in data and isinstance(data["nodes"], list):
        from .ui_to_api import ui_workflow_to_api

        return ui_workflow_to_api(data)
    # убрать служебные ключи Вью
    return {k: v for k, v in data.items() if not str(k).startswith("_")}


def _is_negative_clip(node: dict) -> bool:
    title = str((node.get("_meta") or {}).get("title") or "").lower()
    if "negative" in title:
        return True
    text = str((node.get("inputs") or {}).get("text") or "").lower()
    return "negative" in text


def inject_text_prompt(workflow: Dict[str, Any], prompt: str) -> Dict[str, Any]:
    """Подставить текст в positive CLIPTextEncode."""
    prompt = (prompt or "").strip()
    if not prompt:
        return workflow
    wf = json.loads(json.dumps(workflow))
    # 1) явный Positive в title
    for _nid, node in wf.items():
        if not isinstance(node, dict) or node.get("class_type") != "CLIPTextEncode":
            continue
        title = str((node.get("_meta") or {}).get("title") or "").lower()
        if ("positive" in title or "prompt" in title) and "negative" not in title:
            if not _is_negative_clip(node):
                node.setdefault("inputs", {})["text"] = prompt
                return wf
    # 2) первый CLIP без Negative
    for _nid, node in wf.items():
        if not isinstance(node, dict) or node.get("class_type") != "CLIPTextEncode":
            continue
        if _is_negative_clip(node):
            continue
        node.setdefault("inputs", {})["text"] = prompt
        return wf
    # 3) fallback
    for _nid, node in wf.items():
        if isinstance(node, dict) and node.get("class_type") == "CLIPTextEncode":
            node.setdefault("inputs", {})["text"] = prompt
            break
    return wf


def inject_negative_prompt(workflow: Dict[str, Any], negative: str) -> Dict[str, Any]:
    negative = (negative or "").strip()
    if not negative:
        return workflow
    wf = json.loads(json.dumps(workflow))
    for _nid, node in wf.items():
        if isinstance(node, dict) and node.get("class_type") == "CLIPTextEncode" and _is_negative_clip(node):
            node.setdefault("inputs", {})["text"] = negative
            return wf
    clip_nodes = [
        node
        for node in wf.values()
        if isinstance(node, dict) and node.get("class_type") == "CLIPTextEncode"
    ]
    if len(clip_nodes) >= 2:
        clip_nodes[1].setdefault("inputs", {})["text"] = negative
    return wf


def inject_seed(workflow: Dict[str, Any], seed: int) -> Dict[str, Any]:
    wf = json.loads(json.dumps(workflow))
    for _nid, node in wf.items():
        if not isinstance(node, dict):
            continue
        inputs = node.get("inputs")
        if not isinstance(inputs, dict):
            continue
        if "seed" in inputs:
            inputs["seed"] = int(seed)
            return wf
        if "noise_seed" in inputs:
            inputs["noise_seed"] = int(seed)
            return wf
    return wf


def inject_seed_image(workflow: Dict[str, Any], image_name: str) -> Dict[str, Any]:
    """Подставить эталон позы в LoadImage I2V (не трогать Viu FaceRef)."""
    name = (image_name or "").strip()
    if not name:
        return workflow
    wf = json.loads(json.dumps(workflow))
    for _nid, node in wf.items():
        if not isinstance(node, dict):
            continue
        if node.get("class_type") != "LoadImage":
            continue
        title = str((node.get("_meta") or {}).get("title") or "")
        low = title.lower()
        if "faceref" in low or title.strip() == "Viu FaceRef":
            continue
        node.setdefault("inputs", {})["image"] = name
        return wf
    # fallback: первый LoadImage без FaceRef в title
    for _nid, node in wf.items():
        if not isinstance(node, dict):
            continue
        if node.get("class_type") != "LoadImage":
            continue
        title = str((node.get("_meta") or {}).get("title") or "")
        if title.strip() == "Viu FaceRef":
            continue
        node.setdefault("inputs", {})["image"] = name
        break
    return wf


def inject_end_seed_image(workflow: Dict[str, Any], image_name: str) -> Dict[str, Any]:
    """Если у WanImageToVideo есть end_image — подставить конечный эталон.

    Стоковый шаблон Viu пока только start_image; end сохраняем в библиотеке
    и инжектим, когда нода/шаблон это умеет.
    """
    name = (image_name or "").strip()
    if not name:
        return workflow
    wf = json.loads(json.dumps(workflow))
    # Уже есть LoadImage с title End / end seed?
    end_load_id = None
    for nid, node in wf.items():
        if not isinstance(node, dict) or node.get("class_type") != "LoadImage":
            continue
        title = str((node.get("_meta") or {}).get("title") or "").lower()
        if "end" in title and "faceref" not in title:
            node.setdefault("inputs", {})["image"] = name
            end_load_id = nid
            break
    for _nid, node in wf.items():
        if not isinstance(node, dict):
            continue
        if node.get("class_type") != "WanImageToVideo":
            continue
        inputs = node.setdefault("inputs", {})
        if "end_image" not in inputs and end_load_id is None:
            # Нода без end_image — ничего не ломаем.
            return wf
        if end_load_id is not None:
            inputs["end_image"] = [end_load_id, 0]
        elif isinstance(inputs.get("end_image"), list) and inputs["end_image"]:
            ref = inputs["end_image"][0]
            load = wf.get(str(ref))
            if isinstance(load, dict) and load.get("class_type") == "LoadImage":
                load.setdefault("inputs", {})["image"] = name
        return wf
    return wf


def inject_vertical_frame(
    workflow: Dict[str, Any],
    *,
    width: int = MOCAP_WIDTH,
    height: int = MOCAP_HEIGHT,
    length: int = MOCAP_LENGTH,
) -> Dict[str, Any]:
    """Портрет 480×832 — фигура на весь кадр под Cascadeur."""
    wf = json.loads(json.dumps(workflow))
    for _nid, node in wf.items():
        if not isinstance(node, dict):
            continue
        if node.get("class_type") not in _LATENT_SIZE_NODES:
            continue
        inputs = node.setdefault("inputs", {})
        if "width" in inputs:
            inputs["width"] = int(width)
        if "height" in inputs:
            inputs["height"] = int(height)
        if "length" in inputs:
            inputs["length"] = int(length)
    return wf


def _find_vae_decode_id(wf: Dict[str, Any]) -> Optional[str]:
    for nid, node in wf.items():
        if isinstance(node, dict) and node.get("class_type") == "VAEDecode":
            return str(nid)
    return None


def _next_node_id(wf: Dict[str, Any], start: int = 900) -> str:
    n = start
    while str(n) in wf:
        n += 1
    return str(n)


_PREFIX_SAVER_NODES = (
    "SaveVideo",
    "VHS_VideoCombine",
    "SaveAnimatedWEBP",
    "SaveWEBM",
    "SaveImage",
)


def inject_filename_prefix(workflow: Dict[str, Any], prefix: str) -> Dict[str, Any]:
    """Подставить читаемый префикс во все узлы сохранения."""
    prefix = (prefix or "").strip() or "viu_mocap"
    wf = json.loads(json.dumps(workflow))
    for node in wf.values():
        if not isinstance(node, dict):
            continue
        if node.get("class_type") in _PREFIX_SAVER_NODES:
            node.setdefault("inputs", {})["filename_prefix"] = prefix
    return wf


def ensure_mp4_output(
    workflow: Dict[str, Any],
    *,
    fps: float = MOCAP_FPS,
    filename_prefix: str = "viu_mocap",
) -> Dict[str, Any]:
    """Заменить WEBP/GIF-сейвер на CreateVideo → SaveVideo (mp4/h264)."""
    wf = json.loads(json.dumps(workflow))
    prefix = (filename_prefix or "").strip() or "viu_mocap"

    # Уже есть SaveVideo — только выставить mp4/h264/fps на CreateVideo
    has_save = any(
        isinstance(n, dict) and n.get("class_type") == "SaveVideo" for n in wf.values()
    )
    has_create = any(
        isinstance(n, dict) and n.get("class_type") == "CreateVideo" for n in wf.values()
    )
    if has_save and has_create:
        for node in wf.values():
            if not isinstance(node, dict):
                continue
            if node.get("class_type") == "CreateVideo":
                node.setdefault("inputs", {})["fps"] = float(fps)
            if node.get("class_type") == "SaveVideo":
                inp = node.setdefault("inputs", {})
                inp["format"] = "mp4"
                inp["codec"] = "h264"
                inp["filename_prefix"] = prefix
        # убрать старые анимированные сейверы, если остались рядом
        for nid in list(wf.keys()):
            node = wf[nid]
            if isinstance(node, dict) and node.get("class_type") in _OLD_SAVERS:
                del wf[nid]
        return wf

    decode_id = _find_vae_decode_id(wf)
    images_ref: Optional[list] = None
    if decode_id is not None:
        images_ref = [decode_id, 0]

    # Снять images с старого сейвера, затем удалить
    for nid in list(wf.keys()):
        node = wf[nid]
        if not isinstance(node, dict):
            continue
        ct = node.get("class_type")
        if ct in _OLD_SAVERS or ct == "SaveImage":
            imgs = (node.get("inputs") or {}).get("images")
            if images_ref is None and isinstance(imgs, list) and len(imgs) >= 2:
                images_ref = imgs
            if ct in _OLD_SAVERS:
                del wf[nid]

    if images_ref is None:
        return wf

    create_id = _next_node_id(wf, 900)
    save_id = _next_node_id({**wf, create_id: {}}, 901)
    wf[create_id] = {
        "class_type": "CreateVideo",
        "inputs": {"images": images_ref, "fps": float(fps)},
        "_meta": {"title": "CreateVideo"},
    }
    wf[save_id] = {
        "class_type": "SaveVideo",
        "inputs": {
            "video": [create_id, 0],
            "filename_prefix": prefix,
            "format": "mp4",
            "codec": "h264",
        },
        "_meta": {"title": "SaveVideo"},
    }
    return inject_filename_prefix(wf, prefix)


def inject_loras(
    workflow: Dict[str, Any],
    loras: Sequence[Union[Any, str, Dict[str, Any]]],
) -> Dict[str, Any]:
    """Вставить цепочку LoraLoaderModelOnly между UNET и ModelSamplingSD3/KSampler."""
    if not loras:
        return workflow
    from .lora import LoraSpec, _parse_lora_item

    specs: List[LoraSpec] = []
    for raw in loras:
        if isinstance(raw, LoraSpec):
            specs.append(raw)
        else:
            spec = _parse_lora_item(raw)
            if spec is not None:
                specs.append(spec)
    if not specs:
        return workflow

    wf = json.loads(json.dumps(workflow))
    consumer_id: Optional[str] = None
    for nid, node in wf.items():
        if isinstance(node, dict) and node.get("class_type") == "ModelSamplingSD3":
            consumer_id = str(nid)
            break
    if consumer_id is None:
        for nid, node in wf.items():
            if not isinstance(node, dict):
                continue
            if node.get("class_type") in ("KSampler", "KSamplerAdvanced", "SamplerCustom"):
                consumer_id = str(nid)
                break
    if consumer_id is None:
        return wf

    consumer = wf.get(consumer_id)
    if not isinstance(consumer, dict):
        return wf
    model_ref = (consumer.get("inputs") or {}).get("model")
    if not isinstance(model_ref, list) or len(model_ref) < 2:
        return wf

    prev_out: list = list(model_ref)
    for i, spec in enumerate(specs):
        lora_id = _next_node_id(wf, 850 + i)
        lora_name = spec.file
        if spec.subfolder:
            lora_name = f"{spec.subfolder}/{spec.file}"
        wf[lora_id] = {
            "class_type": "LoraLoaderModelOnly",
            "inputs": {
                "model": prev_out,
                "lora_name": lora_name,
                "strength_model": float(spec.strength),
            },
            "_meta": {"title": f"LoRA {spec.file}"},
        }
        prev_out = [lora_id, 0]

    consumer.setdefault("inputs", {})["model"] = prev_out
    return wf


def inject_face_swap(
    workflow: Dict[str, Any],
    *,
    face_image: str,
    decode_node_id: str = "",
    create_video_node_id: str = "",
    reactor_class: str = "ReActorFaceSwap",
) -> Dict[str, Any]:
    """ReActor: VAEDecode → face swap → CreateVideo. face_image — имя в ComfyUI/input/."""
    if not (face_image or "").strip():
        return workflow
    wf = json.loads(json.dumps(workflow))

    decode_id = decode_node_id
    if not decode_id:
        for nid, node in wf.items():
            if isinstance(node, dict) and node.get("class_type") == "VAEDecode":
                decode_id = str(nid)
                break
    if not decode_id:
        return workflow

    cv_id = create_video_node_id
    if not cv_id:
        for nid, node in wf.items():
            if isinstance(node, dict) and node.get("class_type") == "CreateVideo":
                cv_id = str(nid)
                break
    if not cv_id:
        return workflow

    load_id = _next_node_id(wf, 910)
    reactor_id = _next_node_id(wf, 911)
    wf[load_id] = {
        "class_type": "LoadImage",
        "inputs": {"image": face_image.strip()},
        "_meta": {"title": "Viu FaceRef"},
    }
    wf[reactor_id] = {
        "class_type": reactor_class or "ReActorFaceSwap",
        "inputs": {
            "enabled": True,
            "input_image": [decode_id, 0],
            "source_image": [load_id, 0],
            "swap_model": "inswapper_128.onnx",
            "facedetection": "retinaface_resnet50",
            "face_restore_model": "none",
            "face_restore_visibility": 1.0,
            "codeformer_weight": 0.5,
            "detect_gender_input": "no",
            "detect_gender_source": "no",
            "input_faces_index": "0",
            "source_faces_index": "0",
            "console_log_level": 1,
        },
        "_meta": {"title": "Viu ReActor"},
    }
    cv = wf.get(cv_id)
    if isinstance(cv, dict):
        cv.setdefault("inputs", {})["images"] = [reactor_id, 0]
    return wf


def prepare_mocap_workflow(
    workflow: Dict[str, Any],
    *,
    action: str = "",
    filename_prefix: str = "",
) -> Dict[str, Any]:
    """Кадр/длина по действию (стоя≠лёжа) + mp4 — поверх любого t2v на диске."""
    from .framing import frame_spec_for_action

    spec = frame_spec_for_action(action)
    wf = inject_vertical_frame(
        workflow, width=spec.width, height=spec.height, length=spec.length
    )
    prefix = (filename_prefix or "").strip() or "viu_mocap"
    wf = ensure_mp4_output(wf, fps=spec.fps, filename_prefix=prefix)
    return inject_filename_prefix(wf, prefix)


def workflow_is_stub(path: Path) -> bool:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return True
    return bool(isinstance(data, dict) and data.get("_viu_stub"))


def _template_rev(path: Path) -> int:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return 0
    if not isinstance(data, dict):
        return 0
    try:
        return int(data.get("_viu_template_rev") or 0)
    except (TypeError, ValueError):
        return 0


def ensure_workflow_templates(config, *, overwrite_stubs: bool = False) -> list[Path]:
    """Скопировать шаблоны t2v/i2v/default; обновить если rev шаблона новее."""
    dest = comfy_workflows_dir(config)
    written: list[Path] = []
    for name in ("t2v.json", "i2v.json", "default.json", "seed_refine_img2img.json"):
        target = dest / name
        src = _TEMPLATES / name
        if not src.is_file():
            continue
        src_rev = _template_rev(src)
        if target.is_file():
            dst_rev = _template_rev(target)
            if workflow_is_stub(target) and overwrite_stubs:
                pass  # перезаписать stub
            elif src_rev > dst_rev:
                pass  # обновить устаревший
            else:
                continue
        shutil.copy2(src, target)
        written.append(target)
    write_install_readme(config)
    return written


def write_install_readme(config) -> Path:
    path = comfy_workflows_dir(config) / "README.txt"
    path.write_text(
        "Workflows для Вью (API Format).\n"
        "\n"
        "t2v.json / i2v.json / default.json — Wan 2.1 "
        "(официальные примеры, UI→API конвертит Вью).\n"
        f"MoCap: кадр по позе (стоя 576×1024 / лёжа 1024×576), MP4 {int(MOCAP_FPS)} fps, "
        f"длина 4n+1 (idle≈81), template rev {_TEMPLATE_REV}.\n"
        "Обновление: comfy_install / lab topic=comfy / авто при comfy_triple.\n"
        "Доки: docs/COMFY_SETUP.md\n",
        encoding="utf-8",
    )
    return path
