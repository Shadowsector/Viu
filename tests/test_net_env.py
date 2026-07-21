"""Снятие мёртвого proxy из env."""

import os

from viu.net_env import apply_proxy_scrub_to_process, scrub_proxy_env


def test_scrub_removes_proxy(monkeypatch):
    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:3067")
    monkeypatch.setenv("http_proxy", "http://127.0.0.1:3067")
    monkeypatch.delenv("VIU_KEEP_PROXY", raising=False)
    env = scrub_proxy_env()
    assert "HTTPS_PROXY" not in env
    assert "http_proxy" not in env
    assert env.get("NO_PROXY") == "*"


def test_keep_proxy(monkeypatch):
    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:3067")
    monkeypatch.setenv("VIU_KEEP_PROXY", "1")
    env = scrub_proxy_env()
    assert env["HTTPS_PROXY"] == "http://127.0.0.1:3067"


def test_apply_to_process(monkeypatch):
    monkeypatch.setenv("ALL_PROXY", "http://127.0.0.1:3067")
    monkeypatch.delenv("VIU_KEEP_PROXY", raising=False)
    removed = apply_proxy_scrub_to_process()
    assert "ALL_PROXY" in removed
    assert "ALL_PROXY" not in os.environ
