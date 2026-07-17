"""Каталог совместных анимаций (multi-actor interactions)."""

from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

# --- статусы сцены (порядок пайплайна) ---
STATUS_WISHED = "wished"
STATUS_BLOCKING = "blocking_done"
STATUS_MASTER_DRAFT = "master_draft"
STATUS_MASTER_APPROVED = "master_approved"
STATUS_ISOLATED = "isolated_done"
STATUS_ANIMATED = "animated"
STATUS_ASSEMBLED = "assembled"
STATUS_VERIFIED = "verified"
STATUS_LINKED = "linked"
STATUS_REJECTED = "rejected"

ACTOR_STATUS_PENDING = "pending"
ACTOR_STATUS_REF = "ref_done"
ACTOR_STATUS_ANIMATED = "animated"
ACTOR_STATUS_EXPORTED = "exported"

# Роли в сцене (не путать с creature slug)
INTERACTION_ROLES: Dict[str, str] = {
    "initiator": "Инициатор действия",
    "target": "Цель / объект взаимодействия",
    "bystander": "Наблюдатель на фоне",
    "rider": "Верхом",
    "mount": "Носитель",
}

RIG_KINDS = ("humanoid", "quadruped", "flying", "other")
MOTION_PATHS = ("mocap", "control_pose", "hybrid_keys")

DEFAULT_FPS = 24
DEFAULT_DURATION_FRAMES = 72


def interaction_id(slug: str) -> str:
    return hashlib.sha256(slug.lower().encode("utf-8")).hexdigest()[:16]


def _slugify(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", text.lower().strip())
    return s.strip("_") or "interaction"


@dataclass
class ChoreographyLock:
    """Общие параметры съёмки — все Comfy/MoCap прогоны ссылаются на это."""

    fps: int = DEFAULT_FPS
    duration_frames: int = DEFAULT_DURATION_FRAMES
    camera_type: str = "ortho_studio"
    camera_height_m: float = 1.8
    camera_distance_m: float = 4.0
    studio: str = "white"
    beats: List[int] = field(default_factory=lambda: [0, 24, 48, 71])

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @staticmethod
    def from_dict(d: Optional[Dict[str, Any]]) -> "ChoreographyLock":
        if not d:
            return ChoreographyLock()
        beats = d.get("beats")
        return ChoreographyLock(
            fps=int(d.get("fps") or DEFAULT_FPS),
            duration_frames=int(d.get("duration_frames") or DEFAULT_DURATION_FRAMES),
            camera_type=str(d.get("camera_type") or "ortho_studio"),
            camera_height_m=float(d.get("camera_height_m") or 1.8),
            camera_distance_m=float(d.get("camera_distance_m") or 4.0),
            studio=str(d.get("studio") or "white"),
            beats=[int(x) for x in (beats or [0, 24, 48, 71])],
        )


@dataclass
class SyncMarker:
    frame: int
    event: str
    note: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "SyncMarker":
        return SyncMarker(
            frame=int(d.get("frame") or 0),
            event=str(d.get("event") or ""),
            note=str(d.get("note") or ""),
        )


@dataclass
class ActorMotionTrack:
    """Один участник сцены — ref, изоляция, анимация."""

    role: str
    creature_slug: str
    rig_kind: str = "humanoid"
    motion_path: str = "mocap"
    ref_video: str = ""
    isolated_ref: str = ""
    mocap_fbx: str = ""
    status: str = ACTOR_STATUS_PENDING

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "ActorMotionTrack":
        rig = str(d.get("rig_kind") or "humanoid")
        if rig not in RIG_KINDS:
            rig = "other"
        path = str(d.get("motion_path") or "mocap")
        if path not in MOTION_PATHS:
            path = "mocap" if rig == "humanoid" else "control_pose"
        return ActorMotionTrack(
            role=str(d.get("role") or "initiator"),
            creature_slug=str(d.get("creature_slug") or ""),
            rig_kind=rig,
            motion_path=path,
            ref_video=str(d.get("ref_video") or ""),
            isolated_ref=str(d.get("isolated_ref") or ""),
            mocap_fbx=str(d.get("mocap_fbx") or ""),
            status=str(d.get("status") or ACTOR_STATUS_PENDING),
        )


@dataclass
class InteractionWish:
    """Одна совместная сцена — аналог AnimationWish для группы."""

    slug: str
    title_ru: str
    when_used: str
    looks_like: str
    actors: List[ActorMotionTrack] = field(default_factory=list)
    choreography: ChoreographyLock = field(default_factory=ChoreographyLock)
    sync_markers: List[SyncMarker] = field(default_factory=list)
    wave: int = 1
    status: str = STATUS_WISHED
    enters_from: List[str] = field(default_factory=list)
    exits_to: List[str] = field(default_factory=list)
    master_ref_draft: str = ""
    master_ref: str = ""
    blocking_blend: str = ""
    assembly_blend: str = ""
    assembly_target: str = "blender"
    verify_report: str = ""
    notes: str = ""
    id: str = ""

    def __post_init__(self) -> None:
        if not self.id:
            self.id = interaction_id(self.slug)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "slug": self.slug,
            "title_ru": self.title_ru,
            "when_used": self.when_used,
            "looks_like": self.looks_like,
            "wave": self.wave,
            "status": self.status,
            "enters_from": list(self.enters_from),
            "exits_to": list(self.exits_to),
            "choreography": self.choreography.to_dict(),
            "sync_markers": [m.to_dict() for m in self.sync_markers],
            "actors": [a.to_dict() for a in self.actors],
            "master_ref_draft": self.master_ref_draft,
            "master_ref": self.master_ref,
            "blocking_blend": self.blocking_blend,
            "assembly_blend": self.assembly_blend,
            "assembly_target": self.assembly_target,
            "verify_report": self.verify_report,
            "notes": self.notes,
        }

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "InteractionWish":
        actors = [ActorMotionTrack.from_dict(x) for x in (d.get("actors") or []) if isinstance(x, dict)]
        markers = [SyncMarker.from_dict(x) for x in (d.get("sync_markers") or []) if isinstance(x, dict)]
        return InteractionWish(
            id=str(d.get("id") or interaction_id(str(d.get("slug", "")))),
            slug=str(d.get("slug", "")),
            title_ru=str(d.get("title_ru", "")),
            when_used=str(d.get("when_used", "")),
            looks_like=str(d.get("looks_like", "")),
            wave=int(d.get("wave") or 1),
            status=str(d.get("status") or STATUS_WISHED),
            enters_from=list(d.get("enters_from") or []),
            exits_to=list(d.get("exits_to") or []),
            choreography=ChoreographyLock.from_dict(d.get("choreography")),
            sync_markers=markers,
            actors=actors,
            master_ref_draft=str(d.get("master_ref_draft") or ""),
            master_ref=str(d.get("master_ref") or ""),
            blocking_blend=str(d.get("blocking_blend") or ""),
            assembly_blend=str(d.get("assembly_blend") or ""),
            assembly_target=str(d.get("assembly_target") or "blender"),
            verify_report=str(d.get("verify_report") or ""),
            notes=str(d.get("notes") or ""),
        )

    def render_block(self) -> str:
        lines = [
            f"### {self.title_ru} (`{self.slug}`)",
            f"**Статус:** {self.status} (wave {self.wave})",
            f"**Когда:** {self.when_used}",
            f"**Как выглядит:** {self.looks_like}",
        ]
        if self.enters_from or self.exits_to:
            lines.append(
                f"**Граф:** {self.enters_from or '—'} → `{self.slug}` → {self.exits_to or '—'}"
            )
        ch = self.choreography
        lines.append(
            f"**Хореография:** {ch.duration_frames}f @ {ch.fps}fps, "
            f"камера {ch.camera_type}, studio={ch.studio}"
        )
        if self.sync_markers:
            mk = ", ".join(f"@{m.frame}:{m.event}" for m in self.sync_markers)
            lines.append(f"**Маркеры:** {mk}")
        if self.actors:
            lines.append("**Актёры:**")
            for a in self.actors:
                lines.append(
                    f"  - {a.role} `{a.creature_slug}` ({a.rig_kind}, {a.motion_path}) — {a.status}"
                )
        if self.master_ref:
            lines.append(f"**Master:** {self.master_ref}")
        elif self.master_ref_draft:
            lines.append(f"**Master draft:** {self.master_ref_draft}")
        if self.blocking_blend:
            lines.append(f"**Blocking:** {self.blocking_blend}")
        if self.assembly_blend:
            lines.append(f"**Assembly:** {self.assembly_blend}")
        if self.verify_report:
            lines.append(f"**Verify:** {self.verify_report[:200]}")
        return "\n".join(lines)


def _default_pilot() -> InteractionWish:
    return InteractionWish(
        slug="shanya_wolf_approach",
        title_ru="Шаня и волк: подход и касание",
        when_used="Два персонажа рядом; волк осторожно подходит и касается плеча.",
        looks_like="Studio, статичная камера, подход, краткий контакт, отход.",
        wave=1,
        enters_from=["idle_near_pair"],
        exits_to=["idle_separate"],
        choreography=ChoreographyLock(
            fps=24,
            duration_frames=72,
            beats=[0, 24, 48, 71],
        ),
        sync_markers=[
            SyncMarker(0, "start", "оба в стойке"),
            SyncMarker(24, "contact_shoulder", "контакт у плеча"),
            SyncMarker(48, "release", "волк отступает"),
            SyncMarker(71, "end", "стабильная дистанция"),
        ],
        actors=[
            ActorMotionTrack(
                role="initiator",
                creature_slug="wolf_alpha",
                rig_kind="quadruped",
                motion_path="control_pose",
            ),
            ActorMotionTrack(
                role="target",
                creature_slug="shanya",
                rig_kind="humanoid",
                motion_path="mocap",
            ),
        ],
        notes="MVP-пилот — docs/INTERACTION_PIPELINE.md",
    )


DEFAULT_INTERACTIONS: List[InteractionWish] = [_default_pilot()]
