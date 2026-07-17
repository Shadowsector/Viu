"""Runtime-выбор reflect-модели в GUI."""

from viu.config import Config
from viu.llm_roles import effective_model
from viu.runtime_settings import get_reflect_model_override, set_reflect_model_override


def test_reflect_model_persists_in_runtime_json(tmp_path):
    cfg = Config(root=tmp_path, data_dir=tmp_path / ".viu").ensure_dirs()
    assert get_reflect_model_override(cfg) == ""
    set_reflect_model_override(cfg, "viu-magnum")
    assert get_reflect_model_override(cfg) == "viu-magnum"
    cfg2 = Config(root=tmp_path, data_dir=tmp_path / ".viu")
    assert effective_model(cfg2, "reflect") == "viu-magnum"
