"""Локальные Modelfile не затираются при zip-обновлении."""

from __future__ import annotations

from pathlib import Path

from viu.ollama_layout import copy_install_tree_item, merge_ollama_dir


def test_merge_ollama_preserves_local_modelfile(tmp_path: Path) -> None:
    src = tmp_path / "src" / "ollama"
    dest = tmp_path / "dest" / "ollama"
    src.mkdir(parents=True)
    dest.mkdir(parents=True)

    (src / "Modelfile.viu-cydonia.example").write_text("FROM template\nSYSTEM \"\"\"new\"\"\"", encoding="utf-8")
    (src / "Modelfile.viu-cydonia").write_text("FROM template\nSYSTEM \"\"\"from zip\"\"\"", encoding="utf-8")
    (dest / "Modelfile.viu-cydonia").write_text("FROM template\nSYSTEM \"\"\"my jailbreak\"\"\"", encoding="utf-8")

    merge_ollama_dir(src, dest)

    assert (dest / "Modelfile.viu-cydonia").read_text(encoding="utf-8") == (
        'FROM template\nSYSTEM """my jailbreak"""'
    )
    assert (dest / "Modelfile.viu-cydonia.example").read_text(encoding="utf-8") == (
        'FROM template\nSYSTEM """new"""'
    )


def test_merge_ollama_seeds_missing_local_from_zip(tmp_path: Path) -> None:
    src = tmp_path / "src" / "ollama"
    dest = tmp_path / "dest" / "ollama"
    src.mkdir(parents=True)
    dest.mkdir(parents=True)

    (src / "Modelfile.viu-magnum").write_text("FROM magnum\nSYSTEM \"\"\"zip\"\"\"", encoding="utf-8")

    merge_ollama_dir(src, dest)

    assert (dest / "Modelfile.viu-magnum").read_text(encoding="utf-8") == (
        'FROM magnum\nSYSTEM """zip"""'
    )


def test_copy_install_tree_item_merges_ollama_dir(tmp_path: Path) -> None:
    src_root = tmp_path / "zip"
    dest_root = tmp_path / "viu"
    ollama_src = src_root / "ollama"
    ollama_dest = dest_root / "ollama"
    ollama_src.mkdir(parents=True)
    ollama_dest.mkdir(parents=True)

    (ollama_src / "Modelfile.viu-cydonia.example").write_text("example", encoding="utf-8")
    (ollama_dest / "Modelfile.viu-cydonia").write_text("local", encoding="utf-8")

    copy_install_tree_item(ollama_src, dest_root)

    assert (ollama_dest / "Modelfile.viu-cydonia").read_text(encoding="utf-8") == "local"
    assert (ollama_dest / "Modelfile.viu-cydonia.example").read_text(encoding="utf-8") == "example"
