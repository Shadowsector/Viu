"""Реестр LoRA для Comfy MoCap: привязка к catalog_slug, подкачка, подстановка в workflow."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ...config import Config
from .paths import resolve_comfy_root

_REGISTRY_REV = 1
_TEMPLATES = Path(__file__).resolve().parent / "templates"
_REGISTRY_NAME = "comfy_loras.json"


@dataclass(frozen=True)
class LoraSpec:
    file: str
    strength: float = 0.85
    trigger: str = ""
    subfolder: str = ""


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
    data = load_registry(config)
    loras_root = comfy_loras_dir(config)
    lines = [
        f"Реестр: {registry_path(config)}",
        f"LoRA dir: {loras_root}",
        "",
    ]
    defaults = data.get("defaults") or []
    if defaults:
        lines.append("defaults (всегда):")
        for item in defaults:
            spec = _parse_lora_item(item)
            if spec:
                lines.append(_format_spec_line(config, spec, prefix="  • "))
        lines.append("")

    by_slug = data.get("by_slug") or {}
    if not by_slug:
        lines.append("by_slug: (пусто — добавь comfy_lora_bind)")
    else:
        lines.append("by_slug:")
        for slug in sorted(by_slug.keys()):
            binding = by_slug[slug]
            if not isinstance(binding, dict):
                continue
            lines.append(f"  [{slug}]")
            for item in binding.get("loras") or []:
                spec = _parse_lora_item(item)
                if spec:
                    lines.append(_format_spec_line(config, spec, prefix="    • "))
            dl = binding.get("download")
            if isinstance(dl, dict) and dl.get("url"):
                lines.append(f"    ↓ {dl.get('url')}")

    lib = data.get("library") or {}
    if lib:
        lines.append("")
        lines.append("library:")
        for name in sorted(lib.keys()):
            entry = lib[name]
            if not isinstance(entry, dict):
                continue
            url = str(entry.get("download_url") or entry.get("url") or "")
            on_disk = (loras_root / name).is_file()
            mark = "✓" if on_disk else "✗"
            lines.append(f"  {mark} {name}" + (f" — {url[:60]}…" if len(url) > 60 else (f" — {url}" if url else "")))
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
