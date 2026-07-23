"""Тесты merge Inbox и VIU_MEMORY."""

from __future__ import annotations

from pathlib import Path

from install_merge import merge_inbox_dir
from viu.ollama_layout import copy_install_tree_item
from viu.viu_memory import (
    append_memory_line,
    ensure_viu_memory,
    extract_remember_payload,
    process_reflect_exchange,
    read_viu_memory,
    viu_memory_path,
    _SECTION_EXPLICIT,
)


def test_merge_inbox_preserves_user_files(tmp_path: Path) -> None:
    src = tmp_path / "zip" / "Inbox"
    dest = tmp_path / "viu" / "Inbox"
    src.mkdir(parents=True)
    dest.mkdir(parents=True)

    (src / "README.txt").write_text("from zip", encoding="utf-8")
    (src / "references").mkdir()
    (src / "references" / "README.txt").write_text("refs readme", encoding="utf-8")
    (dest / "references").mkdir()
    (dest / "references" / "my_pose.png").write_bytes(b"user image")
    (dest / "README.txt").write_text("user readme", encoding="utf-8")

    merge_inbox_dir(src, dest)

    assert (dest / "references" / "my_pose.png").read_bytes() == b"user image"
    # README из zip обновляется; пользовательские файлы — нет
    assert (dest / "README.txt").read_text(encoding="utf-8") == "from zip"
    assert (dest / "references" / "README.txt").read_text(encoding="utf-8") == "refs readme"


def test_copy_install_tree_item_merges_inbox(tmp_path: Path) -> None:
    src_root = tmp_path / "zip"
    dest_root = tmp_path / "viu"
    inbox_src = src_root / "Inbox"
    inbox_dest = dest_root / "Inbox"
    inbox_src.mkdir(parents=True)
    inbox_dest.mkdir(parents=True)
    (inbox_src / "references").mkdir()
    (inbox_dest / "references").mkdir()
    (inbox_dest / "references" / "keep.jpg").write_bytes(b"x")

    copy_install_tree_item(inbox_src, dest_root)

    assert (inbox_dest / "references" / "keep.jpg").read_bytes() == b"x"


def test_extract_remember_payload() -> None:
    assert extract_remember_payload("запомни: я не писал промпты для Wan") == (
        "я не писал промпты для Wan"
    )
    assert extract_remember_payload("привет") is None


def test_viu_memory_explicit_and_summary(tmp_path: Path, monkeypatch) -> None:
    from viu.config import Config

    monkeypatch.setenv("VIU_ROOT", str(tmp_path / "Viu"))
    root = tmp_path / "Viu"
    root.mkdir()
    cfg = Config(root=root, data_dir=root / ".viu")

    ensure_viu_memory(cfg)
    assert viu_memory_path(cfg).is_file()

    process_reflect_exchange(cfg, "запомни: Inbox не должен пустеть при апдейте", "ок")
    text = read_viu_memory(cfg)
    assert "Inbox не должен пустеть" in text
    assert _SECTION_EXPLICIT in text

    append_memory_line(cfg, _SECTION_EXPLICIT, "- (test) duplicate")
    again = read_viu_memory(cfg)
    assert again.count("(test) duplicate") == 1
