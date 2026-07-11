# Канал Cursor ↔ Viu

Ден — визионер и технический писатель. **Не** кнопконажиматель.

| Направление | Файл | Кто пишет |
|-------------|------|-----------|
| Viu → Cursor | `docs/CURSOR_HANDOFF.md` | Viu (`cursor_handoff_with_logs`) |
| Cursor → Viu | `docs/VIU_INBOX.json` | Cursor (commit/push) |

## Как работает

1. **Cursor** кладёт задачу в `VIU_INBOX.json` (`status: pending`) и пушит ветку.
2. **Viu** (GUI) раз в ~3 мин сама тянет inbox с GitHub. Или агент вызывает `cursor_inbox_pull`.
3. Viu выполняет инструментами (`overlay_playtest`, Unity, Blender…).
4. Viu ставит `done` / `blocked` / `needs_decision` через `cursor_inbox_complete` и пишет handoff.
5. **Дена** зовут только при `needs_decision` или живом выборе (сюжет, вкус, деньги).

## Инструменты Viu

| Tool | Зачем |
|------|--------|
| `cursor_inbox_pull` | Скачать pending |
| `cursor_inbox_complete` | Закрыть задачу + push |
| `overlay_playtest` | Сборка + запуск + boot-лог + gist |
| `cursor_handoff_with_logs` | Отчёт Cursor |

## Настройка

В `U:\Viu\.env`:

```env
VIU_GITHUB_TOKEN=ghp_...
VIU_GITHUB_REPO=Shadowsector/Viu
VIU_HANDOFF_BRANCH=cursor/viu-agent-core-65c2
```

После **Обновить Вью** inbox-поллер стартует сам. Дену достаточно держать Viu открытой.

## Старый односторонний handoff

`CURSOR_HANDOFF.md` остаётся — длинные размышления и логи. Inbox — для **исполняемых** задач.
