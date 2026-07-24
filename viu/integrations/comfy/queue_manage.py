"""Очередь ComfyUI: префиксы выходных файлов, сброс устаревших job."""

from __future__ import annotations

from typing import Any, Dict, List, Sequence, Tuple

from .client import ComfyClient, ComfyError
from .clip_review import normalize_catalog_slug
from .naming import normalize_slug_for_name


def _savevideo_prefixes_from_workflow(workflow: Any) -> List[str]:
    if not isinstance(workflow, dict):
        return []
    out: List[str] = []
    for node in workflow.values():
        if not isinstance(node, dict):
            continue
        if node.get("class_type") != "SaveVideo":
            continue
        inputs = node.get("inputs") or {}
        prefix = str(inputs.get("filename_prefix") or "").strip()
        if prefix:
            out.append(prefix)
    return out


def prefixes_from_queue_item(item: Any) -> List[str]:
    """Из элемента queue_running / queue_pending извлечь filename_prefix."""
    if not isinstance(item, (list, tuple)) or len(item) < 3:
        return []
    workflow = item[2]
    return _savevideo_prefixes_from_workflow(workflow)


def slug_from_output_prefix(prefix: str) -> str:
    """Girl_Idle_to_Lie_down_take_b → lie_down; Girl_Touch_self_take_a → touch_self."""
    p = (prefix or "").strip()
    if not p:
        return ""
    if p.lower().startswith("girl_"):
        p = p[5:]
    low = p.lower()
    if "_to_" in low:
        idx = low.rfind("_to_")
        rest = p[idx + 4 :]
    else:
        rest = p
    rest_low = rest.lower()
    for stop in ("_take", "_loop"):
        j = rest_low.find(stop)
        if j >= 0:
            rest = rest[:j]
            break
    return normalize_catalog_slug(rest)


def queue_prefixes(client: ComfyClient) -> Tuple[List[str], List[str]]:
    """(running_prefixes, pending_prefixes)."""
    q = client.get_queue()
    running: List[str] = []
    pending: List[str] = []
    for item in q.get("queue_running") or []:
        running.extend(prefixes_from_queue_item(item))
    for item in q.get("queue_pending") or []:
        pending.extend(prefixes_from_queue_item(item))
    return running, pending


def queue_slugs(client: ComfyClient) -> Tuple[List[str], List[str]]:
    running, pending = queue_prefixes(client)
    return (
        [slug_from_output_prefix(p) for p in running if slug_from_output_prefix(p)],
        [slug_from_output_prefix(p) for p in pending if slug_from_output_prefix(p)],
    )


def queue_stale_for_slug(
    client: ComfyClient,
    catalog_slug: str,
) -> Tuple[bool, List[str]]:
    """True если в очереди есть job с другим catalog_slug."""
    expected = normalize_slug_for_name(catalog_slug)
    if not expected:
        return False, []
    mismatched: List[str] = []
    running, pending = queue_prefixes(client)
    for prefix in running + pending:
        got = slug_from_output_prefix(prefix)
        if got and got != expected:
            mismatched.append(prefix)
    return bool(mismatched), mismatched


def format_queue_slugs_line(client: ComfyClient, *, limit: int = 5) -> str:
    run_slugs, pend_slugs = queue_slugs(client)
    bits: List[str] = []
    if run_slugs:
        bits.append(f"running: {', '.join(run_slugs[:limit])}")
    if pend_slugs:
        bits.append(f"pending: {', '.join(pend_slugs[:limit])}")
    if not bits:
        return ""
    extra = ""
    total = len(run_slugs) + len(pend_slugs)
    if total > limit:
        extra = f" (+{total - limit} ещё)"
    return "  очередь slugs: " + "; ".join(bits) + extra


def clear_comfy_queue(
    client: ComfyClient,
    *,
    interrupt_running: bool = True,
    free_memory: bool = False,
) -> str:
    """Прервать текущий job и очистить pending."""
    notes: List[str] = []
    q = client.get_queue()
    running_n = len(q.get("queue_running") or [])
    pending_n = len(q.get("queue_pending") or [])
    if running_n and interrupt_running:
        try:
            client.interrupt()
            notes.append(f"interrupt (было running={running_n})")
        except ComfyError as exc:
            notes.append(f"interrupt: {exc}")
    if pending_n:
        try:
            client.clear_queue()
            notes.append(f"clear pending={pending_n}")
        except ComfyError as exc:
            notes.append(f"clear: {exc}")
    elif not running_n:
        notes.append("очередь уже пуста")
    if free_memory:
        try:
            client.free_memory()
            notes.append("free VRAM")
        except ComfyError as exc:
            notes.append(f"free: {exc}")
    if not notes:
        return "Очередь Comfy: без изменений."
    return "Очередь Comfy: " + "; ".join(notes)


def prepare_queue_for_slug(
    client: ComfyClient,
    catalog_slug: str,
    *,
    force: bool = False,
) -> str:
    """Сбросить очередь, если в ней чужие slug (или force)."""
    expected = normalize_slug_for_name(catalog_slug)
    if not expected:
        return ""
    stale, prefixes = queue_stale_for_slug(client, expected)
    q = client.get_queue()
    pending_n = len(q.get("queue_pending") or [])
    running_n = len(q.get("queue_running") or [])
    if not stale and not force:
        return ""
    if not stale and force and pending_n == 0 and running_n == 0:
        return ""
    hint = ", ".join(prefixes[:3])
    if len(prefixes) > 3:
        hint += f" (+{len(prefixes) - 3})"
    msg = clear_comfy_queue(client, interrupt_running=True)
    return (
        f"Сброс устаревшей очереди (ожидался {expected}, было: {hint or 'неизвестно'}).\n"
        + msg
    )
