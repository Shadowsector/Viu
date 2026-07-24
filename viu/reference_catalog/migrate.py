"""Перенос старых путей референсов → Inbox/references/."""

from __future__ import annotations

import shutil
from pathlib import Path

from ..anabarra_layout import library_root
from ..config import Config
from ..inbox_layout import inbox_references_dir, ensure_inbox_readme


def migrate_legacy_reference_files(config: Config) -> tuple[int, str]:
    """Library/References/** и Inbox/references (если пусто после сбоя) — не восстановить удалённое.

    Копирует только то, что ещё лежит в Library/References (images и т.д.).
    """
    stamp = config.data_dir / "references_migrate_done"
    if stamp.is_file():
        return 0, ""
    ensure_inbox_readme(config)
    dest = inbox_references_dir(config)
    lib = library_root(config) / "References"
    n = 0
    if lib.is_dir():
        for src in lib.rglob("*"):
            if not src.is_file():
                continue
            if src.suffix.lower() not in (
                ".png",
                ".jpg",
                ".jpeg",
                ".webp",
                ".gif",
                ".mp4",
                ".webm",
                ".mov",
            ):
                continue
            rel = src.relative_to(lib)
            out = dest / rel.name if len(rel.parts) == 1 else dest / rel
            out.parent.mkdir(parents=True, exist_ok=True)
            if out.is_file():
                continue
            try:
                shutil.copy2(src, out)
                n += 1
            except OSError:
                pass
    try:
        stamp.write_text("ok\n", encoding="utf-8")
    except OSError:
        pass
    if n:
        return n, f"Перенесла {n} файл(ов) из Library/References → Inbox/references/."
    return 0, ""
