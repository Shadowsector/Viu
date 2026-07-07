"""Тесты Unity process detection и lockfile."""

from viu.integrations.unity.process import (
    clear_unity_lockfile,
    prepare_unity_for_batch,
    unity_lockfile,
)


def test_clear_stale_lockfile(tmp_path):
    (tmp_path / "Temp").mkdir()
    lock = unity_lockfile(tmp_path)
    lock.write_bytes(b"")
    assert lock.is_file()

    ok, msg = prepare_unity_for_batch(tmp_path, auto_kill=False)
    assert ok
    assert not lock.is_file()
    assert "lockfile" in msg.lower() or msg == ""


def test_prepare_clears_lock_without_unity_process(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "viu.integrations.unity.process.unity_process_running",
        lambda: False,
    )
    (tmp_path / "Temp").mkdir()
    lock = tmp_path / "Temp" / "UnityLockfile"
    lock.write_bytes(b"stale")

    ok, _ = prepare_unity_for_batch(tmp_path, auto_kill=True)
    assert ok
    assert not lock.exists()


def test_clear_unity_lockfile_missing(tmp_path):
    assert clear_unity_lockfile(tmp_path) is False
