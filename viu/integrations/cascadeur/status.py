"""Статус интеграции Cascadeur."""

from __future__ import annotations

from pathlib import Path

from ...config import Config
from .exe import resolve_cascadeur_exe
from .paths import cascadeur_export, cascadeur_inbox


def cascadeur_status(config: Config) -> tuple[bool, str]:
    lines: list[str] = ["Cascadeur — мост Viu ↔ анимации"]
    try:
        exe = resolve_cascadeur_exe(config)
        lines.append(f"• exe: {exe}")
        ok = True
    except FileNotFoundError as exc:
        lines.append(f"• exe: не найден\n  {exc}")
        ok = False

    inbox = cascadeur_inbox(config)
    export = cascadeur_export(config)
    inbox_fbx = sorted(inbox.glob("*.fbx")) if inbox.is_dir() else []
    export_fbx = sorted(export.glob("*.fbx")) if export.is_dir() else []

    lines.append(f"• Inbox (править в Cascadeur): {inbox}")
    lines.append(f"  FBX: {len(inbox_fbx)}" + (f" — {inbox_fbx[0].name}" if inbox_fbx else ""))
    lines.append(f"• Export → Unity staging: {export}")
    lines.append(f"  FBX: {len(export_fbx)}")

    lines.append(
        "\nWorkflow: Mixamo/Blender FBX → Library/Cascadeur/Inbox → "
        "правка в Cascadeur → Export в Animations → «Обновить аниматор» в Unity."
    )
    if not ok:
        lines.append("\nЗадай VIU_CASCADEUR_EXE в .env — Вью пока только показывает пути.")
    return ok, "\n".join(lines)
