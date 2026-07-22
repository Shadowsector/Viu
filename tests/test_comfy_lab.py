"""Одобрение промпта и lab topic=comfy."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from viu.config import Config
from viu.integrations.comfy.approval import parse_approval_reply
from viu.integrations.comfy.paths import resolve_comfy_root
from viu.integrations.comfy.prompts import mocap_prompt
from viu.integrations.comfy.angles import default_angles
from viu.lab.comfy_pipeline import (
    COMFY_TOPIC,
    apply_prompt_decision,
    ensure_task_file,
    step_draft_prompt,
    step_request_approval,
)
from viu.lab.session import load_session, new_session, save_session
from viu.tools import build_default_registry


def _cfg(tmp_path: Path, monkeypatch) -> Config:
    monkeypatch.setenv("VIU_DATA_DIR", str(tmp_path / ".viu"))
    monkeypatch.setenv("VIU_LIBRARY_ROOT", str(tmp_path / "Library"))
    monkeypatch.delenv("VIU_COMFY_ROOT", raising=False)
    data = tmp_path / ".viu"
    data.mkdir()
    return Config(
        root=tmp_path / "Viu",
        data_dir=data,
        library_root=str(tmp_path / "Library"),
        comfy_root="",
    )


def test_registry_comfy_tools():
    names = build_default_registry().names()
    assert "comfy_ensure" in names
    assert "comfy_mocap" in names
    assert "comfy_triple" in names
    assert "comfy_clip_pick" in names


def test_resolve_prefers_viu_comfyui(tmp_path, monkeypatch):
    monkeypatch.delenv("VIU_COMFY_ROOT", raising=False)
    viu = tmp_path / "Viu"
    comfy = viu / "ComfyUI"
    comfy.mkdir(parents=True)
    (comfy / "main.py").write_text("# stub\n", encoding="utf-8")
    (comfy / "folder_paths.py").write_text("# marker\n", encoding="utf-8")
    cfg = Config(root=viu, data_dir=viu / ".viu", comfy_root="")
    (viu / ".viu").mkdir(parents=True, exist_ok=True)
    assert resolve_comfy_root(cfg) == comfy.resolve()


def test_rejects_unittest_main_as_comfy(tmp_path, monkeypatch):
    """CPython Lib/unittest/main.py — НЕ ComfyUI."""
    monkeypatch.delenv("VIU_COMFY_ROOT", raising=False)
    fake = tmp_path / "Python314" / "Lib" / "unittest"
    fake.mkdir(parents=True)
    (fake / "main.py").write_text("# unittest\n", encoding="utf-8")
    cfg = Config(root=tmp_path / "Viu", data_dir=tmp_path / ".viu", comfy_root=str(fake))
    (tmp_path / "Viu").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".viu").mkdir(parents=True, exist_ok=True)
    assert resolve_comfy_root(cfg) is None
    # сбросили ложный comfy_root
    assert cfg.comfy_root == ""


def test_parse_approval():
    assert parse_approval_reply("ок", current_action="sit") == ("approve", "sit")
    assert parse_approval_reply("стоп", current_action="sit")[0] == "reject"
    d, payload = parse_approval_reply("правки: wave hello", current_action="sit")
    assert d == "edit"
    assert "wave" in payload
    d2, _ = parse_approval_reply(
        "нет, мы другой промт хотели снимать",
        current_action="sleep idle",
    )
    assert d2 == "redraft"
    d3, _ = parse_approval_reply(
        "walking forward at a calm pace, natural arm swing",
        current_action="sit",
    )
    assert d3 == "edit"
    d4, _ = parse_approval_reply("другой кадр", current_action="sit")
    assert d4 == "redraft"


def test_mocap_angles_in_prompt():
    angles = default_angles()
    assert len(angles) == 3
    assert {a.id for a in angles} == {"take_a", "take_b", "take_c"}
    p = mocap_prompt("sit down", angles[0])
    assert "three-quarter" in p
    assert "sit down" in p
    assert "tanned" in p
    assert "white" in p.lower()
    assert "frontal" in p.lower() or "fill light" in p.lower() or "fills the frame" in p


def test_diversify_takes_differ():
    from viu.integrations.comfy.prompts import diversify_action

    a = diversify_action("walking forward", 0)
    b = diversify_action("walking forward", 1)
    c = diversify_action("walking forward", 2)
    assert a != b and b != c



def test_comfy_lab_awaits_telegram(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path, monkeypatch)
    (tmp_path / "Viu").mkdir(parents=True, exist_ok=True)
    ensure_task_file(cfg, action="lean on window")
    session = new_session(COMFY_TOPIC)
    session.steps_total = 9
    session.meta["action"] = "lean on window"
    save_session(cfg, session)

    ok, msg, _ = step_draft_prompt(cfg, session)
    assert ok
    with patch(
        "viu.lab.comfy_pipeline.send_prompt_for_approval",
        return_value=(True, "sent"),
    ):
        ok2, msg2, _ = step_request_approval(cfg, session)
    assert ok2
    loaded = load_session(cfg, COMFY_TOPIC)
    assert loaded is not None
    assert loaded.status == "awaiting_prompt"

    out = apply_prompt_decision(cfg, loaded, "approve", "lean on window")
    assert "принят" in out.lower() or "принят" in out
    loaded2 = load_session(cfg, COMFY_TOPIC)
    assert loaded2 is not None
    assert loaded2.status == "running"
    assert loaded2.meta.get("approved") is True
    assert loaded2.step >= 4


def test_redraft_does_not_approve_complaint(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path, monkeypatch)
    (tmp_path / "Viu").mkdir(parents=True, exist_ok=True)
    session = new_session(COMFY_TOPIC)
    session.steps_total = 9
    session.step = 3
    session.status = "awaiting_prompt"
    session.meta["action"] = "lying down sleep idle"
    session.meta["catalog_slug"] = "sleep_idle"
    save_session(cfg, session)

    with patch(
        "viu.lab.comfy_pipeline.send_prompt_for_approval",
        return_value=(True, "новый промпт в Telegram"),
    ), patch(
        "viu.lab.comfy_director.invent_redraft_shot",
        return_value=type(
            "P",
            (),
            {
                "action": "walking forward",
                "catalog_slug": "walk",
                "title_ru": "Ходьба",
                "enters_from": [],
                "exits_to": [],
                "looped": True,
                "reason": "test",
            },
        )(),
    ):
        out = apply_prompt_decision(
            cfg,
            load_session(cfg, COMFY_TOPIC),
            "redraft",
            "нет, мы другой промт хотели снимать",
        )

    assert "не тот кадр" in out.lower() or "Поняла" in out
    assert "Промпт принят" not in out
    loaded = load_session(cfg, COMFY_TOPIC)
    assert loaded is not None
    assert loaded.status == "awaiting_prompt"
    assert loaded.meta.get("approved") is not True
    assert loaded.meta.get("catalog_slug") == "walk"


def test_format_lab_progress_comfy_labels():
    from viu.lab.progress import format_lab_progress

    s = new_session(COMFY_TOPIC)
    s.steps_total = 9
    s.step = 1
    text = format_lab_progress(s, "ok")
    assert "Comfy online" in text
    assert "Cascadeur" not in text
