"""Личный reflect_mode в Anabarra: голос переживает zip, plumbing — нет."""

from __future__ import annotations

from pathlib import Path

from install_merge import (
    copy_install_tree_item,
    extract_reflect_voice_values,
    format_voice_only_reflect,
    load_reflect_mode_override,
    migrate_stale_reflect_override,
    preserve_reflect_mode,
    user_reflect_mode_path,
)


def test_preserve_reflect_mode_seeds_voice_only(tmp_path: Path, monkeypatch) -> None:
    viu = tmp_path / "Viu"
    anabarra = tmp_path / "Anabarra"
    anabarra.mkdir()
    monkeypatch.setenv("VIU_ANABARRA_ROOT", str(anabarra))

    src = viu / "viu" / "prompts" / "reflect_mode.py"
    src.parent.mkdir(parents=True)
    src.write_text(
        'REFLECT_VOICE = "mine"\n'
        "REFLECT_BARE = REFLECT_VOICE\n"
        "def reflect_no_system():\n"
        "    return True\n",
        encoding="utf-8",
    )

    msg = preserve_reflect_mode(viu)
    dest = user_reflect_mode_path(viu)
    assert dest.is_file()
    text = dest.read_text(encoding="utf-8")
    assert "mine" in text
    assert "REFLECT_OVERRIDE_FORMAT" in text
    assert "def reflect_no_system" not in text
    assert "голос" in msg.lower() or "ViuPrompts" in msg

    # Повторно не перезаписываем редакцию пользователя.
    src.write_text('REFLECT_VOICE = "from-zip"\n', encoding="utf-8")
    assert preserve_reflect_mode(viu) == ""
    assert "mine" in dest.read_text(encoding="utf-8")
    assert "from-zip" not in dest.read_text(encoding="utf-8")


def test_zip_viu_wipe_keeps_anabarra_override(tmp_path: Path, monkeypatch) -> None:
    viu = tmp_path / "Viu"
    anabarra = tmp_path / "Anabarra"
    anabarra.mkdir()
    monkeypatch.setenv("VIU_ANABARRA_ROOT", str(anabarra))

    local = viu / "viu" / "prompts" / "reflect_mode.py"
    local.parent.mkdir(parents=True)
    local.write_text('REFLECT_VOICE = "local-edit"\n', encoding="utf-8")
    (viu / "viu" / "other.py").write_text("x=1\n", encoding="utf-8")

    zip_viu = tmp_path / "zip" / "viu"
    (zip_viu / "prompts").mkdir(parents=True)
    (zip_viu / "prompts" / "reflect_mode.py").write_text(
        'REFLECT_VOICE = "stock"\n', encoding="utf-8"
    )
    (zip_viu / "other.py").write_text("x=2\n", encoding="utf-8")

    copy_install_tree_item(zip_viu, viu)

    assert (viu / "viu" / "prompts" / "reflect_mode.py").read_text(
        encoding="utf-8"
    ) == 'REFLECT_VOICE = "stock"\n'
    assert "local-edit" in user_reflect_mode_path(viu).read_text(encoding="utf-8")


def test_load_reflect_mode_override_applies_voice(tmp_path: Path, monkeypatch) -> None:
    viu = tmp_path / "Viu"
    anabarra = tmp_path / "Anabarra"
    anabarra.mkdir()
    monkeypatch.setenv("VIU_ANABARRA_ROOT", str(anabarra))

    override = user_reflect_mode_path(viu)
    override.parent.mkdir(parents=True)
    override.write_text(
        format_voice_only_reflect(
            {
                "REFLECT_VOICE": "from-anabarra",
                "NSFW_AFFIRM_FALLBACK": "ok",
            }
        ),
        encoding="utf-8",
    )

    ns = {"REFLECT_VOICE": "stock", "NSFW_AFFIRM_FALLBACK": "old"}
    path = load_reflect_mode_override(ns, viu)
    assert path == override
    assert ns["REFLECT_VOICE"] == "from-anabarra"
    assert ns["NSFW_AFFIRM_FALLBACK"] == "ok"
    assert ns["REFLECT_BARE"] == "from-anabarra"


def test_stale_full_override_does_not_wipe_plumbing(
    tmp_path: Path, monkeypatch
) -> None:
    """Полный старый снимок больше не откатывает reflect_no_system из пакета."""
    viu = tmp_path / "Viu"
    anabarra = tmp_path / "Anabarra"
    anabarra.mkdir()
    monkeypatch.setenv("VIU_ANABARRA_ROOT", str(anabarra))

    override = user_reflect_mode_path(viu)
    override.parent.mkdir(parents=True)
    override.write_text(
        'REFLECT_VOICE = "den-voice"\n'
        "def reflect_no_system():\n"
        "    return False\n"
        "def reflect_use_filters():\n"
        "    return True\n",
        encoding="utf-8",
    )

    def package_no_system() -> bool:
        return True

    ns = {
        "REFLECT_VOICE": "stock",
        "reflect_no_system": package_no_system,
        "reflect_use_filters": lambda: False,
    }
    load_reflect_mode_override(ns, viu)
    assert ns["REFLECT_VOICE"] == "den-voice"
    assert ns["reflect_no_system"] is package_no_system
    assert ns["reflect_no_system"]() is True
    assert ns["reflect_use_filters"]() is False

    # Файл мигрирован в voice-only.
    text = override.read_text(encoding="utf-8")
    assert "REFLECT_OVERRIDE_FORMAT" in text
    assert "def reflect_no_system" not in text
    backups = list(override.parent.glob("reflect_mode.py.bak-full-*"))
    assert backups


def test_migrate_stale_reflect_override_idempotent(
    tmp_path: Path, monkeypatch
) -> None:
    viu = tmp_path / "Viu"
    anabarra = tmp_path / "Anabarra"
    anabarra.mkdir()
    monkeypatch.setenv("VIU_ANABARRA_ROOT", str(anabarra))

    override = user_reflect_mode_path(viu)
    override.parent.mkdir(parents=True)
    override.write_text(
        format_voice_only_reflect({"REFLECT_VOICE": "already-ok"}),
        encoding="utf-8",
    )
    assert migrate_stale_reflect_override(viu) == ""
    assert override.read_text(encoding="utf-8").count("already-ok") == 1


def test_extract_reflect_voice_values_aliases(tmp_path: Path) -> None:
    path = tmp_path / "reflect_mode.py"
    path.write_text(
        'REFLECT_VOICE = "v"\nREFLECT_BARE = REFLECT_VOICE\n',
        encoding="utf-8",
    )
    values = extract_reflect_voice_values(path)
    assert values["REFLECT_VOICE"] == "v"
    assert values["REFLECT_BARE"] == "v"
