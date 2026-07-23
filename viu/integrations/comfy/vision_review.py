"""MoCap-клипы: кадр из mp4 → Ollama VL (llava) → вердикт до Telegram."""

from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Tuple

from ...config import Config
from ..vision_eye import ask_vision, pick_vision_model
from .clip_review import extract_last_frame
from .paths import comfy_refs_dir

_CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0

_BAD_VERDICTS = frozenset(
    {
        "BLACK_FRAME",
        "NO_PERSON",
        "CORRUPT",
        "ARTIFACTS",
        "FACE_MISSING",
        "WRONG_POSE",
        "EMPTY",
        "BROKEN",
    }
)

_REVIEW_PROMPT = """Это кадр из сгенерированного AI MoCap-видео (персонаж для 3D-анимации).
Действие в клипе: {action}

Ответь кратко по-русски, СТРОГО в формате (без markdown):
ISSUES: <через запятую конкретные проблемы или «нет»>
VERDICT: OK | BLACK_FRAME | NO_PERSON | WRONG_POSE | ARTIFACTS | FACE_MISSING | CORRUPT

BLACK_FRAME — чёрный/пустой кадр. NO_PERSON — нет цельной фигуры. CORRUPT — глитч, лишние конечности."""


@dataclass
class ClipVisionReview:
    path: str
    angle: str
    verdict: str
    issues: str
    vision_ok: bool
    vision_text: str
    frame_path: str = ""

    @property
    def bad(self) -> bool:
        return self.verdict in _BAD_VERDICTS


def vision_review_enabled() -> bool:
    raw = (os.environ.get("VIU_COMFY_VISION") or "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


def _parse_verdict(text: str) -> Tuple[str, str]:
    issues = ""
    verdict = "UNKNOWN"
    for line in (text or "").splitlines():
        s = line.strip()
        if not s:
            continue
        low = s.lower()
        if low.startswith("issues:"):
            issues = s.split(":", 1)[1].strip()
        elif low.startswith("verdict:"):
            verdict = s.split(":", 1)[1].strip().upper().split()[0]
    upper = (text or "").upper()
    if verdict == "UNKNOWN":
        for tag in ("BLACK_FRAME", "NO_PERSON", "CORRUPT", "ARTIFACTS", "FACE_MISSING", "WRONG_POSE", "OK"):
            if tag in upper:
                verdict = tag
                break
    low = (text or "").lower()
    if verdict == "UNKNOWN":
        if any(x in low for x in ("чёрн", "black frame", "пустой кадр")):
            verdict = "BLACK_FRAME"
        elif any(x in low for x in ("нет человек", "нет фигур", "no person", "no character")):
            verdict = "NO_PERSON"
        elif any(x in low for x in ("глитч", "артефакт", "лишн", "искаж")):
            verdict = "CORRUPT"
    return verdict, issues


def extract_middle_frame(video: Path, dest: Path) -> Tuple[bool, str]:
    """Средний кадр mp4 → PNG (ffmpeg / cv2 / fallback last)."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    if not video.is_file():
        return False, f"нет файла: {video}"

    try:
        import cv2  # type: ignore

        cap = cv2.VideoCapture(str(video))
        if cap.isOpened():
            total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
            idx = max(0, total // 2) if total > 1 else 0
            cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
            ok, frame = cap.read()
            if not ok or frame is None:
                cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                ok, frame = cap.read()
            cap.release()
            if ok and frame is not None and cv2.imwrite(str(dest), frame) and dest.is_file():
                return True, str(dest)
    except Exception:
        pass

    for bin_name in ("ffmpeg", "ffmpeg.exe"):
        try:
            proc = subprocess.run(  # noqa: S603
                [
                    bin_name,
                    "-y",
                    "-ss",
                    "1",
                    "-i",
                    str(video),
                    "-frames:v",
                    "1",
                    str(dest),
                ],
                capture_output=True,
                text=True,
                timeout=120,
                creationflags=_CREATE_NO_WINDOW,
            )
            if proc.returncode == 0 and dest.is_file() and dest.stat().st_size > 0:
                return True, str(dest)
        except (OSError, subprocess.TimeoutExpired, FileNotFoundError):
            continue

    return extract_last_frame(video, dest)


def _move_to_rejected(config: Config, paths: List[str]) -> None:
    import shutil

    from .clip_review import comfy_rejected_dir

    rej_dir = comfy_rejected_dir(config)
    for p in paths:
        src = Path(p)
        if not src.is_file():
            continue
        dest = rej_dir / src.name
        try:
            if dest.is_file():
                dest.unlink()
            shutil.move(str(src), str(dest))
        except OSError:
            pass


def review_mocap_clip(
    config: Config,
    video: Path,
    *,
    action: str = "",
    angle: str = "",
) -> ClipVisionReview:
    """Один mp4 → llava → вердикт."""
    path = Path(video)
    if not pick_vision_model(config.base_url):
        return ClipVisionReview(
            path=str(path),
            angle=angle,
            verdict="UNKNOWN",
            issues="",
            vision_ok=False,
            vision_text="Нет llava/qwen2-vl в Ollama (ollama pull llava).",
        )

    shots = comfy_refs_dir(config) / "vision_review"
    shots.mkdir(parents=True, exist_ok=True)
    frame = shots / f"{path.stem}_mid.png"
    ok_f, fmsg = extract_middle_frame(path, frame)
    if not ok_f:
        return ClipVisionReview(
            path=str(path),
            angle=angle,
            verdict="CORRUPT",
            issues=fmsg,
            vision_ok=False,
            vision_text=f"кадр не извлечь: {fmsg}",
        )

    prompt = _REVIEW_PROMPT.format(action=(action or "mocap")[:200])
    v_ok, v_text = ask_vision(frame, prompt=prompt, config=config)
    verdict, issues = _parse_verdict(v_text if v_ok else "")
    if not v_ok:
        verdict = "UNKNOWN"
    return ClipVisionReview(
        path=str(path),
        angle=angle,
        verdict=verdict,
        issues=issues,
        vision_ok=v_ok,
        vision_text=v_text if v_ok else v_text,
        frame_path=str(frame),
    )


def review_triple_results(
    config: Config,
    results: Dict[str, Any],
    *,
    action: str = "",
    auto_reject: bool = True,
) -> Tuple[Dict[str, Any], str]:
    """Проверить дубли после генерации; плохие — убрать из candidates."""
    if not vision_review_enabled():
        return results, ""

    angles = results.get("angles") or {}
    if not angles:
        return results, ""

    lines: List[str] = ["--- vision (llava) ---"]
    rejected_paths: List[str] = []
    good_files: List[str] = []

    for angle_id, info in angles.items():
        if not isinstance(info, dict):
            continue
        files = list(info.get("files") or [])
        if not files:
            continue
        path = Path(str(files[0]))
        act = str(info.get("action_variant") or action or "")
        rev = review_mocap_clip(config, path, action=act, angle=str(angle_id))
        mark = "✗" if rev.bad else "✓"
        lines.append(
            f"{mark} {angle_id}: {rev.verdict}"
            + (f" ({rev.issues})" if rev.issues else "")
            + f" — {path.name}"
        )
        if rev.vision_ok and rev.vision_text:
            snippet = rev.vision_text.splitlines()
            for ln in snippet[-4:]:
                if ln.strip():
                    lines.append(f"    {ln.strip()[:160]}")
        if rev.bad and auto_reject:
            rejected_paths.append(str(path))
            info["ok"] = False
            info["vision_verdict"] = rev.verdict
            info["vision_rejected"] = True
            info["files"] = []
            info["msg"] = (info.get("msg") or "") + f" [vision: {rev.verdict}]"
        else:
            good_files.append(str(path))
            info["vision_verdict"] = rev.verdict

    results["files"] = good_files
    results["vision_rejected"] = rejected_paths

    if rejected_paths and auto_reject:
        _move_to_rejected(config, rejected_paths)

    if len(lines) <= 1:
        return results, ""
    return results, "\n".join(lines)


def format_vision_summary(reviews: List[ClipVisionReview]) -> str:
    if not reviews:
        return ""
    lines = ["Vision:"]
    for r in reviews:
        mark = "✗" if r.bad else "✓"
        lines.append(f"  {mark} {r.angle or '?'}: {r.verdict} — {Path(r.path).name}")
    return "\n".join(lines)


def review_paths(
    config: Config,
    paths: List[str],
    *,
    action: str = "",
) -> Tuple[bool, str, List[ClipVisionReview]]:
    reviews: List[ClipVisionReview] = []
    for raw in paths:
        p = Path(raw.strip())
        if not p.is_file():
            continue
        reviews.append(review_mocap_clip(config, p, action=action))
    if not reviews:
        return False, "Нет mp4 для проверки.", reviews
    bad = [r for r in reviews if r.bad]
    lines = [format_vision_summary(reviews)]
    for r in reviews:
        if r.vision_text:
            lines.append(f"--- {Path(r.path).name} ---")
            lines.append(r.vision_text[:1200])
    ok = len(bad) == 0
    if bad:
        lines.insert(0, f"Плохих: {len(bad)}/{len(reviews)}")
    return ok, "\n".join(lines), reviews
