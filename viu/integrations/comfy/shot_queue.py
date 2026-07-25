"""Очередь MoCap-анимаций: просмотр вперёд, правка промптов, away снимает по списку."""

from __future__ import annotations

import json
import threading
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from ...config import Config

_LOCK = threading.Lock()


@dataclass
class ShotQueueItem:
    id: str
    catalog_slug: str
    action: str
    title_ru: str = ""
    reason: str = ""
    enters_from: List[str] = field(default_factory=list)
    exits_to: List[str] = field(default_factory=list)
    looped: bool = False
    wan_positive: str = ""
    wan_negative: str = ""
    notes: str = ""
    status: str = "pending"  # pending | done | skipped
    created_at: str = ""
    # LoRA на этот кадр: inherit = пресет сессии; none = без LoRA; pick = lora_indices.
    lora_mode: str = "inherit"
    lora_indices: List[int] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "ShotQueueItem":
        mode = str(d.get("lora_mode") or "inherit").strip().lower()
        if mode not in ("inherit", "none", "pick"):
            mode = "inherit"
        raw_idx = d.get("lora_indices") or []
        indices: List[int] = []
        if isinstance(raw_idx, list):
            for x in raw_idx:
                try:
                    indices.append(int(x))
                except (TypeError, ValueError):
                    continue
        return cls(
            id=str(d.get("id") or uuid.uuid4().hex[:8]),
            catalog_slug=str(d.get("catalog_slug") or "").strip(),
            action=str(d.get("action") or "").strip(),
            title_ru=str(d.get("title_ru") or ""),
            reason=str(d.get("reason") or ""),
            enters_from=[str(x) for x in (d.get("enters_from") or []) if str(x).strip()],
            exits_to=[str(x) for x in (d.get("exits_to") or []) if str(x).strip()],
            looped=bool(d.get("looped")),
            wan_positive=str(d.get("wan_positive") or ""),
            wan_negative=str(d.get("wan_negative") or ""),
            notes=str(d.get("notes") or ""),
            status=str(d.get("status") or "pending"),
            created_at=str(d.get("created_at") or ""),
            lora_mode=mode,
            lora_indices=indices,
        )


def shot_queue_path(config: Config) -> Path:
    return Path(config.data_dir) / "comfy_shot_queue.json"


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _read(config: Config) -> Dict[str, Any]:
    path = shot_queue_path(config)
    if not path.is_file():
        return {"version": 1, "items": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"version": 1, "items": []}
    if not isinstance(data, dict):
        return {"version": 1, "items": []}
    data.setdefault("version", 1)
    data.setdefault("items", [])
    return data


def _write(config: Config, data: Dict[str, Any]) -> None:
    config.ensure_dirs()
    path = shot_queue_path(config)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def load_items(config: Config) -> List[ShotQueueItem]:
    with _LOCK:
        data = _read(config)
        return [ShotQueueItem.from_dict(x) for x in data.get("items") or [] if isinstance(x, dict)]


def save_items(config: Config, items: List[ShotQueueItem]) -> None:
    with _LOCK:
        _write(config, {"version": 1, "items": [i.to_dict() for i in items]})


def pending_items(config: Config) -> List[ShotQueueItem]:
    return [i for i in load_items(config) if i.status == "pending"]


def count_pending(config: Config) -> int:
    return len(pending_items(config))


def _draft_positive(action: str) -> str:
    from .prompts import mocap_prompt

    return mocap_prompt(action, None)


def _draft_negative() -> str:
    from .prompts import mocap_negative

    return mocap_negative()


def item_from_plan(plan: Any) -> ShotQueueItem:
    action = str(getattr(plan, "action", "") or "").strip()
    return ShotQueueItem(
        id=uuid.uuid4().hex[:8],
        catalog_slug=str(getattr(plan, "catalog_slug", "") or "").strip(),
        action=action,
        title_ru=str(getattr(plan, "title_ru", "") or ""),
        reason=str(getattr(plan, "reason", "") or ""),
        enters_from=list(getattr(plan, "enters_from", None) or []),
        exits_to=list(getattr(plan, "exits_to", None) or []),
        looped=bool(getattr(plan, "looped", False)),
        wan_positive=_draft_positive(action) if action else "",
        wan_negative=_draft_negative(),
        status="pending",
        created_at=_now(),
    )


def rebuild_queue(config: Config, *, limit: int = 8, keep_edits: bool = True) -> List[ShotQueueItem]:
    """Собрать очередь дыр графа. keep_edits — сохранить правки pending по slug."""
    from ...lab.comfy_director import invent_shot_choices

    old = {i.catalog_slug: i for i in load_items(config) if i.status == "pending"}
    plans = invent_shot_choices(config, limit=max(1, limit))
    out: List[ShotQueueItem] = []
    seen: set[str] = set()
    for plan in plans:
        slug = str(plan.catalog_slug or "").strip()
        if not slug or slug in seen:
            continue
        seen.add(slug)
        if keep_edits and slug in old:
            prev = old[slug]
            # Обновить граф, но оставить ручные промпты/заметки.
            prev.action = plan.action or prev.action
            prev.title_ru = plan.title_ru or prev.title_ru
            prev.reason = plan.reason or prev.reason
            prev.enters_from = list(plan.enters_from or prev.enters_from)
            prev.exits_to = list(plan.exits_to or prev.exits_to)
            prev.looped = bool(plan.looped)
            if not (prev.wan_positive or "").strip():
                prev.wan_positive = _draft_positive(prev.action)
            if not (prev.wan_negative or "").strip():
                prev.wan_negative = _draft_negative()
            out.append(prev)
        else:
            out.append(item_from_plan(plan))
    # Хвост: старые pending, которых нет в новых кандидатах (Ден уже правил).
    if keep_edits:
        for slug, prev in old.items():
            if slug not in seen:
                out.append(prev)
                seen.add(slug)
    save_items(config, out)
    return out


def update_item(config: Config, item_id: str, **fields: Any) -> Optional[ShotQueueItem]:
    items = load_items(config)
    found: Optional[ShotQueueItem] = None
    for it in items:
        if it.id == item_id:
            for k, v in fields.items():
                if hasattr(it, k):
                    setattr(it, k, v)
            found = it
            break
    if found is None:
        return None
    save_items(config, items)
    return found


def move_item(config: Config, item_id: str, *, delta: int) -> List[ShotQueueItem]:
    items = load_items(config)
    idx = next((i for i, x in enumerate(items) if x.id == item_id), -1)
    if idx < 0 or delta == 0:
        return items
    j = max(0, min(len(items) - 1, idx + delta))
    if j == idx:
        return items
    items[idx], items[j] = items[j], items[idx]
    save_items(config, items)
    return items


def take_next_pending(config: Config) -> Optional[ShotQueueItem]:
    """Снять первый pending → done (для invent_next_shot / away)."""
    with _LOCK:
        data = _read(config)
        items = [ShotQueueItem.from_dict(x) for x in data.get("items") or [] if isinstance(x, dict)]
        for it in items:
            if it.status != "pending":
                continue
            it.status = "done"
            data["items"] = [x.to_dict() for x in items]
            _write(config, data)
            return it
    return None


def peek_next_pending(config: Config) -> Optional[ShotQueueItem]:
    for it in load_items(config):
        if it.status == "pending":
            return it
    return None


def format_queue_brief(config: Config) -> str:
    from .shot_graphs import group_items_by_graph

    pending = pending_items(config)
    if not pending:
        return "Очередь анимаций пуста — «План MoCap» → Собрать."
    lines = [f"Очередь MoCap: {len(pending)} кадров впереди"]
    for graph, chunk in group_items_by_graph(pending):
        lines.append(f"  ▸ {graph.title_ru}")
        for it in chunk[:6]:
            title = it.title_ru or it.catalog_slug
            lines.append(f"    · `{it.catalog_slug}` — {title}: {(it.action or '')[:60]}")
        if len(chunk) > 6:
            lines.append(f"    … ещё {len(chunk) - 6} в этом графе")
    return "\n".join(lines)


def apply_item_lora_to_session(config: Config, item: ShotQueueItem) -> str:
    """Перенести LoRA с кадра очереди в lab-сессию (перед съёмкой)."""
    from ...lab.comfy_pipeline import COMFY_TOPIC
    from ...lab.session import load_session, new_session, save_session
    from .lora import scan_loras, spec_to_dict, specs_from_indices

    mode = (item.lora_mode or "inherit").strip().lower()
    if mode == "inherit":
        return ""
    session = load_session(config, COMFY_TOPIC)
    if session is None:
        session = new_session(COMFY_TOPIC)
    scan_loras(config)
    if mode == "none":
        session.meta["lora_last_pick"] = []
        session.meta["selected_loras"] = []
        save_session(config, session)
        return "LoRA с кадра: без LoRA"
    indices = [int(x) for x in (item.lora_indices or [])]
    specs = specs_from_indices(config, indices)
    session.meta["lora_last_pick"] = list(indices)
    session.meta["selected_loras"] = [spec_to_dict(s) for s in specs]
    save_session(config, session)
    if not specs:
        return "LoRA с кадра: без LoRA"
    return "LoRA с кадра: " + ", ".join(s.file for s in specs)
