"""Скан папки Animations/ — классификация FBX-клипов для Шани."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .paths import resolve_in_unity_project
from .project_scan import scan_fbx_meta

ANIMATIONS_REL = "Assets/Characters/Shanya/Animations"
MANIFEST_NAME = "viu_clips.json"

# Имя файла (lower) → состояние Animator
_NAME_RULES: Tuple[Tuple[re.Pattern, str], ...] = (
    (re.compile(r"idle", re.I), "Idle"),
    (re.compile(r"walk", re.I), "Walk"),
    (re.compile(r"run", re.I), "Run"),
    (re.compile(r"sit", re.I), "Sit"),
    (re.compile(r"sleep", re.I), "Sleep"),
    (re.compile(r"stretch", re.I), "Stretch"),
    (re.compile(r"jump", re.I), "Jump"),
)

_MODEL_SKIP = re.compile(r"shanya|erisa", re.I)
_ANIM_HINT = re.compile(r"idle|walk|run|sit|sleep|stretch|jump|mixamo|x bot|@", re.I)


@dataclass
class AnimationClipInfo:
    fbx_path: str
    file_name: str
    suggested_state: Optional[str]
    is_humanoid: bool = False
    copy_avatar: bool = False
    issues: List[str] = field(default_factory=list)
    needs_question: bool = False

    def render(self) -> str:
        state = self.suggested_state or "?"
        flags = []
        if self.is_humanoid:
            flags.append("Humanoid")
        if self.needs_question:
            flags.append("спросить")
        line = f"  {self.file_name} → {state}"
        if flags:
            line += f" ({', '.join(flags)})"
        if self.issues:
            line += "\n    ⚠ " + "; ".join(self.issues)
        return line


@dataclass
class AnimationScanResult:
    animations_dir: str
    clips: List[AnimationClipInfo] = field(default_factory=list)
    questions: List[str] = field(default_factory=list)

    def render(self) -> str:
        lines = [f"Папка анимаций: {self.animations_dir}"]
        if not self.clips:
            lines.append("FBX не найдены. Положи клипы в Assets/Characters/Shanya/Animations/")
            return "\n".join(lines)
        lines.append(f"\nКлипы ({len(self.clips)}):")
        for c in self.clips:
            lines.append(c.render())
        if self.questions:
            lines.append("\nНужен ответ (ask_user):")
            for q in self.questions:
                lines.append(f"  • {q}")
        return "\n".join(lines)

    @property
    def has_new_actionable(self) -> bool:
        return any(c.suggested_state and not c.needs_question for c in self.clips)


def _load_overrides(anim_dir: Path) -> Dict[str, str]:
    manifest = anim_dir / MANIFEST_NAME
    if not manifest.is_file():
        return {}
    try:
        data = json.loads(manifest.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    raw = data.get("overrides") or data.get("clips")
    if raw is None:
        return {}
    if isinstance(raw, dict):
        return {str(k): str(v) for k, v in raw.items()}
    if isinstance(raw, list):
        result: Dict[str, str] = {}
        for item in raw:
            if isinstance(item, dict) and item.get("file") and item.get("state"):
                result[str(item["file"])] = str(item["state"])
        return result
    return {}


def classify_file_name(file_name: str, overrides: Optional[Dict[str, str]] = None) -> Tuple[Optional[str], List[str], bool]:
    """Возвращает (state_name, issues, needs_question)."""
    overrides = overrides or {}
    if file_name in overrides:
        return overrides[file_name], [], False
    stem = Path(file_name).stem
    low = stem.lower()
    issues: List[str] = []
    if _MODEL_SKIP.search(low) and not _ANIM_HINT.search(low):
        return None, ["похоже на модель, не анимацию"], False
    for pattern, state in _NAME_RULES:
        if pattern.search(low):
            return state, issues, False
    if re.search(r"take\s*\d+", low, re.I) or low.startswith("mixamo"):
        issues.append("непонятное имя — укажи в viu_clips.json или переименуй (Walk, Idle…)")
        return None, issues, True
    issues.append("не удалось угадать состояние по имени файла")
    return None, issues, True


def scan_animations_folder(project_root: Path) -> AnimationScanResult:
    anim_dir = resolve_in_unity_project(project_root, ANIMATIONS_REL)
    result = AnimationScanResult(animations_dir=str(anim_dir))
    if not anim_dir.is_dir():
        result.questions.append(
            f"Создай папку {ANIMATIONS_REL} и положи туда FBX с анимациями (Walk, Idle…)"
        )
        return result

    overrides = _load_overrides(anim_dir)
    seen_states: Dict[str, str] = {}

    for fbx in sorted(anim_dir.glob("*.fbx")):
        meta = scan_fbx_meta(fbx)
        state, issues, needs_q = classify_file_name(fbx.name, overrides)
        info = AnimationClipInfo(
            fbx_path=str(fbx),
            file_name=fbx.name,
            suggested_state=state,
            is_humanoid=meta.is_humanoid,
            copy_avatar=meta.copy_avatar,
            issues=list(issues),
            needs_question=needs_q,
        )
        if not meta.is_humanoid:
            info.issues.append("не Humanoid — в Unity: Rig → Humanoid → Apply")
        if meta.copy_avatar:
            info.issues.append("Copy Avatar — нужен Create From This Model")
        if state:
            if state in seen_states:
                info.needs_question = True
                info.issues.append(
                    f"дубликат состояния {state} (уже есть {seen_states[state]})"
                )
                result.questions.append(
                    f"Два клипа на {state}: {seen_states[state]} и {fbx.name} — какой оставить?"
                )
            else:
                seen_states[state] = fbx.name
        elif needs_q:
            result.questions.append(
                f"Файл {fbx.name}: как назвать состояние? (Idle/Walk/…) — добавь в viu_clips.json"
            )
        result.clips.append(info)

    return result


def folder_fingerprint(project_root: Path) -> str:
    """Хеш содержимого папки для watcher (имена + mtime)."""
    anim_dir = resolve_in_unity_project(project_root, ANIMATIONS_REL)
    if not anim_dir.is_dir():
        return ""
    parts: List[str] = []
    for f in sorted(anim_dir.glob("*")):
        if f.suffix.lower() in (".fbx", ".json"):
            try:
                parts.append(f"{f.name}:{int(f.stat().st_mtime)}")
            except OSError:
                parts.append(f.name)
    return "|".join(parts)
