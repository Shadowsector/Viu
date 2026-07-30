"""Инструменты Вью для работы с Blender.

* blender_info — узнать всё о сцене/файле (через живой Blender или в фоне);
* blender_command — выполнить команду в запущенном Blender (мост);
* blender_screenshot — снять окно Blender (для vision-модели).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from ..integrations.blender import (
    COMMANDS,
    BlenderBridgeError,
    BlenderClient,
    dump_blend_info,
)
from .base import AgentContext, Tool, ToolResult


def _client(ctx: AgentContext) -> BlenderClient:
    return BlenderClient(host=ctx.config.blender_host, port=ctx.config.blender_port)


class BlenderInfoTool(Tool):
    name = "blender_info"
    description = (
        "Получить сведения о сцене Blender: объекты, кости, блендшейпы, материалы. "
        "Если Blender запущен с мостом — берёт из него; иначе читает .blend в фоне"
    )
    parameters = {"blend_file": "путь к .blend (нужен, если Blender не запущен)"}

    def run(self, args: Dict[str, Any], ctx: AgentContext) -> ToolResult:
        client = _client(ctx)
        if client.is_alive():
            try:
                data = client.scene_info()
                return ToolResult(True, "Живой Blender:\n" + json.dumps(data, ensure_ascii=False, indent=2))
            except BlenderBridgeError as exc:
                return ToolResult(False, str(exc))

        blend_file = args.get("blend_file", "")
        if not blend_file:
            return ToolResult(
                False,
                "Blender не запущен с мостом. Укажите blend_file для чтения в фоновом режиме.",
            )
        try:
            data = dump_blend_info(blend_file, blender_exe=ctx.config.blender_exe)
        except (FileNotFoundError, RuntimeError, ValueError) as exc:
            return ToolResult(False, str(exc))
        return ToolResult(True, "Файл (фоновый Blender):\n" + json.dumps(data, ensure_ascii=False, indent=2))


class BlenderCommandTool(Tool):
    name = "blender_command"
    description = "Выполнить команду в запущенном Blender через мост (аналог действия в интерфейсе)"
    parameters = {
        "command": f"одна из: {', '.join(COMMANDS)}",
        "params": "словарь параметров команды (опционально)",
    }

    def run(self, args: Dict[str, Any], ctx: AgentContext) -> ToolResult:
        command = args.get("command", "")
        if command not in COMMANDS:
            return ToolResult(False, f"Команда {command!r} не поддерживается. Доступны: {', '.join(COMMANDS)}")
        params = args.get("params") or {}
        if isinstance(params, str):
            try:
                params = json.loads(params)
            except json.JSONDecodeError:
                return ToolResult(False, "params должен быть корректным JSON-объектом")
        try:
            data = _client(ctx)._post(command, params)
        except BlenderBridgeError as exc:
            return ToolResult(False, str(exc))
        return ToolResult(True, json.dumps(data, ensure_ascii=False, indent=2))


class BlenderScanTool(Tool):
    name = "blender_scan"
    description = (
        "Просканировать папку с .blend-файлами и составить сводку по каждому "
        "(объекты, есть ли скелет/блендшейпы) — чтобы выбрать подходящие модели"
    )
    parameters = {"folder": "путь к папке с .blend"}

    def run(self, args: Dict[str, Any], ctx: AgentContext) -> ToolResult:
        folder = args.get("folder", "")
        if not folder:
            return ToolResult(False, "Не указан folder")
        p = Path(folder)
        if not p.is_dir():
            return ToolResult(False, f"Папка не найдена: {folder}")
        files = sorted(p.glob("*.blend"))
        if not files:
            return ToolResult(True, "В папке нет .blend-файлов.")

        lines = []
        for f in files:
            try:
                info = dump_blend_info(str(f), blender_exe=ctx.config.blender_exe)
            except (FileNotFoundError, RuntimeError, ValueError) as exc:
                lines.append(f"- {f.name}: ошибка чтения ({exc})")
                continue
            objects = info.get("objects", [])
            meshes = [o for o in objects if o.get("type") == "MESH"]
            has_arm = any(o.get("type") == "ARMATURE" for o in objects)
            shape_keys = sorted({sk for o in meshes for sk in o.get("shape_keys", [])})
            lines.append(
                f"- {f.name}: мешей={len(meshes)}, скелет={'да' if has_arm else 'нет'}, "
                f"блендшейпы={len(shape_keys)}"
            )
        return ToolResult(True, "Сводка по папке:\n" + "\n".join(lines))


class BlenderExportCascadeurTool(Tool):
    name = "blender_export_cascadeur"
    description = (
        "Экспорт одного .blend для Cascadeur: без WGT/widget-мешей, только deform bones, "
        "суффикс _cascadeur.fbx"
    )
    parameters = {
        "blend_file": "путь к .blend",
        "output_fbx": "куда сохранить (опционально)",
    }

    def run(self, args: Dict[str, Any], ctx: AgentContext) -> ToolResult:
        from ..integrations.blender.export_cascadeur import export_cascadeur_fbx

        blend = args.get("blend_file", "")
        if not blend:
            return ToolResult(False, "Не указан blend_file")
        out = args.get("output_fbx")
        try:
            path, meta = export_cascadeur_fbx(blend, out, blender_exe=ctx.config.blender_exe)
        except (FileNotFoundError, RuntimeError, OSError) as exc:
            return ToolResult(False, str(exc))
        return ToolResult(
            True,
            f"Cascadeur FBX: {path}\n"
            f"deform_bones={meta.get('deform_bones')}, "
            f"widgets_hidden={meta.get('hidden_widgets')}, "
            f"selected={meta.get('selected')}",
        )


class BlenderExportCascadeurBatchTool(Tool):
    name = "blender_export_cascadeur_batch"
    description = (
        "Пакетный экспорт всех .blend/.fbx из Lab Inbox и Cascadeur Inbox "
        "→ Library/Lab/Models/CascadeurReady/*_cascadeur.fbx"
    )
    parameters = {
        "force": "1 = пересобрать даже если FBX свежее",
        "topic": "cascadeur (manifest в lab artifacts)",
    }

    def run(self, args: Dict[str, Any], ctx: AgentContext) -> ToolResult:
        from ..integrations.blender.export_cascadeur import batch_export_cascadeur_models

        force = str(args.get("force", "0")).lower() in ("1", "true", "yes")
        topic = str(args.get("topic") or "cascadeur").strip().lower()
        ok, msg, manifest = batch_export_cascadeur_models(
            ctx.config, topic=topic, force=force,
        )
        return ToolResult(ok, msg + f"\n\nManifest: {manifest}")


class BlenderExportShanyaTool(Tool):
    name = "blender_export_shanya"
    description=(
        "Экспорт FBX из Shanya_Erisa.blend для Unity: скрывает WGT/Circle/Sphere, "
        "Mesh+Armature, без bake animation"
    )
    parameters = {
        "blend_file": "путь к .blend",
        "output_fbx": "куда сохранить .fbx (опционально, рядом с blend)",
    }

    def run(self, args: Dict[str, Any], ctx: AgentContext) -> ToolResult:
        from ..integrations.blender.export_shanya import export_shanya_fbx

        blend = args.get("blend_file", "")
        if not blend:
            return ToolResult(False, "Не указан blend_file")
        out = args.get("output_fbx")
        try:
            path = export_shanya_fbx(blend, out, blender_exe=ctx.config.blender_exe)
        except (FileNotFoundError, RuntimeError, OSError) as exc:
            return ToolResult(False, str(exc))
        return ToolResult(
            True,
            f"FBX готов: {path}\nСкопируй в Unity Assets/Characters/Shanya/",
        )


class BlenderMakeAnimTool(Tool):
    name = "blender_make_anim"
    description = (
        "Сделать клип в Blender: позы-hold (stand/sit/kneel/all_fours/lie) "
        "или motion (idle/wave/…). Опционально blend from→to. "
        "Полировка — Cascadeur."
    )
    parameters = {
        "blend_file": "путь к .blend с ригом",
        "preset": "stand|sit|kneel|all_fours|lie|idle|wave|nod|look_left|look_right|stretch",
        "from_preset": "стартовая поза для blend_to (опционально)",
        "blend_frames": "кадров перехода (по умолчанию 12)",
        "action_name": "имя Action (опционально)",
        "out_blend": "куда сохранить .blend (опционально)",
    }

    def run(self, args: Dict[str, Any], ctx: AgentContext) -> ToolResult:
        from ..integrations.blender.exe import resolve_blender_exe
        from ..integrations.blender.make_anim import ANIM_PRESETS, make_simple_anim

        blend = args.get("blend_file", "")
        if not blend:
            return ToolResult(False, "Не указан blend_file")
        preset = str(args.get("preset") or "idle").strip().lower()
        if preset not in ANIM_PRESETS:
            return ToolResult(False, f"preset: {', '.join(ANIM_PRESETS)}")
        from_preset = str(args.get("from_preset") or "").strip().lower()
        try:
            blend_frames = int(args.get("blend_frames") or 0)
        except (TypeError, ValueError):
            blend_frames = 0
        try:
            exe = resolve_blender_exe(ctx.config)
            path, meta = make_simple_anim(
                blend,
                preset=preset,
                from_preset=from_preset,
                blend_frames=blend_frames,
                action_name=str(args.get("action_name") or ""),
                out_blend=args.get("out_blend") or None,
                blender_exe=exe,
            )
        except (FileNotFoundError, RuntimeError, ValueError, OSError) as exc:
            return ToolResult(False, str(exc))
        return ToolResult(
            True,
            f"Клип готов: {path}\n"
            f"action={meta.get('action')}, mode={meta.get('mode')}, "
            f"frames={meta.get('frames')}, bones={meta.get('bones_used')}\n"
            "Дальше: blender_export_cascadeur_anim или blender_anim_to_cascadeur.",
        )


class BlenderPoseCharacterTool(Tool):
    name = "blender_pose_character"
    description = (
        "Поставить персонажа (Шаня…) в позу-hold/motion на канон-риге. "
        "Ищет .blend сама или по blend_file=."
    )
    parameters = {
        "character": "shanya|viu (по умолчанию shanya)",
        "pose": "stand|sit|kneel|all_fours|lie|idle|wave|…",
        "blend_file": "явный .blend (опционально)",
        "out_blend": "куда сохранить (опционально)",
    }

    def run(self, args: Dict[str, Any], ctx: AgentContext) -> ToolResult:
        from ..integrations.blender.exe import resolve_blender_exe
        from ..integrations.blender.pose_ops import format_pose_help, pose_character

        pose = str(args.get("pose") or "").strip()
        if not pose:
            return ToolResult(False, "Нужен pose=.\n" + format_pose_help())
        try:
            exe = resolve_blender_exe(ctx.config)
            path, meta = pose_character(
                ctx.config,
                str(args.get("character") or "shanya"),
                pose,
                blend_file=str(args.get("blend_file") or ""),
                out_blend=args.get("out_blend") or None,
                blender_exe=exe,
            )
        except (FileNotFoundError, RuntimeError, ValueError, OSError) as exc:
            return ToolResult(False, str(exc))
        return ToolResult(
            True,
            f"Поза «{pose}»: {path}\n"
            f"action={meta.get('action')}, frames={meta.get('frames')}\n"
            "Export: blender_export_cascadeur_anim.",
        )


class BlenderBlendToTool(Tool):
    name = "blender_blend_to"
    description = (
        "Переход между позами в Blender: from_pose → to_pose за N кадров "
        "(пример: stand→sit, frames=12)."
    )
    parameters = {
        "character": "shanya|viu",
        "to_pose": "целевая поза",
        "from_pose": "старт (по умолчанию stand)",
        "frames": "кадров (по умолчанию 12)",
        "blend_file": "явный .blend (опционально)",
        "out_blend": "куда сохранить (опционально)",
    }

    def run(self, args: Dict[str, Any], ctx: AgentContext) -> ToolResult:
        from ..integrations.blender.exe import resolve_blender_exe
        from ..integrations.blender.pose_ops import blend_to, format_pose_help

        to_pose = str(args.get("to_pose") or args.get("pose") or "").strip()
        if not to_pose:
            return ToolResult(False, "Нужен to_pose=.\n" + format_pose_help())
        try:
            frames = int(args.get("frames") or 12)
        except (TypeError, ValueError):
            frames = 12
        try:
            exe = resolve_blender_exe(ctx.config)
            path, meta = blend_to(
                ctx.config,
                str(args.get("character") or "shanya"),
                to_pose,
                from_pose=str(args.get("from_pose") or "stand"),
                frames=frames,
                blend_file=str(args.get("blend_file") or ""),
                out_blend=args.get("out_blend") or None,
                blender_exe=exe,
            )
        except (FileNotFoundError, RuntimeError, ValueError, OSError) as exc:
            return ToolResult(False, str(exc))
        return ToolResult(
            True,
            f"Переход → «{to_pose}»: {path}\n"
            f"from={meta.get('from_preset')}, frames={meta.get('frames')}, "
            f"mode={meta.get('mode')}\n"
            "Дальше polish в Cascadeur или Unity.",
        )


class BlenderExportCascadeurAnimTool(Tool):
    name = "blender_export_cascadeur_anim"
    description = (
        "Экспорт .blend с анимацией → FBX (bake_anim) для Cascadeur, без WGT, deform bones"
    )
    parameters = {
        "blend_file": "путь к .blend (уже с Action)",
        "output_fbx": "куда сохранить (опционально)",
    }

    def run(self, args: Dict[str, Any], ctx: AgentContext) -> ToolResult:
        from ..integrations.blender.exe import resolve_blender_exe
        from ..integrations.blender.export_cascadeur import export_cascadeur_anim_fbx

        blend = args.get("blend_file", "")
        if not blend:
            return ToolResult(False, "Не указан blend_file")
        try:
            exe = resolve_blender_exe(ctx.config)
            path, meta = export_cascadeur_anim_fbx(
                blend, args.get("output_fbx"), blender_exe=exe
            )
        except (FileNotFoundError, RuntimeError, OSError) as exc:
            return ToolResult(False, str(exc))
        return ToolResult(
            True,
            f"Anim FBX: {path}\n"
            f"deform_bones={meta.get('deform_bones')}, bake_anim={meta.get('bake_anim')}",
        )


class BlenderAnimToCascadeurTool(Tool):
    name = "blender_anim_to_cascadeur"
    description = (
        "Полный шаг: простой клип в Blender → FBX с анимацией → Cascadeur Inbox "
        "+ pending LabImport (mode=animation). Потом полируй в Cascadeur."
    )
    parameters = {
        "blend_file": "путь к .blend с ригом",
        "preset": "stand|sit|kneel|all_fours|lie|idle|wave|… (если skip_make=0)",
        "skip_make": "1 = не создавать клип, только экспорт уже готового .blend",
        "open_cascadeur": "1 = поднять Cascadeur (default 1)",
    }

    def run(self, args: Dict[str, Any], ctx: AgentContext) -> ToolResult:
        from ..integrations.blender.anim_to_cascadeur import run_blender_anim_to_cascadeur

        blend = args.get("blend_file", "")
        if not blend:
            return ToolResult(False, "Не указан blend_file")
        skip = str(args.get("skip_make", "0")).lower() in ("1", "true", "yes")
        open_csc = str(args.get("open_cascadeur", "1")).lower() not in (
            "0",
            "false",
            "no",
        )
        ok, msg, _meta = run_blender_anim_to_cascadeur(
            ctx.config,
            blend,
            preset=str(args.get("preset") or "idle"),
            skip_make=skip,
            open_cascadeur=open_csc,
        )
        return ToolResult(ok, msg)


class BlenderScreenshotTool(Tool):
    name = "blender_screenshot"
    description = "Сделать снимок окна Blender и вернуть путь к файлу (для анализа vision-моделью)"
    parameters = {"path": "куда сохранить .png (опционально)"}

    def run(self, args: Dict[str, Any], ctx: AgentContext) -> ToolResult:
        path = args.get("path")
        try:
            data = _client(ctx).screenshot(path)
        except BlenderBridgeError as exc:
            return ToolResult(False, str(exc))
        return ToolResult(True, f"Снимок сохранён: {data.get('path') if isinstance(data, dict) else data}")
