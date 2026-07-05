"""Веб-инструменты: поиск и загрузка страниц (доступ к интернету).

Используют только стандартную библиотеку. При отсутствии сети или при
VIU_ALLOW_NETWORK=0 корректно возвращают ошибку, не роняя агента.
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict

from .base import AgentContext, Tool, ToolResult

_USER_AGENT = "ViuAgent/0.1 (+https://github.com/Shadowsector/Viu)"
_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def _http_get(url: str, timeout: float = 30.0) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        charset = resp.headers.get_content_charset() or "utf-8"
        return resp.read().decode(charset, "replace")


class WebFetchTool(Tool):
    name = "web_fetch"
    description = "Загрузить страницу по URL и вернуть текст (без HTML-тегов)"
    parameters = {"url": "полный URL", "max_chars": "ограничение длины (опционально)"}

    def run(self, args: Dict[str, Any], ctx: AgentContext) -> ToolResult:
        if not ctx.config.allow_network:
            return ToolResult(False, "Сеть отключена (VIU_ALLOW_NETWORK=0)")
        url = args.get("url", "")
        if not url:
            return ToolResult(False, "Не указан url")
        try:
            max_chars = int(args.get("max_chars", 4000))
        except (TypeError, ValueError):
            max_chars = 4000
        try:
            html = _http_get(url)
        except (urllib.error.URLError, ValueError, OSError) as exc:
            return ToolResult(False, f"Не удалось загрузить {url}: {exc}")
        text = _WS_RE.sub(" ", _TAG_RE.sub(" ", html)).strip()
        return ToolResult(True, text[:max_chars])


class WebSearchTool(Tool):
    name = "web_search"
    description = "Поиск в интернете (DuckDuckGo Instant Answer API)"
    parameters = {"query": "поисковый запрос"}

    def run(self, args: Dict[str, Any], ctx: AgentContext) -> ToolResult:
        if not ctx.config.allow_network:
            return ToolResult(False, "Сеть отключена (VIU_ALLOW_NETWORK=0)")
        query = args.get("query", "")
        if not query:
            return ToolResult(False, "Не указан query")
        url = "https://api.duckduckgo.com/?" + urllib.parse.urlencode(
            {"q": query, "format": "json", "no_html": "1", "no_redirect": "1"}
        )
        try:
            raw = _http_get(url)
            data = json.loads(raw)
        except (urllib.error.URLError, ValueError, OSError) as exc:
            return ToolResult(False, f"Ошибка поиска: {exc}")

        results = []
        if data.get("AbstractText"):
            results.append(data["AbstractText"])
        for topic in data.get("RelatedTopics", [])[:5]:
            if isinstance(topic, dict) and topic.get("Text"):
                results.append(topic["Text"])
        if not results:
            return ToolResult(True, "Ничего не найдено по запросу.")
        return ToolResult(True, "\n".join(f"- {r}" for r in results))
