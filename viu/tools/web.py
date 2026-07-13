"""Веб-инструменты: поиск и загрузка страниц (доступ к интернету).

Используют только стандартную библиотеку. При отсутствии сети или при
VIU_ALLOW_NETWORK=0 корректно возвращают ошибку, не роняя агента.
"""

from __future__ import annotations

import html
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List

from .base import AgentContext, Tool, ToolResult

_USER_AGENT = "ViuAgent/0.1 (+https://github.com/Shadowsector/Viu)"
_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")
_DDG_TITLE_RE = re.compile(
    r'class="result__a"[^>]*href="[^"]*"[^>]*>([^<]+)</a>',
    re.IGNORECASE,
)
_DDG_SNIPPET_RE = re.compile(
    r'class="result__snippet"[^>]*>([^<]+)</',
    re.IGNORECASE,
)

# Полезные официальные страницы Cascadeur — если DDG API пустой.
_CASCADEUR_DOC_URLS = (
    "https://cascadeur.com/help/getting_started/import_fbxdae",
    "https://cascadeur.com/help/getting_started/export_fbxdae/export_to_unity",
    "https://cascadeur.com/help/tools/animation_tools/python_scripting_in_cascadeur",
)


def _http_get(url: str, timeout: float = 30.0) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        charset = resp.headers.get_content_charset() or "utf-8"
        return resp.read().decode(charset, "replace")


def _strip_html(text: str) -> str:
    return _WS_RE.sub(" ", _TAG_RE.sub(" ", text)).strip()


def _search_ddg_instant(query: str) -> List[str]:
    url = "https://api.duckduckgo.com/?" + urllib.parse.urlencode(
        {"q": query, "format": "json", "no_html": "1", "no_redirect": "1"}
    )
    raw = _http_get(url)
    data = json.loads(raw)
    results: List[str] = []
    if data.get("AbstractText"):
        results.append(data["AbstractText"])
    for topic in data.get("RelatedTopics", [])[:8]:
        if isinstance(topic, dict) and topic.get("Text"):
            results.append(str(topic["Text"]))
    return results


def _search_ddg_html(query: str, *, max_results: int = 5) -> List[str]:
    url = "https://html.duckduckgo.com/html/?" + urllib.parse.urlencode({"q": query})
    page = _http_get(url)
    titles = [html.unescape(t.strip()) for t in _DDG_TITLE_RE.findall(page)]
    snippets = [html.unescape(s.strip()) for s in _DDG_SNIPPET_RE.findall(page)]
    results: List[str] = []
    for i, title in enumerate(titles[:max_results]):
        line = title
        if i < len(snippets) and snippets[i]:
            line = f"{title} — {snippets[i]}"
        results.append(line)
    return results


def _fetch_doc_summaries(urls: tuple[str, ...], *, max_chars: int = 900) -> List[str]:
    out: List[str] = []
    for url in urls:
        try:
            text = _strip_html(_http_get(url))[:max_chars]
            if text:
                out.append(f"[{url}]\n{text}")
        except (urllib.error.URLError, ValueError, OSError):
            continue
    return out


def search_web(query: str, *, max_results: int = 5) -> List[str]:
    """Поиск: Instant Answer API → HTML DDG → официальные docs Cascadeur (если в запросе)."""
    results = _search_ddg_instant(query)
    if not results:
        results = _search_ddg_html(query, max_results=max_results)
    if not results and "cascadeur" in query.lower():
        results = _fetch_doc_summaries(_CASCADEUR_DOC_URLS, max_chars=700)
    return results[:max_results]


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
            html_body = _http_get(url)
        except (urllib.error.URLError, ValueError, OSError) as exc:
            return ToolResult(False, f"Не удалось загрузить {url}: {exc}")
        text = _strip_html(html_body)
        return ToolResult(True, text[:max_chars])


class WebSearchTool(Tool):
    name = "web_search"
    description = "Поиск в интернете (DuckDuckGo API + HTML fallback + docs Cascadeur)"
    parameters = {"query": "поисковый запрос", "max_results": "сколько строк (опционально)"}

    def run(self, args: Dict[str, Any], ctx: AgentContext) -> ToolResult:
        if not ctx.config.allow_network:
            return ToolResult(False, "Сеть отключена (VIU_ALLOW_NETWORK=0)")
        query = args.get("query", "")
        if not query:
            return ToolResult(False, "Не указан query")
        try:
            max_results = max(1, int(args.get("max_results", 5)))
        except (TypeError, ValueError):
            max_results = 5
        try:
            results = search_web(query, max_results=max_results)
        except (urllib.error.URLError, ValueError, OSError) as exc:
            return ToolResult(False, f"Ошибка поиска: {exc}")

        if not results:
            return ToolResult(True, "Ничего не найдено по запросу.")
        return ToolResult(True, "\n".join(f"- {r}" for r in results))
