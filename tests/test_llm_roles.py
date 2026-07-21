"""Роли моделей — effective tag для UI."""

from viu.config import Config
from viu.llm_roles import effective_model, model_label, needs_viu_wrap_hint, resolve_model


def test_runtime_reflect_override(tmp_path):
    from viu.runtime_settings import set_reflect_model_override

    cfg = Config(
        root=tmp_path,
        data_dir=tmp_path / ".viu",
        model_reflect="viu-cydonia",
    ).ensure_dirs()
    assert effective_model(cfg, "reflect") == "viu-cydonia"
    set_reflect_model_override(cfg, "viu-command-r")
    assert effective_model(cfg, "reflect") == "viu-command-r"
    assert model_label(cfg, "reflect") == "viu-command-r"


def test_reflect_combo_labels():
    from viu.llm_roles import REFLECT_MODEL_IDS, reflect_combo_labels, reflect_model_from_combo

    labels = reflect_combo_labels()
    assert any("viu-command-r" in x for x in labels)
    assert reflect_model_from_combo(labels[1]) in REFLECT_MODEL_IDS


def test_empty_reflect_defaults_to_viu_cydonia(tmp_path):
    cfg = Config(
        root=tmp_path,
        data_dir=tmp_path / ".viu",
        model="qwen2.5-coder:14b",
        model_reflect="",
        model_work="",
        model_code="qwen2.5-coder:14b",
    )
    assert resolve_model(cfg, "reflect") is None
    assert effective_model(cfg, "reflect") == "viu-cydonia"
    assert effective_model(cfg, "work") == "viu-qwen32"
    assert effective_model(cfg, "code") == "qwen2.5-coder:14b"
    assert model_label(cfg, "reflect") == "viu-cydonia"
    assert not needs_viu_wrap_hint(cfg)


def test_explicit_bare_reflect_hint(tmp_path):
    cfg = Config(
        root=tmp_path,
        data_dir=tmp_path / ".viu",
        model="viu-qwen32",
        model_reflect="qwen2.5-coder:14b",
    )
    assert effective_model(cfg, "reflect") == "qwen2.5-coder:14b"
    assert needs_viu_wrap_hint(cfg)


def test_explicit_viu_wrap_clean(tmp_path):
    cfg = Config(
        root=tmp_path,
        data_dir=tmp_path / ".viu",
        model="qwen2.5:32b",
        model_reflect="viu-cydonia",
        model_work="viu-qwen32",
    )
    assert effective_model(cfg, "reflect") == "viu-cydonia"
    assert model_label(cfg, "reflect") == "viu-cydonia"
    assert not needs_viu_wrap_hint(cfg)
