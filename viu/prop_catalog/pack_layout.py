"""Сборка паков: blend + textures не должны разъезжаться."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import List

TEXTURE_FOLDER_NAMES = frozenset(
    {"textures", "texture", "maps", "tex", "materials", "material"}
)


def is_texture_folder(path: Path) -> bool:
    return path.is_dir() and path.name.lower() in TEXTURE_FOLDER_NAMES


def repair_split_pack(blend: Path, library_root: Path) -> List[str]:
    """Если textures уехали в References/images — вернуть рядом с .blend."""
    blend = blend.expanduser().resolve()
    library_root = library_root.expanduser().resolve()
    lines: List[str] = []

    for name in TEXTURE_FOLDER_NAMES:
        if (blend.parent / name).is_dir() or (blend.parent / name.capitalize()).is_dir():
            return lines

    ref_root = library_root / "References" / "images"
    if not ref_root.is_dir():
        return lines

    for src in sorted(ref_root.iterdir()):
        if not is_texture_folder(src):
            continue
        dest = blend.parent / src.name
        if dest.exists():
            continue
        blend.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dest))
        lines.append(f"textures восстановлены: {src} → {dest}")
        break
    return lines
