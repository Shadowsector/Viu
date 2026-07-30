"""FaceRefs groups + shoot panel from_shoot_panel skip awaiting."""

from __future__ import annotations

from pathlib import Path

from viu.config import Config
from viu.integrations.comfy.face_refs import (
    clear_active_face_ref,
    face_list_labels,
    list_face_ref_entries,
    pick_face_ref,
    set_active_face_ref,
)
from viu.lab.comfy_pipeline import COMFY_TOPIC, step_request_approval
from viu.lab.session import new_session, save_session


def _cfg(tmp_path: Path) -> Config:
    return Config(root=tmp_path, data_dir=tmp_path / ".viu").ensure_dirs()


def test_face_ref_groups_and_star(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    from viu.integrations.comfy import face_refs as fr

    root = tmp_path / "FaceRefs"
    root.mkdir()
    (root / "Ru").mkdir()
    (root / "Oli").mkdir()
    ru = root / "Ru" / "a.png"
    oli = root / "Oli" / "b.png"
    ru.write_bytes(b"x")
    oli.write_bytes(b"y")
    monkeypatch.setattr(fr, "comfy_face_refs_dir", lambda _c: root)
    monkeypatch.setattr(fr, "ensure_face_refs_dir", lambda _c: root)

    entries = list_face_ref_entries(cfg)
    labels = [e[0] for e in entries]
    assert "Ru/a.png" in labels
    assert "Oli/b.png" in labels

    ok, msg = set_active_face_ref(cfg, ru)
    assert ok
    assert "Ru" in msg or "a.png" in msg
    assert pick_face_ref(cfg) == ru.resolve()
    assert any("← ВЫБРАН" in x for x in face_list_labels(cfg))

    clear_active_face_ref(cfg)
    # без выбора — всё ещё может взять файл из списка
    assert pick_face_ref(cfg) is not None


def test_from_shoot_panel_skips_awaiting(tmp_path):
    cfg = _cfg(tmp_path)
    session = new_session(COMFY_TOPIC)
    session.meta["action"] = "standing relaxed in soft light"
    session.meta["from_shoot_panel"] = True
    session.meta["setup_lora_indices"] = []
    save_session(cfg, session)
    ok, msg, _ = step_request_approval(cfg, session)
    assert ok
    session2 = __import__("viu.lab.session", fromlist=["load_session"]).load_session(
        cfg, COMFY_TOPIC
    )
    assert session2 is not None
    assert session2.status == "running"
    assert "from_shoot_panel" not in (session2.meta or {})
    assert "Снимаю" in msg or "очередь" in msg.lower() or "Wan" in msg
