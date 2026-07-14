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


def workflow_is_stub(path: Path) -> bool:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return True
    return bool(isinstance(data, dict) and data.get("_viu_stub"))


def ensure_workflow_templates(config, *, overwrite_stubs: bool = False) -> list[Path]:
    """Скопировать шаблоны t2v/i2v/default из пакета Вью."""
    dest = comfy_workflows_dir(config)
    written: list[Path] = []
    for name in ("t2v.json", "i2v.json", "default.json"):
        target = dest / name
        src = _TEMPLATES / name
        if not src.is_file():
            continue
        if target.is_file():
            if not overwrite_stubs or not workflow_is_stub(target):
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
        "Обновление: comfy_install / lab topic=comfy.\n"
        "Доки: docs/COMFY_SETUP.md\n",
        encoding="utf-8",
    )
    return path
