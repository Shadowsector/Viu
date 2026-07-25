"""Привязка личной установки Вью к машине Дена.

Не использует материнку / GPU / MAC — их Ден меняет.
Опора: имя пользователя + hostname + якоря путей U: + стабильный install_id.

Файл: ``.viu/machine_bind.json``. После апгрейда железа:
``python -m viu machine rebind`` или tool ``machine_bind action=rebind``.
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from getpass import getuser
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .anabarra_layout import anabarra_root, mascot_archive_dir, viu_install_root
from .config import Config

BIND_FILENAME = "machine_bind.json"
PERSONAL_OWNER = "den"  # канон: личная Анабарра / Вью


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _env_skip() -> bool:
    return os.environ.get("VIU_MACHINE_BIND_SKIP", "").strip() in ("1", "true", "yes")


@dataclass
class SoftTraits:
    """Мягкие признаки машины (переживают смену платы/GPU)."""

    username: str
    hostname: str
    viu_root: str
    anabarra_root: str
    mascot_root: str

    def fingerprint(self) -> str:
        blob = "|".join(
            [
                self.username.lower().strip(),
                self.hostname.lower().strip(),
                self.viu_root.lower().replace("\\", "/").rstrip("/"),
                self.anabarra_root.lower().replace("\\", "/").rstrip("/"),
                self.mascot_root.lower().replace("\\", "/").rstrip("/"),
            ]
        )
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:32]


@dataclass
class MachineBind:
    install_id: str
    owner: str = PERSONAL_OWNER
    personal_use_only: bool = True
    soft_fingerprint: str = ""
    traits: Dict[str, str] = field(default_factory=dict)
    created_at: str = ""
    updated_at: str = ""
    rebind_count: int = 0
    notes: str = (
        "Личная установка Анабарры. Не материнка/GPU — после апгрейда: viu machine rebind."
    )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, raw: Dict[str, Any]) -> "MachineBind":
        return cls(
            install_id=str(raw.get("install_id") or ""),
            owner=str(raw.get("owner") or PERSONAL_OWNER),
            personal_use_only=bool(raw.get("personal_use_only", True)),
            soft_fingerprint=str(raw.get("soft_fingerprint") or ""),
            traits={str(k): str(v) for k, v in (raw.get("traits") or {}).items()},
            created_at=str(raw.get("created_at") or ""),
            updated_at=str(raw.get("updated_at") or ""),
            rebind_count=int(raw.get("rebind_count") or 0),
            notes=str(raw.get("notes") or ""),
        )


def bind_path(config: Config) -> Path:
    return Path(config.data_dir) / BIND_FILENAME


def collect_soft_traits(config: Config) -> SoftTraits:
    try:
        user = getuser()
    except Exception:
        user = os.environ.get("USERNAME") or os.environ.get("USER") or "unknown"
    host = platform.node() or "unknown-host"
    return SoftTraits(
        username=user,
        hostname=host,
        viu_root=str(viu_install_root(config)),
        anabarra_root=str(anabarra_root(config)),
        mascot_root=str(mascot_archive_dir(config)),
    )


def load_bind(config: Config) -> Optional[MachineBind]:
    path = bind_path(config)
    if not path.is_file():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    if not isinstance(raw, dict):
        return None
    try:
        return MachineBind.from_dict(raw)
    except (TypeError, ValueError):
        return None


def save_bind(config: Config, bind: MachineBind) -> Path:
    path = bind_path(config)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(bind.to_dict(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return path


def ensure_bind(config: Config) -> Tuple[MachineBind, bool]:
    """Создать привязку при первом запуске. Returns (bind, created)."""
    existing = load_bind(config)
    if existing and existing.install_id and existing.soft_fingerprint:
        return existing, False
    traits = collect_soft_traits(config)
    now = _utc_now()
    bind = MachineBind(
        install_id=str(uuid.uuid4()),
        owner=PERSONAL_OWNER,
        personal_use_only=True,
        soft_fingerprint=traits.fingerprint(),
        traits=asdict(traits),
        created_at=now,
        updated_at=now,
        rebind_count=0,
    )
    save_bind(config, bind)
    return bind, True


def verify_bind(config: Config) -> Tuple[bool, str, Optional[MachineBind]]:
    """Проверить, что текущая машина совпадает с привязкой."""
    if _env_skip():
        return True, "VIU_MACHINE_BIND_SKIP=1 — проверка отключена", load_bind(config)
    bind = load_bind(config)
    if bind is None:
        return False, "привязки нет — вызови ensure / viu machine ensure", None
    traits = collect_soft_traits(config)
    current = traits.fingerprint()
    if bind.soft_fingerprint == current:
        return True, f"ok install_id={bind.install_id[:8]}… personal={bind.personal_use_only}", bind
    # Частичный матч: тот же user+host, но пути съехали — мягкое предупреждение
    same_user = (bind.traits.get("username") or "").lower() == traits.username.lower()
    same_host = (bind.traits.get("hostname") or "").lower() == traits.hostname.lower()
    if same_user and same_host:
        return (
            False,
            "отпечаток сменился (пути U: или data_dir). После переезда папок: "
            "viu machine rebind",
            bind,
        )
    return (
        False,
        "другая машина/пользователь. Личная Вью — rebind только если это всё ещё Ден: "
        "viu machine rebind",
        bind,
    )


def rebind(config: Config, *, reason: str = "") -> Tuple[MachineBind, str]:
    """Обновить soft_fingerprint, сохранив install_id (тот же личный контур)."""
    old, _ = ensure_bind(config)
    traits = collect_soft_traits(config)
    now = _utc_now()
    bind = MachineBind(
        install_id=old.install_id or str(uuid.uuid4()),
        owner=PERSONAL_OWNER,
        personal_use_only=True,
        soft_fingerprint=traits.fingerprint(),
        traits=asdict(traits),
        created_at=old.created_at or now,
        updated_at=now,
        rebind_count=int(old.rebind_count) + 1,
        notes=(
            old.notes
            or "Личная установка Анабарры."
        )
        + (f" rebind: {reason}" if reason else ""),
    )
    path = save_bind(config, bind)
    return bind, f"перепривязано → {path} (rebind #{bind.rebind_count})"


def require_personal_machine(
    config: Config,
    *,
    auto_ensure: bool = True,
) -> Tuple[bool, str]:
    """Гейт для операций с архивом ассетов / provenance."""
    if _env_skip():
        return True, "bind skip"
    bind = load_bind(config)
    if bind is None and auto_ensure:
        bind, _ = ensure_bind(config)
    ok, msg, _ = verify_bind(config)
    if ok and bind and not bind.personal_use_only:
        return False, "personal_use_only=false — откажись или почини machine_bind.json"
    return ok, msg


def status_text(config: Config) -> str:
    ok, msg, bind = verify_bind(config)
    traits = collect_soft_traits(config)
    lines: List[str] = [
        "Привязка машины (без материнки/GPU):",
        f"  статус: {'OK' if ok else 'НУЖЕН REBIND'}",
        f"  деталь: {msg}",
        f"  user/host: {traits.username} @ {traits.hostname}",
        f"  viu: {traits.viu_root}",
        f"  anabarra: {traits.anabarra_root}",
        f"  mascot: {traits.mascot_root}",
        f"  fp сейчас: {traits.fingerprint()}",
    ]
    if bind:
        lines.extend(
            [
                f"  install_id: {bind.install_id}",
                f"  personal_use_only: {bind.personal_use_only}",
                f"  owner: {bind.owner}",
                f"  rebind_count: {bind.rebind_count}",
                f"  файл: {bind_path(config)}",
            ]
        )
    else:
        lines.append(f"  файл: {bind_path(config)} (ещё нет)")
    lines.append("  после смены платы/GPU: python -m viu machine rebind")
    return "\n".join(lines)
