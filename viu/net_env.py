"""Сеть: убрать мёртвый локальный прокси из окружения.

Частая Windows-беда: Clash/V2Ray/VPN прописали HTTPS_PROXY=127.0.0.1:XXXX,
прокси не запущен → pip и GitHub API падают с WinError 10061, хотя интернет есть.
"""

from __future__ import annotations

import os
import urllib.request
from typing import Mapping, Optional

_PROXY_KEYS = (
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
    "http_proxy",
    "https_proxy",
    "all_proxy",
    "PIP_PROXY",
    "pip_proxy",
)


def keep_proxy_requested() -> bool:
    return os.environ.get("VIU_KEEP_PROXY", "").strip().lower() in ("1", "true", "yes")


def scrub_proxy_env(env: Optional[Mapping[str, str]] = None) -> dict[str, str]:
    """Копия env без proxy-переменных (если не VIU_KEEP_PROXY=1)."""
    out: dict[str, str] = dict(env or os.environ)
    if keep_proxy_requested():
        return out
    for key in _PROXY_KEYS:
        out.pop(key, None)
    # не ходить в системный proxy для pip/urllib в этом процессе-наследнике
    out["NO_PROXY"] = "*"
    out["no_proxy"] = "*"
    return out


def install_direct_opener() -> None:
    """urllib без proxy (env + Windows Internet Settings)."""
    if keep_proxy_requested():
        return
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    urllib.request.install_opener(opener)


def apply_proxy_scrub_to_process() -> list[str]:
    """Убрать proxy из os.environ текущего процесса. Возвращает имена снятых ключей."""
    if keep_proxy_requested():
        return []
    removed: list[str] = []
    for key in _PROXY_KEYS:
        if key in os.environ:
            removed.append(key)
            os.environ.pop(key, None)
    os.environ["NO_PROXY"] = "*"
    os.environ["no_proxy"] = "*"
    # Windows: urllib ещё читает системный proxy из реестра — обходим opener'ом
    install_direct_opener()
    return removed


def proxy_hint(removed: list[str]) -> str:
    if not removed:
        return ""
    return (
        "Сняты proxy-переменные: "
        + ", ".join(removed)
        + ". Если прокси нужен — VIU_KEEP_PROXY=1 и запусти свой VPN/Clash."
    )
