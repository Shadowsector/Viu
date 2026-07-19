"""Наборы одежды / видимости мешей — JSON рядом с prepared."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional


def empty_outfit_doc(slug: str, name: str = "") -> dict:
    return {
        "slug": slug,
        "name": name or slug,
        "sets": [],
    }


def load_outfit_sets(path: Path) -> dict:
    path = Path(path)
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def save_outfit_sets(path: Path, data: dict) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def upsert_outfit_set(
    data: dict,
    *,
    set_id: str,
    label: str,
    snapshot: dict,
    confirmed: bool = False,
    notes: str = "",
) -> dict:
    rows = {s.get("id"): s for s in data.get("sets") or [] if isinstance(s, dict)}
    row = dict(rows.get(set_id, {}))
    row.update(
        {
            "id": set_id,
            "label": label or set_id,
            "confirmed": bool(confirmed),
            "show_meshes": list(snapshot.get("show_meshes") or []),
            "hide_meshes": list(snapshot.get("hide_meshes") or []),
            "hide_genital_mesh": not bool(snapshot.get("genital_mesh_visible")),
            "genital_mesh_visible": bool(snapshot.get("genital_mesh_visible")),
            "clothing_visible": bool(snapshot.get("clothing_visible")),
            "notes": notes or "",
        }
    )
    rows[set_id] = row
    data["sets"] = sorted(rows.values(), key=lambda s: str(s.get("id") or ""))
    return data


def list_confirmed_sets(data: dict) -> List[dict]:
    return [s for s in data.get("sets") or [] if isinstance(s, dict) and s.get("confirmed")]
