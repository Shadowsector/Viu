"""Единый стандартный скелет (риг) для персонажей Анабарры.

Определяет один набор названий костей, совместимый с системой Unity
«Humanoid», и умеет сопоставлять скелет любой модели с этим стандартом,
подсказывая план переименования.
"""

from .analyze import RigReport, analyze_skeleton
from .humanoid_map import HumanoidMap, detect_rig_type, map_to_humanoid
from .standard import (
    ALIAS_MAP,
    BONES,
    CANON_ORDER,
    REQUIRED,
    normalize,
    standard_summary,
)

__all__ = [
    "analyze_skeleton",
    "RigReport",
    "map_to_humanoid",
    "HumanoidMap",
    "detect_rig_type",
    "BONES",
    "CANON_ORDER",
    "REQUIRED",
    "ALIAS_MAP",
    "normalize",
    "standard_summary",
]
