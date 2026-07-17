"""Тесты сбора логов (support bundle)."""

import zipfile

from viu.config import Config
from viu.support import collect_support_bundle, upload_bundle_to_gist


def _config(tmp_path):
    return Config(root=tmp_path, data_dir=tmp_path / ".viu").ensure_dirs()


def test_collect_bundle_has_system_info(tmp_path):
    config = _config(tmp_path)
    logs = config.data_dir / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    (logs / "chat_20260706_120000.txt").write_text("привет", encoding="utf-8")

    bundle = collect_support_bundle(config)
    assert bundle.is_file()
    with zipfile.ZipFile(bundle) as zf:
        names = zf.namelist()
        assert "system_info.txt" in names
        assert any(n.startswith("chat_") for n in names)
        info = zf.read("system_info.txt").decode("utf-8")
        assert "Viu support bundle" in info


def test_upload_without_token_returns_hint(tmp_path, monkeypatch):
    monkeypatch.delenv("VIU_GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    config = _config(tmp_path)
    bundle = collect_support_bundle(config)
    ok, msg = upload_bundle_to_gist(bundle)
    assert not ok
    assert "токен" in msg.lower()
