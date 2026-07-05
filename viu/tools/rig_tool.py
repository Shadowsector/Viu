"""Инструменты Вью для работы с единым скелетом (ригом).

* rig_check — сравнить скелет модели со стандартом и предложить план
  переименования (кости берутся из живого Blender, из .blend-файла или
  передаются напрямую списком);
* rig_apply — применить переименование костей в запущенном Blender;
* rig_apply_auto — проверить и применить переименование без ручного JSON;
* rig_standard — показать сам стандартный скелет.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Tuple

from ..integrations.blender import BlenderBridgeError, BlenderClient, dump_blend_info
from ..integrations.rig import (
    analyze_skeleton,
    is_complex_rig,
    map_to_humanoid,
    standard_summary,
)
from .base import AgentContext, Tool, ToolResult


def _client(ctx: AgentContext) -> BlenderClient:
    return BlenderClient(host=ctx.config.blender_host, port=ctx.config.blender_port)


def _score_armature(obj: dict) -> int:
    """Оценка «главности» арматуры: больше костей и типичное имя — выше."""
    bones = obj.get("bones", [])
    n = len(bones)
    if n == 0:
        return -9999
    name = (obj.get("name") or "").lower()
    score = n
    if name in ("rig_", "_armature", "rigg_blake"):
        score += 500
    if "genesis" in name and "female" in name:
        score += 500
    if "model" in name and n > 50 and ".00" not in name:
        score += 200
    if "swimwear" in name or "weapon" in name:
        score -= 800
    if "tongue" in name and n < 30:
        score -= 500
    if n < 40 and bones and all(
        any(x in b.lower() for x in ("wpn", "weapon", "ctr_", "skn_wpn", "prop"))
        for b in bones
    ):
        score -= 2000
    return score


def _pick_armature(
    objects: List[dict], armature: Optional[str] = None
) -> Tuple[Optional[str], Optional[List[str]]]:
    """Выбирает главную арматуру сцены и возвращает (имя, кости)."""
    arms = [o for o in objects if o.get("type") == "ARMATURE"]
    if not arms:
        return None, None
    if armature:
        for o in arms:
            if o.get("name") == armature:
                return o.get("name"), list(o.get("bones", []))
        return None, None
    best = max(arms, key=_score_armature)
    return best.get("name"), list(best.get("bones", []))


def _resolve_bones(args: Dict[str, Any], ctx: AgentContext):
    """Возвращает (armature_name, bones, error_text)."""
    bones = args.get("bones")
    if bones:
        if isinstance(bones, str):
            bones = [b.strip() for b in bones.split(",") if b.strip()]
        return args.get("armature"), bones, None

    armature = args.get("armature")
    objects = None
    client = _client(ctx)
    if client.is_alive():
        try:
            scene = client.scene_info()
            objects = scene.get("objects", []) if isinstance(scene, dict) else None
        except BlenderBridgeError as exc:
            return None, None, str(exc)
    elif args.get("blend_file"):
        try:
            scene = dump_blend_info(args["blend_file"], blender_exe=ctx.config.blender_exe)
            objects = scene.get("objects", [])
        except (FileNotFoundError, RuntimeError, ValueError) as exc:
            return None, None, str(exc)
    else:
        return None, None, "Нет данных о скелете. Передайте bones, blend_file или запустите Blender с мостом."

    arm_name, bones = _pick_armature(objects or [], armature)
    if bones is None:
        return None, None, "В сцене не найдено арматуры (скелета)."
    return arm_name, bones, None


def _format_armature_header(armature: Optional[str], bone_count: int) -> str:
    if armature:
        return f"Арматура: {armature} ({bone_count} костей)\n\n"
    return ""


class RigStandardTool(Tool):
    name = "rig_standard"
    description = "Показать единый стандартный скелет (список костей и обязательность)"
    parameters = {}

    def run(self, args: Dict[str, Any], ctx: AgentContext) -> ToolResult:
        return ToolResult(True, standard_summary())


class RigCheckTool(Tool):
    name = "rig_check"
    description = (
        "Проанализировать скелет модели. Для сложных ригов (Rigify, метариг) "
        "строит карту Unity Humanoid без переименования; для простых — план переименования"
    )
    parameters = {
        "bones": "список имён костей (опционально)",
        "blend_file": "путь к .blend (опционально)",
        "armature": "имя арматуры, если их несколько (опционально)",
    }

    def run(self, args: Dict[str, Any], ctx: AgentContext) -> ToolResult:
        armature, bones, error = _resolve_bones(args, ctx)
        if error:
            return ToolResult(False, error)

        header = _format_armature_header(armature, len(bones))

        if is_complex_rig(bones):
            hm = map_to_humanoid(bones)
            text = header + hm.render()
            text += (
                "\n\nЭто карта для Unity (слот Humanoid → кость). Переименование не нужно — "
                "в Unity эта карта подтверждается в настройке Avatar."
            )
            text += "\n\nmapping (JSON):\n" + json.dumps(hm.mapping, ensure_ascii=False)
            return ToolResult(not hm.missing_required, text)

        report = analyze_skeleton(bones)
        text = header + report.render()
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
        armature, bones, error = _resolve_bones(args, ctx)
        if error:
            return ToolResult(False, error)
        hm = map_to_humanoid(bones)
        text = _format_armature_header(armature, len(bones)) + hm.render()
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


class RigApplyAutoTool(Tool):
    name = "rig_apply_auto"
    description = (
        "Автоматически проверить главный скелет и применить переименование в Blender "
        "(без ручной передачи JSON mapping — удобно для простых ригов)"
    )
    parameters = {
        "armature": "имя арматуры (опционально — выберется главный скелет сцены)",
    }

    def run(self, args: Dict[str, Any], ctx: AgentContext) -> ToolResult:
        armature, bones, error = _resolve_bones(args, ctx)
        if error:
            return ToolResult(False, error)
        if not armature:
            return ToolResult(False, "Не удалось определить арматуру.")

        if is_complex_rig(bones):
            hm = map_to_humanoid(bones)
            text = (
                f"Арматура {armature!r} — сложный риг ({hm.rig_type}). "
                "Переименование не применяем (сломает риг). Используй rig_map и Unity Avatar.\n\n"
                + hm.render()
            )
            text += "\n\nmapping (JSON):\n" + json.dumps(hm.mapping, ensure_ascii=False)
            return ToolResult(False, text)

        report = analyze_skeleton(bones)
        if not report.rename_plan:
            return ToolResult(True, f"Арматура {armature!r}: переименование не требуется.")
        try:
            data = _client(ctx).rename_bones(armature, report.rename_plan)
        except BlenderBridgeError as exc:
            return ToolResult(False, str(exc))
        summary = (
            f"Арматура {armature!r}: переименовано {len(report.rename_plan)} костей.\n"
            + json.dumps(data, ensure_ascii=False, indent=2)
        )
        return ToolResult(report.ok, summary)
