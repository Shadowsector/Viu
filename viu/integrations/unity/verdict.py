"""Краткий вердикт по состоянию Unity-проекта."""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from .log_parser import UnityLogSummary
from .project_scan import UnityProjectScan


def build_verdict(
    log: UnityLogSummary,
    scan: Optional[UnityProjectScan],
    all_cs: List[str],
) -> str:
    lines = ["=== Вердикт ==="]
    cs_count = len(all_cs) or len(log.compiler_errors)
    if log.safe_mode or log.playmode_blockers or cs_count:
        if log.safe_mode and not cs_count and not log.playmode_blockers:
            lines.append("⛔ Unity в Safe Mode — Play и анимацию проверить нельзя.")
            lines.append("   Причина: ошибки компиляции C# (см. Console / Editor.log).")
            lines.append("   Действие: Package Manager → Remove/Update Input System")
            lines.append("   или новый проект Universal 3D на Unity LTS.")
            return "\n".join(lines)
        lines.append("⛔ Play Mode ЗАБЛОКИРОВАН — анимацию проверить нельзя.")
        lines.append(f"   Причина: ошибки компиляции C# ({cs_count} в Editor.log).")
        lines.append("   Действие: Unity Console → первая красная CS → исправить")
        lines.append("   или новый проект Universal 3D / удалить Library + TutorialInfo.")
        return "\n".join(lines)

    if log.rig_errors:
        lines.append("⛔ Rig Error в логе — проверь Humanoid (Create From This Model).")
        return "\n".join(lines)

    if scan and scan.fbx_files:
        names = ", ".join(Path(f.fbx_path).name for f in scan.fbx_files)
        lines.append(f"✓ FBX в проекте: {names} (Humanoid).")
    else:
        lines.append("? FBX не найдены в Assets/.")

    lines.append("")
    lines.append("Если Play жмётся, но модель в T-pose:")
    lines.append("  • Animator → Controller + Avatar Shanya_ErisaAvatar")
    lines.append("  • Смотри вкладку Game (не Scene)")
    lines.append("  • Mixamo FBX: Create From This Model, Without Skin")
    return "\n".join(lines)
