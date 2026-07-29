"""Тесты merge Inbox и VIU_MEMORY."""

from __future__ import annotations

from pathlib import Path

from install_merge import merge_inbox_dir
from viu.ollama_layout import copy_install_tree_item
from viu.viu_memory import (
    append_memory_line,
    ensure_viu_memory,
    extract_remember_payload,
    format_reflect_block,
    looks_like_memory_echo,
    process_reflect_exchange,
    read_viu_memory,
    sanitize_poisoned_summaries,
    viu_memory_path,
    _SECTION_EXPLICIT,
    _SECTION_SUMMARIES,
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
    assert extract_remember_payload("запомни, что Inbox не должен пустеть") == (
        "Inbox не должен пустеть"
    )
    assert extract_remember_payload("держи в памяти: Шаня — томбой") == (
        "Шаня — томбой"
    )
    assert extract_remember_payload("привет") is None


def test_remember_survives_memory_echo_assistant(tmp_path: Path, monkeypatch) -> None:
    """Даже если ассистент свалился в дамп VIU_MEMORY — «запомни» пишется."""
    from viu.config import Config

    monkeypatch.setenv("VIU_ROOT", str(tmp_path / "Viu"))
    root = tmp_path / "Viu"
    root.mkdir()
    cfg = Config(root=root, data_dir=root / ".viu").ensure_dirs()
    echo = "# Память Вью\n\n## Явные записи\n\n- старое\n"
    process_reflect_exchange(
        cfg,
        "запомни: мы сочинили историю про сарай и Шаню",
        echo,
    )
    text = read_viu_memory(cfg)
    assert "сарай" in text.lower() or "шаню" in text.lower()



def test_remember_with_conversation_context(tmp_path: Path, monkeypatch) -> None:
    from viu.config import Config
    from viu.viu_memory import (
        remember_needs_context,
        resolve_remember_payload,
    )

    monkeypatch.setenv("VIU_ROOT", str(tmp_path / "Viu"))
    root = tmp_path / "Viu"
    root.mkdir()
    cfg = Config(root=root, data_dir=root / ".viu").ensure_dirs()

    assert remember_needs_context("этот квест")
    assert remember_needs_context("это")
    assert not remember_needs_context(
        "Inbox не должен пустеть при zip-апдейте никогда"
    )

    history = [
        {"role": "user", "content": "Квест: найти домового в сарае до заката."},
        {
            "role": "assistant",
            "content": "Ок, квест «Домовой в сарае»: найти его до заката, награда — ключ.",
        },
        {"role": "user", "content": "И Оля боится туда идти одна."},
        {
            "role": "assistant",
            "content": "Запомнила: Оля не идёт в сарай без поддержки.",
        },
    ]
    payload = resolve_remember_payload(
        cfg,
        "запомни этот квест",
        history=history,
        assistant_text="Хорошо, держу квест про домового в памяти.",
    )
    assert payload is not None
    assert "домового" in payload.lower() or "сарай" in payload.lower()
    assert "запомни" not in payload.lower()

    process_reflect_exchange(
        cfg,
        "запомни этот квест",
        "Хорошо, держу квест про домового в памяти.",
        history=history,
    )
    text = read_viu_memory(cfg)
    assert "домового" in text.lower() or "сарай" in text.lower()
    assert _SECTION_EXPLICIT in text


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


def test_memory_echo_detection_and_sanitize(tmp_path: Path, monkeypatch) -> None:
    from viu.config import Config

    monkeypatch.setenv("VIU_ROOT", str(tmp_path / "Viu"))
    root = tmp_path / "Viu"
    root.mkdir()
    cfg = Config(root=root, data_dir=root / ".viu")

    dump = (
        "# Память Вью\n\n## Явные записи\n\n"
        "<!-- сюда попадает «запомни» -->\n\n"
        "## Привычки и предпочтения\n\n- мяу\n"
    )
    assert looks_like_memory_echo(dump)
    assert not looks_like_memory_echo("Конечно, Ден — продолжаю по студии.")

    ensure_viu_memory(cfg)
    path = viu_memory_path(cfg)
    text = path.read_text(encoding="utf-8")
    text = text.replace(
        _SECTION_SUMMARIES,
        _SECTION_SUMMARIES
        + "\n\n- (2026-07-25) Ден: как там? → Вью: # Память Вью ## Явные записи\n"
        + "- (ok) Ден: привет → Вью: мяу, гладьки\n",
    )
    path.write_text(text, encoding="utf-8")
    removed = sanitize_poisoned_summaries(cfg)
    assert removed >= 1
    cleaned = path.read_text(encoding="utf-8")
    assert "# Память Вью ## Явные" not in cleaned
    assert "мяу, гладьки" in cleaned

    append_memory_line(cfg, _SECTION_EXPLICIT, "- (2026-07-26) не трогай Inbox")
    block = format_reflect_block(cfg)
    assert "не трогай Inbox" in block
    assert "Итоги чатов" not in block
    assert "Явные:" in block

    # Эхо-ответ не пишется в итоги
    before = path.read_text(encoding="utf-8")
    process_reflect_exchange(cfg, "Вью, как там?", dump, source="chat")
    assert path.read_text(encoding="utf-8") == before
