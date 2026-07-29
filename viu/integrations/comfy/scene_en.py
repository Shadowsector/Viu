"""Русская сцена из чата → короткий EN action для Wan/MoCap."""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from ...config import Config

# Типовые фразы Дена → чистая поза (без сырого русского в Wan).
_SCENE_MAP: tuple[tuple[re.Pattern[str], str], ...] = (
    (
        re.compile(r"(?i)развал\w*.{0,20}кресл"),
        "lounging sprawled in an armchair, leaning back, legs relaxed, full body",
    ),
    (
        re.compile(r"(?i)развал\w*.{0,20}(?:диван|sofa|couch)"),
        "lounging sprawled on a sofa, leaning back, relaxed full body",
    ),
    (
        re.compile(r"(?i)(?:сид\w+|сидишь|сидит).{0,20}кресл"),
        "sitting in an armchair, upright then soft, full body",
    ),
    (
        re.compile(r"(?i)кресл"),
        "sitting in an armchair, full body",
    ),
    (
        re.compile(r"(?i)у\s+окна|смотр\w*\s+в\s+окно"),
        "standing by a window looking outside, full body",
    ),
    (
        re.compile(r"(?i)на\s+закате|закат"),
        "standing outdoors at sunset, full body",
    ),
    (
        re.compile(r"(?i)фентез|фэнтез|fantasy"),
        "standing in a fantasy landscape, full body",
    ),
    (
        re.compile(r"(?i)в\s+лесу|лесн"),
        "standing in a forest, full body",
    ),
    (
        re.compile(r"(?i)леж\w*|разлег"),
        "lying down relaxed, full body horizontal",
    ),
    (
        re.compile(r"(?i)сто\w*\s+в\s+секси|секси\s+поз"),
        "standing in a confident pose, weight on one hip, full body",
    ),
    (
        re.compile(r"(?i)селфи|selfie"),
        "close-up selfie looking at camera, upper body",
    ),
)


def has_cyrillic(text: str) -> bool:
    return bool(re.search(r"[А-Яа-яЁё]", text or ""))


def map_scene_heuristics(wish: str) -> Optional[str]:
    w = (wish or "").strip()
    if not w:
        return None
    for pat, en in _SCENE_MAP:
        if pat.search(w):
            return en
    return None


def _ollama_root(base_url: str) -> str:
    root = (base_url or "").rstrip("/")
    if root.endswith("/v1"):
        root = root[:-3]
    return root


def translate_scene_via_ollama(config: "Config", wish: str) -> Optional[str]:
    """Короткий EN pose-line через Ollama (без vision)."""
    base = str(getattr(config, "base_url", "") or "").strip()
    if not base:
        return None
    model = (
        str(getattr(config, "model_work", "") or "").strip()
        or str(getattr(config, "model", "") or "").strip()
        or "llama3.2"
    )
    prompt = (
        "Convert this Russian scene direction into ONE short English line "
        "for a MoCap video prompt: pose, body action, prop/place. "
        "No style words, no emotion, no clothing essay. "
        "Output ONLY the English line.\n\n"
        f"RU: {wish.strip()[:240]}"
    )
    url = f"{_ollama_root(base)}/api/generate"
    body = json.dumps(
        {"model": model, "prompt": prompt, "stream": False, "options": {"temperature": 0.2}}
    ).encode("utf-8")
    req = urllib.request.Request(
        url, data=body, headers={"Content-Type": "application/json"}, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=45) as resp:  # noqa: S310
            data = json.loads(resp.read().decode("utf-8", errors="replace"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
        return None
    text = (data.get("response") or "").strip()
    if not text:
        return None
    # первая строка, без кавычек
    line = text.splitlines()[0].strip().strip("`\"'")
    if has_cyrillic(line) or len(line) < 8:
        return None
    if len(line) > 180:
        line = line[:177].rstrip() + "…"
    return line


def scene_wish_to_en(
    wish: str,
    *,
    config: Optional["Config"] = None,
) -> str:
    """RU/смешанное описание → EN action для Wan."""
    w = (wish or "").strip()
    if not w:
        return "relaxed medium shot, natural motion, full body"
    if not has_cyrillic(w):
        return w
    mapped = map_scene_heuristics(w)
    if mapped:
        return mapped
    if config is not None:
        got = translate_scene_via_ollama(config, w)
        if got:
            return got
    # Запас: не тащить сырой русский в Wan — нейтральная поза + якорь места.
    if re.search(r"(?i)кресл", w):
        return "lounging in an armchair, relaxed full body"
    return "young woman in the described pose, medium shot, full body, natural motion"
