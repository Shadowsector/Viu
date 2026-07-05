"""Разбор Unity Editor.log — ошибки и предупреждения импорта."""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional


@dataclass
class UnityLogSummary:
    path: str
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    wgt_tangent_count: int = 0
    rig_errors: List[str] = field(default_factory=list)
    compiler_errors: List[str] = field(default_factory=list)
    playmode_blockers: List[str] = field(default_factory=list)

    def render(self) -> str:
        lines = [f"Unity Editor.log: {self.path}"]
        if self.playmode_blockers:
            lines.append("\n⛔ Блокирует Play Mode:")
            for e in self.playmode_blockers[:10]:
                lines.append(f"  • {e}")
        if self.compiler_errors:
            lines.append(f"\nОшибки компиляции C# ({len(self.compiler_errors)}):")
            for e in self.compiler_errors[:8]:
                lines.append(f"  • {e}")
        if self.rig_errors:
            lines.append(f"\nRig Error ({len(self.rig_errors)}):")
            for e in self.rig_errors[:5]:
                lines.append(f"  • {e}")
        if self.wgt_tangent_count:
            lines.append(
                f"\nПредупреждения WGT/rig widgets (без normals): {self.wgt_tangent_count} шт."
                "\n  → не блокируют Play; убери WGT-* из FBX в Blender перед экспортом."
            )
        other_warn = [
            w for w in self.warnings
            if "Can't calculate tangents" not in w and "WGT" not in w
        ]
        if other_warn:
            lines.append(f"\nПрочие предупреждения ({len(other_warn)}):")
            for w in other_warn[-8:]:
                lines.append(f"  • {w[:200]}")
        if self.errors:
            other_err = [e for e in self.errors if e not in self.rig_errors and e not in self.compiler_errors]
            if other_err:
                lines.append(f"\nПрочие ошибки ({len(other_err)}):")
                for e in other_err[-8:]:
                    lines.append(f"  • {e[:200]}")
        if not any(
            [self.playmode_blockers, self.compiler_errors, self.rig_errors, self.errors, other_warn]
        ):
            lines.append("\nКритичных ошибок в хвосте лога не найдено.")
        return "\n".join(lines)


_WGT_TANGENT = re.compile(r"Can't calculate tangents.*'(WGT[^']*)'", re.I)
_RIG_ERROR = re.compile(r"Rig Error:", re.I)
_CS_ERROR = re.compile(r"error CS\d+", re.I)
_PLAYMODE = re.compile(r"compiler errors have to be fixed|All compiler errors", re.I)


def default_editor_log() -> Path:
    """Типичный путь Editor.log на Windows."""
    local = Path.home() / "AppData/Local/Unity/Editor/Editor.log"
    if local.exists():
        return local
    return local


def parse_editor_log(path: Path, tail_lines: int = 400) -> UnityLogSummary:
    if not path.exists():
        return UnityLogSummary(path=str(path), errors=[f"Файл не найден: {path}"])
    raw = path.read_text(encoding="utf-8", errors="replace").splitlines()
    chunk = raw[-tail_lines:] if tail_lines else raw
    summary = UnityLogSummary(path=str(path))

    wgt_names: Counter = Counter()
    for line in chunk:
        low = line.strip()
        if not low:
            continue
        if _PLAYMODE.search(low):
            summary.playmode_blockers.append(low)
        if _RIG_ERROR.search(low):
            summary.rig_errors.append(low)
            summary.errors.append(low)
        elif low.startswith("error ") or _CS_ERROR.search(low):
            summary.compiler_errors.append(low)
            summary.errors.append(low)
        elif "error:" in low.lower() and "warning" not in low.lower():
            summary.errors.append(low)
        elif low.startswith("Warning") or "warning:" in low.lower():
            summary.warnings.append(low)
        m = _WGT_TANGENT.search(low)
        if m:
            wgt_names[m.group(1)] += 1

    summary.wgt_tangent_count = sum(wgt_names.values())
    return summary
