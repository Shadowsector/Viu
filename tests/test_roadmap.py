"""Тесты дорожной карты и автопилота (project_state)."""

from viu.config import Config
from viu.project_state import next_step, project_status
from viu.roadmap import Roadmap, RoadmapStore


def _config(tmp_path, **kw):
    return Config(root=tmp_path, data_dir=tmp_path / ".viu", **kw).ensure_dirs()


def test_roadmap_default_focus_is_walk():
    rm = Roadmap.default()
    focus = rm.current_focus()
    assert focus is not None
    assert "walk" in focus.title.lower() or "локомоц" in focus.title.lower()


def test_roadmap_store_persists(tmp_path):
    store = RoadmapStore(tmp_path / "roadmap.json")
    store.set_status(4, "done", note="walk работает")
    reopened = RoadmapStore(tmp_path / "roadmap.json")
    m4 = next(m for m in reopened.roadmap.milestones if m.id == 4)
    assert m4.status == "done"
    # После done фокус смещается с вехи 4 на другую незавершённую.
    assert reopened.roadmap.current_focus().id != 4


def test_roadmap_invalid_status(tmp_path):
    store = RoadmapStore(tmp_path / "roadmap.json")
    import pytest

    with pytest.raises(ValueError):
        store.set_status(4, "notastatus")


def test_next_step_no_unity(tmp_path):
    config = _config(tmp_path, unity_project="")
    msg = next_step(config)
    assert "Walk" in msg or "walk" in msg.lower()
    assert "проект" in msg.lower() or "unity" in msg.lower()


def test_next_step_missing_walk(tmp_path):
    unity = tmp_path / "unity"
    (unity / "Assets/Characters/Shanya/Animations").mkdir(parents=True)
    idle = unity / "Assets/Characters/Shanya/Animations/X Bot@Idle.fbx"
    idle.write_bytes(b"")
    config = _config(tmp_path, unity_project=str(unity))
    msg = next_step(config)
    assert "Walk" in msg
    assert "Добавить анимацию" in msg


def test_project_status_renders(tmp_path):
    config = _config(tmp_path, unity_project="")
    out = project_status(config)
    assert "Дорожная карта" in out
    assert "Следующий шаг" in out
