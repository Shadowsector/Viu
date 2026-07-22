"""Реестр LoRA для Comfy MoCap: скан папки, выбор перед пулом, подстановка в workflow."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from ...config import Config
from .paths import resolve_comfy_root

_REGISTRY_REV = 2
_TEMPLATES = Path(__file__).resolve().parent / "templates"
_REGISTRY_NAME = "comfy_loras.json"
_INDEX_NAME = "comfy_loras_index.json"
_LORA_EXTS = (".safetensors", ".pt", ".ckpt")

_LORA_PICK_PREFIX_RE = re.compile(
    r"^\s*(?:lora|лора)\s*[:\-–]\s*(.+)$",
    re.IGNORECASE,
)
_LORA_NONE_RE = re.compile(
    r"^\s*(?:none|нет|без|skip|пропустить|0|ничего)\b",
    re.IGNORECASE,
)
_TRIGGER_PARENS_RE = re.compile(r"\(([^)]+)\)")
_SIDECAR_NAMES = (
    "description.txt",
    "описание.txt",
    "readme.txt",
)


@dataclass(frozen=True)
class LoraSpec:
    file: str
    strength: float = 0.85
    trigger: str = ""
    subfolder: str = ""


@dataclass
class LoraIndexEntry:
    """Проиндексированный файл с диска (номер для выбора в чате)."""

    index: int
    file: str
    subfolder: str = ""
    size_mb: float = 0.0
    tags: List[str] = None  # type: ignore[assignment]
    trigger: str = ""
    description: str = ""
    folder_slug: str = ""
    strength: float = 0.85
    mtime: float = 0.0

    def __post_init__(self) -> None:
        if self.tags is None:
            self.tags = []

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "LoraIndexEntry":
        tags = d.get("tags")
        return LoraIndexEntry(
            index=int(d.get("index") or 0),
            file=str(d.get("file") or ""),
            subfolder=str(d.get("subfolder") or ""),
            size_mb=float(d.get("size_mb") or 0),
            tags=[str(t) for t in (tags or [])],
            trigger=str(d.get("trigger") or ""),
            description=str(d.get("description") or ""),
            folder_slug=str(d.get("folder_slug") or ""),
            strength=float(d.get("strength") or 0.85),
            mtime=float(d.get("mtime") or 0),
        )

    def to_spec(self) -> LoraSpec:
        return LoraSpec(
            file=self.file,
            strength=self.strength,
            trigger=self.trigger,
            subfolder=self.subfolder,
        )


def index_path(config: Config) -> Path:
    return config.data_dir / _INDEX_NAME


def registry_path(config: Config) -> Path:
    return config.data_dir / _REGISTRY_NAME


def comfy_loras_dir(config: Config) -> Path:
    """Каталог LoRA внутри ComfyUI (или fallback в .viu/comfy/loras)."""
    root = resolve_comfy_root(config)
    if root is not None:
        p = root / "models" / "loras"
    else:
        p = config.data_dir / "comfy" / "loras"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _lora_disk_path(config: Config, spec: LoraSpec) -> Path:
    base = comfy_loras_dir(config)
    sub = (spec.subfolder or "").strip().replace("\\", "/").strip("/")
    if sub:
        return base / sub / spec.file
    return base / spec.file


def _empty_registry() -> Dict[str, Any]:
    return {
        "_viu_rev": _REGISTRY_REV,
        "defaults": [],
        "by_slug": {},
        "library": {},
    }


def load_registry(config: Config) -> Dict[str, Any]:
    ensure_registry(config)
    try:
        data = json.loads(registry_path(config).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return _empty_registry()
    if not isinstance(data, dict):
        return _empty_registry()
    data.setdefault("defaults", [])
    data.setdefault("by_slug", {})
    data.setdefault("library", {})
    return data


def save_registry(config: Config, data: Dict[str, Any]) -> Path:
    path = registry_path(config)
    path.parent.mkdir(parents=True, exist_ok=True)
    data["_viu_rev"] = _REGISTRY_REV
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def ensure_registry(config: Config) -> Path:
    path = registry_path(config)
    if path.is_file():
        return path
    src = _TEMPLATES / _REGISTRY_NAME
    path.parent.mkdir(parents=True, exist_ok=True)
    if src.is_file():
        shutil.copy2(src, path)
    else:
        save_registry(config, _empty_registry())
    return path


def _parse_lora_item(raw: Any) -> Optional[LoraSpec]:
    if isinstance(raw, str):
        name = raw.strip()
        if name:
            return LoraSpec(file=name)
        return None
    if not isinstance(raw, dict):
        return None
    file = str(raw.get("file") or raw.get("lora_file") or raw.get("name") or "").strip()
    if not file:
        return None
    try:
        strength = float(raw.get("strength", raw.get("strength_model", 0.85)))
    except (TypeError, ValueError):
        strength = 0.85
    trigger = str(raw.get("trigger") or raw.get("trigger_words") or "").strip()
    subfolder = str(raw.get("subfolder") or "").strip()
    return LoraSpec(file=file, strength=strength, trigger=trigger, subfolder=subfolder)


def _slug_binding(data: Dict[str, Any], catalog_slug: str) -> Dict[str, Any]:
    by_slug = data.get("by_slug") or {}
    if not isinstance(by_slug, dict):
        return {}
    key = (catalog_slug or "").strip()
    if not key:
        return {}
    binding = by_slug.get(key)
    return binding if isinstance(binding, dict) else {}


def find_loras_for_slug(config: Config, catalog_slug: str) -> List[LoraIndexEntry]:
    """LoRA из подпапки loras/<slug>/ (или совпадение по имени папки)."""
    slug = (catalog_slug or "").strip().lower()
    if not slug:
        return []
    entries = load_index(config)
    out: List[LoraIndexEntry] = []
    for entry in entries:
        folder = (entry.folder_slug or _folder_slug_from_subfolder(entry.subfolder)).lower()
        full = (entry.subfolder or "").replace("\\", "/").strip("/").lower()
        if folder == slug or full == slug:
            out.append(entry)
    return out


def suggest_loras_for_slug(config: Config, catalog_slug: str) -> List[LoraSpec]:
    """Реестр by_slug + привязка по папке на диске."""
    specs: List[LoraSpec] = []
    seen: set[str] = set()

    def _add(spec: LoraSpec) -> None:
        key = f"{spec.subfolder}/{spec.file}".lower()
        if key in seen:
            return
        seen.add(key)
        specs.append(spec)

    for spec in resolve_loras_for_slug(config, catalog_slug):
        _add(spec)

    if lora_folder_bind_enabled():
        for entry in find_loras_for_slug(config, catalog_slug):
            _add(entry.to_spec())

    return specs


def resolve_loras_for_slug(config: Config, catalog_slug: str) -> List[LoraSpec]:
    """LoRA только для текущего slug (+ defaults). Без slug — пусто (не грузим лишнее в VRAM)."""
    data = load_registry(config)
    specs: List[LoraSpec] = []
    seen: set[str] = set()

    def _add(raw_list: Any) -> None:
        if not isinstance(raw_list, list):
            return
        for item in raw_list:
            spec = _parse_lora_item(item)
            if spec is None:
                continue
            key = f"{spec.subfolder}/{spec.file}".lower()
            if key in seen:
                continue
            seen.add(key)
            lib = (data.get("library") or {}).get(spec.file)
            if isinstance(lib, dict):
                if not spec.subfolder and lib.get("subfolder"):
                    spec = LoraSpec(
                        file=spec.file,
                        strength=spec.strength,
                        trigger=spec.trigger or str(lib.get("trigger") or ""),
                        subfolder=str(lib.get("subfolder") or ""),
                    )
                if not spec.trigger and lib.get("trigger"):
                    spec = LoraSpec(
                        file=spec.file,
                        strength=spec.strength,
                        trigger=str(lib.get("trigger") or ""),
                        subfolder=spec.subfolder,
                    )
            if not spec.trigger:
                file_trigger = _triggers_from_filename(spec.file)
                if file_trigger:
                    spec = LoraSpec(
                        file=spec.file,
                        strength=spec.strength,
                        trigger=file_trigger,
                        subfolder=spec.subfolder,
                    )
            specs.append(spec)

    _add(data.get("defaults"))
    binding = _slug_binding(data, catalog_slug)
    _add(binding.get("loras"))
    return specs


def append_trigger_words(prompt: str, loras: List[LoraSpec]) -> str:
    prompt = (prompt or "").strip()
    extras: List[str] = []
    for spec in loras:
        t = (spec.trigger or "").strip()
        if t and t.lower() not in prompt.lower():
            extras.append(t)
    if not extras:
        return prompt
    suffix = ", ".join(extras)
    return f"{prompt}, {suffix}" if prompt else suffix


def _tags_from_filename(name: str) -> List[str]:
    stem = Path(name).stem.lower()
    parts = re.split(r"[_\-\s]+", stem)
    return [p for p in parts if len(p) >= 2]


def _triggers_from_filename(name: str) -> str:
    """Триггер из скобок в имени: my_lora_(touch_motion).safetensors."""
    stem = Path(name).stem
    matches = _TRIGGER_PARENS_RE.findall(stem)
    if not matches:
        return ""
    return matches[-1].strip()


def _folder_slug_from_subfolder(subfolder: str) -> str:
    sub = (subfolder or "").strip().replace("\\", "/").strip("/")
    if not sub:
        return ""
    return sub.split("/")[-1].lower()


def _read_sidecar_description(lora_path: Path) -> str:
    """Описание из txt рядом с LoRA или в её подпапке."""
    parent = lora_path.parent
    stem = lora_path.stem
    candidates = [
        lora_path.with_suffix(lora_path.suffix + ".txt"),
        parent / f"{stem}.txt",
    ]
    for name in _SIDECAR_NAMES:
        candidates.append(parent / name)
    seen: set[str] = set()
    for path in candidates:
        key = str(path).lower()
        if key in seen:
            continue
        seen.add(key)
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8").strip()
        except OSError:
            continue
        if text:
            return text[:800]
    return ""


def lora_folder_bind_enabled() -> bool:
    raw = (os.environ.get("VIU_COMFY_LORA_FOLDER_BIND") or "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


def lora_auto_pick_enabled() -> bool:
    raw = (os.environ.get("VIU_COMFY_LORA_AUTO") or "0").strip().lower()
    return raw in ("1", "true", "yes", "on")


def _library_entry(data: Dict[str, Any], filename: str) -> Dict[str, Any]:
    lib = data.get("library") or {}
    if not isinstance(lib, dict):
        return {}
    entry = lib.get(filename)
    return entry if isinstance(entry, dict) else {}


def scan_loras(config: Config, *, save: bool = True) -> List[LoraIndexEntry]:
    """Проиндексировать все LoRA в ComfyUI/models/loras/ (рекурсивно)."""
    ensure_registry(config)
    data = load_registry(config)
    root = comfy_loras_dir(config)
    found: List[LoraIndexEntry] = []
    try:
        paths = sorted(
            (p for p in root.rglob("*") if p.is_file() and p.suffix.lower() in _LORA_EXTS),
            key=lambda p: str(p.relative_to(root)).lower(),
        )
    except OSError:
        paths = []
    for i, path in enumerate(paths, start=1):
        try:
            rel = path.relative_to(root)
            subfolder = "" if rel.parent == Path(".") else str(rel.parent).replace("\\", "/")
            stat = path.stat()
            lib = _library_entry(data, path.name)
            file_trigger = _triggers_from_filename(path.name)
            lib_trigger = str(lib.get("trigger") or "").strip()
            sidecar = _read_sidecar_description(path)
            lib_desc = str(lib.get("description") or "").strip()
            tags = [str(t) for t in (lib.get("tags") or [])] or _tags_from_filename(path.name)
            found.append(
                LoraIndexEntry(
                    index=i,
                    file=path.name,
                    subfolder=subfolder,
                    size_mb=round(stat.st_size / (1024 * 1024), 1),
                    tags=tags,
                    trigger=lib_trigger or file_trigger,
                    description=lib_desc or sidecar,
                    folder_slug=_folder_slug_from_subfolder(subfolder),
                    strength=float(lib.get("strength") or 0.85),
                    mtime=stat.st_mtime,
                )
            )
        except (OSError, ValueError):
            continue
    if save:
        save_index(config, found)
    return found


def save_index(config: Config, entries: List[LoraIndexEntry]) -> Path:
    path = index_path(config)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "_viu_rev": _REGISTRY_REV,
        "scanned_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "loras_dir": str(comfy_loras_dir(config)),
        "entries": [e.to_dict() for e in entries],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def load_index(config: Config, *, rescan_if_missing: bool = True) -> List[LoraIndexEntry]:
    path = index_path(config)
    if not path.is_file():
        if rescan_if_missing:
            return scan_loras(config)
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        raw = data.get("entries") or []
        entries = [LoraIndexEntry.from_dict(x) for x in raw if isinstance(x, dict)]
        if entries:
            return entries
    except (OSError, json.JSONDecodeError):
        pass
    return scan_loras(config) if rescan_if_missing else []


def format_lora_pick_message(entries: List[LoraIndexEntry]) -> str:
    if not entries:
        return (
            "В ComfyUI/models/loras/ нет LoRA.\n"
            "Скачай .safetensors в эту папку → comfy_lora_scan.\n"
            "Ответь: `lora: none` — генерировать без LoRA."
        )
    lines = [
        "Выбери LoRA для этого пула (можно несколько):",
        "",
    ]
    for e in entries:
        tag_hint = f" [{', '.join(e.tags[:4])}]" if e.tags else ""
        sub = f" ({e.subfolder}/)" if e.subfolder else ""
        trig = f' trigger="{e.trigger}"' if e.trigger else ""
        desc = ""
        if e.description:
            one_line = " ".join(e.description.split())
            desc = f"\n      {one_line[:160]}{'…' if len(one_line) > 160 else ''}"
        lines.append(f"  {e.index}. {e.file}{sub} — {e.size_mb} MB{tag_hint}{trig}{desc}")
    lines.extend(
        [
            "",
            "Ответь:",
            "• `lora: 1` или `lora: 1,3` — выбранные",
            "• `lora: all` — все из списка",
            "• `lora: none` — без LoRA (чистый Wan)",
        ]
    )
    return "\n".join(lines)


def parse_lora_pick_reply(text: str, *, max_index: int = 99) -> Optional[List[int]]:
    """None = не поняла; [] = без LoRA; [1,3] = выбор."""
    raw = (text or "").strip()
    if not raw:
        return None
    if _LORA_NONE_RE.match(raw):
        return []
    body = raw
    m = _LORA_PICK_PREFIX_RE.match(raw)
    if m:
        body = m.group(1).strip()
        if _LORA_NONE_RE.match(body) or body.lower() in ("none", "0"):
            return []
    elif _LORA_NONE_RE.match(raw):
        return []
    elif not re.search(r"\d", raw):
        return None
    if body.lower() in ("all", "все", "*"):
        return list(range(1, max_index + 1))
    nums: List[int] = []
    for part in re.split(r"[,;\s]+", body):
        part = part.strip()
        if not part:
            continue
        if part.lower() in ("all", "все"):
            return list(range(1, max_index + 1))
        try:
            n = int(part)
        except ValueError:
            return None
        if n < 1 or n > max_index:
            return None
        if n not in nums:
            nums.append(n)
    return nums if nums else None


def specs_from_indices(config: Config, indices: List[int]) -> List[LoraSpec]:
    entries = load_index(config)
    by_idx = {e.index: e for e in entries}
    specs: List[LoraSpec] = []
    for i in indices:
        entry = by_idx.get(i)
        if entry is not None:
            specs.append(entry.to_spec())
    return specs


def spec_to_dict(spec: LoraSpec) -> Dict[str, Any]:
    return {
        "file": spec.file,
        "strength": spec.strength,
        "trigger": spec.trigger,
        "subfolder": spec.subfolder,
    }


def specs_from_session_meta(meta: Dict[str, Any]) -> List[LoraSpec]:
    raw = meta.get("selected_loras") or []
    specs: List[LoraSpec] = []
    if not isinstance(raw, list):
        return specs
    for item in raw:
        spec = _parse_lora_item(item)
        if spec is not None:
            specs.append(spec)
    return specs


def update_library_entry(
    config: Config,
    lora_file: str,
    *,
    trigger: str = "",
    strength: float | None = None,
    tags: str = "",
) -> Tuple[bool, str]:
    name = (lora_file or "").strip()
    if not name:
        return False, "Нужен lora_file=."
    data = load_registry(config)
    lib = data.setdefault("library", {})
    entry = dict(lib.get(name) or {})
    if trigger:
        entry["trigger"] = trigger.strip()
    if strength is not None:
        entry["strength"] = float(strength)
    if tags:
        entry["tags"] = [t.strip() for t in re.split(r"[,;]", tags) if t.strip()]
    lib[name] = entry
    save_registry(config, data)
    scan_loras(config)
    return True, f"Заметки для {name} сохранены (trigger/strength/tags)."


def _download_url_for_spec(config: Config, spec: LoraSpec) -> Optional[str]:
    data = load_registry(config)
    lib = (data.get("library") or {}).get(spec.file)
    if isinstance(lib, dict):
        url = str(lib.get("download_url") or lib.get("url") or "").strip()
        if url:
            return url
    for binding in (data.get("by_slug") or {}).values():
        if not isinstance(binding, dict):
            continue
        dl = binding.get("download")
        if not isinstance(dl, dict):
            continue
        if str(dl.get("file") or "").strip() == spec.file:
            url = str(dl.get("url") or dl.get("download_url") or "").strip()
            if url:
                return url
    return None


def _sha256_for_spec(config: Config, spec: LoraSpec) -> str:
    data = load_registry(config)
    lib = (data.get("library") or {}).get(spec.file)
    if isinstance(lib, dict):
        return str(lib.get("sha256") or "").strip().lower()
    return ""


def _http_headers() -> Dict[str, str]:
    headers = {"User-Agent": "Viu-ComfyLoRA/1.0"}
    token = os.environ.get("VIU_CIVITAI_TOKEN", "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _download_file(url: str, dest: Path, *, timeout: float = 600.0) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    req = urllib.request.Request(url, headers=_http_headers())
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = resp.read()
    tmp.write_bytes(data)
    tmp.replace(dest)


def fetch_lora_file(
    config: Config,
    spec: LoraSpec,
    *,
    force: bool = False,
) -> Tuple[bool, str]:
    dest = _lora_disk_path(config, spec)
    if dest.is_file() and not force:
        return True, f"уже есть: {dest.name}"
    url = _download_url_for_spec(config, spec)
    if not url:
        return False, f"нет download_url для {spec.file} (добавь в library или comfy_lora_bind)"
    try:
        _download_file(url, dest)
    except (urllib.error.URLError, OSError, TimeoutError) as exc:
        return False, f"скачать {spec.file}: {exc}"
    expected = _sha256_for_spec(config, spec)
    if expected:
        digest = hashlib.sha256(dest.read_bytes()).hexdigest().lower()
        if digest != expected:
            try:
                dest.unlink(missing_ok=True)
            except OSError:
                pass
            return False, f"sha256 mismatch для {spec.file}"
    return True, f"скачано → {dest}"


def ensure_lora_files(
    config: Config,
    loras: List[LoraSpec],
    *,
    auto_fetch: bool = True,
) -> Tuple[bool, List[str]]:
    """Проверить файлы на диске; при auto_fetch попытаться скачать из реестра."""
    if not loras:
        return True, []
    notes: List[str] = []
    all_ok = True
    for spec in loras:
        dest = _lora_disk_path(config, spec)
        if dest.is_file():
            notes.append(f"OK {spec.file}")
            continue
        if auto_fetch:
            ok, msg = fetch_lora_file(config, spec)
            notes.append(msg)
            if ok:
                continue
        all_ok = False
        notes.append(f"НЕТ {spec.file} → {dest}")
    return all_ok, notes


def bind_slug(
    config: Config,
    *,
    catalog_slug: str,
    lora_file: str,
    strength: float = 0.85,
    trigger: str = "",
    subfolder: str = "",
    download_url: str = "",
    replace: bool = False,
) -> Tuple[bool, str]:
    slug = (catalog_slug or "").strip()
    file = (lora_file or "").strip()
    if not slug or not file:
        return False, "Нужны catalog_slug= и lora_file=."
    data = load_registry(config)
    by_slug = data.setdefault("by_slug", {})
    binding: Dict[str, Any]
    if replace or slug not in by_slug:
        binding = {"loras": []}
    else:
        binding = dict(by_slug.get(slug) or {})
        binding.setdefault("loras", [])
    loras = binding.setdefault("loras", [])
    if not isinstance(loras, list):
        loras = []
        binding["loras"] = loras
    entry: Dict[str, Any] = {"file": file, "strength": strength}
    if trigger:
        entry["trigger"] = trigger
    if subfolder:
        entry["subfolder"] = subfolder
    loras.append(entry)
    by_slug[slug] = binding
    if download_url:
        lib = data.setdefault("library", {})
        lib_entry = dict(lib.get(file) or {})
        lib_entry["download_url"] = download_url.strip()
        if trigger:
            lib_entry["trigger"] = trigger
        if subfolder:
            lib_entry["subfolder"] = subfolder
        lib[file] = lib_entry
    save_registry(config, data)
    return True, f"Привязано {file} (strength={strength}) → slug {slug}"


def list_registry_status(config: Config) -> str:
    ensure_registry(config)
    entries = load_index(config)
    loras_root = comfy_loras_dir(config)
    lines = [
        f"Индекс: {index_path(config)}",
        f"LoRA dir: {loras_root}",
        f"На диске: {len(entries)} файл(ов)",
        "",
    ]
    if entries:
        lines.append("Список (номера для `lora: 1,2`):")
        for e in entries:
            tag_hint = f" — {', '.join(e.tags[:5])}" if e.tags else ""
            sub = f"{e.subfolder}/" if e.subfolder else ""
            trig = f' | trigger="{e.trigger}"' if e.trigger else ""
            lines.append(f"  {e.index}. {sub}{e.file} @ {e.strength}{tag_hint}{trig}")
        lines.append("")
    else:
        lines.append("Папка пуста — скачай LoRA в models/loras/, потом comfy_lora_scan.")
        lines.append("")

    data = load_registry(config)
    lib = data.get("library") or {}
    if lib:
        lines.append("library (trigger/strength/tags):")
        for name in sorted(lib.keys()):
            entry = lib[name]
            if not isinstance(entry, dict):
                continue
            trig = str(entry.get("trigger") or "")
            lines.append(f"  • {name}" + (f' — "{trig}"' if trig else ""))
    return "\n".join(lines)


def _format_spec_line(config: Config, spec: LoraSpec, *, prefix: str = "") -> str:
    dest = _lora_disk_path(config, spec)
    mark = "✓" if dest.is_file() else "✗"
    bits = [f"{mark} {spec.file} @ {spec.strength}"]
    if spec.trigger:
        bits.append(f'trigger="{spec.trigger}"')
    if spec.subfolder:
        bits.append(f"sub={spec.subfolder}")
    return prefix + " ".join(bits)


def fetch_for_slug(
    config: Config,
    catalog_slug: str,
    *,
    force: bool = False,
) -> Tuple[bool, str]:
    specs = resolve_loras_for_slug(config, catalog_slug)
    if not specs:
        return False, f"Для slug {catalog_slug!r} LoRA не привязаны."
    lines: List[str] = []
    ok_all = True
    for spec in specs:
        ok, msg = fetch_lora_file(config, spec, force=force)
        lines.append(msg)
        ok_all = ok_all and ok
    return ok_all, "\n".join(lines)


def fetch_all_missing(config: Config, *, force: bool = False) -> Tuple[bool, str]:
    data = load_registry(config)
    seen: Dict[str, LoraSpec] = {}
    for item in data.get("defaults") or []:
        spec = _parse_lora_item(item)
        if spec:
            seen[spec.file] = spec
    for binding in (data.get("by_slug") or {}).values():
        if not isinstance(binding, dict):
            continue
        for item in binding.get("loras") or []:
            spec = _parse_lora_item(item)
            if spec:
                seen[spec.file] = spec
    if not seen:
        return True, "Нечего качать — реестр пуст."
    lines: List[str] = []
    ok_all = True
    for spec in seen.values():
        dest = _lora_disk_path(config, spec)
        if dest.is_file() and not force:
            lines.append(f"skip {spec.file}")
            continue
        ok, msg = fetch_lora_file(config, spec, force=force)
        lines.append(msg)
        ok_all = ok_all and ok
    return ok_all, "\n".join(lines)
