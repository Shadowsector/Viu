"""Папки и матчинг ассетов под карточки 【AIS_Chara】.

Схема::

    U:\\Anabarra\\Inbox\\ais_cards\\    ← PNG-карточки (или копии из TempUnityCard)
    U:\\Anabarra\\Inbox\\ais_assets\\   ← россыпь ассетов (fbx/zip/png/unity…)
    U:\\Viu\\.viu\\character_cards_extract\\  ← JSON после десериализации

Процесс: card PNG → AnabarraAppearance JSON → скан ais_assets по ID/имени.
"""

from __future__ import annotations

import json
import re
import zipfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable, Optional

from .anabarra_layout import inbox_dir
from .config import Config

AIS_CARDS_SUBDIR = "ais_cards"
AIS_ASSETS_SUBDIR = "ais_assets"

_ASSET_SUFFIXES = frozenset(
    {
        ".fbx",
        ".blend",
        ".glb",
        ".gltf",
        ".obj",
        ".png",
        ".jpg",
        ".jpeg",
        ".webp",
        ".zip",
        ".7z",
        ".rar",
        ".unitypackage",
        ".asset",
        ".prefab",
        ".mat",
        ".mesh",
        ".txt",
        ".json",
        ".csv",
    }
)

_ID_IN_NAME = re.compile(r"(?<![A-Za-z])(\d{2,6})(?![A-Za-z])")
_TOKEN_SPLIT = re.compile(r"[^a-zA-Z0-9а-яА-ЯёЁ_+.-]+")


@dataclass
class AppearanceNeed:
    """Что ищем по карточке."""

    hair_ids: list[int] = field(default_factory=list)
    numeric_ids: list[int] = field(default_factory=list)
    name_tokens: list[str] = field(default_factory=list)
    kkex_mods: list[str] = field(default_factory=list)
    raw_hints: list[str] = field(default_factory=list)


@dataclass
class AssetHit:
    path: str
    score: float
    reasons: list[str] = field(default_factory=list)
    kind: str = ""  # hair | body | cloth | pack | other

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class MatchReport:
    card_json: str
    assets_root: str
    needs: AppearanceNeed
    hits: list[AssetHit] = field(default_factory=list)
    scanned_files: int = 0
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "card_json": self.card_json,
            "assets_root": self.assets_root,
            "needs": asdict(self.needs),
            "hits": [h.to_dict() for h in self.hits],
            "scanned_files": self.scanned_files,
            "notes": self.notes,
        }

    def format(self) -> str:
        lines = [
            f"Card JSON: {self.card_json}",
            f"Assets: {self.assets_root} ({self.scanned_files} files)",
            f"hair_ids={self.needs.hair_ids}",
            f"other_ids={self.needs.numeric_ids[:30]}",
            f"name_tokens={self.needs.name_tokens[:20]}",
            f"kkex={self.needs.kkex_mods[:15]}",
            f"hits={len(self.hits)}",
        ]
        if self.notes:
            lines.append(self.notes)
        for h in self.hits[:40]:
            why = ", ".join(h.reasons[:4])
            lines.append(f"  [{h.score:.1f}] {h.kind}: {h.path}")
            if why:
                lines.append(f"       ← {why}")
        if len(self.hits) > 40:
            lines.append(f"  … +{len(self.hits) - 40} more")
        return "\n".join(lines)


def inbox_ais_cards_dir(config: Config) -> Path:
    p = inbox_dir(config) / AIS_CARDS_SUBDIR
    p.mkdir(parents=True, exist_ok=True)
    return p


def inbox_ais_assets_dir(config: Config) -> Path:
    p = inbox_dir(config) / AIS_ASSETS_SUBDIR
    p.mkdir(parents=True, exist_ok=True)
    return p


def character_cards_extract_dir(config: Config) -> Path:
    p = Path(config.data_dir) / "character_cards_extract"
    p.mkdir(parents=True, exist_ok=True)
    return p


def ensure_ais_inbox_layout(config: Config) -> list[Path]:
    """Создать папки + README. Возвращает пути."""
    cards = inbox_ais_cards_dir(config)
    assets = inbox_ais_assets_dir(config)
    extract = character_cards_extract_dir(config)
    (cards / "README.txt").write_text(
        "Сюда PNG-карточки 【AIS_Chara】 (можно копировать из U:\\TempUnityCard).\n"
        "Вью: character_card_probe path=<эта папка>\n"
        "JSON появится в U:\\Viu\\.viu\\character_cards_extract\\\n",
        encoding="utf-8",
    )
    (assets / "README.txt").write_text(
        "Россыпь ассетов под карточку: .fbx .zip .png .unitypackage .blend …\n"
        "Можно без сортировки. Потом: character_card_match json=<…__anabarra.json>\n"
        "Вью поищет файлы по hair_ids / именам / числам в имени.\n",
        encoding="utf-8",
    )
    return [cards, assets, extract]


def load_appearance_dict(path: Path | str) -> dict[str, Any]:
    path = Path(path)
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("JSON root must be object")
    # допускаем полный ais dump с вложенным appearance
    if "appearance" in data and isinstance(data["appearance"], dict):
        app = dict(data["appearance"])
        if data.get("kkex_keys") and not app.get("kkex_mods"):
            app["kkex_mods"] = data["kkex_keys"]
        return app
    return data


def needs_from_appearance(app: dict[str, Any]) -> AppearanceNeed:
    need = AppearanceNeed()
    for x in app.get("hair_ids") or []:
        try:
            need.hair_ids.append(int(x))
        except (TypeError, ValueError):
            continue
    for part in app.get("hair_parts") or []:
        if isinstance(part, dict) and part.get("id") is not None:
            try:
                need.hair_ids.append(int(part["id"]))
            except (TypeError, ValueError):
                pass
    need.hair_ids = sorted(set(need.hair_ids))

    name = str(app.get("character_name") or "").strip()
    if name:
        need.name_tokens.extend(_tokens(name))
        need.raw_hints.append(name)

    for mod in app.get("kkex_mods") or app.get("kkex_keys") or []:
        s = str(mod).strip()
        if s:
            need.kkex_mods.append(s)
            need.name_tokens.extend(_tokens(s))

    # числа из face_detail / raw_parameter (осторожно — много шума)
    for blob in (app.get("face_detail"), app.get("raw_parameter")):
        need.numeric_ids.extend(_collect_small_ints(blob, limit=40))

    need.numeric_ids = sorted(
        {i for i in need.numeric_ids if i not in need.hair_ids and 0 < i < 100000}
    )[:60]
    need.name_tokens = _uniq_keep([t for t in need.name_tokens if len(t) >= 3])[:40]
    need.kkex_mods = _uniq_keep(need.kkex_mods)[:40]
    return need


def _tokens(text: str) -> list[str]:
    out = []
    for t in _TOKEN_SPLIT.split(text.lower()):
        t = t.strip("._-")
        if len(t) >= 3 and not t.isdigit():
            out.append(t)
    return out


def _uniq_keep(items: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for x in items:
        k = x.lower()
        if k in seen:
            continue
        seen.add(k)
        out.append(x)
    return out


def _collect_small_ints(node: Any, *, limit: int, out: Optional[list[int]] = None) -> list[int]:
    if out is None:
        out = []
    if len(out) >= limit:
        return out
    if isinstance(node, bool):
        return out
    if isinstance(node, int) and 1 <= node <= 99999:
        out.append(node)
        return out
    if isinstance(node, dict):
        for k, v in node.items():
            # id-like keys preferred
            kl = str(k).lower()
            if any(x in kl for x in ("id", "kind", "hair", "cloth", "wear", "type")):
                _collect_small_ints(v, limit=limit, out=out)
            elif isinstance(v, (dict, list)):
                _collect_small_ints(v, limit=limit, out=out)
            if len(out) >= limit:
                break
    elif isinstance(node, list):
        for v in node[:50]:
            _collect_small_ints(v, limit=limit, out=out)
            if len(out) >= limit:
                break
    return out


def _guess_kind(path: Path, reasons: list[str]) -> str:
    low = path.name.lower() + " " + str(path.parent).lower()
    joined = " ".join(reasons).lower()
    if "hair" in low or "hair" in joined or "прич" in low:
        return "hair"
    if any(x in low for x in ("cloth", "outfit", "wear", "coord", "одежд")):
        return "cloth"
    if any(x in low for x in ("body", "face", "head", "skin")):
        return "body"
    if path.suffix.lower() in {".zip", ".7z", ".rar", ".unitypackage"}:
        return "pack"
    return "other"


def iter_asset_files(root: Path, *, limit: int = 5000) -> list[Path]:
    files: list[Path] = []
    if not root.is_dir():
        return files
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        if p.name.lower().startswith("readme"):
            continue
        if p.suffix.lower() not in _ASSET_SUFFIXES and p.suffix:
            # без расширения — тоже берём (иногда сырые дампы)
            if p.suffix:
                continue
        files.append(p)
        if len(files) >= limit:
            break
    return files


def _zip_name_blob(path: Path, *, max_names: int = 80) -> str:
    try:
        with zipfile.ZipFile(path, "r") as zf:
            names = zf.namelist()[:max_names]
        return " ".join(names).lower()
    except (OSError, zipfile.BadZipFile):
        return ""


def score_asset(path: Path, need: AppearanceNeed) -> AssetHit | None:
    name = path.name
    low = name.lower()
    parent = path.parent.name.lower()
    blob = f"{low} {parent}"
    reasons: list[str] = []
    score = 0.0

    ids_in_name = {int(m.group(1)) for m in _ID_IN_NAME.finditer(name)}

    for hid in need.hair_ids:
        if hid in ids_in_name:
            score += 8.0
            reasons.append(f"hair_id={hid} in filename")
        elif re.search(rf"(?:hair|ha|h_)[_-]?0*{hid}\b", low):
            score += 9.0
            reasons.append(f"hair pattern {hid}")

    for nid in need.numeric_ids:
        if nid in ids_in_name and nid not in need.hair_ids:
            score += 2.5
            reasons.append(f"id={nid} in filename")

    for tok in need.name_tokens:
        if tok.lower() in low or tok.lower() in parent:
            score += 3.0
            reasons.append(f"token '{tok}'")

    for mod in need.kkex_mods:
        mlow = mod.lower()
        short = mlow.split(".")[-1] if "." in mlow else mlow
        if len(short) >= 4 and short in blob:
            score += 4.0
            reasons.append(f"kkex '{short}'")

    # zip: peek inner names for ids/tokens
    if path.suffix.lower() == ".zip" and score < 12:
        inner = _zip_name_blob(path)
        if inner:
            for hid in need.hair_ids:
                if re.search(rf"(?:hair|ha)?[_-]?0*{hid}\b", inner):
                    score += 6.0
                    reasons.append(f"hair_id={hid} inside zip")
                    break
            for tok in need.name_tokens[:10]:
                if tok.lower() in inner:
                    score += 2.0
                    reasons.append(f"token '{tok}' in zip")
                    break

    if score < 2.5:
        return None
    return AssetHit(
        path=str(path),
        score=round(score, 1),
        reasons=reasons,
        kind=_guess_kind(path, reasons),
    )


def match_appearance_to_assets(
    card_json: Path | str,
    assets_root: Path | str,
    *,
    min_score: float = 2.5,
    limit_files: int = 5000,
) -> MatchReport:
    card_json = Path(card_json)
    assets_root = Path(assets_root)
    app = load_appearance_dict(card_json)
    need = needs_from_appearance(app)
    files = iter_asset_files(assets_root, limit=limit_files)
    hits: list[AssetHit] = []
    for f in files:
        hit = score_asset(f, need)
        if hit and hit.score >= min_score:
            hits.append(hit)
    hits.sort(key=lambda h: (-h.score, h.path.lower()))
    notes = ""
    if not need.hair_ids and not need.name_tokens and not need.numeric_ids:
        notes = "WARN: в JSON мало якорей (нет hair_ids/имени) — матчинг слабый."
    if not files:
        notes = (notes + " " if notes else "") + f"Папка ассетов пуста: {assets_root}"
    return MatchReport(
        card_json=str(card_json),
        assets_root=str(assets_root),
        needs=need,
        hits=hits,
        scanned_files=len(files),
        notes=notes.strip(),
    )
