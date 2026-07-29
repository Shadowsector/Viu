"""Редактируемая память Вью — VIU_MEMORY.md + явные «запомни» из чата.

Файл лежит в корне установки (U:\\Viu\\VIU_MEMORY.md) — Ден может править вручную.
Вью подмешивает его в reflect и work-заметки; JSON memory.json — для инструментов.
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Optional

from .anabarra_layout import viu_install_root
from .config import Config

VIU_MEMORY_FILENAME = "VIU_MEMORY.md"
_META_NAME = "viu_memory_meta.json"

_SECTION_EXPLICIT = "## Явные записи"
_SECTION_PREFS = "## Привычки и предпочтения"
_SECTION_REFS = "## Референсы (вдохновение)"
_SECTION_SUMMARIES = "## Итоги чатов"

# Без этой строки при NO_SYSTEM Magnum/Euryale зовут Дена Owner.
_IDENTITY_PREF_LINE = (
    "- Собеседника зовут Ден (Denis / Денис); обращаться «Ден» / на «ты», "
    "не Owner и не User."
)

_TEMPLATE = """# Память Вью

Редактируй свободно — Вью читает этот файл при размышлении.
Строки с `<!-- ... -->` — служебные; секции ниже не удаляй.

## Явные записи

<!-- сюда попадает «запомни» / «сохрани» из чата -->

## Привычки и предпочтения

- Собеседника зовут Ден (Denis / Денис); обращаться «Ден» / на «ты», не Owner и не User.

<!-- твои привычки, что нравится / не нравится в пайплайне и в игре -->

## Референсы (вдохновение)

<!-- описания референсов после твоей правки в окне «Референсы» -->

## Итоги чатов

<!-- короткие summary, не полный лог -->
"""

_REMEMBER = re.compile(
    r"(?:^|[\s,.:;])(?:"
    r"запомни(?:\s*,?\s*что)?|сохрани(?:\s+в(?:\s+)?память)?|не\s+забудь|"
    r"запиши\s+в\s+память|remember(?:\s+this)?|save\s+this"
    r")(?:\s|,|:|—|-|\.)?\s*",
    re.IGNORECASE | re.MULTILINE,
)

# «запомни это / тот квест / что обсуждали» — нужен контекст прошлых реплик
_DEICTIC_PAYLOAD = re.compile(
    r"(?is)^\s*(?:"
    r"это|то|всё\s+это|все\s+это|"
    r"(?:этот|тот|эту|ту|это|про)\s+"
    r"(?:квест|событие|сюжет|сцен\w*|разговор|момент|бит)(?:\s+\w+){0,4}|"
    r"(?:то\s*,?\s*)?что\s+(?:мы\s+)?(?:обсужда\w*|говорили|говорили)|"
    r"что\s+(?:выше|раньше)|"
    r"выше|предыдущ\w+|всё\s+выше"
    r")\.?\s*$"
)

_CONTEXT_HINT = re.compile(
    r"(?i)\b(?:"
    r"квест|событие|сюжет|сцен|разговор|момент|"
    r"обсужда|говорили|выше|этот|тот|это"
    r")\b"
)

_SUMMARY_EVERY_N = 8


def viu_memory_path(config: Config) -> Path:
    return viu_install_root(config) / VIU_MEMORY_FILENAME


def _meta_path(config: Config) -> Path:
    return Path(config.data_dir) / _META_NAME


def ensure_viu_memory(config: Config) -> Path:
    path = viu_memory_path(config)
    if not path.is_file():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(_TEMPLATE, encoding="utf-8")
    else:
        try:
            ensure_identity_pref(config)
        except Exception:  # noqa: BLE001
            pass
    return path


def read_viu_memory(config: Config, *, max_chars: int = 3200) -> str:
    path = ensure_viu_memory(config)
    try:
        text = path.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return ""
    if len(text) > max_chars:
        return text[:max_chars] + "\n…"
    return text


_MEMORY_ECHO_MARKERS = (
    "# Память Вью",
    "## Явные записи",
    "## Привычки и предпочтения",
    "## Референсы (вдохновение)",
    "## Итоги чатов",
    "--- VIU_MEMORY",
    "--- Память Вью",
)


def looks_like_memory_echo(text: str) -> bool:
    """Ответ модели = дамп VIU_MEMORY.md (после склейки памяти в user-msg)."""
    body = (text or "").strip()
    if not body:
        return False
    hits = sum(1 for m in _MEMORY_ECHO_MARKERS if m in body)
    if hits >= 2:
        return True
    if body.lstrip().startswith("# Память Вью"):
        return True
    if "<!-- сюда попадает" in body or "<!-- короткие summary" in body:
        return True
    return False


def _strip_html_comments(text: str) -> str:
    return re.sub(r"<!--.*?-->", "", text or "", flags=re.DOTALL)


def _section_body(text: str, section_header: str) -> str:
    idx = text.find(section_header)
    if idx < 0:
        return ""
    after = idx + len(section_header)
    rest = text[after:]
    next_h = re.search(r"\n## ", rest)
    chunk = rest[: next_h.start()] if next_h else rest
    lines = []
    for raw in chunk.splitlines():
        line = raw.strip()
        if not line or line.startswith("<!--"):
            continue
        lines.append(raw.rstrip())
    return "\n".join(lines).strip()


def format_reflect_block(config: Config, *, max_chars: int = 1600) -> str:
    """Короткий digest для reflect — без «Итогов чатов» (они провоцируют эхо)."""
    try:
        sanitize_poisoned_summaries(config)
    except OSError:
        pass
    try:
        ensure_identity_pref(config)
    except Exception:  # noqa: BLE001
        pass
    raw = read_viu_memory(config, max_chars=12000)
    if not raw:
        return ""
    text = _strip_html_comments(raw)
    parts: list[str] = []
    for header, label in (
        (_SECTION_EXPLICIT, "Явные"),
        (_SECTION_PREFS, "Привычки"),
        (_SECTION_REFS, "Референсы"),
    ):
        body = _section_body(text, header)
        if body:
            parts.append(f"{label}:\n{body}")
    digest = "\n\n".join(parts).strip()
    if not digest:
        return ""
    if len(digest) > max_chars:
        digest = digest[:max_chars].rstrip() + "\n…"
    return (
        "--- VIU_MEMORY (опирайся тихо; НЕ цитируй и НЕ пересказывай файл целиком) ---\n"
        + digest
    )


def sanitize_poisoned_summaries(config: Config) -> int:
    """Убрать из «Итоги чатов» строки, где Вью зачитала память вместо ответа."""
    path = viu_memory_path(config)
    if not path.is_file():
        return 0
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return 0
    if _SECTION_SUMMARIES not in text:
        return 0
    idx = text.find(_SECTION_SUMMARIES)
    head = text[: idx + len(_SECTION_SUMMARIES)]
    rest = text[idx + len(_SECTION_SUMMARIES) :]
    next_h = re.search(r"\n## ", rest)
    section = rest[: next_h.start()] if next_h else rest
    tail = rest[next_h.start() :] if next_h else ""
    kept: list[str] = []
    removed = 0
    for line in section.splitlines():
        if looks_like_memory_echo(line) or (
            line.strip().startswith("-")
            and any(m in line for m in ("# Память Вью", "## Явные", "VIU_MEMORY"))
        ):
            removed += 1
            continue
        kept.append(line)
    if removed <= 0:
        return 0
    new_section = "\n".join(kept)
    if not new_section.startswith("\n"):
        new_section = "\n" + new_section
    if not new_section.endswith("\n"):
        new_section += "\n"
    path.write_text(head + new_section + tail, encoding="utf-8")
    return removed


def _load_meta(config: Config) -> dict:
    path = _meta_path(config)
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _save_meta(config: Config, meta: dict) -> None:
    path = _meta_path(config)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _ensure_sections(text: str) -> str:
    if _SECTION_EXPLICIT not in text:
        text = text.rstrip() + f"\n\n{_SECTION_EXPLICIT}\n\n"
    for sec in (_SECTION_PREFS, _SECTION_REFS, _SECTION_SUMMARIES):
        if sec not in text:
            text = text.rstrip() + f"\n\n{sec}\n\n"
    return text


def _append_under_section(text: str, section_header: str, line: str) -> str:
    text = _ensure_sections(text)
    line = line.strip()
    if not line:
        return text
    if line in text:
        return text
    idx = text.find(section_header)
    if idx < 0:
        return text.rstrip() + f"\n\n{section_header}\n\n{line}\n"
    after = idx + len(section_header)
    rest = text[after:]
    next_h = re.search(r"\n## ", rest)
    if next_h:
        insert_at = after + next_h.start()
        return text[:insert_at].rstrip() + f"\n{line}\n" + text[insert_at:]
    return text.rstrip() + f"\n{line}\n"


def ensure_identity_pref(config: Config) -> bool:
    """Дописать имя Дена в prefs, если в памяти его ещё нет (старые пустые файлы)."""
    path = viu_memory_path(config)
    if not path.is_file():
        return False
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    if _IDENTITY_PREF_LINE in text:
        return False
    prefs = _section_body(_strip_html_comments(text), _SECTION_PREFS)
    if re.search(r"(?i)\bден\b|\bdenis\b|\bденис\b", prefs or ""):
        return False
    updated = _append_under_section(text, _SECTION_PREFS, _IDENTITY_PREF_LINE)
    if updated == text:
        return False
    try:
        path.write_text(updated, encoding="utf-8")
    except OSError:
        return False
    return True


def append_memory_line(
    config: Config,
    section_header: str,
    line: str,
    *,
    tags: Optional[list[str]] = None,
) -> None:
    path = ensure_viu_memory(config)
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        text = _TEMPLATE
    updated = _append_under_section(text, section_header, line)
    path.write_text(updated, encoding="utf-8")
    try:
        from .memory import MemoryStore

        MemoryStore(Path(config.data_dir) / "memory.json").add(
            line[:500],
            tags=list(tags or ["viu_memory"]),
        )
    except OSError:
        pass


def extract_remember_payload(user_text: str) -> Optional[str]:
    """Текст после «запомни» / «сохрани» — или None.

    Убирает лишнее «что» после запятой: «запомни, что X» → «X».
    Для «запомни это» вернёт короткое указание — контекст добирает
    ``resolve_remember_payload``.
    """
    raw = (user_text or "").strip()
    if not raw:
        return None
    m = _REMEMBER.search(raw)
    if not m:
        return None
    payload = raw[m.end() :].strip()
    payload = re.sub(r"^[—\-:.,]+", "", payload).strip()
    payload = re.sub(r"^(?:что|как)\s+", "", payload, flags=re.IGNORECASE).strip()
    if len(payload) < 3:
        # «запомни» / «запомни это» без тела — всё равно remember-запрос
        payload = raw
    return payload[:1200]


def remember_needs_context(payload: str) -> bool:
    """Нужны ли прошлые реплики, а не только хвост после «запомни»."""
    p = (payload or "").strip()
    if not p:
        return True
    if _DEICTIC_PAYLOAD.match(p):
        return True
    if looks_like_remember_request(p) and len(p) < 80:
        # payload = вся фраза «запомни этот квест»
        return True
    if len(p) < 48 and _CONTEXT_HINT.search(p):
        return True
    if len(p) < 24:
        return True
    return False


def _format_turn_lines(
    turns: list[tuple[str, str]],
    *,
    max_chars: int = 900,
) -> str:
    lines: list[str] = []
    size = 0
    for role, text in turns:
        who = "Ден" if role == "user" else "Вью"
        bit = re.sub(r"\s+", " ", (text or "").strip())
        if not bit:
            continue
        if looks_like_remember_request(bit):
            continue
        piece = f"{who}: {bit[:320]}"
        if size + len(piece) > max_chars and lines:
            break
        lines.append(piece)
        size += len(piece) + 1
    return " | ".join(lines)


def build_remember_context(
    config: Config,
    user_text: str,
    *,
    history: Optional[list] = None,
    assistant_text: str = "",
    max_chars: int = 900,
) -> str:
    """Собрать суть события/квеста из нескольких предыдущих сообщений."""
    turns: list[tuple[str, str]] = []

    hist = list(history or [])
    for m in hist:
        role = str((m or {}).get("role") or "")
        content = str((m or {}).get("content") or "").strip()
        if role in ("user", "assistant") and content:
            turns.append((role, content))

    # story_memory: текущий ход уже мог записаться — берём хвост и фильтруем
    try:
        from .story_memory import get_story_memory

        for beat in get_story_memory(config).recent(14):
            turns.append((beat.role, beat.text))
    except OSError:
        pass

    # Убрать дубли подряд и remember-фразу
    deduped: list[tuple[str, str]] = []
    seen: set[str] = set()
    for role, text in turns:
        key = f"{role}:{text[:120]}"
        if key in seen:
            continue
        seen.add(key)
        if looks_like_remember_request(text):
            continue
        if text.strip() == (user_text or "").strip():
            continue
        deduped.append((role, text))

    # Последние реплики до «запомни» важнее
    recent = deduped[-8:]
    body = _format_turn_lines(recent, max_chars=max_chars)

    # Недавние события (если уже были биты)
    try:
        from .event_memory import get_event_memory

        events = get_event_memory(config).recent(3)
        if events:
            bits = []
            for ev in events:
                bits.append(f"{ev.title}: {ev.what}"[:200])
            extra = "События: " + " · ".join(bits)
            if body:
                room = max_chars - len(body) - 3
                if room > 40:
                    body = body + " || " + extra[:room]
            else:
                body = extra[:max_chars]
    except Exception:  # noqa: BLE001
        pass

    # Короткий ответ Вью в этом же ходе — часто пересказ
    a = re.sub(r"\s+", " ", (assistant_text or "").strip())
    if a and not looks_like_memory_echo(a) and len(a) > 20:
        note = f"Вью сейчас: {a[:280]}"
        if body:
            room = max_chars - len(body) - 3
            if room > 40:
                body = body + " || " + note[:room]
        else:
            body = note[:max_chars]

    return body.strip()


def resolve_remember_payload(
    config: Config,
    user_text: str,
    *,
    history: Optional[list] = None,
    assistant_text: str = "",
) -> Optional[str]:
    """Итоговая строка для «Явные записи»: факт + контекст разговора при нужде."""
    payload = extract_remember_payload(user_text)
    if payload is None:
        return None

    # Если payload = вся фраза «запомни этот квест» — выкинуть сам триггер
    cleaned = payload
    if looks_like_remember_request(cleaned) and _REMEMBER.search(cleaned):
        m = _REMEMBER.search(cleaned)
        assert m is not None
        tail = cleaned[m.end() :].strip()
        tail = re.sub(r"^[—\-:.,]+", "", tail).strip()
        tail = re.sub(r"^(?:что|как)\s+", "", tail, flags=re.IGNORECASE).strip()
        if tail:
            cleaned = tail
        # иначе оставляем deictic/целиком для needs_context

    if not remember_needs_context(cleaned):
        return cleaned[:1200]

    ctx = build_remember_context(
        config,
        user_text,
        history=history,
        assistant_text=assistant_text,
    )
    if not ctx:
        return cleaned[:1200] if cleaned else None

    if cleaned and not _DEICTIC_PAYLOAD.match(cleaned) and len(cleaned) >= 12:
        # Есть своя формулировка + добираем обсуждение
        return f"{cleaned} — из разговора: {ctx}"[:1200]
    return f"Из разговора (событие/квест): {ctx}"[:1200]


def looks_like_remember_request(user_text: str) -> bool:
    return extract_remember_payload(user_text) is not None


def record_explicit_memory(
    config: Config,
    user_text: str,
    *,
    source: str = "chat",
    history: Optional[list] = None,
    assistant_text: str = "",
) -> bool:
    payload = resolve_remember_payload(
        config,
        user_text,
        history=history,
        assistant_text=assistant_text,
    )
    if not payload:
        return False
    stamp = time.strftime("%Y-%m-%d")
    line = f"- ({stamp}, {source}) {payload}"
    append_memory_line(
        config,
        _SECTION_EXPLICIT,
        line,
        tags=["explicit", "remember", source],
    )
    # Если речь про событие/квест — продублировать короткий бит в event_memory
    if re.search(r"(?i)квест|событие|сюжет|сцен", user_text + " " + payload):
        try:
            from .event_memory import get_event_memory

            title = "Запись из чата"
            m = re.search(
                r"(?i)(?:квест|событие|сюжет|сцена)\s*[«\":]?\s*(.{4,60})",
                payload,
            )
            if m:
                title = m.group(1).strip(" .,—-")[:60] or title
            get_event_memory(config).add(
                title=title,
                what=payload[:500],
                tags=["explicit", "remember"],
                source=source,
            )
        except Exception:  # noqa: BLE001
            pass
    return True


def record_reference_inspiration(config: Config, entry) -> None:
    """После сохранения референса в окне — в память для сцен и опыта."""
    from pathlib import Path as P

    title = (getattr(entry, "title", "") or P(getattr(entry, "path", "")).stem).strip()
    ru = (getattr(entry, "ru", "") or "").strip()
    pose = (getattr(entry, "en_pose", "") or "").strip()
    look = (getattr(entry, "en_look", "") or "").strip()
    notes = (getattr(entry, "notes", "") or "").strip()
    if not ru and not pose and not notes:
        return
    parts = [f"**{title}**"]
    if ru:
        parts.append(ru[:280])
    if pose:
        parts.append(f"pose: {pose[:160]}")
    if look:
        parts.append(f"look: {look[:120]}")
    if notes:
        parts.append(f"заметки: {notes[:160]}")
    line = "- " + " | ".join(parts)
    append_memory_line(
        config,
        _SECTION_REFS,
        line,
        tags=["reference", "inspiration"],
    )


def _one_line_summary(user_text: str, assistant_text: str) -> str:
    u = re.sub(r"\s+", " ", user_text).strip()[:160]
    a = re.sub(r"\s+", " ", assistant_text).strip()[:160]
    return f"Ден: {u} → Вью: {a}"


def maybe_record_chat_summary(
    config: Config,
    user_text: str,
    assistant_text: str,
) -> bool:
    """Короткий итог — не каждую реплику, а периодически и по весу темы."""
    from .prompts.reflect_mode import looks_like_story_chat

    if looks_like_memory_echo(assistant_text):
        return False

    combined = len(user_text) + len(assistant_text)
    story = looks_like_story_chat(user_text)
    work = bool(
        re.search(
            r"comfy|mocap|blender|unity|cascadeur|квест|сюжет|референс|inbox|анимац",
            (user_text + assistant_text).lower(),
        )
    )
    if not story and not work:
        return False
    if combined < 120 and not story:
        return False

    meta = _load_meta(config)
    n = int(meta.get("exchange_count", 0)) + 1
    meta["exchange_count"] = n
    _save_meta(config, meta)

    if n % _SUMMARY_EVERY_N != 0 and combined < 400:
        return False

    stamp = time.strftime("%Y-%m-%d %H:%M")
    line = f"- ({stamp}) {_one_line_summary(user_text, assistant_text)}"
    append_memory_line(
        config,
        _SECTION_SUMMARIES,
        line,
        tags=["summary", "chat"],
    )
    return True


def process_reflect_exchange(
    config: Config,
    user_text: str,
    assistant_text: str,
    *,
    source: str = "chat",
    history: Optional[list] = None,
) -> None:
    """После ответа reflect: явное «запомни» и редкие summary."""
    ensure_viu_memory(config)
    try:
        sanitize_poisoned_summaries(config)
    except OSError:
        pass
    if looks_like_memory_echo(assistant_text):
        return
    if record_explicit_memory(
        config,
        user_text,
        source=source,
        history=history,
        assistant_text=assistant_text,
    ):
        return
    maybe_record_chat_summary(config, user_text, assistant_text)
