"""Загрузка API-workflow JSON для ComfyUI."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any, Dict, Optional

from .paths import comfy_workflows_dir

_TEMPLATES = Path(__file__).resolve().parent / "templates"


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
            "В ComfyUI открой Wan 2.1 T2V/I2V → Save (API Format) → "
            "перезапиши t2v.json / i2v.json. Дальше Вью ведёт сама."
        )
    if "prompt" in data and isinstance(data["prompt"], dict):
        return data["prompt"]
    if "nodes" in data and isinstance(data["nodes"], list):
        raise ValueError(
            "Это UI-workflow (nodes[]). Нужен Save → API Format "
            "(плоский dict id→node)."
        )
    return data


def inject_text_prompt(workflow: Dict[str, Any], prompt: str) -> Dict[str, Any]:
    """Подставить текст в первый CLIPTextEncode (positive) если есть."""
    prompt = (prompt or "").strip()
    if not prompt:
        return workflow
    wf = json.loads(json.dumps(workflow))
    encoded = False
    for _nid, node in wf.items():
        if not isinstance(node, dict):
            continue
        if node.get("class_type") != "CLIPTextEncode":
            continue
        inputs = node.setdefault("inputs", {})
        text = str(inputs.get("text") or "")
        if "negative" in text.lower() and not encoded:
            continue
        inputs["text"] = prompt
        encoded = True
        break
    if not encoded:
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
    clip_nodes = [
        (nid, node)
        for nid, node in wf.items()
        if isinstance(node, dict) and node.get("class_type") == "CLIPTextEncode"
    ]
    if len(clip_nodes) >= 2:
        _nid, node = clip_nodes[1]
        node.setdefault("inputs", {})["text"] = negative
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


def workflow_is_stub(path: Path) -> bool:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return True
    return bool(isinstance(data, dict) and data.get("_viu_stub"))


def ensure_workflow_templates(config) -> list[Path]:
    """Скопировать шаблоны t2v/i2v/default если ещё нет файлов."""
    dest = comfy_workflows_dir(config)
    written: list[Path] = []
    for name in ("t2v.json", "i2v.json", "default.json"):
        target = dest / name
        if target.is_file():
            continue
        src = _TEMPLATES / name
        if src.is_file():
            shutil.copy2(src, target)
            written.append(target)
    write_install_readme(config)
    return written


def write_install_readme(config) -> Path:
    path = comfy_workflows_dir(config) / "README.txt"
    path.write_text(
        "Workflows для Вью (API Format из ComfyUI).\n"
        "\n"
        "t2v.json  — Wan 2.1 Text-to-Video (основной)\n"
        "i2v.json  — Wan 2.1 Image-to-Video (last frame → next)\n"
        "default.json — fallback (= t2v)\n"
        "\n"
        "Если файл с пометкой _viu_stub — один раз открой официальный Wan workflow\n"
        "в ComfyUI → Save (API Format) → перезапиши файл. Дальше Вью не трогает UI.\n"
        "Доки: docs/COMFY_SETUP.md\n",
        encoding="utf-8",
    )
    return path
