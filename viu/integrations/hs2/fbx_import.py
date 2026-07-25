"""FBX из MeshExporter / ручного дампа → Inbox/animations."""

from __future__ import annotations

import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple

from ...anabarra_layout import inbox_dir
from ...animation_catalog import AnimationCatalogStore, animation_catalog_path, match_fbx_to_wish, suggest_rename_for_wish
from ...config import Config
from ...inbox_layout import inbox_animations_dir
from .catalog_hints import suggest_catalog_slug
from .paths import hs2_fbx_dump_dir


@dataclass
class FbxImportReport:
    ok: bool = True
    copied: List[Tuple[str, str]] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)

    def format(self) -> str:
        lines = ["HS2 FBX → Inbox/animations"]
        if not self.copied:
            lines.append("Нечего копировать.")
        for src, dest in self.copied:
            lines.append(f"  • {src} → {dest}")
        for e in self.errors:
            lines.append(f"  ⚠ {e}")
        if self.copied:
            lines.append(
                "\nДальше: «Принять анимацию (Inbox)» — по одному FBX + окно описания."
            )
        return "\n".join(lines)


def _sanitize_out_name(stem: str, suggested_slug: Optional[str]) -> str:
    if suggested_slug:
        base = "Shanya_" + "".join(p.capitalize() for p in suggested_slug.split("_"))
        return f"{base}.fbx"
    safe = re.sub(r"[^a-zA-Z0-9._-]+", "_", stem).strip("_")
    return f"HS2_{safe}.fbx" if safe else "HS2_clip.fbx"


def _unique_dest(dest: Path) -> Path:
    if not dest.exists():
        return dest
    stem, suffix = dest.stem, dest.suffix
    n = 2
    while dest.exists():
        dest = dest.with_name(f"{stem}_{n}{suffix}")
        n += 1
    return dest


def import_fbx_dump(
    config: Config,
    *,
    source_dir: Optional[Path] = None,
    limit: int = 20,
    use_catalog_rename: bool = True,
) -> FbxImportReport:
    """Копирует FBX из дампа в Inbox/animations с именами для matcher."""
    report = FbxImportReport()
    src_root = source_dir or hs2_fbx_dump_dir(config)
    if not src_root.is_dir():
        report.ok = False
        report.errors.append(f"Папка дампа не найдена: {src_root}")
        return report

    fbx_files = sorted(src_root.rglob("*.fbx"))
    if not fbx_files:
        report.errors.append(
            f"В {src_root} нет .fbx — экспортируй анимации из HS2 (MeshExporter / Studio)."
        )
        report.ok = False
        return report

    inbox_anim = inbox_animations_dir(config)
    inbox_anim.mkdir(parents=True, exist_ok=True)
    store = AnimationCatalogStore(animation_catalog_path(config)).load()

    for fbx in fbx_files[:limit]:
        slug_hint = suggest_catalog_slug(fbx.stem)
        wish = store.get_by_slug(slug_hint) if slug_hint else None
        if wish is None and use_catalog_rename:
            w2, score, _ = match_fbx_to_wish(fbx, store)
            if w2 and score >= 0.65:
                wish = w2

        if wish and use_catalog_rename:
            out_name = suggest_rename_for_wish(wish, fbx.name)
        else:
            out_name = _sanitize_out_name(fbx.stem, slug_hint)

        dest = _unique_dest(inbox_anim / out_name)
        try:
            shutil.copy2(fbx, dest)
            report.copied.append((fbx.name, str(dest)))
        except OSError as exc:
            report.errors.append(f"{fbx.name}: {exc}")

    if not report.copied:
        report.ok = False
    return report


def inbox_animations_pending_count(config: Config) -> int:
    inbox = inbox_dir(config)
    anim = inbox_animations_dir(config)
    n = 0
    for root in (inbox, anim):
        if not root.is_dir():
            continue
        for p in root.glob("*.fbx"):
            if p.is_file():
                n += 1
    return n
