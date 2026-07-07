"""Проверка результата setup / Play по логам и файлам проекта."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from .log_parser import UnityLogSummary, extract_compiler_errors, parse_editor_log
from .project_scan import UnityProjectScan, scan_unity_project

_SETUP_OK = re.compile(r"\[Viu\]\s*Setup готов", re.I)
_SETUP_ERR = re.compile(r"\[Viu\].*(?:Error|не найден|Avatar не найден)", re.I)
_PLAY_ENTER = re.compile(
    r"Entering Play Mode|Entered Play Mode|Exiting Play Mode",
    re.I,
)
_ANIMATOR = re.compile(r"Animator is not playing|No controller|Avatar is invalid", re.I)


@dataclass
class UnityVerifyResult:
    project_path: str
    setup_log_ok: bool = False
    setup_log_errors: List[str] = field(default_factory=list)
    editor_log: Optional[UnityLogSummary] = None
    scan: Optional[UnityProjectScan] = None
    controller_found: bool = False
    editor_script_found: bool = False
    play_entered: bool = False
    cs_errors: List[str] = field(default_factory=list)
    locomotion_in_scene: bool = False
    scene_exists: bool = False

    def render(self) -> str:
        lines = ["=== Проверка setup / Play ==="]

        if self.setup_log_ok:
            lines.append("✓ viu_setup.log: Setup Shanya завершён успешно.")
        elif self.setup_log_errors:
            lines.append("⛔ viu_setup.log: ошибки setup:")
            for e in self.setup_log_errors[:8]:
                lines.append(f"  • {e}")
        else:
            lines.append("? viu_setup.log: нет записи об успехе — нажми «Тест: Шаня стоит и ходит».")

        if self.scene_exists:
            lines.append("✓ Сцена Assets/Scenes/GameTest.unity найдена.")
        else:
            lines.append("→ Нет GameTest.unity — «Тест: Шаня стоит и ходит».")

        if self.locomotion_in_scene:
            lines.append("✓ ShanyaLocomotion на сцене (A/D должны работать).")
        elif self.scene_exists:
            lines.append(
                "→ На сцене нет ShanyaLocomotion — A/D не сработают. "
                "Нажми «Тест: Шаня стоит и ходит»."
            )

        if self.editor_script_found:
            lines.append("✓ Editor-скрипт Viu установлен (Assets/Editor/Viu/).")
        else:
            lines.append("→ Нет ShanyaSetup.cs — вызови unity_deploy_setup.")

        if self.controller_found:
            lines.append("✓ Animator Controller Shanya_Idle_Stand найден.")
        else:
            lines.append("→ Controller не найден — Viu → Setup Shanya (Idle).")

        cs = self.cs_errors or (self.editor_log.compiler_errors if self.editor_log else [])
        if self.editor_log and self.editor_log.safe_mode:
            lines.append("⛔ Unity в Safe Mode — Play недоступен.")
        elif cs:
            lines.append(f"⛔ CS-ошибки ({len(cs)}) — Play заблокирован.")
            lines.append(f"  • {cs[0][:180]}")
        elif self.editor_log and self.editor_log.playmode_blockers:
            lines.append("⛔ Play Mode заблокирован (compiler errors).")
        elif self.play_entered:
            lines.append("✓ Play Mode был (запись в Editor.log). Кликни окно Game перед A/D.")
        elif self.editor_log:
            lines.append(
                "? Play в хвосте Editor.log не виден (лог мог прокрутиться). "
                "Если уже жал Play — смотри Game tab, не Scene."
            )

        if self.editor_log and self.editor_log.rig_errors:
            lines.append("⛔ Rig Error в Editor.log — проверь Humanoid Configure.")

        if self.scan and self.scan.fbx_files:
            n = len(self.scan.fbx_files)
            lines.append(f"✓ FBX в проекте: {n}.")

        # Итог
        lines.append("")
        if cs or (self.editor_log and (self.editor_log.safe_mode or self.editor_log.playmode_blockers)):
            lines.append("Вердикт: ⛔ сначала исправь компиляцию (unity_fix_manifest / новый проект).")
        elif not self.controller_found:
            lines.append("Вердикт: 🚧 нет Animator — «Обновить аниматор» или импорт FBX.")
        elif not self.setup_log_ok or not self.locomotion_in_scene:
            lines.append(
                "Вердикт: 🚧 Animator готов, сцена не собрана — «Тест: Шаня стоит и ходит», "
                "потом Play в окне Game, A/D."
            )
        elif self.play_entered and not self.editor_log.rig_errors:
            lines.append("Вердикт: ✓ по логам всё готово — смотри Game tab, Idle должен играть.")
        else:
            lines.append(
                "Вердикт: 🚧 сцена есть. Play в Unity → кликни Game → A/D. "
                "Idle не зациклен? — «Обновить аниматор»."
            )

        return "\n".join(lines)


def _read_setup_log(project_root: Path) -> tuple[bool, List[str]]:
    log = project_root / "viu_setup.log"
    if not log.is_file():
        return False, []
    text = log.read_text(encoding="utf-8", errors="replace")
    errors = [ln.strip() for ln in text.splitlines() if _SETUP_ERR.search(ln)]
    ok = bool(_SETUP_OK.search(text))
    return ok, errors


def _scan_project_files(project_root: Path) -> tuple[bool, bool]:
    controller_paths = (
        project_root / "Assets/Characters/Shanya/Animations/Shanya_Idle_Stand.controller",
        project_root / "Assets/Characters/Shanya/Shanya_Idle_Stand.controller",
    )
    controller = any(p.is_file() for p in controller_paths)
    editor = (project_root / "Assets/Editor/Viu/ShanyaSetup.cs").is_file()
    return controller, editor


def _scene_status(project_root: Path) -> tuple[bool, bool]:
    scene = project_root / "Assets/Scenes/GameTest.unity"
    if not scene.is_file():
        return False, False
    text = scene.read_text(encoding="utf-8", errors="replace")
    return True, "ShanyaLocomotion" in text


def verify_unity_project(
    project_root: Path,
    editor_log: Optional[Path] = None,
) -> UnityVerifyResult:
    from .log_parser import default_editor_log

    log_path = editor_log or default_editor_log()
    setup_ok, setup_errs = _read_setup_log(project_root)
    ctrl, editor = _scan_project_files(project_root)
    scene_exists, locomotion = _scene_status(project_root)
    scan = scan_unity_project(project_root) if (project_root / "Assets").is_dir() else None

    editor_sum = parse_editor_log(log_path) if log_path.is_file() else None
    cs = extract_compiler_errors(log_path) if log_path.is_file() else []
    play = False
    if log_path.is_file():
        raw = log_path.read_text(encoding="utf-8", errors="replace")
        play = bool(_PLAY_ENTER.search(raw))

    return UnityVerifyResult(
        project_path=str(project_root.resolve()),
        setup_log_ok=setup_ok,
        setup_log_errors=setup_errs,
        editor_log=editor_sum,
        scan=scan,
        controller_found=ctrl,
        editor_script_found=editor,
        play_entered=play,
        cs_errors=cs,
        locomotion_in_scene=locomotion,
        scene_exists=scene_exists,
    )
