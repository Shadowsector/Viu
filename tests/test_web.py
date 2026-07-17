"""Тесты web_search с HTML fallback."""

from pathlib import Path

from viu.config import Config
from viu.tools.base import AgentContext
from viu.tools.web import WebSearchTool, search_web


def _cfg(tmp_path: Path) -> Config:
    import os

    os.environ["VIU_DATA_DIR"] = str(tmp_path / ".viu")
    return Config(root=tmp_path, data_dir=tmp_path / ".viu").ensure_dirs()


def _ctx(cfg: Config) -> AgentContext:
    from viu.memory import MemoryStore
    from viu.planning import Planner
    from viu.tools import ToolRegistry

    return AgentContext(
        config=cfg,
        memory=MemoryStore(cfg.data_dir / "memory.json"),
        planner=Planner(cfg.data_dir / "lab_plan.json"),
        registry=ToolRegistry(),
    )


def test_search_web_html_fallback(monkeypatch):
    def fake_get(url: str, timeout: float = 30.0) -> str:
        if "api.duckduckgo.com" in url:
            return '{"AbstractText":"","RelatedTopics":[]}'
        if "html.duckduckgo.com" in url:
            return (
                '<a class="result__a" href="http://x">Export to Unity - Cascadeur</a>'
                '<a class="result__snippet">Import Model workflow</a>'
            )
        raise AssertionError(url)

    monkeypatch.setattr("viu.tools.web._http_get", fake_get)
    hits = search_web("Cascadeur export FBX Unity", max_results=3)
    assert hits
    assert any("Unity" in h or "Cascadeur" in h for h in hits)


def test_search_web_cascadeur_docs_fallback(monkeypatch):
    def fake_get(url: str, timeout: float = 30.0) -> str:
        if "api.duckduckgo.com" in url or "html.duckduckgo.com" in url:
            if "api.duckduckgo.com" in url:
                return '{"AbstractText":"","RelatedTopics":[]}'
            return "<html></html>"
        if "cascadeur.com" in url:
            return "<html><body>Import FBX Scene mode</body></html>"
        raise AssertionError(url)

    monkeypatch.setattr("viu.tools.web._http_get", fake_get)
    hits = search_web("Cascadeur rig retarget", max_results=3)
    assert hits
    assert any("Import FBX" in h or "cascadeur.com" in h for h in hits)


def test_web_search_tool_ok(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)

    def fake_get(url: str, timeout: float = 30.0) -> str:
        if "api.duckduckgo.com" in url:
            return '{"AbstractText":"","RelatedTopics":[]}'
        return (
            '<a class="result__a" href="http://x">Cascadeur docs</a>'
            '<a class="result__snippet">FBX export</a>'
        )

    monkeypatch.setattr("viu.tools.web._http_get", fake_get)
    res = WebSearchTool().run({"query": "Cascadeur FBX"}, _ctx(cfg))
    assert res.ok
    assert "Ничего не найдено" not in res.content
    assert "Cascadeur" in res.content or "FBX" in res.content
