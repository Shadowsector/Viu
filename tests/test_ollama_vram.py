"""Тесты лимита VRAM Ollama."""

import os

from viu.config import Config
from viu.ollama_vram import apply_ollama_vram_limit, ollama_vram_gb


def test_ollama_vram_default_10gb():
    old = os.environ.pop("VIU_LAB_VRAM_GB", None)
    old_max = os.environ.pop("OLLAMA_MAX_VRAM", None)
    try:
        assert ollama_vram_gb() == 10.0
        gb = apply_ollama_vram_limit()
        assert gb == 10.0
        assert os.environ["OLLAMA_MAX_VRAM"] == str(10 * 1024**3)
    finally:
        if old is not None:
            os.environ["VIU_LAB_VRAM_GB"] = old
        elif "VIU_LAB_VRAM_GB" in os.environ:
            del os.environ["VIU_LAB_VRAM_GB"]
        if old_max is not None:
            os.environ["OLLAMA_MAX_VRAM"] = old_max
        elif "OLLAMA_MAX_VRAM" in os.environ:
            del os.environ["OLLAMA_MAX_VRAM"]


def test_ollama_vram_from_env(tmp_path, monkeypatch):
    monkeypatch.setenv("VIU_LAB_VRAM_GB", "10")
    cfg = Config(root=tmp_path, data_dir=tmp_path / ".viu").ensure_dirs()
    gb = apply_ollama_vram_limit(cfg)
    assert gb == 10.0
    assert int(os.environ["OLLAMA_MAX_VRAM"]) == 10 * 1024**3
