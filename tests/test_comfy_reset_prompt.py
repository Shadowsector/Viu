"""Reset lab comfy не должен тащить чужой Wan-промпт на новый slug."""

from __future__ import annotations

from viu.lab.comfy_pipeline import COMFY_TOPIC
from viu.lab.prepare import prepare_lab_session
from viu.lab.session import new_session, save_session


def test_comfy_reset_does_not_keep_foreign_prompt(tmp_path, monkeypatch):
    from viu.config import Config

    cfg = Config(data_dir=tmp_path / ".viu")
    cfg.data_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("VIU_DATA_DIR", str(cfg.data_dir))

    old = new_session(COMFY_TOPIC)
    old.meta.update(
        {
            "catalog_slug": "sit_down",
            "action": "from standing to sit on a bed",
            "approved_action": "from standing to sit on a bed",
            "wan_positive": "nude young woman is sit up on a bed",
            "draft": "old draft",
            "lora_last_pick": [1],
        }
    )
    save_session(cfg, old)

    session, mode, note = prepare_lab_session(cfg, COMFY_TOPIC, force_reset=True)
    assert mode == "fresh"
    assert session.meta.get("wan_positive") in (None, "")
    assert session.meta.get("approved_action") in (None, "")
    assert session.meta.get("catalog_slug") in (None, "")
    assert session.meta.get("lora_last_pick") == [1]
    assert "LoRA" in note or "пресет" in note.lower()


def test_director_summary_uses_take_count():
    from viu.integrations.comfy.angles import mocap_take_count
    from viu.lab.comfy_director import MocapShotPlan

    plan = MocapShotPlan(
        action="touch self while seated",
        catalog_slug="touch_self",
        enters_from=["idle"],
        exits_to=["sit_idle"],
        reason="test",
        title_ru="Ласкает себя",
    )
    text = plan.summary_ru()
    assert f"{mocap_take_count()} разных дублей" in text
    if mocap_take_count() != 3:
        assert "3 разных дубля" not in text
