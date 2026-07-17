from viu.memory import MemoryStore
from viu.planning import Planner


def test_memory_add_search_persist(tmp_path):
    path = tmp_path / "memory.json"
    store = MemoryStore(path)
    store.add("Движок для Анабарры пока не выбран", tags=["анабарра"])
    store.add("Прототип уровня должен быть маленьким", tags=["дизайн"])

    hits = store.search("анабарра")
    assert hits and "Анабарры" in hits[0].text

    # Проверяем персистентность: новый экземпляр читает тот же файл.
    reloaded = MemoryStore(path)
    assert len(reloaded.all()) == 2


def test_memory_corrupted_file_is_safe(tmp_path):
    path = tmp_path / "memory.json"
    path.write_text("{ not json", encoding="utf-8")
    store = MemoryStore(path)
    assert store.all() == []


def test_planner_create_update_persist(tmp_path):
    path = tmp_path / "plan.json"
    planner = Planner(path)
    planner.create("Основа игры", ["Шаг 1", "Шаг 2"])
    planner.update_step(1, status="done", note="готово")

    reloaded = Planner(path)
    assert reloaded.plan.goal == "Основа игры"
    assert reloaded.plan.steps[0].status == "done"
    assert reloaded.plan.steps[0].note == "готово"


def test_planner_invalid_status(tmp_path):
    planner = Planner(tmp_path / "plan.json")
    planner.create("g", ["a"])
    try:
        planner.update_step(1, status="bogus")
        assert False, "должно бросить ValueError"
    except ValueError:
        pass
