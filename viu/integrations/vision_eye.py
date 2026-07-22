"""Глаза Вью: скрин → Ollama VL (если есть) → вердикт; иначе handoff Cursor со скрином."""

from __future__ import annotations

import base64
import json
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ..config import Config
from ..health import ollama_models
from .screen.capture import capture_window_png, default_shot_path, list_windows


_VL_PREFER = (
    "qwen2.5-vl",
    "qwen2-vl",
    "llava",
    "llama3.2-vision",
    "minicpm-v",
    "moondream",
)

_DEFAULT_PROMPT = (
    "Это скрин Unity/оверлея игры Анабарра (персонаж Шаня). "
    "Ответь кратко по пунктам на русском:\n"
    "1) Виден ли персонаж? Стоит нормально или тело/кости искажены?\n"
    "2) Виден ли дом/сарай на фоне?\n"
    "3) Это оверлей на рабочем столе или окно Unity Editor?\n"
    "4) Вердикт одной строкой: OK | BROKEN_IDLE | NO_HOME | NO_CHARACTER | NO_OVERLAY | UNKNOWN\n"
)


def pick_vision_model(base_url: str, prefer: str = "") -> Optional[str]:
    names = ollama_models(base_url)
    if not names:
        return None
    if prefer:
        for n in names:
            if prefer.lower() in n.lower():
                return n
    lower = [n.lower() for n in names]
    for key in _VL_PREFER:
        for i, n in enumerate(lower):
            if key in n:
                return names[i]
    return None


def _ollama_root(base_url: str) -> str:
    root = base_url.rstrip("/")
    if root.endswith("/v1"):
        root = root[:-3]
    return root


def ask_vision(
    image_path: Path,
    *,
    prompt: str,
    config: Config,
    model: str = "",
) -> Tuple[bool, str]:
    """Ollama /api/generate с images[]. Без VL-модели — False."""
    if not image_path.is_file():
        return False, f"Нет файла: {image_path}"
    chosen = model or pick_vision_model(config.base_url, prefer="")
    if not chosen:
        return False, (
            "Нет vision-модели в Ollama (llava / qwen2-vl / …). "
            "Поставь: ollama pull llava. Скрин всё равно уйдёт Cursor."
        )
    raw = image_path.read_bytes()
    b64 = base64.b64encode(raw).decode("ascii")
    url = f"{_ollama_root(config.base_url)}/api/generate"
    body = json.dumps(
        {
            "model": chosen,
            "prompt": prompt or _DEFAULT_PROMPT,
            "images": [b64],
            "stream": False,
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    timeout = float(getattr(config, "llm_timeout", 1800) or 1800)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
            data = json.loads(resp.read().decode("utf-8", errors="replace"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
        return False, f"Ollama vision fail ({chosen}): {exc}"
    text = (data.get("response") or "").strip()
    if not text:
        return False, f"Пустой ответ vision ({chosen})"
    return True, f"[{chosen}]\n{text}"


def observe_window(
    config: Config,
    *,
    title_substr: str,
    prompt: str = "",
    prefix: str = "eye",
) -> Dict[str, Any]:
    """Скрин окна + VL (если есть). Всегда возвращает path скрина при успехе захвата."""
    path = default_shot_path(config.data_dir, prefix=prefix)
    ok, msg = capture_window_png(path, title_substr=title_substr)
    out: Dict[str, Any] = {
        "capture_ok": ok,
        "capture_msg": msg,
        "path": str(path) if ok else "",
        "vision_ok": False,
        "vision": "",
        "windows": [t for _, t in list_windows()[:30]],
    }
    if not ok:
        return out
    vok, vtext = ask_vision(path, prompt=prompt or _DEFAULT_PROMPT, config=config)
    out["vision_ok"] = vok
    out["vision"] = vtext
    return out


def upload_shot_note(path: Path, vision_text: str = "") -> Tuple[bool, str]:
    """Gist: README + base64 PNG для Cursor."""
    from ..env_file import github_token
    from .github.api import upload_gist

    token = github_token()
    if not token:
        return False, "Нет VIU_GITHUB_TOKEN — скрин только локально."
    if not path.is_file():
        return False, f"Нет файла: {path}"
    b64 = base64.b64encode(path.read_bytes()).decode("ascii")
    body = (
        f"Viu eyes\nfile={path.name}\n\nvision:\n{vision_text or '(none)'}\n\n"
        f"--- base64 png ---\n{b64}\n"
    )
    return upload_gist(
        path.name + ".b64.txt",
        body,
        token=token,
        description="Viu eyes screenshot",
    )
