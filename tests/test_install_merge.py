"""Тесты install_merge и bootstrap zip (Inbox не затирается)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

from install_merge import copy_install_tree_item, merge_inbox_dir


def test_merge_inbox_keeps_user_references(tmp_path: Path) -> None:
    dest = tmp_path / "Inbox"
    refs = dest / "references"
    refs.mkdir(parents=True)
    user_file = refs / "my_pose.png"
    user_file.write_bytes(b"user")

    src = tmp_path / "zip" / "Inbox"
    src_refs = src / "references"
    src_refs.mkdir(parents=True)
    (src_refs / "README.txt").write_text("new readme\n", encoding="utf-8")
    (src / "README.txt").write_text("inbox readme\n", encoding="utf-8")

    merge_inbox_dir(src, dest)

    assert user_file.is_file()
    assert user_file.read_bytes() == b"user"
    assert (refs / "README.txt").read_text(encoding="utf-8") == "new readme\n"


def test_copy_install_tree_item_never_wipes_inbox(tmp_path: Path) -> None:
    dest_root = tmp_path / "viu"
    dest_root.mkdir()
    inbox = dest_root / "Inbox"
    refs = inbox / "references"
    refs.mkdir(parents=True)
    (refs / "clip.mp4").write_bytes(b"data")

    src_root = tmp_path / "archive"
    src_inbox = src_root / "Inbox"
    (src_inbox / "references" / "README.txt").parent.mkdir(parents=True)
    (src_inbox / "references" / "README.txt").write_text("readme", encoding="utf-8")

    copy_install_tree_item(src_inbox, dest_root)

    assert (refs / "clip.mp4").read_bytes() == b"data"


def test_bootstrap_loader_uses_install_merge_from_extracted_zip(tmp_path: Path, monkeypatch) -> None:
    """Симуляция: на диске старый код, в zip — install_merge.py."""
    repo = tmp_path / "live"
    repo.mkdir()
    extract = tmp_path / "extract" / "Viu-branch"
    extract.mkdir(parents=True)
    merge_src = Path(__file__).resolve().parents[1] / "install_merge.py"
    (extract / "install_merge.py").write_text(
        merge_src.read_text(encoding="utf-8"), encoding="utf-8"
    )
    inbox_zip = extract / "Inbox"
    (inbox_zip / "references").mkdir(parents=True)
    (inbox_zip / "references" / "README.txt").write_text("z", encoding="utf-8")

    user_inbox = repo / "Inbox" / "references"
    user_inbox.mkdir(parents=True)
    (user_inbox / "photo.png").write_bytes(b"x")

    spec = importlib.util.spec_from_file_location(
        "_viu_install_merge", extract / "install_merge.py"
    )
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.copy_install_tree_item(inbox_zip, repo)

    assert (user_inbox / "photo.png").read_bytes() == b"x"
