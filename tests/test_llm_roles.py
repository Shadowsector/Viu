"""Роли моделей — effective tag для UI."""

from viu.config import Config
from viu.llm_roles import effective_model, model_label, resolve_model


def test_effective_model_falls_back_to_viu_model(tmp_path):
    cfg = Config(
        root=tmp_path,
        data_dir=tmp_path / ".viu",
        model="qwen2.5:32b-instruct-q6_K",
        model_reflect="",
    )
    assert resolve_model(cfg, "reflect") is None
    assert effective_model(cfg, "reflect") == "qwen2.5:32b-instruct-q6_K"
    assert "без viu-обёртки" in model_label(cfg, "reflect")


def test_model_label_viu_wrap_clean(tmp_path):
    cfg = Config(
        root=tmp_path,
        data_dir=tmp_path / ".viu",
        model="qwen2.5:32b",
        model_reflect="viu-cydonia",
    )
    assert effective_model(cfg, "reflect") == "viu-cydonia"
    assert model_label(cfg, "reflect") == "viu-cydonia"
