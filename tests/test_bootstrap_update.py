"""Тесты bootstrap_update.py (stdlib)."""

import importlib.util
import json
from pathlib import Path
from unittest.mock import patch


def _load_bootstrap():
    path = Path(__file__).resolve().parent.parent / "bootstrap_update.py"
    spec = importlib.util.spec_from_file_location("bootstrap_update", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_needs_update_first_install(tmp_path, monkeypatch):
    mod = _load_bootstrap()
    monkeypatch.setattr(mod, "root_dir", lambda: tmp_path)
    with patch.object(mod, "remote_sha", return_value="deadbeef" * 5):
        outdated, sha, reason = mod.needs_update()
    assert outdated
    assert sha.startswith("deadbeef")


def test_bootstrap_auto_returns_2_when_update_fails(tmp_path, monkeypatch):
    mod = _load_bootstrap()
    monkeypatch.setattr(mod, "root_dir", lambda: tmp_path)
    monkeypatch.setattr(mod, "refresh_bootstrap_script", lambda: False)
    monkeypatch.setattr(mod, "cleanup_obsolete", lambda: None)
    with patch.object(mod, "needs_update", return_value=(True, "deadbeef" * 5, "outdated")):
        with patch.object(mod, "run_update", return_value=False):
            assert mod.main(["--auto"]) == 2


def test_bootstrap_apply_returns_1_on_failure(tmp_path, monkeypatch):
    mod = _load_bootstrap()
    monkeypatch.setattr(mod, "root_dir", lambda: tmp_path)
    monkeypatch.setattr(mod, "refresh_bootstrap_script", lambda: False)
    monkeypatch.setattr(mod, "cleanup_obsolete", lambda: None)
    with patch.object(mod, "run_update", return_value=False):
        assert mod.main(["--apply"]) == 1


def test_needs_update_up_to_date(tmp_path, monkeypatch):
    mod = _load_bootstrap()
    monkeypatch.setattr(mod, "root_dir", lambda: tmp_path)
    sha = "cafebabe" * 5
    mod.write_stamp(sha)
    with patch.object(mod, "remote_sha", return_value=sha):
        outdated, _, reason = mod.needs_update()
    assert not outdated
    assert "актуально" in reason
