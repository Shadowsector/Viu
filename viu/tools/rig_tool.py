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
from ..integrations.rig import (
    analyze_skeleton,
    detect_rig_type,
    map_to_humanoid,
    standard_summary,
)
from .base import AgentContext, Tool, ToolResult


def _client(ctx: AgentContext) -> BlenderClient:
    return BlenderClient(host=ctx.config.blender_host, port=ctx.config.blender_port)


def _armature_bones(objects: List[dict], armature: Optional[str]) -> Optional[List[str]]:
    """Достаёт список костей из описания сцены (живой Blender или .blend)."""
    for o in objects:
        if o.get("type") == "ARMATURE" and (armature is None or o.get("name") == armature):
            return list(o.get("bones", []))
    return None


def _resolve_bones(args: Dict[str, Any], ctx: AgentContext):
    """Возвращает (bones, error_text). Кости: из args, из живого Blender или .blend."""
    bones = args.get("bones")
    if bones:
        if isinstance(bones, str):
            bones = [b.strip() for b in bones.split(",") if b.strip()]
        return bones, None

    armature = args.get("armature")
    objects = None
    client = _client(ctx)
    if client.is_alive():
        try:
            scene = client.scene_info()
            objects = scene.get("objects", []) if isinstance(scene, dict) else None
        except BlenderBridgeError as exc:
            return None, str(exc)
    elif args.get("blend_file"):
        try:
            scene = dump_blend_info(args["blend_file"], blender_exe=ctx.config.blender_exe)
            objects = scene.get("objects", [])
        except (FileNotFoundError, RuntimeError, ValueError) as exc:
            return None, str(exc)
    else:
        return None, "Нет данных о скелете. Передайте bones, blend_file или запустите Blender с мостом."

    bones = _armature_bones(objects or [], armature)
    if bones is None:
        return None, "В сцене не найдено арматуры (скелета)."
    return bones, None


class RigStandardTool(Tool):
    name = "rig_standard"
    description = "Показать единый стандартный скелет (список костей и обязательность)"
    parameters = {}

    def run(self, args: Dict[str, Any], ctx: AgentContext) -> ToolResult:
        return ToolResult(True, standard_summary())


class RigCheckTool(Tool):
    name = "rig_check"
    description = (
        "Проанализировать скелет модели. Для сложных ригов (Rigify) строит карту "
        "Unity Humanoid без переименования; для простых — план переименования"
    )
    parameters = {
        "bones": "список имён костей (опционально)",
        "blend_file": "путь к .blend (опционально)",
        "armature": "имя арматуры, если их несколько (опционально)",
    }

    def run(self, args: Dict[str, Any], ctx: AgentContext) -> ToolResult:
        bones, error = _resolve_bones(args, ctx)
        if error:
            return ToolResult(False, error)

        rig_type = detect_rig_type(bones)
        has_deform = any(b.startswith("DEF-") for b in bones)

        if rig_type == "rigify" or has_deform:
            # Сложный риг: сопоставляем, НЕ переименовываем.
            hm = map_to_humanoid(bones)
            text = hm.render()
            text += (
                "\n\nЭто карта для Unity (слот Humanoid → кость). Переименование не нужно — "
                "в Unity эта карта подтверждается в настройке Avatar."
            )
            return ToolResult(hm.renaming_needed is False and not hm.missing_required, text)

        # Простой риг: предлагаем привести имена к стандарту.
        report = analyze_skeleton(bones)
        text = report.render()
        if report.rename_plan:
            text += "\n\nrename_plan (JSON):\n" + json.dumps(report.rename_plan, ensure_ascii=False)
        return ToolResult(report.ok, text)


class RigMapTool(Tool):
    name = "rig_map"
    description = (
        "Построить карту соответствия костей модели слотам Unity Humanoid "
        "(без переименования; подходит для Rigify и сложных ригов)"
    )
    parameters = {
        "bones": "список имён костей (опционально)",
        "blend_file": "путь к .blend (опционально)",
        "armature": "имя арматуры (опционально)",
    }

    def run(self, args: Dict[str, Any], ctx: AgentContext) -> ToolResult:
        bones, error = _resolve_bones(args, ctx)
        if error:
            return ToolResult(False, error)
        hm = map_to_humanoid(bones)
        text = hm.render()
        text += "\n\nmapping (JSON):\n" + json.dumps(hm.mapping, ensure_ascii=False)
        return ToolResult(not hm.missing_required, text)


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
