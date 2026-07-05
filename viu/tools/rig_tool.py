"""Инструменты Вью для работы с единым скелетом (ригом).

* rig_check — сравнить скелет модели со стандартом и предложить план
  переименования (кости берутся из живого Blender, из .blend-файла или
  передаются напрямую списком);
* rig_apply — применить переименование костей в запущенном Blender;
* rig_standard — показать сам стандартный скелет.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from ..integrations.blender import BlenderBridgeError, BlenderClient, dump_blend_info
from ..integrations.rig import analyze_skeleton, standard_summary
from .base import AgentContext, Tool, ToolResult


def _client(ctx: AgentContext) -> BlenderClient:
    return BlenderClient(host=ctx.config.blender_host, port=ctx.config.blender_port)


def _armature_bones(objects: List[dict], armature: Optional[str]) -> Optional[List[str]]:
    """Достаёт список костей из описания сцены (живой Blender или .blend)."""
    for o in objects:
        if o.get("type") == "ARMATURE" and (armature is None or o.get("name") == armature):
            return list(o.get("bones", []))
    return None


class RigStandardTool(Tool):
    name = "rig_standard"
    description = "Показать единый стандартный скелет (список костей и обязательность)"
    parameters = {}

    def run(self, args: Dict[str, Any], ctx: AgentContext) -> ToolResult:
        return ToolResult(True, standard_summary())


class RigCheckTool(Tool):
    name = "rig_check"
    description = (
        "Сравнить скелет модели со стандартным ригом и предложить план переименования. "
        "Кости берутся из bones (список), из blend_file или из живого Blender"
    )
    parameters = {
        "bones": "список имён костей (опционально)",
        "blend_file": "путь к .blend (опционально)",
        "armature": "имя арматуры, если их несколько (опционально)",
    }

    def run(self, args: Dict[str, Any], ctx: AgentContext) -> ToolResult:
        bones = args.get("bones")
        armature = args.get("armature")

        if not bones:
            objects = None
            client = _client(ctx)
            if client.is_alive():
                try:
                    scene = client.scene_info()
                    objects = scene.get("objects", []) if isinstance(scene, dict) else None
                except BlenderBridgeError as exc:
                    return ToolResult(False, str(exc))
            elif args.get("blend_file"):
                try:
                    scene = dump_blend_info(args["blend_file"], blender_exe=ctx.config.blender_exe)
                    objects = scene.get("objects", [])
                except (FileNotFoundError, RuntimeError, ValueError) as exc:
                    return ToolResult(False, str(exc))
            else:
                return ToolResult(
                    False,
                    "Нет данных о скелете. Передайте bones, или blend_file, или запустите Blender с мостом.",
                )

            bones = _armature_bones(objects or [], armature)
            if bones is None:
                return ToolResult(False, "В сцене не найдено арматуры (скелета).")

        if isinstance(bones, str):
            bones = [b.strip() for b in bones.split(",") if b.strip()]

        report = analyze_skeleton(bones)
        text = report.render()
        # Отдаём план переименования отдельно в JSON, чтобы его можно было передать в rig_apply.
        if report.rename_plan:
            text += "\n\nrename_plan (JSON):\n" + json.dumps(report.rename_plan, ensure_ascii=False)
        return ToolResult(report.ok, text)


class RigApplyTool(Tool):
    name = "rig_apply"
    description = "Применить переименование костей в запущенном Blender (по плану из rig_check)"
    parameters = {"armature": "имя арматуры", "mapping": "JSON {старое_имя: новое_имя}"}

    def run(self, args: Dict[str, Any], ctx: AgentContext) -> ToolResult:
        armature = args.get("armature", "")
        mapping = args.get("mapping")
        if not armature or not mapping:
            return ToolResult(False, "Нужны armature и mapping")
        if isinstance(mapping, str):
            try:
                mapping = json.loads(mapping)
            except json.JSONDecodeError:
                return ToolResult(False, "mapping должен быть корректным JSON-объектом")
        try:
            data = _client(ctx).rename_bones(armature, mapping)
        except BlenderBridgeError as exc:
            return ToolResult(False, str(exc))
        return ToolResult(True, json.dumps(data, ensure_ascii=False, indent=2))
