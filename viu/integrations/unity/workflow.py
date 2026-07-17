"""Чеклист пайплайна Шани — чтобы Вью знала, где мы в процессе."""

from __future__ import annotations

from typing import List, Optional

SHANYA_PIPELINE: List[dict] = [
    {
        "id": 1,
        "phase": "Blender",
        "title": "Shanya_Erisa готова",
        "checks": [
            "Файл Shanya_Erisa.blend сохранён",
            "Outfit: одета / купальник / душ — через переключатели рига",
            "Body Shapes на дефолте (без клиппинга одежды)",
            "rig_map: _Armature, advanced, 21/21 Humanoid",
        ],
    },
    {
        "id": 2,
        "phase": "Blender → FBX",
        "title": "Экспорт FBX",
        "checks": [
            "Скрыты лишние outfit-меши и WGT-* (виджеты рига)",
            "Export FBX: Mesh + Armature, без Bake Animation",
            "Путь: Assets/Characters/Shanya/",
        ],
    },
    {
        "id": 3,
        "phase": "Unity",
        "title": "Импорт модели",
        "checks": [
            "Проект Universal 3D (URP)",
            "FBX модели: Rig → Humanoid → Create From This Model → Configure → Apply",
            "Avatar: Hips=pelvis/Torso, ORG_* = руки/ноги",
        ],
    },
    {
        "id": 4,
        "phase": "Unity",
        "title": "Mixamo анимации",
        "checks": [
            "Mixamo FBX: Humanoid → Create From This Model (НЕ Copy Avatar)",
            "Import Animation включён",
            "Animator Controller + клип Idle/Walk",
            "На персонаже: Controller + Avatar модели Shanya_ErisaAvatar",
        ],
    },
    {
        "id": 5,
        "phase": "Unity",
        "title": "Сцена и Play",
        "checks": [
            "В Hierarchy один outfit (лишние меши выключены)",
            "Console: нет Rig Error и CS ошибок",
            "Play → Game: Idle/Walk играет",
        ],
    },
    {
        "id": 6,
        "phase": "Дальше",
        "title": "Cascadeur + игра",
        "checks": [
            "FBX в Cascadeur для правок анимаций",
            "Outfit switch в Unity (скрипт или prefab variants)",
        ],
    },
]


def workflow_status_text(current_step: Optional[int] = None) -> str:
    lines = ["Пайплайн Шани (Анабарра) — текущий маршрут:\n"]
    for step in SHANYA_PIPELINE:
        mark = "→" if current_step and step["id"] == current_step else " "
        lines.append(f"{mark} [{step['id']}] {step['phase']}: {step['title']}")
        for c in step["checks"]:
            lines.append(f"      • {c}")
        lines.append("")
    lines.append(
        "Важно: mixamorig на модели НЕ нужен. Humanoid mapping + Mixamo клипы Without Skin."
    )
    return "\n".join(lines)
