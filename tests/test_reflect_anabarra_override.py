"""Личный reflect_mode в Anabarra не затирается zip-апдейтом."""

from __future__ import annotations

from pathlib import Path

from install_merge import (
    copy_install_tree_item,
    load_reflect_mode_override,
    preserve_reflect_mode,
    user_reflect_mode_path,
)


def test_preserve_reflect_mode_seeds_anabarra_once(tmp_path: Path, monkeypatch) -> None:
    viu = tmp_path / "Viu"
    anabarra = tmp_path / "Anabarra"
    anabarra.mkdir()
    monkeypatch.setenv("VIU_ANABARRA_ROOT", str(anabarra))

    src = viu / "viu" / "prompts" / "reflect_mode.py"
    src.parent.mkdir(parents=True)
    src.write_text("REFLECT_VOICE = 'mine'\n", encoding="utf-8")

    msg = preserve_reflect_mode(viu)
    dest = user_reflect_mode_path(viu)
    assert dest.is_file()
    assert "mine" in dest.read_text(encoding="utf-8")
    assert "ViuPrompts" in msg

    # Повторно не перезаписываем редакцию пользователя.
    src.write_text("REFLECT_VOICE = 'from-zip'\n", encoding="utf-8")
    assert preserve_reflect_mode(viu) == ""
    assert dest.read_text(encoding="utf-8") == "REFLECT_VOICE = 'mine'\n"


def test_zip_viu_wipe_keeps_anabarra_override(tmp_path: Path, monkeypatch) -> None:
    viu = tmp_path / "Viu"
    anabarra = tmp_path / "Anabarra"
    anabarra.mkdir()
    monkeypatch.setenv("VIU_ANABARRA_ROOT", str(anabarra))

    local = viu / "viu" / "prompts" / "reflect_mode.py"
    local.parent.mkdir(parents=True)
    local.write_text("REFLECT_VOICE = 'local-edit'\n", encoding="utf-8")
    (viu / "viu" / "other.py").write_text("x=1\n", encoding="utf-8")

    zip_viu = tmp_path / "zip" / "viu"
    (zip_viu / "prompts").mkdir(parents=True)
    (zip_viu / "prompts" / "reflect_mode.py").write_text(
        "REFLECT_VOICE = 'stock'\n", encoding="utf-8"
    )
    (zip_viu / "other.py").write_text("x=2\n", encoding="utf-8")

    copy_install_tree_item(zip_viu, viu)

    # Пакет обновлён шаблоном…
    assert (viu / "viu" / "prompts" / "reflect_mode.py").read_text(
        encoding="utf-8"
    ) == "REFLECT_VOICE = 'stock'\n"
    # …а личная копия в Анабарре цела.
    assert user_reflect_mode_path(viu).read_text(encoding="utf-8") == (
        "REFLECT_VOICE = 'local-edit'\n"
    )


def test_load_reflect_mode_override_applies_voice(tmp_path: Path, monkeypatch) -> None:
    viu = tmp_path / "Viu"
    anabarra = tmp_path / "Anabarra"
    anabarra.mkdir()
    monkeypatch.setenv("VIU_ANABARRA_ROOT", str(anabarra))

    override = user_reflect_mode_path(viu)
    override.parent.mkdir(parents=True)
    override.write_text(
        "REFLECT_VOICE = 'from-anabarra'\nNSFW_AFFIRM_FALLBACK = 'ok'\n",
        encoding="utf-8",
    )

    ns = {"REFLECT_VOICE": "stock", "NSFW_AFFIRM_FALLBACK": "old"}
    path = load_reflect_mode_override(ns, viu)
    assert path == override
    assert ns["REFLECT_VOICE"] == "from-anabarra"
    assert ns["NSFW_AFFIRM_FALLBACK"] == "ok"
