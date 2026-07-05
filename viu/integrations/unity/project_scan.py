"""Сканирование Unity-проекта: FBX, .meta, настройки Humanoid."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional


# animationType в .meta: 0=None, 1=Legacy, 2=Generic, 3=Humanoid (зависит от версии Unity)
# В современных Unity часто: 2=Humanoid в YAML — проверяем и copyAvatar
_HUMANOID_ANIM = re.compile(r"^\s*animationType:\s*([23])\s*$", re.M)
_COPY_AVATAR = re.compile(r"^\s*copyAvatar:\s*1\s*$", re.M)
_AVATAR_SOURCE = re.compile(r"^\s*lastHumanDescriptionAvatarSource:", re.M)
_WGT_MESH = re.compile(r"WGT[-_.]", re.I)


@dataclass
class FbxImportInfo:
    fbx_path: str
    meta_path: str
    is_humanoid: bool = False
    copy_avatar: bool = False
    has_avatar_source: bool = False
    issues: List[str] = field(default_factory=list)

    def render(self) -> str:
        flags = []
        if self.is_humanoid:
            flags.append("Humanoid")
        if self.copy_avatar:
            flags.append("CopyAvatar=ДА")
        line = f"  {Path(self.fbx_path).name}: {', '.join(flags) or 'не Humanoid'}"
        if self.issues:
            line += "\n    ⚠ " + "; ".join(self.issues)
        return line


@dataclass
class UnityProjectScan:
    project_path: str
    unity_version: str = ""
    fbx_files: List[FbxImportInfo] = field(default_factory=list)
    wgt_mesh_names: List[str] = field(default_factory=list)
    has_controller: bool = False
    has_viu_editor: bool = False
    issues: List[str] = field(default_factory=list)

    def render(self) -> str:
        lines = [f"Unity-проект: {self.project_path}"]
        if self.unity_version:
            lines.append(f"Unity: {self.unity_version}")
        if self.has_viu_editor:
            lines.append("Viu Editor: ✓ ShanyaSetup.cs")
        if self.has_controller:
            lines.append("Animator: ✓ Shanya_Idle_Stand.controller")
        if not self.fbx_files:
            lines.append("FBX в Assets/ не найдены.")
        else:
            lines.append(f"\nFBX ({len(self.fbx_files)}):")
            for f in self.fbx_files:
                lines.append(f.render())
        if self.wgt_mesh_names:
            lines.append(
                f"\nWGT/rig widget меши в проекте: {len(self.wgt_mesh_names)} "
                "(лишние для игры, лучше не экспортировать из Blender)"
            )
            for n in self.wgt_mesh_names[:12]:
                lines.append(f"  • {n}")
            if len(self.wgt_mesh_names) > 12:
                lines.append(f"  … и ещё {len(self.wgt_mesh_names) - 12}")
        if self.issues:
            lines.append("\nРекомендации:")
            for i in self.issues:
                lines.append(f"  • {i}")
        return "\n".join(lines)


def _read_meta(meta: Path) -> str:
    try:
        return meta.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def scan_fbx_meta(fbx: Path) -> FbxImportInfo:
    meta = fbx.with_suffix(fbx.suffix + ".meta")
    info = FbxImportInfo(fbx_path=str(fbx), meta_path=str(meta))
    if not meta.exists():
        info.issues.append("нет .meta — Unity ещё не импортировал файл")
        return info
    text = _read_meta(meta)
    info.is_humanoid = bool(_HUMANOID_ANIM.search(text)) or "humanDescription:" in text
    info.copy_avatar = bool(_COPY_AVATAR.search(text))
    info.has_avatar_source = bool(_AVATAR_SOURCE.search(text))
    if info.copy_avatar:
        info.issues.append(
            "Copy Avatar включён — для Mixamo-анимации нужен Create From This Model"
        )
    return info


def scan_unity_project(project_root: Path) -> UnityProjectScan:
    assets = project_root / "Assets"
    scan = UnityProjectScan(project_path=str(project_root.resolve()))
    ver = project_root / "ProjectSettings/ProjectVersion.txt"
    if ver.is_file():
        for line in ver.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.startswith("m_EditorVersion:"):
                scan.unity_version = line.split(":", 1)[1].strip()
                break
    scan.has_controller = (
        project_root / "Assets/Characters/Shanya/Shanya_Idle_Stand.controller"
    ).is_file()
    scan.has_viu_editor = (project_root / "Assets/Editor/Viu/ShanyaSetup.cs").is_file()
    if not assets.is_dir():
        scan.issues.append(f"Нет папки Assets: {assets}")
        return scan

    for fbx in sorted(assets.rglob("*.fbx")):
        scan.fbx_files.append(scan_fbx_meta(fbx))
        # имена из meta guid не парсим — WGT ищем по имени файла
        if _WGT_MESH.search(fbx.name):
            scan.wgt_mesh_names.append(fbx.name)

    # WGT часто внутри модели — подсказка общая
    model_fbx = [f for f in scan.fbx_files if "shanya" in f.fbx_path.lower() or "erisa" in f.fbx_path.lower()]
    if model_fbx and not scan.wgt_mesh_names:
        scan.issues.append(
            "Если в Console сотни WGT-tangent warnings — в Blender скрой/удали "
            "меши WGT-* и Circle/Sphere перед экспортом FBX"
        )

    copies = [f for f in scan.fbx_files if f.copy_avatar]
    if copies:
        scan.issues.append(
            f"Исправь Rig на FBX с Copy Avatar ({len(copies)} файл(ов)) → Create From This Model → Apply"
        )

    humanoids = [f for f in scan.fbx_files if f.is_humanoid]
    if len(humanoids) < 2 and len(scan.fbx_files) >= 2:
        scan.issues.append("Убедись, что и модель, и Mixamo-анимация — Humanoid")

    if not scan.has_viu_editor:
        scan.issues.append("unity_deploy_setup — установить Editor-скрипты Viu")
    if scan.fbx_files and not scan.has_controller:
        scan.issues.append("Viu → Setup Shanya (Idle) или unity_run_setup")

    return scan
