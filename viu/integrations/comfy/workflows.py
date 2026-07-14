"""Загрузка API-workflow JSON для ComfyUI."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, Optional

from .paths import comfy_workflows_dir


def list_workflows(config) -> list[Path]:
    d = comfy_workflows_dir(config)
    return sorted(d.glob("*.json"))


def load_workflow(config, name: str = "default") -> Dict[str, Any]:
    """Загрузить workflow. name без .json или полный путь."""
    raw = (name or "default").strip()
    path = Path(raw)
    if path.is_file():
        data = json.loads(path.read_text(encoding="utf-8"))
    else:
        stem = raw[:-5] if raw.lower().endswith(".json") else raw
        path = comfy_workflows_dir(config) / f"{stem}.json"
        if not path.is_file():
            raise FileNotFoundError(
                f"Нет workflow {path}.\n"
                "В ComfyUI: Save (API Format) → положи JSON в:\n"
                f"  {comfy_workflows_dir(config)}\n"
                "Имя по умолчанию: default.json"
            )
        data = json.loads(path.read_text(encoding="utf-8"))
    return _unwrap_api_export(data)


def _unwrap_api_export(data: Any) -> Dict[str, Any]:
    """Comfy иногда сохраняет {\"prompt\": {...}} или плоский graph."""
    if not isinstance(data, dict):
        raise ValueError("workflow JSON должен быть объектом")
    if "prompt" in data and isinstance(data["prompt"], dict):
        return data["prompt"]
    # UI format имеет "nodes" list — не API
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
    # Копия
    wf = json.loads(json.dumps(workflow))
    encoded = False
    for _nid, node in wf.items():
        if not isinstance(node, dict):
            continue
        if node.get("class_type") != "CLIPTextEncode":
            continue
        inputs = node.setdefault("inputs", {})
        # Первый CLIPTextEncode без уже длинного negative-looking — positive
        text = str(inputs.get("text") or "")
        if "negative" in text.lower() and not encoded:
            continue
        inputs["text"] = prompt
        encoded = True
        break
    if not encoded:
        # fallback: любой CLIPTextEncode
        for _nid, node in wf.items():
            if isinstance(node, dict) and node.get("class_type") == "CLIPTextEncode":
                node.setdefault("inputs", {})["text"] = prompt
                break
    return wf


def write_install_readme(config) -> Path:
    path = comfy_workflows_dir(config) / "README.txt"
    path.write_text(
        "Положи сюда workflow в API Format из ComfyUI (Save → API Format).\n"
        "Имя: default.json — для comfy_run без аргумента workflow=.\n"
        "Для video→Cascadeur позже: i2v.json / t2v.json.\n"
        "Документ: docs/COMFY_CASCADEUR_PIPELINE.md\n",
        encoding="utf-8",
    )
    return path
