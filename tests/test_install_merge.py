"""Zip-обновление не должно затирать Inbox/references."""

from pathlib import Path

from viu.ollama_layout import merge_inbox_dir


def test_merge_inbox_keeps_user_references(tmp_path):
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
