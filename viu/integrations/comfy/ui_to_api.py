"""Конвертация ComfyUI UI-workflow (nodes/links) → API Format."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

# Порядок widget-полей для узлов Wan / native Comfy (без запущенного Comfy).
_WIDGET_ORDER: Dict[str, List[str]] = {
    "CLIPTextEncode": ["text"],
    "UNETLoader": ["unet_name", "weight_dtype"],
    "CLIPLoader": ["clip_name", "type", "device"],
    "VAELoader": ["vae_name"],
    "KSampler": ["seed", "steps", "cfg", "sampler_name", "scheduler", "denoise"],
    "EmptyHunyuanLatentVideo": ["width", "height", "length", "batch_size"],
    "ModelSamplingSD3": ["shift"],
    "SaveAnimatedWEBP": ["filename_prefix", "fps", "lossless", "quality", "method"],
    "SaveWEBM": ["filename_prefix", "codec", "fps", "crf"],
    "SaveImage": ["filename_prefix"],
    "VAEDecode": [],
    "CLIPVisionLoader": ["clip_name"],
    "LoadImage": ["image"],
    "WanImageToVideo": ["width", "height", "length", "batch_size"],
    "CLIPVisionEncode": ["crop"],
}

_SEED_CONTROLS = frozenset({"randomize", "fixed", "increment", "decrement"})


def ui_workflow_to_api(ui: Dict[str, Any]) -> Dict[str, Any]:
    """Преобразовать UI JSON в плоский API prompt dict."""
    if not isinstance(ui, dict):
        raise ValueError("workflow должен быть объектом")
    if "nodes" not in ui:
        # уже API?
        if any(isinstance(v, dict) and "class_type" in v for v in ui.values()):
            return {k: v for k, v in ui.items() if not str(k).startswith("_")}
        raise ValueError("Нет nodes[] и не похоже на API Format")

    link_from: Dict[int, tuple[int, int]] = {}
    for link in ui.get("links") or []:
        if not isinstance(link, list) or len(link) < 5:
            continue
        link_from[int(link[0])] = (int(link[1]), int(link[2]))

    api: Dict[str, Any] = {}
    for node in ui.get("nodes") or []:
        if not isinstance(node, dict):
            continue
        if node.get("mode") == 4:  # muted
            continue
        nid = str(node["id"])
        class_type = str(node.get("type") or "")
        if not class_type:
            continue
        inputs: Dict[str, Any] = {}
        for inp in node.get("inputs") or []:
            if not isinstance(inp, dict):
                continue
            name = inp.get("name")
            link = inp.get("link")
            if not name or link is None:
                continue
            src = link_from.get(int(link))
            if src:
                inputs[str(name)] = [str(src[0]), int(src[1])]

        widgets = list(node.get("widgets_values") or [])
        if class_type == "LoadImage" and widgets and widgets[-1] == "image":
            widgets = widgets[:-1]

        names = _WIDGET_ORDER.get(class_type, [])
        wi = 0
        for name in names:
            if wi >= len(widgets):
                break
            if class_type == "KSampler" and name == "seed":
                inputs[name] = widgets[wi]
                wi += 1
                if wi < len(widgets) and isinstance(widgets[wi], str) and widgets[wi] in _SEED_CONTROLS:
                    wi += 1
                continue
            inputs[name] = widgets[wi]
            wi += 1

        title = str(node.get("title") or class_type)
        api[nid] = {
            "class_type": class_type,
            "inputs": inputs,
            "_meta": {"title": title},
        }
    return api


def looks_like_ui_workflow(data: Any) -> bool:
    return isinstance(data, dict) and isinstance(data.get("nodes"), list)
