"""Кадр и длина клипа под Cascadeur MoCap.

Длина не «с потолка»: Wan ждёт число кадров вида 4n+1, FPS = 24 (как таймлайн
Cascadeur). Длительность ≈ frames/fps — столько, чтобы действие успело
прочитаться MoCap (idle с микродвижениями длиннее, чем короткий жест).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal, Tuple

Orientation = Literal["vertical", "horizontal"]

# Кратно 16 (Wan latent). Вертикаль — стоя/сидя; горизонталь — лёжа.
STAND_SIZE: Tuple[int, int] = (576, 1024)  # W×H
LIE_SIZE: Tuple[int, int] = (1024, 576)
MOCAP_FPS = 24.0

# Wan T2V: length = 4n+1
_LENGTH_IDLE = 81  # ~3.4 с — дыхание, сдвиг веса, поворот головы
_LENGTH_ACTION = 49  # ~2.0 с — один жест / шаг
_LENGTH_TRANSITION = 65  # ~2.7 с — sit_down / stand_up / lie_down
# Короткий preview перед полными дублями (~1.4 с @24fps)
PREVIEW_LENGTH = 33


_LIE_RE = re.compile(
    r"\b("
    r"lie|lying|lie[_\s-]?down|sleep|sleeping|prone|supine|reclining|"
    r"on\s+the\s+back|on\s+back|на\s+спине|леж|спать|сон"
    r")\b",
    re.I,
)
_IDLE_RE = re.compile(
    r"\b("
    r"idle|stand|standing|breathing|wait|waiting|"
    r"стой|дыхан|ожидан"
    r")\b",
    re.I,
)
_TRANSITION_RE = re.compile(
    r"\b("
    r"sit[_\s-]?down|stand[_\s-]?up|get[_\s-]?up|lie[_\s-]?down|"
    r"sit|stand_up|lie_down|transition|"
    r"сесть|встать|лечь"
    r")\b",
    re.I,
)


@dataclass(frozen=True)
class MocapFrameSpec:
    orientation: Orientation
    width: int
    height: int
    length: int  # frames (4n+1)
    fps: float
    reason: str

    @property
    def duration_sec(self) -> float:
        return self.length / self.fps if self.fps else 0.0

    def summary_ru(self) -> str:
        orient = "вертикаль" if self.orientation == "vertical" else "горизонталь"
        return (
            f"{orient} {self.width}×{self.height}, "
            f"{self.length} кадров @ {self.fps:.0f} fps ≈ {self.duration_sec:.1f} с "
            f"({self.reason})"
        )


def detect_orientation(action: str) -> Orientation:
    """Стоячие/сидячие → vertical; лежачие → horizontal."""
    if _LIE_RE.search(action or ""):
        return "horizontal"
    return "vertical"


def choose_length(action: str) -> Tuple[int, str]:
    text = (action or "").strip()
    if _LIE_RE.search(text) and not _TRANSITION_RE.search(text):
        # sleep_idle / lying idle — тоже длинный loop
        if _IDLE_RE.search(text) or "idle" in text.lower():
            return _LENGTH_IDLE, "лежачий idle — микродвижения ~3.4 с"
        return _LENGTH_IDLE, "лёжа — достаточно кадров для MoCap"
    if _TRANSITION_RE.search(text) and not _IDLE_RE.search(text):
        return _LENGTH_TRANSITION, "переход позы ~2.7 с"
    if _IDLE_RE.search(text) or not text:
        return _LENGTH_IDLE, "idle — дыхание/жесты/поворот головы ~3.4 с"
    return _LENGTH_ACTION, "короткое действие ~2.0 с"


def frame_spec_for_action(action: str, *, preview: bool = False) -> MocapFrameSpec:
    orient = detect_orientation(action)
    w, h = STAND_SIZE if orient == "vertical" else LIE_SIZE
    length, reason = choose_length(action)
    if preview:
        length = PREVIEW_LENGTH
        reason = f"preview MoCap (~{length / MOCAP_FPS:.1f} с); финал: {reason}"
    return MocapFrameSpec(
        orientation=orient,
        width=w,
        height=h,
        length=length,
        fps=MOCAP_FPS,
        reason=reason,
    )


def enrich_idle_action(action: str) -> str:
    """Если действие — голый idle stand, добавить микродвижения в промпт."""
    raw = (action or "").strip()
    low = raw.lower()
    if not raw:
        return (
            "idle stand, subtle breathing, soft weight shift side to side, "
            "small natural head turn, slight finger and shoulder micro-movements, "
            "relaxed athletic stance, loopable idle"
        )
    # уже подробно
    if any(k in low for k in ("weight shift", "head turn", "micro", "breathing", "gesture")):
        return raw
    if _IDLE_RE.search(raw) and "sit" not in low and not _LIE_RE.search(raw):
        return (
            f"{raw}, subtle breathing, soft weight shift, "
            "small head turn, slight arm and finger micro-movements, natural idle loop"
        )
    if _LIE_RE.search(raw) and _IDLE_RE.search(raw):
        return (
            f"{raw}, subtle breathing, small restless shifts, "
            "gentle head movement, natural sleep-idle loop"
        )
    return raw
