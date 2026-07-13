# Лаборатория Вью (Lab v1)

Два режима в одном окне:

| Режим | Кто | Что делает |
|-------|-----|------------|
| **Оператор** | Кнопки GUI | Экспорт, оверлей, inbox — скрипты, без «характера» |
| **Лаборатория** | Фон + чат | Cascadeur, web, journal, скрины, оценки |

## Cascadeur — headless?

**Нет.** У Cascadeur нет API/headless. Lab:

1. Запускает `Cascadeur.exe` (если закрыт)
2. Переносит окно на **3-й монитор** (`VIU_LAB_MONITOR=2`, нумерация с 0)
3. Кладёт sample FBX в `Library/Cascadeur/Inbox`
4. Делает **скрин окна** → `lab/cascadeur/artifacts/`
5. Пишет **journal.md** и просит **оценку**

Ден может смотреть на правый монитор, пока Вью «трудится».

## Пайплайн (6 шагов)

1. Статус (Inbox/Export/exe)
2. Web-исследование (docs, export FBX)
3. Sample FBX в Inbox
4. Запуск + монитор
5. Скрин UI
6. Отчёт → **awaiting_rating**

Прерывание: любая **кнопка GUI** или **«Обновить Вью»** → `paused`, journal сохранён.

## Оценки (1–5)

| Критерий | id |
|----------|-----|
| Техника | `technique` |
| Изобретательность | `creativity` |
| Старание | `effort` |
| Полезность | `usefulness` |
| Ясность отчёта | `clarity` |

GUI: **«Оценить лабораторию»** или инструмент `lab_rate`.

## Файлы

```
U:\Viu\.viu\lab\cascadeur\
  TASK.md       ← задание (не трогать без причины)
  session.json  ← шаг, статус, артефакты
  journal.md    ← ход мыслей
  artifacts\    ← PNG скрины
```

## Настройки

```env
VIU_LAB_VRAM_GB=6
VIU_LAB_MONITOR=2
VIU_LAB_INTERVAL_MIN=5
VIU_CASCADEUR_EXE=C:\Program Files\Cascadeur\Cascadeur.exe
```

`OLLAMA_MAX_VRAM` подсказывается при lab-шагах с web/LLM.

## Кнопки / инструменты

- **Лаборатория: Cascadeur** — `lab_start` + первый шаг
- **Оценить лабораторию** — форма оценок
- `lab_step`, `lab_status`, `lab_rate` — для чата/агента

В **автономном режиме** (меня нет) lab делает **+1 шаг** каждые `VIU_LAB_INTERVAL_MIN` минут, если не занят оператор.

## Отложено: NSFW / фанфик-референсы

Идея: читать **18+ fantasy** как учебник **сюжетных приёмов** (не пересказ), конспект в `lab/literature/`.

**Статус: записано, не включено.** Нужен явный флаг `VIU_LAB_NSFW_RESEARCH=1` и локальная папка `References/literature/` — реализуем отдельно, когда Ден скажет.

## Связанные документы

- [CASCADEUR.md](./CASCADEUR.md) — пути Inbox/Export
- [EYES.md](./EYES.md) — скрины окон
- [VIU_HEARTBEAT.md](./VIU_HEARTBEAT.md) — heartbeat ≠ lab
