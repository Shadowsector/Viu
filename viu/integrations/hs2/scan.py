"""Скан abdata и экспорт AnimationClip → JSON (UnityPy, опционально)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ...config import Config
from .catalog_hints import suggest_catalog_slug
from .paths import abdata_animation_roots, hs2_scan_cache_path, resolve_hs2_root

_BUNDLE_SUFFIXES = (".unity3d", ".assets", ".assetbundle", ".ab")


def _try_unitypy():
    try:
        from UnityPy import Environment  # type: ignore
        from UnityPy.enums import ClassIDType  # type: ignore

        return Environment, ClassIDType
    except ImportError:
        return None, None


@dataclass
class ClipIndexEntry:
    name: str
    bundle: str
    suggested_slug: Optional[str] = None
    length: float = 0.0
    sample_rate: float = 30.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "bundle": self.bundle,
            "suggested_slug": self.suggested_slug,
            "length": self.length,
            "sample_rate": self.sample_rate,
        }


@dataclass
class ScanResult:
    ok: bool
    hs2_root: Optional[str] = None
    clips: List[ClipIndexEntry] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    unitypy: bool = False

    def format_brief(self, limit: int = 40) -> str:
        lines = ["HS2 animation scan"]
        if self.hs2_root:
            lines.append(f"Корень: {self.hs2_root}")
        lines.append(f"UnityPy: {'да' if self.unitypy else 'нет (pip install UnityPy)'}")
        lines.append(f"Клипов: {len(self.clips)}")
        for err in self.errors[:5]:
            lines.append(f"  ⚠ {err}")
        shown = self.clips[:limit]
        for c in shown:
            slug = f" → `{c.suggested_slug}`" if c.suggested_slug else ""
            lines.append(f"  • {c.name}{slug}  ({Path(c.bundle).name})")
        if len(self.clips) > limit:
            lines.append(f"  … и ещё {len(self.clips) - limit}")
        return "\n".join(lines)


def _iter_bundle_files(roots: List[Path], max_files: int) -> List[Path]:
    found: List[Path] = []
    for root in roots:
        for p in root.rglob("*"):
            if not p.is_file():
                continue
            if p.suffix.lower() in _BUNDLE_SUFFIXES or p.name.lower().endswith(".unity3d"):
                found.append(p)
                if len(found) >= max_files:
                    return found
    return found


def scan_abdata(
    config: Config,
    *,
    max_bundles: int = 200,
    max_clips: int = 2000,
    use_cache: bool = True,
) -> ScanResult:
    """Список AnimationClip в abdata (без экспорта FBX)."""
    result = ScanResult(ok=False)
    hs2 = resolve_hs2_root(config)
    if not hs2:
        result.errors.append(
            "HS2 не найден. Задай VIU_HS2_ROOT=путь к игре (папка с abdata)."
        )
        return result

    result.hs2_root = str(hs2)
    cache = hs2_scan_cache_path(config)
    if use_cache and cache.is_file():
        try:
            data = json.loads(cache.read_text(encoding="utf-8"))
            if str(data.get("hs2_root") or "") == str(hs2):
                for row in data.get("clips") or []:
                    if isinstance(row, dict) and row.get("name"):
                        result.clips.append(
                            ClipIndexEntry(
                                name=str(row["name"]),
                                bundle=str(row.get("bundle") or ""),
                                suggested_slug=row.get("suggested_slug"),
                                length=float(row.get("length") or 0),
                                sample_rate=float(row.get("sample_rate") or 30),
                            )
                        )
                result.unitypy = bool(data.get("unitypy"))
                result.ok = True
                return result
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            pass

    Environment, ClassIDType = _try_unitypy()
    if Environment is None or ClassIDType is None:
        result.errors.append("Установь UnityPy: pip install UnityPy")
        return result

    result.unitypy = True
    roots = abdata_animation_roots(hs2)
    bundles = _iter_bundle_files(roots, max_bundles)
    if not bundles:
        result.errors.append("В abdata не найдено bundle-файлов (.unity3d).")
        return result

    seen_names: set[str] = set()
    for bundle_path in bundles:
        try:
            env = Environment(str(bundle_path))
        except Exception as exc:  # noqa: BLE001 — разные форматы bundle
            result.errors.append(f"{bundle_path.name}: {exc}")
            continue
        for obj in env.objects:
            if obj.type != ClassIDType.AnimationClip:
                continue
            try:
                clip = obj.read()
            except Exception:
                continue
            name = str(getattr(clip, "m_Name", "") or "").strip()
            if not name or name in seen_names:
                continue
            seen_names.add(name)
            length = _clip_length(clip)
            sr = float(getattr(clip, "m_SampleRate", 0) or 30)
            entry = ClipIndexEntry(
                name=name,
                bundle=str(bundle_path),
                suggested_slug=suggest_catalog_slug(name),
                length=length,
                sample_rate=sr,
            )
            result.clips.append(entry)
            if len(result.clips) >= max_clips:
                break
        if len(result.clips) >= max_clips:
            break

    result.ok = True
    try:
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(
            json.dumps(
                {
                    "hs2_root": str(hs2),
                    "unitypy": True,
                    "clips": [c.to_dict() for c in result.clips],
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
    except OSError as exc:
        result.errors.append(f"cache: {exc}")

    return result


def _clip_length(clip: Any) -> float:
    best = 0.0
    for attr in (
        "m_RotationCurves",
        "m_PositionCurves",
        "m_FloatCurves",
        "m_ScaleCurves",
    ):
        curves = getattr(clip, attr, None) or []
        for curve_row in curves:
            ac = getattr(curve_row, "curve", None)
            if ac is None:
                continue
            keys = getattr(ac, "m_Curve", None) or getattr(ac, "keys", None)
            if keys:
                for k in keys:
                    t = getattr(k, "time", None) or getattr(k, "m_Time", 0)
                    try:
                        best = max(best, float(t))
                    except (TypeError, ValueError):
                        pass
    return best


def export_clip_json(
    config: Config,
    clip_name: str,
    dest_dir: Optional[Path] = None,
) -> Tuple[bool, str]:
    """Экспорт одного клипа по имени (после scan) в JSON кривых."""
    from .paths import hs2_clip_json_dir

    scan = scan_abdata(config, use_cache=True)
    if not scan.ok:
        return False, scan.format_brief()

    match = next((c for c in scan.clips if c.name == clip_name), None)
    if not match:
        return False, f"Клип «{clip_name}» не в скане. Сначала hs2_anim_scan."

    Environment, ClassIDType = _try_unitypy()
    if Environment is None:
        return False, "pip install UnityPy"

    bundle = Path(match.bundle)
    if not bundle.is_file():
        return False, f"Bundle не найден: {bundle}"

    try:
        env = Environment(str(bundle))
    except Exception as exc:
        return False, str(exc)

    clip_obj = None
    for obj in env.objects:
        if obj.type != ClassIDType.AnimationClip:
            continue
        try:
            clip = obj.read()
        except Exception:
            continue
        if str(getattr(clip, "m_Name", "")) == clip_name:
            clip_obj = clip
            break

    if clip_obj is None:
        return False, f"В {bundle.name} нет клипа {clip_name}"

    payload = _clip_to_viu_json(clip_obj, clip_name)
    out_dir = dest_dir or hs2_clip_json_dir(config)
    out_dir.mkdir(parents=True, exist_ok=True)
    safe = re_safe_name(clip_name)
    out_path = out_dir / f"{safe}.json"
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return True, f"JSON: {out_path}"


def re_safe_name(name: str) -> str:
    import re

    s = re.sub(r"[^a-zA-Z0-9._-]+", "_", name.strip())
    return s[:120] or "clip"


def _clip_to_viu_json(clip: Any, name: str) -> Dict[str, Any]:
    """Сериализация кривых для Blender-ретаргета."""
    bones: Dict[str, Dict[str, Any]] = {}

    def add_key(path: str, prop: str, time: float, value: float) -> None:
        bone_path = path or "Root"
        slot = bones.setdefault(bone_path, {"properties": {}})
        props = slot["properties"]
        curve = props.setdefault(prop, {"times": [], "values": []})
        curve["times"].append(round(time, 6))
        curve["values"].append(value)

    for row in getattr(clip, "m_FloatCurves", None) or []:
        path = str(getattr(row, "path", "") or "")
        attr = str(getattr(row, "attribute", "") or getattr(row, "m_Attribute", "") or "float")
        curve = getattr(row, "curve", None)
        if curve is None:
            continue
        keys = getattr(curve, "m_Curve", None) or getattr(curve, "keys", None) or []
        for k in keys:
            t = float(getattr(k, "time", None) or getattr(k, "m_Time", 0))
            v = float(getattr(k, "value", None) or getattr(k, "m_Value", 0))
            add_key(path, attr, t, v)

    for row in getattr(clip, "m_RotationCurves", None) or []:
        path = str(getattr(row, "path", "") or "")
        curve = getattr(row, "curve", None)
        if curve is None:
            continue
        # QuaternionCurve — четыре компоненты в одной кривой? обычно отдельные float curves
        keys = getattr(curve, "m_Curve", None) or []
        for k in keys:
            t = float(getattr(k, "time", None) or getattr(k, "m_Time", 0))
            v = float(getattr(k, "value", None) or getattr(k, "m_Value", 0))
            add_key(path, "m_LocalRotation.w", t, v)

    sample_rate = float(getattr(clip, "m_SampleRate", 0) or 30)
    return {
        "format": "viu_hs2_clip_v1",
        "name": name,
        "sample_rate": sample_rate,
        "length": _clip_length(clip),
        "bones": bones,
    }
