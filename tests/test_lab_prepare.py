"""Тесты prepare/recover lab."""

from viu.config import Config
from viu.lab.cascadeur_pipeline import CASCADEUR_TOPIC
from viu.lab.prepare import prepare_lab_session
from viu.lab.recover import should_recover_instead_of_retry
from viu.lab.session import load_session, new_session, save_session
from viu.lab.version import persist_build_stamp, viu_build_stamp


def _cfg(tmp_path):
    import os

    os.environ["VIU_DATA_DIR"] = str(tmp_path / ".viu")
    return Config(root=tmp_path, data_dir=tmp_path / ".viu").ensure_dirs()


def test_auto_reset_on_viu_build_change(tmp_path):
    cfg = _cfg(tmp_path)
    s = new_session(CASCADEUR_TOPIC)
    s.step = 7
    s.viu_build_stamp = "olddeadbeef"
    save_session(cfg, s)
    persist_build_stamp(cfg)
    session, mode, note = prepare_lab_session(cfg, CASCADEUR_TOPIC)
    assert mode == "fresh"
    assert session.step == 0
    assert "Обновление Viu" in note or viu_build_stamp(cfg) in session.viu_build_stamp


def test_should_recover_after_two_fails():
    s = new_session(CASCADEUR_TOPIC)
    s.last_fail_step = 7
    s.step_fail_counts = {"7": 2}
    assert should_recover_instead_of_retry(s)


def test_auto_reset_on_global_build_stamp(tmp_path):
    cfg = _cfg(tmp_path)
    s = new_session(CASCADEUR_TOPIC)
    s.step = 5
    s.viu_build_stamp = viu_build_stamp(cfg)
    save_session(cfg, s)
    stamp_path = cfg.data_dir / "lab" / "viu_build_stamp.txt"
    stamp_path.parent.mkdir(parents=True, exist_ok=True)
    stamp_path.write_text("ancient-build\n", encoding="utf-8")
    session, mode, note = prepare_lab_session(cfg, CASCADEUR_TOPIC)
    assert mode == "fresh"
    assert session.step == 0


def test_prepare_recover_mode(tmp_path):
    cfg = _cfg(tmp_path)
    s = new_session(CASCADEUR_TOPIC)
    s.last_fail_step = 7
    s.step_fail_counts = {"7": 2}
    s.viu_build_stamp = viu_build_stamp(cfg)
    save_session(cfg, s)
    persist_build_stamp(cfg)
    session, mode, note = prepare_lab_session(cfg, CASCADEUR_TOPIC)
    assert mode == "recover"
    assert "recover" in note.lower()
